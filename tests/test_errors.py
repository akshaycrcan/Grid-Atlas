from types import SimpleNamespace

import pytest

from pwrbnb.errors import describe_error


@pytest.mark.parametrize(
    "code", ["credit_balance_exhausted", "insufficient_quota", "billing_hard_limit_reached"]
)
def test_billing_failure_is_actionable_and_redacts_provider_message(code):
    exc = SimpleNamespace(status_code=429, body={"code": code, "message": "Secret: sk-test-do-not-display"})
    message = describe_error(exc)
    assert "billing" in message and "credits" in message
    assert "sk-test" not in message
    assert "Wait briefly" not in message


def test_rate_limit_is_distinct_from_no_credits():
    exc = SimpleNamespace(status_code=429, body={"error": {"code": "rate_limit_exceeded"}})
    assert "Wait briefly" in describe_error(exc)


@pytest.mark.parametrize(
    "status, phrase",
    [
        (401, "rejected the API key"),
        (403, "lacks permission"),
        (404, "model"),
        (400, "configuration"),
        (503, "temporary server error"),
    ],
)
def test_status_messages_are_safe(status, phrase):
    exc = SimpleNamespace(status_code=status, body={"message": "raw private payload"})
    assert phrase in describe_error(exc)
    assert "private payload" not in describe_error(exc)


def test_unexpected_error_does_not_leak_exception_text():
    assert "sk-secret" not in describe_error(ValueError("sk-secret"))
