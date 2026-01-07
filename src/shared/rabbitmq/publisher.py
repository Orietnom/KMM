import json
from typing import Any

import pandas as pd
import pika
from shared.logger import logger
import os
from dotenv import load_dotenv
load_dotenv()

def rabbit_mq_publisher(
        data: Any,
        queue_name: str
):
    if isinstance(data, pd.DataFrame):
        logger.info("Estrutura de dados => Dataframe")
    elif isinstance(data, list) and all(isinstance(item, dict) for item in data):
        logger.info("Estrutura de dados => lista de dicionarios")
    else:
        logger.warning(
            "Lista de dados enviada com estrutura diferente de list[dict] ou DataFrame"
        )
        raise TypeError("Dados devem ser pandas.Dataframe ou uma lista de dicionarios List[Dict]")


    try:
        params = pika.URLParameters(os.getenv("RABBIT_URL"))
        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        channel.queue_declare(queue=queue_name, durable=True)
        channel.confirm_delivery()
        if isinstance(data, pd.DataFrame):
            for i, row in data.iterrows():
                payload = row.to_dict()
                payload["_row_number"] = str(i)

                channel.basic_publish(
                    exchange="",
                    routing_key=queue_name,
                    body=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type="application/json"
                    ),
                )
        else:
            for item in data:
                channel.basic_publish(
                    exchange="",
                    routing_key=queue_name,
                    body=json.dumps(item, ensure_ascii=False).encode("utf-8"),
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type="application/json"
                    ),
                )
    finally:
        connection.close()
