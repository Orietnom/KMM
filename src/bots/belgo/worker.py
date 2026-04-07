import os
from dotenv import load_dotenv
from datetime import datetime
from src.bots.belgo.kmm_process import process
from src.bots.belgo.models import BelgoItemProcess
from src.shared.logger import logger
from src.shared.db_handler.db_handler import DB, create_return_excel
from src.shared.email_handler import send_email
import src.exceptions.personalized_exceptions as pe
from pathlib import Path
load_dotenv()

QUEUE_NAME = "belgo"


def process_case() -> None:
    log = logger.bind(service='belgo')
    try:
        db = DB()
        cases = db.get_data(
            table="complementar_belgo2",
            date_range=True
        )
    except Exception as e:
        log.exception("Falha ao obter os casos do banco de dados")
        return False

    if not cases:
        log.info("Não há casos")
        return

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
                    levo_lot=case.get('LOTACAO_LEVOLOG'),
                    nf=case.get('NOTA_FISCAL'),
                    submotive=case.get('SUBMOTIVO'),
                    cte_value=case.get('VALOR_CTE'),
                    contract_value=case.get('VALOR_CONTRATO'),
                    driver_value=case.get('VALOR_MOTORISTA'),
                    freto_cte=case.get('CTE_FRETOLOG'),
                    freto_serie=case.get('SERIE_FRETOLOG'),
                    levo_cte=case.get('CTE_LEVOLOG'),
                    levo_serie=case.get('SERIE_LEVOLOG'),
                    n_incidents=case.get('N_INCIDENTES'),
                    incident_id=case.get('ID_INCIDENTE'),
                    complement_cte_fretolog=case.get('CTE_FRETOLOG_COMPLEMENTAR'),
                    complement_cte_levolog=case.get('CTE_LEVOLOG_COMPLEMENTAR'),
                    contract=case.get('CONTRATO'),
                    complement_cte_fretolog_date=case.get('DATA_EMISSAO_CTE_FRETO'),
                    edicao_caso=case.get('EDICAO_CASO')
                )
            )
            if processed:
                db.update(
                    table='complementar_belgo2',
                    column='STATUS_',
                    value='OK',
                    id=case["ID"]
                )
                db.update(
                    table='complementar_belgo2',
                    column='FINALIZADO_EM',
                    value=datetime.now(),
                    id=case["ID"]
                )
            else:
                raise Exception(f"Falha ao processar o caso de transporte {case.get('TRANSPORTE')}")
        except pe.KMMProcess as pe_error:

            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value=f'Falha no KMM. {type(pe_error).__name__}',
                id=case["ID"]
            )
            log.exception(pe_error)
        except RuntimeError as re:
            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value='Falha de lentidão KMM',
                id=case["ID"]
            )
            log.exception(re)
        except Exception as e:
            log.exception(f"Falha não mapeada. Erro {str(e)}")
            db.update(
                table='complementar_belgo2',
                column='STATUS_',
                value='Falha no KMM não mapeada',
                id=case["ID"]
            )

if __name__ == "__main__":
    logger.info("Inicio da excução Belgo worker")
    process_case()
    file_path = Path(__file__).resolve().parent / "output" / f"Retorno Belgo.xlsx"
    created = create_return_excel(file_path, 'complementar_belgo2')
    if created:
        send_email(
            os.getenv("BELGO_RECIPIENTS"),
            "Automação Belgo Finalizada",
            "Segue em anexo a planilha gerada",
            file_path
        )
    else:
        send_email(
            os.getenv("BELGO_RECIPIENTS"),
            "Automação Belgo Finalizada",
            "Não há casos"
        )
    logger.info("Fim da execução Belgo worker")