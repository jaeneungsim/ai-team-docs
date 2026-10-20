import base64
import io
import json
import urllib.error

import pytest

from team_docs.confluence import Confluence, ConfluenceError

ROOT = "https://api.atlassian.com/ex/confluence/cloud-1"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Opener:
    """Stands in for urllib.request.urlopen: answers with the next item, or raises it."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Response(json.dumps(answer).encode())


def http_error(code, body=b"{}", headers=None):
    return urllib.error.HTTPError(ROOT, code, "error", headers or {}, io.BytesIO(body))


def client(*answers):
    opener, waits = Opener(answers), []
    return Confluence("cloud-1", "me@example.com", "secret-token", opener=opener, sleep=waits.append), opener, waits


def test_page_list_follows_next_links_under_the_gateway():
    first = {"results": [{"id": "1"}], "_links": {"base": "https://x.atlassian.net/wiki", "next": "/wiki/api/v2/p?c=2"}}
    second = {"results": [{"id": "2"}], "_links": {"base": "https://x.atlassian.net/wiki"}}
    confluence, opener, _ = client(first, second)
    listing = confluence.current_pages("100")
    assert [page["id"] for page in listing.pages] == ["1", "2"]
    assert listing.base == "https://x.atlassian.net/wiki"
    assert [request.full_url for request in opener.requests] == [
        f"{ROOT}/wiki/api/v2/spaces/100/pages?status=current&body-format=storage&limit=250",
        f"{ROOT}/wiki/api/v2/p?c=2",
    ]


def test_every_request_is_a_get_with_basic_auth():
    confluence, opener, _ = client({"results": [{"id": "100", "key": "INV"}]})
    assert confluence.space("INV")["id"] == "100"
    request = opener.requests[0]
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("Authorization") == "Basic " + base64.b64encode(b"me@example.com:secret-token").decode()
    assert not any(hasattr(Confluence, name) for name in ("post", "put", "patch", "delete"))


def test_retries_follow_retry_after_then_back_off():
    confluence, _, waits = client(http_error(429, headers={"Retry-After": "3"}), http_error(503), {"results": [1]})
    assert confluence.get("/wiki/api/v2/x") == {"results": [1]}
    assert waits == [3.0, 2.0]


def test_gives_up_after_four_retries():
    confluence, opener, waits = client(*[http_error(500)] * 5)
    with pytest.raises(ConfluenceError):
        confluence.get("/wiki/api/v2/x")
    assert len(opener.requests) == 5
    assert waits == [1.0, 2.0, 4.0, 8.0]


def test_errors_carry_the_status_and_title_but_not_the_token():
    body = json.dumps({"errors": [{"title": "Unauthorized; scope does not match"}]}).encode()
    confluence, _, _ = client(http_error(401, body))
    with pytest.raises(ConfluenceError) as raised:
        confluence.space("INV")
    assert raised.value.status == 401
    assert str(raised.value) == "HTTP 401: Unauthorized; scope does not match"
    assert "secret-token" not in str(raised.value)


def test_page_status_keeps_trashed_pages_and_maps_missing_ones():
    trashed = {"id": "5", "status": "trashed", "spaceId": "100"}
    confluence, _, _ = client(trashed, http_error(404), http_error(403))
    assert confluence.page_status("5") == (200, trashed)
    assert confluence.page_status("6") == (404, None)
    assert confluence.page_status("7") == (403, None)


def test_a_missing_space_is_an_error():
    confluence, _, _ = client({"results": []})
    with pytest.raises(ConfluenceError, match="space INV not found"):
        confluence.space("INV")
