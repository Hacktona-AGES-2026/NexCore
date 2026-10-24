"""Runs the challenge's official verifier on a queue, as a black box.

backend/dataset/verificar_fila_priorizada.py came from the organizers: it is
never imported nor edited, only called in a subprocess with the same Python
(it needs pandas, which requirements-dev.txt brings). It reads the dataset's
ORIGINAL CSVs, so `dataset_dir` is backend/dataset/, not normalizado/.

Requests and events that arrived through ingestion are not in those CSVs, so
they go as `extra` rows: the verifier then reads a copy of the two files with
the rows appended, in the same temporary folder. Without them it would call
every new request an unknown id.
"""
import csv
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from ..config import BACKEND_ROOT

SCRIPT = BACKEND_ROOT / "dataset" / "verificar_fila_priorizada.py"
FILE_NAME = "fila_priorizada.csv"
TIMEOUT = 120
#: Ingestion kind -> the source CSV it extends.
SOURCE_FILES = {"fila": "fila_cirurgica.csv", "eventos": "eventos_clinicos.csv"}


class VerifierUnavailable(Exception):
    """The verifier did not run to a verdict (missing script, no pandas, crash)."""


def _extended_dataset(dataset_dir, folder, extra):
    """Copies the two source CSVs into `folder`/dataset with the extra rows appended."""
    target = Path(folder, "dataset")
    target.mkdir()
    for kind, name in SOURCE_FILES.items():
        shutil.copyfile(Path(dataset_dir, name), target / name)
        rows = extra.get(kind) or ()
        if not rows:
            continue
        with (target / name).open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle))
        with (target / name).open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
            writer.writerows(rows)
    return target


def run(csv_text, dataset_dir, script=SCRIPT, timeout=TIMEOUT, extra=None):
    """Returns (ok, output). Exit 0 is OK, 1 is a failed queue; anything else raises.

    The file goes in a temporary folder and the verifier runs from there with a
    relative name, so its output says "Arquivo: fila_priorizada.csv" and no path
    of the server leaks to the front. `extra` maps "fila"/"eventos" to source
    rows that arrived after the dataset (see the module docstring).
    """
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, FILE_NAME).write_text(csv_text, encoding="utf-8", newline="")
        try:
            if extra and any(extra.values()):
                dataset_dir = _extended_dataset(dataset_dir, folder, extra)
            done = subprocess.run(
                [sys.executable, str(script), FILE_NAME, "--dataset", str(dataset_dir)],
                cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
            )
        except (OSError, csv.Error, StopIteration, subprocess.TimeoutExpired) as exc:
            raise VerifierUnavailable(str(exc)) from exc
    output = done.stdout.strip()
    if done.returncode not in (0, 1) or not output:
        raise VerifierUnavailable(done.stderr.strip()[-2000:] or f"exit {done.returncode}")
    return done.returncode == 0, output
