"""Tests for the dynamic and auditable DPS prioritization module."""
import csv
import io

import pytest

from app.prioritization.dps import calculate_priority, prioritize
from app.prioritization.export import ORDER_FIELDS, export_repository
from app.prioritization.pipeline import (
    DpsStep,
    PipelineSources,
    PrioritizationPipeline,
)


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
        "cid_descricao": "Hernia sem complicacao",
        "oncologico_cid": False,
        "flag_diabetico_norm": False,
        "flag_piora_clinica_norm": False,
        "intensidade_dor_eva": 2,
        "limitacao_funcional_norm": "nenhuma",
        "asa": 1,
        "data_entrada_fila": "2026-01-01",
    }
    row.update(changes)
    return row


def event(event_id="EVT-1", **changes):
    row = {
        "evento_id": event_id,
        "solicitacao_id": "SOL-1",
        "paciente_id": "PAC-1",
        "data_evento": "2026-03-01",
        "tipo_evento_norm": "exame_imagem",
        "resultado_norm": "progressao",
        "duplicata_conteudo": False,
        "solicitacao_na_fila": True,
        "paciente_coincide_fila": True,
    }
    row.update(changes)
    return row


def test_formula_dps_usa_t_m_e_c():
    result = calculate_priority(request(), [], SWALIS, "2026-04-11")
    assert result["waiting_days"] == 100
    assert result["swalis"]["class"] == "D"
    expected = 100 / 360 * (1 + result["clinical_factor"]["value"])
    assert result["dps"]["score"] == pytest.approx(expected, abs=1e-6)


def test_novo_evento_de_progressao_muda_swalis_e_score():
    before = calculate_priority(request(), [], SWALIS, "2026-04-11")
    after = calculate_priority(
        request(), [event()], SWALIS, "2026-04-11"
    )
    assert before["swalis"]["class"] == "D"
    assert after["swalis"]["class"] == "A2"
    assert after["dps"]["score"] > before["dps"]["score"]
    assert after["event_history"]["latest_imaging_result"] == "progressao"
    assert "EVT-1" in after["justification"]
    assert "01/03/2026" in after["justification"]
    assert "P=(t/M)×(1+c)" in after["justification"]


def test_novo_evento_clinico_muda_a_posicao_na_fila():
    first = request("SOL-1", data_entrada_fila="2026-01-01")
    second = request("SOL-2", data_entrada_fila="2026-03-01")
    before = prioritize(
        [first, second], {"SOL-1": [], "SOL-2": []}, SWALIS, "2026-04-11"
    )
    progression = event(
        solicitacao_id="SOL-2", paciente_id="PAC-2", data_evento="2026-04-01"
    )
    after = prioritize(
        [first, second],
        {"SOL-1": [], "SOL-2": [progression]},
        SWALIS,
        "2026-04-11",
    )
    assert [item["solicitacao_id"] for item in before] == ["SOL-1", "SOL-2"]
    assert [item["solicitacao_id"] for item in after] == ["SOL-2", "SOL-1"]


def test_evento_futuro_duplicado_ou_de_outro_paciente_nao_influencia():
    events = [
        event("EVT-FUT", data_evento="2027-01-01"),
        event("EVT-DUP", duplicata_conteudo=True),
        event("EVT-ERR", paciente_id="PAC-X", paciente_coincide_fila=False),
    ]
    result = calculate_priority(request(), events, SWALIS, "2026-04-11")
    assert result["swalis"]["class"] == "D"
    assert result["event_history"]["considered"] == 0
    assert result["event_history"]["rejected"] == {
        "future": 1,
        "duplicate": 1,
        "inconsistent_link": 1,
    }


def test_evento_hba1c_mais_novo_atualiza_vulnerabilidade():
    patient = request(
        flag_diabetico_norm=True,
        hba1c_ultima=7.0,
        data_hba1c_ultima="2026-01-15",
    )
    before = calculate_priority(patient, [], SWALIS, "2026-04-11")
    after = calculate_priority(
        patient,
        [
            event(
                tipo_evento_norm="hba1c",
                resultado_norm="resultado",
                valor_numerico=9.2,
            )
        ],
        SWALIS,
        "2026-04-11",
    )
    before_metabolic = before["clinical_factor"]["components"][
        "vulnerabilidade_metabolica"
    ]
    after_metabolic = after["clinical_factor"]["components"][
        "vulnerabilidade_metabolica"
    ]
    assert after_metabolic > before_metabolic
    assert after["dps"]["score"] > before["dps"]["score"]
    assert after["requires_human_review"] is True


def test_historico_de_pronto_socorro_influencia_sem_tratar_evento_antigo_como_agudo():
    old_er = event(
        "EVT-OLD",
        data_evento="2025-01-01",
        tipo_evento_norm="pronto_socorro",
        resultado_norm="atendido_liberado",
    )
    recent_er_1 = event(
        "EVT-R1",
        data_evento="2026-03-01",
        tipo_evento_norm="pronto_socorro",
        resultado_norm="atendido_liberado",
    )
    recent_er_2 = event(
        "EVT-R2",
        data_evento="2026-03-20",
        tipo_evento_norm="pronto_socorro",
        resultado_norm="observacao",
    )
    result = calculate_priority(
        request(), [old_er, recent_er_1, recent_er_2], SWALIS, "2026-04-11"
    )
    assert result["event_history"]["historical_er"] == 3
    assert result["event_history"]["recent_er_180d"] == 2
    assert result["swalis"]["class"] == "B"


