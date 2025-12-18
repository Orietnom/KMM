# kmm_core/automation/drivers/kmm_ie_driver.py

from __future__ import annotations

import os
import time
import uuid
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union, Callable, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
)

# Selenium 3.141.0: DesiredCapabilities é o caminho mais estável para IE
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"src\.env")
# -----------------------------
# Configs / Tipos
# -----------------------------

@dataclass(frozen=True)
class IEDriverConfig:
    # Caminho opcional do IEDriverServer.exe; se None, usa o PATH
    driver_path: Optional[str] = os.getenv("WEBDRIVER_PATH")
    if not driver_path:
        raise ValueError("IEDRIVER_PATH não configurado")

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


Locator = Union[str, Tuple[str, str]]  # "id:foo" ou ("id", "foo")


class KMMIEDriver:
    """
    Wrapper “anti-caos” para Selenium + Internet Explorer.

    Regras:
      - Sem implicit wait (IE fica zumbi com isso)
      - Waits explícitos via WebDriverWait
      - safe_* com retry curto
      - dump_state para evidências
    """

    def __init__(self, config: Optional[IEDriverConfig] = None):
        self.config = config or IEDriverConfig()
        self._driver: Optional[WebDriver] = None

        # Garante pasta de evidências
        Path(self.config.evidence_dir).mkdir(parents=True, exist_ok=True)

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
        options.require_window_focus = self.config.require_window_focus
        options.native_events = self.config.native_events
        options.ensure_clean_session = self.config.ensure_clean_session

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
            # fallback para variações de assinatura dependendo do selenium build
            if self.config.driver_path:
                self._driver = webdriver.Ie(
                    self.config.driver_path,
                    capabilities=caps,
                )
            else:
                self._driver = webdriver.Ie(capabilities=caps)

        # Timeouts importantes
        self._driver.set_page_load_timeout(self.config.page_load_timeout)
        self._driver.set_script_timeout(self.config.script_timeout)

        # IMPORTANTÍSSIMO: não usar implicit wait
        self._driver.implicitly_wait(0)

        return self._driver

    def stop(self) -> None:
        if not self._driver:
            return

        try:
            self._driver.quit()
        except Exception:
            # IE é IE…
            pass
        finally:
            self._driver = None

        if self.config.kill_processes_on_stop:
            self._kill_ie_processes()

    def restart(self) -> WebDriver:
        self.stop()
        return self.start()

    # -----------------------------
    # Navegação / básicos
    # -----------------------------

    def open(self, url: str) -> None:
        self.driver.get(url)

    def refresh(self) -> None:
        self.driver.refresh()

    def current_url(self) -> str:
        try:
            return self.driver.current_url
        except Exception:
            return ""

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
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        return wait.until(EC.visibility_of_element_located((self._by(by), value)))

    def wait_present(self, locator: Locator, timeout: Optional[int] = None):
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        return wait.until(EC.presence_of_element_located((self._by(by), value)))

    def wait_clickable(self, locator: Locator, timeout: Optional[int] = None):
        by, value = self._parse_locator(locator)
        wait = WebDriverWait(self.driver, timeout or self.config.default_wait)
        return wait.until(EC.element_to_be_clickable((self._by(by), value)))

    # -----------------------------
    # safe_* com retry curto
    # -----------------------------

    def safe_find(self, locator: Locator, timeout: Optional[int] = None):
        try:
            return self.wait_present(locator, timeout=timeout)
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
        self._with_retry(
            fn=lambda: self._click_once(locator, timeout, use_js_fallback),
            retries=retries,
            backoff_s=backoff_s,
            on_fail_label="safe_click_fail",
        )

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
    ) -> None:
        def _type():
            el = self.wait_visible(locator, timeout=timeout)
            if clear_first:
                try:
                    el.clear()
                except Exception:
                    # alguns inputs no IE falham no clear()
                    self.driver.execute_script("arguments[0].value = '';", el)
            el.send_keys(text)

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
        def _get():
            el = self.wait_visible(locator, timeout=timeout)
            return (el.text or "").strip()

        return self._with_retry(
            fn=_get,
            retries=retries,
            backoff_s=backoff_s,
            on_fail_label="safe_get_text_fail",
        )

    def exists(self, locator: Locator, timeout: int = 2) -> bool:
        try:
            self.wait_present(locator, timeout=timeout)
            return True
        except TimeoutException:
            return False

    def _with_retry(
        self,
        fn: Callable[[], Any],
        on_fail_label: str,
        retries: int = 3,
        backoff_s: float = 1,
    ):
        last_exc = None
        for attempt in range(retries + 1):
            try:
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
        self.driver.switch_to.default_content()

    def switch_to_frame(self, locator: Locator, timeout: Optional[int] = None) -> None:
        frame = self.wait_present(locator, timeout=timeout)
        self.driver.switch_to.frame(frame)

    def switch_to_window(self, index: int = -1) -> None:
        handles = self.driver.window_handles
        if not handles:
            raise RuntimeError("Nenhuma janela disponível para switch.")
        self.driver.switch_to.window(handles[index])

    # -----------------------------
    # Evidências / Diagnóstico
    # -----------------------------

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
