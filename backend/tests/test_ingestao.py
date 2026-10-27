"""Testes da ingestão (POST /fila/entradas e /fila/eventos, docs/CONTRATO_BACKEND.md §4.6).

O corpo é uma linha dos CSVs de origem; o servidor valida contra o dicionário,
normaliza como o normalizador, reavalia, encaixa na fila e empurra os frames. A
maior parte roda sobre um dataset sintético de três solicitações, para conferir
posições exatas; as funções puras (`place`, `intake`) têm testes próprios; e o
dataset real entra no fim, inclusive contra o verificador oficial.
"""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from app import create_app
from app.prioritization import golden_rule_violation, place
from app.regulation import intake, verifier
from app.regulation.errors import ContractError

H = "/v1/hospitais/hsl"
REF = "2026-10-23"
JUSTIFICATIVA = "Critério clínico revisado com a equipe cirúrgica responsável."

PROCEDIMENTOS = [
    {"procedimento_id": "PROC001", "procedimento": "Hernioplastia inguinal", "especialidade": "Cirurgia Geral"},
    {"procedimento_id": "PROC011", "procedimento": "Mastectomia / setorectomia de mama", "especialidade": "Mastologia"},
]


def linha(rid, cid="K40.9", dor=2, limitacao="leve", dias=100, paciente=None, proc="PROC001", nome=None):
    """Uma linha de fila_cirurgica_normalizada.csv, com as colunas *_norm coerentes."""
    cid_norm = cid.replace(".", "")
    return {
        "solicitacao_id": rid, "paciente_id": paciente or f"PAC-{rid}",
        "nome_paciente": nome or f"Paciente {rid}", "sexo": "F", "sexo_norm": "f", "idade": 50,
        "municipio": "Porto Alegre", "municipio_norm": "Porto Alegre", "uf": "RS",
        "procedimento_id": proc, "procedimento": "Hernioplastia inguinal", "especialidade": "Cirurgia Geral",
        "cid_principal": cid, "cid_principal_norm": cid_norm,
        "oncologico_cid": "sim" if cid_norm.startswith("C") else "nao",
        "intensidade_dor_eva": dor, "limitacao_funcional": limitacao, "limitacao_funcional_norm": limitacao,
        "justificativa_clinica": "Solicito cirurgia.", "data_entrada_fila": "2026-07-15", "dias_em_fila": dias,
    }


def nova_entrada(rid="SOL-NOVA", **campos):
    """O corpo de POST /fila/entradas: só colunas de origem, como o dicionário define."""
    corpo = {
        "solicitacao_id": rid, "paciente_id": "PAC-NOVA", "nome_paciente": "Rosa Maria Dutra",
        "sexo": "F", "idade": 58, "municipio": "Canoas", "uf": "RS", "procedimento_id": "PROC011",
        "cid_principal": "C50.9", "intensidade_dor_eva": 3, "limitacao_funcional": "leve",
        "justificativa_clinica": "Nodulo de mama, core biopsy com carcinoma ductal invasivo.",
        "data_entrada_fila": REF,
    }
    corpo.update(campos)
    return corpo


def novo_evento(rid="SOL-C", tipo="pronto_socorro", resultado="observacao", **campos):
    corpo = {
        "solicitacao_id": rid, "paciente_id": f"PAC-{rid}", "data_evento": "2026-10-20",
        "tipo_evento": tipo, "resultado": resultado, "descricao": "Dor abdominal.", "origem": "PS Hospital Sao Lucas",
    }
    corpo.update(campos)
    return corpo


@pytest.fixture()
def fila(app_sintetico):
    """A (oncológica), B (dor moderada, classe C) e C (calma, classe D), nessa ordem."""
    return app_sintetico(
        fila=[linha("SOL-A", cid="C50.9"), linha("SOL-B", dor=5), linha("SOL-C")],
        procedimentos=PROCEDIMENTOS,
    )


@pytest.fixture()
def cliente_fila(fila):
    return fila.test_client()


