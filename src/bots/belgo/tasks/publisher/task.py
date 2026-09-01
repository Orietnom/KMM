from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd
from ergon.connector import Connector, Transaction
from ergon.connector.ergon_platform import CreateItemInput
from ergon.task import policies
from ergon.task.mixins import ProducerTask

from src.bots.belgo.tasks.publisher.connectors import (
    PENDING_PHASE_ID,
    PROCESSABLE_PHASE_ID,
    WORKFLOW_ID,
    DryRunErgonPlatformConnector,
    is_definitive_pre_acceptance_failure,
)
from src.bots.belgo.tasks.publisher.idempotency import (
    BelgoIdempotencyLedger,
    ClaimState,
)
from src.bots.belgo.tasks.publisher.schemas import (
    BelgoIncident,
    CaptureRoute,
    platform_field_map,
)
from src.bots.belgo.tasks.publisher.services import BelgoPortalService
from src.shared.db_handler.db_handler import DB

logger = logging.getLogger(__name__)


class TaskBelgoPublisher(ProducerTask):
    producer_policy: policies.ProducerPolicy
    processable_connector: Connector
    pending_connector: Connector
    db_service: DB
    portal_service: BelgoPortalService
    _ledger: BelgoIdempotencyLedger | None = None
    _failures: list[str]

    def _connector_for(self, incident: BelgoIncident) -> Connector:
        if incident.route is CaptureRoute.PROCESSABLE:
            return self.processable_connector
        return self.pending_connector

    def _is_dry_run(self) -> bool:
        return isinstance(self.processable_connector, DryRunErgonPlatformConnector)

    def prepare_transaction(self, transaction: Transaction) -> CreateItemInput:
        incident = BelgoIncident.model_validate(transaction.payload)
        description = ""
        if incident.error_reasons:
            description = "Motivo da pendência:\n" + "\n".join(
                f"- {reason}" for reason in incident.error_reasons
            )
        return CreateItemInput(
            title=incident.card_title(),
            field_values=incident.to_card_fields(),
            extra_fields={"description": description},
        )

    def _insert_processable_sql(self, incident: BelgoIncident) -> None:
        record = incident.to_sql_record()
        self.db_service.insert_ignore_df(
            table="complementar_belgo2",
            df=pd.DataFrame([record]),
            unique_keys=["ID_INCIDENTE"],
        )

    @staticmethod
    def _platform_items(connector: Connector) -> Any:
        client = getattr(connector, "client", None)
        items = getattr(getattr(client, "workflows", None), "items", None)
        if items is None:
            raise RuntimeError("Conector Ergon Platform sem API de itens")
        return items

    @staticmethod
    def _as_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        dump = getattr(value, "model_dump", None)
        if callable(dump):
            payload = dump()
            return payload if isinstance(payload, dict) else {}
        return {}

    @classmethod
    def _current_phase_id(cls, items: Any, item_id: str) -> str | None:
        payload = cls._as_mapping(items.get(item_id))
        for container in (payload, cls._as_mapping(payload.get("data"))):
            for key in ("current_phase_id", "phase_id"):
                value = container.get(key)
                if value:
                    return str(value)
            phase = cls._as_mapping(container.get("phase"))
            if phase.get("id"):
                return str(phase["id"])
        return None

    def _update_created_card(
        self,
        connector: Connector,
        incident: BelgoIncident,
        result: CreateItemInput,
        platform_item_id: str,
        previous_route: str,
    ) -> None:
        items = self._platform_items(connector)
        items.update(
            platform_item_id,
            title=result.title,
            field_values=dict(result.field_values or {}),
            **result.extra_fields,
        )
        if incident.route is not CaptureRoute.PROCESSABLE or previous_route == CaptureRoute.PROCESSABLE.value:
            return

        current_phase_id = self._current_phase_id(items, platform_item_id)
        if current_phase_id != PROCESSABLE_PHASE_ID:
            items.route(platform_item_id, to_phase_id=PROCESSABLE_PHASE_ID)
        assert self._ledger is not None
        self._ledger.mark_route(incident.id, CaptureRoute.PROCESSABLE.value)

    def handle_prepare_success(
        self,
        transaction: Transaction,
        result: CreateItemInput,
    ) -> Any:
        incident = BelgoIncident.model_validate(transaction.payload)
        connector = self._connector_for(incident)
        outbound = Transaction(
            id=transaction.id,
            payload=result,
            metadata=transaction.metadata,
        )

        # Dry-run não pode alimentar a fila SQL, pois o worker seria liberado sem
        # que o card correspondente existisse na Platform.
        if self._is_dry_run():
            return connector.dispatch_transactions([outbound])

        assert self._ledger is not None
        claim = self._ledger.claim(incident.id, incident.route.value)
        if claim.state is ClaimState.CREATED:
            if not claim.platform_item_id:
                raise RuntimeError(f"Claim criado sem platform_item_id para o incidente {incident.id}")
            self._update_created_card(
                connector,
                incident,
                result,
                claim.platform_item_id,
                claim.route,
            )
            if incident.route is CaptureRoute.PROCESSABLE:
                self._insert_processable_sql(incident)
            logger.info("Card BELGO atualizado para incidente %s", incident.id)
            return claim
        if claim.state is not ClaimState.CLAIMED:
            detail = (
                f"Claim {claim.state.value} encontrado para o incidente {incident.id}; "
                "reconciliação manual é necessária antes de nova tentativa."
            )
            if claim.state is ClaimState.PENDING:
                self._ledger.mark_manual_reconciliation(incident.id, detail)
            raise RuntimeError(detail)

        try:
            created = connector.dispatch_transactions([outbound])
        except Exception as error:
            if is_definitive_pre_acceptance_failure(error):
                self._ledger.release_definitive_failure(incident.id)
            else:
                self._ledger.mark_manual_reconciliation(
                    incident.id,
                    f"Resultado ambíguo ao criar card: {type(error).__name__}: {error}",
                )
            raise

        if not isinstance(created, list) or len(created) != 1 or not str(created[0]).strip():
            detail = "A criação do card não retornou um ID estável; reconciliar manualmente."
            self._ledger.mark_manual_reconciliation(incident.id, detail)
            raise RuntimeError(detail)

        outcome = self._ledger.mark_created(incident.id, str(created[0]))
        logger.info(
            "Card BELGO criado para incidente %s na fase %s: %s",
            incident.id,
            transaction.metadata["phase_id"],
            outcome.platform_item_id,
        )
        if incident.route is CaptureRoute.PROCESSABLE:
            self._insert_processable_sql(incident)
        return outcome

    def handle_prepare_exception(self, transaction: Transaction, error: Exception) -> None:
        message = f"Incidente {transaction.id}: {error}"
        self._failures.append(message)
        logger.error("Falha no producer BELGO: %s", message)

    @staticmethod
    def _field_identifiers(payload: Any) -> set[str]:
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        if isinstance(payload, list):
            result: set[str] = set()
            for item in payload:
                result.update(TaskBelgoPublisher._field_identifiers(item))
            return result
        if not isinstance(payload, dict):
            return set()
        result = {
            str(payload[key])
            for key in ("id", "name", "slug", "label")
            if payload.get(key)
        }
        for key in ("data", "items", "results", "fields"):
            if key in payload:
                result.update(TaskBelgoPublisher._field_identifiers(payload[key]))
        return result

    def _validate_platform_fields(self) -> None:
        if self._is_dry_run() or os.getenv("BELGO_VALIDATE_PLATFORM_FIELDS", "true").lower() != "true":
            return
        expected = set(platform_field_map().values())
        for connector, phase_id in (
            (self.processable_connector, PROCESSABLE_PHASE_ID),
            (self.pending_connector, PENDING_PHASE_ID),
        ):
            fields = connector.list_phase_fields(phase_id, workflow_id=WORKFLOW_ID)
            available = self._field_identifiers(fields)
            missing = expected - available
            if missing:
                raise RuntimeError(
                    f"Campos BELGO ausentes na fase {phase_id}: {', '.join(sorted(missing))}"
                )

    def execute(self, *args: Any, **kwargs: Any) -> int:
        self._failures = []
        self._validate_platform_fields()
        self._ledger = None if self._is_dry_run() else BelgoIdempotencyLedger.from_env()
        skip_ids = self.db_service.get_existing_belgo_incident_ids()
        result = self.portal_service.capture(skip_ids)
        transactions = [
            Transaction(
                id=incident.id,
                payload=incident,
                metadata={
                    "task": self.name,
                    "route": incident.route.value,
                    "workflow_id": WORKFLOW_ID,
                    "phase_id": (
                        PROCESSABLE_PHASE_ID
                        if incident.route is CaptureRoute.PROCESSABLE
                        else PENDING_PHASE_ID
                    ),
                },
            )
            for incident in result.all
        ]
        if not transactions:
            logger.info("Nenhum incidente BELGO novo para publicar")
            return 0
        processed = self.produce_transactions(transactions, self.producer_policy)
        if self._failures:
            raise RuntimeError("; ".join(self._failures))
        return processed
