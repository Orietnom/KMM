from typing import Any

from ergon.connector import Connector, ConnectorConfig, Transaction

from src.shared.db_handler.db_handler import DB


class BelgoFretologSQLConnector(Connector):
    def __init__(self, db: DB | None = None) -> None:
        self.db = db or DB()

    def fetch_transactions(
        self,
        batch_size: int | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> list[Transaction]:
        rows = self.db.claim_belgo_fretolog_cases(batch_size or 10)
        return [
            Transaction(
                id=str(row["ID"]),
                payload=row,
                metadata={"incident_id": str(row["ID_INCIDENTE"])},
            )
            for row in rows
        ]

    def fetch_transaction_by_id(
        self,
        transaction_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Transaction:
        row = self.db.get_belgo_case_by_row_id(int(transaction_id))
        if row is None:
            raise LookupError(f"Linha BELGO {transaction_id} não encontrada")
        return Transaction(
            id=str(row["ID"]),
            payload=row,
            metadata={"incident_id": str(row["ID_INCIDENTE"])},
        )

    def dispatch_transactions(
        self,
        transactions: list[Transaction],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        raise NotImplementedError("O conector SQL BELGO é somente de consumo")

    def mark_failed(self, transaction: Transaction, message: str) -> None:
        self.db.update(
            table="complementar_belgo2",
            column="STATUS_",
            value=message,
            id=int(transaction.id),
        )

    def close(self) -> None:
        self.db.close()


def build_worker_connector_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector=BelgoFretologSQLConnector,
        kwargs={},
    )
