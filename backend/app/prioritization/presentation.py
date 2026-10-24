"""Public representation of a DPS ranking.

The scoring engine deliberately returns structured evidence.  This module
combines that evidence with the complete source queue row, keeping transport
concerns out of the clinical calculation.
"""

ORDER_FIELDS = (
    "position",
    "dps",
    "ranking_band",
    "swalis_class",
    "waiting_days",
    "max_wait_days",
    "clinical_factor",
    "justification",
)


def complete_ranked_records(queue, ranking):
    """Return order fields first, then every source and DPS evidence field."""
    queue_by_id = {row.get("solicitacao_id"): row for row in queue}
    records = []
    for priority in ranking:
        source = queue_by_id.get(priority.get("solicitacao_id"), {})
        swalis = priority["swalis"]
        clinical_factor = priority["clinical_factor"]
        dps = priority["dps"]
        record = {
            "position": priority["position"],
            "dps": dps["score"],
            "ranking_band": (
                "safety_A1_A2"
                if swalis["class"] in {"A1", "A2"}
                else "general"
            ),
            "swalis_class": swalis["class"],
            "waiting_days": priority["waiting_days"],
            "max_wait_days": swalis["maximum_wait_days"],
            "clinical_factor": clinical_factor["value"],
            "justification": priority["justification"],
            **source,
            "active": priority["active"],
            "as_of": priority["as_of"],
            "swalis_details": swalis,
            "clinical_factor_details": clinical_factor,
            "dps_details": dps,
            "event_history": priority["event_history"],
            "data_quality": priority["data_quality"],
            "operational_readiness": priority["operational_readiness"],
            "requires_human_review": priority["requires_human_review"],
            "explanation": priority["explanation"],
            "versions": priority["versions"],
            "ranking_policy": priority["ranking_policy"],
        }
        records.append(record)
    return records
