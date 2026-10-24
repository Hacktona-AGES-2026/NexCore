"""Fixtures com uma mini-fila sintética, para não tocar nos CSVs do repositório."""
from pathlib import Path
import csv

import pytest

DATASET = Path(__file__).resolve().parents[1]

COLUNAS_FILA = [
    "solicitacao_id", "paciente_id", "nome_paciente", "sexo", "idade", "municipio", "uf",
    "distancia_hospital_km", "procedimento_id", "procedimento", "especialidade",
    "cid_principal", "cid_descricao", "cid_secundario", "asa", "comorbidades",
    "intensidade_dor_eva", "limitacao_funcional", "justificativa_clinica", "observacoes",
    "data_entrada_fila", "dias_em_fila", "prioridade_regulacao",
    "data_ultima_revisao_prioridade", "flag_oncologico", "flag_diabetico",
    "flag_piora_clinica", "hba1c_ultima", "data_hba1c_ultima",
    "avaliacao_pre_anestesica", "exames_pre_op_validos",
]
COLUNAS_EVENTOS = [
    "evento_id", "solicitacao_id", "paciente_id", "data_evento", "tipo_evento",
    "resultado", "valor_numerico", "descricao", "origem",
]


def _linha_fila(**campos):
    base = dict.fromkeys(COLUNAS_FILA, "")
    base.update(
        solicitacao_id="SOL-2025-00001", paciente_id="PAC-00001",
        nome_paciente="Paciente Teste", sexo="F", idade="60",
        municipio="Porto Alegre", uf="RS", distancia_hospital_km="10",
        procedimento_id="PROC001", procedimento="Procedimento Teste",
        especialidade="Cirurgia Geral", cid_principal="K40.9",
        cid_descricao="Hernia inguinal", asa="2", intensidade_dor_eva="2",
        limitacao_funcional="nenhuma", justificativa_clinica="Quadro estavel.",
        data_entrada_fila="2025-01-01", dias_em_fila="600",
        prioridade_regulacao="baixa", flag_oncologico="nao",
        flag_diabetico="nao", flag_piora_clinica="nao",
        avaliacao_pre_anestesica="pendente", exames_pre_op_validos="nao",
    )
    base.update({k: str(v) for k, v in campos.items()})
    return base


def _linha_evento(**campos):
    base = dict.fromkeys(COLUNAS_EVENTOS, "")
    base.update(
        evento_id="EVT-000001", solicitacao_id="SOL-2025-00001",
        paciente_id="PAC-00001", data_evento="2026-09-01",
        tipo_evento="contato_telefonico", resultado="atendeu",
        descricao="Contato de rotina.", origem="call center",
    )
    base.update({k: str(v) for k, v in campos.items()})
    return base


def escrever_csv(caminho, colunas, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas)


@pytest.fixture()
def fabrica_fila():
    return _linha_fila


@pytest.fixture()
def fabrica_evento():
    return _linha_evento


@pytest.fixture()
def mini_dataset(tmp_path):
    """Monta um diretório com a mesma forma do dataset real e devolve um montador."""

    def montar(linhas_fila, linhas_eventos=(), procedimentos=None, swalis=None):
        escrever_csv(tmp_path / "fila_cirurgica.csv", COLUNAS_FILA, linhas_fila)
        escrever_csv(tmp_path / "eventos_clinicos.csv", COLUNAS_EVENTOS, linhas_eventos)
        escrever_csv(
            tmp_path / "procedimentos.csv",
            ["procedimento_id", "procedimento", "especialidade", "porte",
             "risco_cirurgico", "duracao_media_min", "necessita_uti"],
            procedimentos or [{
                "procedimento_id": "PROC001", "procedimento": "Procedimento Teste",
                "especialidade": "Cirurgia Geral", "porte": "medio",
                "risco_cirurgico": "2", "duracao_media_min": "60", "necessita_uti": "nao",
            }],
        )
        escrever_csv(
            tmp_path / "referencias" / "swalis.csv",
            ["classe", "descricao", "prazo_maximo_dias", "exemplos"],
            swalis or [{"classe": "A1", "descricao": "Risco de vida",
                        "prazo_maximo_dias": "15", "exemplos": "Neoplasia em progressao"}],
        )
        escrever_csv(
            tmp_path / "IBGE.csv",
            ["ano", "sigla_uf", "id_municipio", "rede", "tipo_localizacao", "inse"],
            [
                {"ano": "2021", "sigla_uf": "RS", "id_municipio": "4314902",
                 "rede": "0", "tipo_localizacao": "0", "inse": "5.0"},
                {"ano": "2021", "sigla_uf": "RS", "id_municipio": "4314902",
                 "rede": "2", "tipo_localizacao": "1", "inse": "3.0"},
                {"ano": "2021", "sigla_uf": "RS", "id_municipio": "4300604",
                 "rede": "0", "tipo_localizacao": "0", "inse": "2.0"},
            ],
        )
        escrever_csv(
            tmp_path / "referencias" / "municipios_ibge.csv",
            ["municipio_norm", "uf", "id_municipio", "municipio_ibge"],
            [
                {"municipio_norm": "Porto Alegre", "uf": "RS",
                 "id_municipio": "4314902", "municipio_ibge": "Porto Alegre"},
            ],
        )
        return tmp_path

    return montar


@pytest.fixture()
def colunas_fila():
    return list(COLUNAS_FILA)