def test_resultado_clinico_mais_recente_substitui_progressao_anterior():
    progression = event("EVT-1", data_evento="2026-02-01")
    stable = event(
        "EVT-2", data_evento="2026-03-01", resultado_norm="estavel"
    )
    result = calculate_priority(
        request(), [progression, stable], SWALIS, "2026-04-11"
    )
    assert result["event_history"]["latest_imaging_result"] == "estavel"
    assert result["swalis"]["class"] == "D"


def test_desistencia_mais_recente_retira_da_fila_ativa():
    withdrew = event(
        tipo_evento_norm="contato_telefonico", resultado_norm="desistiu"
    )
    ranking = prioritize(
        [request()], {"SOL-1": [withdrew]}, SWALIS, "2026-04-11"
    )
    assert ranking == []
    included = prioritize(
        [request()],
        {"SOL-1": [withdrew]},
        SWALIS,
        "2026-04-11",
        include_inactive=True,
    )
    assert included[0]["active"] is False


def test_faixa_de_seguranca_mantem_a2_antes_de_caso_estavel_antigo():
    oncological = request(
        "SOL-1", oncologico_cid=True, cid_principal="C50.4",
        data_entrada_fila="2026-04-01"
    )
    stable = request("SOL-2", data_entrada_fila="2020-01-01")
    ranking = prioritize(
        [stable, oncological], {"SOL-1": [], "SOL-2": []}, SWALIS, "2026-04-11"
    )
    assert [item["solicitacao_id"] for item in ranking] == ["SOL-1", "SOL-2"]


def test_websocket_priorizado_expoe_limites_e_aviso_de_validacao(pedir):
    body = pedir("queue.prioritize", specialty="oftalmologia")
    assert body["data"][0]["position"] == 1
    assert body["model"]["weights_validated_with_paprika"] is False
    assert body["model"]["clinical_use_authorized"] is False


def test_websocket_dps_retorna_fila_completa_em_ingles(pedir, app):
    body = pedir("queue.prioritize", as_of="2026-10-23")
    assert body["total"] == 924
    first = body["data"][0]
    assert list(first)[: len(ORDER_FIELDS)] == list(ORDER_FIELDS)
    assert set(app.extensions["repository"].queue[0]) <= set(first)
    assert first["position"] == 1
    assert first["justification"].strip()


def test_websocket_recarrega_evento_novo_sem_reiniciar(app_sintetico):
    rows = [request()]
    app = app_sintetico(fila=rows, swalis=SWALIS)
    from app.realtime import limits
    from app.realtime.channel import serve
    from tests.conftest import WsFalso

    def prioritize_over_socket():
        ws = WsFalso([{
            "action": "queue.prioritize",
            "params": {"as_of": "2026-04-11"},
        }])
        serve(ws, app.extensions["repository"], limits(app.config))
        return ws.payload()["data"][0]

    before = prioritize_over_socket()
    assert before["swalis_class"] == "D"

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
                "evento_id": "EVT-NEW",
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

    after = prioritize_over_socket()
    assert after["swalis_class"] == "A2"
    assert after["dps"] > before["dps"]


def test_exportacao_preserva_todos_os_campos_originais_da_fila(
    app_sintetico, tmp_path
):
    app = app_sintetico(fila=[request()], swalis=SWALIS)
    repository = app.extensions["repository"]
    output = tmp_path / "fila_priorizada.csv"
    export_repository(repository, output, as_of="2026-04-11")

    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        exported = next(reader)
        expected_fields = list(ORDER_FIELDS) + [
            field for field in repository.queue[0] if field not in ORDER_FIELDS
        ]
        assert reader.fieldnames == expected_fields

    assert exported["solicitacao_id"] == "SOL-1"
    assert exported["cid_principal"] == "K40.9"
    assert exported["position"] == "1"
    assert "P=(t/M)×(1+c)" in exported["justification"]


def test_pipeline_permite_etapa_posterior_usar_procedimentos():
    class ProcedureRiskStep:
        name = "procedure-risk-example"
        version = "test"

        def run(self, sources, records=None, **_):
            for item in records:
                procedure = sources.procedures_by_id[item["procedimento_id"]]
                item["procedure_risk_signal"] = procedure["risco_cirurgico"]
            return records

    sources = PipelineSources(
        queue=[request()],
        events_by_request={"SOL-1": []},
        procedures_by_id={"PROC001": {"risco_cirurgico": 4}},
        swalis=SWALIS,
    )
    result = PrioritizationPipeline([DpsStep(), ProcedureRiskStep()]).run(
        sources, as_of="2026-04-11"
    )
    assert result["records"][0]["procedure_risk_signal"] == 4
    assert [step["name"] for step in result["pipeline"]["steps"]] == [
        "dps",
        "procedure-risk-example",
    ]
