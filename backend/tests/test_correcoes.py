"""Testes das correções de pendências (regulation/pendencies.py + corrections.py).

Toda pendência tem o mesmo formato, qualquer que seja o tipo, e resolver muda o
dado de verdade (cópia da fila, nunca o dataset), recalcula a fila e audita o
antes e o depois. A prévia (`/simular`) roda o mesmo código e não muda nada.
"""
import pytest

from app import create_app

H = "/v1/hospitais/hsl"
CHAVES = {"id", "kind", "kindLabel", "title", "detail", "name", "entryIds", "risk", "riskReason",
          "divergences", "evidence", "actions", "suggestion"}


@pytest.fixture()
def app_nova():
    return create_app("teste")


@pytest.fixture()
def nova(app_nova):
    return app_nova.test_client()


def pendencias(cliente, tipo=None):
    todas = cliente.get(f"{H}/pendencias").get_json()
    return [p for p in todas if tipo is None or p["kind"] == tipo]


def fila(cliente):
    return {e["id"]: e for e in cliente.get(f"{H}/fila").get_json()["entries"]}


def resolver(cliente, pid, acao, valores=None, nota=None):
    return cliente.post(f"{H}/pendencias/{pid}/resolver", json={"action": acao, "values": valores or {}, "note": nota})


def simular(cliente, pid, acao, valores=None):
    return cliente.post(f"{H}/pendencias/{pid}/simular", json={"action": acao, "values": valores or {}})


# --- formato único ---------------------------------------------------------

def test_toda_pendencia_tem_o_mesmo_formato(cliente):
    for p in pendencias(cliente):
        assert CHAVES <= set(p), p["id"]
        assert p["risk"] in {"alto", "medio", "baixo"}
        assert p["divergences"] and all(len(d["values"]) >= 2 for d in p["divergences"])
        assert p["actions"] and all({"id", "label", "fields", "requiresJustification", "changesQueue"} <= set(a) for a in p["actions"])
        sugerida = p["suggestion"]["actionId"]
        assert sugerida is None or sugerida in {a["id"] for a in p["actions"]}


def test_biopsia_e_cid_benigno_com_marcacao_de_cancer_sao_risco_alto(cliente):
    assert all(p["risk"] == "alto" for p in pendencias(cliente, "biopsy"))
    altos = [p for p in pendencias(cliente, "cid_flag") if p["risk"] == "alto"]
    assert altos and all("CID" in p["divergences"][0]["values"][0]["source"] for p in altos)


# --- validação -------------------------------------------------------------

def test_cid_invalido_e_recusado(nova):
    p = pendencias(nova, "biopsy")[0]
    resposta = resolver(nova, p["id"], "update_cid", {"cid": "abc"}, "Laudo conferido com a patologia.")
    assert resposta.status_code == 400 and "CID" in resposta.get_json()["detail"]


def test_acao_que_exige_justificativa_sem_ela_e_recusada(nova):
    p = pendencias(nova, "duplicate")[0]
    assert resolver(nova, p["id"], "keep_both").status_code == 400


def test_confirmar_saida_exige_dizer_como_foi_confirmado(nova):
    p = pendencias(nova, "left_queue")[0]
    resposta = resolver(nova, p["id"], "remove")
    assert resposta.status_code == 400 and "confirmado" in resposta.get_json()["detail"]


# --- prévia ----------------------------------------------------------------

def test_previa_nao_muda_a_fila_e_bate_com_a_resolucao(nova):
    p = next(x for x in pendencias(nova, "biopsy"))
    rid = p["entryIds"][0]
    antes = fila(nova)[rid]["position"]
    previa = simular(nova, p["id"], "unrelated").get_json()
    assert fila(nova)[rid]["position"] == antes
    mudanca = next(c for c in previa["changes"] if c["entryId"] == rid)
    assert mudanca["from"] == antes and mudanca["classFrom"] == "A2" and mudanca["classTo"] != "A2"
    assert previa["summary"]
    resolver(nova, p["id"], "unrelated", nota="Biópsia era de outro procedimento.")
    assert fila(nova)[rid]["position"] == mudanca["to"]


