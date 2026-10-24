"""What the free text says: highlighted excerpts and alarm words.

Both are regular expressions over the clinical note. The highlight rules are a
port of the front's mock (`frontend/src/mock/highlights.ts`), so the server
marks the same excerpts the prototype showed; the alarm list is the official
verifier's, so "no clinical urgency" here means exactly what it means there.
"""
import re

_FLAGS = re.IGNORECASE | re.ASCII

#: (kind, pattern) in precedence order: an excerpt already claimed by an
#: earlier kind is not marked again by a later one.
HIGHLIGHT_RULES = (
    ("red_flag", re.compile(
        r"lesao de tronco[^.,;]*|sincope[^.,;]*|melena[^.,;]*|enterorragia[^.,;]*|"
        r"queda de Hb[^.,;]*|transfundid\w*[^.,;]*|suboclusao[^.,;]*|subestenosante|"
        r"crescimento rapido|lesao ulcerada|ulcera de pressao[^.,;]*|acamad\w*[^.,;]*|"
        r"risco de glaucoma[^.,;]*|dessaturacao[^.,;]*|queda em casa[^.,;]*|"
        r"perda ponderal[^.,;]*|emagrecimento[^.,;]*|disfagia|sangramento[^.,;]*",
        _FLAGS,
    )),
    ("urgency", re.compile(
        r"\b(?:adeno)?carcinoma(?: \w+)?|\bneoplasia\b|\btumor\b|\bAP confirmad\w*|"
        r"displasia de alto grau|PET-CT com captacao|angina(?: instavel| CCS \w+)?|"
        r"BI-RADS ?\w+|DAC triarterial|estadiamento \w+",
        _FLAGS,
    )),
    ("events", re.compile(
        r"internacao(?: recente)?(?: na UPA)?|\bPS\b[^.,;]*|pronto[- ]socorro|\bpiora\b|"
        r"pede urgencia|reavaliacao da prioridade",
        _FLAGS,
    )),
    ("symptoms", re.compile(
        r"\bdor(?: em repouso| incapacitante| intensa| importante| moderada| aos esforcos|"
        r" pelvica)?\b|nao sobe escadas|nao consegue[^.,;]*|deambula com dificuldade|"
        r"uso de muletas|limitacao|parestesias \w+|dependente de familiares|"
        r"afastado do trabalho",
        _FLAGS,
    )),
)

#: Copied from the official verifier (KW_ALARME). It matches against the
#: lowercased clinical note, as the verifier does.
ALARM = re.compile(
    r"encarcer|estrangul|colangite|icter|pancreatite|enterorragia|melena|hematemese|"
    r"suboclus|perda ponderal|disfagia|sepse|hidronefrose|perda de funcao|transfund|"
    r"hemoptise|rouquidao|linfonodo.*(?:fixo|palpavel)|sangramento espontaneo|acamad|"
    r"ulcera de pressao|quedas de repeticao|glaucoma facomorfico|retencao de co2|"
    r"dano neurologico|psa em elevacao|dessaturacao|angina em repouso|sincope|"
    r"crescimento rapido|retencao urinaria aguda|massa anexial|ca-125"
)


def _scan(text, field):
    found = []
    for kind, pattern in HIGHLIGHT_RULES:
        for match in pattern.finditer(text):
            start = match.start()
            end = start + len(match.group(0).rstrip())
            if not any(start < h["end"] and end > h["start"] for h in found):
                found.append({"field": field, "start": start, "end": end, "kind": kind})
    return sorted(found, key=lambda h: h["start"])


def highlights(clinical_note, regulation_note=None):
    """Non-overlapping excerpts of the two free-text fields, by character index."""
    marks = _scan(clinical_note or "", "clinicalNote")
    if regulation_note:
        marks += _scan(regulation_note, "regulationNote")
    return marks


def has_alarm(clinical_note):
    return bool(ALARM.search((clinical_note or "").lower()))
