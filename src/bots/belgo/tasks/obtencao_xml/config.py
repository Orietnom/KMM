import os

from ergon import task

from src.bots.belgo.tasks import constants, settings
from src.bots.belgo.tasks.obtencao_xml.connectors import build_connector_config
from src.bots.belgo.tasks.obtencao_xml.task import TaskBelgoXMLDownload

CONCURRENCY_POLICY = task.policies.ConcurrencyPolicy(
    value=os.getenv("TASK_POLICY_BELGO_XML_CONCURRENCY", "1")
)
if CONCURRENCY_POLICY.value != 1:
    raise ValueError("O worker BELGO XML exige concorrência 1 por usar uma sessão KMM")

WORKER_POLICY = task.policies.ConsumerPolicy(
    name="worker",
    loop=task.policies.ConsumerLoopPolicy(
        concurrency=CONCURRENCY_POLICY,
        limit=os.getenv("TASK_POLICY_BELGO_XML_LIMIT") or None,
        streaming=False,
    ),
    fetch=task.policies.FetchPolicy(
        connector_name="sql",
        retry=constants.default_retry_policy(),
        batch=task.policies.BatchPolicy(
            size=os.getenv("TASK_POLICY_BELGO_XML_BATCH_SIZE", "10")
        ),
    ),
    transaction_runtime=task.policies.TransactionRuntimePolicy(
        timeout=os.getenv("TASK_POLICY_BELGO_XML_TIMEOUT", "1800")
    ),
    process=task.policies.ProcessPolicy(
        retry=task.policies.RetryPolicy(max_attempts=1)
    ),
    success=task.policies.SuccessPolicy(retry=constants.default_retry_policy()),
    exception=task.policies.ExceptionPolicy(retry=constants.default_retry_policy()),
)

TASK_BELGO_XML_DOWNLOAD = task.TaskConfig(
    name="belgo-worker-obtencao-xml",
    task=TaskBelgoXMLDownload,
    connectors={"sql": build_connector_config()},
    services={"platform_state": settings.BELGO_PLATFORM_STATE_SERVICE},
    policies=[WORKER_POLICY],
    logging=settings.LOGGING,
    tracing=settings.TRACING,
)

task.manager.register(TASK_BELGO_XML_DOWNLOAD)


def run() -> None:
    task.manager.run("belgo-worker-obtencao-xml", debug=True, worker_id=0)


if __name__ == "__main__":
    run()
