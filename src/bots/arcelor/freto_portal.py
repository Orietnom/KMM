from zipfile import Path

import requests
import time
import re
import os
from shared.logger import logger
from pipefy_handler import API
from pdf_handler import read_pdf
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
load_dotenv()

driver_path = ChromeDriverManager().install()
driver = webdriver.Chrome(executable_path=driver_path)
wait = WebDriverWait(driver, 30)
output_dir = Path.cwd() / 'output'

def login():
    try:
        logger.info("Login no portal freto")
        driver.get(os.getenv("FRETO_PORTAL_URL"))

        # realizando o login dentro do site
        driver.find_element(by=By.ID, value="Email").send_keys(os.getenv("FRETO_PORTAL_USERNAME"))
        driver.find_element(by=By.ID, value="Password").send_keys(os.getenv("FRETO_PORTAL_PASSWORD"))
        driver.find_element(by=By.ID, value="btnLogin").click()

        time.sleep(5)
        return True
    except Exception as e:
        logger.exception(f'Falha ao logar. Erro -> {str(e)}')
        return False


def get_incidents_data(incidents):

    try:
        transports = []
        logger.info("Inicio da obtencao dos dados dos incidentes")

        index = 0
        for incident in incidents:

            if not incident['Transporte']:
                continue
            else:
                API().move_card(phase='Portal Freto', card_id=incident['card id'])

            incident['Transporte'] = int(incident['Transporte'])

            if "," in str(incident["Valor a pagar (Contrato)"]):
                incident["Valor a pagar (Contrato)"] = str(incident["Valor a pagar (Contrato)"]).replace(",", "")
            if "," in str(incident["Valor aprovado emissão (CTe)"]):
                incident["Valor aprovado emissão (CTe)"] = str(incident["Valor aprovado emissão (CTe)"]).replace(",",
                                                                                                                 "").strip()

            if (incident["Motivo"] == "Pedágio") or (incident["Motivo"] == "Pedagio"):
                logger.info(f"Motivo {incident['Motivo']} detectado, realizando ajuste no valor do contrato")

                valor_contrato = reimbursement(valor=incident["Valor a pagar (Contrato)"])
                incident["Valor a pagar (Contrato)"] = str(valor_contrato)

            if float(incident["Valor a pagar (Contrato)"]) >= 7000.00:
                logger.info(f"Valor do contrato excedeu R$7.000,00. Valor -> {incident['Valor a pagar (Contrato)']}")
                
                incident["motorista"] = None
                incident["Cte"] = None
                index += 1
                transports.append(incident)
                continue

            incident["motorista"] = get_driver_name(transport_number=incident['Transporte'])

            if type(incident["motorista"]) == dict or not incident['motorista']:
                logger.exception("Falha ao encontrar o nome do motorista")
                index += 1
                continue

            incident["cte_levolog"], incident["serie_levolog"], incident["cte_fretolog"], incident[
                "serie_fretolog"] = get_cte_value()

            if incident['cte_levolog'] != "arquivo viagem nao encontrado":
                logger.success(f"CTE levolog encontrado -> {incident['cte_levolog']}")

            if incident['cte_fretolog'] != "arquivo viagem nao encontrado":
                logger.success(f"CTE fretolog encontrado -> {incident['cte_fretolog']}")

            transports.append(incident)

            index += 1

    except Exception as e:
        logger.exception(f"Falha ao obter dados do incidente. Erro: {e}")
    finally:
        return transports

def get_driver_name(transport_number):
    try:

        logger.info(
            "Buscando nome do motorista",
        )

        driver.get(os.getenv("FRETO_PORTAL_CALENDAR"))
        wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id=\"calendar\"]/div[1]/div[1]/button")))

        time.sleep(5)

        driver.find_element(by=By.ID, value="nameTransport").send_keys(transport_number)
        time.sleep(10)

        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "fc-title")))
        except:
            for i in range(6):
                logger.info("Nao encontrou o valor no mes atual, buscando no anterior")

                driver.find_element(By.XPATH, "//*[@id=\"calendar\"]/div[1]/div[1]/div/button[1]").click()
                time.sleep(5)
                try:
                    wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "fc-title")))
                    break
                except:
                    if i < 5:
                        continue
                    else:
                        logger.warning("Valor não encontrado")

                        infos = {
                            'numero_cte': 'numero cte nao encontrado', 'motorista': ''}
                        return infos

        driver.find_element(By.CLASS_NAME, "fc-title").click()
        time.sleep(5)

        driver.find_element(by=By.ID, value="ticketLoadRequestItem1").click()
        driver_name_locator = wait.until(EC.visibility_of_element_located((By.ID, "ticketDriverName1")))

        driver_name = driver_name_locator.text
        logger.success(f'Nome do motorista encontrado=> {driver_name}')
        
        return driver_name

    except Exception as e:
        logger.exception(f"Falha ao obter dados do motorista. Erro: {e}")
        return None
       
