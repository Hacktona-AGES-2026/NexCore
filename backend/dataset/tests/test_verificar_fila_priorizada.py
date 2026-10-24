"""Testes do verificador oficial da regra de ouro.

`verificar_fila_priorizada.py` vem dos organizadores e é a referência de
autoconferência da entrega, então é exercitado como caixa-preta — por
subprocess, sem importar nem alterar o script. Os testes documentam o que ele
trata como erro (sai com 1) e o que trata como aviso (sai com 0).
"""
from pathlib import Path
import csv
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "verificar_fila_priorizada.py"

pytestmark = pytest.mark.lento


def escrever_saida(destino, linhas):
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)
    return destino


def verificar(dataset_dir, linhas_saida, nome="fila_priorizada.csv"):
    arquivo = escrever_saida(Path(dataset_dir) / nome, linhas_saida)
    processo = subprocess.run(
        [sys.executable, str(SCRIPT), str(arquivo), "--dataset", str(dataset_dir)],
        capture_output=True,
        text=True,
    )
    return processo


def posicoes(*ids):
    return [
        {"solicitacao_id": sol, "posicao": i, "justificativa": f"motivo de {sol}"}
        for i, sol in enumerate(ids, start=1)
    ]


@pytest.fixture()
def onco_e_calmo(mini_dataset, fabrica_fila):
    """Dois casos: um oncológico (CID C*) e um sem nenhuma urgência clínica."""
    return mini_dataset([
        fabrica_fila(
            solicitacao_id="SOL-ONCO", paciente_id="PAC-1", cid_principal="C50.4",
            intensidade_dor_eva="5", justificativa_clinica="Carcinoma ductal invasivo.",
        ),
        fabrica_fila(
            solicitacao_id="SOL-CALMO", paciente_id="PAC-2", cid_principal="K40.9",
            intensidade_dor_eva="2", limitacao_funcional="nenhuma",
            justificativa_clinica="Hernia redutivel, assintomatica.",
        ),
    ])


# --- regra de ouro --------------------------------------------------------

def test_oncologico_na_frente_passa(onco_e_calmo):
    r = verificar(onco_e_calmo, posicoes("SOL-ONCO", "SOL-CALMO"))
    assert r.returncode == 0, r.stdout
    assert "OK" in r.stdout
    assert "REGRA DE OURO VIOLADA" not in r.stdout


def test_oncologico_atras_de_caso_sem_urgencia_viola(onco_e_calmo):
    r = verificar(onco_e_calmo, posicoes("SOL-CALMO", "SOL-ONCO"))
    assert r.returncode == 1
    assert "REGRA DE OURO VIOLADA" in r.stdout
    assert "SOL-ONCO" in r.stdout


def test_dor_alta_tira_o_caso_de_sem_urgencia(mini_dataset, fabrica_fila):
    """Com dor EVA > 3 o caso não é 'sem urgência', então não ancora a violação."""
    base = mini_dataset([
        fabrica_fila(solicitacao_id="SOL-ONCO", cid_principal="C18.7"),
        fabrica_fila(solicitacao_id="SOL-DOR", cid_principal="K40.9",
                     intensidade_dor_eva="8", limitacao_funcional="moderada"),
    ])
    r = verificar(base, posicoes("SOL-DOR", "SOL-ONCO"))
    assert r.returncode == 0, r.stdout


def test_palavra_de_alarme_no_texto_tira_de_sem_urgencia(mini_dataset, fabrica_fila):
    base = mini_dataset([
        fabrica_fila(solicitacao_id="SOL-ONCO", cid_principal="C18.7"),
        fabrica_fila(solicitacao_id="SOL-ALARME", cid_principal="K40.9",
                     intensidade_dor_eva="1",
                     justificativa_clinica="Hernia com episodios de encarceramento."),
    ])
    r = verificar(base, posicoes("SOL-ALARME", "SOL-ONCO"))
    assert r.returncode == 0, r.stdout