@pytest.fixture()
def frames(fila):
    """Tudo que o hub publicou desde a criação da fixture."""
    inscricao = fila.extensions["queue_state"].hub.subscribe()

    def coletar():
        saida = []
        while (frame := inscricao.get(0)) is not None:
            saida.append(frame)
        return saida

    return coletar


def ordem(cliente):
    return [e["id"] for e in cliente.get(f"{H}/fila").get_json()["entries"]]


def entrada(cliente, rid):
    return next(e for e in cliente.get(f"{H}/fila").get_json()["entries"] if e["id"] == rid)


# --- encaixe na ordem (função pura) ------------------------------------------

def avaliacao(classe, score, onco=False, calmo=False):
    return {"urgency_class": classe, "score": score, "oncological": onco, "no_urgency": calmo}


def test_place_entra_depois_dos_pares_que_valem_tanto_quanto_ele():
    av = {"a": avaliacao("A2", 50, onco=True), "b": avaliacao("C", 20), "c": avaliacao("C", 20), "n": avaliacao("C", 20)}
    assert place(["a", "b", "c"], av, "n") == ["a", "b", "c", "n"]


def test_place_respeita_movimento_manual_dos_outros():
    # "d" foi posto à mão no topo: continua acima de "b". Logo abaixo de "b" ou
    # no topo, o novo discorda de um só; no empate fica a posição mais alta
    av = {"b": avaliacao("B", 30), "d": avaliacao("D", 5, calmo=True), "c": avaliacao("C", 15), "n": avaliacao("B", 25)}
    proposta = place(["d", "b", "c"], av, "n")
    assert proposta == ["n", "d", "b", "c"]
    assert proposta.index("d") < proposta.index("b")


def test_place_sobe_oncologico_acima_do_primeiro_calmo():
    # um calmo movido para o topo: o oncológico novo tem de ficar acima dele
    av = {"calmo": avaliacao("D", 5, calmo=True), "b": avaliacao("B", 60), "n": avaliacao("A2", 40, onco=True)}
    proposta = place(["calmo", "b"], av, "n")
    assert proposta == ["n", "calmo", "b"]
    assert golden_rule_violation(proposta, av) is None


def test_place_desce_calmo_abaixo_do_ultimo_oncologico():
    # um oncológico movido para baixo: o calmo novo não pode entrar acima dele
    av = {"x": avaliacao("C", 20), "onco": avaliacao("A2", 40, onco=True), "n": avaliacao("D", 30, calmo=True)}
    proposta = place(["x", "onco"], av, "n")
    assert proposta == ["x", "onco", "n"]
    assert golden_rule_violation(proposta, av) is None


def test_place_nao_e_arrastado_por_quem_foi_movido_para_longe():
    # um A1 rebaixado à mão para o fim não leva o novo B junto
    av = {"b": avaliacao("B", 40), "c": avaliacao("C", 15), "a1": avaliacao("A1", 80), "n": avaliacao("B", 30)}
    assert place(["b", "c", "a1"], av, "n") == ["b", "n", "c", "a1"]


def test_place_reposiciona_quem_ja_esta_na_ordem():
    av = {"a": avaliacao("B", 30), "b": avaliacao("C", 20), "c": avaliacao("A1", 70)}
    assert place(["a", "b", "c"], av, "c") == ["c", "a", "b"]


# --- normalização da linha (função pura) -------------------------------------

CATALOGO = {p["procedimento_id"]: p for p in PROCEDIMENTOS}


def test_linha_vira_o_registro_que_o_leitor_produziria():
    r = intake.queue_record(nova_entrada(
        cid_principal="c50.9 ", municipio="CANOAS", prioridade_regulacao="Média",
        flag_oncologico=False, idade="58", data_entrada_fila="2026-10-01",
    ), CATALOGO, REF)
    assert r["cid_principal_norm"] == "C509" and r["oncologico_cid"] is True
    assert r["municipio_norm"] == "Canoas"
    assert r["prioridade_regulacao"] == "Média" and r["prioridade_regulacao_norm"] == "media"
    assert r["flag_oncologico"] == "nao" and r["flag_oncologico_norm"] is False
    assert r["idade"] == 58
    assert r["dias_em_fila"] == 22
    assert r["especialidade"] == "Mastologia"
    assert r["data_ultima_revisao_prioridade"] == "2026-10-01"


