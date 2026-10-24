"""Export the current DPS ranking as the challenge-compatible CSV."""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

from app import create_app
from app.prioritization.presentation import ORDER_FIELDS, complete_ranked_records


def export_repository(repository, output, as_of=None, include_inactive=False):
    """Export ordering fields first, followed by every original queue field."""
    content, count = render_repository_csv(
        repository, as_of=as_of, include_inactive=include_inactive
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="")
    return count, output


def render_repository_csv(repository, as_of=None, include_inactive=False):
    """Render a fresh prioritized queue as CSV without creating a server-side file."""
    ranking = repository.prioritized_queue(
        as_of=as_of, include_inactive=include_inactive
    )
    records = complete_ranked_records(repository.queue, ranking)
    queue_fields = list(repository.queue[0]) if repository.queue else []
    fields = list(ORDER_FIELDS) + [
        field for field in queue_fields if field not in ORDER_FIELDS
    ]
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for row in records:
        writer.writerow({field: row.get(field) for field in fields})
    return handle.getvalue(), len(ranking)


def export(output, as_of=None, include_inactive=False):
    app = create_app()
    repository = app.extensions["repository"]
    return export_repository(
        repository,
        output,
        as_of=as_of,
        include_inactive=include_inactive,
    )


def main():
    parser = argparse.ArgumentParser(description="Exporta a fila DPS priorizada")
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of", help="data de corte YYYY-MM-DD")
    parser.add_argument("--include-inactive", action="store_true")
    arguments = parser.parse_args()
    count, path = export(
        arguments.output,
        as_of=arguments.as_of,
        include_inactive=arguments.include_inactive,
    )
    print(f"{count} solicitações exportadas para {path}")


if __name__ == "__main__":
    main()
