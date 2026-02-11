from sqlalchemy import column

from src.kmm.services.kmm_actions import KMMActions, LoginParams
from src.bots.jmendes.models import JMNItemProcess
from dotenv import load_dotenv
from src.shared.db_handler.db_handler import DB
import os
import src.exceptions.personalized_exceptions as pe
from pathlib import Path
BASE_DIR  = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(BASE_DIR / ".env")

def process(queue_item: JMNItemProcess):
    db = DB()
    with KMMActions(service='JMendes') as kmm:
        kmm.login(
            LoginParams(
                url = os.getenv('KMM_URL'),
                username = os.getenv('KMM_JMN_USERNAME'),
                password= os.getenv('KMM_JMN_PASSWORD')
            ),
            management=queue_item.management
        )

        if not queue_item.contract:
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
                contract_value=queue_item.contract_value,
            )
            if not contract_number:
                raise Exception("Número do contrato não foi gerado")
            db.update(
                table='complementar_jmendes',
                column='CONTRATO',
                value=contract_number,
                id=queue_item.bd_id
            )

        else:
            contract_number = queue_item.contract

        payment = kmm.payment(contract_number=contract_number, management=queue_item.management)
        if not payment:
            raise pe.KMMPaymentError()

        return True