def test_previa_de_acao_sem_efeito_na_fila_diz_isso(nova):
    p = pendencias(nova, "cid_flag")[0]
    previa = simular(nova, p["id"], "fix_cadastro").get_json()
    assert previa["summary"].startswith("Nenhuma mudança na fila")


# --- correções que mudam o dado ---------------------------------------------

def test_corrigir_o_cid_recalcula_e_audita_o_antes_e_depois(nova, app_nova):
    p = pendencias(nova, "biopsy")[0]
    rid = p["entryIds"][0]
    cid_antigo = fila(nova)[rid]["cid"]
    registro = resolver(nova, p["id"], "update_cid", {"cid": "c50.9"}, "Laudo conferido com a patologia.").get_json()
    entrada = fila(nova)[rid]
    assert entrada["cid"] == "C50.9" and entrada["oncologic"] is True
    assert f"CID corrigido de {cid_antigo} para C50.9." in registro["justification"]
    assert all(x["id"] != p["id"] for x in pendencias(nova))
    # o dataset continua intacto: a correção vive na cópia da fila
    assert app_nova.extensions["repository"].get_request(rid)["cid_principal"] == cid_antigo


def test_cid_corrigido_para_cancer_faz_o_paciente_subir(nova):
    p = next(x for x in pendencias(nova, "cid_flag") if x["risk"] == "alto")
    rid = p["entryIds"][0]
    antes = fila(nova)[rid]["position"]
    resolver(nova, p["id"], "update_cid", {"cid": "C50.9"}, "Cadastro estava certo; CID corrigido.")
    assert fila(nova)[rid]["position"] < antes


def test_mesclar_junta_os_eventos_na_solicitacao_mantida(nova):
    p = pendencias(nova, "duplicate")[0]
    antiga, nova_id = p["entryIds"][:2]
    eventos = len(fila(nova)[antiga]["events"]) + len(fila(nova)[nova_id]["events"])
    resolver(nova, p["id"], "merge")
    entradas = fila(nova)
    assert nova_id not in entradas and len(entradas[antiga]["events"]) == eventos


def test_orfaos_do_dataset_so_podem_ser_arquivados(cliente):
    """Nenhum paciente com evento órfão tem outra solicitação ativa neste dataset."""
    assert all([a["id"] for a in p["actions"]] == ["archive"] for p in pendencias(cliente, "orphan_event"))


def test_vincular_evento_orfao_leva_o_evento_para_a_solicitacao_escolhida(nova, app_nova):
    from app.regulation.pendencies import _action

    p = pendencias(nova, "orphan_event")[0]
    alvo = next(iter(fila(nova)))
    # Monta o caso que o dataset não tem: o paciente do evento com uma solicitação ativa.
    estado = app_nova.extensions["queue_state"]
    estado.pendencies[p["id"]]["actions"].insert(0, _action(
        "link", "Vincular", "", fields=[{"name": "target", "label": "Solicitação", "type": "select", "required": True,
                                         "options": [{"value": alvo, "label": alvo}], "suggested": alvo}],
        justification=True, changes_queue=True,
    ))
    eventos = len(fila(nova)[alvo]["events"])
    registro = resolver(nova, p["id"], "link", {"target": alvo}, "Mesmo paciente, mesmo problema clínico.").get_json()
    assert len(fila(nova)[alvo]["events"]) == eventos + 1
    assert f"vinculado à solicitação {alvo}" in registro["justification"]


def test_confirmar_saida_tira_da_fila_e_encerra_outras_pendencias_do_paciente(nova):
    p = pendencias(nova, "left_queue")[0]
    rid = p["entryIds"][0]
    resolver(nova, p["id"], "remove", {"confirmacao": "ligacao"})
    corpo = nova.get(f"{H}/fila").get_json()
    assert rid not in {e["id"] for e in corpo["entries"]} and corpo["total"] == 940
    assert all(rid not in x["entryIds"] for x in pendencias(nova))
