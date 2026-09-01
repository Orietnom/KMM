import os

from ergon import task

from src.bots.belgo.tasks import constants, settings
from src.bots.belgo.tasks.complementar_fretolog.connectors import (
    build_worker_connector_config,
)
from src.bots.belgo.tasks.complementar_fretolog.task import (
    TaskBelgoFretologComplement,
)

CONCURRENCY_POLICY = task.policies.ConcurrencyPolicy(
    value=os.getenv("TASK_POLICY_BELGO_FRETOLOG_CONCURRENCY", "1")
)
if CONCURRENCY_POLICY.value != 1:
    raise ValueError("O worker BELGO Fretolog exige concorrência 1 por usar uma sessão KMM")

WORKER_POLICY = task.policies.ConsumerPolicy(
    name="worker",
    loop=task.policies.ConsumerLoopPolicy(
        concurrency=CONCURRENCY_POLICY,
        limit=os.getenv("TASK_POLICY_BELGO_FRETOLOG_LIMIT") or None,
        streaming=False,
    ),
    fetch=task.policies.FetchPolicy(
        connector_name="sql",
        retry=constants.default_retry_policy(),
        batch=task.policies.BatchPolicy(
            size=os.getenv("TASK_POLICY_BELGO_FRETOLOG_BATCH_SIZE", "10")
        ),
    ),
    transaction_runtime=task.policies.TransactionRuntimePolicy(
        timeout=os.getenv("TASK_POLICY_BELGO_FRETOLOG_TIMEOUT", "1800")
    ),
    process=task.policies.ProcessPolicy(
        retry=task.policies.RetryPolicy(max_attempts=1)
    ),
    success=task.policies.SuccessPolicy(retry=constants.default_retry_policy()),
    exception=task.policies.ExceptionPolicy(retry=constants.default_retry_policy()),
)

TASK_BELGO_FRETOLOG_COMPLEMENT = task.TaskConfig(
    name="belgo-worker-complementar-fretolog",
    task=TaskBelgoFretologComplement,
    connectors={"sql": build_worker_connector_config()},
    services={"platform_state": settings.BELGO_PLATFORM_STATE_SERVICE},
    policies=[WORKER_POLICY],
    logging=settings.LOGGING,
    tracing=settings.TRACING,
)

task.manager.register(TASK_BELGO_FRETOLOG_COMPLEMENT)


def run() -> None:
    task.manager.run("belgo-worker-complementar-fretolog", debug=True, worker_id=0)


if __name__ == "__main__":
    run()
