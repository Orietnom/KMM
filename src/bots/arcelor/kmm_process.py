from src.shared.logger import logger
from src.kmm.services.kmm_actions import KMMActions, LoginParams
from src.shared.db_handler.db_handler import DB
from src.bots.arcelor.models import ArcelorItemProcess
from src.bots.arcelor.pipefy_handler import API
from dotenv import load_dotenv
import os
import src.exceptions.personalized_exceptions as pe
from pathlib import Path
BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
BOT_DIR = BASE_DIR  = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

    
def process(queue_item: ArcelorItemProcess):
    db = DB()
    log = logger.bind(service='arcelor')
    with KMMActions(service='Arcelor Freto', evidence_dir= BOT_DIR / 'output' / 'evidence') as freto_kmm:

        log.info(f"Iniciando o caso {queue_item} pela filial Fretolog")
        freto_kmm.login(
            params=LoginParams(
                url=os.getenv('KMM_URL'),
                username=os.getenv('KMM_ARCELOR_USERNAME'),
                password=os.getenv('KMM_ARCELOR_PASSWORD')
            ),
            management='freto'
        )

        freto_kmm.arcelor_load_user_profile(
            user=os.getenv('KMM_ARCELOR_USERNAME'),
            management='freto',
            center=queue_item.center
        )

        if not queue_item.complement_cte_fretolog:
            fretolog_cte_complement = freto_kmm.emitting_cte(
                cte=queue_item.cte_fretolog,
                serie=queue_item.serie_fretolog,
                cte_value=queue_item.cte_value,
                driver_name=queue_item.driver_name,
                management='freto',
                belgo=False
            )

            if not fretolog_cte_complement:
                log.error(f"Falha ao emitir o cte de complemento Fretolog para o caso {queue_item}")
                raise pe.KMMEmittingCTeError()

            log.success(f"Cte de complemento fretolog emitido com sucesso. "
                           f"Cte de complemento emitido -> {fretolog_cte_complement}")
            db.update(
                table='complementar_arcelor',
                column='CTE_FRETOLOG_COMPLEMENTAR',
                value=fretolog_cte_complement,
                id=queue_item.bd_id
            )

        else:
            fretolog_cte_complement = queue_item.complement_cte_fretolog

        if not queue_item.cte_levolog:

            if not queue_item.contract:
                API().move_card('Contrato', queue_item.card_id)
                contract_number = freto_kmm.emitting_contract_repomfreted(
                    contract_value=queue_item.contract_value,
                    complement_cte=fretolog_cte_complement,
                    serie=queue_item.serie_fretolog,
                    transport=queue_item.transport,
                    liberation_user=os.getenv("KMM_CONTRACT_LIBERATION_USER"),
                    control_number=int(os.getenv("KMM_ARCELOR_CONTROL_NUMBER"))
                )

                if not contract_number:
                    log.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                    raise pe.KMMEmittingContractError()

                log.success(f"Contrato emitido com sucesso. Contrato -> {contract_number}")
                db.update(
                    table='complementar_arcelor',
                    column='CONTRATO',
                    value=contract_number,
                    id=queue_item.bd_id
                )

            else:
                contract_number = queue_item.contract

            API().move_card('Quitação de Contrato', queue_item.card_id)
            ok = freto_kmm.payment(contract_number=contract_number)

            if not ok:
                log.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
                raise pe.KMMPaymentError()
            API().move_card('Liberar', queue_item.card_id)
            log.success(f"Sucesso ao quitar o caso {queue_item}")
            return True
        else:
            log.info("Fim da etapa Fretolog")

    with KMMActions(service='Arcelor Levo') as levo_kmm:

        log.info(f"Iniciando o caso {queue_item} pela filial Levolog")
        levo_kmm.login(
            params=LoginParams(
                url=os.getenv('KMM_URL'),
                username=os.getenv('KMM_ARCELOR_USERNAME'),
                password=os.getenv('KMM_ARCELOR_PASSWORD')
            ),
            management='levo'
        )

        levo_kmm.arcelor_load_user_profile(
            user=os.getenv('KMM_ARCELOR_USERNAME'),
            management='levo',
            center=queue_item.center
        )

        if not queue_item.complement_cte_levolog:
            API().move_card('CTe Levo', queue_item.card_id)
            levolog_cte_complement = levo_kmm.emitting_cte(
                cte=queue_item.cte_levolog,
                serie=queue_item.serie_levolog,
                cte_value=queue_item.cte_value,
                driver_name=queue_item.driver_name,
                management='levo',
                markup=0.98,
                belgo=False
            )

            if not levolog_cte_complement:
                log.error(f"Falha ao emitir o cte de complemento Levolog para o caso {queue_item}")
                raise pe.KMMEmittingCTeError()

            log.success(f"Cte de complemento fretolog emitido com sucesso. "
                           f"Cte de complemento emitido -> {levolog_cte_complement}")
            db.update(
                table='complementar_arcelor',
                column='CTE_LEVOLOG_COMPLEMENTAR',
                value=levolog_cte_complement,
                id=queue_item.bd_id
            )
        else:
            levolog_cte_complement = queue_item.complement_cte_levolog

        if not queue_item.contract:
            API().move_card('Contrato', queue_item.card_id)
            levo_contract_number = levo_kmm.emitting_contract_repomfreted(
                contract_value=queue_item.contract_value,
                complement_cte=levolog_cte_complement,
                serie=queue_item.serie_levolog,
                transport=queue_item.transport,
                liberation_user=os.getenv("KMM_ARCELOR_LIBERATION_USER"),
                control_number=int(os.getenv("KMM_ARCELOR_CONTROL_NUMBER"))
            )

            if not levo_contract_number:
                log.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                raise pe.KMMEmittingContractError()
            log.success(f"Contrato emitido com sucesso. Contrato -> {levo_contract_number}")

            db.update(
                table='complementar_arcelor',
                column='CONTRATO',
                value=levo_contract_number,
                id=queue_item.bd_id
            )
        else:
            levo_contract_number = queue_item.contract

        API().move_card('Quitação de Contrato', queue_item.card_id)
        ok = levo_kmm.payment(contract_number=levo_contract_number, management='levo')

        if not ok:
            log.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
            raise pe.KMMPaymentError()

        API().move_card('Liberar', queue_item.card_id)
        log.success(f"Sucesso ao quitar o caso {queue_item}")
        return True
