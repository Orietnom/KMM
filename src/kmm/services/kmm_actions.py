from __future__ import annotations
from kmm.ie_driver.ie_driver import KMMIEDriver
from dataclasses import dataclass
from typing import Optional, Any
from kmm.helper.find_management import find_management
from kmm.helper.str_handler import str_to_float
from kmm.helper.kmm_password_generator import password_generate
import time
from urllib.parse import unquote
import exceptions.personalized_exceptions as pe
import re
from shared.logger import logger

@dataclass(frozen=True)
class LoginParams:
    url: str
    username: str
    password: str

class KMMActions:
    def __init__(self, service: str, driver: KMMIEDriver | None = None, config = None):
        self.driver = driver or KMMIEDriver(config)
        self._started = False
        self.log = logger.bind(service=service)
    
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
        try:
            self.start()

            self.log.info("Iniciando login")
            self.driver.open(params.url)
            self.driver.safe_type(locator="id:USUARIO", text=params.username)
            self.driver.safe_type(locator="id:SENHA", text=params.password)

            if 'levo' in management.lower().lstrip():
                self.driver.safe_click(locator="xpath://label[normalize-space()='Levolog Transportes']/input")
            else:
                self.driver.safe_click(locator="xpath://label[normalize-space()='Freto Log']/input")

            self.driver.safe_click(locator="xpath://button[@title='Entrar']")
            time.sleep(5)
            self.log.info("Fim do Login")
        except Exception as e:
            raise pe.KMMLoginError(
                f"Erro ao realizar o login no KMM | Usuario: {params.username} - Filial: {management}"
            ) from e
        
    def quick_access(self, term: str):

        try:
            self.driver.switch_to_default()
            self.log.info(f"Acessando menu {term} via acesso rápido")
            self.driver.wait_present("id:principal")
            self.driver.switch_to_frame(principal=True)
            self.driver.safe_type(locator="id:ACESSO_RAPIDO", text=term)
            self.driver.safe_click("xpath://button[contains(@class, 'botao-16x16')]")
            time.sleep(5)
            self.log.info("Fim do acesso rápido")
        except Exception as e:
            raise pe.KMMQuickAccessError(
                f"Falha ao acessar o menu {term} via acesso rápido."
            ) from e

    def belgo_load_user_profile(self, user: str, management: str, lotation: str):

        try:
            self.quick_access('lot')
            self.log.info("Realizando lotação do usuário")
            value = find_management(
                management=management,
                lotation=lotation
            )
            self.log.info(f"Filial {value}")
            self._load_user_profile(user=user, value=value)
        except Exception as e:
            raise pe.KMMBelgoLoadUserProfileError(
                f"Falha ao realizar lotação para o usuário {user} para a filial {management}"
            ) from e

    def arcelor_load_user_profile(self, user: str, management: str, center: str):

        try:
            if 'levo' in management.lower().lstrip():
                if 'mg' in center.lower().lstrip():
                    value = 'LEVO LOG - FILIAL MG'
                else:
                    value = 'LEVO LOG - MATRIZ SP'
            else:
                self.log.info("Filial diferente de Levolog")
                raise Exception("Filial diferente de Levolog")

            self._load_user_profile(user=user, value=value)
        except Exception as e:
            raise pe.KMMArcelorLoadUserProfileError(
                f"Falha ao realizar lotação para o usuário {user} filial {management}"
            ) from e


    def _load_user_profile(self, user, value):
        try:
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
                    raise Exception(f"Falha ao lotar o usuário: {user} com filial {value}")
        except Exception as e:
            raise Exception(f"Falha ão mapeada ao lotar o usuário: {user}") from e

    def _status_cte(self, cte: str, serie: str) -> Any:
        try:
            self.driver.switch_to_frame(principal=False)
            self.driver.select_by_visible_text('id:CONHECIMENTO_TIPO_ID', 'Conhecimento de Complemento')
            self.driver.select_by_visible_text('id:TIPO_COMPLEMENTO_ID', 'CTe de Complemento')
            self.driver.safe_type('id:NUM_CONHECIMENTO_COMPLEMENTO', cte)
            self.driver.select_by_value('id:SERIE_COMPLEMENTO', serie)
            alert = self.driver.wait_alert(5)
            if alert:
                self.log.info(alert.text)
                return alert.text
            return False
        except Exception as e:
            raise pe.KMMStatusCteError(
                f"Falha ao obter o status do cte para gerar o comploemento. Cte {cte} Serie {serie}"
            ) from e

    def _get_driver_name(self) -> str | None:
        for i in range(10):
            self.driver.switch_to_frame(principal=False)
            self.driver.safe_get_text(locator='id:MOTORISTA')
            kmm_driver_name = self.driver.safe_get_attribute(locator='id:MOTORISTA', attribute='value')
            if kmm_driver_name:
                return kmm_driver_name.lower().lstrip()
            else:
                time.sleep(1)
        return None

    def _get_taxes(self) -> float:

        try:
            self.driver.switch_to_frame(principal=False)
            self.driver.safe_click('id:td_impostos_title', timeout=60)
            time.sleep(3)
            tax_table = self.driver.wait_present('id:tb_lista_IMPOSTOS')
            rows = tax_table.find_elements(self.driver._by('css'), "tr[id^='tr_lista_IMPOSTOS_']")

            for row in rows:
                cols = row.find_elements(self.driver._by('css'), "td.linha_1")
                if not cols:
                    continue
                for idx, col in enumerate(cols):
                    if 'icms' in col.text.lower():
                        idx = row.get_attribute("id").split("_")[-1]
                        icms_aliquota = row.find_element(self.driver._by('id'), f"ALIQUOTA_IMPOSTOS_{idx}").get_attribute(
                            "value")
                        icms_descricao = row.find_element(self.driver._by('id'), f"DESCRICAO_IMPOSTOS_{idx}").get_attribute(
                            "value")

                        if 'presumido' not in icms_descricao:
                            self.log.info(f"Imposto encontrado: {icms_descricao} com alíquota {icms_aliquota}")
                            return str_to_float(icms_aliquota)
        except Exception as e:
            raise pe.KMMGetTaxesError("Não foi possível obter os impostos.") from e

        raise pe.KMMGetTaxesError("Falha não mapeada ao obter os impostos.")

    def _click_on_negotiation_menu(self):
        try:
            aba = self.driver.driver.find_element(self.driver._by('id'), "tbl_abas").find_elements(self.driver._by('tag'), "td")
            for td in aba:
                if "Negociação" in td.text:
                    self.driver.execute_js("arguments[0].click();", td)
                    return

            raise Exception("Não foi possível clicar no menu negociação")
        except Exception as e:
            raise Exception("Falha não mapeada ao clicar no menu negociação") from e

    def emitting_cte(
            self,
            cte: str,
            serie: str,
            cte_value: float,
            management: str,
            driver_name: str = None,
            markup: float = None,
            taxes: bool = False,
            incident_number: Optional[int] = 1
    ) -> str:

        try:
            self.quick_access('ectecomp')
            status = self._status_cte(cte, serie)

            if not status:
                raise pe.KMMStatusCteError(f"Problema ao verificar status do CTE. Pop-up não apareceu")
            elif isinstance(status, str):
                if not incident_number:
                    raise pe.KMMStatusCteError(f"Problema ao verificar status do CTE. Alerta {status}")

                kmm_incident_number = re.findall("\d+", status)[0]
                kmm_incident_number = int(kmm_incident_number[0]) if kmm_incident_number else 0
                if kmm_incident_number >= incident_number:
                    raise pe.KMMComplementCTEAlreadyEmitted(
                        f"Numero de ctes emitidos maior ou igual a quantidade de incidentes no portal. Incidentes no "
                        f"portal {incident_number} no KMM {kmm_incident_number}"
                    )

            if driver_name:
                kmm_driver_name = self._get_driver_name()
                if not kmm_driver_name == driver_name.lower():
                    self.log.error("Nome do motorista divergente. Nome no portal BBA -> {driver_name} Nome no KMM ->: {kmm_driver_name}")
                    raise pe.KMMGetDriverNameError(
                        f"Nome do motorista divergente. Nome no portal BBA: {driver_name} - Nome no KMM: {kmm_driver_name}"
                    )

            if taxes:
                icms = self._get_taxes()
                value_with_no_tax = round((cte_value * (1 - (icms / 100))), 2)
            else:
                value_with_no_tax = cte_value

            self._click_on_negotiation_menu()

            if 'freto' in management:
                str_value_with_no_tax = f"{value_with_no_tax:.2f}"

                self.driver.execute_js(
                    f"""
                        document.getElementById('VARIAVEL_VALORUNITARIOFRETE_CALC').value = '{str_value_with_no_tax}'
                        document.getElementById('VARIAVEL_VALORUNITARIOFRETE').value = '{str_value_with_no_tax}'; 
                        f_calculos();
                    """
                )
                time.sleep(7)
                saved_value = self.driver.safe_get_attribute('id:VARIAVEL_VALORUNITARIOFRETE_CALC', 'value')

                if saved_value != str_value_with_no_tax:
                    raise Exception("KMM com falha ao salvar o valor inserido no campo Valor Frete Unitário")

            else:
                if not markup:
                    raise Exception("Filial levolog sem markup")
                if 1 < markup <= 100:
                    markup /= 100

                net_value = round(value_with_no_tax * markup, 2)
                str_net_value = f"{net_value:.2f}"
                self.driver.execute_js(
                    f"""document.getElementById('VARIAVEL_FRETEPESO_CALC').value = '{str_net_value}';
                       document.getElementById('VARIAVEL_FRETEPESO').value = '{str_net_value}';
                       f_calculos();
                    """
                )

                saved_value = self.driver.safe_get_attribute('id:VARIAVEL_FRETEPESO_CALC', 'value')

                if saved_value != str_net_value:
                    raise Exception("KMM com falha ao salvar o valor inserido no campo Valor Frete Unitário")

            self.driver.switch_to_frame(principal=True)

            self.driver.safe_click('id:btn_confirmar')
            alert = self.driver.wait_alert(10)
            if not alert:
                window = self.driver.switch_to_window("Alerta", timeout=10)
                if window:
                    message = self.driver.safe_get_attribute('name:MENSAGEM', 'value')
                    decoded_message = unquote(message)
                    raise Exception(f"Não foi possível emitir o CT-e de complemento devido a: {decoded_message}")
                raise pe.KMMEmittingCTeError("Pop-up de confirmação não apareceu")

            window = self.driver.switch_to_window(target_title="Engenharia de Sistemas")

            if not window:
                raise Exception(f"Janela com o cte de complemento não encontrado")
            self.driver.switch_to_frame(principal=False)

            cte_complement = self.driver.safe_get_text("xpath:/html/body/form/table/tbody/tr[1]/td[1]/fieldset/table/tbody/tr[2]/td[2]")
            self.driver.close_window()
            self.driver.switch_to_window(home_window=True)
            return cte_complement
        except pe.KMMProcess:
            raise
        except Exception as e:
            raise pe.KMMEmittingCTeError(
                f"Falha ao emitir CTe de complemento para o Cte {cte} Serie {serie} Valor {cte_value} Filial {management}"
                f"Motorista {driver_name}."
            ) from e

    def _get_contract_number(self) -> str:
        try:
            for _ in range(18):

                self.log.info("Obtendo o número do contrato através do retorno da REPOM")

                contract_number = self.driver.safe_get_text(
                    "xpath:/html/body/form/table/tbody/tr/td/fieldset/table/tbody/tr[3]/td[2]"
                )

                if contract_number:
                    self.log.info("Contrato obtido com sucesso")
                    self.driver.close_window()
                    self.driver.switch_to_window(home_window=True)
                    return contract_number

                self.log.info("Número do encontrado ainda não disponível...")

                time.sleep(10)
                self.driver.safe_click(
                    "xpath:/html/body/form/table/tbody/tr/td/fieldset/table/tbody/tr[8]/td[2]/button"
                )

            self.log.error("Tempo de 180 segundos excedido")
            raise Exception("Falha ao obter o retorno da REPOM. Tempo de 180 segundos excedido ")
        except Exception as e:
            raise Exception("Falha não esperada") from e

    def _find_contract_number_window_handle(self) -> bool:
        
        for handle in self.driver.window_handles:

            self.log.info("Procurando pela janela que aparece o numero do contrato")

            self.driver.switch_to.window(handle)
            title = self.driver.title

            if not (("Engenharia de Sistemas" in title) | ("Sistema KMM" in title)):
                continue
                
            if "Engenharia de Sistemas" in title:

                title = self.driver.safe_get_text("id:td_titulo_pagina")

                if "integrar contrato" in title.lower():
                    self.log.info("Janela encontrada!")
                    return True
        
        return False

    def emitting_contract_repomfretea(
            self,
            license_plate: str,
            driver_name: str,
            nature: str,
            operation: str,
            route: str,
            card: str,
            sender: str,
            recipient: str,
            liberation_user: str,
            control_number: int,
            weight: Optional[str] = None,
            contract_value: Optional[str] = None,
            max_retries: int = 2
    ):

        try:
            for attempt in range(1, max_retries + 1):
                try:
                    self.quick_access('REPOMFRETEA')

                    self.driver.switch_to_frame(principal=False)
                    self.driver.safe_type('id:PLACA_CONTROLE', license_plate)

                    kmm_driver_name = self._get_driver_name()

                    if not kmm_driver_name:
                        raise pe.KMMGetDriverNameError("Falha ao obter o nome do motorista")

                    if kmm_driver_name != driver_name.lower().lstrip():
                        raise Exception("Divergência no nome do motorista")

                    self.driver.safe_type('id:NUM_NATUREZA', nature)
                    self.driver.safe_type('id:OPERACAO_ID', operation)
                    self.driver.safe_type('id:ROTA_ID', route)

                    self.driver.select_by_value('id:UTILIZA_VALE_PEDAGIO', '0')
                    self.driver.safe_type('id:CARTAO_NUMERO', card)
                    self.driver.safe_type('id:REM_CNPJ', sender)
                    self.driver.safe_type('id:DEST_CNPJ', recipient)

                    if contract_value is not None:
                        time.sleep(15)
                        self.driver.safe_type('id:VALOR_UNITARIO', contract_value)
                        self.driver.safe_type('id:PESO', '1')
                        self.driver.safe_type('id:VOLUME', '1')

                    if weight is not None:
                        self.driver.safe_type('id:PESO', weight)
                        self.driver.safe_type('id:VOLUME', weight)

                    self.driver.select_by_value('id:CON_UNIDADE_COMBO', 'Kg')

                    self.driver.safe_type('id:USUARIO_LIBERACAO', liberation_user)

                    kmm_pass = password_generate(license_plate=license_plate, control_number=control_number)
                    self.driver.safe_type('id:SENHA_LIBERACAO', kmm_pass)
                    self.driver.safe_type('id:OBSERVACAO', '.')
                    self.driver.safe_click('id:btn_confirmar')

                    alert = self.driver.wait_alert(timeout=30)
                    alert_text = alert.text.lower()
                    if "sucesso" in alert_text:
                        self.log.info("Contrato enviado a REPOM, aguardando retorno do número do contrato")

                    else:
                        raise pe.KMMEmittingContractError(f"Falha ao gerar o contrato. Mensagem da pop-up: {alert_text}")

                    contract_window = self._find_contract_number_window_handle()
                    if not contract_window:
                        self.driver.refresh()
                        continue

                    self.driver.switch_to_frame(principal=False)

                    contract_number = self._get_contract_number()
                    self.driver.switch_to_window(home_window=True)
                    return contract_number

                except Exception as e:
                    if attempt == max_retries:
                        raise
                    self.log.error(f"Falha ao gerar o contrato, tentando novamente. Erro => {str(e)}")
                    self.driver.switch_to_window(home_window=True)
                    self.driver.refresh()
                    self.quick_access(term="REPOMFRETED")

        except pe.KMMProcess:
            raise
        except Exception as e:
            raise pe.KMMEmittingContractError(
                f"Falha ao gerar o contrato. placa {license_plate}, motorista {driver_name}, natureza {nature}, operação {operation}, rota {route} "
                f"cartao {card}, remetente {sender}, destinatario {recipient}, peso {weight}, valor do contrato {contract_value} "
            ) from e

    def emitting_contract_repomfreted(
            self,
            contract_value: str,
            complement_cte: str,
            serie:str,
            submotive: str,
            transport: str,
            liberation_user: str,
            control_number: int = 17,
            max_retries: int = 2
    ):

        try:
            for attempt in range(1, max_retries + 1):

                try:
                    self.quick_access('REPOMFRETED')
                    self.log.info(f"Tentativa {attempt} de gerar o contrato")

                    self.driver.switch_to_frame(principal=False)
                    self.driver.wait_present('id:TIPO_DIARIA', 180)

                    self.log.info("Preenchendo formulário do contrato")


                    self.driver.select_by_value('id:TIPO_DIARIA', '1')
                    self.driver.safe_type("id:DIARIA_NUM_CTRC", complement_cte)
                    self.driver.select_by_value('id:CTRC_DIARIA_SERIE', serie)
                    self.driver.safe_type("id:ROTA_ID", '15')
                    self.driver.execute_js('f_busca_rota()')
                    self.driver.safe_type('id:VALOR_UNITARIO', contract_value)
                    self.log.info(f"Valor do contrato => {contract_value}")

                    time.sleep(5)
                    self.driver.select_by_value("id:USUARIO_LIBERACAO", liberation_user)

                    license_plate = None
                    for _ in range(2):
                        license_plate = self.driver.safe_get_attribute('id:PLACA_CONTROLE', 'value', timeout=15)
                        if not license_plate:
                            if _ == 1:
                                raise Exception("Não foi possível obter a placa do veículo")
                            time.sleep(2)
                            continue
                        else:
                            break

                    self.log.info(f"Placa => {license_plate}")

                    kmm_pass = password_generate(license_plate=license_plate[-2::], control_number=control_number, p6=False)
                    self.driver.safe_type('id:SENHA_LIBERACAO', kmm_pass)
                    self.driver.safe_type('id:OBSERVACAO', f"TR: {transport} \nMOTIVO: {submotive.upper()}")
                    time.sleep(3)
                    self.driver.execute_js('f_change_valor_unitario(true);')

                    self.driver.switch_to_frame(principal=True)
                    self.driver.safe_click('id:btn_confirmar')

                    self.log.info("Formulário preenchido e botão de confirmar clicado com sucesso.")

                    alert = self.driver.wait_alert(180)

                    if not alert:
                        raise Exception("Pop-up não apareceu")

                    alert_text = alert.text.lower()
                    if "sucesso" in alert_text:
                        self.log.info("Contrato enviado a REPOM, aguardando retorno do número do contrato")

                    else:
                        raise f"Falha ao gerar o contrato. Mensagem da pop-up: {alert_text}"

                    contract_window = self._find_contract_number_window_handle()
                    if not contract_window:
                        self.driver.refresh()
                        continue

                    self.driver.switch_to_frame(principal=False)

                    try:
                        contract_number = self._get_contract_number()
                    except Exception as e:
                        self.log.error(str(e))
                        raise

                    self.driver.switch_to_window(home_window=True)
                    return contract_number

                except BaseException as e:

                    if attempt == max_retries:
                        raise
                    self.log.error(f"Falha ao gerar o contrato, tentando novamente. Erro => {str(e)}")
                    self.driver.switch_to_window(home_window=True)
                    self.driver.refresh()
                    self.quick_access(term="REPOMFRETED")

        except pe.KMMProcess:
            raise
        except Exception as e:
            raise pe.KMMEmittingContractError(
                f"Falha ao gerar o contrato. Valor do contrato {contract_value}, cte de complemento {complement_cte} "
                f"serie {serie} submotivo {submotive}, transporte {transport}, "
            ) from e

    def payment(self, contract_number: str, cod_pessoa_filial: str) -> bool:

        try:
            self.quick_access('LTREPOMFRETE')

            self.driver.switch_to_frame(principal=False)
            self.driver.safe_type('id:PROCESSO_TRANSPORTE_CODIGO', contract_number)

            self.driver.switch_to_frame(principal=True)
            self.driver.safe_click('id:btn_confirmar')

            self.driver.switch_to_frame(principal=False)
            self.driver.safe_click('xpath:/html/body/form/table/tbody/tr/td/div/table/tbody/tr/td[8]/button')
            self.log.info("Clicado no ícone de quitação")

            self.driver.select_by_value('id:COD_PESSOA_FILIAL', cod_pessoa_filial)
            self.log.info("Filial inserida")

            self.driver.select_by_value("id:COD_CENTRO_CUSTO", "370")
            self.log.info("Centro de custo inserido")

            self.driver.safe_type('id:PESO_ENTREGA', '1.00')
            self.log.info("Peso inserido")
            self.log.info("Todos parâmetros inseridos, realizando quitação")

            self.driver.switch_to_frame(principal=True)
            iframe = self.driver.find_element(
                by="xpath",
                value="/html/body/table/tbody/tr[1]/td[2]/table/tbody/tr[4]/td/iframe"
            )
            self.driver.switch_to.frame(iframe)

            self.driver.safe_click('xpath:/html/body/form/div/table/tbody/tr[3]/td/button[2]')

            alert = self.driver.wait_alert(10)
            if not alert:
                raise pe.KMMPaymentError(f"Falha na quitação. Número do contrato: {contract_number}")

            alert_text = alert.text.lower()
            if 'quitado' in alert_text:
                self.log.info("Quitado com sucesso")
                return True
            else:
                raise pe.KMMPaymentError(f"Falha na quitação. Mensagem da pop-up {alert_text}")

        except pe.KMMProcess:
            raise
        except Exception as e:
            raise pe.KMMPaymentError(
                f"Falha ao realizar o pagamento. Numero do contrato {contract_number}"
            ) from e