def test_campo_opcional_ausente_fica_nulo_nao_zero():
    r = intake.queue_record(nova_entrada(intensidade_dor_eva=None, limitacao_funcional=""), CATALOGO, REF)
    assert r["intensidade_dor_eva"] is None and r["limitacao_funcional_norm"] is None
    assert r["asa"] is None and r["distancia_hospital_km"] is None


def test_procedimento_especialidade_e_dias_vem_do_servidor():
    r = intake.queue_record(nova_entrada(
        procedimento="Outro", especialidade="Outra", dias_em_fila=9999,
    ), CATALOGO, REF)
    assert r["procedimento"] == "Mastectomia / setorectomia de mama"
    assert r["dias_em_fila"] == 0


@pytest.mark.parametrize("campos, trecho", [
    ({"idade": 200}, "'idade' deve ser um número inteiro entre 0 e 120"),
    ({"idade": True}, "'idade' deve ser um número inteiro"),
    ({"intensidade_dor_eva": 11}, "'intensidade_dor_eva' deve ser um número inteiro entre 0 e 10"),
    ({"limitacao_funcional": "muita"}, "'limitacao_funcional' deve ser um de: nenhuma, leve, moderada, grave"),
    ({"sexo": "X"}, "'sexo' deve ser um de: f, m"),
    ({"prioridade_regulacao": "urgente"}, "'prioridade_regulacao' deve ser um de: alta, media, baixa"),
    ({"flag_oncologico": "talvez"}, "'flag_oncologico' deve ser sim ou nao"),
    ({"data_entrada_fila": "23/10/2026"}, "'data_entrada_fila' deve ser uma data AAAA-MM-DD"),
    ({"data_entrada_fila": "2026-10-24"}, "não pode ser posterior à data de referência (2026-10-23)"),
    ({"procedimento_id": "PROC999"}, "procedimento 'PROC999' não está no catálogo"),
    ({"cid": "C50"}, "campos desconhecidos: cid"),
    ({"nome_paciente": 42}, "'nome_paciente' deve ser texto"),
])
def test_linha_fora_do_dominio_e_recusada(campos, trecho):
    with pytest.raises(ContractError) as erro:
        intake.queue_record(nova_entrada(**campos), CATALOGO, REF)
    assert trecho in erro.value.detail
    assert erro.value.status == 400


def test_todos_os_problemas_saem_de_uma_vez():
    with pytest.raises(ContractError) as erro:
        intake.queue_record({"solicitacao_id": "SOL-1", "idade": "x"}, CATALOGO, REF)
    detalhe = erro.value.detail
    assert detalhe.startswith("Entrada SOL-1:")
    for campo in ("paciente_id", "nome_paciente", "cid_principal", "justificativa_clinica", "idade"):
        assert f"'{campo}'" in detalhe


# --- POST /fila/entradas -----------------------------------------------------

def test_oncologico_novo_entra_entre_os_pares_e_acima_dos_calmos(cliente_fila, frames):
    resposta = cliente_fila.post(f"{H}/fila/entradas", json=nova_entrada())
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["id"] == "SOL-NOVA" and corpo["position"] == 2
    assert corpo["urgencyClass"] == "A2" and corpo["oncologic"] is True
    assert corpo["procedure"] == "Mastectomia / setorectomia de mama" and corpo["daysWaiting"] == 0
    assert "previousPosition" not in corpo
    assert ordem(cliente_fila) == ["SOL-A", "SOL-NOVA", "SOL-B", "SOL-C"]

    patch, audit, atividade = frames()
    assert patch["type"] == "queue.patch" and patch["total"] == 4
    assert {e["id"] for e in patch["entries"]} == {"SOL-NOVA", "SOL-B", "SOL-C"}
    assert audit["type"] == "audit.appended"
    assert audit["entry"]["kind"] == "intake" and audit["entry"]["author"] == "Neco"
    assert (audit["entry"]["from"], audit["entry"]["to"]) == (None, 2)
    assert "Urgente (A2)" in audit["entry"]["justification"]
    assert atividade == {"type": "activity", "at": audit["entry"]["at"], "text": "Nova entrada: Rosa na posição 2"}


