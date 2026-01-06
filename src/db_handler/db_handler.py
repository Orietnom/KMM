# import os
# from datetime import datetime
#
# import pandas as pd
# import pyodbc
# from dateutil.relativedelta import relativedelta
# from sqlalchemy import create_engine, text, event
# from sqlalchemy.engine import Engine
# from dotenv import load_dotenv
# load_dotenv()
#
#
# class DB:
#     _instance = None
#
#     def __new__(cls, *args, **kwargs):
#         if not cls._instance:
#             cls._instance = super(DB, cls).__new__(cls)
#             cls._instance.__initialized = False
#         return cls._instance
#
#     def __init__(self):
#
#         if not self.__initialized:
#             self.cursor, self.conn = self.connect()
#             self.__initialized = True
#
#     # @staticmethod
#     # def connect():
#     #     bd_secrets = Vault().get_secret('DB_BELGO_PRD')
#     #     conn = pyodbc.connect(
#     #         'DRIVER=ODBC Driver 17 for SQL Server;'
#     #         f'SERVER={os.getenv("DB_SERVER")};'
#     #         f'DATABASE={os.getenv("DATABASE")};'
#     #         f'UID={os.getenv("DB_UID")};'
#     #         f'PWD={os.getenv("DB_PASSWORD")}'
#     #     )
#     #
#     #     cursor = conn.cursor()
#     #     return cursor, conn
#     @staticmethod
#     def connect() -> Engine:
#
#         server = os.getenv("DB_SERVER")
#         database = os.getenv("DATABASE")
#         uid = os.getenv("DB_UID")
#         pwd = os.getenv("DB_PASSWORD")
#         driver = "ODBC Driver 17 for SQL Server"
#
#         # Observação: usar URL com driver e credenciais
#         conn_str = (
#             f"mssql+pyodbc://{uid}:{pwd}@{server}/{database}"
#             f"?driver={driver.replace(' ', '+')}"
#         )
#
#         engine = create_engine(conn_str, future=True)
#
#         # Habilita fast_executemany (grande ganho no insert em massa)
#         @event.listens_for(engine, "before_cursor_execute")
#         def _enable_fast_executemany(conn, cursor, statement, parameters, context, executemany):
#             if executemany:
#                 cursor.fast_executemany = True
#
#         return engine
#
#     def get_data(self, table) -> list:
#
#         range = datetime.now() - relativedelta(days=7)
#         query = f"""
#                 SELECT *
#                 FROM Ergondata_Robo.dbo.{table}
#                 WHERE CTE_FRETOLOG_COMPLEMENTAR IS NULL \
#                   AND CRIADO_EM >= ? AND RETENTATIVA < 3\
#                 """
#
#         self.cursor.execute(query, range)
#         bd_response = self.cursor.fetchall()
#
#         columns = [column[0] for column in self.cursor.description]
#
#         result = [dict(zip(columns, row)) for row in bd_response]
#
#         return result
#
#     def update(self, queue_item: dict, collumn: str, table):
#         query = f"""
#             UPDATE Ergondata_Robo.dbo.{table}
#             SET {collumn} = ?
#             WHERE ID = ?
#             """
#         values = (queue_item[collumn], queue_item['ID'])
#
#         self.cursor.execute(query, values)
#         self.conn.commit()
#
#     def insert_df(self, df: pd.DataFrame, table: str, schema: str = "dbo", chunksize: int = 5000):
#         """
#         Envia o DataFrame para uma tabela.
#         - if_exists="append" é o padrão mais comum (não apaga tabela).
#         """
#         df.to_sql(
#             name=table,
#             con=self.engine,
#             schema=schema,
#             if_exists="append",
#             index=False,
#             chunksize=chunksize,
#             method="multi",  # melhora performance em muitos cenários
#         )
#
#     def close(self):
#         # Fechar a conexão
#         self.cursor.close()
#         self.conn.close()

import os
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


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
        server = os.getenv("DB_SERVER")
        database = os.getenv("DATABASE")
        uid = os.getenv("DB_UID")
        pwd = os.getenv("DB_PASSWORD")
        driver = "ODBC Driver 17 for SQL Server"

        conn_str = (
            f"mssql+pyodbc://{uid}:{pwd}@{server}/{database}"
            f"?driver={driver.replace(' ', '+')}"
        )

        return create_engine(conn_str, future=True, pool_pre_ping=True)

    def get_data(self, table: str) -> list[dict]:
        dt_min = datetime.now() - relativedelta(days=7)

        query = text(f"""
            SELECT *
            FROM Ergondata_Robo.dbo.{table}
            WHERE CRIADO_EM >= :dt_min
              AND RETENTATIVA < 3
              AND STATUS_ <> "OK"
        """)

        df = pd.read_sql(query, self.engine, params={"dt_min": dt_min})
        return df.to_dict(orient="records")

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
        ]
        if table not in allowed_tables:
            raise ValueError("Tabela não permitida")

        if df.empty:
            return False

        table = _validate_identifier(table)
        schema = _validate_identifier(schema)

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

        with self.engine.begin() as conn:
            result = conn.execute(stmt, rows)

        return result.rowcount

    def update(self, queue_item: dict, column: str, table: str):
        stmt = text(f"""
            UPDATE Ergondata_Robo.dbo.{table}
            SET {column} = :value
            WHERE ID = :id
        """)

        with self.engine.begin() as conn:
            conn.execute(stmt, {"value": queue_item[column], "id": queue_item["ID"]})

    def close(self):
        self.engine.dispose()
