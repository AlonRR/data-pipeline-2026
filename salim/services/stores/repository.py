"""Writing branch records into Postgres.

Four rules shape this module:

**The upsert only touches the columns its source owns.** A Stores-file run must
not blank out ``phone`` / ``city`` / coordinates that the locator scrape filled
in earlier, so ``ON CONFLICT DO UPDATE`` lists the Stores-file columns
explicitly instead of replacing the whole row.

**Deactivation is only safe after a successful fetch.** ``is_active`` is derived
from presence in the newest Stores file, so a chain whose fetch failed must be
left alone entirely — otherwise one network error marks every branch closed.

**``chains`` is seeded first.** ``branches.chain_id`` is a foreign key to it, so
a branch cannot be written for a chain with no row. Seeding uses the shared
registry with ON CONFLICT DO NOTHING, so whichever service runs first wins and
neither overwrites the display name the other would have set.

**Opening hours are replaced, never merged.** They live in a child table keyed
by weekday, so a branch that stops publishing a day would otherwise keep
yesterday's row for it forever.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from base import StoreRecord
from hours import intervals_for
from shared.chains import CHAINS
from shared.models import Branch, BranchOpeningHour, Chain

log = logging.getLogger("salim.stores.repository")

# Columns owned by the Stores file. Everything else on the row belongs to the
# enrichment step and is never written here.
_SOURCE_COLUMNS = ("name", "address", "city_code", "store_type", "source_file")


def seed_chains(session: Session) -> None:
    """Ensure every known chain has a row, so the branches FK resolves."""
    rows = [{"chain_id": chain_id, "name": name} for chain_id, name in CHAINS.items()]
    session.execute(insert(Chain).values(rows).on_conflict_do_nothing())


def upsert_branches(session: Session, chain_id: str, records: list[StoreRecord]) -> int:
    """Insert or update rows for *records*. Returns the number written."""
    if not records:
        return 0

    now = datetime.now(timezone.utc)
    rows = [
        {
            "chain_id": chain_id,
            "branch_id": r.store_id,
            "is_active": True,
            "name": r.name,
            "address": r.address,
            "city_code": r.city_code,
            "store_type": r.store_type,
            "source_file": r.source_file,
            "last_seen_at": now,
        }
        for r in records
    ]

    statement = insert(Branch).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[Branch.chain_id, Branch.branch_id],
        set_={
            **{col: getattr(statement.excluded, col) for col in _SOURCE_COLUMNS},
            # Re-appearing in the file reactivates a branch that had closed.
            "is_active": True,
            "last_seen_at": statement.excluded.last_seen_at,
            "metadata_updated_at": now,
        },
    )
    session.execute(statement)
    log.info("upserted %d row(s)", len(rows))
    return len(rows)


def replace_opening_hours(
    session: Session, chain_id: str, branch_id: str, opening_hours: dict | None
) -> int:
    """Rewrite one branch's weekly hours. Returns the number of intervals written.

    Delete-then-insert rather than upsert: a branch that stops publishing
    Sunday should lose its Sunday row, and an upsert keyed on weekday would
    leave the stale one in place indefinitely.
    """
    session.execute(
        delete(BranchOpeningHour).where(
            BranchOpeningHour.chain_id == chain_id,
            BranchOpeningHour.branch_id == branch_id,
        )
    )
    intervals = intervals_for(opening_hours)
    if not intervals:
        return 0

    session.execute(
        insert(BranchOpeningHour).values(
            [
                {
                    "chain_id": chain_id,
                    "branch_id": branch_id,
                    "weekday": weekday,
                    "interval_index": index,
                    "opens_at": opens,
                    "closes_at": closes,
                }
                for weekday, index, opens, closes in intervals
            ]
        )
    )
    return len(intervals)


def apply_enrichment(
    session, chain_id, provider, locator_records, matches, not_provided
) -> dict[str, int]:
    """Write locator data onto matched branch rows.

    Which fields are safe depends on how the branch matched:

    - **unique** — one branch, one locator record: write everything.
    - **ambiguous** — several branches share one locator record, because the
      chain runs more than one business at that address (a supermarket and a
      produce store, each with its own id, while the locator lists the site
      once). Address-intrinsic facts still hold for both: coordinates, city,
      and the phone number. **Opening hours do not** — a produce counter does
      not keep the supermarket's hours — so they are left alone rather than
      guessed at.

    ``not_provided`` is the source's own gap list, written to every row it
    touches so a null column can be told apart from one this locator never
    carries at all.
    """
    by_external = {r.external_id: r for r in locator_records}
    now = datetime.now(timezone.utc)
    stats = {"unique": 0, "ambiguous": 0, "hour_rows": 0}

    for branch_id, match in matches.items():
        record = by_external.get(match.external_id)
        if record is None:
            continue

        values = {
            "city": record.city,
            "phone": record.phone,
            "latitude": record.latitude,
            "longitude": record.longitude,
            "enrichment_source": f"{provider}:{match.external_id}"[:128],
            "enrichment_match": "unique" if match.is_unique else "ambiguous",
            "enriched_at": now,
            "metadata_updated_at": now,
        }
        session.execute(
            update(Branch)
            .where(Branch.chain_id == chain_id, Branch.branch_id == branch_id)
            .values(
                # A locator with no value for a field must not erase one the
                # Stores file supplied, so Nones are dropped — but the gap list
                # is written unconditionally, since "this source carries no
                # phone column at all" is itself the fact worth recording.
                **{k: v for k, v in values.items() if v is not None},
                fields_not_provided=list(not_provided),
            )
        )

        if match.is_unique:
            stats["hour_rows"] += replace_opening_hours(
                session, chain_id, branch_id, record.opening_hours
            )
        stats["unique" if match.is_unique else "ambiguous"] += 1

    log.info(
        "%s: enriched %d row(s) uniquely, %d with address-only data, %d opening-hour row(s)",
        provider,
        stats["unique"],
        stats["ambiguous"],
        stats["hour_rows"],
    )
    return stats


def deactivate_missing(session: Session, chain_id: str, seen_ids: set[str]) -> int:
    """Flag branches of *chain_id* that the newest file no longer lists.

    Call only after that chain's fetch succeeded and returned records.
    """
    if not seen_ids:
        log.warning("refusing to deactivate %s: fetch returned no records", chain_id)
        return 0

    result = session.execute(
        update(Branch)
        .where(
            Branch.chain_id == chain_id,
            Branch.branch_id.not_in(seen_ids),
            Branch.is_active.is_(True),
        )
        .values(is_active=False, metadata_updated_at=datetime.now(timezone.utc))
    )
    count = result.rowcount or 0
    if count:
        log.info("deactivated %d branch(es) no longer listed by %s", count, chain_id)
    return count
