def test_indice_lista_rotas(cliente):
    corpo = cliente.get("/").get_json()
    assert "/api/queue" in corpo["routes"]


def test_saude_conta_o_dataset(cliente):
    corpo = cliente.get("/api/health").get_json()
    assert corpo["status"] == "ok"
    assert corpo["dataset"]["queue"] == 941
    assert corpo["dataset"]["events"] == 1505


def test_estatisticas_derivam_oncologia_do_cid(cliente):
    corpo = cliente.get("/api/statistics").get_json()
    assert corpo["oncological_by_cid"] == 177
    assert corpo["oncological_flag_mismatch"] == 44
    assert corpo["wait_days"]["over_365"] == 353


def test_fila_pagina_e_ordena_por_espera(cliente):
    corpo = cliente.get("/api/queue?size=5").get_json()
    assert corpo["pagination"]["total"] == 941
    assert len(corpo["data"]) == 5
    esperas = [r["dias_em_fila"] for r in corpo["data"]]
    assert esperas == sorted(esperas, reverse=True)


def test_fila_paginas_nao_se_repetem(cliente):
    primeira = cliente.get("/api/queue?size=3&page=1").get_json()["data"]
    segunda = cliente.get("/api/queue?size=3&page=2").get_json()["data"]
    assert {r["solicitacao_id"] for r in primeira} & {
        r["solicitacao_id"] for r in segunda
    } == set()


def test_filtro_oncologico(cliente):
    corpo = cliente.get("/api/queue?oncological=sim&size=500").get_json()
    assert corpo["pagination"]["total"] == 177
    assert all(r["oncologico_cid"] for r in corpo["data"])


def test_filtro_combina_especialidade_e_espera(cliente):
    corpo = cliente.get(
        "/api/queue?specialty=oftalmologia&min_days=400&size=500"
    ).get_json()
    assert corpo["pagination"]["total"] > 0
    for registro in corpo["data"]:
        assert registro["especialidade"] == "Oftalmologia"
        assert registro["dias_em_fila"] >= 400


def test_busca_ignora_acento_e_caixa(cliente):
    corpo = cliente.get("/api/queue?search=CARCINOMA&size=1").get_json()
    assert corpo["pagination"]["total"] > 0


def test_detalhe_traz_procedimento_e_eventos(cliente):
    corpo = cliente.get("/api/queue/SOL-2025-00048").get_json()
    assert corpo["request"]["paciente_id"] == "PAC-00348"
    assert corpo["procedure"]["procedimento_id"] == "PROC011"
    assert corpo["total_events"] == len(corpo["events"])


def test_eventos_vem_em_ordem_cronologica(cliente, app):
    repo = app.extensions["repository"]
    alvo = next(
        r["solicitacao_id"]
        for r in repo.queue
        if len(repo.events_for_request(r["solicitacao_id"])) > 2
    )
    eventos = cliente.get(f"/api/queue/{alvo}/events").get_json()["data"]
    datas = [e["data_evento"] for e in eventos]
    assert datas == sorted(datas)


def test_solicitacao_inexistente_retorna_404_em_json(cliente):
    resposta = cliente.get("/api/queue/SOL-9999-99999")
    assert resposta.status_code == 404
    assert resposta.get_json()["error"]["status"] == 404


def test_parametro_invalido_retorna_400(cliente):
    resposta = cliente.get("/api/queue?page=abc")
    assert resposta.status_code == 400
    assert "page" in resposta.get_json()["error"]["message"]


def test_tamanho_acima_do_maximo_rejeitado(cliente):
    assert cliente.get("/api/queue?size=10000").status_code == 400


def test_catalogo_e_referencias(cliente):
    assert cliente.get("/api/procedures").get_json()["total"] == 23
    assert cliente.get("/api/references/swalis").get_json()["total"] == 5
    filtros = cliente.get("/api/references/filters").get_json()
    assert "Oftalmologia" in filtros["specialties"]
    assert filtros["priorities"] == ["alta", "baixa", "media"]
