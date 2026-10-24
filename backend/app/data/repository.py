"""In-memory repository over the normalized dataset.

The queue holds fewer than a thousand requests, so everything is loaded once
when the application is created and served from id-keyed indexes. Nothing is
imputed: a value missing from the CSV stays null in the response.

Record keys are the dataset's own Portuguese column names.
"""
from collections import Counter, defaultdict
from pathlib import Path
from threading import RLock

from .reader import FILES, OPTIONAL_FILES, load, strip_accents

SORT_KEYS = {
    "dias_em_fila": lambda r: r.get("dias_em_fila") or 0,
    "idade": lambda r: r.get("idade") or 0,
    "data_entrada_fila": lambda r: r.get("data_entrada_fila") or "",
    "intensidade_dor_eva": lambda r: r.get("intensidade_dor_eva") or 0,
    "solicitacao_id": lambda r: r.get("solicitacao_id") or "",
}

SEARCH_FIELDS = (
    "solicitacao_id",
    "paciente_id",
    "nome_paciente",
    "procedimento",
    "cid_principal",
    "cid_descricao",
    "justificativa_clinica",
    "observacoes",
)


class Repository:
    def __init__(self, directory, reference_date=None):
        self.directory = str(Path(directory))
        self.reference_date = reference_date
        self._lock = RLock()
        self._signature = None
        self._replace_tables(load(self.directory))
        self._signature = self._source_signature()

    def _replace_tables(self, tables):
        self.queue = tables["fila"]
        self.events = tables["eventos"]
        self.procedures = tables["procedimentos"]
        self.swalis = tables["swalis"]
        self.socioeconomic = tables.get("socioeconomic", [])
        self.disease_burden = tables.get("disease_burden", [])

        self._by_request = {r["solicitacao_id"]: r for r in self.queue}
        self._by_procedure = {r["procedimento_id"]: r for r in self.procedures}
        self._events_by_request = defaultdict(list)
        self._events_by_patient = defaultdict(list)
        for event in self.events:
            self._events_by_request[event["solicitacao_id"]].append(event)
            self._events_by_patient[event["paciente_id"]].append(event)
        for group in self._events_by_request.values():
            group.sort(key=lambda e: e.get("data_evento") or "")
        self._search_index = {
            r["solicitacao_id"]: strip_accents(
                " ".join(str(r.get(f) or "") for f in SEARCH_FIELDS)
            )
            for r in self.queue
        }

    def _source_signature(self):
        directory = Path(self.directory)
        return tuple(
            (
                name,
                (directory / filename).stat().st_mtime_ns,
                (directory / filename).stat().st_size,
            )
            for name, filename in sorted({**FILES, **OPTIONAL_FILES}.items())
            if (directory / filename).exists()
        )

    def refresh_if_changed(self):
        """Atomically reload all normalized tables when any source CSV changes.

        The producer should replace CSVs atomically (temporary file + rename). This
        keeps every API request on one coherent snapshot while allowing clinical
        events and queue corrections to affect prioritization without a restart.
        """
        signature = self._source_signature()
        if signature == self._signature:
            return False
        with self._lock:
            signature = self._source_signature()
            if signature == self._signature:
                return False
            tables = load(self.directory)
            self._replace_tables(tables)
            self._signature = signature
            return True

    # --- queries -------------------------------------------------------

    def counts(self):
        return {
            "queue": len(self.queue),
            "events": len(self.events),
            "procedures": len(self.procedures),
            "swalis": len(self.swalis),
        }

    def get_request(self, request_id):
        return self._by_request.get(request_id)

    def get_procedure(self, procedure_id):
        return self._by_procedure.get(procedure_id)

    def events_for_request(self, request_id):
        return list(self._events_by_request.get(request_id, []))

    def events_for_patient(self, patient_id):
        return list(self._events_by_patient.get(patient_id, []))

    @property
    def events_by_request(self):
        """Read-only-by-convention index used by prioritization snapshots."""
        return self._events_by_request

    @property
    def procedures_by_id(self):
        """Read-only-by-convention procedure index for pipeline steps."""
        return self._by_procedure

    def prioritized_queue(self, as_of=None, include_inactive=False, weights=None):
        if weights is not None:
            from ..prioritization import prioritize

            return prioritize(
                self.queue,
                self._events_by_request,
                self.swalis,
                as_of or self.reference_date,
                weights=weights,
                include_inactive=include_inactive,
            )
        return self.run_prioritization_pipeline(
            as_of=as_of, include_inactive=include_inactive
        )["records"]

    def run_prioritization_pipeline(self, as_of=None, include_inactive=False):
        from ..prioritization.pipeline import DEFAULT_PIPELINE, PipelineSources

        sources = PipelineSources(
            queue=self.queue,
            events_by_request=self._events_by_request,
            procedures_by_id=self._by_procedure,
            swalis=self.swalis,
            socioeconomic=self.socioeconomic,
            disease_burden=self.disease_burden,
        )
        return DEFAULT_PIPELINE.run(
            sources,
            as_of=as_of or self.reference_date,
            include_inactive=include_inactive,
        )

    def priority_for_request(self, request_id, as_of=None, weights=None):
        ranked = self.prioritized_queue(
            as_of=as_of, include_inactive=True, weights=weights
        )
        return next(
            (item for item in ranked if item["solicitacao_id"] == request_id), None
        )

    def filter(self, filters):
        return [r for r in self.queue if self._matches(r, filters)]

    def _matches(self, record, filters):
        specialty = filters.get("specialty")
        if specialty and strip_accents(record.get("especialidade")) != specialty:
            return False

        priority = filters.get("priority")
        if priority and record.get("prioridade_regulacao_norm") != priority:
            return False

        oncological = filters.get("oncological")
        if oncological is not None and bool(record.get("oncologico_cid")) != oncological:
            return False

        procedure_id = filters.get("procedure_id")
        if procedure_id and record.get("procedimento_id") != procedure_id:
            return False

        city = filters.get("city")
        if city and strip_accents(record.get("municipio_norm")) != city:
            return False

        min_days = filters.get("min_days")
        if min_days is not None and (record.get("dias_em_fila") or 0) < min_days:
            return False

        max_days = filters.get("max_days")
        if max_days is not None and (record.get("dias_em_fila") or 0) > max_days:
            return False

        min_age = filters.get("min_age")
        if min_age is not None and (record.get("idade") or 0) < min_age:
            return False

        term = filters.get("search")
        if term and term not in self._search_index[record["solicitacao_id"]]:
            return False

        return True

    def sort(self, records, field, descending):
        key = SORT_KEYS.get(field, SORT_KEYS["solicitacao_id"])
        return sorted(records, key=key, reverse=descending)

    # --- aggregations --------------------------------------------------

    def statistics(self):
        oncological = [r for r in self.queue if r.get("oncologico_cid")]
        waits = [r.get("dias_em_fila") or 0 for r in self.queue]
        mismatched = [
            r["solicitacao_id"]
            for r in self.queue
            if r.get("flag_oncologico_norm") is not None
            and bool(r.get("flag_oncologico_norm")) != bool(r.get("oncologico_cid"))
        ]
        pairs = Counter(
            (r.get("paciente_id"), r.get("procedimento_id")) for r in self.queue
        )
        return {
            "total_requests": len(self.queue),
            "oncological_by_cid": len(oncological),
            "oncological_flag_mismatch": len(mismatched),
            "repeated_patient_procedure_pairs": sum(
                1 for n in pairs.values() if n > 1
            ),
            "wait_days": {
                "min": min(waits) if waits else 0,
                "max": max(waits) if waits else 0,
                "mean": round(sum(waits) / len(waits), 1) if waits else 0,
                "over_365": sum(1 for d in waits if d > 365),
            },
            "by_priority": self._count("prioridade_regulacao_norm"),
            "by_specialty": self._count("especialidade"),
            "events_by_type": dict(
                Counter(e.get("tipo_evento_norm") or "unknown" for e in self.events)
            ),
        }

    def _count(self, field):
        tally = Counter(r.get(field) or "unknown" for r in self.queue)
        return dict(sorted(tally.items(), key=lambda pair: -pair[1]))

    def specialties(self):
        return sorted({r.get("especialidade") for r in self.queue if r.get("especialidade")})

    def priorities(self):
        return sorted(
            {
                r.get("prioridade_regulacao_norm")
                for r in self.queue
                if r.get("prioridade_regulacao_norm")
            }
        )
