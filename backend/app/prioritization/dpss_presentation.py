"""Public representation of the experimental DPSS ranking."""

ORDER_FIELDS = (
    "position",
    "ranking_score",
    "ranking_basis",
    "dpss_score",
    "disability_weight",
    "final_score",
    "swalis_class",
    "waiting_days",
    "max_wait_days",
    "clinical_factor",
    "socioeconomic_vulnerability",
    "justification",
)


def complete_ranked_records(queue, ranking):
    queue_by_id = {row.get("solicitacao_id"): row for row in queue}
    records = []
    for priority in ranking:
        source = queue_by_id.get(priority.get("solicitacao_id"), {})
        swalis = priority["swalis"]
        clinical = priority["clinical_factor"]
        dpss = priority["dpss"]
        burden = priority["burden_adjustment"]
        record = {
            "position": priority["position"],
            "ranking_score": priority["ranking_score"],
            "ranking_basis": priority["ranking_basis"],
            "dpss_score": dpss["score"],
            "disability_weight": burden["disability_weight"],
            "final_score": burden["final_score"],
            "swalis_class": swalis["class"],
            "waiting_days": priority["waiting_days"],
            "max_wait_days": swalis["maximum_wait_days"],
            "clinical_factor": clinical["value"],
            "socioeconomic_vulnerability": dpss["socioeconomic_vulnerability"],
            "justification": priority["justification"],
            **source,
            **{
                key: value
                for key, value in priority.items()
                if key not in {"position", "justification"}
            },
        }
        records.append(record)
    return records
