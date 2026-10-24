"""Testes da configuração e da fábrica da aplicação."""
from pathlib import Path

import pytest

from app import create_app
from app.config import Config, TestConfig, _bool, get_config
from app.data import DatasetUnavailable


@pytest.mark.parametrize(
    "entrada, esperado",
    [("1", True), ("true", True), ("sim", True), ("ON", True),
     ("0", False), ("nao", False), ("qualquer", False), (None, False)],
)
def test_bool_de_variavel_de_ambiente(entrada, esperado):
    assert _bool(entrada) is esperado


def test_bool_respeita_o_padrao_quando_ausente():
    assert _bool(None, default=True) is True


def test_ambiente_de_teste_liga_a_flag_testing():
    assert get_config("teste") is TestConfig
    assert TestConfig.TESTING is True


def test_ambiente_desconhecido_cai_no_padrao():
    assert get_config("inexistente") is Config


def test_dataset_dir_padrao_aponta_para_normalizado():
    assert Config.DATASET_DIR.name == "normalizado"
    assert Config.DATASET_DIR.is_dir(), "rode dataset/normalizar_dataset.py"


def test_data_de_referencia_segue_o_dataset():
    assert Config.REFERENCE_DATE == "2026-10-23"


def test_dataset_dir_vem_do_ambiente(monkeypatch, dataset_sintetico):
    destino = dataset_sintetico(fila=[{"solicitacao_id": "SOL-1"}])
    monkeypatch.setenv("DATASET_DIR", str(destino))
    import importlib

    from app import config as modulo

    importlib.reload(modulo)
    assert modulo.Config.DATASET_DIR == Path(destino)
    monkeypatch.delenv("DATASET_DIR")
    importlib.reload(modulo)


def test_sobrescritas_chegam_na_config():
    app = create_app("teste", DEFAULT_PAGE_SIZE=7)
    assert app.config["DEFAULT_PAGE_SIZE"] == 7


def test_dataset_ausente_falha_na_criacao_da_aplicacao(tmp_path):
    with pytest.raises(DatasetUnavailable):
        create_app("teste", DATASET_DIR=tmp_path / "nao-existe")


def test_repositorio_fica_registrado_nas_extensions(app):
    assert app.extensions["repository"].counts()["queue"] == 941


def test_json_nao_escapa_acento(app):
    assert app.json.ensure_ascii is False
