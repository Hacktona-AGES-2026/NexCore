"""The queue as the regulation sees it: ranked, mutable, audited, broadcast.

Built once from the read-only repository when the app starts, then changed by
the admin's actions and by ingestion (new requests and clinical events, which
the Neco places and recalculates on its own). State lives in memory (a
decision for the hackathon): restarting the server goes back to the dataset,
the Neco's initial ranking and an empty audit log, ingested rows included. That also means ONE process — two gunicorn workers would hold two
different queues.

Every mutation runs under one lock and publishes its frames before releasing
it, so every socket sees the changes in the order they happened.
"""
import json
from pathlib import Path
import threading

from ..data.reader import strip_accents
from ..prioritization import CLASS_LABEL, assess, golden_rule_violation, place, rank, relocate
from . import ask, corrections, impact, intake, panels, pendencies, serializers
from .audit import AuditLog, utc_now
from .errors import ContractError
from .hub import Hub

ADMIN = "Marina Albuquerque"
NECO = "Neco"
MIN_JUSTIFICATION = 40
MUNICIPALITIES = Path(__file__).with_name("municipalities.json")

#: How the audit and the activity feed name each event type.
EVENT_LABEL = {
    "biopsia": "biópsia",
    "hba1c": "HbA1c",
    "pronto_socorro": "ida ao pronto-socorro",
    "internacao": "internação",
    "exame_imagem": "exame de imagem",
    "consulta_reavaliacao": "reavaliação",
    "contato_telefonico": "contato do call center",
    "falta": "falta",
}


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

        self.repository = repository
        self.places = load_municipalities() if municipalities is None else municipalities
        self.coordinates = {p["name"]: p for p in self.places.values()}
        self.procedures = repository.procedures_by_id
        self.records = {}
        self.events = {}
        self.cities = {}
        self.assessments = {}
        self._entries = {}
        self.confirmed = set()  # left-queue alerts a human dismissed ("the patient wants to stay")
        for record in repository.queue:
            rid = record["solicitacao_id"]
            # Own copies: corrections and ingestion change these, never the repository's rows.
            self.records[rid] = dict(record)
            self.events[rid] = repository.events_for_request(rid)
            self._evaluate(rid)
        self.event_ids = {e["evento_id"] for e in repository.events}
        self.ingested = {"fila": [], "eventos": []}  # source rows, for the verifier

        self.order = rank(self.assessments)
        self.suggested = {}
        self._refresh_suggested()
        self.locked = set()
        self.previous = {}
        self.pendencies = {p["id"]: p for p in pendencies.detect(repository, self.assessments)}
        self._pendency_seq = len(self.pendencies)
        self._impact = None  # (key, report): the verifier is slow, so one run per queue
        self._initial_audit()

    # --- reads ---------------------------------------------------------

    def _entry(self, rid, position):
        entry = dict(self._entries[rid])
        entry["position"] = position
        if rid in self.previous:
            entry["previousPosition"] = self.previous[rid]
        entry["locked"] = rid in self.locked
        entry["suggestedPosition"] = self.suggested.get(rid, position)
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

    def export_csv(self):
        """fila_priorizada.csv of the queue as it stands, manual moves included."""
        with self._lock:
            signals = {rid: self.assessments[rid]["signals"] for rid in self.order}
            return impact.official_csv(self.entries(), signals)

    def impact(self, verify):
        """ImpactReport; `verify(csv_text) -> (ok, output)` runs the official verifier.

        The verifier only sees positions, so its runs are cached by the order and
        run outside the lock: a slow check never holds up the admin's actions.
        """
        with self._lock:
            # an ingested event can change who is calm without moving anyone
            key = (tuple(self.order), len(self.ingested["eventos"]))
            if self._impact and self._impact[0] == key:
                return self._impact[1]
            entries = self.entries()
            neco_csv = self.export_csv()
            manual = impact.manual_order(entries, list(self.records))
            extra = {"fila": list(self.ingested["fila"]), "eventos": list(self.ingested["eventos"])}
        options = {"extra": extra} if any(extra.values()) else {}
        neco_run = impact.verifier_run(*verify(neco_csv, **options))
        manual_run = impact.verifier_run(*verify(impact.manual_csv(entries, manual), **options))
        report = impact.report(entries, manual, neco_run, manual_run)
        with self._lock:
            self._impact = (key, report)
        return report

    def explanation_context(self, rid):
        """What the Neco needs to explain one position (neco_ia.texts.patient_facts)."""
        with self._lock:
            self._require(rid)
            index = self.order.index(rid)
            entries = self.entries()
            return {
                "entry": entries[index],
                "above": entries[index - 1] if index > 0 else None,
                "below": entries[index + 1] if index + 1 < len(entries) else None,
                "audit_records": [r for r in reversed(self.audit.newest_first()) if r["entryId"] == rid],
                "suggested_position": self.suggested.get(rid, index + 1),
                "total": len(entries),
            }

    def chat_snapshot(self):
        """A consistent read of everything the chat's tools may look at."""
        with self._lock:
            entries = self.entries()
            return {
                "entries": entries,
                "summary": panels.summary(entries),
                "equity": panels.equity(entries, self.records, self.coordinates),
                "pendencies": self.pendency_list(),
                "audit": self.audit.newest_first(),
            }

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

    def _plan(self, pendency_id, action, values, note):
        """Validates and applies a resolution on a draft. Raises ContractError."""
        pendency = self.pendencies.get(pendency_id)
        if pendency is None:
            raise ContractError(f"Pendência {pendency_id} não encontrada.", 404)
        try:
            action_def, values = pendencies.validate(pendency, action, values or {}, note)
        except ValueError as exc:
            raise ContractError(str(exc)) from exc
        draft = corrections.Draft(
            self.records, self.events, self.assessments, self.order, self.locked, self.confirmed, self.reference_date,
        )
        facts = corrections.apply(draft, pendency, action, values, self.repository.events_for_request)
        order = draft.reranked()
        violation = golden_rule_violation(order, draft.assessments)
        if violation:
            raise ContractError(self._violation_detail(order, *violation), 422)
        return pendency, action_def, values, draft, order, facts

    def simulate(self, pendency_id, action, values=None):
        """What resolving would change, without changing anything (PendencyPreview).

        The justification is not checked here: the preview comes before writing it.
        """
        with self._lock:
            pendency = self.pendencies.get(pendency_id)
            placeholder = "(prévia)" * 2 if pendency else ""
            pendency, action_def, _, draft, order, _ = self._plan(pendency_id, action, values, placeholder)
            before = {rid: i for i, rid in enumerate(self.order, start=1)}
            after = {rid: i for i, rid in enumerate(order, start=1)}
            ids = list(dict.fromkeys([*pendency["entryIds"], *draft.touched, *draft.removed]))
            changes = []
            for rid in ids:
                if rid not in before:
                    continue
                changes.append({
                    "entryId": rid, "name": self._entries[rid]["name"],
                    "from": before[rid], "to": after.get(rid),
                    "classFrom": self.assessments[rid]["urgency_class"],
                    "classTo": draft.assessments[rid]["urgency_class"],
                })
            return {"action": action, "changes": changes, "summary": self._preview_summary(action_def, changes)}

    @staticmethod
    def _preview_summary(action_def, changes):
        if not changes or not action_def["changesQueue"]:
            return "Nenhuma mudança na fila: só o registro é corrigido."
        parts = []
        for c in changes:
            name = first_name(c["name"])
            if c["to"] is None:
                parts.append(f"{name} sai da fila (estava na {c['from']}ª).")
            elif c["to"] == c["from"] and c["classFrom"] == c["classTo"]:
                parts.append(f"{name} continua na {c['from']}ª.")
            else:
                cls = "" if c["classFrom"] == c["classTo"] else f" e passa de {c['classFrom']} para {c['classTo']}"
                parts.append(f"{name} vai da {c['from']}ª para a {c['to']}ª{cls}.")
        return " ".join(parts)

    def resolve(self, pendency_id, action, note=None, values=None):
        with self._lock:
            note = note.strip() if isinstance(note, str) else ""
            pendency, _, values, draft, order, facts = self._plan(pendency_id, action, values, note)

            self.records, self.events, self.assessments = draft.records, draft.events, draft.assessments
            self.locked, self.confirmed = draft.locked, draft.confirmed
            for rid in draft.touched:
                self._rebuild_entry(rid)
            changed = self._commit(order, extra=draft.touched - set(draft.removed))
            if draft.removed or draft.touched:
                self._refresh_suggested()

            # The pendency, and any other one left with no active request, are settled.
            settled = [pendency_id] + [
                pid for pid, p in self.pendencies.items()
                if pid != pendency_id and p["entryIds"] and not any(rid in self.order for rid in p["entryIds"])
            ]
            for pid in settled:
                del self.pendencies[pid]

            outcome = pendencies.OUTCOME[action].format(**{**values, **facts})
            justification = f"{pendency['title']}. {outcome}"
            if note:
                justification += f" {note}"
            record = self.audit.append(
                "data", self.author, (pendency["entryIds"] or [pendency_id])[0],
                pendency["name"], None, 0, justification,
            )
            for pid in settled:
                self.hub.publish({"type": "pendency.resolved", "id": pid})
            self._publish_audit(record)
            if changed or draft.removed:
                self._publish_patch(changed, draft.removed)
            if draft.removed:
                self._activity(f"{first_name(pendency['name'])} saiu da fila: {outcome}", record["at"])
            elif changed:
                self._activity(f"Correção de dados recalculou a fila ({first_name(pendency['name'])})", record["at"])
            return record

    # --- ingestion -----------------------------------------------------

    def add_entries(self, rows):
        """New requests (fila_cirurgica.csv rows): assessed, placed, audited, pushed.

        The whole batch is checked before anything changes, so a bad row leaves
        the queue as it was. Returns the created QueueEntries.
        """
        with self._lock:
            records = []
            seen = set()
            for n, raw in enumerate(rows, start=1):
                label = f"Linha {n}" if len(rows) > 1 else "Entrada"
                record = intake.queue_record(raw, self.procedures, self.reference_date, label)
                rid = record["solicitacao_id"]
                if rid in self.records or rid in seen:
                    raise ContractError(f"{label}: a solicitação {rid} já existe.", 409)
                seen.add(rid)
                records.append(record)

            created = []
            for record in records:
                rid = record["solicitacao_id"]
                self.records[rid] = record
                self.events[rid] = []
                self._evaluate(rid)
                changed = self._commit(place(self.order, self.assessments, rid), extra={rid})
                self._refresh_suggested()
                position = self.order.index(rid) + 1
                self.ingested["fila"].append(intake.source_row(record, intake.QUEUE_COLUMNS))

                a = self.assessments[rid]
                name = self._entries[rid]["name"]
                audit = self.audit.append(
                    "intake", NECO, rid, name, None, position,
                    f"Nova entrada. Classificada como {CLASS_LABEL[a['urgency_class']]} "
                    f"({a['urgency_class']}): {a['class_reason']}. Entrou na posição {position} "
                    f"de {len(self.order)}." + (
                        " Câncer pelo CID: fica acima de todos os casos sem urgência clínica."
                        if a["oncological"] else ""
                    ),
                )
                self._publish_patch(changed)
                self._publish_audit(audit)
                self._activity(f"Nova entrada: {first_name(name)} na posição {position}", audit["at"])
                same = [
                    self.records[other] for other in self.order
                    if self.records[other].get("paciente_id") == record.get("paciente_id")
                    and self.records[other].get("procedimento_id") == record.get("procedimento_id")
                ]
                if len(same) > 1:  # the new group replaces the one listed for the pair
                    ids = {r["solicitacao_id"] for r in same}
                    for pendency_id, p in list(self.pendencies.items()):
                        if p["kind"] == "duplicate" and set(p["entryIds"]) <= ids:
                            del self.pendencies[pendency_id]
                self._open_pendencies(
                    pendencies.cid_flag(record, a, self.events[rid]),
                    pendencies.duplicate(same) if len(same) > 1 else None,
                )
                created.append(self._entry(rid, position))
            return created

    def add_events(self, rows):
        """Clinical events (eventos_clinicos.csv rows): the request is reassessed.

        It moves only when its class or index changed, and a request a human
        locked stays where it was put. HbA1c is a pre-op criterion: it is
        recorded and audited but never changes the priority. Returns the
        updated QueueEntries, one per row.
        """
        with self._lock:
            events = []
            pending = {}
            for n, raw in enumerate(rows, start=1):
                label = f"Linha {n}" if len(rows) > 1 else "Evento"
                event = intake.event_record(
                    raw,
                    lambda rid: self.records.get(rid) if rid in self.order else None,
                    lambda rid: self.events[rid] + pending.get(rid, []),
                    self.reference_date,
                    label,
                )
                event_id = event["evento_id"]
                if event_id and (event_id in self.event_ids or event_id in {e["evento_id"] for e in events}):
                    raise ContractError(f"{label}: o evento {event_id} já existe.", 409)
                pending.setdefault(event["solicitacao_id"], []).append(event)
                events.append(event)

            updated = []
            for event in events:
                updated.append(self._apply_event(event))
            return updated

    def _apply_event(self, event):
        rid = event["solicitacao_id"]
        if not event["evento_id"]:
            event["evento_id"] = self._next_event_id()
        self.event_ids.add(event["evento_id"])
        self.events[rid].append(event)
        self.events[rid].sort(key=lambda e: e.get("data_evento") or "")
        self.ingested["eventos"].append(intake.source_row(event, intake.EVENT_COLUMNS))

        before = self.assessments[rid]
        kind = event["tipo_evento_norm"]
        if kind == "contato_telefonico" and event["resultado_norm"] in pendencies.LEFT_QUEUE_TITLE:
            self.confirmed.discard(rid)  # new news: the warning comes back
        self._evaluate(rid)
        after = self.assessments[rid]

        origin = self.order.index(rid) + 1
        moves = (
            rid not in self.locked
            and (before["urgency_class"], before["score"]) != (after["urgency_class"], after["score"])
        )
        changed = self._commit(place(self.order, self.assessments, rid) if moves else self.order, extra={rid})
        self._refresh_suggested()
        target = self.order.index(rid) + 1

        name = self._entries[rid]["name"]
        audit = self.audit.append(
            "recalc", NECO, rid, name, origin, target, self._recalc_text(event, before, after, origin, target),
        )
        self._publish_patch(changed)
        self._publish_audit(audit)
        what = EVENT_LABEL[kind]
        if target < origin:
            text = f"{first_name(name)} subiu de {origin} para {target} após {what}"
        elif target > origin:
            text = f"{first_name(name)} desceu de {origin} para {target} após {what}"
        else:
            text = f"{first_name(name)}: {what} registrada, posição {target} mantida"
        self._activity(text, audit["at"])
        record = self.records[rid]
        self._open_pendencies(pendencies.left_queue(event, record), self._new_biopsy_pendency(rid))
        return self._entry(rid, target)

    def _recalc_text(self, event, before, after, origin, target):
        kind = event["tipo_evento_norm"]
        sentence = f"Evento recebido: {EVENT_LABEL[kind]} ({event['resultado_norm']}) em {pendencies.br_date(event['data_evento'])}."
        if kind == "hba1c":
            return f"{sentence} HbA1c é critério de preparo cirúrgico, não de prioridade: posição mantida."
        if before["urgency_class"] != after["urgency_class"]:
            sentence += (
                f" Reclassificado de {CLASS_LABEL[before['urgency_class']]} ({before['urgency_class']}) "
                f"para {CLASS_LABEL[after['urgency_class']]} ({after['urgency_class']}): {after['class_reason']}."
            )
        elif before["score"] != after["score"]:
            sentence += f" Índice de {before['score']:.1f} para {after['score']:.1f}, classe mantida."
        else:
            sentence += " Não muda classe nem índice."
        if after["pending_confirmation"] and not before["pending_confirmation"]:
            sentence += " Posição mantida até confirmação humana: o Neco não retira pacientes da fila."
        elif event["solicitacao_id"] in self.locked and (
            (before["urgency_class"], before["score"]) != (after["urgency_class"], after["score"])
        ):
            sentence += f" Posição {target} mantida: foi fixada pela regulação."
        elif target != origin:
            sentence += f" Posição {origin} → {target}."
        return sentence

    def _next_event_id(self):
        numbers = [int(i[4:]) for i in self.event_ids if i and i.startswith("EVT-") and i[4:].isdigit()]
        return f"EVT-{max(numbers, default=0) + 1:06d}"

    def _new_biopsy_pendency(self, rid):
        open_for = any(p["kind"] == "biopsy" and rid in p["entryIds"] for p in self.pendencies.values())
        return None if open_for else pendencies.biopsy(self.records[rid], self.assessments[rid], self.events[rid])

    def _open_pendencies(self, *found):
        for pendency in found:
            if pendency is None:
                continue
            self._pendency_seq += 1
            pendency_id = f"PEN-{self._pendency_seq:04d}"
            kind_label = pendencies.KIND_LABEL.get(pendency["kind"], pendency["kind"])
            self.pendencies[pendency_id] = {"id": pendency_id, "kindLabel": kind_label, **pendency}
            self._activity(f"Nova pendência: {pendency['title']}")

    # --- internals -----------------------------------------------------

    def _evaluate(self, rid):
        """(Re)assesses one request from its record and events and rebuilds its entry."""
        place_ = self.places.get(strip_accents(self.records[rid].get("municipio_norm")))
        self.cities[rid] = place_["name"] if place_ else None
        self.assessments[rid] = assess(self.records[rid], self.events[rid], self.reference_date)
        self._rebuild_entry(rid)

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

    def _refresh_suggested(self):
        """Where the Neco alone would put each active request, ignoring manual moves."""
        active = {rid: self.assessments[rid] for rid in self.order}
        self.suggested = {rid: i for i, rid in enumerate(rank(active), start=1)}

    def _rebuild_entry(self, rid):
        entry = serializers.queue_entry(self.records[rid], self.assessments[rid], self.events[rid], city=self.cities[rid])
        if rid in self.confirmed:
            entry["pendingConfirmation"] = False
            entry["warnings"] = [w for w in entry["warnings"] if w["level"] != "critical"]
        self._entries[rid] = entry

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
