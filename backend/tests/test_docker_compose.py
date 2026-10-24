"""Compose da raiz: o simulador sobe junto, com imagem própria, só depois do backend.

Lê o compose resolvido por `docker compose config --format json` (sem PyYAML no venv);
pulado sem Docker instalado.
"""
import json
import shutil
import subprocess

import pytest

from app.config import BACKEND_ROOT

REPO_ROOT = BACKEND_ROOT.parent
DOCKER = shutil.which("docker")

pytestmark = pytest.mark.skipif(DOCKER is None, reason="Docker não instalado")


@pytest.fixture(scope="module")
def servicos():
    saida = subprocess.run(
        [DOCKER, "compose", "config", "--format", "json"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    if saida.returncode != 0:
        pytest.skip(f"docker compose indisponível: {saida.stderr.strip()}")
    return json.loads(saida.stdout)["services"]


def test_simulador_tem_imagem_propria(servicos):
    assert servicos["simulador"]["build"]["context"] == str(REPO_ROOT / "simulador")


def test_simulador_espera_o_healthcheck_do_backend(servicos):
    assert servicos["simulador"]["depends_on"]["backend"]["condition"] == "service_healthy"


def test_simulador_fala_com_o_backend_pela_rede_do_compose(servicos):
    assert servicos["simulador"]["environment"]["BACKEND_URL"] == "http://backend:5000"


def test_simulador_usa_o_mesmo_hospital_e_data_do_backend(servicos):
    simulador = servicos["simulador"]["environment"]
    backend = servicos["backend"]["environment"]
    assert simulador["HOSPITAL_ID"] == backend["HOSPITAL_ID"]
    assert simulador["REFERENCE_DATE"] == backend["REFERENCE_DATE"]
