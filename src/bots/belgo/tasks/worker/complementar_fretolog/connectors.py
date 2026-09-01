import os

from ergon.connector import ConnectorConfig
from ergon.connector.ergon_platform import (
    ErgonPlatformClient,
    ErgonPlatformConnector,
    ErgonPlatformConsumerConfig,
)

from src.bots.belgo.tasks.publisher.connectors import PROCESSABLE_PHASE_ID, WORKFLOW_ID


def build_worker_connector_config() -> ConnectorConfig:
    missing = [
        name
        for name in ("ERGON_CLIENT_ID", "ERGON_CLIENT_SECRET")
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(
            f"Credenciais obrigatórias ausentes para o worker BELGO: {', '.join(missing)}"
        )

    client = ErgonPlatformClient(
        client_id=os.environ["ERGON_CLIENT_ID"],
        client_secret=os.environ["ERGON_CLIENT_SECRET"],
        base_url=os.getenv("ERGON_BASE_URL", "https://platform.ergondata.ai"),
        company_id=os.getenv("ERGON_COMPANY_ID") or None,
        timeout=float(os.getenv("ERGON_PLATFORM_TIMEOUT", "30")),
        max_retries=int(os.getenv("ERGON_PLATFORM_MAX_RETRIES", "2")),
    )
    consumer_config = ErgonPlatformConsumerConfig(
        workflow_id=WORKFLOW_ID,
        phase_id=PROCESSABLE_PHASE_ID,
        batch_size=int(os.getenv("TASK_POLICY_BELGO_FRETOLOG_BATCH_SIZE", "10")),
        unassigned=True,
    )
    return ConnectorConfig(
        connector=ErgonPlatformConnector,
        kwargs={
            "client": client,
            "consumer_config": consumer_config,
        },
    )