def test_campo_vazio_nao_e_imputado_na_entrada(cliente_fila):
    corpo = cliente_fila.post(f"{H}/fila/entradas", json=nova_entrada(intensidade_dor_eva=None)).get_json()
    assert "pain" not in corpo and "asa" not in corpo


def test_lote_devolve_uma_entrada_por_linha(cliente_fila):
    resposta = cliente_fila.post(f"{H}/fila/entradas", json=[
        nova_entrada("SOL-N1"), nova_entrada("SOL-N2", paciente_id="PAC-N2", cid_principal="K40.9", procedimento_id="PROC001"),
    ])
    assert resposta.status_code == 201
    assert [e["id"] for e in resposta.get_json()] == ["SOL-N1", "SOL-N2"]
    assert ordem(cliente_fila)[-1] == "SOL-N2"  # calma: fica no fim, depois de SOL-C (mesma classe, mais espera)


def test_lote_com_linha_ruim_nao_muda_nada(cliente_fila, frames):
    resposta = cliente_fila.post(f"{H}/fila/entradas", json=[nova_entrada("SOL-N1"), nova_entrada("SOL-N2", idade=-1)])
    assert resposta.status_code == 400
    assert resposta.get_json()["detail"].startswith("Linha 2 SOL-N2:")
    assert ordem(cliente_fila) == ["SOL-A", "SOL-B", "SOL-C"]
    assert frames() == []


@pytest.mark.parametrize("corpo", [
    [nova_entrada("SOL-A")],
    [nova_entrada("SOL-N1"), nova_entrada("SOL-N1")],
])
def test_solicitacao_repetida_e_conflito(cliente_fila, corpo):
    resposta = cliente_fila.post(f"{H}/fila/entradas", json=corpo)
    assert resposta.status_code == 409
    assert "já existe" in resposta.get_json()["detail"]


@pytest.mark.parametrize("corpo", ["texto", [], [1, 2], 3])
def test_corpo_que_nao_e_linha_nem_lote(cliente_fila, corpo):
    resposta = cliente_fila.post(f"{H}/fila/entradas", json=corpo)
    assert resposta.status_code == 400
    assert resposta.get_json() == {"detail": "Envie uma linha (objeto JSON) ou um lote (lista de objetos)."}


def test_corpo_que_nao_e_json(cliente_fila):
    resposta = cliente_fila.post(f"{H}/fila/entradas", data="solicitacao_id=1")
    assert resposta.status_code == 400


def test_mesmo_paciente_e_procedimento_abre_pendencia_de_duplicata(cliente_fila):
    cliente_fila.post(f"{H}/fila/entradas", json=nova_entrada(
        "SOL-C2", paciente_id="PAC-SOL-C", procedimento_id="PROC001", cid_principal="K40.9",
    ))
    duplicatas = [p for p in cliente_fila.get(f"{H}/pendencias").get_json() if p["kind"] == "duplicate"]
    assert len(duplicatas) == 1
    assert duplicatas[0]["entryIds"] == ["SOL-C", "SOL-C2"]  # a mais antiga primeiro


def test_flag_que_contradiz_o_cid_abre_pendencia(cliente_fila):
    cliente_fila.post(f"{H}/fila/entradas", json=nova_entrada(flag_oncologico="nao"))
    pendencia = next(p for p in cliente_fila.get(f"{H}/pendencias").get_json() if p["kind"] == "cid_flag")
    assert pendencia["entryIds"] == ["SOL-NOVA"]
    assert "O cadastro não marca câncer" in entrada(cliente_fila, "SOL-NOVA")["warnings"][0]["text"]


