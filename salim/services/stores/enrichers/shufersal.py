"""Shufersal — a public Wix Data collection, reached in two requests.

The locator is not on the shop domain. ``www.shufersal.co.il`` links to it as
``javascript:toggleBranchesModal()``, and the real address is in the page as
``window.miglog.branchesLink`` = ``/corp/branches`` — a Wix site whose records
live in a collection called ``Branches`` with ``permissions.read: anyone``.

Reading it takes an anonymous token first: ``GET /corp/_api/v1/access-tokens``
returns one token per installed app, and the ``instance`` of the wix-data app
authorises ``POST /corp/_api/cloud-data/v2/items/query``. The API caps a page at
200, so it is paged.

Two properties of this collection matter more than the transport:

- **It is wider than the chain.** 1,001 rows across 15 sub-networks, against 417
  Shufersal branches in the mandated Stores file. 209 of them are ``מחסנים`` —
  warehouses, not shops. Enriching against those attaches a warehouse's phone to
  a real branch whose address happens to match, so they are dropped here rather
  than left for ``matching.py`` to trip over.
- **Absence is encoded three ways**, all of which survive a truthiness check:
  the string ``"undefined"`` (coordinates), the empty string (address, phone),
  and ``"0"`` (phone, on 17 rows). A parser that trusts the value writes
  ``"undefined"`` into a coordinate column and ``0`` as a phone number.
"""
from __future__ import annotations

import logging

import requests

from enrichers.base import Enricher, LocatorRecord

log = logging.getLogger("salim.stores.enrich.shufersal")

SITE_URL = "https://www.shufersal.co.il/corp"
BRANCHES_PAGE = f"{SITE_URL}/branches"
TOKENS_URL = f"{SITE_URL}/_api/v1/access-tokens"
QUERY_URL = f"{SITE_URL}/_api/cloud-data/v2/items/query"

# The wix-data app; its `instance` is what authorises the collection query.
WIX_DATA_APP_ID = "675bbcef-18d8-41f5-800e-131ec9e08762"
COLLECTION = "Branches"
PAGE_SIZE = 200

# Not a retail branch. Kept as a set so a second non-shop network can be added
# without touching the loop.
EXCLUDED_NETWORKS = {"מחסנים"}

HEADERS = {
    "User-Agent": "salim-crawler/1.0 (+https://github.com/ShakedZrihen/data-pipeline-2026)",
    "Accept": "application/json",
}

# Values the collection uses to mean "no value".
_ABSENT = {"", "undefined", "null", "none"}


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _ABSENT else text


def _phone(value: object) -> str | None:
    """Same as ``_text`` but also rejects the "0" placeholder."""
    phone = _text(value)
    if phone is None or phone.strip("0 -") == "":
        return None
    return phone


def _coord(value: object) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        # Anything non-numeric that is not already a known absence marker is
        # worth seeing rather than silently dropping.
        log.warning("unparseable coordinate %r", value)
        return None


def _branch_id(value: object) -> str | None:
    """``branchId`` arrives as a float (160.0). "160.0" matches nothing."""
    text = _text(value)
    if text is None:
        return None
    try:
        return str(int(float(text)))
    except ValueError:
        return text


class ShufersalEnricher(Enricher):
    name = "shufersal"

    def fetch(self) -> list[LocatorRecord]:
        session = requests.Session()
        session.headers.update(HEADERS)

        # The token endpoint is scoped to a visitor session, so the page has to
        # be requested first for it to hand out a usable instance.
        session.get(BRANCHES_PAGE, timeout=30)
        tokens = session.get(TOKENS_URL, timeout=30).json()
        try:
            instance = tokens["apps"][WIX_DATA_APP_ID]["instance"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                "no wix-data instance token in the access-tokens response; "
                "the corp site's app set may have changed"
            ) from exc

        rows = self._all_rows(session, instance)
        records: list[LocatorRecord] = []
        skipped = 0

        for row in rows:
            network = _text(row.get("companyNetwork"))
            if network in EXCLUDED_NETWORKS:
                skipped += 1
                continue

            external_id = _branch_id(row.get("branchId"))
            if external_id is None:
                skipped += 1
                continue

            records.append(
                LocatorRecord(
                    external_id=external_id,
                    address=_text(row.get("branchAddress")),
                    name=_text(row.get("branchName")),
                    city=_text(row.get("city")),
                    phone=_phone(row.get("branchPhone")),
                    latitude=_coord(row.get("latitude")),
                    longitude=_coord(row.get("longitude")),
                )
            )

        log.info(
            "fetched %d branch(es) from the Wix collection (%d non-retail or unidentified rows skipped)",
            len(records),
            skipped,
        )
        return records

    def _all_rows(self, session: requests.Session, instance: str) -> list[dict]:
        headers = {"Authorization": instance, "Content-Type": "application/json"}
        rows: list[dict] = []
        offset = 0
        while True:
            resp = session.post(
                QUERY_URL,
                headers=headers,
                json={
                    "dataCollectionId": COLLECTION,
                    "query": {"paging": {"limit": PAGE_SIZE, "offset": offset}},
                },
                timeout=40,
            )
            resp.raise_for_status()
            page = resp.json().get("dataItems") or []
            if not page:
                break
            rows.extend(item.get("data") or {} for item in page)
            offset += len(page)
            if len(page) < PAGE_SIZE:
                break
        return rows
