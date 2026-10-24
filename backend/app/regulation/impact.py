"""The deliverable CSV and the impact panel: the Neco against today's manual queue.

Pure functions over the current queue (the front's QueueEntry dicts, in queue
order). `official_csv` is `GET /fila/exportar`, the challenge's
fila_priorizada.csv as the queue stands now, manual moves included. `report` is
`GET /painel/impacto`; it takes the verifier's output already run, so nothing
here starts a process. The reference implementation is entrega/gerar_entrega.py.
"""
from collections import Counter
import csv
import io
import re

from ..prioritization import CLASS_LABEL, CLASSES, DEADLINE_DAYS
from .serializers import initials

HEADER = ("solicitacao_id", "posicao", "justificativa")
MANUAL_RANK = {"alta": 3, "media": 2, "baixa": 1}
PRIORITIES = ("alta", "media", "baixa", "vazia")
MOVERS = 6
BASELINE = (
    "Fila de hoje: prioridade manual da regulação (alta, média, baixa), "
    "com desempate pelo maior tempo de espera."
)

#: What the panel reads from the verifier's text; None when the line is absent.
INDICATORS = {
    "medianaOnco": re.compile(r"posição mediana dos oncológicos: (\d+)"),
    "oncoPrimeiroTerco": re.compile(r"oncológicos no primeiro terço: (\d+)%"),
    "psPrimeiraMetade": re.compile(r"últimos 180 dias na primeira metade: (\d+)%"),
    "calmosUltimoTerco": re.compile(r"sem urgência clínica no último terço: (\d+)%"),
}
VIOLATIONS = re.compile(r"REGRA DE OURO VIOLADA: (\d+)")


def _br(number):
    return f"{number:g}".replace(".", ",")


def _dpss_text(entry):
    """How the DPSS was composed: DPSS = (T/M) * (1 + c + w*S)."""
    factor = {f["key"]: f["value"] for f in entry["factors"]}
    priority = entry["priority"]
    band = "Faixa protegida (A1/A2 ou câncer), ordenada pelo DPSS. " if priority["protected"] else ""
    if entry["score"] is None:
        return band + "DPSS não calculado: classe SWALIS não inferida com segurança."
    social = priority["socioeconomicVulnerability"]
    return band + (
        f"DPSS {_br(entry['score'])} = espera/prazo {_br(factor['wait'])} × "
        f"(1 + fator clínico {_br(factor['clinical'])} + vulnerabilidade social {_br(factor['social'])}"
        + (f", S={_br(round(social, 3))} com peso {_br(priority['socioeconomicWeight'])}" if social is not None else "")
        + ")."
    )


def _manual_priority(entry):
    return entry.get("manualPriority") or "vazia"


def justification(entry, signals=None):
    """The `justificativa` column, the same text as entrega/neco.py and the front."""
    cls = entry["urgencyClass"]
    deadline = DEADLINE_DAYS[cls]
    days = entry["daysWaiting"] or 0
    late = days - deadline
    parts = [f"Classe {cls} ({CLASS_LABEL[cls]}, SWALIS inferido pelo DPS): {entry['classReason']}."]
    events = []
    if signals:
        if signals["recent_visits"]:
            events.append(f"{signals['recent_visits']} PS/internação em 180 dias")
        if signals["worsening"]:
            events.append(f"{signals['worsening']} relato(s) de piora")
        if signals["progression"]:
            events.append("imagem com progressão")
    if events:
        parts.append("Eventos: " + "; ".join(events) + ".")
    parts.append(
        f"Espera de {days} dias"
        + (f", {late} além do prazo de {deadline}." if late > 0 else f", dentro do prazo de {deadline}.")
    )
    parts.append(_dpss_text(entry))
    parts.extend(w["text"] for w in entry["warnings"])
    if entry.get("locked"):
        parts.append("Posição ajustada manualmente pela regulação; motivo no relatório de auditoria.")
    return " ".join(parts)


def to_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue()


def official_csv(entries, signals=None):
    """fila_priorizada.csv of the queue as it is. `signals` maps id -> rules.signals."""
    signals = signals or {}
    return to_csv(
        (e["id"], e["position"], justification(e, signals.get(e["id"]))) for e in entries
    )


def manual_order(entries, dataset_order):
    """Today's queue: manual priority, then the longest wait; ties in dataset order."""
    by_id = {e["id"]: e for e in entries}
    ids = [rid for rid in dataset_order if rid in by_id]
    ids.sort(key=lambda rid: (
        -MANUAL_RANK.get(by_id[rid].get("manualPriority"), 0), -(by_id[rid]["daysWaiting"] or 0),
    ))
    return ids


def manual_csv(entries, order):
    by_id = {e["id"]: e for e in entries}
    return to_csv(
        (rid, position, f"Prioridade manual: {_manual_priority(by_id[rid])}; "
                        f"{by_id[rid]['daysWaiting']} dias em fila.")
        for position, rid in enumerate(order, start=1)
    )


def verifier_run(ok, output):
    """The verifier's exit and text -> the front's VerifierRun."""
    found = VIOLATIONS.search(output)
    run = {"ok": ok, "output": output, "violacoes": int(found.group(1)) if found else 0}
    for key, pattern in INDICATORS.items():
        match = pattern.search(output)
        run[key] = int(match.group(1)) if match else None
    return run


def report(entries, manual, neco_run, manual_run):
    """ImpactReport. `manual` is manual_order(); the runs come from verifier_run()."""
    manual_position = {rid: i for i, rid in enumerate(manual, start=1)}
    matrix = Counter((e["urgencyClass"], _manual_priority(e)) for e in entries)
    by_class = Counter(e["urgencyClass"] for e in entries)
    urgent = [e for e in entries if e["urgencyClass"] in ("A1", "A2")]
    movers = sorted(entries, key=lambda e: e["position"] - manual_position[e["id"]])[:MOVERS]
    return {
        "source": "backend",
        "total": len(entries),
        "baseline": BASELINE,
        "verifier": {"neco": neco_run, "manual": manual_run},
        "matrix": [{"cls": cls, **{p: matrix[(cls, p)] for p in PRIORITIES}} for cls in CLASSES],
        "headline": {
            "a1Total": by_class["A1"],
            "a1Low": matrix[("A1", "baixa")] + matrix[("A1", "vazia")],
            "urgentTotal": len(urgent),
            "urgentLow": sum(1 for e in urgent if _manual_priority(e) in ("baixa", "vazia")),
            "dTotal": by_class["D"],
            "dHigh": matrix[("D", "alta")],
        },
        "movers": [
            {
                "id": e["id"],
                "initials": initials(e["name"]),
                "procedure": e["procedure"],
                "cls": e["urgencyClass"],
                "reason": e["classReason"],
                "manualPriority": _manual_priority(e),
                "manualPosition": manual_position[e["id"]],
                "necoPosition": e["position"],
            }
            for e in movers
        ],
    }
