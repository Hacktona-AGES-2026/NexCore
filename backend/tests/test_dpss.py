"""Tests for the isolated, experimental DPSS extension."""

import csv

import pytest

from app.prioritization.dps import calculate_priority
from app.prioritization.dpss import extend_priority, prioritize


SWALIS = [
    {"classe_norm": "A1", "prazo_maximo_dias": 15},
    {"classe_norm": "A2", "prazo_maximo_dias": 21},
    {"classe_norm": "B", "prazo_maximo_dias": 60},
    {"classe_norm": "C", "prazo_maximo_dias": 180},
    {"classe_norm": "D", "prazo_maximo_dias": 360},
]


def request(request_id="SOL-1", **changes):
    row = {
        "solicitacao_id": request_id,
        "paciente_id": f"PAC-{request_id[-1]}",
        "procedimento_id": "PROC001",
        "procedimento": "Procedimento teste",
        "especialidade": "Cirurgia Geral",
        "cid_principal": "K40.9",
        "cid_principal_norm": "K409",
        "cid_descricao": "Hernia sem complicacao",
        "municipio": "Porto Alegre",
        "municipio_norm": "Porto Alegre",
        "uf": "RS",
        "id_municipio": "4314902",
        "oncologico_cid": False,
        "flag_diabetico_norm": False,
        "flag_piora_clinica_norm": False,
        "intensidade_dor_eva": 2,
        "limitacao_funcional_norm": "nenhuma",
        "asa": 1,
        "data_entrada_fila": "2026-01-01",
        "distancia_hospital_km": 75,
    }
    row.update(changes)
    return row


SOCIOECONOMIC = [
    {
        "id_municipio": "4314902",
        "s_vulnerabilidade": 0.8,
        "source_version": "IBGE-test",
    }
]
BURDEN = [
    {
        "cid_prefix_norm": "K40",
        "health_state": "test state",
        "disability_weight_norm": 0.5,
        "source_version": "GBD-test",
    }
]


def dps(row=None):
    row = row or request()
    return calculate_priority(row, [], SWALIS, "2026-04-11")


def test_formula_dpss_e_ajuste_de_incapacidade():
    row = request()
    result = extend_priority(dps(row), row, SOCIOECONOMIC, BURDEN, 0.25)
    c = result["clinical_factor"]["value"]
    expected_s = 0.8 * 0.8 + 0.2 * (75 / 150)
    expected_dpss = 100 / 360 * (1 + c + 0.25 * expected_s)
    assert result["dpss"]["score"] == pytest.approx(expected_dpss, abs=1e-6)
    assert result["burden_adjustment"]["final_score"] == pytest.approx(
        expected_dpss * 0.5, abs=1e-6
    )
    assert result["ranking_basis"] == "final_score"
    assert result["reference_coverage"]["complete"] is True


def test_referencia_ausente_usa_fallback_socioeconomico_0_5():
    row = request()
    original = dps(row)
    result = extend_priority(original, row)
    assert result["dpss"]["score"] is not None
    assert result["dpss"]["socioeconomic_vulnerability"] == 0.5
    assert result["burden_adjustment"]["final_score"] is None
    assert result["ranking_score"] == result["dpss"]["score"]
    assert result["ranking_basis"] == "dpss_without_disability_weight"
    assert result["reference_coverage"]["socioeconomic_fallback"] is True
    assert result["requires_human_review"] is True
    assert "fallback neutro 0,5" in result["justification"]


def test_sem_peso_de_incapacidade_ordena_pelo_dpss_calculado():
    row = request()
    result = extend_priority(dps(row), row, SOCIOECONOMIC, [], 0.25)
    assert result["dpss"]["computed"] is True
    assert result["ranking_score"] == result["dpss"]["score"]
    assert result["ranking_basis"] == "dpss_without_disability_weight"


def test_match_de_cid_usa_prefixo_mais_especifico():
    row = request()
    references = BURDEN + [
        {"cid_prefix_norm": "K409", "disability_weight_norm": 0.7}
    ]
    result = extend_priority(dps(row), row, SOCIOECONOMIC, references)
    assert result["burden_adjustment"]["disability_weight"] == 0.7


def test_match_territorial_ambiguo_e_rejeitado():
    row = request()
    result = extend_priority(dps(row), row, SOCIOECONOMIC * 2, BURDEN)
    assert result["dpss"]["computed"] is False
    assert "socioeconomic reference: ambiguous" in result["data_quality"]["alerts"]


def test_uf_desambigua_municipios_homonimos():
    row = request(uf="RS", id_municipio=None)
    references = [
        {
            "municipio_norm": "Porto Alegre",
            "uf": "RS",
            "s_vulnerabilidade": 0.8,
        },
        {
            "municipio_norm": "Porto Alegre",
            "uf": "SC",
            "s_vulnerabilidade": 0.2,
        }
    ]
    result = extend_priority(dps(row), row, references, BURDEN)
    assert result["dpss"]["socioeconomic_vulnerability"] == pytest.approx(0.74)


