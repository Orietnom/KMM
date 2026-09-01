from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ergon.connector import Transaction
from ergon.task.mixins.consumer import ConsumerTask

from src.bots.belgo.tasks.publisher.connectors import PROCESSABLE_PHASE_ID, WORKFLOW_ID
from src.bots.belgo.tasks.worker.complementar_fretolog.schemas import (
    REQUIRED_CARD_FIELDS,
    RESULT_CARD_FIELDS,
    FretologComplementInput,
    FretologComplementResult,
)
from src.kmm.services.kmm_actions import CTeEmissionResult, KMMActions, LoginParams

logger = logging.getLogger(__name__)

FRETOLOG_COMPLEMENT_PHASE_ID = "24399475-131c-4d02-9222-33f57b73c6ef"
BASE_DIR = Path(__file__).resolve().parents[6]


class TaskBelgoFretologComplement(ConsumerTask):
    kmm_factory = KMMActions

    @staticmethod
    def _field_identifiers(fields: Any) -> set[str]:
        identifiers: set[str] = set()
        for field in fields or []:
            if isinstance(field, dict):
                for key in ("id", "name"):
                    if field.get(key):
                        identifiers.add(str(field[key]))
                continue
            for key in ("id", "name"):
                value = getattr(field, key, None)
                if value:
                    identifiers.add(str(value))
        return identifiers

    def _validate_platform_fields(self) -> None:
        if os.getenv("BELGO_VALIDATE_PLATFORM_FIELDS", "true").lower() != "true":
            return
        for phase_id, expected in (
            (PROCESSABLE_PHASE_ID, REQUIRED_CARD_FIELDS),
            (
                FRETOLOG_COMPLEMENT_PHASE_ID,
                REQUIRED_CARD_FIELDS | RESULT_CARD_FIELDS,
            ),
        ):
            fields = self.platform_connector.list_phase_fields(
                phase_id,
                workflow_id=WORKFLOW_ID,
            )
            missing = expected - self._field_identifiers(fields)
            if missing:
                raise RuntimeError(
                    f"Campos BELGO ausentes na fase {phase_id}: {', '.join(sorted(missing))}"
                )

    def _route_to_stage(self, card_id: str) -> None:
        self.platform_connector.client.workflows.items.route(
            card_id,
            to_phase_id=FRETOLOG_COMPLEMENT_PHASE_ID,
        )

    def _update_card(self, card_id: str, result: FretologComplementResult) -> None:
        self.platform_connector.client.workflows.items.update(
            card_id,
            field_values={
                "Valor Complementar Fretolog": result.net_value,
                "N CT-e Complementar Fretolog": result.cte_number,
            },
        )

    def _emit(self, item: FretologComplementInput) -> FretologComplementResult:
        username = os.environ["KMM_BELGO_USERNAME"]
        with self.kmm_factory(
            service="Belgo Freto",
            evidence_dir=BASE_DIR / "output" / "evidence",
        ) as freto_kmm:
            logger.info(
                "Iniciando incidente %s pela filial Fretolog (%s)",
                item.incident_id,
                item.center,
            )
            freto_kmm.login(
                params=LoginParams(
                    url=os.environ["KMM_URL"],
                    username=username,
                    password=os.environ["KMM_BELGO_PASSWORD"],
                ),
                management="freto",
            )
            freto_kmm.belgo_load_user_profile(
                user=username,
                management="freto",
                lotation=item.freto_lot,
            )
            emitted = freto_kmm.emitting_cte(
                cte=item.freto_cte,
                serie=item.freto_serie,
                cte_value=item.cte_value,
                management="freto",
                incident_number=item.number_of_incidents,
                taxes=True,
                belgo=True,
                return_details=True,
            )
        if not isinstance(emitted, CTeEmissionResult) or not emitted.number:
            raise RuntimeError(
                f"KMM não retornou um CT-e complementar estável para {item.incident_id}"
            )
        return FretologComplementResult(
            cte_number=emitted.number,
            net_value=emitted.net_value,
        )

    def process_transaction(self, transaction: Transaction) -> FretologComplementResult:
        item = FretologComplementInput.from_platform_payload(transaction.payload)
        self._route_to_stage(transaction.id)

        sql_record = self.db_service.get_belgo_incident(item.incident_id)
        if sql_record is None:
            raise RuntimeError(
                f"Incidente {item.incident_id} não encontrado em complementar_belgo2"
            )

        existing_cte = sql_record.get("CTE_FRETOLOG_COMPLEMENTAR")
        if existing_cte:
            if item.complement_value is None:
                raise RuntimeError(
                    "CT-e Fretolog já existe no SQL, mas o valor líquido não está no card; "
                    "reconciliação manual necessária"
                )
            result = FretologComplementResult(
                cte_number=str(existing_cte),
                net_value=item.complement_value,
                resumed_from_sql=True,
            )
            self._update_card(transaction.id, result)
            return result

        result = self._emit(item)
        self.db_service.save_belgo_fretolog_complement(
            row_id=int(sql_record["ID"]),
            cte_number=result.cte_number,
            emitted_at=datetime.now(),
        )
        self._update_card(transaction.id, result)
        return result

    def handle_process_success(
        self,
        transaction: Transaction,
        result: FretologComplementResult,
    ) -> None:
        self.platform_connector.release_item(transaction.id)
        logger.info(
            "CT-e complementar Fretolog concluído para card %s: %s",
            transaction.id,
            result.cte_number,
        )

    def handle_process_exception(self, transaction: Transaction, exc: Exception) -> None:
        logger.error(
            "Falha no CT-e complementar Fretolog do card %s: %s",
            transaction.id,
            exc,
        )
        self.platform_connector.release_item(transaction.id)

    def execute(self) -> int:
        self._validate_platform_fields()
        return self.consume_transactions(self.worker_policy)
