from pathlib import Path
import csv

import pytest

from app import create_app

COLUNAS_FILA_NORM = [
    "solicitacao_id", "paciente_id", "nome_paciente", "sexo", "idade", "municipio",
    "uf", "distancia_hospital_km", "procedimento_id", "procedimento", "especialidade",
    "cid_principal", "cid_descricao", "cid_secundario", "asa", "comorbidades",
    "intensidade_dor_eva", "limitacao_funcional", "justificativa_clinica",
    "observacoes", "data_entrada_fila", "dias_em_fila", "prioridade_regulacao",
    "data_ultima_revisao_prioridade", "flag_oncologico", "flag_diabetico",
    "flag_piora_clinica", "hba1c_ultima", "data_hba1c_ultima",
    "avaliacao_pre_anestesica", "exames_pre_op_validos", "cid_principal_norm",
    "cid_secundario_norm", "oncologico_cid", "municipio_norm",
    "prioridade_regulacao_norm", "flag_oncologico_norm", "flag_diabetico_norm",
    "flag_piora_clinica_norm", "avaliacao_pre_anestesica_norm",
    "exames_pre_op_validos_norm", "limitacao_funcional_norm", "sexo_norm",
]
COLUNAS_EVENTOS_NORM = [
    "evento_id", "solicitacao_id", "paciente_id", "data_evento", "tipo_evento",
    "resultado", "valor_numerico", "descricao", "origem", "tipo_evento_norm",
    "resultado_norm", "duplicata_conteudo", "solicitacao_na_fila",
    "paciente_coincide_fila",
]
COLUNAS_PROCS_NORM = [
    "procedimento_id", "procedimento", "especialidade", "porte", "risco_cirurgico",
    "duracao_media_min", "necessita_uti", "porte_norm", "necessita_uti_norm",
    "especialidade_norm",
]
COLUNAS_SWALIS_NORM = ["classe", "descricao", "prazo_maximo_dias", "exemplos", "classe_norm"]


# --- aplicação sobre o dataset real --------------------------------------

@pytest.fixture(scope="session")
def app():
    return create_app("teste")


@pytest.fixture()
def cliente(app):
    return app.test_client()


@pytest.fixture(scope="session")
def repo(app):
    return app.extensions["repository"]


# --- dataset sintético, para controlar os valores exatos ------------------

def _escrever(caminho, colunas, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas)
        escritor.writeheader()
        for linha in linhas:
            completa = dict.fromkeys(colunas, "")
            completa.update({k: "" if v is None else str(v) for k, v in linha.items()})
            escritor.writerow(completa)


@pytest.fixture()
def dataset_sintetico(tmp_path):
    """Monta um diretório no formato de dataset/normalizado/ com linhas controladas."""

    def montar(fila=(), eventos=(), procedimentos=(), swalis=()):
        destino = tmp_path / "normalizado"
        _escrever(destino / "fila_cirurgica_normalizada.csv", COLUNAS_FILA_NORM, fila)
        _escrever(destino / "eventos_clinicos_normalizados.csv", COLUNAS_EVENTOS_NORM, eventos)
        _escrever(destino / "procedimentos_normalizados.csv", COLUNAS_PROCS_NORM, procedimentos)
        _escrever(destino / "swalis_normalizado.csv", COLUNAS_SWALIS_NORM, swalis)
        return destino

    return montar


@pytest.fixture()
def app_sintetico(dataset_sintetico):
    """Aplicação apontada para um dataset sintético."""

    def montar(**tabelas):
        destino = dataset_sintetico(**tabelas)
        return create_app("teste", DATASET_DIR=Path(destino))

    return montar
