"""Realtime actions for the DPS prioritization module.

The WebSocket transport is intentionally a thin adapter.  Clinical rules live
in ``app.prioritization`` and can be tested or reused without a socket.
"""

from . import params as p
from .actions import Progress, action
from ..prioritization.dps import MODEL_VERSION
from ..prioritization.pipeline import PipelineSources, DEFAULT_PIPELINE
from ..prioritization.presentation import complete_ranked_records

BATCH = 100


@action("queue.prioritize")
def prioritize_queue(repository, params, limits):
    """Run DPS on demand and return the complete, currently ranked queue.

    Client command::

        {"action": "queue.prioritize", "params": {"as_of": "2026-10-23"}}

    Queue filters are optional.  ``include_inactive`` defaults to false, so a
    withdrawal or surgery reported by a newer clinical event leaves the active
    ranking without deleting its source data.
    """
    if limits.get("auto_refresh_dataset", True):
        repository.refresh_if_changed()

    as_of = p.iso_date(params, "as_of", repository.reference_date)
    include_inactive = p.boolean(params, "include_inactive", False)
    source_queue = repository.filter(p.queue_filters(params))
    sources = PipelineSources(
        queue=source_queue,
        events_by_request=repository.events_by_request,
        procedures_by_id=repository.procedures_by_id,
        swalis=repository.swalis,
    )
    result = DEFAULT_PIPELINE.run(
        sources,
        as_of=as_of,
        include_inactive=include_inactive,
    )
    records = complete_ranked_records(source_queue, result["records"])
    total = len(records)

    # Frames keep a large response observable and correlate it with the command.
    for completed in range(BATCH, total, BATCH):
        yield Progress(completed, total, "prioritizing queue with DPS")
    if total:
        yield Progress(total, total, "prioritizing queue with DPS")

    return {
        "strategy": "dps",
        "provisional": True,
        "reference_date": as_of,
        "total": total,
        "model": {
            "name": "DPS Module 1",
            "version": MODEL_VERSION,
            "formula": "P = (t / M) * (1 + c)",
            "weights_validated_with_paprika": False,
            "clinical_use_authorized": False,
        },
        "pipeline": result["pipeline"],
        "data": records,
    }
