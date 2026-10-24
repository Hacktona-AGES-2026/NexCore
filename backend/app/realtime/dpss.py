"""Realtime adapter for the experimental, reference-dependent DPSS engine."""

from . import params as p
from .actions import Progress, action
from ..prioritization.dpss import (
    DEFAULT_SOCIOECONOMIC_WEIGHT,
    MODEL_VERSION,
)
from ..prioritization.dpss_presentation import complete_ranked_records
from ..prioritization.pipeline import PipelineSources, dpss_pipeline

BATCH = 100


@action("queue.prioritize.dpss")
def prioritize_queue_dpss(repository, params, limits):
    if limits.get("auto_refresh_dataset", True):
        repository.refresh_if_changed()

    as_of = p.iso_date(params, "as_of", repository.reference_date)
    include_inactive = p.boolean(params, "include_inactive", False)
    socioeconomic_weight = p.number(
        params,
        "socioeconomic_weight",
        default=DEFAULT_SOCIOECONOMIC_WEIGHT,
        minimum=0.0,
        maximum=1.0,
    )
    source_queue = repository.filter(p.queue_filters(params))
    sources = PipelineSources(
        queue=source_queue,
        events_by_request=repository.events_by_request,
        procedures_by_id=repository.procedures_by_id,
        swalis=repository.swalis,
        socioeconomic=repository.socioeconomic,
        disease_burden=repository.disease_burden,
    )
    result = dpss_pipeline(socioeconomic_weight).run(
        sources,
        as_of=as_of,
        include_inactive=include_inactive,
    )
    records = complete_ranked_records(source_queue, result["records"])
    total = len(records)

    for completed in range(BATCH, total, BATCH):
        yield Progress(completed, total, "prioritizing queue with experimental DPSS")
    if total:
        yield Progress(total, total, "prioritizing queue with experimental DPSS")

    complete = sum(
        record["reference_coverage"]["complete"] for record in records
    )
    return {
        "strategy": "dpss_experimental",
        "provisional": True,
        "reference_date": as_of,
        "total": total,
        "model": {
            "name": "DPSS experimental extension",
            "version": MODEL_VERSION,
            "formula": "DPSS=(T/M)*(1+c+w*S); final=DPSS*disability_weight",
            "socioeconomic_weight": socioeconomic_weight,
            "clinical_use_authorized": False,
            "replaces_default_dps": False,
        },
        "coverage": {
            "complete": complete,
            "incomplete": total - complete,
            "ratio": round(complete / total, 6) if total else 0.0,
            "socioeconomic_reference_rows": len(repository.socioeconomic),
            "disease_burden_reference_rows": len(repository.disease_burden),
        },
        "pipeline": result["pipeline"],
        "data": records,
    }
