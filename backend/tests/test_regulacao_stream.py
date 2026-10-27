"""Testes do WebSocket que só empurra (/v1/ws) e do hub que o alimenta.

O laço `stream.serve` recebe o socket como argumento, então a maior parte usa um
duplo. A integração sobe o servidor numa porta efêmera para provar o que o duplo
não prova: rota registrada, snapshot ao conectar, e uma ação REST chegando como
frames para quem está conectado.
"""
import json
import threading

import pytest
from werkzeug.serving import make_server

from app import create_app
from app.regulation.hub import Hub
from app.regulation.stream import serve

simple_websocket = pytest.importorskip("simple_websocket")

TIMEOUT = 5
H = "/v1/hospitais/hsl"


class WsEmpurrado:
    """Duplo: guarda o que recebeu e pode "cair" depois de N frames."""

    def __init__(self, cai_depois=None):
        self.enviados = []
        self.connected = True
        self._cai_depois = cai_depois

    def send(self, texto):
        if self._cai_depois is not None and len(self.enviados) >= self._cai_depois:
            raise ConnectionError("cliente saiu")
        self.enviados.append(json.loads(texto))


# --- hub -------------------------------------------------------------------

def test_hub_entrega_a_todos_na_ordem():
    hub = Hub()
    a, b = hub.subscribe(), hub.subscribe()
    hub.publish({"n": 1})
    hub.publish({"n": 2})
    for s in (a, b):
        assert [s.get(0)["n"], s.get(0)["n"]] == [1, 2]
        assert s.get(0) is None


def test_cliente_atrasado_e_derrubado_para_ressincronizar():
    hub = Hub(max_pending=2)
    lento = hub.subscribe()
    for n in range(3):
        hub.publish({"n": n})
    assert lento.closed
    assert len(hub) == 0


# --- laço do socket --------------------------------------------------------

def test_serve_repassa_frames_e_para_quando_o_cliente_sai():
    hub = Hub()
    sub = hub.subscribe()
    sub.put({"type": "queue.snapshot"})
    sub.put({"type": "activity"})
    ws = WsEmpurrado()

    def sair():
        ws.connected = False

    threading.Timer(0.2, sair).start()
    serve(ws, sub, poll_seconds=0.05)
    assert [f["type"] for f in ws.enviados] == ["queue.snapshot", "activity"]
    assert sub.closed and len(hub) == 0


def test_serve_termina_quando_o_envio_falha():
    hub = Hub()
    sub = hub.subscribe()
    for n in range(3):
        sub.put({"n": n})
    ws = WsEmpurrado(cai_depois=1)
    serve(ws, sub, poll_seconds=0.05)
    assert len(ws.enviados) == 1
    assert sub.closed


# --- estado -> frames ------------------------------------------------------

@pytest.fixture()
def app_nova():
    return create_app("teste")


def test_inscricao_comeca_pelo_snapshot(app_nova):
    sub = app_nova.extensions["queue_state"].subscribe("hsl")
    frame = sub.get(0)
    assert frame["type"] == "queue.snapshot"
    assert frame["snapshot"]["total"] == 941


def test_reordenar_publica_patch_auditoria_e_atividade(app_nova):
    st = app_nova.extensions["queue_state"]
    sub = st.subscribe("hsl")
    sub.get(0)  # snapshot
    st.reorder("SOL-2025-00274", 210, "Critério clínico", "x" * 45)
    patch, auditoria, atividade = sub.get(0), sub.get(0), sub.get(0)
    assert patch["type"] == "queue.patch" and patch["total"] == 941
    assert {e["position"] for e in patch["entries"]} == set(range(22, 211))
    assert auditoria["type"] == "audit.appended" and auditoria["entry"]["kind"] == "manual"
    assert atividade == {
        "type": "activity", "at": auditoria["entry"]["at"],
        "text": "Marina moveu Gabriela de 22 para 210",
    }


def test_resolver_remocao_publica_removed(app_nova):
    st = app_nova.extensions["queue_state"]
    sub = st.subscribe("hsl")
    sub.get(0)
    st.resolve("PEN-0045", "merge")
    tipos = []
    while (frame := sub.get(0)) is not None:
        tipos.append(frame)
    assert [f["type"] for f in tipos[:3]] == ["pendency.resolved", "audit.appended", "queue.patch"]
    assert tipos[2]["removed"] == ["SOL-2024-00044"]
    assert tipos[2]["total"] == 940


# --- conexão de verdade ----------------------------------------------------

@pytest.fixture()
def servidor(app_nova):
    srv = make_server("127.0.0.1", 0, app_nova, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()
        thread.join(timeout=TIMEOUT)


def _receber(cliente):
    return json.loads(cliente.receive(timeout=TIMEOUT))


def test_conexao_real_recebe_snapshot_e_mudancas(servidor, app_nova):
    cliente = simple_websocket.Client(f"ws://{servidor}/v1/ws?hospital=hsl")
    try:
        snapshot = _receber(cliente)
        assert snapshot["type"] == "queue.snapshot"
        assert snapshot["snapshot"]["entries"][0]["id"] == "SOL-2023-00010"

        resposta = app_nova.test_client().post(
            f"{H}/fila/SOL-2025-00274/validar",
        )
        assert resposta.status_code == 200
        frame = _receber(cliente)
        assert frame["type"] == "audit.appended"
        assert frame["entry"]["kind"] == "validation"
    finally:
        cliente.close()


def test_hospital_errado_nao_recebe_nada(servidor):
    with pytest.raises(Exception):
        cliente = simple_websocket.Client(f"ws://{servidor}/v1/ws?hospital=outro")
        try:
            cliente.receive(timeout=TIMEOUT)
        finally:
            cliente.close()


def test_origin_recusada_nao_recebe_nada():
    app = create_app("teste", CORS_ORIGINS="http://localhost:5173")
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(Exception):
            cliente = simple_websocket.Client(
                f"ws://127.0.0.1:{srv.server_port}/v1/ws",
                headers={"Origin": "http://intruso.example"},
            )
            try:
                cliente.receive(timeout=TIMEOUT)
            finally:
                cliente.close()
    finally:
        srv.shutdown()
        thread.join(timeout=TIMEOUT)
