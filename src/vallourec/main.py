from kmm.services.kmm_actions import KMMActions, LoginParams
from kmm.ie_driver.ie_driver import IEDriverConfig
from models import VallourecItemProcess
from dotenv import load_dotenv
import os
load_dotenv()


class VALLOUREC:

    def __init__(self) -> None:
        self.kmm = KMMActions(service='Vallourec')

    def process(self, queue_item: VallourecItemProcess):

        self.kmm.login(
            LoginParams(
                url = os.getenv('KMM_URL'),
                username = os.getenv('KMM_VALLOUREC_USERNAME'),
                password= os.getenv('KMM_VALLOUREC_PASSWORD')
            )
        )

        contract_number = self.kmm.emitting_contract_repomfretea(
            license_plate=queue_item.license_plate,
            driver_name=queue_item.driver_name,
            nature=queue_item.nature,
            operation=queue_item.operation,
            route=queue_item.route,
            card=queue_item.card,
            sender=queue_item.sender,
            recipient=queue_item.recipient,
            liberation_user=os.getenv("VALLOUREC_LIBERATION_USER"),
            control_number=21,
            weight=queue_item.weight,
        )

        if not contract_number:
            raise Exception("Número do contrato não foi gerado")

        payment = self.kmm.payment(
            contract_number=contract_number,
            cod_pessoa_filial=os.getenv("VALLOUREC_COD_PESSOA_FILIAL")
        )

