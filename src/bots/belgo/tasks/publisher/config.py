import os

from ergon import task

from src.bots.belgo.tasks import constants, settings
from src.bots.belgo.tasks.publisher.connectors import (
    PENDING_PHASE_ID,
    PROCESSABLE_PHASE_ID,
    build_connector_config,
)
from src.bots.belgo.tasks.publisher.task import TaskBelgoPublisher

CONCURRENCY_POLICY = task.policies.ConcurrencyPolicy(
    value=os.getenv("TASK_POLICY_BELGO_PUBLISHER_CONCURRENCY", "1")
)
if CONCURRENCY_POLICY.value != 1:
    raise ValueError("O publisher BELGO exige concorrência 1 por compartilhar a sessão do portal")

BATCH_POLICY = task.policies.BatchPolicy(
    size=os.getenv("TASK_POLICY_BELGO_PUBLISHER_BATCH_SIZE", "100")
)
PRODUCER_LOOP_POLICY = task.policies.ProducerLoopPolicy(
    concurrency=CONCURRENCY_POLICY,
    batch=BATCH_POLICY,
    limit=os.getenv("TASK_POLICY_BELGO_PUBLISHER_LIMIT") or None,
)
BELGO_PUBLISHER_POLICY = task.policies.ProducerPolicy(
    name="producer",
    loop=PRODUCER_LOOP_POLICY,
    prepare=task.policies.PreparePolicy(retry=constants.default_retry_policy()),
    success=task.policies.SuccessPolicy(retry=constants.default_retry_policy()),
    exception=task.policies.ExceptionPolicy(retry=constants.default_retry_policy()),
)

TASK_BELGO_PUBLISHER = task.TaskConfig(
    name="belgo-publisher",
    task=TaskBelgoPublisher,
    connectors={
        "processable": build_connector_config(PROCESSABLE_PHASE_ID),
        "pending": build_connector_config(PENDING_PHASE_ID),
    },
    services={
        "db": settings.BELGO_DB_SERVICE,
        "portal": settings.BELGO_PORTAL_SERVICE,
    },
    policies=[BELGO_PUBLISHER_POLICY],
    logging=settings.LOGGING,
    tracing=settings.TRACING,
)

task.manager.register(TASK_BELGO_PUBLISHER)


def run() -> None:
    task.manager.run("belgo-publisher", debug=True, worker_id=0)


if __name__ == "__main__":
    run()
