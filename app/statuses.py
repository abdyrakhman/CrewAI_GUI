"""Run status vocabulary: one place for "this run is over" and "this run is stuck"."""
from __future__ import annotations

TERMINAL = frozenset({"completed", "failed", "cancelled", "force_stopping"})
ORPHAN_CANDIDATES = frozenset({"queued", "running", "cancelling"})
# After a process restart no run can still be alive, including a forced one.
STALE_ON_START = ORPHAN_CANDIDATES | {"force_stopping"}
ACTIVE = ORPHAN_CANDIDATES | {"force_stopping"}
