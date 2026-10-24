"""O canal WebSocket sobre o dataset real.

Os números travados aqui são os mesmos que a API HTTP travava antes da migração
(941 solicitações, 177 oncológicas por CID, 44 flags divergentes, 353 esperas
acima de 365 dias): o transporte mudou, os dados não.
"""

# --- handshake ------------------------------------------------------------

def test_welcome_abre_a_conexao_com_o_que_o_servidor_responde(conversa):
    ws = conversa()
    welcome = ws.welcome
    assert welcome["type"] == "welcome"
    assert welcome["protocol"] == 1
    assert welcome["reference_date"] == "2026-10-23"
    assert welcome["dataset"]["queue"] == 941
    assert "queue.list" in welcome["actions"]
    assert ws.frames == [], "nada mais deve sair antes do primeiro comando"


def test_cliente_fechando_encerra_sem_erro(conversa):
    assert len(conversa().enviados) == 1


# --- leituras da fila -----------------------------------------------------

def test_fila_pagina_e_ordena_por_espera(pedir):
    payload = pedir("queue.list", size=5)
    assert payload["pagination"]["total"] == 941
    esperas = [r["dias_em_fila"] for r in payload["data"]]
    assert len(esperas) == 5
    assert esperas == sorted(esperas, reverse=True)


def test_paginas_nao_se_repetem(pedir):
    primeira = pedir("queue.list", size=3, page=1)["data"]
    segunda = pedir("queue.list", size=3, page=2)["data"]
    assert {r["solicitacao_id"] for r in primeira} & {
        r["solicitacao_id"] for r in segunda
    } == set()


def test_filtro_oncologico_vem_do_cid(pedir):
    payload = pedir("queue.list", oncological=True, size=500)
    assert payload["pagination"]["total"] == 177
    assert all(r["oncologico_cid"] for r in payload["data"])


def test_filtro_combina_especialidade_e_espera(pedir):
    payload = pedir("queue.list", specialty="oftalmologia", min_days=400, size=500)
    assert payload["pagination"]["total"] > 0
    for registro in payload["data"]:
        assert registro["especialidade"] == "Oftalmologia"
        assert registro["dias_em_fila"] >= 400


def test_busca_ignora_acento_e_caixa(pedir):
    assert pedir("queue.list", search="CARCINOMA", size=1)["pagination"]["total"] > 0


def test_ordem_ascendente(pedir):
    payload = pedir("queue.list", order="asc", size=5)
    esperas = [r["dias_em_fila"] for r in payload["data"]]
    assert esperas == sorted(esperas)
    assert payload["sort"]["descending"] is False


def test_detalhe_traz_procedimento_e_eventos(pedir):
    payload = pedir("queue.request", request_id="SOL-2025-00048")
    assert payload["request"]["paciente_id"] == "PAC-00348"
    assert payload["procedure"]["procedimento_id"] == "PROC011"
    assert payload["total_events"] == len(payload["events"])


def test_id_aceita_minusculas(pedir):
    payload = pedir("queue.request", request_id="sol-2025-00048")
    assert payload["request"]["solicitacao_id"] == "SOL-2025-00048"


def test_eventos_vem_em_ordem_cronologica(pedir, repo):
    alvo = next(
        r["solicitacao_id"]
        for r in repo.queue
        if len(repo.events_for_request(r["solicitacao_id"])) > 2
    )
    eventos = pedir("queue.events", request_id=alvo)["data"]
    datas = [e["data_evento"] for e in eventos]
    assert datas == sorted(datas)


def test_eventos_de_paciente(pedir, repo):
    paciente = next(e["paciente_id"] for e in repo.events if e.get("paciente_id"))
    payload = pedir("patient.events", patient_id=paciente)
    assert payload["pagination"]["total"] >= 1
    assert all(e["paciente_id"] == paciente for e in payload["data"])


# --- catálogo, referências e agregados ------------------------------------

def test_catalogo_e_referencias(pedir):
    assert pedir("catalog.procedures")["total"] == 23
    assert pedir("catalog.swalis")["total"] == 5
    filtros = pedir("catalog.filters")
    assert "Oftalmologia" in filtros["specialties"]
    assert filtros["priorities"] == ["alta", "baixa", "media"]


