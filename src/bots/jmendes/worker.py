import json
import pika
import os
from dotenv import load_dotenv
from src.bots.jmendes.kmm_process import process
from src.bots.jmendes.models import JMNItemProcess
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
            table="complementar_jmendes"
        )
    except Exception as e:
        logger.exception("Falha não mapeada")
        return False

    for case in cases:
        try:
            db.update(
                table='complementar_jmendes',
                column='STATUS_',
                value='Processando',
                id=case["ID"]
            )
            process(
                JMNItemProcess(
                    license_plate=case.get('PLACA'),
                    driver_name=case.get('NOME_MOTORISTA'),
                    tbe=case.get('TBE'),
                    nature=case.get('NATUREZA'),
                    operation=case.get('OPERACAO'),
                    route=case.get('ROTA'),
                    card=case.get('CARTAO'),
                    sender=case.get('REMETENTE'),
                    recipient=case.get('DESTINATARIO'),
                    weight=case.get('PESO'),
                    bd_id=case.get("ID")
                )
            )
        except pe.KMMProcess as pe_error:
            retry = case['RETENTATIVA'] + 1
            db.update(
                table='complementar_jmendes',
                column='STATUS_',
                value='Falha no KMM',
                id=case["ID"]
            )
            db.update(
                table='complementar_jmendes',
                column='RETENTATIVA',
                value=retry,
                id=case["ID"]
            )
            logger.exception(pe_error)
        except Exception as e:
            logger.exception(f"Falha não mapeada. Erro {str(e)}")

def main() -> None:
    params = pika.URLParameters(RABBITMQ_URL)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    channel.basic_qos(prefetch_count=1)

    def on_message(ch, method, properties, body: bytes):
        try:
            case = json.loads(body.decode("utf-8"))
            process_case(case)

            # ACK só depois de processar (garante “at least once”)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            print("Erro processando mensagem:", e)

            # Opção 1 (mais segura): requeue=True tenta de novo (cuidado com loop infinito)
            # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            # Opção 2: descarta (requeue=False)
            # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    print("Aguardando mensagens... Ctrl+C pra sair")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("Parando...")
    finally:
        connection.close()


if __name__ == "__main__":
    process_case()