def test_cid_de_urgencia_tira_de_sem_urgencia(mini_dataset, fabrica_fila):
    base = mini_dataset([
        fabrica_fila(solicitacao_id="SOL-ONCO", cid_principal="C18.7"),
        fabrica_fila(solicitacao_id="SOL-URG", cid_principal="K40.3",
                     intensidade_dor_eva="1"),
    ])
    r = verificar(base, posicoes("SOL-URG", "SOL-ONCO"))
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize(
    "tipo_evento, resultado",
    [
        ("pronto_socorro", "atendido"),
        ("internacao", "alta"),
        ("biopsia", "positivo"),
        ("exame_imagem", "progressao"),
        ("consulta_reavaliacao", "piora"),
    ],
)
def test_evento_de_piora_tira_de_sem_urgencia(
    mini_dataset, fabrica_fila, fabrica_evento, tipo_evento, resultado
):
    base = mini_dataset(
        [
            fabrica_fila(solicitacao_id="SOL-ONCO", cid_principal="C18.7"),
            fabrica_fila(solicitacao_id="SOL-PIORA", cid_principal="K40.9",
                         intensidade_dor_eva="1"),
        ],
        [fabrica_evento(evento_id="EVT-1", solicitacao_id="SOL-PIORA",
                        tipo_evento=tipo_evento, resultado=resultado)],
    )
    r = verificar(base, posicoes("SOL-PIORA", "SOL-ONCO"))
    assert r.returncode == 0, r.stdout


def test_evento_irrelevante_nao_protege_de_violacao(
    mini_dataset, fabrica_fila, fabrica_evento
):
    base = mini_dataset(
        [
            fabrica_fila(solicitacao_id="SOL-ONCO", cid_principal="C18.7"),
            fabrica_fila(solicitacao_id="SOL-CALMO", cid_principal="K40.9",
                         intensidade_dor_eva="1"),
        ],
        [fabrica_evento(evento_id="EVT-1", solicitacao_id="SOL-CALMO",
                        tipo_evento="contato_telefonico", resultado="atendeu")],
    )
    r = verificar(base, posicoes("SOL-CALMO", "SOL-ONCO"))
    assert r.returncode == 1
    assert "REGRA DE OURO VIOLADA" in r.stdout


# --- formato --------------------------------------------------------------

def test_coluna_obrigatoria_ausente(onco_e_calmo):
    linhas = [{"solicitacao_id": "SOL-ONCO", "posicao": 1}]
    r = verificar(onco_e_calmo, linhas)
    assert r.returncode == 1
    assert "justificativa" in r.stdout


def test_solicitacao_repetida(onco_e_calmo):
    linhas = posicoes("SOL-ONCO", "SOL-CALMO")
    linhas[1]["solicitacao_id"] = "SOL-ONCO"
    r = verificar(onco_e_calmo, linhas)
    assert r.returncode == 1
    assert "repetido" in r.stdout


def test_posicao_repetida(onco_e_calmo):
    linhas = posicoes("SOL-ONCO", "SOL-CALMO")
    linhas[1]["posicao"] = 1
    r = verificar(onco_e_calmo, linhas)
    assert r.returncode == 1
    assert "posicao repetida" in r.stdout


def test_posicao_nao_inteira(onco_e_calmo):
    linhas = posicoes("SOL-ONCO", "SOL-CALMO")
    linhas[0]["posicao"] = "1.5"
    r = verificar(onco_e_calmo, linhas)
    assert r.returncode == 1
    assert "inteira" in r.stdout


def test_id_inexistente_na_fila(onco_e_calmo):
    r = verificar(onco_e_calmo, posicoes("SOL-ONCO", "SOL-CALMO", "SOL-FANTASMA"))
    assert r.returncode == 1
    assert "não existem na fila" in r.stdout


# --- avisos (não bloqueiam) ----------------------------------------------

def test_justificativa_vazia_e_apenas_aviso(onco_e_calmo):
    linhas = posicoes("SOL-ONCO", "SOL-CALMO")
    linhas[1]["justificativa"] = "   "
    r = verificar(onco_e_calmo, linhas)
    assert r.returncode == 0, r.stdout
    assert "sem justificativa" in r.stdout


def test_cobertura_incompleta_e_apenas_aviso(onco_e_calmo):
    r = verificar(onco_e_calmo, posicoes("SOL-ONCO"))
    assert r.returncode == 0, r.stdout
    assert "não aparecem no arquivo" in r.stdout


def test_oncologico_fora_do_arquivo_gera_aviso(onco_e_calmo):
    r = verificar(onco_e_calmo, posicoes("SOL-CALMO"))
    assert r.returncode == 0, r.stdout
    assert "oncológicos ficaram FORA" in r.stdout


# --- indicadores ----------------------------------------------------------

def test_relatorio_traz_indicadores(onco_e_calmo):
    r = verificar(onco_e_calmo, posicoes("SOL-ONCO", "SOL-CALMO"))
    assert "posição mediana dos oncológicos" in r.stdout
    assert "2 posições" in r.stdout
