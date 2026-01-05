import pandas as pd
from dotenv import load_dotenv
from shared import sharepoint
from shared.logger import logger
from rabbitmq import publisher
import os

load_dotenv()

def run():
    try:
        download_dir = f"{os.getcwd()}/excel_files"
        ok = sharepoint.get_items(
            url=os.getenv("JMN_SHAREPOINT_URL"),
            download_dir= download_dir,
            file_name=os.getenv("JMN_EXCEL_FILE_NAME")
        )

        if ok:
            full_file_path = os.path.join(download_dir, os.getenv("JMN_EXCEL_FILE_NAME"))
            df = pd.read_excel(full_file_path)
            publisher.rabbit_mq_publisher(
                data=df,
                queue_name="jmendes"
            )
    except Exception as e:
        logger.exception(f"Falha ao obter os casos: Erro {str(e)}")
