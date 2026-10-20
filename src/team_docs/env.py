"""Settings that the Lambda functions read from their environment."""

from __future__ import annotations

import os


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"environment variable {name} is not set")
    return value
