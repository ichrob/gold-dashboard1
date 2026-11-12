"""Capacity of Bob's existing production Postgres volume.

Confirmed by authenticated Render metadata on 2026-11-04 at 21:44 UTC:
dpg-datjno1srm7s738vv500-a, diskSizeGB=5. Not a RAM budget.
This records an operator-completed purchase; it never provisions storage.
"""
ALLOCATION_BYTES = 5_000_000_000
CAUTION_BYTES = ALLOCATION_BYTES // 2
ACTION_BYTES = ALLOCATION_BYTES * 7 // 10
MAX_VOLUME_BYTES = ALLOCATION_BYTES * 75 // 100
REPACK_MAX_VOLUME_BYTES = ALLOCATION_BYTES * 73 // 100
COMPACTION_MAX_VOLUME_BYTES = ALLOCATION_BYTES * 725 // 1000
