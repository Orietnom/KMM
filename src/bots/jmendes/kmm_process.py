from sqlalchemy import column

from kmm.services.kmm_actions import KMMActions, LoginParams
from models import JMNItemProcess
from dotenv import load_dotenv
from shared.db_handler.db_handler import DB
import os
import exceptions.personalized_exceptions as pe
load_dotenv()

def process(queue_item: JMNItemProcess):
    db = DB()
    with KMMActions(service='JMendes') as kmm:
        kmm.login(
            LoginParams(
                url = os.getenv('KMM_URL'),
                username = os.getenv('KMM_JMN_USERNAME'),
                password= os.getenv('KMM_JMN_PASSWORD')
            )
        )
    
        contract_number = kmm.emitting_contract_repomfretea(
            license_plate=queue_item.license_plate,
            driver_name=queue_item.driver_name,
            nature=queue_item.nature,
            operation=queue_item.operation,
            route=queue_item.route,
            card=queue_item.card,
            sender=queue_item.sender,
            recipient=queue_item.recipient,
            liberation_user=os.getenv("JMN_LIBERATION_USER"),
            control_number=21,
            weight=queue_item.weight,
        )
    
        if not contract_number:
            raise Exception("Número do contrato não foi gerado")
    
        payment = kmm.payment(contract_number=contract_number, cod_pessoa_filial=os.getenv("JMN_COD_PESSOA_FILIAL"))
        if not payment:
            raise pe.KMMPaymentError()
