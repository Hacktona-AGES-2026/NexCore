"""Data problems a human has to settle (docs/CONTRATO_BACKEND.md §7).

The Neco already works around each one in the calculation — oncology comes from
the CID, duplicates are ranked separately — but fixing the record is a human
decision, so they are listed, never silently corrected.
"""
from collections import OrderedDict

from ..prioritization.rules import LEFT_QUEUE, clinical_events

#: Kind -> the actions `/resolver` accepts, in the order the front shows them.
ACTIONS = {
    "cid_flag": ("fix_cadastro",),
    "duplicate": ("merge", "keep_both"),
    "biopsy": ("update_cid", "keep"),
    "left_queue": ("remove", "keep"),
    "orphan_event": ("archive",),
}

#: What each action records in the audit log.
OUTCOME = {
    "fix_cadastro": "Cadastro corrigido para bater com o CID.",
    "update_cid": "CID atualizado após conferir a biópsia.",
    "keep": "Conferido e mantido como está.",
    "merge": "Solicitações duplicadas mescladas; mantida a entrada mais antiga.",
    "keep_both": "Conferido: são solicitações distintas.",
    "remove": "Saída da fila confirmada com o paciente.",
    "archive": "Evento arquivado: solicitação não está na fila.",
}

LEFT_QUEUE_TITLE = {
    "desistiu": "Paciente desistiu",
    "informou_cirurgia_outro_servico": "Operou em outro serviço",
}


def br_date(iso):
    return "/".join(reversed(iso.split("-"))) if iso else "?"


def _sentence(text):
    text = (text or "").strip()
    return text if not text or text.endswith(".") else text + "."


def _cid_flag(repository):
    for r in repository.queue:
        flag = r.get("flag_oncologico_norm")
        oncological = bool(r.get("oncologico_cid"))
        if flag is None or bool(flag) == oncological:
            continue
        side = "sem câncer" if oncological else "câncer"
        yield {
            "kind": "cid_flag",
            "title": f"Cadastro diz {side}, CID {r.get('cid_principal')} diz o contrário",
            "detail": f"{_sentence(r.get('cid_descricao'))} O Neco já usa o CID; falta corrigir o cadastro.",
            "name": r.get("nome_paciente"),
            "entryIds": [r["solicitacao_id"]],
        }


def _duplicates(repository):
    groups = OrderedDict()
    for r in repository.queue:
        groups.setdefault((r.get("paciente_id"), r.get("procedimento_id")), []).append(r)
    for records in groups.values():
        if len(records) < 2:
            continue
        records = sorted(records, key=lambda r: (r.get("data_entrada_fila") or "", r["solicitacao_id"]))
        dates = [br_date(r.get("data_entrada_fila")) for r in records]
        listed = ", ".join(dates[:-1]) + " e " + dates[-1]
        yield {
            "kind": "duplicate",
            "title": f"{len(records)} solicitações para o mesmo procedimento",
            "detail": f"{records[0].get('procedimento')}. Entradas em {listed}.",
            "name": records[0].get("nome_paciente"),
            "entryIds": [r["solicitacao_id"] for r in records],
        }


def _biopsy(repository, assessments):
    for r in repository.queue:
        a = assessments[r["solicitacao_id"]]
        if a["oncological"] or not a["signals"]["positive_biopsy"]:
            continue
        yield {
            "kind": "biopsy",
            "title": f"Biópsia positiva, mas o CID {r.get('cid_principal')} não é de câncer",
            "detail": "O Neco já trata como câncer (classe A2). Confirme e atualize o CID.",
            "name": r.get("nome_paciente"),
            "entryIds": [r["solicitacao_id"]],
        }


def _left_queue(repository):
    """One per call-center contact reporting the patient left, in event order."""
    for event in clinical_events(repository.events):
        result = event.get("resultado_norm")
        if event.get("tipo_evento_norm") != "contato_telefonico" or result not in LEFT_QUEUE:
            continue
        record = repository.get_request(event.get("solicitacao_id"))
        if record is None:
            continue
        yield {
            "kind": "left_queue",
            "title": LEFT_QUEUE_TITLE[result],
            "detail": f"Call center em {br_date(event.get('data_evento'))}: {_sentence(event.get('descricao'))}",
            "name": record.get("nome_paciente"),
            "entryIds": [record["solicitacao_id"]],
        }


def _orphans(repository):
    for event in clinical_events(repository.events):
        if event.get("solicitacao_na_fila") is not False:
            continue
        yield {
            "kind": "orphan_event",
            "title": f"Evento para a solicitação {event.get('solicitacao_id')}, que não está na fila",
            "detail": (
                f"{(event.get('tipo_evento_norm') or event.get('tipo_evento') or '').replace('_', ' ')} em "
                f"{br_date(event.get('data_evento'))}: {_sentence(event.get('descricao'))}"
            ),
            "name": event.get("paciente_id"),
            "entryIds": [],
        }


def detect(repository, assessments):
    """Every pendency, numbered PEN-0001… in the order the kinds are listed."""
    found = [
        *_cid_flag(repository),
        *_duplicates(repository),
        *_biopsy(repository, assessments),
        *_left_queue(repository),
        *_orphans(repository),
    ]
    return [{"id": f"PEN-{n:04d}", **p} for n, p in enumerate(found, start=1)]
