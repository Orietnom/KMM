from __future__ import annotations
from kmm.ie_driver.ie_driver import KMMIEDriver
from dataclasses import dataclass
from typing import Optional
from kmm.helper.find_management import find_management

import time
import re

@dataclass(frozen=True)
class LoginParams:
    url: str
    username: str
    password: str

class KMMActions():
    def __init__(self, driver: KMMIEDriver | None = None, config = None):
        self.driver = driver or KMMIEDriver(config)
        self._started = False
    
    # --- lifecycle ---
    def start(self) -> None:
        if not self._started:
            self.driver.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self.driver.stop()
            self._started = False

    def __enter__(self) -> "KMMActions":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
    
    # --- Ações ---

    def login(self, params: LoginParams, management: str = 'freto'):
        self.start()
        
        print("Iniciando login")
        self.driver.open(params.url)
        self.driver.safe_type(locator="id:USUARIO", text=params.username)
        self.driver.safe_type(locator="id:SENHA", text=params.password)

        if 'levo' in management.lower().lstrip():
            self.driver.safe_click(locator="xpath://label[normalize-space()='Levolog Transportes']/input")
        else:
            self.driver.safe_click(locator="xpath://label[normalize-space()='Freto Log']/input")

        self.driver.safe_click(locator="xpath://button[@title='Entrar']")
        time.sleep(5)
        print("Fim do Login")
        
    def quick_access(self, term: str):
        self.start()

        print(f"Acessando menu {term} via acesso rápido")
        self.driver.wait_present("id:principal")
        self.driver.switch_to_frame(principal=True)
        self.driver.safe_type(locator="id:ACESSO_RAPIDO", text=term)
        self.driver.safe_click("xpath://button[contains(@class, 'botao-16x16')]")
        time.sleep(5)
        print("Fim do acesso rápido")

    def belgo_load_user_profile(self, user: str, management: str, freto_lotation: Optional[str] = None, levolog_lotation: Optional[str] = None):

        print("Realizando lotação do usuário")
        value = find_management(
            management=management,
            freto_lotation=freto_lotation,
            levolog_lotation=levolog_lotation
        )
        print(f"Filial {value}")
        self._load_user_profile(user=user, value=value)

    def arcelor_load_user_profie(self, user: str, management: str, center: str):
        if 'levo' in management.lower().lstrip():
            if 'mg' in center.lower().lstrip():
                value = 'LEVO LOG - FILIAL MG'
            else:
                value = 'LEVO LOG - MATRIZ SP'
        else:
            print("Filial diferente de Levolog")
            raise "Filial diferente de Levolog"

        self._load_user_profile(user=user, value=value)


    def _load_user_profile(self, user, value):
        self.driver.switch_to_frame(principal=False)
        self.driver.select_by_value("id:USUARIO", user)
        self.driver.safe_click("xpath://button[contains(@class, 'botao-16x16')]")
        user_lotation = self.driver.safe_get_attribute(locator=f"xpath://tr[td[normalize-space()='{value}']]", attribute='class')
        if not 'destaque' in user_lotation:
            self.driver.safe_click(
                f"xpath://tr[td[normalize-space()='{value}']]//button[.//img[@alt='Lotar']]"
            )
            alert_text = self.driver.accept_alert()
            time.sleep(3)

            if not 'lotado com sucesso' in alert_text:
                print("Falha")

    def _status_cte(self, cte: str, serie: str, driver_name: str) -> bool:
        self.driver.switch_to_frame(principal=False)
        self.driver.select_by_visible_text('id:CONHECIMENTO_TIPO_ID', 'Conhecimento de Complemento')
        self.driver.select_by_visible_text('id:TIPO_COMPLEMENTO_ID', 'CTe de Complemento')
        self.driver.safe_type('id:NUM_CONHECIMENTO_COMPLEMENTO', cte)
        self.driver.select_by_value('id:SERIE_COMPLEMENTO', serie)
        alert = self.driver.wait_alert(5)
        if alert:
            return False

        return True

    def emitting_cte(self, cte: str, serie: str, driver_name: str) -> bool:
        status = self._status_cte(cte, serie, driver_name)

        if not status:
            raise "CT-e de complemento já gerado"

        self._click_on_negotiation_menu()
        pass


    def _click_on_negotiation_menu(self):
        aba = self.driver.driver.find_element(self.driver._by('id'), "tbl_abas").find_elements(self.driver._by('tag'), "td")
        for td in aba:
            if "Negociação" in td.text:
                self.driver.execute_js("arguments[0].click();", td)
                break