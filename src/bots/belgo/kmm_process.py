from shared.logger import logger
from kmm.services.kmm_actions import KMMActions, LoginParams
from shared.db_handler.db_handler import DB
from models import BelgoItemProcess
from dotenv import load_dotenv
import os
import exceptions.personalized_exceptions as pe
load_dotenv()

    
def process(queue_item: BelgoItemProcess):
    db = DB()
    with KMMActions(service='Belgo Freto') as freto_kmm:

        logger.info(f"Iniciando o caso {queue_item} pela filial Fretolog")
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
            lotation=queue_item.center
        )

        file_path = freto_kmm.get_xml('337521')

        if not queue_item.complement_cte_fretolog:
            fretolog_cte_complement = freto_kmm.emitting_cte(
                cte=queue_item.freto_cte,
                serie=queue_item.freto_serie,
                cte_value=queue_item.cte_value,
                management='freto',
                incident_number=queue_item.n_incidents,
                taxes=True
            )

            if not fretolog_cte_complement:
                logger.error(f"Falha ao emitir o cte de complemento Fretolog para o caso {queue_item}")
                raise pe.KMMEmittingCTeError()

            logger.success(f"Cte de complemento fretolog emitido com sucesso. "
                           f"Cte de complemento emitido -> {fretolog_cte_complement}")
            db.update(
                table='complementar_belgo2',
                column='CTE_FRETOLOG_COMPLEMENTAR',
                value=fretolog_cte_complement,
                id=queue_item.bd_id
            )
        else:
            fretolog_cte_complement = queue_item.complement_cte_fretolog

        if not queue_item.cte_levolog:

            if not queue_item.contract:
                contract_number = freto_kmm.emitting_contract_repomfreted(
                    contract_value=queue_item.contract_value,
                    complement_cte=fretolog_cte_complement,
                    serie=queue_item.serie_fretolog,
                    transport=queue_item.transport,
                    liberation_user=os.getenv("KMM_CONTRACT_LIBERATION_USER"),
                    control_number=int(os.getenv("KMM_BELGO_CONTROL_NUMBER"))
                )

                if not contract_number:
                    logger.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                    raise pe.KMMEmittingContractError()

                logger.success(f"Contrato emitido com sucesso. Contrato -> {contract_number}")
                db.update(
                    table='complementar_belgo2',
                    column='CONTRATO',
                    value=contract_number,
                    id=queue_item.bd_id
                )
            else:
                contract_number = queue_item.contract

            ok = freto_kmm.payment(
                contract_number=contract_number,
                cod_pessoa_filial=os.getenv("KMM_BELGO_COD_PESSOA_FILIAL")
            )

            if not ok:
                logger.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
                raise pe.KMMPaymentError()
            logger.success(f"Sucesso ao quitar o caso {queue_item}")
            return True
        else:
            logger.info("Fim da etapa Fretolog")

    with KMMActions(service='Belgo Levo') as levo_kmm:

        logger.info(f"Iniciando o caso {queue_item} pela filial Levolog")
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
            center=queue_item.center
        )

        if not queue_item.complement_cte_levolog:
            levolog_cte_complement = levo_kmm.emitting_cte(
                cte=queue_item.cte_levolog,
                serie=queue_item.serie_levolog,
                cte_value=queue_item.cte_value_levolog,
                management='levo',
                driver_name=queue_item.driver_name,
                incident_number=queue_item.n_incidents,
                markup=0.98
            )

            if not levolog_cte_complement:
                logger.error(f"Falha ao emitir o cte de complemento Levolog para o caso {queue_item}")
                raise pe.KMMEmittingCTeError()

            logger.success(f"Cte de complemento fretolog emitido com sucesso. "
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
                serie=queue_item.serie_levolog,
                transport=queue_item.transport,
                liberation_user=os.getenv("KMM_BELGO_LIBERATION_USER"),
                control_number=int(os.getenv("KMM_BELGO_CONTROL_NUMBER"))
            )

            if not levo_contract_number:
                logger.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                raise pe.KMMEmittingContractError()
            logger.success(f"Contrato emitido com sucesso. Contrato -> {levo_contract_number}")

            db.update(
                table='complementar_belgo2',
                column='CONTRATO',
                value=levo_contract_number,
                id=queue_item.bd_id
            )
        else:
            levolog_contract_number = queue_item.contract

        ok = freto_kmm.payment(
            contract_number=levo_contract_number,
            cod_pessoa_filial=os.getenv("KMM_BELGO_COD_PESSOA_FILIAL")
        )

        if not ok:
            logger.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
            raise pe.KMMPaymentError()

        logger.success(f"Sucesso ao quitar o caso {queue_item}")
        return True
