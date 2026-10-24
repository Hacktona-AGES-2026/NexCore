"""Validated, atomic writes into the source CSV dataset."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
import math
import threading

from ..errors import RequestError


EVFAM_FIELDS = {
    "evfam_dificuldade_financeira",
    "evfam_uso_medicamentos_continuos",
    "evfam_sem_apoio_familiar",
    "evfam_vulnerabilidade_habitacional",
}


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "sim" if value else "nao"
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    raise RequestError("dataset fields must be scalar values")


def _iso_date(row, field, required=False):
    value = _text(row.get(field))
    if not value and not required:
        return
    try:
        row[field] = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise RequestError(f"field '{field}' must use YYYY-MM-DD")


def _number(row, field, minimum=None, maximum=None, required=False):
    value = _text(row.get(field))
    if not value and not required:
        return
    try:
        parsed = float(value.replace(",", "."))
    except ValueError:
        raise RequestError(f"field '{field}' must be numeric")
    if not math.isfinite(parsed):
        raise RequestError(f"field '{field}' must be finite")
    if minimum is not None and parsed < minimum:
        raise RequestError(f"field '{field}' must be >= {minimum}")
    if maximum is not None and parsed > maximum:
        raise RequestError(f"field '{field}' must be <= {maximum}")


class DatasetIngestion:
    """Persist commands, then synchronously trigger the reactive DPSS cycle."""

    def __init__(self, source_directory, reactive_dpss):
        self.source_directory = Path(source_directory)
        self.reactive_dpss = reactive_dpss
        self._lock = threading.RLock()

    def _read(self, name):
        path = self.source_directory / name
        if not path.exists():
            raise RequestError(f"source dataset file not found: {name}", 503)
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or ()), list(reader)

    def _write(self, name, fields, rows):
        path = self.source_directory / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)

    def _prepare(self, payload):
        if not isinstance(payload, dict):
            raise RequestError("entity payload must be an object")
        return {str(key): _text(value) for key, value in payload.items()}

    def _commit(self, filename, fields, rows, entity, identifier):
        self._write(filename, fields, rows)
        published = self.reactive_dpss.poll_once()
        snapshot = self.reactive_dpss.snapshot()
        return {
            "accepted": True,
            "entity": entity,
            "id": identifier,
            "recalculated": published,
            "revision": snapshot["revision"],
            "queue_total": snapshot["total"],
        }

    def create_request(self, payload):
        with self._lock:
            fields, rows = self._read("fila_cirurgica.csv")
            row = self._prepare(payload)
            allowed = set(fields) | EVFAM_FIELDS
            unknown = set(row) - allowed
            if unknown:
                raise RequestError(
                    "unknown queue fields", details={"fields": sorted(unknown)}
                )
            required = (
                "solicitacao_id", "paciente_id", "nome_paciente", "municipio",
                "uf", "procedimento_id", "cid_principal", "data_entrada_fila",
            )
            missing = [field for field in required if not row.get(field)]
            if missing:
                raise RequestError("missing required queue fields", details={"fields": missing})
            row["solicitacao_id"] = row["solicitacao_id"].upper()
            row["paciente_id"] = row["paciente_id"].upper()
            row["procedimento_id"] = row["procedimento_id"].upper()
            if any(item.get("solicitacao_id") == row["solicitacao_id"] for item in rows):
                raise RequestError(f"request '{row['solicitacao_id']}' already exists", 409)
            procedure_fields, procedures = self._read("procedimentos.csv")
            del procedure_fields
            if row["procedimento_id"] not in {
                item.get("procedimento_id") for item in procedures
            }:
                raise RequestError(
                    f"procedure '{row['procedimento_id']}' not found", 422
                )
            _iso_date(row, "data_entrada_fila", required=True)
            for field, low, high in (
                ("idade", 0, 130), ("distancia_hospital_km", 0, None),
                ("asa", 1, 5), ("intensidade_dor_eva", 0, 10),
                ("hba1c_ultima", 0, 30),
            ):
                _number(row, field, low, high)
            for field in EVFAM_FIELDS:
                if row.get(field):
                    _number(row, field, 0, 1)
                    if float(row[field].replace(",", ".")) not in {0.0, 1.0}:
                        raise RequestError(f"field '{field}' must be 0 or 1")
            for field in EVFAM_FIELDS:
                if field not in fields:
                    fields.append(field)
            rows.append({field: row.get(field, "") for field in fields})
            return self._commit(
                "fila_cirurgica.csv", fields, rows, "queue_request", row["solicitacao_id"]
            )

    def create_event(self, payload):
        with self._lock:
            fields, rows = self._read("eventos_clinicos.csv")
            row = self._prepare(payload)
            unknown = set(row) - set(fields)
            if unknown:
                raise RequestError(
                    "unknown clinical event fields", details={"fields": sorted(unknown)}
                )
            required = (
                "evento_id", "solicitacao_id", "paciente_id", "data_evento",
                "tipo_evento", "resultado",
            )
            missing = [field for field in required if not row.get(field)]
            if missing:
                raise RequestError("missing required event fields", details={"fields": missing})
            for field in ("evento_id", "solicitacao_id", "paciente_id"):
                row[field] = row[field].upper()
            if any(item.get("evento_id") == row["evento_id"] for item in rows):
                raise RequestError(f"event '{row['evento_id']}' already exists", 409)
            _, queue = self._read("fila_cirurgica.csv")
            request = next(
                (item for item in queue if item.get("solicitacao_id") == row["solicitacao_id"]),
                None,
            )
            if request is None:
                raise RequestError(f"request '{row['solicitacao_id']}' not found", 422)
            if request.get("paciente_id") != row["paciente_id"]:
                raise RequestError("event patient does not match queue request", 422)
            _iso_date(row, "data_evento", required=True)
            _number(row, "valor_numerico")
            rows.append({field: row.get(field, "") for field in fields})
            return self._commit(
                "eventos_clinicos.csv", fields, rows, "clinical_event", row["evento_id"]
            )

    def upsert_procedure(self, payload):
        with self._lock:
            fields, rows = self._read("procedimentos.csv")
            row = self._prepare(payload)
            unknown = set(row) - set(fields)
            if unknown:
                raise RequestError(
                    "unknown procedure fields", details={"fields": sorted(unknown)}
                )
            identifier = row.get("procedimento_id", "").upper()
            if not identifier:
                raise RequestError("field 'procedimento_id' is required")
            row["procedimento_id"] = identifier
            for field, low, high in (
                ("risco_cirurgico", 1, 5),
                ("duracao_media_min", 1, None),
            ):
                _number(row, field, low, high)
            existing = next(
                (item for item in rows if item.get("procedimento_id") == identifier),
                None,
            )
            if existing is None:
                missing = [
                    field for field in ("procedimento", "especialidade", "porte")
                    if not row.get(field)
                ]
                if missing:
                    raise RequestError(
                        "missing required procedure fields", details={"fields": missing}
                    )
                rows.append({field: row.get(field, "") for field in fields})
                operation = "created"
            else:
                existing.update({key: value for key, value in row.items() if value != ""})
                operation = "updated"
            result = self._commit(
                "procedimentos.csv", fields, rows, "procedure", identifier
            )
            result["operation"] = operation
            return result

