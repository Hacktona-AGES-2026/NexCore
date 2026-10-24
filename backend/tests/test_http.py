"""O que sobrou de HTTP depois da migração para WebSocket.

Só o health check e a raiz: toda leitura de dados virou ação no canal. O resto
destes testes guarda a promessa de que nenhum erro sai como HTML.
"""

from app import create_app


def test_saude_conta_o_dataset(cliente):
    corpo = cliente.get("/api/health").get_json()
    assert corpo["status"] == "ok"
    assert corpo["reference_date"] == "2026-10-23"
    assert corpo["dataset"]["queue"] == 941
    assert corpo["dataset"]["events"] == 1505


def test_saude_aponta_o_caminho_do_socket(cliente):
    """O front consulta isso antes de abrir a conexão."""
    assert cliente.get("/api/health").get_json()["websocket"] == "/ws"


def test_raiz_anuncia_o_transporte_e_as_acoes(cliente):
    corpo = cliente.get("/").get_json()
    assert corpo["transport"] == "websocket"
    assert corpo["websocket"] == "/ws"
    assert corpo["protocol"] == 1
    assert "queue.list" in corpo["actions"]
    assert "queue.prioritize" in corpo["actions"]


def test_os_endpoints_de_leitura_sairam(cliente):
    """A migração é remoção, não convivência: nenhum deles responde mais."""
    for rota in (
        "/api/queue", "/api/queue/SOL-2025-00048", "/api/statistics",
        "/api/procedures", "/api/references/swalis", "/api/references/filters",
        "/api/patients/PAC-00348/events",
    ):
        assert cliente.get(rota).status_code == 404, rota


def test_rotas_registradas_sao_so_as_duas(cliente):
    rotas = set(cliente.get("/").get_json()["routes"])
    assert rotas == {"/", "/api/health", "/ws"}


def test_rota_inexistente_devolve_json(cliente):
    resposta = cliente.get("/api/nao-existe")
    assert resposta.status_code == 404
    assert resposta.is_json
    assert resposta.get_json()["error"]["status"] == 404


def test_metodo_nao_permitido_devolve_json(cliente):
    resposta = cliente.post("/api/health")
    assert resposta.status_code == 405
    assert resposta.get_json()["error"]["status"] == 405


def test_cabecalhos_de_cors_nas_respostas(cliente):
    for rota in ("/", "/api/health"):
        resposta = cliente.get(rota)
        assert resposta.headers["Access-Control-Allow-Origin"] == "*"
        assert "GET" in resposta.headers["Access-Control-Allow-Methods"]


def test_excecao_inesperada_vira_500_em_json():
    app = create_app("teste", PROPAGATE_EXCEPTIONS=False)

    @app.get("/explode")
    def explode():
        raise RuntimeError("falha simulada")

    resposta = app.test_client().get("/explode")
    assert resposta.status_code == 500
    assert resposta.get_json()["error"]["message"] == "internal server error"
    assert "falha simulada" not in resposta.get_data(as_text=True)
