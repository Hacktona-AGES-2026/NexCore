"""Data problems a human has to settle (docs/CONTRATO_BACKEND.md §7).

The Neco already works around each one in the calculation — oncology comes from
the CID, duplicates are ranked separately — but fixing the record is a human
decision, so they are listed, never silently corrected.

Every pendency has the same shape, whatever its kind, so one correction panel
in the front renders all of them, including kinds that do not exist yet:

- `divergences`: which piece of data disagrees and what each source says;
- `evidence`: what the regulator should read before deciding;
- `actions`: what can be done, each with the fields it asks for;
- `suggestion`: the action the Neco would pick, and why;
- `risk`: "alto" when the problem may be hiding a serious patient.

A new detector only has to yield this shape; the corrections it can apply live
in `corrections.py`.
"""
from collections import OrderedDict
import re

from ..prioritization.rules import LEFT_QUEUE, clinical_events

KIND_LABEL = {
    "cid_flag": "Câncer divergente",
    "biopsy": "Biópsia × CID",
    "duplicate": "Duplicata",
    "left_queue": "Saída da fila",
    "orphan_event": "Evento órfão",
}
RISK_ORDER = {"alto": 0, "medio": 1, "baixo": 2}
CID_PATTERN = r"^[A-Za-z][0-9]{2}(\.?[0-9]{1,2})?$"

#: The audit text of each action; `{...}` are filled from the values sent.
OUTCOME = {
    "fix_cadastro": "Cadastro corrigido para bater com o CID.",
    "update_cid": "CID corrigido de {before} para {cid}.",
    "keep": "Conferido e mantido como está.",
    "unrelated": "Biópsia desconsiderada para esta solicitação.",
    "merge": "Solicitações duplicadas mescladas; mantida a {kept}.",
    "keep_both": "Conferido: são solicitações distintas.",
    "remove": "Saída da fila confirmada ({confirmacao}).",
    "link": "Evento vinculado à solicitação {target}.",
    "archive": "Evento arquivado: solicitação não está na fila.",
}

CONFIRMATIONS = [
    {"value": "ligacao", "label": "Ligação com o paciente"},
    {"value": "familiar", "label": "Ligação com familiar"},
    {"value": "documento", "label": "Documento do outro serviço"},
    {"value": "presencial", "label": "Paciente informou pessoalmente"},
]

LEFT_QUEUE_TITLE = {
    "desistiu": "Paciente desistiu",
    "informou_cirurgia_outro_servico": "Operou em outro serviço",
}

#: Malignant CID the procedure usually means, to pre-fill a correction.
CID_BY_PROCEDURE = (
    ("mama", "C50.9"), ("colectomia", "C18.9"), ("gastrectomia", "C16.9"), ("prostatectomia", "C61"),
    ("histerectomia", "C54.1"), ("tireoidectomia", "C73"), ("lobectomia", "C34.9"), ("pele", "C44.9"),
)


def br_date(iso):
    return "/".join(reversed(str(iso).split("-"))) if iso else "?"


def _sentence(text):
    text = (text or "").strip()
    return text if not text or text.endswith(".") else text + "."


def _cid_label(record):
    return f"{record.get('cid_principal')} · {record.get('cid_descricao') or 'sem descrição'}"


def suggested_cid(record):
    procedure = (record.get("procedimento") or "").lower()
    return next((cid for key, cid in CID_BY_PROCEDURE if key in procedure), "")


def _note_evidence(record):
    items = [{"label": "Justificativa do médico", "text": record.get("justificativa_clinica") or "—"}]
    if record.get("observacoes"):
        items.append({"label": "Observações da regulação", "text": record["observacoes"]})
    return items


def _event_evidence(event, label=None):
    kind = (event.get("tipo_evento_norm") or "").replace("_", " ")
    result = (event.get("resultado_norm") or "").replace("_", " ")
    return {
        "label": label or f"{kind.capitalize()} · {result}",
        "date": event.get("data_evento"),
        "text": _sentence(event.get("descricao")) or "—",
    }


# --- actions -----------------------------------------------------------------

def _action(action_id, label, description, fields=(), justification=False, danger=False, changes_queue=False):
    return {
        "id": action_id, "label": label, "description": description, "fields": list(fields),
        "requiresJustification": justification, "danger": danger, "changesQueue": changes_queue,
    }


