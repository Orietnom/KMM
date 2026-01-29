from __future__ import annotations

import time
import uuid
import subprocess
import threading
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Union, Callable, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from src.exceptions.personalized_exceptions import HardTimeoutError
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
)

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from dotenv import load_dotenv
from src.shared.logger import logger

load_dotenv()
# -----------------------------
# Configs / Tipos
# -----------------------------

@dataclass(frozen=True)
class IEDriverConfig:
    # Caminho opcional do IEDriverServer.exe; se None, usa o PATH
    driver_path: Optional[str] = r"C:\IEDriverServer.exe"

    # Timeouts (segundos)
    page_load_timeout: int = 60
    script_timeout: int = 30
    default_wait: int = 20

    # Evidências
    evidence_dir: str = "output/evidence"

    # Políticas IE (ajuste conforme seu ambiente)
    ignore_zoom_level: bool = True
    ignore_protected_mode_settings: bool = True
    require_window_focus: bool = True
    native_events: bool = False
    ensure_clean_session: bool = True

    # Page load strategy: "normal" costuma ser mais previsível no IE
    page_load_strategy: str = "normal"

    # Mata processos no stop() se necessário
    kill_processes_on_stop: bool = True

    # Timeouts caso a ação venha a travar
    hard_timeout: int = int(os.getenv("KMM_HARD_TIMEOUT")) or 300
    hard_grace: int = 5


Locator = Union[str, Tuple[str, str]]  # "id:foo" ou ("id", "foo")


