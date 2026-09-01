from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import mechanize
import pdfplumber
import pygetwindow as gw
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from src.bots.belgo.tasks.publisher.schemas import BelgoIncident, BelgoPortalResult
from src.shared import email_handler
from src.shared.logger import logger
from src.shared.sharepoint import wait_file

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output" / "evidence"
DOWNLOAD_DIR = BASE_DIR / "downloads"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def create_chrome_driver(download_dir: Path) -> webdriver.Chrome:
    download_dir.mkdir(parents=True, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_argument("--window-size=1366,768")
    chrome_options.add_argument("--force-device-scale-factor=1")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": os.path.join(os.getcwd(), 'downloads'),  # pasta de download
            "download.prompt_for_download": False,  # não perguntar
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True  # evita bloqueio do Chrome
        }
    )
    driver_path = ChromeDriverManager().install()
    return webdriver.Chrome(executable_path=driver_path, options=chrome_options)


class BelgoPortal:

    def __init__(self, itens_in_bd=None) -> None:
        self.itens_in_bd = set(itens_in_bd or ())
        self.br = mechanize.Browser()
        self.driver = create_chrome_driver(DOWNLOAD_DIR)
        self.wait = WebDriverWait(self.driver, 30)
        self.log = logger.bind(service="belgo")
        self.incidents = []

    def quit_driver(self) -> None:
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            self.log.exception("Falha ao encerrar o driver.")

    @staticmethod
    def maximize_window():
        windows = gw.getWindowsWithTitle("Chrome")
        if windows:
            win = windows[0]
            win.maximize()

    def config(self):

        self.br.open(os.getenv("BBA_PORTAL_LOGIN_URL"))
        self.br.select_form(nr=0)
        self.br["user[email]"] = os.getenv("BBA_PORTAL_USERNAME")
        self.br["user[password]"] = os.getenv("BBA_PORTAL_PASSWORD")
        self.br.find_control(id="user_aceitou_termos").items[0].selected = True

        self.br.set_handle_referer(False)
        self.br.set_handle_robots(False)

        self.br.submit()

    def open(self):
        self.log.info("Acessando o portal BBA")
        self.driver.get(os.getenv("BBA_PORTAL_INCIDENTS_URL"))
        self.driver.maximize_window()
        self.maximize_window()
        btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/button")))
        time.sleep(3)
        btn.click()

    def access(self) -> bool:
        self.log.info("Realizando login")
        import ctypes

        self.log.info(f"W: {ctypes.windll.user32.GetSystemMetrics(0)}")
        self.log.info(f"H: {ctypes.windll.user32.GetSystemMetrics(1)}")

        try:
            self.driver.find_element(By.ID, "user_email").send_keys(os.getenv("BBA_PORTAL_USERNAME"))
            self.driver.find_element(By.ID, "user_password").send_keys(os.getenv("BBA_PORTAL_PASSWORD"))
            terms_and_conditions = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//label[@for='user_aceitou_termos']"))
            ).click()

            for i in range(1, 5):
                try:
                    name = self.driver.find_element(By.XPATH, f"//*[@id='new_user']/div[{i}]").text
                    if 'entrar' in name.lower():
                        self.log.info('Botão encontrado')
                        self.driver.find_element(By.XPATH, f"//*[@id='new_user']/div[{i}]/button").click()
                        self.log.info("Login realizado com sucesso")
                        return True
                    else:
                        continue
                except:
                    pass
            self.log.error("Falha ao realizar o login")
            return False

        except Exception as error:
            self.log.exception("Falha inesperada ao realizar o login.")
            return False

    def search_for(self, term):
        self.log.info(f"Realizando busca pelo termo: {term}")

        try:
            alert = self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='modal_informe]/div/div/div[3]/button")))
            alert.click()
            self.log.info("Alerta fechado.")
        except:
            self.log.info("Alerta não apareceu")

        text_box = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id='incidente_workflows_datatable_filter']/label/input")))
        text_box.send_keys(term)
        time.sleep(10)

    def _get_table_headers(self, table_id: str):
        table = self.driver.find_element(By.ID, table_id)
        headers = table.find_elements(By.TAG_NAME, "th")
        count = 1
        headers_dict = {}
        for header in headers:
            headers_dict[header.text] = count
            count += 1
        return headers_dict

    def _get_number_of_incidentes_button(self):
        ul = self.driver.find_element(By.XPATH, '/html/body/div[3]/div/div/div[2]/div/div/div/div[6]/ul')

        for btn in ul.find_elements(By.TAG_NAME, 'li'):
            if 'incidentes' in btn.text.lower().lstrip():
                return btn
        return None

    def _get_table_size(self):
        itens = self.driver.find_element(By.ID, 'incidente_workflows_datatable_info').text
        itens_de = int(re.findall('(?:Mostrando de\s*)(\d*)', itens)[0])
        itens_ate = int(re.findall('(?:Mostrando de\s*\d*\s*até\s*)(\d*)', itens)[0])
        self.log.info(f'Mostrando de {itens_de} até {itens_ate}')
        n_itens = itens_ate - itens_de + 1
        return n_itens

    def _get_page_row_count(self):
        """Conta as linhas reais de dados na página atual.

        O portal tem um bug em que exibe páginas extras (com o botão 'próxima'
        ativo) porém sem nenhum registro. Nesses casos o DataTables renderiza a
        linha placeholder 'Nenhum registro encontrado' (td.dataTables_empty).
        """
        empty = self.driver.find_elements(
            By.XPATH,
            "//*[@id='incidente_workflows_datatable']/tbody/tr/td[contains(@class,'dataTables_empty')]"
        )
        if empty:
            return 0
        rows = self.driver.find_elements(
            By.XPATH,
            "//*[@id='incidente_workflows_datatable']/tbody/tr"
        )
        return len(rows)

    def get_incidents(self) -> tuple[list[dict], list[dict]]:

        self.log.info("Iniciando a obtenção da lista de incidentes")
        incidents = []
        errors =  []
        validation = self.driver.find_element(By.TAG_NAME, 'tbody').text
        if validation == "Nenhum registro encontrado":
            self.log.warning("Nenhum registro encontrado")
            return [], []

        line_path = "//*[@id='incidente_workflows_datatable']/tbody/tr[{0}]/td[{1}]"

        n_itens = self._get_page_row_count()
        self.log.info(f"{n_itens} incidentes encontrados. Filtrando...")

        headers = self._get_table_headers("incidente_workflows_datatable")
        if len(headers) < 12:
            headers = {
                'Id': 1,
                'Transporte': 2,
                'Transportadora': 3,
                'Centro': 4,
                'Natureza': 5,
                'Submotivo': 6,
                'Etapa': 7,
                'Criado Em': 8,
                'Na Etapa desde': 9,
                'Tentativas CTE': 10,
                'Status': 11,
            }

        page = 1
        while True:

            self.log.info(f"Página {page}")
            n_itens = self._get_page_row_count()

            if n_itens == 0:
                self.log.info("Página sem registros. Fim da paginação.")
                break

            for item in range(1, n_itens + 1):

                id_ = self.driver.find_element(By.XPATH, line_path.format(item, headers["Id"])).get_attribute('innerHTML')
                transport = self.driver.find_element(By.XPATH, line_path.format(item, headers["Transporte"])).get_attribute('innerHTML')
                subreason = self.driver.find_element(By.XPATH, line_path.format(item, headers["Submotivo"])).get_attribute('innerHTML')
                cte_attempt = self.driver.find_element(By.XPATH, line_path.format(item, headers['Tentativas CTE'])).get_attribute('innerHTML')
                branch = self.driver.find_element(By.XPATH, line_path.format(item, headers['Centro'])).get_attribute('innerHTML')

                if str(id_).strip() in self.itens_in_bd:
                    self.log.info("Caso já existe no banco de dados")
                    continue

                # Se no campo de tentativas CTE não estiver em branco
                if cte_attempt:
                    self.log.warning(f"ID {cte_attempt} possui tentativa de CTe")
                    errors.append({
                        "id": id_,
                        "transport": transport,
                        "subreason": subreason,
                        "cte_attempt": cte_attempt,
                        "error": "Tentativa de CTe diferente de 0"
                    })
                    continue

                reason = self.driver.find_element(By.XPATH, line_path.format(item, headers['Submotivo'])).text
                if reason in [
                    "DESCARGA",
                    "TICKET DE PEDÁGIO NÃO EMITIDO",
                    "DESLOCAMENTO",
                    "COMPLEMENTO DE PEDÁGIO",
                    "PEDÁGIO COMPLEMENTO DE VALOR",
                    "DEMORA NO CARREGAMENTO",
                    "OUTROS",
                    "REVERSA",
                    "VEÍCULO SEM TAG",
                    "DIÁRIA NA DESCARGA",
                    "AJUSTE FINANCEIRO DE CTE"
                ]:
                    # Se no campo Centro Conter Mesquita
                    if "MESQUITA" in branch:
                        center = "FRETO LOG - FILIAL RJ"
                    else:
                        center = "FRETO LOG - MATRIZ"

                    item_data = {
                        "id": id_,
                        "center": center,
                        "transport": transport,
                        "subreason": subreason
                    }
                    incidents.append(item_data)
                    self.log.info(f"Dados obtidos: {item_data}")
                else:
                    errors.append({
                        "id": id_,
                        "transport": transport,
                        "subreason": subreason,
                        "cte_attempt": cte_attempt,
                        "branch": branch,
                        "error": f"Motivo fora do escopo da automação {subreason}"
                    })
                    self.log.warning(f"O motivo {reason} do id {id_} esta fora do escopo da automação")
                    continue

            next_btn = self.driver.find_element(By.ID, 'incidente_workflows_datatable_next')
            if 'disabled' in (next_btn.get_attribute('class') or ''):
                self.log.info("Fim da paginação")
                break

            first_id_previous_page = self.driver.find_element(By.XPATH, line_path.format(1, headers['Id'])).text
            next_btn.click()

            page_changed = False
            for _ in range(20):
                time.sleep(1)
                if self._get_page_row_count() == 0:
                    page_changed = True
                    break
                try:
                    first_id_actual_page = self.driver.find_element(By.XPATH, line_path.format(1, headers['Id'])).text
                except Exception:
                    continue
                if first_id_actual_page != first_id_previous_page:
                    page_changed = True
                    break

            if not page_changed:
                self.log.info("Fim da paginação (página não mudou)")
                break

            page += 1

        self.log.info(f"{len(incidents)} incidentes são elegíveis para automação tratar")
        return incidents, errors

    def get_additional_incident_data(self, incident) -> None | dict:

        historic_element = "incidente_workflow_observacao"
        nf_element = "incidente_workflow_incidente_workflow_nfs_attributes_0_numero_nf"

        try:
            self.log.info(f"Iniciando a obtenção de dados adicionais para o ID: {incident['id']}")

            url_edit_incident = os.getenv("BBA_PORTAL_EDIT_INCIDENTS_URL").format(incident["id"])
            self.driver.get(url_edit_incident)
            historic_el = self.wait.until(EC.presence_of_element_located((By.ID, historic_element)))
            historic = historic_el.text
            nf_el = self.wait.until(EC.presence_of_element_located((By.ID, nf_element)))
            nf = nf_el.get_attribute('value')

            cte_value = self.get_cte_value(historic=historic)
            if not cte_value:
                self.log.error(f"Falha ao encontrar valor do CTE para o ID {incident['id']}")
                incident["_error"] = "Valor do CTe não encontrado no histórico"
                return None

            full_contract_value =self.get_contract_value(historic=historic)
            if not full_contract_value:
                self.log.error(f"Falha ao encontrar valor do contrato para o ID {incident['id']}")
                incident["_error"] = "Valor do contrato não encontrado no histórico"
                return None
            contract_value = self.ajusta_valor_moeda(valor=str(full_contract_value))
            if not contract_value:
                self.log.error(f"Falha ao ajustar valor do contrato para o ID {incident['id']}")
                incident["_error"] = "Valor do contrato possui formato inválido"
                return None
            driver_value = self.get_driver_reimbursement_value(valor=float(contract_value))

            if not driver_value or not cte_value or not contract_value:
                self.log.error("Falha ao encontrar valor do motorista, cte ou contrato do histórico do caso para p "
                             f"ID: {incident['id']}")
                incident["_error"] = "Valores de CTe, contrato ou motorista incompletos"
                return None

            if float(cte_value) < 7000.00:

                self.log.info(f'Informação de valores encontrados para o ID {incident["id"]}. '
                            f'Valor motorista: {driver_value} - Valor cte {cte_value} - '
                           f'N nf {nf}')
                data = {
                    'cte_value': cte_value,
                    'contract_value': contract_value,
                    'driver_value': driver_value,
                    'nf': nf
                }
                return data
            else:
                message = ('Valor de CT-e é maior ou igual a R$ 7.000,00. Informação de valores encontrados '
                           f'para o ID {incident["id"]}. Valor motorista: {driver_value} '
                           f'- Valor cte {cte_value} - N nf {nf}')
                self.log.warning(message)
                incident["_error"] = "Valor de CT-e é maior ou igual a R$ 7.000,00"
                return None

        except Exception as error:
            self.log.exception(f"Falha ao obter dados do histórico para o caso {incident['id']}")
            incident["_error"] = "Falha ao obter dados do histórico do incidente"
            return None

    def get_driver_reimbursement_value(self, valor):
        inss = (float(valor) * 0.2) * float(os.getenv("TAX2"))
        sest_sesnat = (float(valor) * 0.2) * float(os.getenv("TAX4"))
        contrato = round((float(valor) + inss + sest_sesnat), 2)

        self.log.info(f"Valor do contrato: {contrato}")

        return contrato

    def truck_carreta(self, valor_cte, historic):
        try:

            reembolso = {
                "Taxa1": os.getenv("TAX1"),
                "Taxa2": os.getenv("TAX2"),
                "Taxa3": os.getenv("TAX3"),
                "Taxa4": os.getenv("TAX4"),
                "Truck": os.getenv("TRUCK"),
                "TruckCorrigido": os.getenv("TRUCK_CORRIGIDO"),
                "Carreta": os.getenv("CARRETA"),
                "CarretaCorrigido": os.getenv("CARRETA_CORRIGIDA")
            }
            if valor_cte % float(reembolso["Truck"]) == 0:
                diaria = valor_cte / float(reembolso["Truck"])
                valor_contrato = round(diaria * float(reembolso["TruckCorrigido"]), 2)
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                self.log.info(f"Caso Truck, valor motorista: {valor_motorista}")

            elif valor_cte % float(reembolso["Carreta"]) == 0:
                diaria = valor_cte / float(reembolso["Carreta"])
                valor_contrato = round(diaria * float(reembolso["CarretaCorrigido"]), 2)
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                self.log.info(f"Caso carreta, valor motorista: {valor_motorista}")

            else:
                valor_contrato = re.findall("VALOR TOTAL\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
                if not valor_contrato:
                    valor_contrato = re.findall("VALOR\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
                    if not valor_contrato:
                        self.log.error(
                            "Não foi encontrado o valor do contrato, nem pelo padrão VALOR TOTAL, nem pelo padrão "
                            "VALOR.")
                        raise Exception("Valor do contrato não obtido")

                valor_contrato = valor_contrato[-1] if valor_contrato else None
                valor_contrato = self.ajusta_valor_moeda(valor=str(valor_contrato))
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                self.log.info(f"Nem Truck, nem carreta, valor motorista: {valor_motorista}")

            return valor_motorista, valor_contrato
        except Exception as e:
            self.log.exception("Falha ao ajustar o valor para truck ou carreta")
            valor_motorista = None
            valor_contrato = None
            return valor_motorista, valor_contrato

    def ajusta_valor_moeda(self, valor) -> str | None:
        if valor[-3] == '.':
            valor = valor.replace(',', '')
        elif valor[-3] == ',':
            valor = valor.replace('.', '').replace(',', '.')
        else:
            return None
        return valor

    def get_cte_value(self, historic) -> str | None:
        valor_cte = None

        try:
            valor_cte = re.findall(r"RESULTADO\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
            valor_cte = valor_cte[-1] if valor_cte else None
            if not valor_cte:
                raise ValueError('CTE')
            valor_cte = self.ajusta_valor_moeda(valor=str(valor_cte))
            return valor_cte
        except ValueError as e:
            self.log.exception(f"Problema ao procurar o valor do {e}")
            valor_cte = None
            return valor_cte

    def get_contract_value(self, historic):

        valor_contrato = None
        try:
            valor_contrato = re.findall("VALOR TOTAL\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
            if not valor_contrato:
                valor_contrato = re.findall("VALOR\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
                if not valor_contrato:
                    self.log.error("Não foi encontrado o valor do contrato, nem pelo padrão VALOR TOTAL, nem pelo padrão "
                                 "VALOR.")
                    return None

            valor_contrato = valor_contrato[-1]
            return valor_contrato
        except Exception as e:
            valor_contrato = None
            self.log.exception(f"Problema ao obter o valor do contrato no histórico do caso.")
            return valor_contrato

    def get_incident_nf(self, incident):

        self.log.info("Etapa de obtencao dos cte code")
        try:
            self.driver.get(os.getenv("BBA_PORTAL_TRANSPORT_URL") + incident["transport"])
            self.wait.until(EC.presence_of_element_located((By.ID, "nav_dados_transporte")))

            for i in range(15):
                document_exists = False
                try:
                    url_pdf = self.driver.find_element(By.XPATH, f"//*[@id='doc_{i}']/a").text
                    name = re.search("(^Viagem)[A-z]?[0-9]+?", url_pdf)

                    if name:
                        self.log.info("Documento viagem existe")
                        pdf_link = self.driver.find_element(By.XPATH, f"//*[@id='doc_{i}']/a").get_attribute("href")
                        document_exists = True
                        break
                except Exception as e:
                    self.log.info(f"Não existe documento com nome \"Viagem\" para o id {incident['id']}")
                    return None

            if not document_exists:
                self.log.info(f"Falta documento no portal para o id {incident['id']}")
                return None

            response = self.br.open(pdf_link)
            with open(DOWNLOAD_DIR / "download.pdf", "wb") as f:
                f.write(response.read())

            file_downloaded = wait_file(DOWNLOAD_DIR, 'download.pdf')
            if not file_downloaded:
                return None

            data = self.get_nf_data(nf_portal=int(incident["nf"]))

            return data

        except Exception as e:
            self.log.exception("Falha ao extrair dados das NFs ou na obtenção da quantidade de incidentes")
            return None

    def get_nf_data(self, nf_portal):

        file_path = os.path.join(DOWNLOAD_DIR, "download.pdf")
        cte_fretolog_code = None
        cte_levolog_code = None
        serie_levolog = None
        index = 0
        nf_data = {}

        try:
            self.log.info("Inicio de obtenção de dados da nf")
            flag = False
            with pdfplumber.open(file_path) as pdf:
                pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

            self.log.info("Texto do pdf obtido")

            nfs = re.findall("(Notas*\sf*F*iscais:*\s*\d+/?)(\d+)?", pdf_text)
            verify = re.findall('(levo log)', pdf_text.lower())
            data = re.findall('\d{2}/\d{2}/\d{4}', pdf_text)
            freto_lot = re.findall(
                r'(?:INÍCIO DESCARGA DATA \/ HORA\n[0-9 \/:]*)([A-Za-z -]+)(?=.*\nTÉRMINO)',
                pdf_text
            )

            if not freto_lot:
                freto_lot = re.findall('(?<=INÍCIO DA PRESTAÇÃO\\n).*?(?=INÍCIO)',
                                       pdf_text.encode('utf-8').decode('unicode_escape'))

            if verify:

                pf = True

                levo_lot = re.findall("(?:FILIALLEVO LOG - )(FILIAL [A-Z]{2})", pdf_text)
                cte_levolog_code = re.findall(r"(?:INÍCIO DESCARGA DATA \/ HORA\n)([0-9]+)", pdf_text)
                serie_levolog = re.findall(r"(?:INÍCIO DESCARGA DATA \/ HORA\n[0-9]+ )([0-9]{1})", pdf_text)

                serie_fretolog = re.findall(r"(?:N* \d* Serie) (\d)", pdf_text)

                if not cte_fretolog_code:
                    cte_fretolog_code = re.findall(r"(?:N*)(\d*) (?:Serie \d)", pdf_text)

                if not serie_fretolog:
                    serie_fretolog = re.findall(r"Serie\s+(\d+)", pdf_text, flags=re.IGNORECASE)

                if not cte_fretolog_code:
                    cte_fretolog_code = re.findall(r"\bN[oº]?\s*(\d+)", pdf_text, flags=re.IGNORECASE)

            else:
                pf = False
                cte_fretolog_code = re.findall(r"(?:INÍCIO DESCARGA DATA \/ HORA\n)([0-9]+)", pdf_text)
                serie_fretolog = re.findall(r"(?:INÍCIO DESCARGA DATA \/ HORA\n[0-9]+ )([0-9]{1})", pdf_text)
                levo_lot = []

            if len(nfs) > 0:

                for nf in nfs:

                    for number in nf:
                        if str(nf_portal) in number:
                            flag = True
                            if pf:
                                cte_levolog_code = cte_levolog_code[index]
                                serie_levolog = serie_levolog[index]
                                data = data[index]

                                if cte_fretolog_code:
                                    cte_fretolog_code = cte_fretolog_code[index]
                                    serie_fretolog = serie_fretolog[index]

                            else:

                                cte_levolog_code = None
                                serie_levolog = None
                                cte_fretolog_code = cte_fretolog_code[index]
                                serie_fretolog = serie_fretolog[index]
                                data = data[0]
                            break

                    index += 1

                    if flag:
                        break

            if not flag:
                self.log.error(
                    'Numero da NF não encontrada no arquivo Viagem'
                )
                return None

            else:

                self.log.info("Sucesso ao obter os dados da nf")
                nf_data = {
                    "cte_levolog_code": cte_levolog_code,
                    "cte_fretolog_code": cte_fretolog_code,
                    "serie_levolog": serie_levolog,
                    "serie_fretolog": serie_fretolog,
                    "pf": pf,
                    "date": data,
                    "freto_lot": freto_lot[0],
                    "levo_lot": levo_lot[0] if levo_lot else None
                }
                return nf_data

        except Exception as e:
            self.log.exception("Falha ao obter os dados da nf")
            return None

        finally:
            if os.path.isfile(file_path):
                os.remove(os.path.join(DOWNLOAD_DIR, "download.pdf"))

    def get_number_of_incidents(self, incident):

        self.log.info(f"Etapa de obtencao da quantidade de incidentes para o id {incident['id']}")
        self.driver.get(os.getenv("BBA_PORTAL_TRANSPORT_URL") + incident["transport"])

        incident_names = [
            'diáriaexterna',
            'diáriainterna',
            'pedágio',
            'reembolso'
        ]
        counter = 0

        try:
            btn = self._get_number_of_incidentes_button()
            if btn:
                btn.click()
            else:
                self.log.error("Botão \"Incidentes\" não encontrado")
                return None
        except Exception as e:
            self.log.error("Botão \"Incidentes\" não encontrado")
            return None

        number_of_incidents = len(self.driver.find_elements(By.XPATH, "//*[@id='incidentes']/div"))
        if not number_of_incidents:
            self.log.error("Não há nenhum incidente para este caso")
            return None

        for item in range(1, number_of_incidents + 1):

            text = self.driver.find_element(By.XPATH, f"//*[@id='incidentes']/div[{item}]/a").text

            splited_text = text.split("\n")
            splited_name = re.findall(r'[A-zÀ-ÿ-]+', splited_text[0])
            name = ''

            for sn in splited_name[1:]:
                if '-' in sn:
                    break
                name = name + sn

            if name.lower() in incident_names:

                id_ = re.findall('[0-9]+', splited_text[0])[0]
                phase = splited_text[1].replace("Etapa: ", "")
                status = splited_text[2].replace("Status: ", "")

                if (phase.lower() == 'emissão de cte' or phase.lower() == 'finalizado') and (status.lower() == 'em aberto' or status.lower() == 'aprovado'):
                    counter += 1
                    self.log.info(f"Incidente encontrado para o ID buscado. Id => {id_} - Nome => {name} - "
                                f"Fase => {phase} - Status => {status}")

                    incident['incident_status'] = True
                else:
                    self.log.error(f"Incidente com id ou fase não correspondente id {id_} - fase {phase} - status {status}")
            else:
                self.log.error(f"Nome do incidente {name} não corresponde a 'diária externa', 'diária interna', 'pedágio' ou 'reembolso'")

        self.log.info(f"Foram obtidos {counter} incidentes")
        return counter

    def get_values_and_nf_data(self, incidents: list[dict], errors: list[dict]):
        
        new_incidents = []
        for incident in incidents:
            additional_data = self.get_additional_incident_data(incident)
            if not additional_data:
                self.log.error(f"Não foi possível obter todas as informações para o id {incident['id']}")
                errors.append({
                    **incident,
                    "error": incident.pop(
                        "_error",
                        "Não foi possível obter informações de histórico e/ou número NF",
                    ),
                })
                continue
            else:
                new_incidents.append({**additional_data, **incident})
        self.log.info(f"Foram obtidos {len(new_incidents)} incidentes com valores e NF")

        return new_incidents, errors

    def get_nfs_data(self, incidents: list[dict], errors: list[dict]):
        nf_data = []
        for incident in incidents:
            nfs_data = self.get_incident_nf(incident)
            if nfs_data:
                nf_data.append({**incident, **nfs_data})
            else:
                errors.append({
                    **incident,
                    "error": "Não foi possível obter informações de NF ou documento não existe"
                })
        return nf_data, errors

    def get_incidents_number_of_incidents(self, incidents: list[dict], errors: list[dict]):
        final_data = []
        for incident in incidents:
            number_of_incidents = self.get_number_of_incidents(incident=incident)
            if number_of_incidents:
                final_data.append({**incident, "number_of_incidents": number_of_incidents})
            else:
                errors.append({
                    **incident,
                    "error": "Não foi possível obter informações de número de incidentes"
                })
        return final_data, errors

    @staticmethod
    def _get_error_email_recipients() -> list[str]:
        raw = os.getenv("BBA_PORTAL_EMAIL_TO") or os.getenv("BELGO_RECIPIENTS")
        if not raw:
            return []
        return [email.strip() for email in raw.split(",") if email.strip()]

    @staticmethod
    def _build_incident_errors_email(
        errors: list[dict],
        total_found: int,
        total_success: int,
    ) -> tuple[str, str]:
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        subject = f"Belgo BBA — {len(errors)} caso(s) com falha na ingestão"

        lines = [
            "Automação Belgo — Publisher (Portal BBA)",
            f"Execução: {timestamp}",
            "",
            "Resumo",
            "------",
            f"Incidentes encontrados no portal: {total_found}",
            f"Incidentes prontos para a fila: {total_success}",
            f"Casos com falha: {len(errors)}",
        ]

        by_error: dict[str, list[dict]] = {}
        for item in errors:
            by_error.setdefault(item["error"], []).append(item)

        lines.extend(["", "Falhas por tipo", "--------------"])
        for error_msg, items in by_error.items():
            lines.append(f"• {error_msg}: {len(items)} caso(s)")

        lines.extend(["", "Detalhes dos casos", "------------------"])
        for index, item in enumerate(errors, start=1):
            lines.extend([
                f"{index}. ID incidente: {item.get('id', '-')}",
                f"   Transporte: {item.get('transport', '-')}",
                f"   Submotivo: {item.get('subreason', '-')}",
                f"   Erro: {item.get('error', '-')}",
                "",
            ])

        return subject, "\n".join(lines).rstrip()

    @staticmethod
    def _pending_from_error(error: dict) -> BelgoIncident:
        payload = {key: value for key, value in error.items() if key not in {"error", "_error", "branch"}}
        if not payload.get("center") and error.get("branch"):
            payload["center"] = error["branch"]
        payload["error_reasons"] = [str(error.get("error") or "Pendência não especificada")]
        return BelgoIncident.model_validate(payload)

    def get_capture_result(self) -> BelgoPortalResult:
        final_data = []
        errors = []
        try:
            self.config()
            self.open()
            access = self.access()
            if not access:
                self.log.error("Falha ao acessar o portal BBA")
                raise Exception
            self.search_for(term="emissão de cte")
            incidents, errors = self.get_incidents()
            total_found = len(incidents) + len(errors)
            if not incidents and not errors:
                self.log.info(f"Nenhum Registro encontrado")
                return BelgoPortalResult()

            if incidents:
                enriched_incidents, errors = self.get_values_and_nf_data(incidents, errors)
                enriched_nf_data_incidents, errors = self.get_nfs_data(enriched_incidents, errors)
                final_data, errors = self.get_incidents_number_of_incidents(enriched_nf_data_incidents, errors)

            self.log.info("Fim da obtenção e classificação dos casos.")
            if errors:
                subject, body = self._build_incident_errors_email(
                    errors=errors,
                    total_found=total_found,
                    total_success=len(final_data),
                )
                recipients = self._get_error_email_recipients()
                if recipients:
                    email_handler.send_email(
                        to=recipients,
                        subject=subject,
                        body=body,
                    )
                else:
                    self.log.warning(
                        "Casos com erro no BBA, mas nenhum destinatário configurado "
                        "(BBA_PORTAL_EMAIL_TO ou BELGO_RECIPIENTS)."
                    )
            return BelgoPortalResult(
                processable=[BelgoIncident.model_validate(item) for item in final_data],
                pending=[self._pending_from_error(item) for item in errors],
            )
        except Exception as e:
            self.log.exception(f"Erro na obtenção dos dados.")
            raise
        finally:
            self.log.info("Entrou no finally. Fechando driver...")
            try:
                self.driver.quit()
                self.log.info("Driver fechado com close().")
            except Exception:
                self.log.exception("Erro ao executar driver.close()")

    def get_incidents_in_bba_portal(self) -> list[dict]:
        """Compatibilidade com o publisher legado durante a migração."""
        return [
            item.model_dump(mode="python")
            for item in self.get_capture_result().processable
        ]


class BelgoXML:
    def __init__(self):

        self.br = mechanize.Browser()
        self.driver = self.driver_config()
        self.wait = WebDriverWait(self.driver, 30)
        self.log = logger.bind(service='belgo')

    def driver_config(self):
        chrome_options = Options()
        chrome_options.add_argument("--window-size=1366,768")
        chrome_options.add_argument("--force-device-scale-factor=1")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": os.path.join(os.getcwd(), 'downloads'),  # pasta de download
                "download.prompt_for_download": False,  # não perguntar
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True  # evita bloqueio do Chrome
            }
        )
        driver_path = ChromeDriverManager().install()
        driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)
        return driver

    @staticmethod
    def maximize_window():
        windows = gw.getWindowsWithTitle("Chrome")
        if windows:
            win = windows[0]
            win.maximize()

    def config(self):

        self.br.open(os.getenv("BBA_PORTAL_LOGIN_URL"))
        self.br.select_form(nr=0)
        self.br["user[email]"] = os.getenv("BBA_PORTAL_USERNAME")
        self.br["user[password]"] = os.getenv("BBA_PORTAL_PASSWORD")
        self.br.find_control(id="user_aceitou_termos").items[0].selected = True

        self.br.set_handle_referer(False)
        self.br.set_handle_robots(False)

        self.br.submit()

    def open(self):
        self.log.info("Acessando o portal BBA")
        self.driver.get(os.getenv("BBA_PORTAL_INCIDENTS_URL"))
        self.driver.maximize_window()
        self.maximize_window()
        btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/button")))
        time.sleep(3)
        btn.click()

    def access(self) -> bool:
        self.log.info("Realizando login")

        try:
            self.driver.find_element(By.ID, "user_email").send_keys(os.getenv("BBA_PORTAL_USERNAME"))
            self.driver.find_element(By.ID, "user_password").send_keys(os.getenv("BBA_PORTAL_PASSWORD"))
            terms_and_conditions = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//label[@for='user_aceitou_termos']"))
            ).click()

            for i in range(1, 5):
                try:
                    name = self.driver.find_element(By.XPATH, f"//*[@id='new_user']/div[{i}]").text
                    if 'entrar' in name.lower():
                        self.log.info('Botão encontrado')
                        self.driver.find_element(By.XPATH, f"//*[@id='new_user']/div[{i}]/button").click()
                        self.log.info("Login realizado com sucesso")
                        return True
                    else:
                        continue
                except:
                    pass
            self.log.error("Falha ao realizar o login")
            return False

        except Exception as error:
            self.log.exception("Falha inesperada ao realizar o login.")
            return False

    def _go_to_incident_page(self, incident_id):
        url_edit_incident = os.getenv("BBA_PORTAL_EDIT_INCIDENTS_URL").format(incident_id)
        self.driver.get(url_edit_incident)

    def _edit_info(self, complement_cte, file_path) -> bool:
        
        try:
            # Preencher CTE
            self.driver.find_element(By.ID, 'incidente_workflow_campos_numero_cte').send_keys(complement_cte)
            time.sleep(2)
            
            # Buscar botao adicionar anexo com retry
            for _ in range(3):
                try:
                    for btn in self.driver.find_elements(By.XPATH, '//*[contains(@class,"btn")]'):
                        try:
                            if 'adicionar' in btn.text.lower() and 'anexo' in btn.text.lower():
                                btn.click()
                                break
                        except StaleElementReferenceException:
                            continue
                    break
                except StaleElementReferenceException:
                    time.sleep(1)
                    continue
            
            time.sleep(2)
            
            # Aguardar campo de arquivo
            inp = self.wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, "input[type='file'][id$='_anexo']"
            )))
            inp.send_keys(str(file_path))
            
            time.sleep(2)
            
            # Buscar botao enviar com retry (FRESH, nao reutilizar referencias)
            for _ in range(3):
                try:
                    buttons_found = False
                    for btn in self.driver.find_elements(By.XPATH, '//*[contains(@class,"btn")]'):
                        try:
                            if btn.text.lower() == 'enviar':
                                btn.click()
                                buttons_found = True
                                break
                        except StaleElementReferenceException:
                            continue
                    if buttons_found:
                        break
                except StaleElementReferenceException:
                    time.sleep(1)
                    continue
            erros = [
                elemento.text.strip()
                for elemento in self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class, 'alert-danger')]//ul/li"
                )
                if elemento.text.strip()
            ]

            if erros:
                self.log.error(f"Erros encontrados no portal: {erros}")
                return False

            self.log.info("Dados editados com sucesso no portal")
            return True
        except Exception as e:
            self.log.exception(f"Erro ao editar informacoes do incidente: {str(e)}")
            raise

    def extrair_cte_xml_do_zip(
            self,
            zip_path: str | Path,
            output_dir: str | Path,
            novo_nome: str,
            apagar_zip: bool = True,
    ) -> Path:
        """
        Extrai do ZIP o XML do CT-e (ex.: CTe123-cte.xml), renomeia para {novo_nome}.xml
        e retorna o caminho final do arquivo.
        - Procura recursivamente dentro do ZIP (mesmo se estiver em subpastas).
        - Não lista a pasta inteira; só trabalha com o conteúdo do ZIP.
        - Cria output_dir se não existir.
        """
        cte_xml_re = re.compile(r"(?i)^cte\d+.*-cte\.xml$")  # ex: CTe12345-cte.xml (case-insensitive)
        zip_path = Path(zip_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        destino_final = output_dir / f"{novo_nome}.xml"

        with ZipFile(zip_path, "r") as z:
            # Filtra apenas arquivos (não diretórios) e procura o XML esperado
            candidatos = [
                name for name in z.namelist()
                if not name.endswith("/") and cte_xml_re.match(Path(name).name)
            ]

            if not candidatos:
                # fallback: pega qualquer .xml se não bater no padrão (às vezes mudam o nome)
                candidatos = [
                    name for name in z.namelist()
                    if not name.endswith("/") and Path(name).suffix.lower() == ".xml"
                ]

            if not candidatos:
                raise FileNotFoundError("Nenhum arquivo .xml encontrado dentro do ZIP.")

            # Se tiver mais de um XML, prioriza o que bate no padrão; senão pega o primeiro
            escolhido = candidatos[0]

            # Extrai o arquivo escolhido para a pasta de saída
            extraido_path = output_dir / Path(escolhido).name
            with z.open(escolhido) as src, open(extraido_path, "wb") as dst:
                dst.write(src.read())

        # Renomeia/move para o nome final
        if destino_final.exists():
            destino_final.unlink()
        extraido_path.replace(destino_final)

        if apagar_zip:
            zip_path.unlink(missing_ok=True)

        return destino_final

    def insert_xml(self, id_, complement_cte, file_path):
        try:
            status = False
            if 'xml' in str(file_path):
                xml_path = file_path
            else:
                dir_path = Path(file_path).parent
                xml_path = self.extrair_cte_xml_do_zip(
                    file_path,
                    dir_path,
                    f"CTE {complement_cte}"
                )
            self.config()
            self.open()
            access = self.access()
            if not access:
                self.log.error("Falha ao acessar o portal BBA")
                raise Exception("Falha ao acessar o portal BBA")
            self._go_to_incident_page(id_)
            status = self._edit_info(complement_cte, xml_path)
            self.log.info(f"Incidente {id_} finalizado com sucesso no portal BBA")
            return status
        except Exception as e:
            self.log.exception(f"Erro na edição dos dados para incidente {id_}. Erro: {str(e)}")
            return False
        finally:
            self.driver.close()

