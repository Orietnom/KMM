from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
from shared.logger import logger
from dotenv import load_dotenv

import math
import os
import re
import time
import json
import os
import mechanize

load_dotenv()
INPUT_DIR = f"{os.getcwd()}\\input"
OUTPUT_DIR = f"{os.getcwd()}\\output"

driver_path = ChromeDriverManager().install()
driver = webdriver.Chrome(executable_path=driver_path)
wait = WebDriverWait(driver, 30)
chrome_options = Options()
chrome_options.add_experimental_option(
    "prefs",
    {
        "download.default_directory": os.path.join(os.getcwd(), 'downloads'),   # pasta de download
        "download.prompt_for_download": False,        # não perguntar
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True                  # evita bloqueio do Chrome
    }
)
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
        btn.click()

    def access(self):
        logger.info("Realizando login")
        try:
            driver.find_element(By.ID, "user_email").send_keys(os.getenv("BBA_PORTAL_USERNAME"))
            driver.find_element(By.ID, "user_password").send_keys(os.getenv("BBA_PORTAL_PASSWORD"))

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
        input_field = "xpath://*[@id='incidente_workflows_datatable_filter']/label/input"
        text_box = wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id='incidente_workflows_datatable_filter']/label/input")))
        text_box.send_keys(term)

    def get_incidents(self):

        self.incidents = []
        line_path = "xpath://*[@id=\"incidente_workflows_datatable\"]/tbody/tr[{0}]/td[{1}]"
        validation = browser_lib.get_text("xpath://tbody")
        itens = browser_lib.get_text("id:incidente_workflows_datatable_info")
        total_itens = int(re.search("\d+ registro", itens).group().replace("registro", "").strip())
        n_itens = total_itens
        itens_de = int(re.findall('(?:Mostrando de\s*)(\d*)', itens)[0])
        itens_ate = int(re.findall('(?:Mostrando de\s*\d*\s*até\s*)(\d*)', itens)[0])
        logger.info(
            f'Mostrando de {itens_de} até {itens_ate}',
            
        )

        logger.info(f"{n_itens} incidentes encontrados. Filtrando...")

        if validation == "Nenhum registro encontrado":
            self.store.set_status(
                code=1,
                step="BelgoPortal.get_incidents",
                error="Nenhum registro encontrado",
                message="Nenhum registro encontrado"
            )

            self.store.send_email(
                subject=self.subject,
                body=self.body_2,
                recipients=self.to,
                attachments=""
            )
        else:
            first_id_previous_page = None
            for i in range(math.ceil(total_itens / 25)):

                if i > 0:
                    try:
                        first_id_previous_page = browser_lib.get_text(line_path.format(1, 1))
                        browser_lib.click_element("id:incidente_workflows_datatable_next")
                    except:
                        browser_lib.click_element("id:incident_workflows_datatable_next")

                    # time.sleep(5)

                    for i in range(20):
                        first_id_actual_page = browser_lib.get_text(line_path.format(1, 1))
                        if first_id_previous_page == first_id_actual_page:
                            time.sleep(6)
                            continue
                        itens = browser_lib.get_text("id:incidente_workflows_datatable_info")
                        itens_de = int(re.findall('(?:Mostrando de\s*)(\d*)', itens)[0])
                        itens_ate = int(re.findall('(?:Mostrando de\s*\d*\s*até\s*)(\d*)', itens)[0])
                        logger.info(f'Mostrando de {itens_de} até {itens_ate}')
                        n_itens = itens_ate - itens_de + 1
                        break

                for item in range(n_itens):
                    if (item + 1) == 26:
                        i += 1
                        break
                    # Se no campo de tentativas CTE não estiver em branco
                    if not browser_lib.get_text(line_path.format(item + 1, 9)):
                        continue

                    branch = browser_lib.get_text(line_path.format(item + 1, 4))
                    # Se no campo Centro Conter Mesquita
                    if "MESQUITA" in branch:
                        center = "FRETO LOG - FILIAL RJ"
                    else:
                        center = "FRETO LOG - MATRIZ"

                    reason = browser_lib.get_text(line_path.format(item + 1, 6))
                    if (
                            reason == "DESCARGA" or
                            reason == "TICKET DE PEDÁGIO NÃO EMITIDO" or
                            reason == "DESLOCAMENTO" or
                            reason == "COMPLEMENTO DE PEDÁGIO" or
                            reason == "PEDÁGIO COMPLEMENTO DE VALOR" or
                            reason == "DEMORA NO CARREGAMENTO" or
                            reason == "OUTROS" or
                            reason == "REVERSA" or
                            reason == "VEÍCULO SEM TAG" or
                            reason == "DIÁRIA NA DESCARGA" or
                            reason == "AJUSTE FINANCEIRO DE CTE"
                    ):
                        id = browser_lib.get_text(line_path.format(item + 1, 1))
                        transport = browser_lib.get_text(line_path.format(item + 1, 2))
                        subreason = browser_lib.get_text(line_path.format(item + 1, 6))

                        if int(id) in self.itens_in_bd:
                            logger.info('Caso já existe no BD')
                            continue
                    else:
                        continue

                    dict = {
                        "id": id,
                        "center": center,
                        "transport": transport,
                        "subreason": subreason
                    }

                    self.incidents.append(dict)
                    logger.info(f"Dados obtidos: {dict}")

            logger.info(f"{len(self.incidents)} incidentes são elegíveis para automação tratar")

    def get_incidents_additional_data(self):

        historic_element = "id:incidente_workflow_observacao"
        nf_element = "id:incidente_workflow_incidente_workflow_nfs_attributes_0_numero_nf"
        index = 0

        for incident in self.incidents:

            try:
                logger.info(f"Iniciando a obtenção de dados adicionais para o ID: {incident['id']}")

                url_edit_incident = self.paths["url_edit_incidents"].replace("*", incident["id"])
                browser_lib.go_to(url_edit_incident)
                time.sleep(10)
                historic = browser_lib.find_element(historic_element)
                historic = historic.text

                incident['cte_value'] = self.get_cte_value(historic=historic)
                incident["contract_value"], incident['driver_value'] = self.get_contract_value(historic=historic,
                                                                                               incident=incident)
                incident["nf"] = browser_lib.get_value(nf_element)

                if (not incident['driver_value']) or (not incident['cte_value']) or (not incident['contract_value']):
                    self.mail.send_email(
                        subject=self.subject,
                        body="Falha ao obter dados referente ao histórico. ID: {0}, TRANSPORTE: {1}".format(
                            incident['id'], incident['transport']),
                        recipients=self.to,
                        attachments=""
                    )
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
                    logger.info(message)

                    self.mail.send_email(
                        subject=self.subject,
                        body=message,
                        recipients=self.to,
                        attachments=""
                    )
                index += 1

            except Exception as error:
                self.store.set_status(
                    code=1,
                    step="Belgo_Portal.get_incidents_additional_data",
                    message="Falha ao obter informações adicionais para o id: {0}. Erro {1}".format(
                        incident['id'], str(error))
                )
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
                "Taxa1": "0.2",
                "Taxa2": "0.114",
                "Taxa3": "0.2",
                "Taxa4": "0.025",
                "Truck": "320.24",
                "TruckCorrigido": "288.53",
                "Carreta": "512.41",
                "CarretaCorrigido": "461.67"
            }
            if (valor_cte % float(reembolso["Truck"])) == 0:
                diaria = valor_cte / float(reembolso["Truck"])
                valor_contrato = diaria * float(reembolso["TruckCorrigido"])
                valor_contrato = round(valor_contrato, 2)
                valor_motorista = BelgoPortal.get_driver_reimbursement_value(
                    self=self, valor=valor_contrato)

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
                        raise ("Valor do contrato não obtido")

                valor_contrato = valor_contrato[-1] if valor_contrato else None
                valor_contrato = self.ajusta_valor_moeda(valor=str(valor_contrato))
                valor_motorista = self.get_driver_reimbursement_value(valor=valor_contrato)

                logger.info(f"Nem Truck, nem carreta, valor motorista: {valor_motorista}")

            return valor_motorista, valor_contrato
        except Exception as e:
            print(str(e))
            valor_motorista = None
            valor_contrato = None
            return valor_motorista, valor_contrato

    def ajusta_valor_moeda(self, valor):
        if valor[-3] == '.':
            valor = valor.replace(',', '')
        elif valor[-3] == ',':
            valor = valor.replace('.', '').replace(',', '.')
        else:
            valor = 'error'
        return valor

    def get_cte_value(self, historic):

        try:
            valor_cte = re.findall(r"RESULTADO\s*(?:R?\$?\s*)+(\d+.?\d+.\d{2})", historic)
            valor_cte = valor_cte[-1] if valor_cte else None
            if not valor_cte:
                raise ValueError('CTE')
            valor_cte = self.ajusta_valor_moeda(valor=str(valor_cte))

            # icms = re.findall(r"(?:ICMS OU ISS\s*)([0-9.,]+)", historic)
            # icms = icms[-1] if icms else None
            # if not icms:
            #     raise ValueError('ICMS')
            # icms = icms.replace(',', '.')

            # valor_cte_corrigido = round(float(valor_cte) * (1 - (float(icms) / 100)), 2)
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

        index = 0
        logger.info("Etapa de obtencao dos cte code")
        for index, incident in enumerate(self.incidents):
            try:
                browser_lib.go_to(self.paths["url_transporte"] + "/" + incident["transport"])
                browser_lib.wait_until_element_is_visible('id:nav_dados_transporte')
                for i in range(15):
                    try:
                        url_pdf = browser_lib.get_text("xpath://*[@id=\"doc_{0}\"]/a".format(i))
                        name = re.search("(^Viagem)[A-z]?[0-9]+?", url_pdf)
                        if name != None:
                            logger.info("Documento viagem existe")
                            pdf_link = browser_lib.get_element_attribute("xpath://*[@id=\"doc_{0}\"]/a".format(i),
                                                                         "href")
                            documet_exist = True
                            break
                    except:

                        documet_exist = False
                        logger.info(f"Não existe documento com nome \"Viagem\" para o id {incident['id']}")
                        break

                if documet_exist == False:
                    logger.info(f"Falta documento no portal para o id {incident['id']}")

                    index += 1
                    continue

                response = self.br.open(pdf_link)
                with open(OUTPUT_DIR + "/download.pdf", "wb") as f:
                    f.write(response.read())

                time.sleep(10)

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

        try:
            logger.info("Inicio de obtenção de dados da nf")
            flag = False
            pdf.open_pdf(OUTPUT_DIR + "/download.pdf")
            text = pdf.get_text_from_pdf(OUTPUT_DIR + "/download.pdf")
            strTexto = json.dumps(text)

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

            if flag == False:

                self.store.set_status(
                    code=1,
                    step="KMM.get_nf_data",
                    error="Falha ao obter os dados da nf"
                )
                logger.warning(
                    'Numero da NF não encontrada no arquivo Viagem'
                )
                raise Exception

            else:

                self.store.set_status(
                    code=2,
                    step="KMM.get_nf_data",
                    message="Sucesso ao obter os dados da nf"
                )

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
            self.store.set_status(
                code=1,
                step="KMM.get_nf_data",
                error=f"Falha ao obter os dados da nf. ERRO => {str(e)}"
            )

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
            pdf.close_all_pdfs()
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
                text = browser_lib.get_text(f'xpath=/html/body/div[3]/div/div/div[2]/div/div/div/div[6]/ul/li[{idx}]/a')
                if text.lower() == 'incidentes':
                    browser_lib.click_element(
                        f"xpath=/html/body/div[3]/div/div/div[2]/div/div/div/div[6]/ul/li[{idx}]/a")
                    break

        except Exception as e:
            logger.info('Menu \"Incidentes\" não foi encontrado.')
            incident['number_of_incidents'] = None

        number_of_incidents = browser_lib.get_element_count('//*[@id="incidentes"]/div')

        for item in range(number_of_incidents):

            text = browser_lib.get_text(f'xpath=//*[@id="incidentes"]/div[{item + 1}]/a')
            text_splited = text.split("\n")
            name_splited = re.findall(r'[A-zÀ-ÿ-]+', text_splited[0])
            name = ''

            for item in name_splited[1:]:
                if '-' in item:
                    break
                name = name + item

            if name.lower() in incident_names:

                id = re.findall('[0-9]+', text_splited[0])[0]
                phase = text_splited[1].replace("Etapa: ", "")
                status = text_splited[2].replace("Status: ", "")

                if id == incident['id'] and phase.lower() == 'emissão de cte' and status.lower() == 'em aberto':
                    counter += 1
                    logger.info(f"Incidente encontrado para o ID buscado. Id => {id} - Nome => {name} - "
                                f"Fase => {phase} - Status => {status}")

                    incident['incident_status'] = True

        incident['number_of_incidents'] = counter

        logger.info("Etapa de obtencao da quantidade de incidentes finalizada")

    # def adjust_cte_value(self):
    #     for incident in self.incidents:
    #         if not incident['cte_value']:
    #             continue
    #         incident['cte_value'] = round(float(incident['cte_value']) * (1 - (incident['icms'] / 100)), 2)

    def run(self):
        try:
            self.config()
            self.open()
            self.access()
            self.search_for(term="emissão de cte")
            self.get_incidents()
            self.get_incidents_additional_data()
            self.get_nfs()
            browser_lib.close_all_browsers()

            logger.info("Fim da obtenção dos casos, inserindo-os na fila.")

        except Exception as e:
            # traceback.print_exc()
            logger.exception(f"Erro na obtenção dos dados da NF. ERRO: {str(e)}")
            browser_lib.close_all_browsers()
        finally:
            return self.incidents

BelgoPortal([]).run()