class KMMIEDriver:
    _HARD_WRAP = {
        "open", "refresh",
        "wait_visible", "wait_present", "wait_clickable", "wait_frame", "wait_alert", "wait_window_by_tile",
        "safe_find", "safe_click", "safe_type", "safe_get_text", "safe_get_attribute",
        "select_by_value", "select_by_index", "select_by_visible_text",
        "switch_to_frame", "switch_to_window", "accept_alert",
        "execute_js",
        "stop", "close_window", "start", "restart",
    }

    # métodos que NUNCA devem ser embrulhados
    _NO_WRAP = {
        "__getattribute__", "__getattr__", "_call_with_watchdog",
        "_kill_ie_processes", "dump_state",
        "_parse_locator", "_by", "_with_retry", "_click_once",
        "driver",
    }

    def __init__(self, config: Optional[IEDriverConfig] = None):
        self.config = config or IEDriverConfig()
        self._driver: Optional[WebDriver] = None
        Path(self.config.evidence_dir).mkdir(parents=True, exist_ok=True)
        self.cleanup_old_evidences(days=10)

    def __getattribute__(self, name: str):
        attr = object.__getattribute__(self, name)

        # não embrulhar métodos internos / mágicos
        if name.startswith("_") or name in object.__getattribute__(self, "_NO_WRAP"):
            return attr

        hard_wrap = object.__getattribute__(self, "_HARD_WRAP")
        if callable(attr) and name in hard_wrap:
            def wrapped(*args, **kwargs):
                return object.__getattribute__(self, "_call_with_watchdog")(name, attr, *args, **kwargs)
            return wrapped

        return attr

    def _call_with_watchdog(self, label: str, fn, *args, **kwargs):
        """
        Executa fn em outra thread e espera no máximo hard_timeout.
        Se estourar, mata IE/IEDriverServer e levanta HardTimeoutError.

        Observação: thread não é interrompida. O que destrava é matar os processos.
        """

        ht = int(getattr(self.config, "hard_timeout", 300))
        grace = int(getattr(self.config, "hard_grace", 5))
        timeout_total = ht + grace

        result_box = {"value": None, "exc": None}

        def runner():
            try:
                result_box["value"] = fn(*args, **kwargs)
            except Exception as e:
                result_box["exc"] = e

        t = threading.Thread(target=runner, daemon=True)
        t.start()

        # Espera "hard timeout"
        t.join(timeout_total)
        logger.debug(f"Inicio {datetime.now().time()}")

        # Se ainda estiver rodando, consideramos travado
        if t.is_alive():
            # tenta evidência
            try:
                self.dump_state(f"hard_timeout_{label}")
            except Exception:
                pass
            self._kill_ie_processes()
            raise HardTimeoutError(f"Hard timeout em {label} ({timeout_total}s)")

        # Se terminou, ou retornou valor, ou lançou exceção
        if result_box["exc"] is not None:
            raise result_box["exc"]

        logger.debug(f"Fim {datetime.now().time()}")
        return result_box["value"]

    # -----------------------------
    # Ciclo de vida
    # -----------------------------

    @property
    def driver(self) -> WebDriver:
        if not self._driver:
            raise RuntimeError("Driver IE não iniciado. Chame start() antes.")
        return self._driver

    def start(self) -> WebDriver:
        if self._driver:
            return self._driver
        caps = DesiredCapabilities.INTERNETEXPLORER.copy()
        caps["pageLoadStrategy"] = self.config.page_load_strategy
        caps["ignoreProtectedModeSettings"] = True
        caps["ignoreZoomSetting"] = True
        caps["requireWindowFocus"] = True
        caps["nativeEvents"] = False
        caps["ie.ensureCleanSession"] = True
        caps["ie.browserCommandLineSwitches"] = "-private"

        # Opções do IE (Selenium 3)
        options = webdriver.IeOptions()
        options.ignore_zoom_level = self.config.ignore_zoom_level
        options.ignore_protected_mode_settings = self.config.ignore_protected_mode_settings

        # Cria driver
        try:
            if self.config.driver_path:
                self._driver = webdriver.Ie(
                    executable_path=self.config.driver_path,
                    capabilities=caps,
                    options=options,
                )
            else:
                self._driver = webdriver.Ie(
                    capabilities=caps,
                    options=options,
                )
        except TypeError:

            if self.config.driver_path:
                self._driver = webdriver.Ie(
                    self.config.driver_path,
                    capabilities=caps,
                )
            else:
                self._driver = webdriver.Ie(capabilities=caps)

        # Timeouts
        self._driver.set_page_load_timeout(self.config.page_load_timeout)
        self._driver.set_script_timeout(self.config.script_timeout)

        # IMPORTANTÍSSIMO: não usar implicit wait
        self._driver.implicitly_wait(0)

        self.home_page_id = self._driver.current_window_handle
        return self._driver

    def stop(self) -> None:
        if not self._driver:
            return

        try:
            self._driver.quit()
        except Exception:
            pass
        finally:
            self._driver = None

        if self.config.kill_processes_on_stop:
            self._kill_ie_processes()

    def restart(self) -> WebDriver:
        logger.debug("Reiniciando navegador")
        self.stop()
        driver = self.start()
        logger.debug("Finalizado")
        return driver

    def _start_watchdog(self, seconds: int, label: str):
        """
        Dispara um Timer que, ao estourar, tenta derrubar o IE/Driver para destravar chamadas travadas.
        Retorna (timer, fired_event).
        """
        fired = threading.Event()

        def _boom():
            # marca que explodiu
            fired.set()
            self._hard_timeout_fired = True

            # tenta evidências (pode falhar se estiver travado)
            try:
                self.dump_state(f"hard_timeout_{label}")
            except Exception:
                pass

            # tenta quit e depois mata processos (modo “sem misericórdia”)
            try:
                if self._driver:
                    try:
                        self._driver.quit()
                    except Exception:
                        pass
            finally:
                if self.config.kill_processes_on_stop:
                    self._kill_ie_processes()

        t = threading.Timer(seconds, _boom)
        t.daemon = True
        t.start()
        return t, fired

    @staticmethod
    def _cancel_watchdog(timer: threading.Timer):
        try:
            timer.cancel()
        except Exception:
            pass

    # -----------------------------
    # Navegação / básicos
    # -----------------------------

    def open(self, url: str) -> None:
        logger.debug(f"Navegando para {url}")
        self.driver.get(url)
        logger.debug("Finalizado")

    def refresh(self) -> None:
        logger.debug("Atualizando a pagina")
        self.driver.refresh()
        logger.debug("Finalizado")

    def current_url(self) -> str:
        try:
            logger.debug("Obtendo URL da pagina atual")
            return self.driver.current_url
        except Exception:
            return ""
        finally:
            logger.debug("Finalizado")

    def close_window(self):
        logger.debug(self.driver.window_handles)
        for page in self.driver.window_handles:
            if page != self.home_page_id:
                self.driver.switch_to.window(page)
                logger.debug(self.driver.title)
                self.driver.close()

    # -----------------------------
    # Locator parser
    # -----------------------------

    def _parse_locator(self, locator: Locator) -> Tuple[str, str]:
        if isinstance(locator, tuple):
            by, value = locator
            return by.lower(), value

        if isinstance(locator, str) and ":" in locator:
            prefix, value = locator.split(":", 1)
            return prefix.strip().lower(), value.strip()

        raise ValueError(f"Locator inválido: {locator!r} (use 'id:foo' ou ('id','foo'))")

    def _by(self, by: str) -> str:
        mapping = {
            "id": By.ID,
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "name": By.NAME,
            "tag": By.TAG_NAME,
            "class": By.CLASS_NAME,
            "link": By.LINK_TEXT,
            "plink": By.PARTIAL_LINK_TEXT,
        }
        if by not in mapping:
            raise ValueError(f"Tipo de locator não suportado: {by}")
        return mapping[by]

    # -----------------------------
    # Waits
    # -----------------------------

    def wait_visible(self, locator: Locator, timeout: Optional[int] = None):
        logger.debug("Aguardando elemento estar visivel")
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        element = wait.until(EC.visibility_of_element_located((self._by(by), value)))
        logger.debug("Fim do método wait")
        return element

    def wait_present(self, locator: Locator, timeout: Optional[int] = None):
        logger.debug("Aguardando elemento estar presente")
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        element = wait.until(EC.presence_of_element_located((self._by(by), value)))
        logger.debug("Fim do método wait")
        return element

    def wait_clickable(self, locator: Locator, timeout: Optional[int] = None):
        logger.debug("Aguardando elemento estar clicavel")
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        element = wait.until(EC.element_to_be_clickable((self._by(by), value)))
        logger.debug("Fim do método wait")
        return element

    def wait_frame(self, locator: Locator, timeout: Optional[int] = None):
        logger.debug("Aguardando frame estar disponível")
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        element = wait.until(EC.frame_to_be_available_and_switch_to_it((self._by(by), value)))
        logger.debug("Fim do método wait")
        return element

    def wait_alert(self, timeout: Optional[int] = None) -> Any:
        logger.debug("Aguardando alerta aparecer")
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        try:
            element = wait.until(EC.alert_is_present())
        except TimeoutException:
            logger.debug("Alerta não apareceu")
            return False
        logger.debug("Fim do método wait")
        return element

    def wait_window_by_tile(self, target_title: str, timeout: Optional[int] = None):
        logger.debug(f"Aguardando janela {target_title} aparecer")
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)

        element = wait.until(lambda d: any((d.switch_to.window(h) or True) and target_title in (d.title or "").lower()
        for h in d.window_handles
        ))
    # -----------------------------
    # safe_* com retry curto
    # -----------------------------

    def safe_find(self, locator: Locator, timeout: Optional[int] = None):
        try:
            logger.debug(f"Procurando um elemento: {locator} com timeout {timeout}")
            element = self.wait_present(locator, timeout=timeout)
            logger.debug("Finalizado")
            return element
        except TimeoutException as e:
            self.dump_state("safe_find_timeout")
            raise e

    def safe_click(
        self,
        locator: Locator,
        timeout: Optional[int] = None,
        retries: int = 2,
        backoff_s: float = 0.6,
        use_js_fallback: bool = True,
    ) -> None:
        logger.debug(f"Clicado no elemento: {locator} com timeout {timeout}, retries {retries} e backoff de {backoff_s} segunndos")

        self._with_retry(
            fn=lambda: self._click_once(locator, timeout, use_js_fallback),
            retries=retries,
            backoff_s=backoff_s,
            on_fail_label="safe_click_fail",
        )
        logger.debug("Finalizado")

    def _click_once(self, locator: Locator, timeout: Optional[int], use_js_fallback: bool) -> None:
        el = self.wait_clickable(locator, timeout=timeout)
        try:
            el.click()
        except (ElementClickInterceptedException, ElementNotInteractableException, WebDriverException):
            if not use_js_fallback:
                raise
            # Fallback JS (IE às vezes precisa)
            self.driver.execute_script("arguments[0].click();", el)

    def safe_type(
        self,
        locator: Locator,
        text: str,
        timeout: Optional[int] = None,
        clear_first: bool = True,
        retries: int = 2,
        backoff_s: float = 0.6,
        time_between_types: float = None
    ) -> None:
        logger.debug(f"Escrevendo texto no elemento: {locator} com timeout {timeout}, retries {retries} e backoff de {backoff_s} segunndos")
        def _type():
            el = self.wait_visible(locator, timeout=timeout)
            if clear_first:
                try:
                    el.clear()
                    el.click()
                except Exception:
                    self.driver.execute_script("arguments[0].value = '';", el)
            if time_between_types:
                for char in text:
                    el.send_keys(char)
                    time.sleep(time_between_types)
            else:
                el.send_keys(text)
            logger.debug("Finalizado")

        self._with_retry(
            fn=_type,
            retries=retries,
            backoff_s=backoff_s,
            on_fail_label="safe_type_fail",
        )

    def safe_get_text(
        self,
        locator: Locator,
        timeout: Optional[int] = None,
        retries: int = 2,
        backoff_s: float = 0.4,
    ) -> str:
        logger.debug(f"Obtendo texto do elemento: {locator} com timeout {timeout}, retries {retries} e backoff de {backoff_s} segunndos")
        def _get():
            el = self.wait_visible(locator, timeout=timeout)
            logger.debug("Finalizado")
            return (el.text or "").strip()

        return self._with_retry(
            fn=_get,
            retries=retries,
            backoff_s=backoff_s,
            on_fail_label="safe_get_text_fail",
        )

    def safe_get_attribute(
            self,
            locator: Locator,
            attribute: str,
            timeout: Optional[int] = None,
            retries: int = 2,
            backoff_s: float = 0.4
            ):
        logger.debug(f"Obtendo atributo {attribute} do locator {locator} com timeout {timeout}, retries {retries} e backoff de {backoff_s} segunndos")
        def _get():
            el = self.wait_present(locator=locator, timeout=timeout)
            logger.debug("Finalizado")
            return (el.get_attribute(attribute))

        return self._with_retry(
            fn=_get,
            retries=retries,
            backoff_s=backoff_s,
            on_fail_label="safe_get_attributes_fail"
        )

    def exists(self, locator: Locator, timeout: int = 2) -> bool:
        try:
            logger.debug(f"Verificando se o locator {locator} existe")
            self.wait_present(locator, timeout=timeout)
            logger.debug("Finalizado")
            return True
        except TimeoutException:
            return False

    def _with_retry(
        self,
        fn: Callable[[], Any],
        on_fail_label: str,
        retries: int = 3,
        backoff_s: float = 1
    ):
        last_exc = None
        for attempt in range(retries + 1):
            timer = None
            fired = None
            try:
                logger.debug(f"Tentativa {attempt + 1}")

                return fn()
            except (StaleElementReferenceException, WebDriverException, TimeoutException, NoSuchElementException) as e:
                last_exc = e

                if attempt < retries:
                    time.sleep(backoff_s * (attempt + 1))
                    continue
                self.dump_state(on_fail_label)
                raise last_exc

        if last_exc:
            raise last_exc
        raise RuntimeError("Retry failed without captured exception")

    # -----------------------------
    # Frames / Windows
    # -----------------------------

    def switch_to_default(self) -> None:
        logger.debug("Trocando para o conteúdo principal da DOM")
        self.driver.switch_to.default_content()
        logger.debug("Sucesso")

    def switch_to_frame(self, principal: bool = True, timeout: Optional[int] = None) -> None:

        self.driver.switch_to.default_content()

        logger.debug("Entrando no frame principal")
        self.wait_frame(locator='id:principal', timeout=timeout)

        time.sleep(0.2)
        if not principal:
            logger.debug("Entrando no frame iconteudo")
            self.wait_frame(locator='name:iconteudo', timeout=timeout)

        logger.debug("Sucesso")

    def switch_to_window(self, target_title: str = None, timeout: Optional[int] = None, home_window: bool = False) -> bool:

        if home_window:
            self.driver.switch_to.window(self.home_page_id)
            return True
        target = target_title.lower()

        logger.debug(f"Pulando para janela => {target_title}")

        try:
            self.wait_window_by_tile(target_title=target, timeout=timeout)
        except TimeoutException:
            logger.debug(f"Janela com título contendo '{target_title}' em {timeout}s não encontrada")
            return False

        for h in self.driver.window_handles:
            self.driver.switch_to.window(h)
            if target in (self.driver.title or "").lower():
                logger.debug(f"Janela encontrada e ativada => {self.driver.title}")
                return True

        return False

    def accept_alert(self) -> str:
        logger.debug("Aceitando um Alert")
        alert = self.wait_alert()
        text = alert.text
        alert.accept()
        logger.debug(f"Texto do alerta {text}")
        return text

    # -----------------------------
    # Selects
    # -----------------------------

    def select_by_value(self, locator: Locator, value:str, timeout: Optional[int] = None) -> None:
        logger.debug(f"Selecionando {value} no locator {locator} com timeout de {timeout}")
        el = self.wait_present(locator=locator, timeout=timeout)
        Select(el).select_by_value(value=value)

    def select_by_index(self, locator: Locator, index:int, timeout: Optional[int] = None) -> None:
        logger.debug(f"Selecionando por index {index} no locator {locator} com timeout de {timeout}")
        el = self.wait_present(locator=locator, timeout=timeout)
        Select(el).select_by_index(index=index)

    def select_by_visible_text(self, locator: Locator, value:str, timeout: Optional[int] = None) -> None:
        logger.debug(f"Selecionando {value} no locator {locator} com timeout de {timeout}")
        el = self.wait_present(locator=locator, timeout=timeout)
        Select(el).select_by_visible_text(text=value)

    #
    # Execute javascript
    #

    def execute_js(self, script:str, arguments = None):
        if arguments:
            self.driver.execute_script(script, arguments)
        else:
            self.driver.execute_script(script)

    # -----------------------------
    # Evidências / Diagnóstico
    # -----------------------------

    def cleanup_old_evidences(self, days: int = 10):
        evidence_dir = Path(self.config.evidence_dir)
        if not evidence_dir.exists():
            return

        limite = datetime.now() - timedelta(days=days)

        for file in evidence_dir.iterdir():
            if not file.is_file():
                continue

            mtime = datetime.fromtimestamp(file.stat().st_mtime)

            if mtime < limite:
                try:
                    file.unlink()
                except Exception:
                    pass

    def dump_state(self, label: str = "state") -> dict:
        """
        Gera evidências no evidence_dir:
          - screenshot png
          - html
          - metadados (url)
        Retorna dict com paths.
        """
        uid = uuid.uuid4().hex[:10]
        base = Path(self.config.evidence_dir) / f"{int(time.time())}_{label}_{uid}"
        png_path = str(base) + ".png"
        html_path = str(base) + ".html"
        meta_path = str(base) + ".txt"

        url = ""
        try:
            url = self.driver.current_url
        except Exception:
            pass

        try:
            self.driver.save_screenshot(png_path)
        except Exception:
            pass

        try:
            html = self.driver.page_source
            Path(html_path).write_text(html, encoding="utf-8", errors="ignore")
        except Exception:
            pass

        try:
            Path(meta_path).write_text(f"url={url}\n", encoding="utf-8", errors="ignore")
        except Exception:
            pass

        return {"png": png_path, "html": html_path, "meta": meta_path, "url": url}

    # -----------------------------
    # Kill de processos (opcional, mas salva vidas)
    # -----------------------------

    def _kill_ie_processes(self) -> None:
        # Windows only
        try:
            subprocess.run(["taskkill", "/F", "/IM", "iexplore.exe"], capture_output=True, text=True)
            subprocess.run(["taskkill", "/F", "/IM", "IEDriverServer.exe"], capture_output=True, text=True)
        except Exception:
            pass

    # -----------------------------
    # Disponibiliza metodos do selenium
    # -----------------------------

    def __getattr__(self, name: str):
        """
        Se alguém chamar kmm.find_element(...), e não existir no wrapper,
        delega para o self.driver do Selenium.
        """
        # Evita loop se driver ainda não iniciou
        if name == "_driver":
            raise AttributeError(name)

        drv = object.__getattribute__(self, "_driver")
        if drv is None:
            raise AttributeError(
                f"'{self.__class__.__name__}' não tem '{name}' (e o driver ainda não foi iniciado). "
                f"Chame start() antes."
            )

        attr = getattr(drv, name)  # pega do Selenium WebDriver
        return attr
