import json
import pika
import os
from dotenv import load_dotenv
from jmendes.kmm_process import process
from jmendes.models import JMNItemProcess
from shared.logger import logger
import exceptions.personalized_exceptions as pe
load_dotenv()

RABBITMQ_URL = os.getenv("RABBIT_URL")
QUEUE_NAME = "jmendes"


def process_case(case: dict) -> None:

    try:
        process(
            JMNItemProcess(
                license_plate=case.get('license_plate'),
                driver_name=case.get('driver_name'),
                tbe=case.get('tbe'),
                nature=case.get('nature'),
                operation=case.get('operation'),
                route=case.get('route'),
                card=case.get('card'),
                sender=case.get('sender'),
                recipient=case.get('recipient'),
                weight=case.get('weight')
            )
        )
    except pe.KMMProcess as pe_error:
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
    main()
