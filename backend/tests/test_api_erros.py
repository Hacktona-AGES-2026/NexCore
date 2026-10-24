"""Caminhos de erro e bordas da API: nenhum deles deve devolver HTML."""
import pytest

from app import create_app


def test_rota_inexistente_devolve_json(cliente):
    resposta = cliente.get("/api/nao-existe")
    assert resposta.status_code == 404
    assert resposta.is_json
    assert resposta.get_json()["erro"]["status"] == 404


def test_metodo_nao_permitido_devolve_json(cliente):
    resposta = cliente.post("/api/fila")
    assert resposta.status_code == 405
    assert resposta.get_json()["erro"]["status"] == 405


@pytest.mark.parametrize(
    "query, trecho",
    [
        ("pagina=0", "pagina"),
        ("pagina=-1", "pagina"),
        ("tamanho=0", "tamanho"),
        ("tamanho=99999", "tamanho"),
        ("tamanho=x", "tamanho"),
        ("dias_minimo=-1", "dias_minimo"),
        ("idade_minima=-5", "idade_minima"),
        ("oncologico=talvez", "oncologico"),
    ],
)
def test_parametro_invalido_vira_400_com_o_nome_do_campo(cliente, query, trecho):
    resposta = cliente.get(f"/api/fila?{query}")
    assert resposta.status_code == 400
    assert trecho in resposta.get_json()["erro"]["mensagem"]


@pytest.mark.parametrize("valor", ["sim", "nao", "true", "false", "1", "0"])
def test_booleano_aceita_as_formas_documentadas(cliente, valor):
    assert cliente.get(f"/api/fila?oncologico={valor}").status_code == 200


def test_parametro_vazio_e_ignorado(cliente):
    corpo = cliente.get("/api/fila?especialidade=&oncologico=&dias_minimo=").get_json()
    assert corpo["paginacao"]["total"] == 941


def test_pagina_alem_do_fim_vem_vazia_sem_erro(cliente):
    corpo = cliente.get("/api/fila?tamanho=50&pagina=999").get_json()
    assert corpo["dados"] == []
    assert corpo["paginacao"]["total"] == 941


def test_filtro_sem_resultado_devolve_lista_vazia(cliente):
    corpo = cliente.get("/api/fila?dias_minimo=99999").get_json()
    assert corpo["dados"] == []
    assert corpo["paginacao"]["paginas"] == 0


def test_ordem_ascendente(cliente):
    corpo = cliente.get("/api/fila?ordem=asc&tamanho=5").get_json()
    esperas = [r["dias_em_fila"] for r in corpo["dados"]]
    assert esperas == sorted(esperas)
    assert corpo["ordenacao"]["descendente"] is False


def test_id_de_solicitacao_aceita_minusculas(cliente):
    corpo = cliente.get("/api/fila/sol-2025-00048").get_json()
    assert corpo["solicitacao"]["solicitacao_id"] == "SOL-2025-00048"


def test_eventos_de_solicitacao_inexistente_dao_404(cliente):
    assert cliente.get("/api/fila/SOL-0000-00000/eventos").status_code == 404


def test_eventos_de_paciente(cliente, repo):
    paciente = next(
        e["paciente_id"] for e in repo.events if e.get("paciente_id")
    )
    corpo = cliente.get(f"/api/pacientes/{paciente}/eventos").get_json()
    assert corpo["paginacao"]["total"] >= 1
    assert all(e["paciente_id"] == paciente for e in corpo["dados"])


def test_paciente_sem_evento_da_404(cliente):
    assert cliente.get("/api/pacientes/PAC-99999/eventos").status_code == 404


def test_cabecalhos_de_cors_em_toda_resposta(cliente):
    for rota in ("/", "/api/saude", "/api/fila?tamanho=1"):
        resposta = cliente.get(rota)
        assert resposta.headers["Access-Control-Allow-Origin"] == "*"
        assert "GET" in resposta.headers["Access-Control-Allow-Methods"]


def test_cors_tambem_na_resposta_de_erro(cliente):
    resposta = cliente.get("/api/fila?pagina=0")
    assert resposta.status_code == 400
    assert resposta.headers["Access-Control-Allow-Origin"] == "*"


def test_excecao_inesperada_vira_500_em_json():
    app = create_app("teste", PROPAGATE_EXCEPTIONS=False)

    @app.get("/explode")
    def explode():
        raise RuntimeError("falha simulada")

    resposta = app.test_client().get("/explode")
    assert resposta.status_code == 500
    assert resposta.get_json()["erro"]["mensagem"] == "erro interno do servidor"
    assert "falha simulada" not in resposta.get_data(as_text=True)


def test_indice_lista_as_rotas_da_api(cliente):
    rotas = cliente.get("/").get_json()["rotas"]
    for rota in ("/api/saude", "/api/fila", "/api/estatisticas", "/api/procedimentos"):
        assert rota in rotas
    assert not any(r.startswith("/static") for r in rotas)
