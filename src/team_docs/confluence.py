"""A Confluence Cloud client that can only read.

There is no way to send anything but GET: the sync never changes Confluence. Calls go through the
api.atlassian.com gateway, which is the address that scoped API tokens work with.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

GATEWAY = "https://api.atlassian.com/ex/confluence"
RETRIES = 4
MAX_WAIT_SECONDS = 30


class ConfluenceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status = status


@dataclass(frozen=True)
class PageList:
    base: str  # the site address that page links start with, for example https://<site>.atlassian.net/wiki
    pages: list[dict[str, Any]]


class Confluence:
    def __init__(
        self,
        cloud_id: str,
        email: str,
        token: str,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.root = f"{GATEWAY}/{cloud_id}"
        self._auth = "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()
        self._open = opener
        self._sleep = sleep

    def get(self, path: str) -> dict[str, Any]:
        """GET a path under the gateway. 429, 5xx and network errors are retried with backoff."""
        for attempt in range(RETRIES + 1):
            request = urllib.request.Request(
                self.root + path, headers={"Authorization": self._auth, "Accept": "application/json"}
            )
            try:
                with self._open(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as err:
                if (err.code == 429 or err.code >= 500) and attempt < RETRIES:
                    self._sleep(_wait(err.headers.get("Retry-After"), attempt))
                    continue
                raise ConfluenceError(err.code, _summary(err)) from None
            except urllib.error.URLError as err:
                if attempt < RETRIES:
                    self._sleep(_wait(None, attempt))
                    continue
                raise ConfluenceError(0, f"cannot reach Confluence: {err.reason}") from None
        raise AssertionError("unreachable")

    def space(self, key: str) -> dict[str, Any]:
        results = self.get(f"/wiki/api/v2/spaces?keys={urllib.parse.quote(key)}")["results"]
        if not results:
            raise ConfluenceError(404, f"space {key} not found, or the token cannot see it")
        return results[0]

    def current_pages(self, space_id: str) -> PageList:
        """Every current page of the space with its storage body. Archived and trashed pages are left out."""
        path: str | None = f"/wiki/api/v2/spaces/{space_id}/pages?status=current&body-format=storage&limit=250"
        pages: list[dict[str, Any]] = []
        base = ""
        while path:
            answer = self.get(path)
            pages.extend(answer["results"])
            links = answer.get("_links", {})
            base = links.get("base", base)
            path = links.get("next")  # a path under the gateway, never under the site address
        return PageList(base, pages)

    def page_status(self, page_id: str) -> tuple[int, dict[str, Any] | None]:
        """HTTP status and page for one id. A trashed or archived page still answers 200, with its status."""
        try:
            return 200, self.get(f"/wiki/api/v2/pages/{page_id}")
        except ConfluenceError as err:
            if err.status in (403, 404):
                return err.status, None
            raise


def _wait(retry_after: str | None, attempt: int) -> float:
    if retry_after and retry_after.strip().isdigit():
        return min(float(retry_after), MAX_WAIT_SECONDS)
    return min(2.0**attempt, MAX_WAIT_SECONDS)


def _summary(err: urllib.error.HTTPError) -> str:
    """The error title Confluence sent, without the request or its headers."""
    try:
        errors = json.loads(err.read().decode("utf-8", "replace")).get("errors") or [{}]
        return str(errors[0].get("title") or err.reason)[:200]
    except (ValueError, AttributeError):
        return str(err.reason)[:200]
