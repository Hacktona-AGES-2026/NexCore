"""Testes da API REST da regulação (docs/CONTRATO_BACKEND.md §2–§9).

O estado é mutável e vive na app, então tudo que muda a fila usa `app_nova`
(uma app por teste); as leituras usam a app da sessão. Os números de referência
dos painéis e das pendências são os do `frontend/src/mock/stats.json`, gerado
pelo front a partir do dataset completo: se divergirem, o front muda de cara.
"""
import pytest

from app import create_app
from app.regulation.audit import chain_hash, chain_is_intact, GENESIS

H = "/v1/hospitais/hsl"
JUSTIFICATIVA = "Angina instável confirmada com a cardiologia, lesão de tronco."


@pytest.fixture()
def app_nova():
    return create_app("teste")


@pytest.fixture()
def nova(app_nova):
    return app_nova.test_client()


def estado(app):
    return app.extensions["queue_state"]


def mover(cliente, rid, posicao, motivo="Critério clínico não considerado", texto=JUSTIFICATIVA):
    return cliente.post(
        f"{H}/fila/{rid}/reordenar",
        json={"position": posicao, "reason": motivo, "justification": texto},
    )


def posicao(cliente, rid):
    return next(e["position"] for e in cliente.get(f"{H}/fila").get_json()["entries"] if e["id"] == rid)


# --- fila ------------------------------------------------------------------

def test_fila_vem_inteira_em_camelcase(cliente):
    corpo = cliente.get(f"{H}/fila").get_json()
    assert corpo["hospitalId"] == "hsl"
    assert corpo["total"] == len(corpo["entries"]) == 941
    primeiro = corpo["entries"][0]
    assert primeiro["id"] == "SOL-2026-00098"
    assert {"patientId", "daysWaiting", "urgencyClass", "classReason", "factors", "highlights"} <= set(primeiro)
    assert "solicitacao_id" not in primeiro


def test_posicoes_sao_continuas(cliente):
    entradas = cliente.get(f"{H}/fila").get_json()["entries"]
    assert [e["position"] for e in entradas] == list(range(1, 942))


def test_entrada_do_exemplo_do_contrato(cliente):
    e = next(x for x in cliente.get(f"{H}/fila").get_json()["entries"] if x["id"] == "SOL-2025-00274")
    assert e["name"] == "Gabriela Ramos Quadros"
    assert e["urgencyClass"] == "C"
    assert e["asa"] == "3" and e["pain"] == "6"  # texto, como em types.ts
    assert [f["key"] for f in e["factors"]] == ["urgency", "wait", "events", "symptoms"]
    assert e["locked"] is False and e["pendingConfirmation"] is False


def test_campo_vazio_e_omitido_nao_imputado(cliente):
    entradas = cliente.get(f"{H}/fila").get_json()["entries"]
    sem_obs = [e for e in entradas if "regulationNote" not in e]
    assert sem_obs, "o dataset tem solicitações sem observação"
    assert all(e.get("regulationNote") != "" for e in entradas)


def test_eventos_duplicados_ficam_de_fora(cliente, repo):
    duplicado = next(e for e in repo.events if e.get("duplicata_conteudo"))
    rid = duplicado["solicitacao_id"]
    entrada = next(e for e in cliente.get(f"{H}/fila").get_json()["entries"] if e["id"] == rid)
    validos = [e for e in repo.events_for_request(rid) if not e.get("duplicata_conteudo")]
    assert len(entrada["events"]) == len(validos)


def test_cidade_sai_com_acento(cliente):
    cidades = {e["city"] for e in cliente.get(f"{H}/fila").get_json()["entries"]}
    assert "Viamão" in cidades and "Viamao" not in cidades


# --- auditoria -------------------------------------------------------------

def test_auditoria_comeca_com_a_carga_inicial(cliente):
    log = cliente.get(f"{H}/auditoria").get_json()
    assert log[-1]["kind"] == "intake"
    assert log[-1]["prevHash"] == GENESIS
    assert "941 solicitações" in log[-1]["justification"]


