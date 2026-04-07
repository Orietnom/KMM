import os
import pandas as pd
import numpy as np
from typing import Any
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from urllib.parse import quote_plus
from dotenv import load_dotenv
from src.shared.logger import logger
load_dotenv()

class DB:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DB, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if not self.__initialized:
            self.engine = self.connect()
            self.__initialized = True

    @staticmethod
    def connect() -> Engine:
        uid = quote_plus(os.getenv("DB_UID"))
        pwd = quote_plus(os.getenv("DB_PASSWORD"))
        conn_str = (
            f"mssql+pyodbc://{uid}:{pwd}@{os.getenv('DB_SERVER')}/{os.getenv('DATABASE')}"
            "?driver=ODBC+Driver+17+for+SQL+Server"
        )

        return create_engine(conn_str, future=True, pool_pre_ping=True)

    def get_data(self, table: str, date_range: bool = False) -> list[dict]:
        if date_range:
            dt_min = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - relativedelta(days=15)
        else:
            dt_min = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        query = text(f"""
            SELECT *
            FROM Ergondata_Robo.dbo.{table}
            WHERE CRIADO_EM >= :dt_min
              AND RETENTATIVA < 3
              AND STATUS_ <> 'OK'
        """)

        df = pd.read_sql(query, self.engine, params={"dt_min": dt_min})
        return df.to_dict(orient="records")

    def get_data_to_excel(self, table: str) -> list[dict]:
        dt_min = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        dt_max = dt_min + relativedelta(days=1)

        query = text(f"""
            SELECT *
            FROM Ergondata_Robo.dbo.{table}
            WHERE ATUALIZADO_EM >= :dt_min and ATUALIZADO_EM < :dt_max
        """)

        df = pd.read_sql(query, self.engine, params={"dt_min": dt_min, "dt_max": dt_max})
        return df

    def insert_ignore_df(
            self,
            table: str,
            df: pd.DataFrame,
            unique_keys: list[str],  # ex: ["PLACA"] ou ["PLACA","TBE"]
            schema: str = "dbo",
    ):
        """
        Insere linhas do DataFrame e ignora as que já existem (baseado em unique_keys).
        Requer que df contenha todas as colunas a inserir.
        """

        allowed_tables = [
            "complementar_jmendes",
            "complementar_arcelor",
            "complementar_belgo2"
        ]
        if table not in allowed_tables:
            raise ValueError("Tabela não permitida")

        if df.empty:
            return False

        cols = [str(c) for c in df.columns]
        if not cols:
            raise ValueError("DataFrame sem colunas.")

        col_list = ", ".join(cols)
        params_list = ", ".join([f":{c}" for c in cols])

        where_unique = " AND ".join([f"T.{k} = :{k}" for k in unique_keys])

        stmt = text(f"""
            INSERT INTO Ergondata_Robo.dbo.{table} ({col_list})
            SELECT {params_list}
            WHERE NOT EXISTS (
                SELECT 1
                FROM Ergondata_Robo.{schema}.{table} T
                WHERE {where_unique}
            );
        """)

        rows = df.where(pd.notna(df), None).to_dict(orient="records")  # NaN -> NULL
        logger.info(f"Inserindo {len(rows)} linhas no banco de dados")
        with self.engine.begin() as conn:
            result = conn.execute(stmt, rows)

        if result.rowcount:
            logger.success(f"Foram inseridas {len(rows)} linhas")
        return result.rowcount

    def update(self, value: Any, column: str, table: str, id: int):
        now = datetime.now()
        stmt = text(f"""
            UPDATE Ergondata_Robo.dbo.{table}
            SET {column} = :value, ATUALIZADO_EM = :date
            WHERE ID = :id
        """)

        with self.engine.begin() as conn:
            conn.execute(stmt, {"value": value, "date": now, "id": id})

    def close(self):
        self.engine.dispose()

def create_return_excel(file_path, table):
    try:
        db = DB()
        data = db.get_data_to_excel(table=table)
        if data.empty:
            return False
        data['CRIADO_EM'] = data['CRIADO_EM'].dt.strftime('%d/%m/%Y %H:%M:%S')
        data['ATUALIZADO_EM'] = data['ATUALIZADO_EM'].dt.strftime('%d/%m/%Y %H:%M:%S')
        data.to_excel(file_path, index=False)
        return True
    except Exception:
        logger.exception("Falha ao obter dados para gerar excel")
        return False