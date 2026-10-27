"""Testes do painel de impacto e do CSV oficial (GET /painel/impacto, GET /fila/exportar).

As funções de `app.regulation.impact` são puras: montam-se entradas à mão no
formato QueueEntry e confere-se o texto exato. Nas rotas, o verificador oficial
é trocado por um falso para conferir formato, cache e erro; os testes `lento`
rodam o verificador de verdade e travam os números de `dados/impacto_referencia.json`
(0 violações no Neco, 177 na fila manual).
"""
import csv
import io
import json
from pathlib import Path

import pytest

from app import create_app
from app.regulation import impact, verifier

H = "/v1/hospitais/hsl"
REFERENCIA = Path(__file__).resolve().parent / "dados" / "impacto_referencia.json"
JUSTIFICATIVA = "Angina instável confirmada com a cardiologia, lesão de tronco."
SAIDA_OK = (
    "Arquivo: fila_priorizada.csv  |  3 posições  |  fila: 3 solicitações\n"
    "- posição mediana dos oncológicos: 1 de 3\n"
    "- oncológicos no primeiro terço: 100%\n\nRESULTADO: OK — regra de ouro respeitada e formato válido"
)
SAIDA_ERRO = (
    "Arquivo: fila_priorizada.csv  |  3 posições\n"
    "- pacientes sem urgência clínica no último terço: 49%\n"
    "ERRO:  REGRA DE OURO VIOLADA: 7 paciente(s) oncológico(s) abaixo...\n\nRESULTADO: 1 erro(s)"
)


def entrada(rid, posicao, cls="D", manual="baixa", dias=100, **extra):
    base = {
        "id": rid,
        "position": posicao,
        "name": "Ana Maria Souza",
        "procedure": "Colectomia",
        "urgencyClass": cls,
        "classReason": "sem dor, limitação ou piora relevantes",
        "daysWaiting": dias,
        "score": 12.5,
        "factors": [
            {"key": "urgency", "value": 4, "max": 40},
            {"key": "wait", "value": 3.5, "max": 25},
            {"key": "events", "value": 0, "max": 20},
            {"key": "symptoms", "value": 5, "max": 12},
        ],
        "warnings": [],
        "locked": False,
    }
    if manual is not None:
        base["manualPriority"] = manual
    base.update(extra)
    return base


def sinais(visitas=0, piora=0, progressao=False):
    return {"recent_visits": visitas, "worsening": piora, "progression": progressao}


def ler_csv(texto):
    return list(csv.DictReader(io.StringIO(texto)))


# --- justificativa e CSV -----------------------------------------------------

def test_justificativa_tem_classe_espera_e_indice():
    texto = impact.justification(entrada("SOL-1", 1))
    assert texto == (
        "Classe D (Eletivo, SWALIS adaptado): sem dor, limitação ou piora relevantes. "
        "Espera de 100 dias, dentro do prazo de 360. "
        "Índice 12,5/97 (urgência 4, espera 3,5, eventos 0, sintomas 5)."
    )


def test_justificativa_cita_atraso_eventos_avisos_e_ajuste_manual():
    e = entrada(
        "SOL-1", 1, cls="A1", dias=40, locked=True,
        warnings=[{"level": "critical", "text": "Call center informou desistência."}],
    )
    texto = impact.justification(e, sinais(visitas=2, piora=1, progressao=True))
    assert "Eventos: 2 PS/internação em 180 dias; 1 relato(s) de piora; imagem com progressão." in texto
    assert "Espera de 40 dias, 25 além do prazo de 15." in texto
    assert "Call center informou desistência." in texto
    assert texto.endswith("Posição ajustada manualmente pela regulação; motivo no relatório de auditoria.")


def test_csv_oficial_tem_o_cabecalho_do_entregavel_e_escapa_aspas():
    e = entrada("SOL-1", 1, classReason='dor "intensa", (8/10)')
    linhas = ler_csv(impact.official_csv([e]))
    assert list(linhas[0]) == ["solicitacao_id", "posicao", "justificativa"]
    assert linhas[0]["solicitacao_id"] == "SOL-1" and linhas[0]["posicao"] == "1"
    assert 'dor "intensa", (8/10)' in linhas[0]["justificativa"]


# --- fila manual e relatório -------------------------------------------------

