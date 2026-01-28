import os
from dotenv import load_dotenv
from src.bots.arcelor.kmm_process import process
from src.bots.arcelor.models import ArcelorItemProcess
from shared.logger import logger
from shared.db_handler.db_handler import DB, create_return_excel
from shared.email_handler import send_email
import exceptions.personalized_exceptions as pe
from pathlib import Path
from datetime import datetime

load_dotenv()

RABBITMQ_URL = os.getenv("RABBIT_URL")
QUEUE_NAME = "arcelor"


def process_case() -> None:
    try:
        db = DB()
        cases = db.get_data(
            table="complementar_arcelor"
        )
    except Exception:
        logger.exception("Falha ao obter os casos do banco de dados")
        return False

    for case in cases:
        try:
            retry = case['RETENTATIVA'] + 1
            db.update(
                table='complementar_arcelor',
                column='STATUS_',
                value='Processando',
                id=case["ID"]
            )
            db.update(
                table='complementar_arcelor',
                column='RETENTATIVA',
                value=retry,
                id=case["ID"]
            )

            processed = process(
                ArcelorItemProcess(
                    cte_fretolog=case.get('CTE_FRETOLOG'),
                    serie_fretolog=case.get('SERIE_FRETOLOG'),
                    cte_levolog=case.get('CTE_LEVOLOG'),
                    serie_levolog=case.get('SERIE_LEVOLOG'),
                    transport=case.get('TRANSPORTE'),
                    driver_name=case.get('NOME_MOTORISTA'),
                    cte_value=case.get("VALOR_CTE"),
                    contract_value=case.get('VALOR_CONTRATO'),
                    center=case.get('FILIAL'),
                    card_id=case.get('CARD_ID'),
                    bd_id=case.get('ID'),
                    complement_cte_fretolog=case.get('CTE_FRETOLOG_COMPLEMENTAR'),
                    complement_cte_levolog=case.get('CTE_LEVOLOG_COMPLEMENTAR'),
                    contract=case.get('CONTRATO'),
                )
            )
            if processed:
                db.update(
                    table='complementar_arcelor',
                    column='STATUS_',
                    value='OK',
                    id=case["ID"]
                )
                db.update(
                    table='complementar_arcelor',
                    column='FINALIZADO_EM',
                    value=datetime.now(),
                    id=case["ID"]
                )
            else:
                raise Exception(f"Falha ao processar o caso de id {case.get('TRANSPORTE')}")
        except pe.KMMProcess as pe_error:
            logger.exception(pe_error)
            db.update(
                table='complementar_arcelor',
                column='STATUS_',
                value='Falha no KMM',
                id=case["ID"]
            )
        except RuntimeError as re:
            logger.exception(re)
            db.update(
                table='complementar_arcelor',
                column='STATUS_',
                value='Falha de lentidão KMM',
                id=case["ID"]
            )

        except Exception as e:
            logger.exception(f"Falha não mapeada. Erro {str(e)}")
            db.update(
                table='complementar_arcelor',
                column='STATUS_',
                value='Falha no KMM não mapeada',
                id=case["ID"]
            )

if __name__ == "__main__":
    process_case()
    file_path = Path.cwd() / 'output' / f"Retorno Arcelor.xlsx"
    created = create_return_excel(file_path, 'complementar_arcelor')

    if created:
        send_email(
            os.getenv("ARCELOR_RECIPIENTS"),
            "Automação Arcelor Finalizada",
            "Segue em anexo a planilha gerada",
            file_path
        )
    else:
        send_email(
            os.getenv("ARCELOR_RECIPIENTS"),
            "Automação Arcelor Finalizada",
            "Não há casos"
        )
