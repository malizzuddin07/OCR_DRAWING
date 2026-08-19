import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from config import (
    ROBOFLOW_API_KEY,
    ROBOFLOW_API_URL,
    ROBOFLOW_MAX_RETRIES,
    ROBOFLOW_EXPECTED_MODEL_ID,
    ROBOFLOW_TIMEOUT_SECONDS,
    ROBOFLOW_WORKFLOW_ID,
    ROBOFLOW_WORKSPACE,
)
from model_registry import active_model_deployment, load_registry


ROBOFLOW_WORKFLOW_OUTPUT_KEYS =("model_output",)
ROBOFLOW_WORKFLOW_PARAMETERS: dict[str, Any] = {}


class RoboflowWorkflowError(RuntimeError):
    """Raised when the configured Roboflow workflow cannot be run safely."""


def get_active_roboflow_deployment():
    try:
        return active_model_deployment(
            load_registry(),
            configured_model_id=ROBOFLOW_EXPECTED_MODEL_ID,
            default_workspace=ROBOFLOW_WORKSPACE,
            default_workflow_id=ROBOFLOW_WORKFLOW_ID,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RoboflowWorkflowError(f"Invalid active model deployment: {exc}") from exc


def _run_workflow_once(
    image: Any,
    *,
    parameters: dict[str, Any],
    excluded_fields: list[str] | None,
    use_cache: bool,
    workspace: str,
    workflow_id: str,
) -> list[dict[str, Any]]:
    from inference_sdk import InferenceHTTPClient

    client = InferenceHTTPClient(
        api_url=ROBOFLOW_API_URL.rstrip("/"),
        api_key=ROBOFLOW_API_KEY,
    )
    return client.run_workflow(
        workspace_name=workspace,
        workflow_id=workflow_id,
        images={"image": image},
        parameters=parameters,
        excluded_fields=excluded_fields,
        use_cache=use_cache,
    )


def run_engineering_symbol_workflow(
    image: Any,
    *,
    parameters: dict[str, Any] | None = None,
    excluded_fields: list[str] | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    if not ROBOFLOW_API_KEY:
        raise RoboflowWorkflowError("ROBOFLOW_API_KEY is not set.")

    runtime_parameters = ROBOFLOW_WORKFLOW_PARAMETERS.copy()
    if parameters:
        unknown = sorted(set(parameters) - set(ROBOFLOW_WORKFLOW_PARAMETERS))
        if unknown:
            raise RoboflowWorkflowError(
                "Unsupported Roboflow workflow parameter(s): " + ", ".join(unknown)
            )
        runtime_parameters.update(parameters)

    attempts = (ROBOFLOW_MAX_RETRIES if max_retries is None else max_retries) + 1
    timeout = ROBOFLOW_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    last_error: Exception | None = None
    deployment = get_active_roboflow_deployment()

    for attempt in range(1, attempts + 1):
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                _run_workflow_once,
                image,
                parameters=runtime_parameters,
                excluded_fields=excluded_fields,
                use_cache=use_cache,
                workspace=deployment["workspace"],
                workflow_id=deployment["workflow_id"],
            )
            try:
                result = future.result(timeout=timeout)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except FutureTimeoutError as exc:
            last_error = exc
            logging.warning("Roboflow workflow timed out after %.1f seconds.", timeout)
        except Exception as exc:
            last_error = exc
            logging.warning("Roboflow workflow attempt %s/%s failed: %s", attempt, attempts, exc)
        else:
            if not isinstance(result, list):
                raise RoboflowWorkflowError(
                    f"Roboflow workflow returned {type(result).__name__}; expected list."
                )
            return result

        if attempt < attempts:
            time.sleep(min(2 ** (attempt - 1), 8))

    raise RoboflowWorkflowError(f"Roboflow workflow failed after {attempts} attempt(s): {last_error}")


def assert_engineering_symbol_output_shape(result: list[dict[str, Any]]) -> None:
    if not result:
        raise RoboflowWorkflowError("Roboflow workflow returned an empty result list.")

    first_result = result[0]
    if not isinstance(first_result, dict):
        raise RoboflowWorkflowError(
            f"Roboflow workflow result item is {type(first_result).__name__}; expected dict."
        )

    model_output = first_result.get("model_output")
    if not isinstance(model_output, dict):
        raise RoboflowWorkflowError("Roboflow workflow response is missing model_output.")

    predictions = model_output.get("predictions")
    if not isinstance(predictions, list):
        raise RoboflowWorkflowError(
            "Roboflow workflow response is missing model_output.predictions."
        )
