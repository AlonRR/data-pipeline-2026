"""Re-export of the shared chain registry.

The registry moved to ``shared/chains.py`` when the stores service needed it
too: ``branches.chain_id`` is a foreign key to ``chains``, so that service has
to seed the same rows, and ``chains.name`` is NOT NULL with
``on_conflict_do_nothing`` — whichever service runs first sets the display
name. Two copies would mean a run order that decides whether the name reads
"שופרסל" or "shufersal".
"""
from shared.chains import CHAINS  # noqa: F401
