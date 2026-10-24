def test_indice_lista_rotas(cliente):
    corpo = cliente.get("/").get_json()
    assert "/api/fila" in corpo["rotas"]


def test_saude_conta_o_dataset(cliente):
    corpo = cliente.get("/api/saude").get_json()
    assert corpo["status"] == "ok"
    assert corpo["dataset"]["fila"] == 941
    assert corpo["dataset"]["eventos"] == 1505


def test_estatisticas_derivam_oncologia_do_cid(cliente):
    corpo = cliente.get("/api/estatisticas").get_json()
    assert corpo["oncologicos_por_cid"] == 177
    assert corpo["flag_oncologica_divergente"] == 44
    assert corpo["espera_dias"]["acima_de_365"] == 353


def test_fila_pagina_e_ordena_por_espera(cliente):
    corpo = cliente.get("/api/fila?tamanho=5").get_json()
    assert corpo["paginacao"]["total"] == 941
    assert len(corpo["dados"]) == 5
    esperas = [r["dias_em_fila"] for r in corpo["dados"]]
    assert esperas == sorted(esperas, reverse=True)


def test_fila_paginas_nao_se_repetem(cliente):
    primeira = cliente.get("/api/fila?tamanho=3&pagina=1").get_json()["dados"]
    segunda = cliente.get("/api/fila?tamanho=3&pagina=2").get_json()["dados"]
    assert {r["solicitacao_id"] for r in primeira} & {
        r["solicitacao_id"] for r in segunda
    } == set()


def test_filtro_oncologico(cliente):
    corpo = cliente.get("/api/fila?oncologico=sim&tamanho=500").get_json()
    assert corpo["paginacao"]["total"] == 177
    assert all(r["oncologico_cid"] for r in corpo["dados"])


def test_filtro_combina_especialidade_e_espera(cliente):
    corpo = cliente.get(
        "/api/fila?especialidade=oftalmologia&dias_minimo=400&tamanho=500"
    ).get_json()
    assert corpo["paginacao"]["total"] > 0
    for registro in corpo["dados"]:
        assert registro["especialidade"] == "Oftalmologia"
        assert registro["dias_em_fila"] >= 400


def test_busca_ignora_acento_e_caixa(cliente):
    corpo = cliente.get("/api/fila?busca=CARCINOMA&tamanho=1").get_json()
    assert corpo["paginacao"]["total"] > 0


def test_detalhe_traz_procedimento_e_eventos(cliente):
    corpo = cliente.get("/api/fila/SOL-2025-00048").get_json()
    assert corpo["solicitacao"]["paciente_id"] == "PAC-00348"
    assert corpo["procedimento"]["procedimento_id"] == "PROC011"
    assert corpo["total_eventos"] == len(corpo["eventos"])


def test_eventos_vem_em_ordem_cronologica(cliente, app):
    repo = app.extensions["repository"]
    alvo = next(
        r["solicitacao_id"]
        for r in repo.queue
        if len(repo.events_for_request(r["solicitacao_id"])) > 2
    )
    eventos = cliente.get(f"/api/fila/{alvo}/eventos").get_json()["dados"]
    datas = [e["data_evento"] for e in eventos]
    assert datas == sorted(datas)


def test_solicitacao_inexistente_retorna_404_em_json(cliente):
    resposta = cliente.get("/api/fila/SOL-9999-99999")
    assert resposta.status_code == 404
    assert resposta.get_json()["erro"]["status"] == 404


def test_parametro_invalido_retorna_400(cliente):
    resposta = cliente.get("/api/fila?pagina=abc")
    assert resposta.status_code == 400
    assert "pagina" in resposta.get_json()["erro"]["mensagem"]


def test_tamanho_acima_do_maximo_rejeitado(cliente):
    assert cliente.get("/api/fila?tamanho=10000").status_code == 400


def test_catalogo_e_referencias(cliente):
    assert cliente.get("/api/procedimentos").get_json()["total"] == 23
    assert cliente.get("/api/referencias/swalis").get_json()["total"] == 5
    filtros = cliente.get("/api/referencias/filtros").get_json()
    assert "Oftalmologia" in filtros["especialidades"]
    assert filtros["prioridades"] == ["alta", "baixa", "media"]
