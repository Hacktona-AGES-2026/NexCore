"""O cliente de linha de comando (tools/ws_client.py).

A rede fica num duplo; o que é testado é o que erra na prática: conversão dos
pares chave=valor e o resumo que evita despejar 941 registros no terminal.
"""
import io
import json

import pytest

from tools.ws_client import conversar, describe, parse_params, summarize


class ClienteFalso:
    """Duplo do simple_websocket.Client: devolve frames prontos em ordem."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.enviados = []

    def send(self, texto):
        self.enviados.append(json.loads(texto))

    def receive(self, timeout=None):
        return json.dumps(self.frames.pop(0))


# --- conversão dos pares chave=valor -------------------------------------

@pytest.mark.parametrize("par, esperado", [
    ("size=3", {"size": 3}),
    ("oncological=true", {"oncological": True}),
    ("oncological=false", {"oncological": False}),
    ("oncological=TRUE", {"oncological": True}),
    ("priority=alta", {"priority": "alta"}),
    ("min_days=-1", {"min_days": -1}),
    ("percent=31.9", {"percent": 31.9}),
    ("specialty=", {"specialty": ""}),
    ("asa=null", {"asa": None}),
    ("request_id=SOL-2025-00048", {"request_id": "SOL-2025-00048"}),
])
def test_par_vira_valor_json(par, esperado):
    assert parse_params([par]) == esperado


def test_valor_com_igual_dentro_fica_inteiro():
    assert parse_params(["search=a=b"]) == {"search": "a=b"}


def test_varios_pares():
    assert parse_params(["size=2", "oncological=true"]) == {
        "size": 2, "oncological": True,
    }


def test_par_sem_igual_e_erro_de_uso():
    with pytest.raises(ValueError, match="chave=valor"):
        parse_params(["queue.list"])


# --- formatação ----------------------------------------------------------

def test_welcome_resume_a_conexao():
    linha = describe({
        "type": "welcome", "protocol": 1, "reference_date": "2026-10-23",
        "dataset": {"queue": 941}, "actions": ["a", "b"],
    })
    assert "protocolo 1" in linha
    assert "941 solicitações" in linha
    assert "2 ações" in linha


def test_progresso_mostra_fracao_e_rotulo():
    linha = describe({
        "type": "progress", "completed": 300, "total": 941,
        "percent": 31.9, "label": "ranqueando a fila",
    })
    assert "300/941" in linha
    assert "31.9%" in linha
    assert "ranqueando a fila" in linha


def test_erro_mostra_status_e_mensagem():
    linha = describe({
        "type": "error", "action": "queue.nope",
        "error": {"status": 404, "message": "unknown action"},
    })
    assert "404" in linha
    assert "unknown action" in linha


def test_frame_desconhecido_nao_explode():
    """O servidor pode ganhar um type novo; o cliente velho não deve quebrar."""
    assert "desconhecido" in describe({"type": "futuro", "x": 1})


def test_resumo_nao_despeja_a_fila_inteira():
    payload = {
        "data": [{"solicitacao_id": f"SOL-{i}"} for i in range(941)],
        "pagination": {"total": 941},
    }
    resumo = summarize(payload)
    assert resumo == "941 registros · total 941"
    assert "SOL-0" not in resumo


def test_resumo_denuncia_priorizacao_provisoria():
    resumo = summarize({
        "data": [], "provisional": True, "strategy": "placeholder:dias_em_fila",
    })
    assert "PROVISÓRIO" in resumo
    assert "placeholder:dias_em_fila" in resumo


def test_resumo_sem_data_lista_as_chaves():
    assert "total_requests" in summarize({"total_requests": 941, "by_priority": {}})


# --- a conversa ----------------------------------------------------------

def test_conversa_manda_o_comando_e_imprime_ate_o_result():
    cliente = ClienteFalso([
        {"type": "progress", "completed": 1, "total": 2, "percent": 50.0, "label": "x"},
        {"type": "result", "action": "queue.prioritize", "payload": {"data": [1, 2]}},
    ])
    saida = io.StringIO()

    final = conversar(cliente, "queue.prioritize", {"size": 2}, False, saida)

    assert cliente.enviados == [
        {"id": "cli", "action": "queue.prioritize", "params": {"size": 2}}
    ]
    assert final["type"] == "result"
    assert saida.getvalue().count("\n") == 2, "uma linha por frame"
    assert "1/2" in saida.getvalue()


def test_conversa_para_no_erro():
    cliente = ClienteFalso([
        {"type": "error", "action": "x", "error": {"status": 400, "message": "ruim"}},
        {"type": "result", "action": "x", "payload": {}},  # não deve ser lido
    ])
    final = conversar(cliente, "x", {}, False, io.StringIO())
    assert final["type"] == "error"
    assert len(cliente.frames) == 1, "parou sem consumir o frame seguinte"


def test_modo_raw_imprime_json_cru():
    cliente = ClienteFalso([{"type": "result", "action": "x", "payload": {"a": 1}}])
    saida = io.StringIO()
    conversar(cliente, "x", {}, True, saida)
    assert json.loads(saida.getvalue())["payload"] == {"a": 1}
