"""Reads the normalized CSVs, converting types and tolerating empty fields.

Column names come from the dataset and stay in Portuguese: they are the data,
documented in backend/dataset/dicionario_dados.md.
"""
from datetime import date, datetime
from pathlib import Path
import csv
import unicodedata

FILES = {
    "fila": "fila_cirurgica_normalizada.csv",
    "eventos": "eventos_clinicos_normalizados.csv",
    "procedimentos": "procedimentos_normalizados.csv",
    "swalis": "swalis_normalizado.csv",
}

# DPSS reference tables are intentionally optional until their provenance and
# mappings have been validated.  Their absence must not stop the existing DPS
# service from starting.
OPTIONAL_FILES = {
    "socioeconomic": "socioeconomic_normalized.csv",
    "disease_burden": "disease_burden_normalized.csv",
}

INTEGER_FIELDS = (
    "idade",
    "dias_em_fila",
    "distancia_hospital_km",
    "asa",
    "intensidade_dor_eva",
    "risco_cirurgico",
    "duracao_media_min",
    "prazo_maximo_dias",
)
FLOAT_FIELDS = (
    "hba1c_ultima",
    "valor_numerico",
    "s_vulnerabilidade",
    "inse_medio",
    "s_evfam",
    "s_ibge",
    "s_social",
    "s_geografico",
    "s_distancia_teto_km",
    "disability_weight_norm",
    "daly_weight_norm",
)
DATE_FIELDS = (
    "data_entrada_fila",
    "data_ultima_revisao_prioridade",
    "data_hba1c_ultima",
    "data_evento",
)
BOOLEAN_FIELDS = (
    "oncologico_cid",
    "flag_oncologico_norm",
    "flag_diabetico_norm",
    "flag_piora_clinica_norm",
    "exames_pre_op_validos_norm",
    "necessita_uti_norm",
    "duplicata_conteudo",
    "solicitacao_na_fila",
    "paciente_coincide_fila",
    "s_vulnerabilidade_imputada",
    "s_distancia_imputada",
)


class DatasetUnavailable(RuntimeError):
    """Startup error: the normalized CSVs could not be found."""


def to_int(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def to_float(text):
    try:
        return float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def to_date(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def to_bool(text):
    text = (text or "").strip().lower()
    if text in {"sim", "true", "1"}:
        return True
    if text in {"nao", "não", "false", "0"}:
        return False
    return None


def strip_accents(text):
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _convert(row):
    record = {}
    for key, raw in row.items():
        if key is None:
            continue
        value = (raw or "").strip()
        record[key] = value or None
        if key in INTEGER_FIELDS:
            record[key] = to_int(value)
        elif key in FLOAT_FIELDS:
            record[key] = to_float(value)
        elif key in DATE_FIELDS:
            parsed = to_date(value)
            record[key] = parsed.isoformat() if parsed else None
        elif key in BOOLEAN_FIELDS:
            record[key] = to_bool(value)
    return record


def read_csv(path):
    path = Path(path)
    if not path.exists():
        raise DatasetUnavailable(f"arquivo nao encontrado: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return [_convert(row) for row in csv.DictReader(handle)]


def load(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise DatasetUnavailable(
            f"diretorio do dataset nao encontrado: {directory}. "
            "Rode `python backend/dataset/normalizar_dataset.py` ou ajuste DATASET_DIR."
        )
    tables = {name: read_csv(directory / file) for name, file in FILES.items()}
    for name, filename in OPTIONAL_FILES.items():
        path = directory / filename
        tables[name] = read_csv(path) if path.exists() else []
    return tables


def today():
    return date.today()
