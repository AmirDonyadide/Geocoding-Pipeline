"""Exclusive successor logical scratch partitions; no native occupancy claim.

Separate fixed partitions avoid a disk writer retaining the observation owner's
serialization credit. Native object/allocator/I/O costs belong to M2's complete
job domain, not an invented64KiB native guarantee. Historical callers opt out.
"""

from contextlib import contextmanager
import threading

from . import s12_retrieval_contract as c

CAPS = {
    "TIMING": 38912,  # one32768 frame +4096 header +2048 readback
    "KERNEL": 8192,
    "EVENT": 8256,  # 4096 canonical +4097 over-limit read probe +hash
    "OBSERVATION": 4160,  # 2048 canonical+2048 immutable body+hash
    "HASH": 4096,
}
c.require(sum(CAPS.values()) <= 65536, "WF_AP2_SCRATCH_LIMIT")
_locks = {key: threading.RLock() for key in CAPS}
_local = threading.local()


@contextmanager
def lease(kind, *, requested=None):
    """Reserve before materialization; a second same-thread lease is rejected.

    Callers pass already claimed backing to nested helpers rather than create
    a second arena. This API checks the requested logical boundary; it does not
    intercept Python/native allocation and never calls it a native bound.
    """
    c.require(
        kind in CAPS
        and (
            requested is None or type(requested) is int and 0 <= requested <= CAPS[kind]
        ),
        "WF_AP2_SCRATCH_LIMIT",
    )
    occupied = getattr(_local, "occupied", set())
    c.require(kind not in occupied, "WF_AP2_SCRATCH_REENTRANT")
    with _locks[kind]:
        _local.occupied = occupied | {kind}
        try:
            yield CAPS[kind]
        finally:
            _local.occupied = occupied
