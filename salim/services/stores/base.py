"""Abstract base for a store-list source, plus the normalized record it yields.

Mirrors the shape of ``crawler.py``: one subclass per chain, each implementing
the single step that actually differs between chains — how you reach that
chain's newest ``Stores`` file. Parsing that file, normalizing it and writing
it to the DB is shared and lives outside the subclass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class StoreRecord:
    """One branch, normalized across chains.

    Only ``provider`` and ``store_id`` are ever guaranteed: the mandated Stores
    file supplies the middle block, and the locator-derived fields stay ``None``
    until the enrichment step fills them in.
    """

    provider: str
    store_id: str

    name: str | None = None
    address: str | None = None
    city_code: str | None = None
    store_type: str | None = None
    chain_id: str | None = None

    city: str | None = None
    phone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    opening_hours: dict | None = None
    opening_from: str | None = None
    opening_to: str | None = None

    source_file: str | None = None

    def is_physical(self) -> bool:
        """False for the non-branch rows chains put in the same file.

        ``StoreType`` 1 is a physical branch; other values are logical entities
        such as Hazi Hinam's "חצי חינם משלוחים", whose Address field holds a URL
        rather than a street. Those must not reach geocoding or the locator match.
        """
        return (self.store_type or "1") == "1"


@dataclass
class SourceResult:
    """What one chain's fetch produced."""

    records: list[StoreRecord] = field(default_factory=list)
    source_file: str | None = None


class StoreSource(ABC):
    """A chain's store list. Subclasses implement ``fetch`` only."""

    #: unique key for config and logs — the crawler's spelling of the chain
    name: str

    #: The numeric ``ChainId`` this chain writes into its own files, e.g.
    #: ``"7290027600007"``. ``branches`` is keyed on it and ``prices.provider``
    #: carries the same value, so it is what makes the two join.
    #:
    #: Declared here rather than read from the parsed file so the enrichment
    #: half has a key even when this run's sync failed or was skipped — and so
    #: a file published under the wrong ChainId is caught instead of silently
    #: creating a second set of branches.
    chain_id: str

    @abstractmethod
    def fetch(self) -> SourceResult:
        """Locate this chain's newest Stores file, download and parse it."""
