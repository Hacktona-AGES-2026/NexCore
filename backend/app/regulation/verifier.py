"""Runs the challenge's official verifier on a queue, as a black box.

backend/dataset/verificar_fila_priorizada.py came from the organizers: it is
never imported nor edited, only called in a subprocess with the same Python
(it needs pandas, which requirements-dev.txt brings). It reads the dataset's
ORIGINAL CSVs, so `dataset_dir` is backend/dataset/, not normalizado/.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

from ..config import BACKEND_ROOT

SCRIPT = BACKEND_ROOT / "dataset" / "verificar_fila_priorizada.py"
FILE_NAME = "fila_priorizada.csv"
TIMEOUT = 120


class VerifierUnavailable(Exception):
    """The verifier did not run to a verdict (missing script, no pandas, crash)."""


def run(csv_text, dataset_dir, script=SCRIPT, timeout=TIMEOUT):
    """Returns (ok, output). Exit 0 is OK, 1 is a failed queue; anything else raises.

    The file goes in a temporary folder and the verifier runs from there with a
    relative name, so its output says "Arquivo: fila_priorizada.csv" and no path
    of the server leaks to the front.
    """
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, FILE_NAME).write_text(csv_text, encoding="utf-8", newline="")
        try:
            done = subprocess.run(
                [sys.executable, str(script), FILE_NAME, "--dataset", str(dataset_dir)],
                cwd=folder, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VerifierUnavailable(str(exc)) from exc
    output = done.stdout.strip()
    if done.returncode not in (0, 1) or not output:
        raise VerifierUnavailable(done.stderr.strip()[-2000:] or f"exit {done.returncode}")
    return done.returncode == 0, output
