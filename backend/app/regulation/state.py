"""The queue as the regulation sees it: ranked, mutable, audited, broadcast.

Built once from the read-only repository when the app starts, then changed only
by the admin's actions. State lives in memory (a decision for the hackathon):
restarting the server goes back to the Neco's initial ranking and an empty
audit log. That also means ONE process — two gunicorn workers would hold two
different queues.

Every mutation runs under one lock and publishes its frames before releasing
it, so every socket sees the changes in the order they happened.
"""
import json
from pathlib import Path
import threading

from ..data.reader import strip_accents
from ..prioritization import CLASS_LABEL, assess, golden_rule_violation, rank, relocate
from . import ask, panels, pendencies, serializers
from .audit import AuditLog, utc_now
from .errors import ContractError
from .hub import Hub

ADMIN = "Marina Albuquerque"
NECO = "Neco"
MIN_JUSTIFICATION = 40
MUNICIPALITIES = Path(__file__).with_name("municipalities.json")


def load_municipalities(path=MUNICIPALITIES):
    """Accent-free key -> {name, lat, lon}. The dataset spells cities without accents."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return {strip_accents(r["name"]): r for r in rows}


def first_name(name):
    return (name or "").split(" ")[0]


class QueueState:
    def __init__(self, repository, author=ADMIN, clock=utc_now, municipalities=None):
        self._lock = threading.RLock()
        self.author = author
        self.reference_date = repository.reference_date
        self.hub = Hub()
        self.audit = AuditLog(clock)
        self._clock = clock

        places = load_municipalities() if municipalities is None else municipalities
        self.coordinates = {p["name"]: p for p in places.values()}
        self.records = {}
        self.assessments = {}
        self._entries = {}
        for record in repository.queue:
            rid = record["solicitacao_id"]
            events = repository.events_for_request(rid)
            assessment = assess(record, events, repository.reference_date)
            place = places.get(strip_accents(record.get("municipio_norm")))
            self.records[rid] = record
            self.assessments[rid] = assessment
            self._entries[rid] = serializers.queue_entry(
                record, assessment, events, city=place["name"] if place else None,
            )

        self.order = rank(self.assessments)
        self.locked = set()
        self.previous = {}
        self.pendencies = {p["id"]: p for p in pendencies.detect(repository, self.assessments)}
        self._initial_audit()

    # --- reads ---------------------------------------------------------

    def _entry(self, rid, position):
        entry = dict(self._entries[rid])
        entry["position"] = position
        if rid in self.previous:
            entry["previousPosition"] = self.previous[rid]
        entry["locked"] = rid in self.locked
        return entry

    def entries(self):
        with self._lock:
            return [self._entry(rid, i) for i, rid in enumerate(self.order, start=1)]

    def snapshot(self, hospital_id):
        with self._lock:
            entries = self.entries()
            return {"hospitalId": hospital_id, "total": len(entries), "entries": entries}

    def audit_log(self):
        with self._lock:
            return self.audit.newest_first()

    def pendency_list(self):
        with self._lock:
            return [dict(p) for p in self.pendencies.values()]

    def summary(self):
        return panels.summary(self.entries())

    def equity(self):
        return panels.equity(self.entries(), self.records, self.coordinates)

    def ask(self, question):
        with self._lock:
            entries = self.entries()
            return ask.answer(
                question, entries, panels.summary(entries),
                panels.equity(entries, self.records, self.coordinates),
                self.pendency_list(),
            )

    def subscribe(self, hospital_id):
        """A subscription whose first frame is the full snapshot.

        Taken under the lock, so no change can slip between the snapshot and the
        first patch the socket receives.
        """
        with self._lock:
            subscription = self.hub.subscribe()
            subscription.put({"type": "queue.snapshot", "snapshot": self.snapshot(hospital_id)})
            return subscription

    # --- actions -------------------------------------------------------

    def _require(self, rid):
        if rid not in self._entries or rid not in self.order:
            raise ContractError(f"Solicitação {rid} não encontrada na fila.", 404)

    def reorder(self, rid, position, reason, justification):
        with self._lock:
            self._require(rid)
            total = len(self.order)
            if isinstance(position, bool) or not isinstance(position, int) or not 1 <= position <= total:
                raise ContractError(f"A posição deve ser um número inteiro entre 1 e {total}.")
            reason = (reason or "").strip() if isinstance(reason, str) else ""
            justification = (justification or "").strip() if isinstance(justification, str) else ""
            if not reason:
                raise ContractError("Informe o motivo da mudança.")
            if len(justification) < MIN_JUSTIFICATION:
                raise ContractError(
                    f"A justificativa precisa de pelo menos {MIN_JUSTIFICATION} caracteres."
                )
            current = self.order.index(rid) + 1
            if position == current:
                raise ContractError(f"A solicitação já está na posição {position}.")

            proposed = relocate(self.order, rid, position)
            violation = golden_rule_violation(proposed, self.assessments)
            if violation:
                raise ContractError(self._violation_detail(proposed, *violation), 422)

            name = self._entries[rid]["name"]
            changed = self._commit(proposed, extra={rid})
            self.locked.add(rid)
            record = self.audit.append(
                "manual", self.author, rid, name, current, position, f"{reason}. {justification}",
            )
            self._publish_patch(changed)
            self._publish_audit(record)
            self._activity(
                f"{first_name(self.author)} moveu {first_name(name)} de {current} para {position}",
                record["at"],
            )
            return record

    def validate(self, rid):
        with self._lock:
            self._require(rid)
            position = self.order.index(rid) + 1
            record = self.audit.append(
                "validation", self.author, rid, self._entries[rid]["name"], position, position,
                "Justificativa do Neco revisada e considerada plausível.",
            )
            self._publish_audit(record)
            return record

    def resolve(self, pendency_id, action, note=None):
        with self._lock:
            pendency = self.pendencies.get(pendency_id)
            if pendency is None:
                raise ContractError(f"Pendência {pendency_id} não encontrada.", 404)
            allowed = pendencies.ACTIONS[pendency["kind"]]
            if action not in allowed:
                raise ContractError(
                    f"A ação '{action}' não se aplica a esta pendência. Use: {', '.join(allowed)}."
                )
            note = note.strip() if isinstance(note, str) else ""

            removed = []
            touched = set()
            ids = [rid for rid in pendency["entryIds"] if rid in self.order]
            if action == "remove":
                removed = ids
            elif action == "merge":
                removed = ids[1:]  # entryIds come oldest first: keep the first
            elif pendency["kind"] == "left_queue" and action == "keep":
                touched = self._clear_confirmation(ids)

            del self.pendencies[pendency_id]
            changed = self._commit([rid for rid in self.order if rid not in removed], extra=touched)
            justification = f"{pendency['title']}. {pendencies.OUTCOME[action]}"
            if note:
                justification += f" {note}"
            record = self.audit.append(
                "data", self.author, (pendency["entryIds"] or [pendency_id])[0],
                pendency["name"], None, 0, justification,
            )
            self.hub.publish({"type": "pendency.resolved", "id": pendency_id})
            self._publish_audit(record)
            if changed or removed:
                self._publish_patch(changed, removed)
            if removed:
                self._activity(f"{first_name(pendency['name'])} saiu da fila: {pendencies.OUTCOME[action]}", record["at"])
            return record

    # --- internals -----------------------------------------------------

    def _commit(self, new_order, extra=()):
        """Adopts `new_order`; returns the ids whose entry must be re-sent."""
        before = {rid: i for i, rid in enumerate(self.order, start=1)}
        changed = set(extra)
        for i, rid in enumerate(new_order, start=1):
            old = before.get(rid)
            if old is not None and old != i:
                self.previous[rid] = old
                changed.add(rid)
        self.order = list(new_order)
        return changed

    def _clear_confirmation(self, ids):
        for rid in ids:
            entry = self._entries[rid]
            entry["pendingConfirmation"] = False
            entry["warnings"] = [w for w in entry["warnings"] if w["level"] != "critical"]
        return set(ids)

    def _violation_detail(self, order, oncological, calm):
        onco_entry = self._entries[oncological]
        calm_entry = self._entries[calm]
        return (
            f"Regra de ouro: {onco_entry['name']} tem câncer (CID {onco_entry['cid']}) e ficaria "
            f"na posição {order.index(oncological) + 1}, abaixo de {calm_entry['name']} "
            f"(posição {order.index(calm) + 1}), que não tem urgência clínica."
        )

    def _publish_patch(self, changed, removed=()):
        positions = {rid: i for i, rid in enumerate(self.order, start=1)}
        entries = [self._entry(rid, positions[rid]) for rid in self.order if rid in changed]
        frame = {"type": "queue.patch", "total": len(self.order), "entries": entries}
        if removed:
            frame["removed"] = list(removed)
        self.hub.publish(frame)

    def _publish_audit(self, record):
        self.hub.publish({"type": "audit.appended", "entry": record})

    def _activity(self, text, at=None):
        self.hub.publish({"type": "activity", "at": at or self._clock(), "text": text})

    def _initial_audit(self):
        total = len(self.order)
        mismatched = sum(1 for p in self.pendencies.values() if p["kind"] == "cid_flag")
        counts = {cls: 0 for cls in CLASS_LABEL}
        for a in self.assessments.values():
            counts[a["urgency_class"]] += 1
        classes = ", ".join(f"{n} {cls}" for cls, n in counts.items())
        text = f"{total} solicitações recebidas e priorizadas ({classes})."
        if mismatched:
            text += f" {mismatched} marcações de câncer do cadastro não batiam com o CID; usei o CID."
        self.audit.append("intake", NECO, "LOTE-0001", "Carga inicial", None, total, text)