def test_exportar_inclui_quem_entrou(cliente_fila):
    cliente_fila.post(f"{H}/fila/entradas", json=nova_entrada())
    linhas = list(csv.DictReader(cliente_fila.get(f"{H}/fila/exportar").get_data(as_text=True).splitlines()))
    assert [(l["solicitacao_id"], l["posicao"]) for l in linhas][1] == ("SOL-NOVA", "2")


# --- POST /fila/eventos ------------------------------------------------------

def test_ida_ao_ps_e_registrada_e_auditada_mesmo_sem_mudar_a_posicao(cliente_fila, frames):
    # no DPSS a ida ao PS entra no fator clínico; aqui não basta para passar SOL-B
    resposta = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento())
    assert resposta.status_code == 202
    corpo = resposta.get_json()
    assert corpo["id"] == "SOL-C" and corpo["urgencyClass"] == "C"
    assert corpo["position"] == 3 and "previousPosition" not in corpo
    assert corpo["events"][-1]["type"] == "pronto_socorro"
    assert ordem(cliente_fila) == ["SOL-A", "SOL-B", "SOL-C"]

    patch, audit, atividade = frames()
    assert {e["id"] for e in patch["entries"]} == {"SOL-C"}
    assert audit["entry"]["kind"] == "recalc" and (audit["entry"]["from"], audit["entry"]["to"]) == (3, 3)
    assert "DPSS de 0,736 para 0,742, classe mantida" in audit["entry"]["justification"]
    assert atividade["text"] == "Paciente: ida ao pronto-socorro registrada, posição 3 mantida"


def test_hba1c_entra_no_dps_como_vulnerabilidade_metabolica(cliente_fila, frames):
    # no DPS a HbA1c é um dos três componentes do fator clínico: 9,1 basta para passar SOL-B
    resposta = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(
        tipo="hba1c", resultado="resultado", valor_numerico=9.1, origem="laboratorio",
    ))
    assert resposta.status_code == 202
    corpo = resposta.get_json()
    assert corpo["events"][-1]["value"] == "9.1"
    assert corpo["urgencyClass"] == "C" and (corpo["position"], corpo["previousPosition"]) == (2, 3)
    assert ordem(cliente_fila) == ["SOL-A", "SOL-C", "SOL-B"]
    patch, audit, atividade = frames()
    assert {e["id"] for e in patch["entries"]} == {"SOL-B", "SOL-C"}
    assert audit["entry"]["kind"] == "recalc" and (audit["entry"]["from"], audit["entry"]["to"]) == (3, 2)
    assert atividade["text"] == "Paciente subiu de 3 para 2 após HbA1c"


def test_quem_a_regulacao_fixou_nao_e_movido_pelo_evento(cliente_fila):
    movida = cliente_fila.post(f"{H}/fila/SOL-B/reordenar", json={
        "position": 3, "reason": "Critério clínico", "justification": JUSTIFICATIVA,
    })
    assert movida.status_code == 200
    assert ordem(cliente_fila) == ["SOL-A", "SOL-C", "SOL-B"]
    cliente_fila.post(f"{H}/fila/eventos", json=[novo_evento("SOL-B"), novo_evento("SOL-B", data_evento="2026-10-21")])
    assert ordem(cliente_fila) == ["SOL-A", "SOL-C", "SOL-B"]
    assert entrada(cliente_fila, "SOL-B")["urgencyClass"] == "B"
    ultima = cliente_fila.get(f"{H}/auditoria").get_json()[0]
    assert "fixada pela regulação" in ultima["justification"]