def get_cte_value():
    try:

        logger.info("Obtencao do CTE")

        pdfs = []

        wait.until(EC.visibility_of_element_located((By.ID, "abrirArqs1")))
        time.sleep(7)
        driver.find_element(by=By.ID, value="abrirArqs1").click()
        logger.info("Clique em ver arquivos")

        wait.until(EC.visibility_of_element_located((By.ID, "myId1")))
        
        arquivo = driver.find_element(by=By.ID, value="myId1").text
        logger.info(f"arquivos {arquivo}")
        arquivo = arquivo.split('\n')

        for index, documento in enumerate(arquivo):
            documento_pj = re.search("^Viagem\d*.pdf", documento)
            documento_pf = re.search("^ct-e\d*.pdf", documento.lower())

            if documento_pj or documento_pf:
                doc_idx = (index + 1) / 2
                logger.info(str(index + 1), documento)
                url_pdf = driver.find_element(By.XPATH, f"//*[@id=\"myId1\"]/div[{doc_idx}]/a[2]").get_attribute("href")

                time.sleep(2)
                if not url_pdf:
                    continue

                file_data = {
                    "name": documento,
                    "url": url_pdf,
                    "response": requests.get(url_pdf)
                }

                pdfs.append(file_data)

        if not pdfs[0]['name']:
            logger.error('Arquivo não encontrado')
            
            numero_cte_fretolog = ''
            numero_cte_levolog = 'arquivo viagem nao encontrado'
            serie_fretolog = ''
            serie_levolog = ''

        else:
            if len(pdfs) == 2:

                logger.info("PF")

                for data in pdfs:
                    open(output_dir / data['name'], "wb").write(data['response'].content)
                    if 'viagem' in data['name'].lower():
                        numero_cte_levolog, serie_levolog = read_pdf(data['name'])
                    else:
                        numero_cte_fretolog, serie_fretolog = read_pdf(data['name'])
                    os.remove(data['name'])
            else:
                logger.info("PJ")
                open(output_dir / pdfs[0]['name'], "wb").write(pdfs[0]['response'].content)
                numero_cte_fretolog, serie_fretolog = read_pdf(pdfs[0]['name'])
                numero_cte_levolog = ''
                serie_levolog = ''
            
            logger.success(
                f"Número do CTE encontrados => levolog {numero_cte_levolog} e fretolog {numero_cte_fretolog}"
            )
            logger.success(
                f"Número das Series encontrados => levolog {serie_levolog} e fretolog {serie_fretolog}"
            )
            
        return numero_cte_levolog, serie_levolog, numero_cte_fretolog, serie_fretolog

    except Exception as e:
        logger.exception(f"Falha ao obter as informações do cte {str(e)}")
        return None, None, None, None


def reimbursement(valor):
    inss = (float(valor) * float(os.getenv("Taxa1"))) * float(os.getenv("Taxa2"))
    sest_sesnat = (float(valor) * float(os.getenv("Taxa3"))) * float(os.getenv("Taxa4"))
    contrato = round((float(valor) + float(inss) + float(sest_sesnat)), 2)
    return contrato


def close_browser():
    driver.close()


def run(incidents):
    try:
        login_status = login()
        if not login_status:
            raise Exception("Falha no login")
        transports = get_incidents_data(incidents)
        if not transports:
            raise Exception("Falha ao obter o incidente")
        driver.close()
        return transports
    except Exception as e:
        logger.exception(f"Erro => {str(e)}")
        return []
