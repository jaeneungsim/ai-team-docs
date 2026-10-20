"""Storage fixtures are copied from the live demo site, so check that nothing identifying came with them."""

import re
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "storage").glob("*.html"))
FAKE_ACCOUNT_ID = "000000:00000000-0000-0000-0000-000000000000"  # mentions in fixtures use this id
IDENTIFYING = {
    "site address": re.compile(r"[\w-]+\.atlassian\.net"),
    "gateway URL with a cloud id": re.compile(r"api\.atlassian\.com/ex/"),
    "email address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "real user id": re.compile(r'ri:(?:account-id|userkey)="(?!' + re.escape(FAKE_ACCOUNT_ID) + '")'),
}


def test_fixtures_exist():
    assert len(FIXTURES) >= 8


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.name)
def test_fixture_has_nothing_identifying(path):
    text = path.read_text()
    for what, pattern in IDENTIFYING.items():
        assert not pattern.search(text), f"{path.name} contains a {what}"
