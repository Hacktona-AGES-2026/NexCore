"""Testes da regra do Neco (app/prioritization): classe, índice, regra de ouro.

As funções são puras, então a maior parte monta um registro à mão com as colunas
do dataset normalizado e confere o resultado exato. Os testes contra o dataset
real travam os números de referência do contrato (29/171/202/247/292) e o que
importa para o entregável: a ordem passa no verificador oficial.
"""
from collections import Counter
import csv
from pathlib import Path
import subprocess
import sys

import pytest

from app.prioritization import assess, golden_rule_violation, rank, relocate
from app.prioritization import rules, text

REF = "2026-10-23"
VERIFICADOR = Path(__file__).resolve().parents[1] / "dataset" / "verificar_fila_priorizada.py"


def registro(**campos):
    base = {
        "solicitacao_id": "SOL-1",
        "cid_principal": "K40.9",
        "cid_principal_norm": "K409",
        "oncologico_cid": False,
        "flag_oncologico_norm": False,
        "intensidade_dor_eva": 2,
        "limitacao_funcional_norm": "leve",
        "dias_em_fila": 100,
        "justificativa_clinica": "Hernia inguinal redutivel.",
        "observacoes": None,
    }
    base.update(campos)
    return base


def evento(tipo, resultado, data="2026-09-01", duplicata=False):
    return {
        "tipo_evento_norm": tipo,
        "resultado_norm": resultado,
        "data_evento": data,
        "duplicata_conteudo": duplicata,
    }


def classe(reg, eventos=()):
    return assess(reg, list(eventos), REF)["urgency_class"]


# --- classe de urgência --------------------------------------------------

def test_cancer_com_ida_recente_ao_ps_e_a1():
    reg = registro(cid_principal_norm="C509", oncologico_cid=True)
    assert classe(reg, [evento("pronto_socorro", "observacao")]) == "A1"


def test_cancer_com_progressao_antiga_ainda_e_a1():
    reg = registro(cid_principal_norm="C509", oncologico_cid=True)
    assert classe(reg, [evento("exame_imagem", "progressao", data="2024-01-01")]) == "A1"


def test_cancer_sem_piora_e_a2():
    assert classe(registro(cid_principal_norm="C509", oncologico_cid=True)) == "A2"


def test_biopsia_positiva_com_cid_benigno_e_a2():
    assert classe(registro(), [evento("biopsia", "positivo")]) == "A2"


@pytest.mark.parametrize("campos", [
    {"cid_principal_norm": "D371"},
    {"cid_principal_norm": "R91"},
    {"intensidade_dor_eva": 7},
    {"limitacao_funcional_norm": "grave"},
])
def test_criterios_da_classe_b(campos):
    assert classe(registro(**campos)) == "B"


def test_duas_idas_recentes_ao_ps_sao_b():
    eventos = [evento("pronto_socorro", "alta"), evento("internacao", "alta")]
    assert classe(registro(), eventos) == "B"


def test_ida_ao_ps_fora_da_janela_de_180_dias_nao_conta():
    assert classe(registro(), [evento("pronto_socorro", "alta", data="2026-01-01")]) == "D"


@pytest.mark.parametrize("campos", [{"intensidade_dor_eva": 4}, {"limitacao_funcional_norm": "moderada"}])
def test_criterios_da_classe_c(campos):
    assert classe(registro(**campos)) == "C"


def test_uma_ida_recente_ao_ps_e_c():
    assert classe(registro(), [evento("pronto_socorro", "alta")]) == "C"


def test_sem_nada_relevante_e_d():
    assert classe(registro()) == "D"


def test_evento_duplicado_nao_conta_duas_vezes():
    eventos = [evento("pronto_socorro", "alta"), evento("pronto_socorro", "alta", duplicata=True)]
    assert classe(registro(), eventos) == "C"


