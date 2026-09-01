from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class ClaimState(str, Enum):
    CLAIMED = "claimed"
    PENDING = "pending"
    CREATED = "created"
    MANUAL_RECONCILIATION = "manual_reconciliation"


@dataclass(frozen=True)
class ClaimOutcome:
    key: str
    incident_id: str
    route: str
    state: ClaimState
    platform_item_id: str | None = None
    detail: str | None = None


def idempotency_key(incident_id: str) -> str:
    return f"belgo:{incident_id.strip()}"


class BelgoIdempotencyLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_env(cls) -> BelgoIdempotencyLedger:
        return cls(os.getenv("BELGO_IDEMPOTENCY_DB", "artifacts/belgo/idempotency.sqlite3"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS belgo_card_claims (
                    idempotency_key TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL UNIQUE,
                    route TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('pending', 'created', 'manual_reconciliation')
                    ),
                    platform_item_id TEXT,
                    detail TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _outcome(row: sqlite3.Row, claimed: bool = False) -> ClaimOutcome:
        return ClaimOutcome(
            key=row["idempotency_key"],
            incident_id=row["incident_id"],
            route=row["route"],
            state=ClaimState.CLAIMED if claimed else ClaimState(row["state"]),
            platform_item_id=row["platform_item_id"],
            detail=row["detail"],
        )

    def claim(self, incident_id: str, route: str) -> ClaimOutcome:
        key = idempotency_key(incident_id)
        now = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM belgo_card_claims WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._outcome(existing)
            connection.execute(
                """
                INSERT INTO belgo_card_claims (
                    idempotency_key, incident_id, route, state, platform_item_id,
                    detail, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', NULL, ?, ?, ?)
                """,
                (
                    key,
                    incident_id,
                    route,
                    "Reservado antes da criação do card.",
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM belgo_card_claims WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            connection.commit()
            assert row is not None
            return self._outcome(row, claimed=True)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_created(self, incident_id: str, platform_item_id: str) -> ClaimOutcome:
        if not platform_item_id.strip():
            raise ValueError("platform_item_id não pode ser vazio")
        return self._update(
            incident_id,
            ClaimState.CREATED,
            platform_item_id=platform_item_id.strip(),
            detail="A Platform retornou um ID estável para o card.",
        )

    def mark_manual_reconciliation(self, incident_id: str, detail: str) -> ClaimOutcome:
        return self._update(
            incident_id,
            ClaimState.MANUAL_RECONCILIATION,
            platform_item_id=None,
            detail=detail,
        )

    def mark_route(self, incident_id: str, route: str) -> ClaimOutcome:
        key = idempotency_key(incident_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE belgo_card_claims
                SET route = ?, detail = ?, updated_at = ?
                WHERE idempotency_key = ? AND state = 'created'
                """,
                (
                    route,
                    f"Card atualizado para a rota {route}.",
                    datetime.now(timezone.utc).isoformat(),
                    key,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Claim BELGO criado não encontrado: {key}")
            row = connection.execute(
                "SELECT * FROM belgo_card_claims WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            connection.commit()
            assert row is not None
            return self._outcome(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _update(
        self,
        incident_id: str,
        state: ClaimState,
        *,
        platform_item_id: str | None,
        detail: str,
    ) -> ClaimOutcome:
        key = idempotency_key(incident_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE belgo_card_claims
                SET state = ?, platform_item_id = ?, detail = ?, updated_at = ?
                WHERE idempotency_key = ?
                """,
                (
                    state.value,
                    platform_item_id,
                    detail,
                    datetime.now(timezone.utc).isoformat(),
                    key,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Claim BELGO desconhecido: {key}")
            row = connection.execute(
                "SELECT * FROM belgo_card_claims WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            connection.commit()
            assert row is not None
            return self._outcome(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release_definitive_failure(self, incident_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM belgo_card_claims WHERE idempotency_key = ? AND state = 'pending'",
                (idempotency_key(incident_id),),
            )

    def created_incident_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT incident_id
                FROM belgo_card_claims
                WHERE state IN ('created', 'manual_reconciliation')
                """
            ).fetchall()
        return {str(row["incident_id"]) for row in rows}

    def inspect(self, incident_id: str) -> ClaimOutcome | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM belgo_card_claims WHERE idempotency_key = ?",
                (idempotency_key(incident_id),),
            ).fetchone()
        return self._outcome(row) if row is not None else None
