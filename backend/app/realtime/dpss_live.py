"""Reactive DPSS snapshots driven by dataset changes.

The request/response WebSocket remains available for explicit calculations.
This service adds the missing event-driven path: raw dataset change,
normalization, repository reload, full DPSS recalculation and push broadcast.
"""
from __future__ import annotations

from pathlib import Path
import threading

from dataset.normalizar_dataset import main as normalize_dataset

from ..prioritization.dpss import DEFAULT_SOCIOECONOMIC_WEIGHT, MODEL_VERSION
from ..prioritization.dpss_presentation import complete_ranked_records
from ..prioritization.pipeline import PipelineSources, dpss_pipeline
from ..regulation.hub import Hub


SOURCE_FILES = (
    "fila_cirurgica.csv",
    "eventos_clinicos.csv",
    "procedimentos.csv",
    "IBGE.csv",
    "referencias/swalis.csv",
    "referencias/municipios_ibge.csv",
)


def _signature(directory, files):
    directory = Path(directory)
    return tuple(
        (
            relative,
            (directory / relative).stat().st_mtime_ns,
            (directory / relative).stat().st_size,
        )
        for relative in files
        if (directory / relative).exists()
    )


class ReactiveDpss:
    """Watch source data and publish a fresh complete DPSS queue on changes."""

    def __init__(
        self,
        repository,
        hospital_id,
        source_directory=None,
        interval_seconds=1.0,
        socioeconomic_weight=DEFAULT_SOCIOECONOMIC_WEIGHT,
        logger=None,
        normalizer=normalize_dataset,
    ):
        self.repository = repository
        self.hospital_id = hospital_id
        self.source_directory = (
            Path(source_directory) if source_directory is not None else None
        )
        self.interval_seconds = max(float(interval_seconds), 0.05)
        self.socioeconomic_weight = socioeconomic_weight
        self.logger = logger
        self.normalizer = normalizer
        self.hub = Hub()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._revision = 0
        self._snapshot = None
        self._source_signature = self._read_source_signature()

    def _read_source_signature(self):
        if self.source_directory is None:
            return None
        return _signature(self.source_directory, SOURCE_FILES)

    def _calculate(self, reason):
        sources = PipelineSources(
            queue=self.repository.queue,
            events_by_request=self.repository.events_by_request,
            procedures_by_id=self.repository.procedures_by_id,
            swalis=self.repository.swalis,
            socioeconomic=self.repository.socioeconomic,
            disease_burden=self.repository.disease_burden,
        )
        result = dpss_pipeline(self.socioeconomic_weight).run(
            sources,
            as_of=self.repository.reference_date,
            include_inactive=False,
        )
        records = complete_ranked_records(
            self.repository.queue, result["records"]
        )
        self._revision += 1
        return {
            "type": "queue.dpss.snapshot",
            "hospitalId": self.hospital_id,
            "revision": self._revision,
            "reason": reason,
            "referenceDate": self.repository.reference_date,
            "total": len(records),
            "model": {
                "name": "DPSS experimental extension",
                "version": MODEL_VERSION,
                "formula": "DPSS=(T/M)*(1+c+w*S)",
                "socioeconomicWeight": self.socioeconomic_weight,
            },
            "pipeline": result["pipeline"],
            "data": records,
        }

    def snapshot(self):
        with self._lock:
            if self._snapshot is None:
                self._snapshot = self._calculate("initial")
            return self._snapshot

    def subscribe(self):
        with self._lock:
            subscription = self.hub.subscribe()
            subscription.put(self.snapshot())
            return subscription

    def poll_once(self):
        """Run one watch cycle; return True only when a new queue was published."""
        with self._lock:
            source_signature = self._read_source_signature()
            source_changed = (
                source_signature is not None
                and source_signature != self._source_signature
            )
            if source_changed:
                self.normalizer(
                    base=self.source_directory,
                    output=self.repository.directory,
                )
                self._source_signature = source_signature

            normalized_changed = self.repository.refresh_if_changed()
            if not source_changed and not normalized_changed:
                return False

            reason = "source_normalized" if source_changed else "normalized_dataset_changed"
            self._snapshot = self._calculate(reason)
            self.hub.publish(self._snapshot)
            return True

    def _watch(self):
        while not self._stop.wait(self.interval_seconds):
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - watcher survives malformed batches
                if self.logger is not None:
                    self.logger.exception("reactive DPSS refresh failed")

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._watch,
                name="nexcore-reactive-dpss",
                daemon=True,
            )
            self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, self.interval_seconds * 2))