def test_desistencia_pede_confirmacao_e_nao_tira_da_fila(cliente_fila):
    corpo = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(
        tipo="contato_telefonico", resultado="desistiu", origem="call center",
    )).get_json()
    assert corpo["pendingConfirmation"] is True and corpo["position"] == 3
    assert corpo["warnings"][0]["level"] == "critical"
    pendencia = next(p for p in cliente_fila.get(f"{H}/pendencias").get_json() if p["kind"] == "left_queue")
    assert pendencia["entryIds"] == ["SOL-C"] and pendencia["title"] == "Paciente desistiu"
    ultima = cliente_fila.get(f"{H}/auditoria").get_json()[0]
    assert "o Neco não retira pacientes da fila" in ultima["justification"]


def test_confirmacao_resolvida_nao_volta_com_outro_evento(cliente_fila):
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(tipo="contato_telefonico", resultado="desistiu"))
    pendencia = next(p for p in cliente_fila.get(f"{H}/pendencias").get_json() if p["kind"] == "left_queue")
    cliente_fila.post(f"{H}/pendencias/{pendencia['id']}/resolver", json={"action": "keep"})
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(tipo="falta", resultado="exame"))
    assert entrada(cliente_fila, "SOL-C")["pendingConfirmation"] is False
    # mas um novo aviso de desistência é notícia nova
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(
        tipo="contato_telefonico", resultado="desistiu", data_evento="2026-10-22",
    ))
    assert entrada(cliente_fila, "SOL-C")["pendingConfirmation"] is True


def test_biopsia_positiva_reclassifica_sobe_e_abre_pendencia_sem_cid_de_cancer(cliente_fila, frames):
    corpo = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(
        tipo="biopsia", resultado="positivo", origem="laboratorio de patologia",
    )).get_json()
    # A2 na faixa protegida, com o mesmo DPSS de SOL-A: o empate fica na ordem do dataset
    assert corpo["urgencyClass"] == "A2" and (corpo["position"], corpo["previousPosition"]) == (2, 3)
    assert ordem(cliente_fila) == ["SOL-A", "SOL-C", "SOL-B"]

    patch, audit, subiu, pendencia = frames()
    assert {e["id"] for e in patch["entries"]} == {"SOL-B", "SOL-C"}
    assert audit["entry"]["kind"] == "recalc" and (audit["entry"]["from"], audit["entry"]["to"]) == (3, 2)
    assert "Reclassificado de Moderado (C) para Urgente (A2)" in audit["entry"]["justification"]
    assert subiu["text"] == "Paciente subiu de 3 para 2 após biópsia"
    assert "o CID K40.9 não é de câncer" in pendencia["text"]
    assert any(p["kind"] == "biopsy" and p["entryIds"] == ["SOL-C"] for p in cliente_fila.get(f"{H}/pendencias").get_json())


def test_evento_repetido_nao_conta_duas_vezes(cliente_fila):
    primeiro = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento()).get_json()
    segundo = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento()).get_json()
    assert segundo["score"] == primeiro["score"]
    assert len(segundo["events"]) == 1


def test_evento_ganha_id_sequencial_e_id_repetido_e_conflito(fila, cliente_fila):
    estado = fila.extensions["queue_state"]
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(evento_id="EVT-000041"))
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(data_evento="2026-10-21"))
    assert {"EVT-000041", "EVT-000042"} <= estado.event_ids
    resposta = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(evento_id="EVT-000041", data_evento="2026-10-22"))
    assert resposta.status_code == 409


def test_lote_de_eventos_sem_id_nao_e_conflito(cliente_fila):
    resposta = cliente_fila.post(f"{H}/fila/eventos", json=[
        novo_evento(), novo_evento("SOL-B", data_evento="2026-10-21"),
    ])
    assert resposta.status_code == 202
    assert [e["id"] for e in resposta.get_json()] == ["SOL-C", "SOL-B"]


