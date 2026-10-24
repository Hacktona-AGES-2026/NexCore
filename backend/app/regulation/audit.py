"""Append-only audit log, chained by SHA-256.

`hash = SHA-256(prevHash + canonical JSON of [at, author, kind, entryId, from,
to, justification])`, and the first record chains to "00000000" — the formula
in docs/CONTRATO_BACKEND.md §5, so anyone can recompute the chain from the CSV
the front exports. There is no edit and no delete: that is the point.
"""
from datetime import datetime, timezone
import hashlib
import json

GENESIS = "00000000"
KINDS = ("recalc", "intake", "manual", "validation", "data")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def chain_hash(prev_hash, at, author, kind, entry_id, origin, target, justification):
    canonical = json.dumps(
        [at, author, kind, entry_id, origin, target, justification],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, clock=utc_now):
        self._clock = clock
        self._records = []  # oldest first

    def append(self, kind, author, entry_id, entry_name, origin, target, justification):
        if kind not in KINDS:
            raise ValueError(f"unknown audit kind '{kind}'")
        at = self._clock()
        prev_hash = self._records[-1]["hash"] if self._records else GENESIS
        record = {
            "id": f"AUD-{len(self._records) + 1:05d}",
            "at": at,
            "author": author,
            "kind": kind,
            "entryId": entry_id,
            "entryName": entry_name,
            "from": origin,
            "to": target,
            "justification": justification,
            "hash": chain_hash(prev_hash, at, author, kind, entry_id, origin, target, justification),
            "prevHash": prev_hash,
        }
        self._records.append(record)
        return dict(record)

    def newest_first(self):
        return [dict(r) for r in reversed(self._records)]

    def __len__(self):
        return len(self._records)


def chain_is_intact(records_newest_first):
    """Recomputes every hash: the check the front only approximates."""
    prev = GENESIS
    for record in reversed(records_newest_first):
        expected = chain_hash(
            prev, record["at"], record["author"], record["kind"], record["entryId"],
            record["from"], record["to"], record["justification"],
        )
        if record["prevHash"] != prev or record["hash"] != expected:
            return False
        prev = record["hash"]
    return True