def test_estatisticas_derivam_oncologia_do_cid(pedir):
    payload = pedir("stats.summary")
    assert payload["oncological_by_cid"] == 177
    assert payload["oncological_flag_mismatch"] == 44
    assert payload["wait_days"]["over_365"] == 353


# --- cálculo longo: progresso antes do resultado ---------------------------

def test_priorizacao_emite_progresso_e_resultado(conversa):
    ws = conversa({"id": "p1", "action": "queue.prioritize"})
    tipos = [f["type"] for f in ws.frames]

    assert tipos[-1] == "result", "o result fecha a sequência"
    assert tipos.count("result") == 1
    assert set(tipos[:-1]) == {"progress"}, "antes dele, só progresso"
    assert len(tipos) > 2, "941 registros em lotes de 100 devem render vários frames"


def test_progresso_cresce_e_termina_em_cem_por_cento(conversa):
    ws = conversa({"id": "p1", "action": "queue.prioritize"})
    progressos = ws.tipos("progress")

    completados = [f["completed"] for f in progressos]
    assert completados == sorted(completados)
    assert all(f["total"] == 924 for f in progressos)
    assert progressos[-1]["completed"] == 924
    assert progressos[-1]["percent"] == 100.0
    assert progressos[0]["label"] == "prioritizing queue with DPS"


def test_todo_frame_do_comando_carrega_o_id_para_correlacionar(conversa):
    ws = conversa({"id": "abc-123", "action": "queue.prioritize"})
    assert {f["id"] for f in ws.frames} == {"abc-123"}
    assert {f["action"] for f in ws.frames} == {"queue.prioritize"}


def test_prioritizacao_cobre_a_fila_com_posicoes_sequenciais(pedir):
    payload = pedir("queue.prioritize")
    assert payload["total"] == 924
    assert [r["position"] for r in payload["data"]] == list(range(1, 925))
    assert len({r["solicitacao_id"] for r in payload["data"]}) == 924


def test_prioritizacao_se_declara_provisoria(pedir):
    """DPS roda de verdade, mas pesos ainda não têm validação PAPRIKA."""
    payload = pedir("queue.prioritize")
    assert payload["provisional"] is True
    assert payload["strategy"] == "dps"
    assert payload["model"]["formula"] == "P = (t / M) * (1 + c)"
    assert payload["model"]["weights_validated_with_paprika"] is False
    assert all(r["justification"].strip() for r in payload["data"])


def test_prioritizacao_aceita_os_mesmos_filtros_da_fila(pedir):
    payload = pedir("queue.prioritize", specialty="oftalmologia")
    assert 0 < payload["total"] < 941
    assert [r["position"] for r in payload["data"]] == list(
        range(1, payload["total"] + 1)
    )


def test_entregavel_tem_as_colunas_do_verificador(pedir, repo):
    """O contrato inglês é aceito pelo verificador e mantém a linha completa."""
    primeira = pedir("queue.prioritize", specialty="oftalmologia")["data"][0]
    assert {"solicitacao_id", "position", "justification", "nome_paciente"} <= set(
        primeira
    )
    assert set(repo.queue[0]) <= set(primeira)


def test_priorizacao_pode_incluir_inativos(pedir):
    payload = pedir("queue.prioritize", include_inactive=True)
    assert payload["total"] == 941
    assert any(record["active"] is False for record in payload["data"])


def test_priorizacao_rejeita_data_de_corte_invalida(conversa):
    frame = conversa({
        "id": "bad-date",
        "action": "queue.prioritize",
        "params": {"as_of": "24-10-2026"},
    }).primeiro("error")
    assert frame["error"]["status"] == 400
    assert "as_of" in frame["error"]["message"]


# --- várias ações na mesma conexão ----------------------------------------

def test_conexao_atende_comandos_em_sequencia(conversa):
    ws = conversa(
        {"id": "a", "action": "catalog.swalis"},
        {"id": "b", "action": "stats.summary"},
        {"id": "c", "action": "queue.list", "params": {"size": 1}},
    )
    results = ws.tipos("result")
    assert [f["id"] for f in results] == ["a", "b", "c"]
    assert [f["action"] for f in results] == [
        "catalog.swalis", "stats.summary", "queue.list",
    ]
