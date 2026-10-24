"""Conexão de verdade: handshake, frames pela rede, Origin recusada.

Os outros testes do canal usam um duplo do socket, que não prova que a rota está
registrada nem que o handshake fecha. Este sobe o servidor numa porta efêmera e
conecta com um cliente WebSocket real — é o teste que pega "esqueci de chamar
realtime.init_app".
"""
import json
import threading

import pytest
from werkzeug.serving import make_server

simple_websocket = pytest.importorskip("simple_websocket")

TIMEOUT = 5


@pytest.fixture()
def endereco(app):
    servidor = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{servidor.server_port}"
    finally:
        servidor.shutdown()
        thread.join(timeout=TIMEOUT)


def _receber(cliente):
    return json.loads(cliente.receive(timeout=TIMEOUT))


def test_conexao_real_recebe_welcome_e_responde_comando(endereco):
    cliente = simple_websocket.Client(f"ws://{endereco}/ws")
    try:
        welcome = _receber(cliente)
        assert welcome["type"] == "welcome"
        assert welcome["dataset"]["queue"] == 941

        cliente.send(json.dumps({"id": "r1", "action": "catalog.swalis"}))
        frame = _receber(cliente)
        assert frame["type"] == "result"
        assert frame["id"] == "r1"
        assert frame["payload"]["total"] == 5
    finally:
        cliente.close()


def test_calculo_longo_chega_em_pedacos_pela_rede(endereco):
    """O progresso tem de sair durante o cálculo, não empilhado no fim."""
    cliente = simple_websocket.Client(f"ws://{endereco}/ws")
    try:
        _receber(cliente)
        cliente.send(json.dumps({"id": "p1", "action": "queue.prioritize"}))

        tipos = []
        while True:
            frame = _receber(cliente)
            tipos.append(frame["type"])
            if frame["type"] in ("result", "error"):
                break

        assert tipos[-1] == "result"
        assert tipos.count("progress") >= 9, "941 em lotes de 100"
    finally:
        cliente.close()


def test_acentos_atravessam_a_rede_sem_escapar(endereco):
    cliente = simple_websocket.Client(f"ws://{endereco}/ws")
    try:
        _receber(cliente)
        cliente.send(json.dumps({
            "action": "queue.list",
            "params": {"specialty": "oftalmologia", "size": 1},
        }))
        registro = _receber(cliente)["payload"]["data"][0]
        assert registro["especialidade"] == "Oftalmologia"
    finally:
        cliente.close()


def test_origin_de_fora_e_recusada(app, endereco):
    """Handshake não passa por CORS: a checagem de Origin é nossa."""
    app.config["CORS_ORIGINS"] = "http://localhost:5173"
    try:
        cliente = simple_websocket.Client(
            f"ws://{endereco}/ws", headers={"Origin": "http://evil.example"}
        )
        with pytest.raises(simple_websocket.ConnectionClosed):
            cliente.receive(timeout=TIMEOUT)
    finally:
        app.config["CORS_ORIGINS"] = "*"


def test_origin_permitida_conecta(app, endereco):
    app.config["CORS_ORIGINS"] = "http://localhost:5173"
    try:
        cliente = simple_websocket.Client(
            f"ws://{endereco}/ws", headers={"Origin": "http://localhost:5173"}
        )
        assert _receber(cliente)["type"] == "welcome"
        cliente.close()
    finally:
        app.config["CORS_ORIGINS"] = "*"
