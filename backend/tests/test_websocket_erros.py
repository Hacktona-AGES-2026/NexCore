"""Caminhos de erro do canal.

Duas invariantes valem para todos eles: o cliente recebe um frame `error` com o
status e o nome do campo, e a conexão **continua aberta** — um comando torto não
pode custar o socket, porque pode haver cálculo longo em andamento nele.
"""
import pytest

from app.realtime import actions, origin_allowed
from app.realtime.actions import Progress


# --- frames malformados ---------------------------------------------------

@pytest.mark.parametrize("cru, trecho", [
    ("isso não é json", "valid JSON"),
    ("[1, 2, 3]", "JSON object"),
    ('"só uma string"', "JSON object"),
    ("{}", "'action' is required"),
    ('{"action": ""}', "'action' is required"),
    ('{"action": 42}', "'action' is required"),
    ('{"action": "queue.list", "params": []}', "'params' must be an object"),
    ('{"action": "queue.list", "id": {"a": 1}}', "'id' must be"),
])
def test_frame_malformado_vira_error(conversa, cru, trecho):
    erro = conversa(cru).primeiro("error")["error"]
    assert erro["status"] == 400
    assert trecho in erro["message"]


def test_frame_binario_e_recusado(app):
    from app.realtime import limits
    from app.realtime.channel import handle
    from tests.conftest import WsFalso

    ws = WsFalso()
    handle(ws, b"\x00\x01", app.extensions["repository"], limits(app.config))
    assert "binary" in ws.enviados[0]["error"]["message"]


def test_acao_desconhecida_devolve_404_e_lista_o_que_existe(conversa):
    erro = conversa({"action": "queue.magica"}).primeiro("error")["error"]
    assert erro["status"] == 404
    assert "queue.magica" in erro["message"]
    assert "queue.list" in erro["details"]["actions"]


def test_erro_ecoa_o_id_do_comando(conversa):
    frame = conversa({"id": "c9", "action": "queue.magica"}).primeiro("error")
    assert frame["id"] == "c9"
    assert frame["action"] == "queue.magica"


def test_erro_antes_de_conhecer_a_acao_vem_com_action_nulo(conversa):
    frame = conversa("{ sem json").primeiro("error")
    assert frame["action"] is None
    assert frame["id"] is None


def test_id_numerico_e_aceito_e_devolvido(pedir, conversa):
    frame = conversa({"id": 7, "action": "catalog.swalis"}).primeiro("result")
    assert frame["id"] == 7


# --- parâmetros inválidos -------------------------------------------------

@pytest.mark.parametrize("params, trecho", [
    ({"page": 0}, "page"),
    ({"page": -1}, "page"),
    ({"page": "abc"}, "page"),
    ({"size": 0}, "size"),
    ({"size": 99999}, "size"),
    ({"size": "x"}, "size"),
    ({"min_days": -1}, "min_days"),
    ({"min_age": -5}, "min_age"),
    ({"oncological": "maybe"}, "oncological"),
    ({"specialty": 10}, "specialty"),
    ({"size": True}, "size"),
])
def test_parametro_invalido_vira_400_com_o_nome_do_campo(conversa, params, trecho):
    comando = {"id": "c1", "action": "queue.list", "params": params}
    erro = conversa(comando).primeiro("error")["error"]
    assert erro["status"] == 400
    assert trecho in erro["message"]


@pytest.mark.parametrize("valor", [
    True, False, "yes", "no", "sim", "nao", "true", "false", "1", "0",
])
def test_booleano_aceita_json_e_as_formas_documentadas(conversa, valor):
    comando = {"action": "queue.list", "params": {"oncological": valor, "size": 1}}
    assert conversa(comando).primeiro("result")


def test_parametro_vazio_e_ignorado(pedir):
    payload = pedir("queue.list", specialty="", oncological="", min_days="")
    assert payload["pagination"]["total"] == 941


def test_pagina_alem_do_fim_vem_vazia_sem_erro(pedir):
    payload = pedir("queue.list", size=50, page=999)
    assert payload["data"] == []
    assert payload["pagination"]["total"] == 941