def test_fila_manual_prioridade_depois_espera_depois_ordem_do_dataset():
    entradas = [
        entrada("SOL-A", 1, manual="baixa", dias=900),
        entrada("SOL-B", 2, manual="alta", dias=10),
        entrada("SOL-C", 3, manual=None, dias=999),
        entrada("SOL-D", 4, manual="alta", dias=50),
        entrada("SOL-E", 5, manual="alta", dias=50),
    ]
    ordem_dataset = ["SOL-E", "SOL-A", "SOL-B", "SOL-C", "SOL-D", "SOL-FORA"]
    assert impact.manual_order(entradas, ordem_dataset) == ["SOL-E", "SOL-D", "SOL-B", "SOL-A", "SOL-C"]


def test_csv_manual_explica_a_prioridade_e_a_vazia():
    entradas = [entrada("SOL-A", 1, manual=None, dias=7)]
    linha = ler_csv(impact.manual_csv(entradas, ["SOL-A"]))[0]
    assert linha["justificativa"] == "Prioridade manual: vazia; 7 dias em fila."


def test_le_os_indicadores_da_saida_do_verificador():
    ok = impact.verifier_run(True, SAIDA_OK)
    assert ok == {
        "ok": True, "output": SAIDA_OK, "violacoes": 0, "medianaOnco": 1,
        "oncoPrimeiroTerco": 100, "psPrimeiraMetade": None, "calmosUltimoTerco": None,
    }
    erro = impact.verifier_run(False, SAIDA_ERRO)
    assert erro["violacoes"] == 7 and erro["calmosUltimoTerco"] == 49 and erro["medianaOnco"] is None


def test_relatorio_monta_matriz_destaques_e_quem_mais_subiu():
    entradas = [
        entrada("SOL-A", 1, cls="A1", manual="baixa", name="Bruno Lima", procedure="Mastectomia",
                classReason="câncer confirmado pelo CID C50.9 com piora recente"),
        entrada("SOL-B", 2, cls="A2", manual=None),
        entrada("SOL-C", 3, cls="D", manual="alta"),
    ]
    manual = ["SOL-C", "SOL-B", "SOL-A"]
    corpo = impact.report(entradas, manual, {"ok": True}, {"ok": False})
    assert corpo["source"] == "backend" and corpo["total"] == 3
    assert corpo["verifier"] == {"neco": {"ok": True}, "manual": {"ok": False}}
    assert [m["cls"] for m in corpo["matrix"]] == ["A1", "A2", "B", "C", "D"]
    assert corpo["matrix"][0] == {"cls": "A1", "alta": 0, "media": 0, "baixa": 1, "vazia": 0}
    assert corpo["matrix"][1]["vazia"] == 1 and corpo["matrix"][4]["alta"] == 1
    assert corpo["headline"] == {
        "a1Total": 1, "a1Low": 1, "urgentTotal": 2, "urgentLow": 2, "dTotal": 1, "dHigh": 1,
    }
    assert [m["id"] for m in corpo["movers"]] == ["SOL-A", "SOL-B", "SOL-C"]
    assert corpo["movers"][0] == {
        "id": "SOL-A", "initials": "B.L.", "procedure": "Mastectomia", "cls": "A1",
        "reason": "câncer confirmado pelo CID C50.9 com piora recente",
        "manualPriority": "baixa", "manualPosition": 3, "necoPosition": 1,
    }


# --- rotas -------------------------------------------------------------------

@pytest.fixture()
def app_nova():
    return create_app("teste")


@pytest.fixture()
def verificador_falso(monkeypatch):
    chamadas = []

    def falso(texto, dataset_dir):
        chamadas.append(texto)
        return (True, SAIDA_OK) if len(chamadas) % 2 else (False, SAIDA_ERRO)

    monkeypatch.setattr(verifier, "run", falso)
    return chamadas


def test_exportar_devolve_a_fila_atual_em_csv(cliente):
    resposta = cliente.get(f"{H}/fila/exportar")
    assert resposta.status_code == 200
    assert resposta.mimetype == "text/csv"
    assert 'filename="fila_priorizada.csv"' in resposta.headers["Content-Disposition"]
    linhas = ler_csv(resposta.get_data(as_text=True))
    fila = cliente.get(f"{H}/fila").get_json()["entries"]
    assert [(l["solicitacao_id"], int(l["posicao"])) for l in linhas] == [(e["id"], e["position"]) for e in fila]
    assert all(l["justificativa"].startswith("Classe ") for l in linhas)


