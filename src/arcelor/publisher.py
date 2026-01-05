import pandas as pd
from dotenv import load_dotenv
from shared import sharepoint
from rabbitmq import publisher
import os

load_dotenv()

# Outras classes
from freto import Freto
# Biliotecas
import os
import json
import time
import pandas as pd
from pathlib import Path
from pipefy_handler import API
from shared.logger import logger
import freto_portal

OUTPUT_DIR = f"{os.getcwd()}/output"
INPUT_DIR = f"{os.getcwd()}/input"


class Main:

    def __init__(self):
        self.incidents = API().get_card_data()

    def run(self):
        try:
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

                publisher.rabbit_mq_publisher(
                    data=incidents,
                    queue_name="jmendes"
                )

            else:
                logger.info('Não há casos para serem tratados')

        finally:
            os.system("taskkill /IM chrome.exe /IM msedge.exe /F")
            os.system("taskkill /f /im IEDriverServer.exe")
            os.system("taskkill /f /im msedge.exe")


if __name__ == "__main__":
    Main().run()
