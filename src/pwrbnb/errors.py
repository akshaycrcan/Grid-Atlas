"""Actionable API failures without exposing provider messages or credentials."""


def describe_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    detail = body.get("error", body) if isinstance(body, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else None
    kind = type(exc).__name__
    if code in {"credit_balance_exhausted", "insufficient_quota", "billing_hard_limit_reached"}:
        return (
            "OpenAI API credits or billing quota are exhausted. Add API credits or review your "
            "project's billing limit at https://platform.openai.com/settings/organization/billing/, "
            "then retry. Your .env file does not need to be moved or recreated."
        )
    if status == 401 or kind == "AuthenticationError":
        return (
            "OpenAI rejected the API key. Check OPENAI_API_KEY in the project .env file and restart the app."
        )
    if status == 403 or kind == "PermissionDeniedError":
        return "The API key lacks permission for this request. Check the key's project permissions and model access."
    if status == 404 or code in {"model_not_found", "invalid_model"}:
        return (
            "The selected model is unavailable to this API project. Check OpenAI model in Research settings."
        )
    if status == 429 or kind == "RateLimitError":
        return "OpenAI's rate limit was reached. Wait briefly and retry, or review the project's API limits."
    if kind in {"APITimeoutError", "TimeoutError", "BudgetExceeded"}:
        return "The request exceeded its time limit. Retry or increase the research time limit in settings."
    if kind == "APIConnectionError":
        return "The app could not connect to OpenAI. Check your connection, proxy, firewall, and certificate setup."
    if status == 400:
        return "OpenAI rejected the request configuration. Check that the model supports web search and structured outputs."
    if status is not None and status >= 500:
        return "OpenAI returned a temporary server error. Please retry shortly."
    if kind in {"LengthFinishReasonError", "ValidationError"}:
        return "The model response could not be validated. Try increasing the output-token limit and retry."
    return (
        "The request could not be completed. Check configuration and retry; no unsupported answer was saved."
    )
