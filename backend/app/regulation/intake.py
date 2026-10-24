"""Ingestion: one row of the dataset's source CSVs in, a normalized record out.

`POST /fila/entradas` takes a row of fila_cirurgica.csv and `POST /fila/eventos`
a row of eventos_clinicos.csv, as JSON with the same Portuguese columns
(backend/dataset/dicionario_dados.md). Here they are checked against the
dictionary's domains and turned into what the repository would have read from
normalizado/: the same `*_norm` columns, derived the way normalizar_dataset.py
derives them, and the same types reader.py converts to. Nothing is imputed: an
optional field left out is null.

Pure functions, no Flask: a bad row raises ContractError with every problem of
the row in one Portuguese sentence, because the caller is a person or a system
that wants to fix it all at once.
"""
from datetime import date

from ..data.reader import to_bool
from .errors import ContractError

QUEUE_COLUMNS = (
    "solicitacao_id", "paciente_id", "nome_paciente", "sexo", "idade", "municipio",
    "uf", "distancia_hospital_km", "procedimento_id", "procedimento", "especialidade",
    "cid_principal", "cid_descricao", "cid_secundario", "asa", "comorbidades",
    "intensidade_dor_eva", "limitacao_funcional", "justificativa_clinica",
    "observacoes", "data_entrada_fila", "dias_em_fila", "prioridade_regulacao",
    "data_ultima_revisao_prioridade", "flag_oncologico", "flag_diabetico",
    "flag_piora_clinica", "hba1c_ultima", "data_hba1c_ultima",
    "avaliacao_pre_anestesica", "exames_pre_op_validos",
)
EVENT_COLUMNS = (
    "evento_id", "solicitacao_id", "paciente_id", "data_evento", "tipo_evento",
    "resultado", "valor_numerico", "descricao", "origem",
)
#: Computed by the server; accepted in the body only so a CSV row can go as is.
DERIVED = {"procedimento", "especialidade", "dias_em_fila"}

REQUIRED_QUEUE = (
    "solicitacao_id", "paciente_id", "nome_paciente", "sexo", "idade", "municipio",
    "uf", "procedimento_id", "cid_principal", "justificativa_clinica", "data_entrada_fila",
)
REQUIRED_EVENT = ("solicitacao_id", "paciente_id", "data_evento", "tipo_evento", "resultado")

SEX = ("f", "m")
LIMITATION = ("nenhuma", "leve", "moderada", "grave")
PRIORITY = {"alta": "alta", "media": "media", "média": "media", "baixa": "baixa"}
PRE_ANESTHETIC = ("realizada", "pendente", "vencida")
YES_NO = ("flag_oncologico", "flag_diabetico", "flag_piora_clinica", "exames_pre_op_validos")

EVENT_RESULTS = {
    "biopsia": ("positivo", "negativo", "inconclusivo"),
    "hba1c": ("resultado",),
    "pronto_socorro": ("atendido_liberado", "observacao"),
    "internacao": ("alta",),
    "exame_imagem": ("estavel", "progressao"),
    "consulta_reavaliacao": ("piora", "estavel", "melhora"),
    "contato_telefonico": (
        "atendeu", "nao_atendeu", "relata_piora", "relata_melhora",
        "informou_cirurgia_outro_servico", "desistiu",
    ),
    "falta": ("consulta", "exame", "avaliacao_pre_anestesica"),
}
#: Event types whose `valor_numerico` means something (HbA1c %, days in hospital).
VALUED = {"hba1c": True, "internacao": False}  # type -> required


def rows(body):
    """The body as a list of rows: one object or a list of them (a batch)."""
    if isinstance(body, dict):
        return [body], False
    if isinstance(body, list) and body and all(isinstance(r, dict) for r in body):
        return body, True
    raise ContractError("Envie uma linha (objeto JSON) ou um lote (lista de objetos).")


