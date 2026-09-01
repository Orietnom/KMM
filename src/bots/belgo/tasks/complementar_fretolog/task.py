from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from ergon.connector import Transaction
from ergon.task.mixins.consumer import ConsumerTask

from src.bots.belgo.tasks.complementar_fretolog.schemas import (
    REQUIRED_PLATFORM_FIELDS,
    FretologComplementInput,
    FretologComplementResult,
)
from src.kmm.services.kmm_actions import CTeEmissionResult, KMMActions, LoginParams

logger = logging.getLogger(__name__)

FRETOLOG_COMPLEMENT_PHASE_ID = "24399475-131c-4d02-9222-33f57b73c6ef"
BASE_DIR = Path(__file__).resolve().parents[5]


class TaskBelgoFretologComplement(ConsumerTask):
    kmm_factory = KMMActions

    def _validate_platform_fields(self) -> None:
        if os.getenv("BELGO_VALIDATE_PLATFORM_FIELDS", "true").lower() != "true":
            return
        self.platform_state_service.validate_phase_fields(
            FRETOLOG_COMPLEMENT_PHASE_ID,
            REQUIRED_PLATFORM_FIELDS,
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
        item = FretologComplementInput.from_sql_payload(transaction.payload)
        card_id = self.platform_state_service.find_card_id(item.incident_id)
        self.platform_state_service.route_to(
            card_id,
            FRETOLOG_COMPLEMENT_PHASE_ID,
        )

        if item.complement_cte:
            result = FretologComplementResult(
                cte_number=item.complement_cte,
                resumed_from_sql=True,
            )
            self.platform_state_service.update_cte_number(
                card_id,
                item.complement_cte,
            )
            return result

        result = self._emit(item)
        self.sql_connector.db.save_belgo_fretolog_complement(
            row_id=item.row_id,
            cte_number=result.cte_number,
            emitted_at=datetime.now(),
        )
        assert result.net_value is not None
        self.platform_state_service.update_results(
            card_id,
            cte_number=result.cte_number,
            net_value=result.net_value,
        )
        return result

    def handle_process_success(
        self,
        transaction: Transaction,
        result: FretologComplementResult,
    ) -> None:
        logger.info(
            "CT-e complementar Fretolog concluído para linha SQL %s: %s",
            transaction.id,
            result.cte_number,
        )

    def handle_process_exception(self, transaction: Transaction, exc: Exception) -> None:
        logger.error(
            "Falha no CT-e complementar Fretolog da linha SQL %s: %s",
            transaction.id,
            exc,
        )
        self.sql_connector.mark_failed(
            transaction,
            f"Falha no KMM. {type(exc).__name__}",
        )

    def execute(self) -> int:
        self._validate_platform_fields()
        return self.consume_transactions(self.worker_policy)