def test_dor_vazia_nao_vira_zero_no_motivo():
    """Nada é imputado: sem EVA, o motivo não inventa uma dor."""
    a = assess(registro(intensidade_dor_eva=None, limitacao_funcional_norm="moderada"), [], REF)
    assert a["class_reason"] == "limitação funcional moderada"


# --- índice ----------------------------------------------------------------

def test_fatores_seguem_as_formulas_do_contrato():
    reg = registro(
        cid_principal="C54.1", cid_principal_norm="C541", oncologico_cid=True,
        intensidade_dor_eva=9, limitacao_funcional_norm="nenhuma", dias_em_fila=264,
    )
    eventos = [evento("internacao", "alta"), evento("exame_imagem", "progressao")]
    a = assess(reg, eventos, REF)
    assert a["factors"] == {"urgency": 40, "wait": 25, "events": 14, "symptoms": pytest.approx(7.2)}
    assert a["score"] == pytest.approx(86.2)


def test_espera_satura_em_duas_vezes_o_prazo():
    a = assess(registro(dias_em_fila=10_000), [], REF)
    assert a["factors"]["wait"] == 25


def test_eventos_tem_teto_de_20():
    eventos = [evento("pronto_socorro", "alta")] * 5
    assert assess(registro(), eventos, REF)["factors"]["events"] == 20


# --- "sem urgência clínica" do verificador ---------------------------------

def test_registro_calmo_e_sem_urgencia():
    assert rules.no_clinical_urgency(registro(), [])


@pytest.mark.parametrize("campos", [
    {"oncologico_cid": True, "cid_principal_norm": "C509"},
    {"intensidade_dor_eva": 4},
    {"limitacao_funcional_norm": "moderada"},
    {"cid_principal_norm": "I200"},
    {"justificativa_clinica": "Episodio de sincope ha duas semanas."},
])
def test_cada_criterio_tira_o_sem_urgencia(campos):
    assert not rules.no_clinical_urgency(registro(**campos), [])


@pytest.mark.parametrize("ev", [
    evento("pronto_socorro", "alta", data="2020-01-01"),
    evento("biopsia", "positivo"),
    evento("exame_imagem", "progressao"),
    evento("consulta_reavaliacao", "piora"),
])
def test_evento_de_alarme_em_qualquer_data_tira_o_sem_urgencia(ev):
    assert not rules.no_clinical_urgency(registro(), [ev])


def test_classe_d_nao_e_o_mesmo_que_sem_urgencia():
    """A regra de ouro usa a definição do verificador, não "classe D"."""
    reg = registro(justificativa_clinica="Hernia com dor, risco de encarceramento.")
    a = assess(reg, [], REF)
    assert a["urgency_class"] == "D"
    assert a["no_urgency"] is False


# --- avisos e destaques ----------------------------------------------------

def test_sinal_de_gravidade_no_texto_gera_aviso_fora_do_topo():
    reg = registro(justificativa_clinica="Angina instavel, lesao de tronco de coronaria esquerda.")
    avisos = assess(reg, [], REF)["warnings"]
    assert avisos[0]["text"].startswith('O texto cita "lesao de tronco de coronaria esquerda"')


def test_angina_sem_evento_que_confirme_gera_aviso():
    avisos = assess(registro(cid_principal_norm="I208"), [], REF)["warnings"]
    assert any("Angina" in a["text"] for a in avisos)


def test_flag_divergente_do_cid_gera_aviso():
    avisos = assess(registro(flag_oncologico_norm=True), [], REF)["warnings"]
    assert any("Usei o CID" in a["text"] for a in avisos)


def test_desistencia_gera_aviso_critico_e_pede_confirmacao():
    a = assess(registro(), [evento("contato_telefonico", "desistiu")], REF)
    assert a["pending_confirmation"] is True
    assert a["warnings"][-1]["level"] == "critical"


