from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from ergon.connector import ConnectorConfig, Transaction
from ergon.connector.connector import Connector
from ergon.connector.ergon_platform import (
    ErgonPlatformClient,
    ErgonPlatformConnector,
    ErgonPlatformProducerConfig,
)
from ergon.connector.ergon_platform.utils import normalize_create_payload

logger = logging.getLogger(__name__)

WORKFLOW_ID = "267af949-e7dc-41d1-ac13-8cc531cf3745"
PROCESSABLE_PHASE_ID = "fa0472b7-80c4-47cc-81b0-bd5da388acf1"
PENDING_PHASE_ID = "2a183aaf-eb37-43e7-a454-e77d7d1a171e"

PRE_ACCEPTANCE_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 409, 413, 415, 422})


class DryRunErgonPlatformConnector(Connector):
    def __init__(self, producer_config: ErgonPlatformProducerConfig) -> None:
        self._producer_config = producer_config
        self.created_cards: list[dict[str, Any]] = []

    def fetch_transactions(self, *args: Any, **kwargs: Any) -> list[Transaction]:
        raise NotImplementedError("Conector BELGO dry-run é apenas de saída")

    def dispatch_transactions(
        self,
        transactions: list[Transaction],
        *args: Any,
        **kwargs: Any,
    ) -> list[str]:
        created_ids = []
        for transaction in transactions:
            card = normalize_create_payload(transaction.payload)
            card.setdefault("workflow_id", self._producer_config.workflow_id)
            card.setdefault("phase_id", self._producer_config.phase_id)
            self.created_cards.append(card)
            created_id = f"dry-run-{transaction.id}"
            created_ids.append(created_id)
            logger.info("[DRY-RUN] Card BELGO: %s", card)
        return created_ids

    def close(self) -> None:
        return


def has_platform_credentials() -> bool:
    return bool(os.getenv("ERGON_CLIENT_ID") and os.getenv("ERGON_CLIENT_SECRET"))


def build_connector_config(phase_id: str) -> ConnectorConfig:
    producer_config = ErgonPlatformProducerConfig(
        workflow_id=WORKFLOW_ID,
        phase_id=phase_id,
    )
    if not has_platform_credentials():
        logger.warning("Credenciais ERGON ausentes; producer BELGO operará em dry-run")
        return ConnectorConfig(
            connector=DryRunErgonPlatformConnector,
            kwargs={"producer_config": producer_config},
        )
    client = ErgonPlatformClient(
        client_id=os.environ["ERGON_CLIENT_ID"],
        client_secret=os.environ["ERGON_CLIENT_SECRET"],
        base_url=os.getenv("ERGON_BASE_URL", "https://platform.ergondata.ai"),
        company_id=os.getenv("ERGON_COMPANY_ID") or None,
        timeout=float(os.getenv("ERGON_PLATFORM_TIMEOUT", "30")),
        max_retries=int(os.getenv("ERGON_PLATFORM_MAX_RETRIES", "2")),
    )
    return ConnectorConfig(
        connector=ErgonPlatformConnector,
        kwargs={"client": client, "producer_config": producer_config},
    )


def is_definitive_pre_acceptance_failure(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in PRE_ACCEPTANCE_STATUS_CODES
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code in PRE_ACCEPTANCE_STATUS_CODES
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    return isinstance(status_code, int) and status_code in PRE_ACCEPTANCE_STATUS_CODES