def test_recalcula_s_em_toda_execucao_e_ignora_valor_materializado_antigo():
    row = request(
        s_vulnerabilidade=0.01,
        evfam_dificuldade_financeira=1,
        evfam_uso_continuo_medicamentos=1,
        evfam_ausencia_apoio_familiar=0,
        evfam_vulnerabilidade_habitacional=0,
        distancia_hospital_km=150,
    )
    result = extend_priority(dps(row), row, SOCIOECONOMIC, BURDEN)
    expected = 0.8 * 0.5 + 0.2 * 1.0
    assert result["dpss"]["socioeconomic_vulnerability"] == expected
    assert result["dpss"]["social_source"] == "evfam_br"
    assert result["dpss"]["geographic_access_barrier"] == 1.0


def test_nova_solicitacao_sem_s_precalculado_recebe_indicador_hibrido():
    row = request(distancia_hospital_km=30)
    assert "s_vulnerabilidade" not in row
    result = extend_priority(dps(row), row, SOCIOECONOMIC, BURDEN)
    expected = 0.8 * 0.8 + 0.2 * (30 / 150)
    assert result["dpss"]["socioeconomic_vulnerability"] == pytest.approx(expected)
    assert result["dpss"]["computed"] is True


def test_peso_socioeconomico_fora_do_intervalo_e_rejeitado():
    with pytest.raises(ValueError, match="between 0 and 1"):
        extend_priority(dps(), request(), SOCIOECONOMIC, BURDEN, 1.1)


def test_faixa_de_seguranca_a2_permanece_acima_da_fila_geral():
    general = request("SOL-1", data_entrada_fila="2020-01-01")
    oncology = request(
        "SOL-2",
        cid_principal="C50.4",
        cid_principal_norm="C504",
        oncologico_cid=True,
        data_entrada_fila="2026-04-01",
    )
    dps_ranking = [dps(general), dps(oncology)]
    result = prioritize(dps_ranking, [general, oncology])
    assert [item["solicitacao_id"] for item in result] == ["SOL-2", "SOL-1"]


def test_websocket_dpss_expoe_cobertura_e_preserva_fila(pedir, app):
    body = pedir("queue.prioritize.dpss", as_of="2026-10-23")
    assert body["strategy"] == "dpss_experimental"
    assert body["model"]["replaces_default_dps"] is False
    assert body["coverage"] == {
        "complete": 0,
        "incomplete": 924,
        "ratio": 0.0,
        "socioeconomic_reference_rows": 5570,
        "disease_burden_reference_rows": 0,
    }
    first = body["data"][0]
    assert set(app.extensions["repository"].queue[0]) <= set(first)
    assert first["ranking_basis"] == "dpss_without_disability_weight"
    assert first["reference_coverage"]["socioeconomic_fallback"] is False
    assert first["position"] == 1


def test_websocket_dpss_calcula_com_referencias_sinteticas(app_sintetico):
    app = app_sintetico(
        fila=[request()],
        swalis=SWALIS,
        socioeconomic=SOCIOECONOMIC,
        disease_burden=BURDEN,
    )
    from app.realtime import limits
    from app.realtime.channel import serve
    from tests.conftest import WsFalso

    ws = WsFalso(
        [{"action": "queue.prioritize.dpss", "params": {"as_of": "2026-04-11"}}]
    )
    serve(ws, app.extensions["repository"], limits(app.config))
    body = ws.payload()
    assert body["coverage"]["complete"] == 1
    assert body["data"][0]["ranking_basis"] == "final_score"


def test_servico_reativo_publica_nova_fila_quando_evento_chega(app_sintetico):
    app = app_sintetico(
        fila=[request()],
        swalis=SWALIS,
        socioeconomic=SOCIOECONOMIC,
        disease_burden=BURDEN,
    )
    from app.realtime.dpss_live import ReactiveDpss

    live = ReactiveDpss(app.extensions["repository"], "hsl")
    subscription = live.subscribe()
    before = subscription.get(0)
    assert before["type"] == "queue.dpss.snapshot"
    assert before["data"][0]["swalis_class"] == "D"

    path = app.config["DATASET_DIR"] / "eventos_clinicos_normalizados.csv"
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "evento_id", "solicitacao_id", "paciente_id", "data_evento",
                "tipo_evento", "resultado", "valor_numerico", "descricao", "origem",
                "tipo_evento_norm", "resultado_norm", "duplicata_conteudo",
                "solicitacao_na_fila", "paciente_coincide_fila",
            ],
        )
        writer.writerow(
            {
                "evento_id": "EVT-DPSS-NEW",
                "solicitacao_id": "SOL-1",
                "paciente_id": "PAC-1",
                "data_evento": "2026-03-01",
                "tipo_evento_norm": "exame_imagem",
                "resultado_norm": "progressao",
                "duplicata_conteudo": "nao",
                "solicitacao_na_fila": "sim",
                "paciente_coincide_fila": "sim",
            }
        )

    assert live.poll_once() is True
    after = subscription.get(0)
    assert after["type"] == "queue.dpss.snapshot"
    assert after["revision"] == before["revision"] + 1
    assert after["reason"] == "normalized_dataset_changed"
    assert after["data"][0]["swalis_class"] == "A2"
    assert after["data"][0]["dpss_score"] > before["data"][0]["dpss_score"]


@pytest.mark.parametrize("value", ["nan", "inf", -0.1, 1.1])
def test_websocket_rejeita_peso_socioeconomico_invalido(conversa, value):
    ws = conversa(
        {
            "action": "queue.prioritize.dpss",
            "params": {"socioeconomic_weight": value},
        }
    )
    assert ws.primeiro("error")["error"]["status"] == 400
