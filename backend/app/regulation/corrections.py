"""What resolving a pendency actually changes: the record, the events, the queue.

A correction never edits the dataset. It is applied to the queue state's own
copies (`records`, `events`), and the audit log keeps the before and after —
the same "nothing is imputed, nothing is lost" rule the normalizer follows.

Everything happens on a `Draft`, a cheap copy of the state's mappings. The
preview (`/simular`) builds a draft, applies the action and diffs positions;
the resolution does the same and then adopts the draft. Either way the same
code runs, so the preview cannot lie.
"""
from ..prioritization import rank


class Draft:
    def __init__(self, records, events, assessments, order, locked, confirmed, reference_date, evaluate):
        self.records = dict(records)
        self.events = dict(events)
        self.assessments = dict(assessments)
        self.order = list(order)
        self.locked = set(locked)
        self.confirmed = set(confirmed)
        self.reference_date = reference_date
        self.evaluate = evaluate  # (record, events) -> assessment, the state's own
        self.touched = set()
        self.removed = []

    # --- edits ---------------------------------------------------------------

    def set_fields(self, rid, **fields):
        before = {k: self.records[rid].get(k) for k in fields}
        self.records[rid] = {**self.records[rid], **fields}
        self.touched.add(rid)
        return before

    def set_events(self, rid, events):
        self.events[rid] = list(events)
        self.touched.add(rid)

    def remove(self, rids):
        gone = [rid for rid in rids if rid in self.order]
        self.order = [rid for rid in self.order if rid not in gone]
        self.locked -= set(gone)
        self.removed.extend(gone)

    # --- recalculation -----------------------------------------------------

    def reassess(self):
        for rid in self.touched:
            self.assessments[rid] = self.evaluate(self.records[rid], self.events[rid])

    def reranked(self):
        """The order after the edits: manual positions stay, everyone else follows the Neco."""
        active = {rid: self.assessments[rid] for rid in self.order}
        positions = {rid: i for i, rid in enumerate(self.order, start=1)}
        return rank(active, locked={rid: positions[rid] for rid in self.locked if rid in positions})


def _normalized_cid(cid):
    return cid.strip().upper()


def apply(draft, pendency, action, values, extra_events):
    """Applies `action` to `draft`; returns the facts the audit text needs.

    `extra_events(request_id)` gives the events of a request that is not in the
    queue (an orphan's), from the read-only repository.
    """
    rids = [rid for rid in pendency["entryIds"] if rid in draft.order]
    facts = {}

    if action == "fix_cadastro":
        rid = rids[0]
        draft.set_fields(rid, flag_oncologico_norm=bool(draft.records[rid].get("oncologico_cid")))

    elif action == "update_cid":
        rid = rids[0]
        cid = _normalized_cid(values["cid"])
        before = draft.set_fields(
            rid,
            cid_principal=cid,
            cid_principal_norm=cid,
            cid_descricao="CID corrigido pela regulação",
            oncologico_cid=cid.startswith("C"),
            flag_oncologico_norm=cid.startswith("C"),
        )
        facts.update(before=before["cid_principal"], cid=cid)

    elif action == "unrelated":
        rid = rids[0]
        draft.set_events(rid, [
            e for e in draft.events[rid]
            if not (e.get("tipo_evento_norm") == "biopsia" and e.get("resultado_norm") == "positivo")
        ])

    elif action == "merge":
        kept = values["keep"]
        others = [rid for rid in rids if rid != kept]
        merged = list(draft.events[kept])
        for rid in others:
            merged.extend(draft.events[rid])
        draft.set_events(kept, sorted(merged, key=lambda e: e.get("data_evento") or ""))
        draft.remove(others)
        oldest = pendency["entryIds"][0]
        facts["kept"] = f"{'entrada mais antiga' if kept == oldest else 'solicitação'} {kept}"

    elif action == "remove":
        draft.remove(rids)
        facts["confirmacao"] = values["confirmacao"]

    elif action == "keep" and pendency["kind"] == "left_queue":
        draft.confirmed |= set(rids)
        draft.touched |= set(rids)

    elif action == "link":
        target = values["target"]
        event = next((e for e in extra_events(pendency["eventRequestId"]) if e.get("evento_id") == pendency.get("eventId")), None)
        if event is not None:
            linked = {**event, "solicitacao_id": target, "solicitacao_na_fila": True}
            draft.set_events(target, sorted([*draft.events[target], linked], key=lambda e: e.get("data_evento") or ""))
        facts["target"] = target

    # keep (biopsy), keep_both and archive change nothing in the data.
    draft.reassess()
    return facts
