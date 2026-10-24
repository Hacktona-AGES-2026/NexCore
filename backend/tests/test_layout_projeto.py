"""Layout do repositório: os caminhos que config.py e pytest.ini assumem existem mesmo.

`dataset/` vive dentro de `backend/` (commit 2b598a1). Mover a pasta sem ajustar os dois
lados quebra a app na criação (`DatasetUnavailable`) e faz o pytest deselecionar a suíte
do dataset em silêncio — foi exatamente o que aconteceu. Estes testes falham antes disso.
"""
import configparser

import pytest

from app.config import BACKEND_ROOT, Config

REPO_ROOT = BACKEND_ROOT.parent
PYTEST_INI = REPO_ROOT / "pytest.ini"
DATASET = BACKEND_ROOT / "dataset"


def _secao_pytest():
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI, encoding="utf-8")
    return parser["pytest"]


def test_backend_root_aponta_para_backend():
    assert BACKEND_ROOT.name == "backend"
    assert (BACKEND_ROOT / "wsgi.py").is_file()


def test_dataset_dir_padrao_fica_dentro_do_backend():
    assert Config.DATASET_DIR == DATASET / "normalizado"
    assert Config.DATASET_DIR.is_dir(), "rode backend/dataset/normalizar_dataset.py"


@pytest.mark.parametrize("arquivo", [
    "normalizar_dataset.py",
    "verificar_fila_priorizada.py",
    "fila_cirurgica.csv",
    "eventos_clinicos.csv",
    "procedimentos.csv",
    "IBGE.csv",
    "referencias/swalis.csv",
    "referencias/municipios_ibge.csv",
])
def test_dataset_de_origem_e_scripts_estao_onde_os_comandos_esperam(arquivo):
    # O verificador oficial lê os CSVs de origem, não os normalizados.
    assert (DATASET / arquivo).is_file()


def test_pytest_ini_esta_na_raiz_do_repositorio():
    assert PYTEST_INI.is_file()


@pytest.mark.parametrize("chave", ["testpaths", "pythonpath"])
def test_caminhos_do_pytest_ini_existem(chave):
    ausentes = [
        valor for valor in _secao_pytest()[chave].split()
        if not (REPO_ROOT / valor).is_dir()
    ]
    assert ausentes == [], f"{chave} aponta para diretorio inexistente: {ausentes}"


def test_pytest_ini_coleta_as_duas_suites():
    assert set(_secao_pytest()["testpaths"].split()) == {
        "backend/tests", "backend/dataset/tests",
    }