def test_hash_segue_a_formula_do_contrato(nova):
    mover(nova, "SOL-2025-00274", 210)
    log = nova.get(f"{H}/auditoria").get_json()
    assert chain_is_intact(log)
    ultimo, anterior = log[0], log[1]
    assert ultimo["prevHash"] == anterior["hash"]
    assert ultimo["hash"] == chain_hash(
        anterior["hash"], ultimo["at"], ultimo["author"], ultimo["kind"],
        ultimo["entryId"], ultimo["from"], ultimo["to"], ultimo["justification"],
    )
    assert len(ultimo["hash"]) == 64


def test_cadeia_alterada_e_detectada(nova):
    mover(nova, "SOL-2025-00274", 210)
    log = nova.get(f"{H}/auditoria").get_json()
    log[1]["justification"] = "editado"
    assert not chain_is_intact(log)


# --- reordenar -------------------------------------------------------------

def test_reordenar_move_trava_e_audita(nova):
    resposta = mover(nova, "SOL-2025-00274", 210)
    assert resposta.status_code == 200
    registro = resposta.get_json()
    assert (registro["kind"], registro["from"], registro["to"]) == ("manual", 404, 210)
    assert registro["author"] == "Marina Albuquerque"
    assert registro["justification"] == f"Critério clínico não considerado. {JUSTIFICATIVA}"

    entradas = nova.get(f"{H}/fila").get_json()["entries"]
    movida = entradas[209]
    assert movida["id"] == "SOL-2025-00274" and movida["locked"] is True
    assert movida["previousPosition"] == 404
    assert [e["position"] for e in entradas] == list(range(1, 942))
    assert entradas[210]["previousPosition"] == 210  # quem estava ali desceu um


@pytest.mark.parametrize("corpo, trecho", [
    ({"position": 210, "reason": "x", "justification": "curta"}, "40 caracteres"),
    ({"position": 210, "reason": "", "justification": JUSTIFICATIVA}, "motivo"),
    ({"position": 0, "reason": "x", "justification": JUSTIFICATIVA}, "entre 1 e 941"),
    ({"position": 942, "reason": "x", "justification": JUSTIFICATIVA}, "entre 1 e 941"),
    ({"position": "210", "reason": "x", "justification": JUSTIFICATIVA}, "inteiro"),
    ({"position": True, "reason": "x", "justification": JUSTIFICATIVA}, "inteiro"),
    ({"position": 404, "reason": "x", "justification": JUSTIFICATIVA}, "já está na posição"),
])
def test_reordenar_valida_de_novo_no_servidor(nova, corpo, trecho):
    resposta = nova.post(f"{H}/fila/SOL-2025-00274/reordenar", json=corpo)
    assert resposta.status_code == 400
    assert trecho in resposta.get_json()["detail"]
    assert posicao(nova, "SOL-2025-00274") == 404


def test_reordenar_sem_corpo_json(nova):
    resposta = nova.post(f"{H}/fila/SOL-2025-00274/reordenar", data="x", content_type="text/plain")
    assert resposta.status_code == 400
    assert "objeto JSON" in resposta.get_json()["detail"]


def test_reordenar_solicitacao_inexistente(nova):
    resposta = mover(nova, "SOL-NAO-EXISTE", 1)
    assert resposta.status_code == 404
    assert "não encontrada" in resposta.get_json()["detail"]


def test_regra_de_ouro_barra_oncologico_abaixo_de_calmo(app_nova, nova):
    st = estado(app_nova)
    calmo = next(r for r in st.order if st.assessments[r]["no_urgency"])
    onco = [r for r in st.order if st.assessments[r]["oncological"]][-1]
    alvo = st.order.index(calmo) + 2
    resposta = mover(nova, onco, alvo)
    assert resposta.status_code == 422
    detalhe = resposta.get_json()["detail"]
    assert "Regra de ouro" in detalhe and "não tem urgência clínica" in detalhe
    assert len(nova.get(f"{H}/auditoria").get_json()) == 1  # nada foi gravado