def test_destaques_nao_se_sobrepoem():
    nota = "Angina instavel, internacao recente, lesao de tronco de coronaria esquerda."
    marcas = text.highlights(nota, "Pct relata que foi ao PS 2x no ultimo mes por dor.")
    por_campo = {}
    for m in marcas:
        por_campo.setdefault(m["field"], []).append(m)
    for lista in por_campo.values():
        for a, b in zip(lista, lista[1:]):
            assert a["end"] <= b["start"]
    assert nota[marcas[0]["start"]:marcas[0]["end"]] == "Angina instavel"
    assert {m["kind"] for m in marcas} >= {"urgency", "events", "red_flag"}


# --- ordenação, travas e regra de ouro -------------------------------------

def avaliacao(cls, score, onco=False, calmo=False):
    return {"urgency_class": cls, "score": score, "oncological": onco, "no_urgency": calmo}


def test_ordena_por_classe_depois_indice_depois_ordem_de_entrada():
    a = {
        "X": avaliacao("C", 50), "Y": avaliacao("A2", 10), "Z": avaliacao("C", 60),
        "W": avaliacao("C", 60),
    }
    assert rank(a) == ["Y", "Z", "W", "X"]


def test_travado_fica_na_posicao_definida():
    a = {"A": avaliacao("A1", 90), "B": avaliacao("B", 50), "C": avaliacao("D", 10)}
    assert rank(a, locked={"C": 1}) == ["C", "A", "B"]


def test_relocate_desloca_os_demais():
    assert relocate(["A", "B", "C", "D"], "D", 2) == ["A", "D", "B", "C"]
    assert relocate(["A", "B", "C", "D"], "A", 3) == ["B", "C", "A", "D"]


def test_oncologico_abaixo_de_calmo_viola():
    a = {"O": avaliacao("A2", 30, onco=True), "K": avaliacao("D", 10, calmo=True)}
    assert golden_rule_violation(["K", "O"], a) == ("O", "K")
    assert golden_rule_violation(["O", "K"], a) is None


def test_oncologico_abaixo_de_classe_d_nao_calmo_e_permitido():
    a = {"O": avaliacao("A2", 30, onco=True), "D": avaliacao("D", 10, calmo=False)}
    assert golden_rule_violation(["D", "O"], a) is None


# --- dataset real ----------------------------------------------------------

@pytest.fixture(scope="module")
def avaliacoes(repo):
    return {
        r["solicitacao_id"]: assess(r, repo.events_for_request(r["solicitacao_id"]), REF)
        for r in repo.queue
    }


def test_classes_batem_com_a_referencia_do_contrato(avaliacoes):
    contagem = Counter(a["urgency_class"] for a in avaliacoes.values())
    assert contagem == {"A1": 29, "A2": 171, "B": 202, "C": 247, "D": 292}


def test_sem_urgencia_no_dataset_real(avaliacoes):
    assert sum(a["no_urgency"] for a in avaliacoes.values()) == 237
    assert sum(a["oncological"] for a in avaliacoes.values()) == 177


def test_ordem_automatica_respeita_a_regra_de_ouro(avaliacoes):
    assert golden_rule_violation(rank(avaliacoes), avaliacoes) is None


def test_topo_da_fila_bate_com_a_referencia(avaliacoes):
    assert rank(avaliacoes)[:3] == ["SOL-2026-00098", "SOL-2026-00229", "SOL-2026-00781"]


@pytest.mark.lento
def test_ordem_passa_no_verificador_oficial(avaliacoes, tmp_path):
    destino = tmp_path / "fila_priorizada.csv"
    with destino.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["solicitacao_id", "posicao", "justificativa"])
        for posicao, rid in enumerate(rank(avaliacoes), start=1):
            a = avaliacoes[rid]
            escritor.writerow([rid, posicao, f"{a['urgency_class']}: {a['class_reason']}"])
    processo = subprocess.run(
        [sys.executable, str(VERIFICADOR), str(destino)], capture_output=True, text=True,
    )
    assert processo.returncode == 0, processo.stdout + processo.stderr
    assert "REGRA DE OURO VIOLADA" not in processo.stdout
    assert "OK" in processo.stdout
