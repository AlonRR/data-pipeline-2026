"""Shufersal locator — a Wix collection that is wider and dirtier than the chain.

It returns 1,001 rows across 15 sub-networks against 417 in the mandated Stores
file, and it encodes absent values three different ways: the string
``"undefined"``, the empty string, and — for phones — ``"0"``. All three are
truthy or parse cleanly, so each one silently produces a wrong column rather
than an error. Every case below is taken from a captured live page.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enrichers.shufersal import ShufersalEnricher

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "shufersal_wixdata.json").read_text(encoding="utf-8"))


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def records(monkeypatch):
    """Serve the captured page once, then an empty page to stop the pager."""
    pages = [FIXTURE, {"dataItems": []}]

    class _Session:
        headers: dict = {}

        def get(self, url, **kwargs):
            if "access-tokens" in url:
                return _FakeResponse({"apps": {"675bbcef-18d8-41f5-800e-131ec9e08762": {"instance": "tok"}}})
            return _FakeResponse({})

        def post(self, url, **kwargs):
            return _FakeResponse(pages.pop(0) if pages else {"dataItems": []})

    monkeypatch.setattr("enrichers.shufersal.requests.Session", _Session)
    return ShufersalEnricher().fetch()


def _by_id(records, external_id):
    return next(r for r in records if r.external_id == external_id)


def test_warehouses_are_excluded_from_enrichment(records):
    """209 of the 1,001 rows are מחסנים, which are not retail branches. Left in,
    they match Stores-file addresses and attach the wrong phone to a real shop."""
    assert len(records) == 3
    assert all(r.external_id != "999" for r in records)


def test_undefined_string_is_not_stored_as_a_coordinate(records):
    """Absent coordinates arrive as the string "undefined", which is truthy and
    would be written straight into a float column as garbage."""
    sparse = _by_id(records, "944")
    assert sparse.latitude is None
    assert sparse.longitude is None


def test_real_coordinates_are_parsed_as_floats(records):
    branch = _by_id(records, "160")
    assert branch.latitude == pytest.approx(32.0661423)
    assert isinstance(branch.longitude, float)


def test_phone_and_address_are_carried_through(records):
    branch = _by_id(records, "160")
    assert branch.phone == "03-5742712"
    assert branch.address == "הירדן 29"


def test_empty_strings_become_none_not_blank(records):
    """A blank address must not overwrite a good one from the Stores file."""
    assert _by_id(records, "944").address is None


def test_placeholder_zero_phone_is_rejected(records):
    """17 rows carry "0" as the phone. It is a placeholder, not a number, and
    it looks entirely valid to a NOT NULL check."""
    assert _by_id(records, "690").phone is None


def test_external_id_is_the_integer_branch_id(records):
    """branchId arrives as a float (160.0); "160.0" would never match the
    Stores file's "160"."""
    assert _by_id(records, "160").external_id == "160"
