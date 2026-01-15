import pandas as pd
from dotenv import load_dotenv
from shared import sharepoint
from shared.logger import logger

from shared.db_handler.db_handler import DB
import os

load_dotenv()

def run():
    try:
        download_dir = os.path.join(os.getcwd(),"excel_files")
        ok = sharepoint.get_items(
            url=os.getenv("JMN_SHAREPOINT_URL"),
            download_dir= download_dir,
            file_name=os.getenv("JMN_EXCEL_FILE_NAME")
        )

        if ok:
            full_file_path = os.path.join(download_dir, os.getenv("JMN_EXCEL_FILE_NAME"))
            df = pd.read_excel(full_file_path, sheet_name=os.getenv("JMN_EXCEL_SHEET_NAME"), dtype="string")
            df = df.drop(columns=["Data"], errors="ignore")
            df_renamed = df.rename(columns={
                "TB-e": "TBE",
                "Cartão": "CARTAO",
                "Placa": "PLACA",
                "Motorista": "NOME_MOTORISTA",
                "Gestão": "GESTAO",
                "Valor": "VALOR_CONTRATO",
                "Natureza": "NATUREZA",
                "Operação": "OPERACAO",
                "Rota": "ROTA",
                "Destinatario": "DESTINATARIO",
                "Status Linha": "STATUS_LINHA",
                "Número contrato": "CONTRATO",
                "Situação Final": "STATUS_"
            })
            df_renamed = df_renamed.dropna(subset=["TBE"])
            df_renamed['STATUS_'] = "Pendente"
            if not df_renamed.empty:
                db = DB()
                db.insert_ignore_df(
                    table="complementar_jmendes",
                    df=df_renamed,
                    unique_keys=["TBE"]
                )
            else:
                logger.warning("Planilha não contém dados")
        else:
            logger.error("Falha ao realizar o download da planilha")

    except Exception as e:
        logger.exception(f"Falha ao obter os casos: Erro {str(e)}")

run()