@pytest.mark.parametrize("campos, status, trecho", [
    ({"solicitacao_id": "SOL-X"}, 404, "solicitação SOL-X não encontrada na fila"),
    ({"paciente_id": "PAC-OUTRO"}, 400, "o paciente PAC-OUTRO não é o da solicitação SOL-C"),
    ({"tipo_evento": "cirurgia"}, 400, "'tipo_evento' deve ser um de: biopsia"),
    ({"resultado": "positivo"}, 400, "'resultado' de pronto_socorro deve ser um de: atendido_liberado, observacao"),
    ({"valor_numerico": 3}, 400, "'valor_numerico' só vale para hba1c e internacao"),
    ({"tipo_evento": "hba1c", "resultado": "resultado"}, 400, "'valor_numerico' é obrigatório em hba1c"),
    ({"data_evento": "2027-01-01"}, 400, "não pode ser posterior à data de referência"),
])
def test_evento_invalido_e_recusado(cliente_fila, campos, status, trecho):
    resposta = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(**campos))
    assert resposta.status_code == status
    assert trecho in resposta.get_json()["detail"]


def test_evento_para_quem_saiu_da_fila_e_recusado(cliente_fila):
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(tipo="contato_telefonico", resultado="desistiu"))
    pendencia = next(p for p in cliente_fila.get(f"{H}/pendencias").get_json() if p["kind"] == "left_queue")
    cliente_fila.post(f"{H}/pendencias/{pendencia['id']}/resolver", json={"action": "remove", "values": {"confirmacao": "ligacao"}})
    resposta = cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(data_evento="2026-10-22"))
    assert resposta.status_code == 404


# --- o verificador enxerga o que entrou --------------------------------------

def test_impacto_manda_as_linhas_ingeridas_ao_verificador(fila, cliente_fila, monkeypatch):
    chamadas = []

    def falso(texto, dataset_dir, extra=None):
        chamadas.append(extra)
        return True, "RESULTADO: OK"

    monkeypatch.setattr(verifier, "run", falso)
    cliente_fila.post(f"{H}/fila/entradas", json=nova_entrada())
    cliente_fila.get(f"{H}/painel/impacto")
    assert [r["solicitacao_id"] for r in chamadas[0]["fila"]] == ["SOL-NOVA"]
    assert chamadas[0]["fila"][0]["cid_principal"] == "C50.9"
    # um evento que não move ninguém ainda muda quem é calmo: o cache não serve mais
    cliente_fila.post(f"{H}/fila/eventos", json=novo_evento(tipo="falta", resultado="exame"))
    cliente_fila.get(f"{H}/painel/impacto")
    assert len(chamadas) == 4 and chamadas[-1]["eventos"][0]["tipo_evento"] == "falta"


def test_copia_do_dataset_recebe_as_linhas_no_cabecalho_de_origem(tmp_path):
    origem = tmp_path / "origem"
    origem.mkdir()
    (origem / "fila_cirurgica.csv").write_text("solicitacao_id,cid_principal\nSOL-1,K40.9\n", encoding="utf-8")
    (origem / "eventos_clinicos.csv").write_text("evento_id,solicitacao_id\n", encoding="utf-8")
    (tmp_path / "trabalho").mkdir()
    destino = verifier._extended_dataset(origem, tmp_path / "trabalho", {
        "fila": [{"cid_principal": "C50.9", "solicitacao_id": "SOL-2", "nome_paciente": "fora do cabeçalho"}],
        "eventos": [],
    })
    assert (destino / "fila_cirurgica.csv").read_text(encoding="utf-8").splitlines() == [
        "solicitacao_id,cid_principal", "SOL-1,K40.9", "SOL-2,C50.9",
    ]
    assert (origem / "fila_cirurgica.csv").read_text(encoding="utf-8").count("\n") == 2  # origem intacta


# --- dataset real ------------------------------------------------------------

@pytest.fixture()
def app_real():
    return create_app("teste")


ENTRADA_REAL = nova_entrada("SOL-2026-09001", paciente_id="PAC-09001")


