"""Aggregates for the public screen and the equity panel (§8 of the contract).

Pure functions over the current queue: `entries` are the front's QueueEntry
dicts in queue order, `records` the dataset rows by id (for the distance, which
the front's entry does not carry).
"""
from collections import OrderedDict

from ..prioritization import CLASSES, is_overdue
from .serializers import initials

TOP_SIZE = 12
WAIT_BUCKETS = (
    ("0–90", 90), ("91–180", 180), ("181–365", 365), ("1–2 anos", 730), ("2+ anos", None),
)
DISTANCE_GROUPS = (("Até 50 km", 50), ("50 a 200 km", 200), ("Mais de 200 km", None))
AGE_GROUPS = (("18 a 39", 39), ("40 a 59", 59), ("60 a 74", 74), ("75 ou mais", None))
SEX_GROUPS = (("Mulheres", "F"), ("Homens", "M"))


def half_up(value):
    """Rounds .5 up, as the front's Math.round does (Python rounds to even)."""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def _overdue(entry):
    return is_overdue(entry["daysWaiting"], entry["urgencyClass"])


def _bucket(value, limits):
    for label, limit in limits:
        if limit is None or value <= limit:
            return label
    return limits[-1][0]


def summary(entries):
    by_class = OrderedDict((cls, {"cls": cls, "total": 0, "overdue": 0}) for cls in CLASSES)
    specialties = {}
    buckets = OrderedDict((label, 0) for label, _ in WAIT_BUCKETS)
    for e in entries:
        late = _overdue(e)
        by_class[e["urgencyClass"]]["total"] += 1
        by_class[e["urgencyClass"]]["overdue"] += late
        spec = specialties.setdefault(e["specialty"], {"label": e["specialty"], "total": 0, "overdue": 0})
        spec["total"] += 1
        spec["overdue"] += late
        buckets[_bucket(e["daysWaiting"] or 0, WAIT_BUCKETS)] += 1
    return {
        "total": len(entries),
        "oncologic": sum(1 for e in entries if e["oncologic"]),
        "overdueTotal": sum(1 for e in entries if _overdue(e)),
        "byClass": list(by_class.values()),
        "bySpecialty": sorted(specialties.values(), key=lambda s: (-s["total"], s["label"])),
        "waitBuckets": [{"label": label, "total": n} for label, n in buckets.items()],
        "top": [
            {
                "position": e["position"],
                "id": e["id"],
                "initials": initials(e["name"]),
                "procedure": e["procedure"],
                "cls": e["urgencyClass"],
                "days": e["daysWaiting"],
            }
            for e in entries[:TOP_SIZE]
        ],
    }


def _group(label, members):
    total = len(members)
    return {
        "label": label,
        "total": total,
        "avgWait": half_up(sum(e["daysWaiting"] or 0 for e in members) / total) if total else 0,
        "overduePct": half_up(100 * sum(1 for e in members if _overdue(e)) / total) if total else 0,
    }


def equity(entries, records, coordinates):
    """`coordinates` maps a city name (as entries spell it) to {lat, lon}."""
    cities = OrderedDict()
    distance = {label: [] for label, _ in DISTANCE_GROUPS}
    age = {label: [] for label, _ in AGE_GROUPS}
    sex = {label: [] for label, _ in SEX_GROUPS}
    for e in entries:
        km = records[e["id"]].get("distancia_hospital_km")
        cities.setdefault(e["city"], []).append((e, km))
        if km is not None:
            distance[_bucket(km, DISTANCE_GROUPS)].append(e)
        if e["age"] is not None:
            age[_bucket(e["age"], AGE_GROUPS)].append(e)
        for label, code in SEX_GROUPS:
            if e["sex"] == code:
                sex[label].append(e)

    city_stats = []
    for name, members in cities.items():
        where = coordinates.get(name)
        if where is None:  # no coordinates: cannot go on the map
            continue
        kms = [km for _, km in members if km is not None]
        city_stats.append({
            "name": name,
            "lat": where["lat"],
            "lon": where["lon"],
            "total": len(members),
            "avgWait": half_up(sum(e["daysWaiting"] or 0 for e, _ in members) / len(members)),
            "overdue": sum(1 for e, _ in members if _overdue(e)),
            "urgent": sum(1 for e, _ in members if e["urgencyClass"] in ("A1", "A2")),
            "distanceKm": half_up(sum(kms) / len(kms)) if kms else None,
        })
    city_stats.sort(key=lambda c: (-c["total"], c["name"]))
    return {
        "cities": city_stats,
        "byDistance": [_group(label, distance[label]) for label, _ in DISTANCE_GROUPS],
        "byAge": [_group(label, age[label]) for label, _ in AGE_GROUPS],
        "bySex": [_group(label, sex[label]) for label, _ in SEX_GROUPS],
    }
