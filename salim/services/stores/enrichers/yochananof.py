"""Yochananof — Apollo GraphQL endpoint, no auth.

Found the way ``enrichers/base.py`` describes: the branch page renders nothing
server-side, and the JS bundle names its endpoint,
``https://api.yochananof.co.il/graphql``. Introspection is left enabled, which
is how ``externalStores`` and its field list were read.

Three things about this source are unlike every other chain, and all three fail
quietly rather than loudly if they are read the obvious way:

- **The site is ``yochananof.co.il``** — a ``ch``, unlike the crawler's
  ``yohananof`` provider name — and its certificate covers only the apex. A
  request to ``www.`` fails verification, so the apex is used and TLS
  verification stays on.
- **Hours are minutes from midnight on a 0-based weekday.** 450 is 07:30, and
  weekday 0 is Sunday, so ``day_name`` needs ``weekday + 1``. Off by one moves
  every branch's short Friday onto Saturday and still looks like a schedule.
- **Coordinates are not fields.** They are embedded in ``locationMapUrl``, a
  Google Maps embed, as ``!2d<longitude>!3d<latitude>`` — longitude first.

It also publishes **no phone numbers at all** (0 of 52 when measured), so the
phone column stays null for this chain however well the matching goes.
"""
from __future__ import annotations

import logging
import re

import requests

from enrichers.base import Enricher, LocatorRecord, day_name, flatten_hours

log = logging.getLogger("salim.stores.enrich.yochananof")

API_URL = "https://api.yochananof.co.il/graphql"
SITE_URL = "https://yochananof.co.il"
HEADERS = {
    "User-Agent": "salim-crawler/1.0 (+https://github.com/ShakedZrihen/data-pipeline-2026)",
    "Content-Type": "application/json",
    "Accept": "application/json",
    # The endpoint is a separate origin from the site; Apollo sends both.
    "Origin": SITE_URL,
    "Referer": f"{SITE_URL}/",
}

QUERY = """
{
  externalStores {
    storeNumber
    storeName
    address
    customerServicePhone
    locationMapUrl
    openingHours {
      defaultByWeekday {
        weekday
        standard { from to }
        daylightSaving { from to }
      }
    }
  }
}
"""

# !2d<longitude>!3d<latitude> inside the Google Maps embed URL.
_COORDS_RE = re.compile(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)")


def _clock(minutes: int | None) -> str | None:
    """Minutes from midnight -> "HH:MM"."""
    if minutes is None:
        return None
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def _coords(map_url: str | None) -> tuple[float | None, float | None]:
    if not map_url:
        return None, None
    match = _COORDS_RE.search(map_url)
    if not match:
        return None, None
    longitude, latitude = float(match.group(1)), float(match.group(2))
    return latitude, longitude


def _city_from(address: str | None) -> str | None:
    """Last comma-separated segment, matching the Hazi Hinam enricher.

    The GraphQL response has no city field, but its addresses carry one after
    the comma ("המפוח 11, א.ת רחובות"). Deriving it here keeps the column
    populated for this chain rather than leaving it null for want of a field.
    """
    if not address or "," not in address:
        return None
    return address.rsplit(",", 1)[-1].strip() or None


def _window(day: dict) -> dict | None:
    """One day's opening window, or ``None`` when the branch is shut.

    ``standard`` is a list of ranges: empty means closed (that is how Saturday
    arrives), and more than one would be a split shift, so the day is taken as
    its outer bounds. ``daylightSaving`` is only present where summer hours
    differ; the standard window is the one stored, since the flat
    ``from``/``to`` the issue asks for cannot express both.
    """
    ranges = day.get("standard") or []
    if not ranges:
        return None
    start = _clock(min(r["from"] for r in ranges))
    end = _clock(max(r["to"] for r in ranges))
    if start is None or end is None:
        return None
    return {"from": start, "to": end}


class YochananofEnricher(Enricher):
    name = "yohananof"  # the crawler's spelling, which keys stores.provider

    def fetch(self) -> list[LocatorRecord]:
        resp = requests.post(API_URL, headers=HEADERS, json={"query": QUERY}, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise RuntimeError(f"GraphQL query failed: {payload['errors']!r}")

        stores = payload["data"]["externalStores"]
        records: list[LocatorRecord] = []

        for store in stores:
            hours: dict[str, dict | None] = {}
            by_weekday = (store.get("openingHours") or {}).get("defaultByWeekday") or []
            for day in by_weekday:
                # 0-based here, 1-based in day_name().
                hours[day_name(int(day["weekday"]) + 1)] = _window(day)

            opening_from, opening_to = flatten_hours(hours)
            latitude, longitude = _coords(store.get("locationMapUrl"))

            records.append(
                LocatorRecord(
                    external_id=str(store["storeNumber"]),
                    address=store.get("address") or None,
                    name=store.get("storeName") or None,
                    city=_city_from(store.get("address")),
                    phone=store.get("customerServicePhone") or None,
                    latitude=latitude,
                    longitude=longitude,
                    opening_hours=hours or None,
                    opening_from=opening_from,
                    opening_to=opening_to,
                )
            )

        log.info("fetched %d branch(es) from the GraphQL locator", len(records))
        return records