def _cid_field(record):
    return {
        "name": "cid", "label": "CID correto", "type": "text", "required": True,
        "suggested": suggested_cid(record), "pattern": CID_PATTERN,
        "help": "Ex.: C50.9. O Neco recalcula a classe com o CID novo.",
    }


def _update_cid(record):
    return _action(
        "update_cid", "Corrigir o CID", "O CID do pedido está errado; informe o correto e o Neco recalcula.",
        fields=[_cid_field(record)], justification=True, changes_queue=True,
    )


# --- detectors ---------------------------------------------------------------

def _cid_flag(repository, assessments):
    for r in repository.queue:
        flag = r.get("flag_oncologico_norm")
        oncological = bool(r.get("oncologico_cid"))
        if flag is None or bool(flag) == oncological:
            continue
        rid = r["solicitacao_id"]
        evidence = _note_evidence(r) + [
            _event_evidence(e, "Biópsia · " + (e.get("resultado_norm") or ""))
            for e in clinical_events(repository.events_for_request(rid)) if e.get("tipo_evento_norm") == "biopsia"
        ]
        cancer_in_text = any(h["kind"] == "urgency" for h in assessments[rid]["highlights"])
        biopsy = assessments[rid]["signals"]["positive_biopsy"]
        if oncological:
            risk, why = "baixo", "O Neco já usa o CID; só o cadastro está desatualizado."
            suggestion = {"actionId": "fix_cadastro", "reason": "O CID é de neoplasia maligna; o cadastro deve acompanhar."}
        else:
            risk, why = "alto", "Se o cadastro estiver certo, há um câncer escondido por um CID benigno."
            suggestion = (
                {"actionId": "update_cid", "reason": "O texto do médico ou uma biópsia indicam câncer; o CID parece errado."}
                if cancer_in_text or biopsy else
                {"actionId": "fix_cadastro", "reason": "Nada no texto nem nos eventos indica câncer; o cadastro parece errado."}
            )
        yield {
            "kind": "cid_flag",
            "title": f"Cadastro diz {'sem câncer' if oncological else 'câncer'}, CID {r.get('cid_principal')} diz o contrário",
            "detail": f"{_sentence(r.get('cid_descricao'))} O Neco já usa o CID; falta corrigir o cadastro.",
            "name": r.get("nome_paciente"),
            "entryIds": [rid],
            "risk": risk, "riskReason": why,
            "divergences": [{
                "field": "oncologia", "label": "Câncer",
                "values": [
                    {"source": "CID principal", "value": f"{_cid_label(r)} ({'câncer' if oncological else 'não é câncer'})"},
                    {"source": "Marcação do cadastro", "value": "câncer" if flag else "sem câncer"},
                ],
            }],
            "evidence": evidence,
            "actions": [
                _action("fix_cadastro", "O CID está certo", "Corrige a marcação do cadastro para acompanhar o CID. A fila não muda."),
                _update_cid(r),
            ],
            "suggestion": suggestion,
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
        options = [
            {"value": r["solicitacao_id"], "label": f"{r['solicitacao_id']} · entrada {br_date(r.get('data_entrada_fila'))}"
             + (" (mais antiga)" if i == 0 else "")}
            for i, r in enumerate(records)
        ]
        yield {
            "kind": "duplicate",
            "title": f"{len(records)} solicitações para o mesmo procedimento",
            "detail": f"{records[0].get('procedimento')}. Entradas em {listed}.",
            "name": records[0].get("nome_paciente"),
            "entryIds": [r["solicitacao_id"] for r in records],
            "risk": "medio", "riskReason": "A mesma pessoa pode estar ocupando duas vagas na fila.",
            "divergences": [{
                "field": "solicitacao", "label": records[0].get("procedimento") or "Procedimento",
                "values": [
                    {"source": r["solicitacao_id"], "value": f"entrada {br_date(r.get('data_entrada_fila'))} · CID {r.get('cid_principal')}"}
                    for r in records
                ],
            }],
            "evidence": [
                {"label": f"Justificativa · {r['solicitacao_id']}", "text": r.get("justificativa_clinica") or "—"} for r in records
            ],
            "actions": [
                _action(
                    "merge", "Mesclar", "Mantém uma solicitação, junta os eventos e tira as outras da fila.",
                    fields=[{"name": "keep", "label": "Manter", "type": "select", "required": True,
                             "options": options, "suggested": records[0]["solicitacao_id"],
                             "help": "Manter a mais antiga preserva o tempo de espera do paciente."}],
                    changes_queue=True,
                ),
                _action("keep_both", "São distintas", "Por exemplo, um procedimento de cada lado. As duas continuam na fila.",
                        justification=True),
            ],
            "suggestion": {"actionId": "merge", "reason": "Mesmo paciente e mesmo procedimento: mantenha a entrada mais antiga."},
        }


def _biopsy(repository, assessments):
    for r in repository.queue:
        rid = r["solicitacao_id"]
        a = assessments[rid]
        if a["oncological"] or not a["signals"]["positive_biopsy"]:
            continue
        biopsies = [e for e in clinical_events(repository.events_for_request(rid))
                    if e.get("tipo_evento_norm") == "biopsia" and e.get("resultado_norm") == "positivo"]
        last = biopsies[-1] if biopsies else {}
        yield {
            "kind": "biopsy",
            "title": f"Biópsia positiva, mas o CID {r.get('cid_principal')} não é de câncer",
            "detail": "O Neco já trata como câncer (classe A2). Confirme e atualize o CID.",
            "name": r.get("nome_paciente"),
            "entryIds": [rid],
            "risk": "alto", "riskReason": "Sem o CID de câncer, a regra de ouro não protege este paciente pelo diagnóstico.",
            "divergences": [{
                "field": "cid", "label": "Diagnóstico",
                "values": [
                    {"source": "CID principal", "value": _cid_label(r)},
                    {"source": f"Biópsia de {br_date(last.get('data_evento'))}", "value": f"positiva · {_sentence(last.get('descricao'))}"},
                ],
            }],
            "evidence": [_event_evidence(e, "Biópsia positiva") for e in biopsies] + _note_evidence(r),
            "actions": [
                _update_cid(r),
                _action("keep", "Manter como está", "O Neco continua tratando como câncer (A2) pela biópsia."),
                _action("unrelated", "A biópsia não é deste pedido",
                        "Desconsidera a biópsia nesta solicitação; o paciente perde a classe A2 e o Neco recalcula.",
                        justification=True, danger=True, changes_queue=True),
            ],
            "suggestion": {"actionId": "update_cid", "reason": "A biópsia confirma malignidade; o CID deve refletir o diagnóstico."},
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
            "risk": "medio", "riskReason": "Confirmar a saída libera uma vaga para quem está esperando.",
            "divergences": [{
                "field": "situacao", "label": "Situação do paciente",
                "values": [
                    {"source": "Fila", "value": "ativo, aguardando cirurgia"},
                    {"source": f"Call center em {br_date(event.get('data_evento'))}", "value": LEFT_QUEUE_TITLE[result].lower()},
                ],
            }],
            "evidence": [_event_evidence(event, "Contato telefônico")] + _note_evidence(record),
            "actions": [
                _action("remove", "Confirmar a saída", "Retira o paciente da fila. Só confirme depois de falar com ele ou ver um documento.",
                        fields=[{"name": "confirmacao", "label": "Como foi confirmado", "type": "select", "required": True,
                                 "options": CONFIRMATIONS}],
                        danger=True, changes_queue=True),
                _action("keep", "Paciente quer continuar", "O paciente confirmou que ainda quer operar; o alerta sai."),
            ],
            "suggestion": {"actionId": None, "reason": "Confirme com o paciente antes de decidir: a informação veio de um contato telefônico."},
        }


def _orphans(repository):
    active = OrderedDict()
    for r in repository.queue:
        active.setdefault(r.get("paciente_id"), []).append(r)
    for event in clinical_events(repository.events):
        if event.get("solicitacao_na_fila") is not False:
            continue
        candidates = active.get(event.get("paciente_id"), [])
        alarming = (event.get("tipo_evento_norm") in ("pronto_socorro", "internacao")
                    or (event.get("tipo_evento_norm"), event.get("resultado_norm")) in
                    {("biopsia", "positivo"), ("exame_imagem", "progressao"), ("consulta_reavaliacao", "piora")})
        actions = []
        if candidates:
            actions.append(_action(
                "link", "Vincular a outra solicitação", "O evento passa a contar para a solicitação escolhida, e o Neco recalcula.",
                fields=[{"name": "target", "label": "Solicitação ativa do paciente", "type": "select", "required": True,
                         "options": [{"value": c["solicitacao_id"], "label": f"{c['solicitacao_id']} · {c.get('procedimento')}"}
                                     for c in candidates],
                         "suggested": candidates[0]["solicitacao_id"]}],
                justification=True, changes_queue=True,
            ))
        actions.append(_action("archive", "Arquivar", "O evento não se refere a nenhuma solicitação ativa."))
        yield {
            "kind": "orphan_event",
            "title": f"Evento para a solicitação {event.get('solicitacao_id')}, que não está na fila",
            "detail": (
                f"{(event.get('tipo_evento_norm') or event.get('tipo_evento') or '').replace('_', ' ')} em "
                f"{br_date(event.get('data_evento'))}: {_sentence(event.get('descricao'))}"
            ),
            "name": event.get("paciente_id"),
            "entryIds": [],
            "eventId": event.get("evento_id"),
            "eventRequestId": event.get("solicitacao_id"),
            "risk": "alto" if alarming and candidates else "baixo",
            "riskReason": ("Evento clínico importante que pode mudar a prioridade de outra solicitação do paciente."
                           if alarming and candidates else "Evento sem efeito em nenhuma solicitação ativa."),
            "divergences": [{
                "field": "vinculo", "label": "Vínculo do evento",
                "values": [
                    {"source": f"Evento de {br_date(event.get('data_evento'))}", "value": f"aponta para {event.get('solicitacao_id')}"},
                    {"source": "Fila", "value": f"{event.get('solicitacao_id')} não está ativa"
                     + (f"; o paciente tem {len(candidates)} solicitação(ões) ativa(s)" if candidates else "")},
                ],
            }],
            "evidence": [_event_evidence(event)],
            "actions": actions,
            "suggestion": (
                {"actionId": "link", "reason": "É um evento clínico importante e o paciente tem outra solicitação ativa."}
                if alarming and candidates else {"actionId": "archive", "reason": "O evento não muda a prioridade de nenhuma solicitação."}
            ),
        }


def detect(repository, assessments):
    """Every pendency, numbered PEN-0001… in the order the kinds are listed."""
    found = [
        *_cid_flag(repository, assessments),
        *_duplicates(repository),
        *_biopsy(repository, assessments),
        *_left_queue(repository),
        *_orphans(repository),
    ]
    return [{"id": f"PEN-{n:04d}", "kindLabel": KIND_LABEL.get(p["kind"], p["kind"]), **p} for n, p in enumerate(found, start=1)]


def validate(pendency, action_id, values, note):
    """(action, values) after checking the action applies and its fields are filled.

    A field left empty takes its `suggested` value (merging keeps the oldest
    entry by default). Raises ValueError with a Portuguese message.
    """
    action = next((a for a in pendency["actions"] if a["id"] == action_id), None)
    if action is None:
        allowed = ", ".join(a["id"] for a in pendency["actions"])
        raise ValueError(f"A ação '{action_id}' não se aplica a esta pendência. Use: {allowed}.")
    resolved = {}
    for field in action["fields"]:
        value = str(values.get(field["name"]) or field.get("suggested") or "").strip()
        resolved[field["name"]] = value
        if field.get("required") and not value:
            raise ValueError(f"Preencha o campo '{field['label']}'.")
        if value and field["type"] == "select" and value not in {o["value"] for o in field["options"]}:
            raise ValueError(f"Valor inválido para '{field['label']}'.")
        if value and field.get("pattern") and not re.match(field["pattern"], value):
            raise ValueError(f"'{value}' não parece um CID válido (ex.: C50.9).")
    if action["requiresJustification"] and len((note or "").strip()) < 10:
        raise ValueError("Escreva uma justificativa de pelo menos 10 caracteres.")
    return action, resolved