def test_regra_de_ouro_barra_calmo_acima_de_oncologico(app_nova, nova):
    st = estado(app_nova)
    calmo = next(r for r in st.order if st.assessments[r]["no_urgency"])
    assert mover(nova, calmo, 1).status_code == 422


def test_oncologico_pode_descer_abaixo_de_quem_nao_e_calmo(app_nova, nova):
    """"Sem urgência" é a definição do verificador; abaixo de um classe C qualquer pode."""
    st = estado(app_nova)
    calmo = next(r for r in st.order if st.assessments[r]["no_urgency"])
    onco = [r for r in st.order if st.assessments[r]["oncological"]][-1]
    alvo = st.order.index(calmo)  # logo acima do primeiro calmo
    assert mover(nova, onco, alvo).status_code == 200


# --- validar ---------------------------------------------------------------

def test_validar_grava_auditoria_na_posicao_atual(nova):
    registro = nova.post(f"{H}/fila/SOL-2025-00274/validar").get_json()
    assert (registro["kind"], registro["from"], registro["to"]) == ("validation", 404, 404)
    assert posicao(nova, "SOL-2025-00274") == 404


# --- pendências ------------------------------------------------------------

def test_pendencias_por_tipo(cliente):
    pendencias = cliente.get(f"{H}/pendencias").get_json()
    contagem = {}
    for p in pendencias:
        contagem[p["kind"]] = contagem.get(p["kind"], 0) + 1
    assert contagem == {"cid_flag": 44, "duplicate": 22, "biopsy": 23, "left_queue": 18, "orphan_event": 9}
    assert pendencias[0]["id"] == "PEN-0001"


def test_pendencia_de_duplicata_lista_a_mais_antiga_primeiro(cliente):
    p = next(x for x in cliente.get(f"{H}/pendencias").get_json() if x["id"] == "PEN-0045")
    assert p["entryIds"] == ["SOL-2024-00003", "SOL-2024-00044"]
    assert p["detail"].endswith("Entradas em 14/01/2024 e 07/05/2024.")


def test_resolver_com_acao_errada(nova):
    resposta = nova.post(f"{H}/pendencias/PEN-0001/resolver", json={"action": "merge"})
    assert resposta.status_code == 400
    assert "fix_cadastro" in resposta.get_json()["detail"]


def test_resolver_pendencia_inexistente(nova):
    assert nova.post(f"{H}/pendencias/PEN-9999/resolver", json={"action": "keep"}).status_code == 404


def test_resolver_tira_a_pendencia_e_audita(nova):
    registro = nova.post(
        f"{H}/pendencias/PEN-0001/resolver", json={"action": "fix_cadastro", "note": "ok"},
    ).get_json()
    assert registro["kind"] == "data" and registro["to"] == 0 and registro["from"] is None
    assert registro["justification"].endswith("Cadastro corrigido para bater com o CID. ok")
    assert all(p["id"] != "PEN-0001" for p in nova.get(f"{H}/pendencias").get_json())


def test_mesclar_remove_as_duplicatas_mais_novas(nova):
    nova.post(f"{H}/pendencias/PEN-0045/resolver", json={"action": "merge"})
    corpo = nova.get(f"{H}/fila").get_json()
    ids = {e["id"] for e in corpo["entries"]}
    assert "SOL-2024-00003" in ids and "SOL-2024-00044" not in ids
    assert corpo["total"] == 940
    assert [e["position"] for e in corpo["entries"]] == list(range(1, 941))


def test_manter_na_fila_limpa_a_confirmacao(nova):
    p = next(x for x in nova.get(f"{H}/pendencias").get_json() if x["kind"] == "left_queue")
    rid = p["entryIds"][0]
    nova.post(f"{H}/pendencias/{p['id']}/resolver", json={"action": "keep"})
    entrada = next(e for e in nova.get(f"{H}/fila").get_json()["entries"] if e["id"] == rid)
    assert entrada["pendingConfirmation"] is False
    assert all(w["level"] != "critical" for w in entrada["warnings"])


# --- painéis ---------------------------------------------------------------

