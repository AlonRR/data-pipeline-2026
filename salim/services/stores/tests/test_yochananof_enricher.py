"""Yochananof locator — the GraphQL response is shaped unlike any other chain's.

Hours arrive as minutes from midnight on a 0-based weekday, coordinates are
buried in a Google Maps embed URL rather than published as fields, and the
phone column is empty for every branch. Each of those is asserted here against
a captured live response, because each one silently produces a wrong row rather
than an error if it is read the obvious way.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enrichers.yochananof import YochananofEnricher

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "yochananof_graphql.json").read_text(encoding="utf-8"))


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def records(monkeypatch):
    def fake_post(url, **kwargs):
        assert "graphql" in url
        return _FakeResponse(FIXTURE)

    monkeypatch.setattr("enrichers.yochananof.requests.post", fake_post)
    return YochananofEnricher().fetch()


def test_fetch_returns_one_record_per_store(records):
    assert len(records) == 2


def test_minutes_from_midnight_become_clock_times(records):
    # 450 -> 07:30 and 1260 -> 21:00 in the captured response.
    sunday = records[0].opening_hours["sunday"]
    assert sunday == {"from": "07:30", "to": "21:00"}


def test_weekday_zero_is_sunday_not_monday(records):
    """The API is 0-based; `day_name` is 1-based. Off by one puts every
    branch's Friday hours on Saturday, which reads as plausible."""
    assert records[0].opening_hours["friday"] is not None
    # Saturday arrives as an empty `standard` list: closed, not unknown.
    assert records[0].opening_hours["saturday"] is None


def test_coordinates_are_parsed_out_of_the_maps_embed_url(records):
    # !2d<longitude>!3d<latitude> — longitude comes first.
    assert records[0].latitude == pytest.approx(31.886541)
    assert records[0].longitude == pytest.approx(34.780207)


def test_missing_map_url_yields_no_coordinates_rather_than_raising(records):
    assert records[1].latitude is None
    assert records[1].longitude is None


def test_phone_is_absent_for_every_branch(records):
    """Yochananof publishes no branch phone numbers. Asserted so that a future
    change to the API surfaces as a failing test rather than a silent gap."""
    assert all(r.phone is None for r in records)


def test_external_id_is_the_store_number(records):
    assert records[0].external_id == "1"


def test_city_is_derived_from_the_address(records):
    """The GraphQL response has no city field, but the address carries one
    after the comma — the same shape the Hazi Hinam enricher relies on."""
    assert records[0].city == "א.ת רחובות"
