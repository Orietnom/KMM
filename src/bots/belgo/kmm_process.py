from src.shared.logger import logger
from src.kmm.services.kmm_actions import KMMActions, LoginParams
from src.shared.db_handler.db_handler import DB
from src.bots.belgo.models import BelgoItemProcess
from src.bots.belgo.bba_portal import BelgoXML
from dotenv import load_dotenv
from datetime import datetime
import os
import src.exceptions.personalized_exceptions as pe
from pathlib import Path
BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(BASE_DIR / ".env")


    
def process(queue_item: BelgoItemProcess):
    db = DB()
    log = logger.bind(service='belgo')

    with KMMActions(service='Belgo Freto') as freto_kmm:

        log.info(f"Iniciando o caso {queue_item} pela filial Fretolog")
        log.info(f"url = {os.getenv('KMM_URL')} -- username = {os.getenv('KMM_BELGO_USERNAME')} -- pass = {os.getenv('KMM_BELGO_PASSWORD')}")
        freto_kmm.login(
            params=LoginParams(
                url=os.getenv('KMM_URL'),
                username=os.getenv('KMM_BELGO_USERNAME'),
                password=os.getenv('KMM_BELGO_PASSWORD')
            ),
            management='freto'
        )

        freto_kmm.belgo_load_user_profile(
            user=os.getenv('KMM_BELGO_USERNAME'),
            management='freto',
            lotation=queue_item.freto_lot
        )

        if not queue_item.complement_cte_fretolog:
            fretolog_cte_complement = freto_kmm.emitting_cte(
                cte=queue_item.freto_cte,
                serie=queue_item.freto_serie,
                cte_value=queue_item.cte_value,
                management='freto',
                incident_number=queue_item.n_incidents,
                taxes=True,
                belgo=True
            )

            if not fretolog_cte_complement:
                log.error(f"Falha ao emitir o cte de complemento Fretolog para o caso {queue_item}")
                raise pe.KMMEmittingCTeError()

            log.success(f"Cte de complemento fretolog emitido com sucesso. "
                           f"Cte de complemento emitido -> {fretolog_cte_complement}")
            db.update(
                table='complementar_belgo2',
                column='CTE_FRETOLOG_COMPLEMENTAR',
                value=fretolog_cte_complement,
                id=queue_item.bd_id
            )
            db.update(
                table='complementar_belgo2',
                column='DATA_EMISSAO_CTE_FRETO',
                value=datetime.now(),
                id=queue_item.bd_id
            )

        else:
            fretolog_cte_complement = queue_item.complement_cte_fretolog

        file_path = freto_kmm.get_xml(fretolog_cte_complement, queue_item.complement_cte_fretolog_date)
        if not file_path:
            raise pe.KMMGetXML()

        if not queue_item.levo_cte:

            if not queue_item.contract:
                contract_number = freto_kmm.emitting_contract_repomfreted(
                    contract_value=queue_item.contract_value,
                    complement_cte=fretolog_cte_complement,
                    serie=queue_item.freto_serie,
                    transport=queue_item.transport,
                    liberation_user=os.getenv("KMM_CONTRACT_LIBERATION_USER"),
                    control_number=int(os.getenv("KMM_BELGO_CONTROL_NUMBER"))
                )

                if not contract_number:
                    log.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                    raise pe.KMMEmittingContractError()

                log.success(f"Contrato emitido com sucesso. Contrato -> {contract_number}")
                db.update(
                    table='complementar_belgo2',
                    column='CONTRATO',
                    value=contract_number,
                    id=queue_item.bd_id
                )
            else:
                contract_number = queue_item.contract

            ok = freto_kmm.payment(contract_number=contract_number)

            if not ok:
                log.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
                raise pe.KMMPaymentError()
            log.success(f"Sucesso ao quitar o caso {queue_item}")

            if not queue_item.edicao_caso:
                BelgoXML().insert_xml(queue_item.incident_id, fretolog_cte_complement, file_path)
            return True
        else:
            log.info("Fim da etapa Fretolog")

    with KMMActions(service='Belgo Levo') as levo_kmm:

        log.info(f"Iniciando o caso {queue_item} pela filial Levolog")
        levo_kmm.login(
            params=LoginParams(
                url=os.getenv('KMM_URL'),
                username=os.getenv('KMM_BELGO_USERNAME'),
                password=os.getenv('KMM_BELGO_PASSWORD')
            ),
            management='levo'
        )

        levo_kmm.arcelor_load_user_profile(
            user=os.getenv('KMM_BELGO_USERNAME'),
            management='levo',
            center=queue_item.levo_cte
        )

        if not queue_item.complement_cte_levolog:
            levolog_cte_complement = levo_kmm.emitting_cte(
                cte=queue_item.levo_cte,
                serie=queue_item.levo_serie,
                cte_value=queue_item.cte_value,
                management='levo',
                incident_number=queue_item.n_incidents,
                markup=0.98,
                belgo=True
            )

            if not levolog_cte_complement:
                log.error(f"Falha ao emitir o cte de complemento Levolog para o caso {queue_item}")
                raise pe.KMMEmittingCTeError()

            log.success(f"Cte de complemento fretolog emitido com sucesso. "
                           f"Cte de complemento emitido -> {levolog_cte_complement}")
            db.update(
                table='complementar_belgo2',
                column='CTE_LEVOLOG_COMPLEMENTAR',
                value=levolog_cte_complement,
                id=queue_item.bd_id
            )
        else:
            levolog_cte_complement = queue_item.complement_cte_levolog

        if not queue_item.contract:
            levo_contract_number = levo_kmm.emitting_contract_repomfreted(
                contract_value=queue_item.contract_value,
                complement_cte=levolog_cte_complement,
                serie=queue_item.levo_serie,
                transport=queue_item.transport,
                liberation_user=os.getenv("KMM_BELGO_LIBERATION_USER"),
                control_number=int(os.getenv("KMM_BELGO_CONTROL_NUMBER")),
                submotive=queue_item.submotive
            )

            if not levo_contract_number:
                log.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                raise pe.KMMEmittingContractError()
            log.success(f"Contrato emitido com sucesso. Contrato -> {levo_contract_number}")

            db.update(
                table='complementar_belgo2',
                column='CONTRATO',
                value=levo_contract_number,
                id=queue_item.bd_id
            )
        else:
            levo_contract_number = queue_item.contract

        ok = levo_kmm.payment(contract_number=levo_contract_number, management='levolog')

        if not ok:
            log.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
            raise pe.KMMPaymentError()

        if not queue_item.edicao_caso:
            BelgoXML().insert_xml(queue_item.incident_id, fretolog_cte_complement, file_path)
        log.success(f"Caso editado com sucesso -> {fretolog_cte_complement}")
        db.update(
            table='complementar_belgo2',
            column='EDICAO_CASO',
            value=True,
            id=queue_item.bd_id
        )
        log.success(f"Sucesso ao quitar o caso {queue_item}")
        return True
