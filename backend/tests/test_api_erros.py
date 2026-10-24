"""Caminhos de erro e bordas da API: nenhum deles deve devolver HTML."""
import pytest

from app import create_app


def test_rota_inexistente_devolve_json(cliente):
    resposta = cliente.get("/api/nao-existe")
    assert resposta.status_code == 404
    assert resposta.is_json
    assert resposta.get_json()["error"]["status"] == 404


def test_metodo_nao_permitido_devolve_json(cliente):
    resposta = cliente.post("/api/queue")
    assert resposta.status_code == 405
    assert resposta.get_json()["error"]["status"] == 405


@pytest.mark.parametrize(
    "query, trecho",
    [
        ("page=0", "page"),
        ("page=-1", "page"),
        ("size=0", "size"),
        ("size=99999", "size"),
        ("size=x", "size"),
        ("min_days=-1", "min_days"),
        ("min_age=-5", "min_age"),
        ("oncological=maybe", "oncological"),
    ],
)
def test_parametro_invalido_vira_400_com_o_nome_do_campo(cliente, query, trecho):
    resposta = cliente.get(f"/api/queue?{query}")
    assert resposta.status_code == 400
    assert trecho in resposta.get_json()["error"]["message"]


@pytest.mark.parametrize("valor", ["yes", "no", "sim", "nao", "true", "false", "1", "0"])
def test_booleano_aceita_as_formas_documentadas(cliente, valor):
    assert cliente.get(f"/api/queue?oncological={valor}").status_code == 200


def test_parametro_vazio_e_ignorado(cliente):
    corpo = cliente.get("/api/queue?specialty=&oncological=&min_days=").get_json()
    assert corpo["pagination"]["total"] == 941


def test_pagina_alem_do_fim_vem_vazia_sem_erro(cliente):
    corpo = cliente.get("/api/queue?size=50&page=999").get_json()
    assert corpo["data"] == []
    assert corpo["pagination"]["total"] == 941


def test_filtro_sem_resultado_devolve_lista_vazia(cliente):
    corpo = cliente.get("/api/queue?min_days=99999").get_json()
    assert corpo["data"] == []
    assert corpo["pagination"]["pages"] == 0


def test_ordem_ascendente(cliente):
    corpo = cliente.get("/api/queue?order=asc&size=5").get_json()
    esperas = [r["dias_em_fila"] for r in corpo["data"]]
    assert esperas == sorted(esperas)
    assert corpo["sort"]["descending"] is False


def test_id_de_solicitacao_aceita_minusculas(cliente):
    corpo = cliente.get("/api/queue/sol-2025-00048").get_json()
    assert corpo["request"]["solicitacao_id"] == "SOL-2025-00048"


def test_eventos_de_solicitacao_inexistente_dao_404(cliente):
    assert cliente.get("/api/queue/SOL-0000-00000/events").status_code == 404


def test_eventos_de_paciente(cliente, repo):
    paciente = next(
        e["paciente_id"] for e in repo.events if e.get("paciente_id")
    )
    corpo = cliente.get(f"/api/patients/{paciente}/events").get_json()
    assert corpo["pagination"]["total"] >= 1
    assert all(e["paciente_id"] == paciente for e in corpo["data"])


def test_paciente_sem_evento_da_404(cliente):
    assert cliente.get("/api/patients/PAC-99999/events").status_code == 404


def test_cabecalhos_de_cors_em_toda_resposta(cliente):
    for rota in ("/", "/api/health", "/api/queue?size=1"):
        resposta = cliente.get(rota)
        assert resposta.headers["Access-Control-Allow-Origin"] == "*"
        assert "GET" in resposta.headers["Access-Control-Allow-Methods"]


def test_cors_tambem_na_resposta_de_erro(cliente):
    resposta = cliente.get("/api/queue?page=0")
    assert resposta.status_code == 400
    assert resposta.headers["Access-Control-Allow-Origin"] == "*"


def test_excecao_inesperada_vira_500_em_json():
    app = create_app("teste", PROPAGATE_EXCEPTIONS=False)

    @app.get("/explode")
    def explode():
        raise RuntimeError("falha simulada")

    resposta = app.test_client().get("/explode")
    assert resposta.status_code == 500
    assert resposta.get_json()["error"]["message"] == "internal server error"
    assert "falha simulada" not in resposta.get_data(as_text=True)


def test_indice_lista_as_rotas_da_api(cliente):
    rotas = cliente.get("/").get_json()["routes"]
    for rota in ("/api/health", "/api/queue", "/api/statistics", "/api/procedures"):
        assert rota in rotas
    assert not any(r.startswith("/static") for r in rotas)