def test_filtro_sem_resultado_devolve_lista_vazia(pedir):
    payload = pedir("queue.list", min_days=99999)
    assert payload["data"] == []
    assert payload["pagination"]["pages"] == 0


def test_priorizacao_sem_ninguem_na_fila_nao_divide_por_zero(pedir):
    payload = pedir("queue.prioritize", min_days=99999)
    assert payload["total"] == 0
    assert payload["data"] == []


# --- identificadores ------------------------------------------------------

@pytest.mark.parametrize("action, campo", [
    ("queue.request", "request_id"),
    ("queue.events", "request_id"),
    ("patient.events", "patient_id"),
])
def test_identificador_obrigatorio(conversa, action, campo):
    erro = conversa({"action": action}).primeiro("error")["error"]
    assert erro["status"] == 400
    assert campo in erro["message"]


@pytest.mark.parametrize("action, params", [
    ("queue.request", {"request_id": "SOL-9999-99999"}),
    ("queue.events", {"request_id": "SOL-0000-00000"}),
    ("patient.events", {"patient_id": "PAC-99999"}),
])
def test_registro_inexistente_devolve_404(conversa, action, params):
    erro = conversa({"action": action, "params": params}).primeiro("error")["error"]
    assert erro["status"] == 404


# --- a conexão sobrevive --------------------------------------------------

def test_erro_nao_derruba_a_conexao(conversa):
    ws = conversa(
        {"id": "ruim", "action": "queue.magica"},
        {"id": "bom", "action": "catalog.swalis"},
    )
    assert [f["type"] for f in ws.frames] == ["error", "result"]
    assert ws.primeiro("result")["payload"]["total"] == 5


def test_excecao_inesperada_vira_500_sem_vazar_a_mensagem(app, monkeypatch, conversa):
    def explode(repository, params, limits):
        raise RuntimeError("falha simulada com dado sensível")

    monkeypatch.setitem(actions._REGISTRY, "test.explode", explode)
    ws = conversa(
        {"id": "x", "action": "test.explode"},
        {"id": "y", "action": "catalog.swalis"},
    )

    erro = ws.primeiro("error")["error"]
    assert erro["status"] == 500
    assert erro["message"] == "internal server error"
    assert "sensível" not in str(ws.enviados)
    assert ws.tipos("result"), "a conexão segue atendendo depois de um bug"


def test_acao_que_falha_no_meio_do_progresso_reporta_erro(monkeypatch, conversa):
    def meia_falha(repository, params, limits):
        yield Progress(1, 2, "indo")
        raise RuntimeError("quebrou no meio")

    monkeypatch.setitem(actions._REGISTRY, "test.meia", meia_falha)
    ws = conversa({"id": "m", "action": "test.meia"})
    assert [f["type"] for f in ws.frames] == ["progress", "error"]


def test_acao_que_rende_coisa_errada_e_bug_nosso_nao_do_cliente(monkeypatch, conversa):
    def torta(repository, params, limits):
        yield "só uma string"

    monkeypatch.setitem(actions._REGISTRY, "test.torta", torta)
    erro = conversa({"action": "test.torta"}).primeiro("error")["error"]
    assert erro["status"] == 500


def test_registrar_nome_repetido_falha_cedo():
    with pytest.raises(RuntimeError, match="already registered"):
        actions.action("queue.list")(lambda *a: None)


# --- Origin: o handshake não passa por CORS -------------------------------

@pytest.mark.parametrize("origin, permitido, esperado", [
    (None, "http://localhost:5173", True),          # curl, teste, outro serviço
    ("http://localhost:5173", "*", True),
    ("http://evil.example", "*", True),             # default de desenvolvimento
    ("http://localhost:5173", "http://localhost:5173", True),
    ("http://evil.example", "http://localhost:5173", False),
    ("http://localhost:5173", "http://a.dev, http://localhost:5173", True),
    ("http://evil.example", "", False),
])
def test_origin_permitido(origin, permitido, esperado):
    assert origin_allowed(origin, permitido) is esperado
