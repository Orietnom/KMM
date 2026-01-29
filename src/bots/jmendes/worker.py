import json
import pandas as pd
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from src.bots.jmendes.kmm_process import process
from src.bots.jmendes.models import JMNItemProcess
from src.shared.logger import logger
from src.shared.db_handler.db_handler import DB, create_return_excel
from src.shared.email_handler import send_email
import src.exceptions.personalized_exceptions as pe
load_dotenv()

RABBITMQ_URL = os.getenv("RABBIT_URL")
QUEUE_NAME = "jmendes"


def process_case() -> None:

    try:
        db = DB()
        cases = db.get_data(
            table="complementar_jmendes"
        )
    except Exception as e:
        logger.exception("Falha ao obter os casos do banco de dados")
        return False

    if not cases:
        logger.info("Não há casos")
        return

    for case in cases:
        try:
            retry = case['RETENTATIVA'] + 1
            db.update(
                table='complementar_jmendes',
                column='STATUS_',
                value='Processando',
                id=case["ID"]
            )
            db.update(
                table='complementar_jmendes',
                column='RETENTATIVA',
                value=retry,
                id=case["ID"]
            )
 
            processed = process(
                JMNItemProcess(
                    license_plate=case.get('PLACA'),
                    driver_name=case.get('NOME_MOTORISTA'),
                    tbe=case.get('TBE'),
                    nature=case.get('NATUREZA'),
                    operation=case.get('OPERACAO'),
                    route=case.get('ROTA'),
                    card=case.get('CARTAO'),
                    sender=case.get('REMETENTE'),
                    recipient=case.get('DESTINATARIO'),
                    contract_value=case.get('VALOR_CONTRATO'),
                    bd_id=case.get("ID"),
                    management=case.get('GESTAO'),
                    contract=case.get('CONTRATO')
                )
            )
            if processed:
                db.update(
                    table='complementar_jmendes',
                    column='STATUS_',
                    value='OK',
                    id=case["ID"]
                )
                db.update(
                    table='complementar_jmendes',
                    column='FINALIZADO_EM',
                    value=datetime.now(),
                    id=case["ID"]
                )
            else:
                raise Exception(f"Falha ao processar o caso de TBE {case.get('TBE')}")
        except pe.KMMProcess as pe_error:
            db.update(
                table='complementar_jmendes',
                column='STATUS_',
                value='Falha no KMM',
                id=case["ID"]
            )
            logger.exception(pe_error)
        except RuntimeError as re:
            db.update(
                table='complementar_jmendes',
                column='STATUS_',
                value='Falha de lentidão KMM',
                id=case["ID"]
            )
            logger.exception(re)
        except Exception as e:
            logger.exception(f"Falha não mapeada. Erro {str(e)}")
            db.update(
                table='complementar_jmendes',
                column='STATUS_',
                value='Falha no KMM não mapeada',
                id=case["ID"]
            )

if __name__ == "__main__":
    logger.info("Inicio da execução")
    process_case()
    file_path = Path(__file__).resolve().parent / "output" / f"Retorno JMendes.xlsx"
    created = create_return_excel(file_path, 'complementar_jmendes')
    if created:
        send_email(
            os.getenv("JMN_RECIPIENTS"),
            "Automação J Mendes Finalizada",
            "Segue em anexo a planilha gerada",
            file_path
        )
    else:
        send_email(
            os.getenv("JMN_RECIPIENTS"),
            "Automação J Mendes Finalizada",
            "Não há casos"
        )
    logger.info("Fim da execução")