def test_resumo_bate_com_a_referencia(cliente):
    resumo = cliente.get(f"{H}/painel/resumo").get_json()
    assert resumo["byClass"] == [
        {"cls": "A1", "total": 29, "overdue": 29}, {"cls": "A2", "total": 171, "overdue": 168},
        {"cls": "B", "total": 202, "overdue": 198}, {"cls": "C", "total": 247, "overdue": 181},
        {"cls": "D", "total": 292, "overdue": 121},
    ]
    assert resumo["overdueTotal"] == 697 and resumo["oncologic"] == 177
    assert [b["total"] for b in resumo["waitBuckets"]] == [173, 162, 253, 201, 152]
    assert len(resumo["top"]) == 12
    assert resumo["top"][0] == {
        "position": 1, "id": "SOL-2026-00098", "initials": "E.L.P.",
        "procedure": "Histerectomia", "cls": "A1", "days": 264,
    }


def test_telao_nao_mostra_nome(cliente):
    resumo = cliente.get(f"{H}/painel/resumo").get_json()
    assert all("name" not in t for t in resumo["top"])


def test_equidade_bate_com_a_referencia(cliente):
    eq = cliente.get(f"{H}/painel/equidade").get_json()
    assert len(eq["cities"]) == 38
    assert eq["cities"][0] == {
        "name": "Porto Alegre", "lat": -30.03, "lon": -51.23, "total": 367,
        "avgWait": 364, "overdue": 252, "urgent": 75, "distanceKm": 14,
    }
    assert [(g["label"], g["avgWait"]) for g in eq["byDistance"]] == [
        ("Até 50 km", 366), ("50 a 200 km", 378), ("Mais de 200 km", 492),
    ]
    assert [g["total"] for g in eq["byAge"]] == [128, 366, 311, 136]
    assert [g["total"] for g in eq["bySex"]] == [549, 392]


# --- Pergunte ao Neco ------------------------------------------------------

def test_neco_conta_casos_por_classe(cliente):
    resposta = cliente.post(f"{H}/neco/perguntar", json={"question": "Quantos casos A1 temos?"})
    assert resposta.get_json()["text"].startswith("Temos 29 casos A1")


def test_neco_explica_paciente_e_cita_o_id(cliente):
    resposta = cliente.post(
        f"{H}/neco/perguntar", json={"question": "Por que a Gabriela Ramos Quadros está na posição dela?"},
    ).get_json()
    assert resposta["entryIds"] == ["SOL-2025-00274"]
    assert "posição 404" in resposta["text"]


def test_neco_pede_pergunta(cliente):
    resposta = cliente.post(f"{H}/neco/perguntar", json={"question": "  "})
    assert resposta.status_code == 400


def test_neco_nao_entende_e_sugere(cliente):
    resposta = cliente.post(f"{H}/neco/perguntar", json={"question": "qual a capital da França?"}).get_json()
    assert resposta["suggestions"]


# --- erros e transporte ----------------------------------------------------

def test_hospital_desconhecido(cliente):
    resposta = cliente.get("/v1/hospitais/outro/fila")
    assert resposta.status_code == 404
    assert resposta.get_json() == {"detail": "Hospital 'outro' não encontrado."}


def test_metodo_errado_sai_com_detail(cliente):
    resposta = cliente.delete(f"{H}/fila")
    assert resposta.status_code == 405
    assert "detail" in resposta.get_json()


def test_erro_interno_nao_vaza(app_nova, nova, monkeypatch):
    def explode(*_):
        raise RuntimeError("segredo interno")

    monkeypatch.setattr(estado(app_nova), "summary", explode)
    resposta = nova.get(f"{H}/painel/resumo")
    assert resposta.status_code == 500
    assert resposta.get_json() == {"detail": "Erro interno do servidor."}
    assert "segredo" not in resposta.get_data(as_text=True)


def test_preflight_de_cors_para_o_post(cliente):
    resposta = cliente.options(
        f"{H}/fila/SOL-2025-00274/reordenar",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert resposta.status_code == 200
    assert resposta.headers["Access-Control-Allow-Origin"] == "*"
    assert "Content-Type" in resposta.headers["Access-Control-Allow-Headers"]
