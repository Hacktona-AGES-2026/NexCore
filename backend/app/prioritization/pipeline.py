"""Composable prioritization pipeline.

Each step receives the same immutable source snapshot, including queue rows,
clinical events, procedures and SWALIS references. New deterministic scores,
deterioration models or a final learning-to-rank aggregator can be added as
steps without changing the HTTP endpoint or CSV contract.
"""
from dataclasses import dataclass

from .dps import MODEL_VERSION, prioritize


@dataclass(frozen=True)
class PipelineSources:
    queue: list
    events_by_request: dict
    procedures_by_id: dict
    swalis: list


class DpsStep:
    name = "dps"
    version = MODEL_VERSION

    def run(self, sources, records=None, as_of=None, include_inactive=False):
        return prioritize(
            sources.queue,
            sources.events_by_request,
            sources.swalis,
            as_of,
            include_inactive=include_inactive,
        )


class PrioritizationPipeline:
    def __init__(self, steps=None):
        self.steps = tuple(steps or (DpsStep(),))

    def run(self, sources, as_of, include_inactive=False):
        records = None
        executed = []
        for step in self.steps:
            records = step.run(
                sources,
                records=records,
                as_of=as_of,
                include_inactive=include_inactive,
            )
            executed.append({"name": step.name, "version": step.version})
        return {
            "records": records or [],
            "pipeline": {
                "steps": executed,
                "as_of": as_of,
                "supports_event_refresh": True,
                "supports_procedure_refresh": True,
            },
        }


DEFAULT_PIPELINE = PrioritizationPipeline()
