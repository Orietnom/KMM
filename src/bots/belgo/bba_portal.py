from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
from shared.logger import logger
from shared.sharepoint import wait_file
from dotenv import load_dotenv

import pdfplumber
import math
import re
import time
import json
import os
import mechanize

load_dotenv()
INPUT_DIR = f"{os.getcwd()}\\input"
OUTPUT_DIR = os.path.join(os.getcwd(), "downloads")

chrome_options = Options()
chrome_options.add_argument("----start-maximized")
chrome_options.add_experimental_option(
    "prefs",
    {
        "download.default_directory": os.path.join(os.getcwd(), 'downloads'),   # pasta de download
        "download.prompt_for_download": False,        # não perguntar
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True                  # evita bloqueio do Chrome
    }
)
driver_path = ChromeDriverManager().install()
driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)
wait = WebDriverWait(driver, 30)


class BelgoPortal:

    def __init__(self, itens_in_bd: list):

        self.itens_in_bd = itens_in_bd
        self.br = mechanize.Browser()

        self.to = [
            "quitacao@freto.com",
            "expedicaofreto@freto.com",
            "lucas.leite@ergondata.com.br"
        ]
        self.subject = "D_FRETO_CTE_COMPLEMENTAR_BELGO"
        self.body_1 = "Prezado, informo que encontrei um valor que está em 10\% a mais do valor original.\nO seguinte valor é passível de erro: {0}"
        self.body_2 = "Sem incidentes"
        self.incidents = []

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
        logger.info("Acessando o portal BBA")
        driver.get(os.getenv("BBA_PORTAL_INCIDENTS_URS"))

        btn = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/button")))
        time.sleep(3)
        btn.click()

    @staticmethod
    def access() -> bool:
        logger.info("Realizando login")
        try:
            driver.find_element(By.ID, "user_email").send_keys(os.getenv("BBA_PORTAL_USERNAME"))
            driver.find_element(By.ID, "user_password").send_keys(os.getenv("BBA_PORTAL_PASSWORD"))
            terms_and_conditions = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//label[@for='user_aceitou_termos']"))
            ).click()

            for i in range(1, 5):
                try:
                    name = driver.find_element(By.XPATH, f"//*[@id='new_user']/div[{i}]").text
                    if 'entrar' in name.lower():
                        logger.info('Botão encontrado')
                        driver.find_element(By.XPATH, f"//*[@id='new_user']/div[{i}]/button").click()
                        logger.info("Login realizado com sucesso")
                        return True
                    else:
                        continue
                except:
                    pass
            logger.error("Falha ao realizar o login")
            return False

        except Exception as error:
            logger.exception("Falha inesperada ao realizar o login.")
            return False

    def search_for(self, term):
        logger.info(f"Realizando busca pelo termo: {term}")

        try:
            alert = wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='modal_informe]/div/div/div[3]/button")))
            alert.click()
            logger.info("Alerta fechado.")
        except:
            logger.info("Alerta não apareceu")

        text_box = wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id='incidente_workflows_datatable_filter']/label/input")))
        text_box.send_keys(term)
        time.sleep(5)

    def _get_table_headers(self, table_id: str):
        table = driver.find_element(By.ID, table_id)
        headers = table.find_elements(By.TAG_NAME, "th")
        count = 1
        headers_dict = {}
        for header in headers:
            headers_dict[header.text] = count
            count += 1
        return headers_dict

    @staticmethod
    def _get_table_size():
        itens = driver.find_element(By.ID, 'incidente_workflows_datatable_info').text
        itens_de = int(re.findall('(?:Mostrando de\s*)(\d*)', itens)[0])
        itens_ate = int(re.findall('(?:Mostrando de\s*\d*\s*até\s*)(\d*)', itens)[0])
        logger.info(f'Mostrando de {itens_de} até {itens_ate}')
        n_itens = itens_ate - itens_de + 1
        return n_itens

    def get_incidents(self):

        logger.info("Iniciando a obtenção da lista de incidentes")
        self.incidents = []
        validation = driver.find_element(By.TAG_NAME, 'tbody').text
        if validation == "Nenhum registro encontrado":
            logger.warning("Nenhum registro encontrado")
            return False

        line_path = "//*[@id='incidente_workflows_datatable']/tbody/tr[{0}]/td[{1}]"
        itens = driver.find_element(By.ID, 'incidente_workflows_datatable_info').text
        total_itens = int(re.search("\d+ registro", itens).group().replace("registro", "").strip())

        n_itens = self._get_table_size()
        logger.info(f"{n_itens} incidentes encontrados. Filtrando...")

        first_id_previous_page = None
        headers = self._get_table_headers("incidente_workflows_datatable")
        for i in range(1, math.ceil((total_itens / 25) + 1)):

            logger.info(f"Página {i}")
            if i > 1:
                try:
                    first_id_previous_page = driver.find_element(By.XPATH, line_path.format(1, headers['Id'])).text
                    driver.find_element(By.ID, 'incidente_workflows_datatable_next').click()
                except:
                    driver.find_element(By.ID, 'incident_workflows_datatable_next').click()

                for _ in range(20):
                    first_id_actual_page = driver.find_element(By.XPATH, line_path.format(1, headers['Id'])).text
                    if first_id_previous_page == first_id_actual_page:
                        time.sleep(6)
                        logger.info("Fim da paginação")
                        continue

                    n_itens = self._get_table_size()
                    break

            for item in range(1, n_itens + 1):
                if (item + 1) == 26:
                    i += 1
                    break

                id = driver.find_element(By.XPATH, line_path.format(item, headers["Id"])).text
                transport = driver.find_element(By.XPATH, line_path.format(item, headers["Transporte"])).text
                subreason = driver.find_element(By.XPATH, line_path.format(item, headers["Submotivo"])).text
                cte_attempt = driver.find_element(By.XPATH, line_path.format(item, headers['Tentativas CTE'])).text
                branch = driver.find_element(By.XPATH, line_path.format(item, headers['Centro'])).text

                if int(id) in self.itens_in_bd:
                    logger.info("Caso já existe no banco de dados")
                    continue

                # Se no campo de tentativas CTE não estiver em branco
                if cte_attempt:
                    logger.warning(f"ID {cte_attempt} possui tentativa de CTe")
                    continue

                reason = driver.find_element(By.XPATH, line_path.format(item, headers['Natureza'])).text
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
                        "id": id,
                        "center": center,
                        "transport": transport,
                        "subreason": subreason
                    }
                    self.incidents.append(item_data)
                    logger.info(f"Dados obtidos: {item_data}")
                else:
                    logger.warning(f"O motivo {reason} do id {id} esta fora do escopo da automação")
                    continue

        logger.info(f"{len(self.incidents)} incidentes são elegíveis para automação tratar")
        return True

    def get_incidents_additional_data(self):

        historic_element = "incidente_workflow_observacao"
        nf_element = "incidente_workflow_incidente_workflow_nfs_attributes_0_numero_nf"
        index = 0

        for incident in self.incidents:

            try:
                logger.info(f"Iniciando a obtenção de dados adicionais para o ID: {incident['id']}")

                url_edit_incident = os.getenv("BBA_PORTAL_INCIDENTS_URL").replace("*", incident["id"])
                driver.get(url_edit_incident)
                historic_el = wait.until(EC.presence_of_element_located((By.ID, historic_element)))
                historic = historic_el.text

                incident['cte_value'] = self.get_cte_value(historic=historic)
                incident["contract_value"], incident['driver_value'] = self.get_contract_value(historic=historic,
                                                                                               incident=incident)
                incident["nf"] = driver.find_element(By.ID, nf_element).get_attribute('value')

                if not incident['driver_value'] or not incident['cte_value'] or not incident['contract_value']:
                    logger.error("Falha ao valor do motorista, cte ou contrato do histórico do caso para p "
                                 f"ID: {incident['id']}")

                    raise Exception("Driver, cte or contract value not exisits")

                if float(incident['cte_value']) < 7000.00:
                    self.incidents[index] = incident

                    logger.info(f'Informação de valores encontrados para o ID {incident["id"]}. '
                                f'Valor motorista: {incident["driver_value"]} - Valor cte {incident["cte_value"]} - '
                               f'N nf {incident["nf"]}')
                else:
                    message = ('Valor de CT-e é maior ou igual a R$ 7.000,00. Informação de valores encontrados '
                               f'para o ID {incident["id"]}. Valor motorista: {incident["driver_value"]} '
                               f'- Valor cte {incident["cte_value"]} - N nf {incident["nf"]}')
                    logger.warning(message)

                index += 1

            except Exception as error:
                logger.exception(f"Falha ao obter dados do histórico para o caso {incident['id']}")
                index += 1

    def get_driver_reimbursement_value(self, valor):
        inss = (float(valor) * 0.2) * 0.114
        sest_sesnat = (float(valor) * 0.2) * 0.025
        contrato = round((float(valor) + inss + sest_sesnat), 2)

        logger.info(f"Valor do contrato: {contrato}")

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
            if (valor_cte % float(reembolso["Truck"])) == 0:
                diaria = valor_cte / float(reembolso["Truck"])
                valor_contrato = diaria * float(reembolso["TruckCorrigido"])
                valor_contrato = round(valor_contrato, 2)
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                logger.info(f"Caso Truck, valor motorista: {valor_motorista}")

            elif (valor_cte % float(reembolso["Carreta"])) == 0:
                diaria = valor_cte / float(reembolso["Carreta"])
                valor_contrato = diaria * float(reembolso["CarretaCorrigido"])
                valor_contrato = round(valor_contrato, 2)
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                logger.info(f"Caso carreta, valor motorista: {valor_motorista}")

            else:
                valor_contrato = re.findall("VALOR TOTAL\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
                if not valor_contrato:
                    valor_contrato = re.findall("VALOR\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
                    if not valor_contrato:
                        logger.error(
                            "Não foi encontrado o valor do contrato, nem pelo padrão VALOR TOTAL, nem pelo padrão "
                            "VALOR.")
                        raise Exception("Valor do contrato não obtido")

                valor_contrato = valor_contrato[-1] if valor_contrato else None
                valor_contrato = self.ajusta_valor_moeda(valor=str(valor_contrato))
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                logger.info(f"Nem Truck, nem carreta, valor motorista: {valor_motorista}")

            return valor_motorista, valor_contrato
        except Exception as e:
            logger.exception("Falha ao ajustar o valor para truck ou carreta")
            valor_motorista = None
            valor_contrato = None
            return valor_motorista, valor_contrato

    @staticmethod
    def ajusta_valor_moeda(valor):
        if valor[-3] == '.':
            valor = valor.replace(',', '')
        elif valor[-3] == ',':
            valor = valor.replace('.', '').replace(',', '.')
        else:
            valor = 'error'
        return valor

    def get_cte_value(self, historic):
        valor_cte = None

        try:
            valor_cte = re.findall(r"RESULTADO\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
            valor_cte = valor_cte[-1] if valor_cte else None
            if not valor_cte:
                raise ValueError('CTE')
            valor_cte = self.ajusta_valor_moeda(valor=str(valor_cte))
        except ValueError as e:
            logger.exception(f"Problema ao procurar o valor do {e}")
            valor_cte = None
        finally:
            return valor_cte

    def get_contract_value(self, historic, incident):

        try:
            valor_contrato = re.findall("VALOR TOTAL\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
            if not valor_contrato:
                valor_contrato = re.findall("VALOR\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
                if not valor_contrato:
                    logger.error("Não foi encontrado o valor do contrato, nem pelo padrão VALOR TOTAL, nem pelo padrão "
                                 "VALOR.")
                    raise Exception("Problema ao obter o valor do contrato")

            valor_contrato = valor_contrato[-1]

            valor_contrato = self.ajusta_valor_moeda(valor=str(valor_contrato))
            valor_motorista = self.get_driver_reimbursement_value(valor=float(valor_contrato))

        except Exception as e:
            valor_contrato = None
            valor_motorista = None

        finally:
            return valor_contrato, valor_motorista

    def get_nfs(self):

        logger.info("Etapa de obtencao dos cte code")
        for index, incident in enumerate(self.incidents):
            try:
                driver.get(os.getenv("BBA_PORTAL_TRANSPORT_URL") + incident["transport"])
                wait.until(EC.presence_of_element_located((By.ID, "nav_dados_transporte")))

                for i in range(15):
                    document_exist = False
                    try:
                        url_pdf = driver.find_element(By.XPATH, f"//*[@id='doc_{i}']/a").text
                        name = re.search("(^Viagem)[A-z]?[0-9]+?", url_pdf)

                        if name:
                            logger.info("Documento viagem existe")
                            pdf_link = driver.find_element(By.XPATH, f"//*[@id='doc_{i}']/a").get_attribute("href")
                            document_exist = True
                            break
                    except Exception as e:
                        document_exist = False
                        logger.info(f"Não existe documento com nome \"Viagem\" para o id {incident['id']}")
                        break

                if not document_exist:
                    logger.info(f"Falta documento no portal para o id {incident['id']}")

                    index += 1
                    continue

                response = self.br.open(pdf_link)
                with open(OUTPUT_DIR + "/download.pdf", "wb") as f:
                    f.write(response.read())

                wait_file(OUTPUT_DIR, 'download.pdf')

                dados = self.get_nf_data(nf_portal=int(incident["nf"]))

                if dados['cte_fretolog_code']:
                    self.get_number_of_incidents(incident=incident)

                self.incidents[index]["cte_code_fretolog"] = dados["cte_fretolog_code"]
                self.incidents[index]["cte_code_levolog"] = dados["cte_levolog_code"]
                self.incidents[index]["serie_levolog"] = dados["serie_levolog"]
                self.incidents[index]["serie_fretolog"] = dados["serie_fretolog"]
                self.incidents[index]["pf"] = dados["pf"]
                self.incidents[index]["data"] = dados["data"]
                self.incidents[index]['freto_lot'] = dados['freto_lot']
                self.incidents[index]['levo_lot'] = dados['levo_lot']

                index += 1

                if self.store.status["code"] == 1:
                    logger.info(f"Não foi encontrado o CTE ou série no documento acessado para o id {incident['id']}")

                    self.store.send_email(
                        subject=self.subject,
                        recipients=self.to,
                        body="Prezados,\nNão foi encontrado o CTE ou série no documento acessado para o id {0}".format(
                            incident['id'])
                    )
            except Exception as e:
                logger.info("Falha ao extrair dados das NFs ou na obtenção da quantidade de incidentes")
                browser_lib.screenshot(
                    filename=OUTPUT_DIR + '\\' + incident['id'] + '_Informacoes_adicionais.png'
                )

        logger.info("Etapa de obtencao dos cte finalizada")

    def get_nf_data(self, nf_portal):

        serie_fretolog = None
        cte_fretolog_code = None
        cte_levolog_code = None
        serie_levolog = None
        data = None
        pf = False
        freto_lot = None
        levo_lot = None
        index = 0
        dados = {}

        try:
            logger.info("Inicio de obtenção de dados da nf")
            flag = False
            with pdfplumber.open(OUTPUT_DIR + "/download.pdf") as pdf:
                pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

            # pdf.open_pdf(OUTPUT_DIR + "/download.pdf")
            # text = pdf.get_text_from_pdf(OUTPUT_DIR + "/download.pdf")
            # strTexto = json.dumps(text)

            logger.info("Texto do pdf obtido")

            nfs = re.findall("(Notas*\sf*F*iscais:*\s*\d+/?)(\d+)?", strTexto)
            verify = re.findall('(levo log)', strTexto.lower())
            data = re.findall('\d{2}/\d{2}/\d{4}', strTexto)
            freto_lot = re.findall('(?<=INÍCIO DA PRESTAÇÃO\\n).*?(?=TÉRMINO DA PRESTAÇÃO)',
                                   strTexto.encode('utf-8').decode('unicode_escape'))

            if not freto_lot:
                freto_lot = re.findall('(?<=INÍCIO DA PRESTAÇÃO\\n).*?(?=INÍCIO)',
                                       strTexto.encode('utf-8').decode('unicode_escape'))

            if verify:

                pf = True

                levo_lot = re.findall("(?:FILIAL\s)([A-Z -]+)(?=NOME)", strTexto)
                cte_levolog_code = re.findall(r"CTE\\n[0-9]+", strTexto)
                serie_levolog = re.findall(r"\\n\d+MODELO", strTexto)

                serie_fretolog = re.findall(r"(?:N* \d* Serie) (\d)", strTexto)

                if not cte_fretolog_code:
                    cte_fretolog_code = re.findall(r"(?:N*)(\d*) (?:Serie \d)", strTexto)

                if not serie_fretolog:
                    serie_fretolog = re.findall(r"Serie\s+(\d+)", strTexto, flags=re.IGNORECASE)

                if not cte_fretolog_code:
                    cte_fretolog_code = re.findall(r"\bN[oº]?\s*(\d+)", strTexto, flags=re.IGNORECASE)

            else:
                pf = False
                cte_fretolog_code = re.findall(r"CTE\\n[0-9]+", strTexto)
                serie_fretolog = re.findall(r"\\n\d+MODELO", strTexto)
                levo_lot = ['fretolog']

            if len(nfs) > 0:

                for nf in nfs:

                    for number in nf:
                        if str(nf_portal) in number:
                            flag = True
                            if pf:
                                cte_levolog_code = cte_levolog_code[index].replace("CTE\\n", "")
                                serie_levolog = serie_levolog[index].replace("\\n", "").replace("MODELO", "")
                                data = data[index]

                                if cte_fretolog_code:
                                    cte_fretolog_code = cte_fretolog_code[index]
                                    serie_fretolog = serie_fretolog[index]

                            else:

                                cte_levolog_code = "Não foi possível obter o dado na nota fiscal."
                                serie_levolog = "Não foi possível obter o dado na nota fiscal."
                                cte_fretolog_code = cte_fretolog_code[index].replace("CTE\\n", "")
                                serie_fretolog = serie_fretolog[index].replace("\\n", "").replace("MODELO", "")
                                data = data[0]
                            break

                    index += 1

                    if flag:
                        break

            if not flag:

                logger.warning(
                    'Numero da NF não encontrada no arquivo Viagem'
                )
                raise Exception

            else:

                logger.info("Sucesso ao obter os dados da nf")
                dados = {
                    "cte_levolog_code": cte_levolog_code,
                    "cte_fretolog_code": cte_fretolog_code,
                    "serie_levolog": serie_levolog,
                    "serie_fretolog": serie_fretolog,
                    "pf": pf,
                    "data": data,
                    "freto_lot": freto_lot[0],
                    "levo_lot": levo_lot[0]
                }

        except Exception as e:
            logger.error("Falha ao obter os dados da nf")

            dados = {
                "cte_levolog_code": None,
                "cte_fretolog_code": None,
                "serie_levolog": None,
                "serie_fretolog": None,
                "pf": None,
                "data": None,
                "freto_lot": None,
                "levo_lot": None
            }

        finally:
            logger.info(dados)
            os.remove(OUTPUT_DIR + "/download.pdf")
            return dados

    def get_number_of_incidents(self, incident):

        logger.info("Etapa de obtencao da quantidade de incidentes")

        incident_names = [
            'diáriaexterna',
            'diáriainterna',
            'pedágio',
            'reembolso'
        ]
        counter = 0

        try:
            for idx in range(1, 21):
                text = driver.find_element(By.XPATH, f'/html/body/div[3]/div/div/div[2]/div/div/div/div[6]/ul/li[{idx}]/a').text

                if text.lower() == 'incidentes':
                    btn = driver.find_element(By.XPATH, f"/html/body/div[3]/div/div/div[2]/div/div/div/div[6]/ul/li[{idx}]/a")
                    btn.click()
                    break

        except Exception as e:
            logger.error('Menu \"Incidentes\" não foi encontrado.')
            incident['number_of_incidents'] = None

        number_of_incidents = len(driver.find_elements(By.XPATH, "//*[@id='incidentes']/div"))
        # number_of_incidents = browser_lib.get_element_count('//*[@id="incidentes"]/div')

        for item in range(1, number_of_incidents + 1):

            text = driver.find_element(By.XPATH, f"//*[@id='incidentes']/div[{item}]/a").text

            splited_text = text.split("\n")
            splited_name = re.findall(r'[A-zÀ-ÿ-]+', splited_text[0])
            name = ''

            for sn in splited_name[1:]:
                if '-' in sn:
                    break
                name = name + sn

            if name.lower() in incident_names:

                id = re.findall('[0-9]+', splited_text[0])[0]
                phase = splited_text[1].replace("Etapa: ", "")
                status = splited_text[2].replace("Status: ", "")

                if id == incident['id'] and phase.lower() == 'emissão de cte' and status.lower() == 'em aberto':
                    counter += 1
                    logger.info(f"Incidente encontrado para o ID buscado. Id => {id} - Nome => {name} - "
                                f"Fase => {phase} - Status => {status}")

                    incident['incident_status'] = True

        incident['number_of_incidents'] = counter

        logger.info("Etapa de obtencao da quantidade de incidentes finalizada")

    def run(self):
        try:
            self.config()
            self.open()
            access = self.access()
            if not access:
                logger.error("Falha ao acessar o portal BBA")
                raise Exception
            self.search_for(term="emissão de cte")
            incidents = self.get_incidents()
            if not incidents:
                logger.info(f"Nenhum Registro encontrado")
                return

            self.get_incidents_additional_data()
            self.get_nfs()

            logger.info("Fim da obtenção dos casos, inserindo-os na fila.")

        except Exception as e:
            logger.exception(f"Erro na obtenção dos dados da NF.")
        finally:
            driver.close()
            return self.incidents

BelgoPortal([]).run()