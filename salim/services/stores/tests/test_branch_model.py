"""`branches` has to carry everything issue #23 asks a store row to hold.

The Stores file supplies identity; the chain's own locator supplies phone,
coordinates and hours. `branches` was added by the loader work for the first
kind and is missing the second, so these assertions are what makes it a
possible destination for this service rather than a parallel `stores` table.

They are deliberately about the *columns the issue names*, not a restatement of
the model: if someone later drops `phone` to simplify the schema, #23's DoD
silently stops being satisfiable and this fails.
"""
from __future__ import annotations

import unittest

from shared.models import Base


class BranchModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.branches = Base.metadata.tables["branches"]
        self.columns = set(self.branches.columns.keys())

    def test_carries_the_identity_fields_from_the_stores_file(self):
        for name in ("chain_id", "branch_id", "name", "address", "city", "is_active"):
            self.assertIn(name, self.columns)

    def test_carries_the_locator_fields_the_stores_file_lacks(self):
        """phone / coordinates are the whole reason the enrichers exist."""
        for name in ("phone", "latitude", "longitude"):
            self.assertIn(name, self.columns, f"#23 asks for {name}")

    def test_carries_the_stores_file_fields_that_are_not_identity(self):
        """`city_code` is a CBS municipality code and is NOT a city name — the
        published Stores file has no city name at all, which is why `city`
        comes from the locator and both columns have to exist."""
        for name in ("city_code", "store_type"):
            self.assertIn(name, self.columns, f"#23's Stores-file half needs {name}")

    def test_records_where_each_row_came_from(self):
        """Enrichment is partial and per-chain, so a row has to say whether it
        was enriched, from what, and how confidently it matched — otherwise a
        null phone is indistinguishable from a phone that was never looked up."""
        for name in ("source_file", "enrichment_source", "enrichment_match", "enriched_at"):
            self.assertIn(name, self.columns)

    def test_records_lifecycle_timestamps(self):
        for name in ("first_seen_at", "last_seen_at"):
            self.assertIn(name, self.columns)

    def test_is_keyed_on_chain_id_so_it_joins_to_prices(self):
        """`prices.provider` is the numeric ChainId. Keying branches the same
        way is what makes the join work without a translation table."""
        self.assertEqual([c.name for c in self.branches.primary_key], ["chain_id", "branch_id"])

    def test_chain_id_is_a_foreign_key_to_chains(self):
        targets = {str(fk.column) for fk in self.branches.foreign_keys}
        self.assertIn("chains.chain_id", targets)


if __name__ == "__main__":
    unittest.main()