def test_oncologico_novo_no_dataset_real_respeita_a_regra_de_ouro(app_real):
    cliente = app_real.test_client()
    resposta = cliente.post(f"{H}/fila/entradas", json=ENTRADA_REAL)
    assert resposta.status_code == 201
    estado = app_real.extensions["queue_state"]
    assert len(estado.order) == 942
    assert golden_rule_violation(estado.order, estado.assessments) is None
    primeiro_calmo = next(i for i, rid in enumerate(estado.order, start=1) if estado.assessments[rid]["no_urgency"])
    assert resposta.get_json()["position"] < primeiro_calmo


def test_id_do_mock_do_front_ja_existe_no_dataset_real(app_real):
    """SOL-2026-00942, a "Rosa" do mockBackend.ts, colide com o dataset: 409, não 500."""
    resposta = app_real.test_client().post(f"{H}/fila/entradas", json=nova_entrada("SOL-2026-00942"))
    assert resposta.status_code == 409


@pytest.mark.lento
def test_fila_com_ingestao_passa_no_verificador_oficial(app_real):
    cliente = app_real.test_client()
    cliente.post(f"{H}/fila/entradas", json=[
        ENTRADA_REAL,
        nova_entrada("SOL-2026-09002", paciente_id="PAC-09002", cid_principal="K40.9",
                     procedimento_id="PROC001", intensidade_dor_eva=1),
    ])
    cliente.post(f"{H}/fila/eventos", json=novo_evento(
        "SOL-2026-09002", paciente_id="PAC-09002", tipo="internacao", resultado="alta", valor_numerico=3,
    ))
    corpo = cliente.get(f"{H}/painel/impacto").get_json()
    neco = corpo["verifier"]["neco"]
    assert neco["ok"] is True and neco["violacoes"] == 0, neco["output"]
    assert "943 posições" in neco["output"] and "/tmp" not in neco["output"]


# --- contrato com o simulador (simulador/, em Go) ------------------------------

SIMULADOR = Path(__file__).resolve().parents[2] / "simulador"
GO = shutil.which("go") or ("/usr/local/go/bin/go" if Path("/usr/local/go/bin/go").exists() else None)


@pytest.mark.lento
@pytest.mark.skipif(GO is None, reason="Go não instalado: o contrato com o simulador não roda aqui")
def test_dados_do_simulador_passam_na_ingestao_e_pulam_na_fila(app_real):
    """O que o simulador manda é aceito, e nenhuma história empurra o paciente para baixo.

    No DPSS o salto depende do perfil: varizes, cálculo e nódulo sobem centenas de
    posições; artrose e hérnia sobem menos; o câncer já entra na faixa protegida e
    quase não se mexe com os eventos.

    Roda o `-dump` do simulador com semente fixa: 27 entradas cobrem os nove perfis, cada
    uma com os 2 eventos que recebe no ritmo padrão (um a cada 5 s, entrada a cada 10 s).
    """
    feito = subprocess.run(
        [GO, "run", ".", "-dump", "27"], cwd=SIMULADOR, capture_output=True, text=True,
        env={**os.environ, "SIM_SEED": "7"}, timeout=300,
    )
    assert feito.returncode == 0, feito.stderr
    lote = json.loads(feito.stdout)
    cliente = app_real.test_client()
    for corpo in lote["entradas"]:
        resposta = cliente.post(f"{H}/fila/entradas", json=corpo)
        assert resposta.status_code == 201, resposta.get_json()
        entrou = resposta.get_json()["position"]
        eventos = [e for e in lote["eventos"] if e["solicitacao_id"] == corpo["solicitacao_id"]]
        for evento in eventos:
            resposta = cliente.post(f"{H}/fila/eventos", json=evento)
            assert resposta.status_code == 202, resposta.get_json()
        final = resposta.get_json()["position"]
        assert final <= entrou, f"{corpo['cid_principal']}: {entrou} → {final}"
    estado = app_real.extensions["queue_state"]
    assert len(estado.order) == 941 + 27
    assert golden_rule_violation(estado.order, estado.assessments) is None
