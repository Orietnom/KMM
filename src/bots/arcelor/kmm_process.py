from shared.logger import logger
from freto_kmm.services.kmm_actions import KMMActions, LoginParams
from models import ArcelorItemProcess
from dotenv import load_dotenv
import os
import exceptions.personalized_exceptions as pe
load_dotenv()

    
def process(queue_item: ArcelorItemProcess):

    with KMMActions(service='Arcelor Freto') as freto_kmm:

        logger.info(f"Iniciando o caso {queue_item} pela filial Fretolog")
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

        fretolog_cte_complement = freto_kmm.emitting_cte(
            cte=queue_item.cte_fretolog,
            serie=queue_item.serie_fretolog,
            cte_value=queue_item.cte_fretolog_value,
            management='freto',
            driver_name=queue_item.driver_name
        )

        if not fretolog_cte_complement:
            logger.error(f"Falha ao emitir o cte de complemento Fretolog para o caso {queue_item}")
            raise pe.KMMEmittingCTeError()

        logger.success(f"Cte de complemento fretolog emitido com sucesso. "
                       f"Cte de complemento emitido -> {fretolog_cte_complement}")

        if not queue_item.cte_levolog:

            contract_number = freto_kmm.emitting_contract_repomfreted(
                contract_value=queue_item.contract_value,
                complement_cte=fretolog_cte_complement,
                serie=queue_item.serie_fretolog,
                transport=queue_item.transport,
                liberation_user=os.getenv("KMM_ARCELOR_LIBERATION_USER"),
                control_number=int(os.getenv("KMM_ARCELOR_CONTROL_NUMBER"))
            )

            if not contract_number:
                logger.error(f"Falha ao emitir o contrato para o caso {queue_item}")
                raise pe.KMMEmittingContractError()
            logger.success(f"Contrato emitido com sucesso. Contrato -> {contract_number}")

            ok = freto_kmm.payment(
                contract_number=contract_number,
                cod_pessoa_filial=os.getenv("KMM_ARCELOR_COD_PESSOA_FILIAL")
            )

            if not ok:
                logger.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
                raise pe.KMMPaymentError()
            logger.success(f"Sucesso ao quitar o caso {queue_item}")
            return True
        else:
            logger.info("Fim da etapa Fretolog")

    with KMMActions(service='Arcelor Levo') as levo_kmm:

        logger.info(f"Iniciando o caso {queue_item} pela filial Levolog")
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

        levolog_cte_complement = levo_kmm.emitting_cte(
            cte=queue_item.cte_levolog,
            serie=queue_item.serie_levolog,
            cte_value=queue_item.cte_value_levolog,
            management='levo',
            driver_name=queue_item.driver_name
        )

        if not levolog_cte_complement:
            logger.error(f"Falha ao emitir o cte de complemento Levolog para o caso {queue_item}")
            raise pe.KMMEmittingCTeError()

        logger.success(f"Cte de complemento fretolog emitido com sucesso. "
                       f"Cte de complemento emitido -> {levolog_cte_complement}")

        levo_contract_number = levo_kmm.emitting_contract_repomfreted(
            contract_value=queue_item.contract_value,
            complement_cte=levolog_cte_complement,
            serie=queue_item.serie_levolog,
            transport=queue_item.transport,
            liberation_user=os.getenv("KMM_ARCELOR_LIBERATION_USER"),
            control_number=int(os.getenv("KMM_ARCELOR_CONTROL_NUMBER"))
        )

        if not levo_contract_number:
            logger.error(f"Falha ao emitir o contrato para o caso {queue_item}")
            raise pe.KMMEmittingContractError()
        logger.success(f"Contrato emitido com sucesso. Contrato -> {levo_contract_number}")

        ok = freto_kmm.payment(
            contract_number=levo_contract_number,
            cod_pessoa_filial=os.getenv("KMM_ARCELOR_COD_PESSOA_FILIAL")
        )

        if not ok:
            logger.error(f"Falha ao realizar a quitação do contrato para o caso {queue_item}")
            raise pe.KMMPaymentError()

        logger.success(f"Sucesso ao quitar o caso {queue_item}")
        return True
