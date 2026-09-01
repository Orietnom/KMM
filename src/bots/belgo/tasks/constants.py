import os

from ergon.task.policies import RetryPolicy


def default_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        max_attempts=os.getenv("TASK_POLICY_DEFAULT_RETRY_MAX_ATTEMPTS", "3"),
        backoff=os.getenv("TASK_POLICY_DEFAULT_RETRY_BACKOFF", "3"),
        backoff_multiplier=os.getenv("TASK_POLICY_DEFAULT_RETRY_BACKOFF_MULTIPLIER", "2"),
        backoff_cap=os.getenv("TASK_POLICY_DEFAULT_RETRY_BACKOFF_CAP", "20"),
    )