class _Row:
    """Reads one row's fields, collecting problems instead of stopping at the first."""

    def __init__(self, raw, columns):
        self.raw = raw
        self.problems = []
        unknown = sorted(set(raw) - set(columns))
        if unknown:
            self.problems.append(f"campos desconhecidos: {', '.join(unknown)}")

    def _blank(self, key):
        value = self.raw.get(key)
        return value is None or (isinstance(value, str) and not value.strip())

    def text(self, key, required=False):
        if self._blank(key):
            if required:
                self.problems.append(f"'{key}' é obrigatório")
            return None
        value = self.raw[key]
        if not isinstance(value, str):
            self.problems.append(f"'{key}' deve ser texto")
            return None
        return value.strip()

    def choice(self, key, allowed, required=False):
        value = self.text(key, required)
        if value is None:
            return None
        folded = value.casefold()
        options = allowed if isinstance(allowed, dict) else {a: a for a in allowed}
        if folded not in options:
            self.problems.append(f"'{key}' deve ser um de: {', '.join(dict.fromkeys(options.values()))}")
            return None
        return options[folded]

    def integer(self, key, low, high, required=False):
        if self._blank(key):
            if required:
                self.problems.append(f"'{key}' é obrigatório")
            return None
        value = self.raw[key]
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            self.problems.append(f"'{key}' deve ser um número inteiro entre {low} e {high}")
            return None
        return value

    def number(self, key, required=False):
        if self._blank(key):
            if required:
                self.problems.append(f"'{key}' é obrigatório")
            return None
        value = self.raw[key]
        if isinstance(value, str):
            try:
                value = float(value.strip().replace(",", "."))
            except ValueError:
                value = None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            self.problems.append(f"'{key}' deve ser um número não negativo")
            return None
        return float(value)

    def day(self, key, latest, required=False):
        value = self.text(key, required)
        if value is None:
            return None
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            self.problems.append(f"'{key}' deve ser uma data AAAA-MM-DD")
            return None
        if parsed.isoformat() > latest:
            self.problems.append(f"'{key}' não pode ser posterior à data de referência ({latest})")
            return None
        return parsed.isoformat()

    def yes_no(self, key):
        if self._blank(key):
            return None
        value = self.raw[key]
        if isinstance(value, bool):
            return value
        parsed = to_bool(value) if isinstance(value, str) else None
        if parsed is None:
            self.problems.append(f"'{key}' deve ser sim ou nao")
        return parsed

    def original(self, key):
        """The cell as sent, trimmed: the source column keeps its spelling."""
        value = self.raw.get(key)
        if isinstance(value, bool):
            return "sim" if value else "nao"
        if value is None or isinstance(value, (dict, list)):
            return None
        return str(value).strip() or None

    def check(self, label):
        if self.problems:
            raise ContractError(f"{label}: {'; '.join(self.problems)}.")


def _cid(value):
    return value.upper().replace(".", "").replace(" ", "") if value else None


def queue_record(raw, procedures, reference_date, label="Entrada"):
    """A fila_cirurgica.csv row -> the record reader.py would have produced.

    `procedures` maps procedimento_id -> catalog row: procedimento and
    especialidade come from it, and dias_em_fila from `reference_date`, never
    from the body (they would contradict the catalog or the reference date).
    """
    row = _Row(raw, QUEUE_COLUMNS)
    rid = row.text("solicitacao_id", True)
    patient = row.text("paciente_id", True)
    name = row.text("nome_paciente", True)
    sex = row.choice("sexo", SEX, True)
    age = row.integer("idade", 0, 120, True)
    city = row.text("municipio", True)
    uf = row.text("uf", True)
    distance = row.integer("distancia_hospital_km", 0, 5000)
    procedure_id = row.text("procedimento_id", True)
    cid = row.text("cid_principal", True)
    cid_description = row.text("cid_descricao")
    cid_secondary = row.text("cid_secundario")
    asa = row.integer("asa", 1, 6)
    comorbidities = row.text("comorbidades")
    pain = row.integer("intensidade_dor_eva", 0, 10)
    limitation = row.choice("limitacao_funcional", LIMITATION)
    note = row.text("justificativa_clinica", True)
    remarks = row.text("observacoes")
    entered = row.day("data_entrada_fila", reference_date, True)
    priority = row.choice("prioridade_regulacao", PRIORITY)
    reviewed = row.day("data_ultima_revisao_prioridade", reference_date)
    flags = {key: row.yes_no(key) for key in YES_NO}
    hba1c = row.number("hba1c_ultima")
    hba1c_date = row.day("data_hba1c_ultima", reference_date)
    pre_anesthetic = row.choice("avaliacao_pre_anestesica", PRE_ANESTHETIC)

    procedure = procedures.get(procedure_id) if procedure_id else None
    if procedure_id and procedure is None:
        row.problems.append(f"procedimento '{procedure_id}' não está no catálogo")
    row.check(f"{label} {rid}" if rid else label)

    days = (date.fromisoformat(reference_date) - date.fromisoformat(entered)).days
    cid_norm = _cid(cid)
    return {
        "solicitacao_id": rid,
        "paciente_id": patient,
        "nome_paciente": name,
        "sexo": row.original("sexo"),
        "idade": age,
        "municipio": city,
        "uf": uf.upper(),
        "distancia_hospital_km": distance,
        "procedimento_id": procedure_id,
        "procedimento": procedure.get("procedimento"),
        "especialidade": procedure.get("especialidade"),
        "cid_principal": cid,
        "cid_descricao": cid_description,
        "cid_secundario": cid_secondary,
        "asa": asa,
        "comorbidades": comorbidities,
        "intensidade_dor_eva": pain,
        "limitacao_funcional": row.original("limitacao_funcional"),
        "justificativa_clinica": note,
        "observacoes": remarks,
        "data_entrada_fila": entered,
        "dias_em_fila": days,
        "prioridade_regulacao": row.original("prioridade_regulacao"),
        "data_ultima_revisao_prioridade": reviewed or entered,
        **{key: row.original(key) for key in YES_NO},
        "hba1c_ultima": hba1c,
        "data_hba1c_ultima": hba1c_date,
        "avaliacao_pre_anestesica": row.original("avaliacao_pre_anestesica"),
        # the normalizer's derived columns, as reader.py types them
        "cid_principal_norm": cid_norm,
        "cid_secundario_norm": _cid(cid_secondary),
        "oncologico_cid": cid_norm.startswith("C"),
        "municipio_norm": city.casefold().title(),
        "prioridade_regulacao_norm": priority,
        "flag_oncologico_norm": flags["flag_oncologico"],
        "flag_diabetico_norm": flags["flag_diabetico"],
        "flag_piora_clinica_norm": flags["flag_piora_clinica"],
        "avaliacao_pre_anestesica_norm": pre_anesthetic,
        "exames_pre_op_validos_norm": flags["exames_pre_op_validos"],
        "limitacao_funcional_norm": limitation,
        "sexo_norm": sex,
    }


