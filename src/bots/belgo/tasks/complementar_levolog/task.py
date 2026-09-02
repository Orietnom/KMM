from __future__ import annotations

import logging
import os
from pathlib import Path

from ergon.connector import Transaction
from ergon.task.mixins.consumer import ConsumerTask

from src.bots.belgo.tasks.complementar_levolog.schemas import (
    REQUIRED_PLATFORM_FIELDS,
    LevologComplementInput,
    LevologComplementResult,
)
from src.kmm.services.kmm_actions import CTeEmissionResult, KMMActions, LoginParams

logger = logging.getLogger(__name__)

LEVOLOG_COMPLEMENT_PHASE_ID = "559aaa39-eb12-485d-80d4-214826e1261a"
BASE_DIR = Path(__file__).resolve().parents[5]


class TaskBelgoLevologComplement(ConsumerTask):
    kmm_factory = KMMActions

    def _validate_platform_fields(self) -> None:
        if os.getenv("BELGO_VALIDATE_PLATFORM_FIELDS", "true").lower() != "true":
            return
        self.platform_state_service.validate_phase_fields(
            LEVOLOG_COMPLEMENT_PHASE_ID,
            REQUIRED_PLATFORM_FIELDS,
        )

    def _emit(self, item: LevologComplementInput) -> LevologComplementResult:
        username = os.environ["KMM_BELGO_USERNAME"]
        with self.kmm_factory(
            service="Belgo Levo",
            evidence_dir=BASE_DIR / "output" / "evidence",
        ) as levo_kmm:
            logger.info(
                "Iniciando incidente %s pela filial Levolog (%s)",
                item.incident_id,
                item.center,
            )
            levo_kmm.login(
                params=LoginParams(
                    url=os.environ["KMM_URL"],
                    username=username,
                    password=os.environ["KMM_BELGO_PASSWORD"],
                ),
                management="levo",
            )
            levo_kmm.arcelor_load_user_profile(
                user=username,
                management="levo",
                center=item.levo_lot,
            )
            emitted = levo_kmm.emitting_cte(
                cte=item.levo_cte,
                serie=item.levo_serie,
                cte_value=item.cte_value,
                management="levo",
                incident_number=item.number_of_incidents,
                markup=0.98,
                belgo=True,
                return_details=True,
            )
        if not isinstance(emitted, CTeEmissionResult) or not emitted.number:
            raise RuntimeError(
                f"KMM não retornou um CT-e complementar estável para {item.incident_id}"
            )
        return LevologComplementResult(
            cte_number=emitted.number,
            net_value=emitted.net_value,
        )

    def process_transaction(self, transaction: Transaction) -> LevologComplementResult:
        item = LevologComplementInput.from_sql_payload(transaction.payload)
        card_id = self.platform_state_service.find_card_id(item.incident_id)
        self.platform_state_service.route_to(
            card_id,
            LEVOLOG_COMPLEMENT_PHASE_ID,
        )

        if item.complement_cte:
            result = LevologComplementResult(
                cte_number=item.complement_cte,
                resumed_from_sql=True,
            )
            self.platform_state_service.update_levolog_cte_number(
                card_id,
                item.complement_cte,
            )
            return result

        result = self._emit(item)
        self.sql_connector.db.save_belgo_levolog_complement(
            row_id=item.row_id,
            cte_number=result.cte_number,
        )
        assert result.net_value is not None
        self.platform_state_service.update_levolog_results(
            card_id,
            cte_number=result.cte_number,
            net_value=result.net_value,
        )
        return result

    def handle_process_success(
        self,
        transaction: Transaction,
        result: LevologComplementResult,
    ) -> None:
        logger.info(
            "CT-e complementar Levolog concluído para linha SQL %s: %s",
            transaction.id,
            result.cte_number,
        )

    def handle_process_exception(self, transaction: Transaction, exc: Exception) -> None:
        logger.error(
            "Falha no CT-e complementar Levolog da linha SQL %s: %s",
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
