# Biliotecas
import os
import pandas as pd
import freto_portal
from shared.db_handler.db_handler import DB
from pipefy_handler import API
from shared.logger import logger

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = f"{os.getcwd()}/output"
INPUT_DIR = f"{os.getcwd()}/input"


class Main:

    def __init__(self):
        self.incidents = API().get_card_data()

    def run(self):
        try:
            if not self.incidents:
                logger.warning("Sem novos casos no Pipefy a serem tratados")
                return False

            incidents = freto_portal.run(
                incidents=self.incidents
            )

            if incidents:
                logger.info(
                    f"{len(self.incidents)} casos encontrados"
                )

                for incident in incidents:
                    logger.info(f"Verificando caso: {incident}")
                    if len(incident) < 8:
                        logger.error("Faltam informações relevantes para prosseguir")
                        continue

                    if not incident.get("motorista") or not incident.get("cte_levolog"):
                        logger.error("Falta informação do motorista ou do cte")
                        continue
                    else:

                        logger.info(f"incidente de transporte {incident['Transporte']} colocado na fila")

                        API().move_card(phase='CTe Freto', card_id=incident['card id'])
                        logger.info(
                            f"O card de id: {incident['card id']} foi movido para fila \'cte freto\'")

                df = pd.DataFrame(incidents)
                df_renamed = df.rename({
                    "Unidade": "UNIDADE",
                    "Transporte": "TRANSPORTE",
                    "Motivo": "MOTIVO",
                    "Valor a pagar (Contrato)": "VALOR_CONTRATO",
                    "Valor aprovado emissão (CTe)": "VALOR_CTE",
                    "Filial": "FILIAL",
                    "card_id": "CARD_ID",
                    "motorista": "NOME_MOTORISTA",
                    "cte_levolog": "CTE_LEVOLOG",
                    "serie_levolog": "SERIE_LEVOLOG",
                    "cte_fretolog": "CTE_FRETOLOG",
                    "serie_fretolog": "SERIE_FRETOLOG"
                })
                DB().insert(
                    table="complementar_arcelor",
                    df=df_renamed,
                    unique_keys=["CTE_FRETOLOG"]
                )

            else:
                logger.info('Não há casos para serem tratados')

        finally:
            os.system("taskkill /IM chrome.exe /IM msedge.exe /F")
            os.system("taskkill /f /im IEDriverServer.exe")
            os.system("taskkill /f /im msedge.exe")


if __name__ == "__main__":
    Main().run()
