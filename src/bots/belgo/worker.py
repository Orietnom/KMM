import json
import os
from dotenv import load_dotenv
from src.bots.belgo.kmm_process import process
from src.bots.belgo.models import BelgoItemProcess
from src.shared.logger import logger
from src.shared.db_handler.db_handler import DB
import exceptions.personalized_exceptions as pe
load_dotenv()

RABBITMQ_URL = os.getenv("RABBIT_URL")
QUEUE_NAME = "jmendes"


def process_case() -> None:

    try:
        db = DB()
        cases = db.get_data(
            table="complementar_belgo2"
        )
    except Exception as e:
        logger.exception("Falha ao obter os casos do banco de dados")
        return False

    for case in cases:
        try:
            retry = case['RETENTATIVA'] + 1
            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value='Processando',
                id=case["ID"]
            )
            db.update(
                table='complementar_belgo2',
                column='RETENTATIVA',
                value=retry,
                id=case["ID"]
            )

            processed = process(
                BelgoItemProcess(
                    bd_id=case.get('ID'),
                    transport=case.get('TRANSPORTE'),
                    center=case.get('FILIAL'),
                    freto_lot=case.get('LOTACAO_FRETOLOG'),
                    levo_lot=case.get('LOTACAO_LEVOLOG') if case.get('LOTACAO_LEVOLOG') != 'fretolog'
                )
            )
            if processed:
                db.update(
                    table='complementar_belgo2',
                    column='STATUS_',
                    value='OK',
                    id=case["ID"]
                )
            else:
                raise Exception(f"Falha ao processar o caso de TBE {case.get('TBE')}")
        except pe.KMMProcess as pe_error:
            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value='Falha no KMM',
                id=case["ID"]
            )
            logger.exception(pe_error)
        except RuntimeError as re:
            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value='Falha de lentidão KMM',
                id=case["ID"]
            )
            logger.exception(re)
        except Exception as e:
            logger.exception(f"Falha não mapeada. Erro {str(e)}")
            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value='Falha no KMM não mapeada',
                id=case["ID"]
            )

if __name__ == "__main__":
    process_case()
