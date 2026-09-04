"""A null field has to say *why* it is null.

Three different facts currently collapse into one NULL: the source publishes no
such field at all, the source has the field but this branch is blank, and
nobody has looked this branch up yet. `enriched_at` separates the third; these
declarations separate the first two, because "not provided" is a property of
the source rather than of the row.

The declarations are measured, not assumed — see the coverage table in
services/stores/README.md.
"""
from __future__ import annotations

import unittest

from enrichers.base import ENRICHABLE_FIELDS, Enricher
from enrichers.hazi_hinam import HaziHinamEnricher
from enrichers.rami_levi import RamiLeviEnricher
from enrichers.shufersal import ShufersalEnricher
from enrichers.yochananof import YochananofEnricher
from shared.models import Base

ALL = (YochananofEnricher, HaziHinamEnricher, RamiLeviEnricher, ShufersalEnricher)


class NotProvidedTests(unittest.TestCase):
    def test_every_enricher_declares_what_it_supplies(self):
        for cls in ALL:
            self.assertTrue(cls.provides, f"{cls.__name__} declares nothing")

    def test_no_enricher_claims_a_field_that_is_not_enrichable(self):
        """A typo in a declaration would otherwise mark a real field as not
        provided forever, and nothing would ever notice."""
        for cls in ALL:
            unknown = set(cls.provides) - ENRICHABLE_FIELDS
            self.assertEqual(unknown, set(), f"{cls.__name__} claims unknown field(s)")

    def test_not_provided_is_the_complement_of_provides(self):
        for cls in ALL:
            self.assertEqual(
                set(cls.not_provided()) | set(cls.provides), ENRICHABLE_FIELDS
            )
            self.assertEqual(set(cls.not_provided()) & set(cls.provides), set())

    def test_the_measured_gaps_are_declared(self):
        """Measured live 3 Sept 2026 across all four locators. These are the
        fields the source has no data for at all — not a scrape that failed."""
        self.assertEqual(YochananofEnricher.not_provided(), ["phone"])
        self.assertEqual(ShufersalEnricher.not_provided(), ["opening_hours"])
        self.assertEqual(RamiLeviEnricher.not_provided(), ["latitude", "longitude"])
        self.assertEqual(HaziHinamEnricher.not_provided(), [])

    def test_branches_can_record_it_per_row(self):
        self.assertIn("fields_not_provided", Base.metadata.tables["branches"].columns)

    def test_not_provided_is_sorted_so_rows_compare_equal(self):
        """Written into a JSONB column and compared across runs; set ordering
        would make two identical rows look like a change."""
        for cls in ALL:
            self.assertEqual(cls.not_provided(), sorted(cls.not_provided()))