def event_record(raw, queue_record_of, events_of, reference_date, label="Evento"):
    """An eventos_clinicos.csv row -> the record reader.py would have produced.

    `queue_record_of(rid)` returns the request's record or None when it is not
    in the queue: an event for it is refused (404) instead of becoming another
    orphan. `events_of(rid)` lists the request's events so far, for the
    normalizer's content-duplicate mark. `evento_id` may be left out; the caller numbers it.
    """
    row = _Row(raw, EVENT_COLUMNS)
    event_id = row.text("evento_id")
    rid = row.text("solicitacao_id", True)
    patient = row.text("paciente_id", True)
    when = row.day("data_evento", reference_date, True)
    kind = row.choice("tipo_evento", tuple(EVENT_RESULTS), True)
    result = row.text("resultado", True)
    value = row.number("valor_numerico")
    description = row.text("descricao")
    origin = row.text("origem")

    if kind and result is not None:
        allowed = EVENT_RESULTS[kind]
        if result.casefold() not in allowed:
            row.problems.append(f"'resultado' de {kind} deve ser um de: {', '.join(allowed)}")
        result = result.casefold()
    if kind in VALUED:
        if VALUED[kind] and row._blank("valor_numerico"):
            row.problems.append(f"'valor_numerico' é obrigatório em {kind}")
    elif kind and not row._blank("valor_numerico"):
        row.problems.append(f"'valor_numerico' só vale para {' e '.join(VALUED)}")
    row.check(f"{label} {event_id}" if event_id else label)

    record = queue_record_of(rid)
    if record is None:
        raise ContractError(f"{label}: solicitação {rid} não encontrada na fila.", 404)
    if record.get("paciente_id") != patient:
        raise ContractError(
            f"{label}: o paciente {patient} não é o da solicitação {rid} ({record.get('paciente_id')})."
        )

    event = {
        "evento_id": event_id,
        "solicitacao_id": rid,
        "paciente_id": patient,
        "data_evento": when,
        "tipo_evento": row.original("tipo_evento"),
        "resultado": row.original("resultado"),
        "valor_numerico": value,
        "descricao": description,
        "origem": origin,
        "tipo_evento_norm": kind,
        "resultado_norm": result,
        "solicitacao_na_fila": True,
        "paciente_coincide_fila": "sim",
    }
    content = _content(event)
    event["duplicata_conteudo"] = any(_content(e) == content for e in events_of(rid))
    return event


def _content(event):
    """What the normalizer compares to call two events duplicates: all but the id."""
    return tuple(event.get(key) for key in EVENT_COLUMNS if key != "evento_id")


def source_row(record, columns):
    """A record back as a source CSV row (text cells), for the official verifier."""
    out = {}
    for key in columns:
        value = record.get(key)
        if isinstance(value, bool):
            value = "sim" if value else "nao"
        elif isinstance(value, float) and value.is_integer():
            value = int(value)
        out[key] = "" if value is None else str(value)
    return out
