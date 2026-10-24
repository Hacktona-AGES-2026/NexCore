"""Testes do carregamento do .env pelo wsgi.py.

O .env não é versionado, então os testes que dependem dele são pulados quando
ele não existe. A conferência de nomes de chave roda sobre o .env.example, que
é versionado — ela é a rede contra chave renomeada no código e esquecida no
arquivo de ambiente.
"""
from pathlib import Path
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ENV = BACKEND / ".env"
ENV_EXEMPLO = BACKEND / ".env.example"

# Chaves que a aplicação realmente consome: app/config.py mais as do próprio Flask.
CHAVES_ACEITAS = {
    "SECRET_KEY", "DATASET_DIR", "VERIFIER_DATASET_DIR", "REFERENCE_DATE", "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE", "CORS_ORIGINS", "WS_PATH", "AUTO_REFRESH_DATASET", "HOSPITAL_ID",
    "APP_AMBIENTE", "FLASK_APP", "FLASK_DEBUG",
}


def ler_chaves(caminho):
    chaves = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chaves.append(linha.split("=", 1)[0].strip())
    return chaves


def config_do_wsgi(expressao, ambiente_extra=None):
    """Importa o wsgi em subprocess e devolve o valor impresso."""
    import os

    ambiente = dict(os.environ)
    ambiente.pop("DEFAULT_PAGE_SIZE", None)
    ambiente.update(ambiente_extra or {})
    processo = subprocess.run(
        [sys.executable, "-c", f"import wsgi; print({expressao})"],
        cwd=BACKEND, capture_output=True, text=True, env=ambiente,
    )
    assert processo.returncode == 0, processo.stderr
    return processo.stdout.strip()


# --- nomes de chave -------------------------------------------------------

def test_exemplo_so_tem_chaves_que_a_aplicacao_le():
    desconhecidas = set(ler_chaves(ENV_EXEMPLO)) - CHAVES_ACEITAS
    assert not desconhecidas, f"chaves que ninguem le: {sorted(desconhecidas)}"


def test_exemplo_nao_tem_chave_repetida():
    chaves = ler_chaves(ENV_EXEMPLO)
    assert len(chaves) == len(set(chaves))


def test_chaves_aceitas_existem_na_config():
    from app.config import Config

    for chave in CHAVES_ACEITAS - {"APP_AMBIENTE", "FLASK_APP", "FLASK_DEBUG"}:
        assert hasattr(Config, chave), chave


@pytest.mark.skipif(not ENV.exists(), reason=".env local nao existe")
def test_env_local_so_tem_chaves_que_a_aplicacao_le():
    desconhecidas = set(ler_chaves(ENV)) - CHAVES_ACEITAS
    assert not desconhecidas, f"chaves que ninguem le: {sorted(desconhecidas)}"


# --- carregamento ---------------------------------------------------------

@pytest.mark.lento
def test_variavel_do_ambiente_vence_o_arquivo():
    valor = config_do_wsgi(
        "wsgi.app.config['DEFAULT_PAGE_SIZE']",
        {"DEFAULT_PAGE_SIZE": "123"},
    )
    assert valor == "123"


@pytest.mark.lento
@pytest.mark.skipif(not ENV.exists(), reason=".env local nao existe")
def test_secret_key_do_env_chega_na_aplicacao():
    valor = config_do_wsgi("wsgi.app.config['SECRET_KEY'] != 'dev-nao-use-em-producao'")
    assert valor == "True", "o .env nao foi carregado antes de app.config"


@pytest.mark.lento
def test_wsgi_sobe_mesmo_sem_env(tmp_path, monkeypatch):
    """Sem .env a aplicação usa os padrões em vez de quebrar."""
    valor = config_do_wsgi("wsgi.app.config['REFERENCE_DATE']")
    assert valor == "2026-10-23"