def test_exportar_respeita_a_reordenacao_manual(app_nova):
    cliente = app_nova.test_client()
    resposta = cliente.post(f"{H}/fila/SOL-2025-00274/reordenar", json={
        "position": 210, "reason": "Critério clínico não considerado", "justification": JUSTIFICATIVA,
    })
    assert resposta.status_code == 200
    linhas = ler_csv(cliente.get(f"{H}/fila/exportar").get_data(as_text=True))
    movida = linhas[209]
    assert movida["solicitacao_id"] == "SOL-2025-00274"
    assert "ajustada manualmente pela regulação" in movida["justificativa"]


def test_impacto_roda_o_verificador_nas_duas_filas(app_nova, verificador_falso):
    corpo = app_nova.test_client().get(f"{H}/painel/impacto").get_json()
    assert corpo["source"] == "backend" and corpo["total"] == 941
    assert corpo["verifier"]["neco"]["ok"] is True
    assert corpo["verifier"]["manual"]["violacoes"] == 7
    neco, manual = verificador_falso
    assert ler_csv(neco)[0]["justificativa"].startswith("Classe A1")
    assert ler_csv(manual)[0]["justificativa"].startswith("Prioridade manual: alta")
    assert sum(corpo["matrix"][i][p] for i in range(5) for p in impact.PRIORITIES) == 941
    assert len(corpo["movers"]) == impact.MOVERS


def test_impacto_reaproveita_o_calculo_ate_a_fila_mudar(app_nova, verificador_falso):
    cliente = app_nova.test_client()
    cliente.get(f"{H}/painel/impacto")
    cliente.get(f"{H}/painel/impacto")
    assert len(verificador_falso) == 2
    cliente.post(f"{H}/fila/SOL-2025-00274/reordenar", json={
        "position": 210, "reason": "Critério clínico não considerado", "justification": JUSTIFICATIVA,
    })
    cliente.get(f"{H}/painel/impacto")
    assert len(verificador_falso) == 4


def test_impacto_sem_verificador_responde_503_sem_vazar_o_erro(app_nova, monkeypatch):
    def quebrado(texto, dataset_dir):
        raise verifier.VerifierUnavailable("ModuleNotFoundError: No module named 'pandas'")

    monkeypatch.setattr(verifier, "run", quebrado)
    resposta = app_nova.test_client().get(f"{H}/painel/impacto")
    assert resposta.status_code == 503
    assert resposta.get_json() == {"detail": "O verificador oficial não está disponível neste servidor."}


def test_verificador_ausente_vira_indisponivel(tmp_path):
    with pytest.raises(verifier.VerifierUnavailable):
        verifier.run("solicitacao_id,posicao,justificativa\n", tmp_path, script=tmp_path / "nao_existe.py")


# --- contra o verificador oficial de verdade ----------------------------------

@pytest.mark.lento
def test_csv_exportado_passa_no_verificador_oficial(cliente, app):
    texto = cliente.get(f"{H}/fila/exportar").get_data(as_text=True)
    ok, saida = verifier.run(texto, app.config["VERIFIER_DATASET_DIR"])
    assert ok, saida
    assert "Arquivo: fila_priorizada.csv" in saida and "/tmp" not in saida


@pytest.mark.lento
def test_impacto_real_bate_com_a_referencia(app_nova):
    corpo = app_nova.test_client().get(f"{H}/painel/impacto").get_json()
    referencia = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    assert corpo["verifier"]["neco"]["ok"] is True and corpo["verifier"]["neco"]["violacoes"] == 0
    assert corpo["verifier"]["manual"]["ok"] is False and corpo["verifier"]["manual"]["violacoes"] == 177
    for chave in ("total", "matrix", "headline"):
        assert corpo[chave] == referencia[chave], chave
    for fila in ("neco", "manual"):
        numeros = {k: v for k, v in corpo["verifier"][fila].items() if k != "output"}
        assert numeros == {k: v for k, v in referencia["verifier"][fila].items() if k != "output"}
