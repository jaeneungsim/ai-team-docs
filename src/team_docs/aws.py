"""boto3 clients, made once per Lambda container."""

from __future__ import annotations

from functools import cache
from typing import Any


@cache
def client(service: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(service, config=Config(retries={"mode": "standard", "max_attempts": 5}))


@cache
def table(name: str) -> Any:
    import boto3

    return boto3.resource("dynamodb").Table(name)


def error_code(err: Exception) -> str:
    """The AWS error code of a botocore ClientError, or an empty string."""
    response = getattr(err, "response", None) or {}
    return str(response.get("Error", {}).get("Code", ""))
