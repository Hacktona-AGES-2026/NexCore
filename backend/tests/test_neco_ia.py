"""Testes dos textos do Neco escritos por IA (app/neco_ia).

Nenhum teste chama o Gemini: `ProvedorFalso` responde o que o teste mandar e
conta as chamadas. O que se trava aqui é a segurança do desenho — o texto da IA
só aparece se todos os números dele estiverem nos dados, qualquer falha cai no
texto por regras, e as respostas ficam em cache até os dados mudarem.
"""
import pytest

from app import create_app
from app.neco_ia import Neco, ProviderUnavailable, RateGate
from app.neco_ia.verify import invented_numbers

H = "/v1/hospitais/hsl"
JUSTIFICATIVA = "Angina instável confirmada com a cardiologia, lesão de tronco."


class ProvedorFalso:
    def __init__(self, resposta=None, erro=None, chat=None):
        self.resposta = resposta
        self.erro = erro
        self.resposta_chat = chat
        self.chamadas = []

    def generate_json(self, system, prompt, schema):
        self.chamadas.append(prompt)
        if self.erro:
            raise self.erro
        return self.resposta(prompt) if callable(self.resposta) else self.resposta

    def chat(self, system, history, question, tools):
        self.chamadas.append((question, history, [t.__name__ for t in tools]))
        if self.erro:
            raise self.erro
        return self.resposta_chat


@pytest.fixture()
def app_nova():
    return create_app("teste")


def com_provedor(app, provedor):
    app.extensions["neco"] = Neco(provedor)
    return app.test_client()


def estado(app):
    return app.extensions["queue_state"]


def primeiro(app, classe):
    return next(e for e in estado(app).entries() if e["urgencyClass"] == classe)


# --- verificador de números ------------------------------------------------

def test_verificador_aceita_numeros_que_estao_nos_dados():
    fatos = {"posicao": 404, "dias": 409, "indice": 48.8, "data": "2026-10-09"}
    assert invented_numbers("Posição 404, espera de 409 dias, índice 48,8 em 09/10/2026.", fatos) == set()


def test_verificador_aponta_numero_inventado():
    assert invented_numbers("Está na posição 12.", {"posicao": 404}) == {"12"}


# --- explicação do paciente --------------------------------------------------

def test_sem_chave_a_explicacao_e_a_por_regras(app_nova):
    cliente = app_nova.test_client()
    e = primeiro(app_nova, "C")
    corpo = cliente.get(f"{H}/fila/{e['id']}/explicacao").get_json()
    assert corpo["source"] == "regras"
    assert corpo["verified"] is True
    assert corpo["text"].startswith("Moderado (C):")
    assert any("dias" in p for p in corpo["points"])


def test_explicacao_da_ia_aparece_quando_passa_na_verificacao(app_nova):
    e = primeiro(app_nova, "A1")
    resposta = {"headline": f"Muito urgente: câncer com piora, posição {e['position']}.", "points": ["Prazo vencido."]}
    cliente = com_provedor(app_nova, ProvedorFalso(resposta))
    corpo = cliente.get(f"{H}/fila/{e['id']}/explicacao").get_json()
    assert corpo == {"text": resposta["headline"], "points": ["Prazo vencido."], "source": "ia", "verified": True}


def test_explicacao_com_numero_inventado_cai_nas_regras(app_nova):
    e = primeiro(app_nova, "A1")
    cliente = com_provedor(app_nova, ProvedorFalso({"headline": "Está na posição 99999.", "points": []}))
    assert cliente.get(f"{H}/fila/{e['id']}/explicacao").get_json()["source"] == "regras"


def test_falha_do_modelo_cai_nas_regras_sem_vazar_o_erro(app_nova):
    e = primeiro(app_nova, "B")
    cliente = com_provedor(app_nova, ProvedorFalso(erro=ProviderUnavailable("gemini 429")))
    resposta = cliente.get(f"{H}/fila/{e['id']}/explicacao")
    assert resposta.status_code == 200
    assert resposta.get_json()["source"] == "regras"
    assert "429" not in resposta.get_data(as_text=True)


def test_resposta_fora_do_formato_cai_nas_regras(app_nova):
    e = primeiro(app_nova, "B")
    cliente = com_provedor(app_nova, ProvedorFalso({"outra": "coisa"}))
    assert cliente.get(f"{H}/fila/{e['id']}/explicacao").get_json()["source"] == "regras"


def test_explicacao_fica_em_cache_ate_o_paciente_mudar(app_nova):
    e = primeiro(app_nova, "C")
    provedor = ProvedorFalso(lambda prompt: {"headline": "Moderado.", "points": []})
    cliente = com_provedor(app_nova, provedor)
    url = f"{H}/fila/{e['id']}/explicacao"
    cliente.get(url)
    cliente.get(url)
    assert len(provedor.chamadas) == 1
    cliente.post(f"{H}/fila/{e['id']}/reordenar",
                 json={"position": e["position"] - 5, "reason": "Informação clínica nova", "justification": JUSTIFICATIVA})
    cliente.get(url)
    assert len(provedor.chamadas) == 2


def test_explicacao_recebe_a_justificativa_manual_e_a_posicao_sem_intervencao(app_nova):
    e = primeiro(app_nova, "C")
    provedor = ProvedorFalso({"headline": "Moderado.", "points": []})
    cliente = com_provedor(app_nova, provedor)
    destino = e["position"] - 20
    cliente.post(f"{H}/fila/{e['id']}/reordenar",
                 json={"position": destino, "reason": "Informação clínica nova", "justification": JUSTIFICATIVA})
    cliente.get(f"{H}/fila/{e['id']}/explicacao")
    prompt = provedor.chamadas[-1]
    assert JUSTIFICATIVA in prompt
    assert f'"posicao_sem_intervencao_manual": {e["position"]}' in prompt
    assert '"posicao_definida_manualmente": true' in prompt


def test_explicacao_de_solicitacao_inexistente_e_404(app_nova):
    resposta = app_nova.test_client().get(f"{H}/fila/SOL-0000-00000/explicacao")
    assert resposta.status_code == 404
    assert "detail" in resposta.get_json()


# --- posição sem intervenção manual -----------------------------------------

def test_posicao_sugerida_acompanha_a_fila_e_fica_quando_alguem_e_movido(app_nova):
    cliente = app_nova.test_client()
    e = primeiro(app_nova, "C")
    assert e["suggestedPosition"] == e["position"]
    cliente.post(f"{H}/fila/{e['id']}/reordenar",
                 json={"position": e["position"] - 20, "reason": "Informação clínica nova", "justification": JUSTIFICATIVA})
    movido = next(x for x in estado(app_nova).entries() if x["id"] == e["id"])
    assert movido["position"] == e["position"] - 20
    assert movido["suggestedPosition"] == e["position"]


# --- equidade e impacto -------------------------------------------------------

def test_painel_de_equidade_nao_espera_pelo_comentario(app_nova):
    assert "insight" not in app_nova.test_client().get(f"{H}/painel/equidade").get_json()


def test_equidade_traz_comentario_por_regras_sem_chave(app_nova):
    insight = app_nova.test_client().get(f"{H}/painel/equidade/comentario").get_json()
    assert insight["source"] == "regras"
    assert "200 km" in insight["text"]


def test_comentario_de_equidade_da_ia_com_numeros_dos_dados(app_nova):
    relatorio = estado(app_nova).equity()
    longe, perto = relatorio["byDistance"][-1], relatorio["byDistance"][0]
    texto = f"Quem mora longe espera {longe['avgWait']} dias, contra {perto['avgWait']}."
    cliente = com_provedor(app_nova, ProvedorFalso({"text": texto}))
    insight = cliente.get(f"{H}/painel/equidade/comentario").get_json()
    assert insight == {"text": texto, "source": "ia", "verified": True}


def test_comentario_de_impacto_usa_os_numeros_do_verificador():
    relatorio = {
        "verifier": {
            "neco": {"ok": True, "violacoes": 0, "medianaOnco": 112, "oncoPrimeiroTerco": 100, "psPrimeiraMetade": 87, "calmosUltimoTerco": 97},
            "manual": {"ok": False, "violacoes": 177, "medianaOnco": 287, "oncoPrimeiroTerco": 53, "psPrimeiraMetade": 38, "calmosUltimoTerco": 49},
        },
        "headline": {"a1Total": 29, "a1Low": 15, "urgentTotal": 200, "urgentLow": 47, "dTotal": 292, "dHigh": 66},
        "movers": [],
    }
    regras = Neco().impact_insight(relatorio)
    assert regras["source"] == "regras" and "177" in regras["text"]
    ia = Neco(ProvedorFalso({"text": "A fila manual tem 177 violações; a do Neco, 0."})).impact_insight(relatorio)
    assert ia["source"] == "ia"
    inventado = Neco(ProvedorFalso({"text": "A fila manual tem 500 violações."})).impact_insight(relatorio)
    assert inventado["source"] == "regras"


# --- Pergunte ao Neco -------------------------------------------------------

def test_chat_da_ia_devolve_texto_e_os_pacientes_citados(app_nova):
    e = primeiro(app_nova, "A1")
    texto = f"O primeiro da fila é {e['name']} ({e['id']}). SOL-9999-99999 não existe."
    provedor = ProvedorFalso(chat=texto)
    cliente = com_provedor(app_nova, provedor)
    historico = [{"from": "me", "text": "oi"}, {"from": "neco", "text": "Olá!"}, {"from": "x", "text": "ignorado"}]
    corpo = cliente.post(f"{H}/neco/perguntar", json={"question": "Quem é o primeiro?", "history": historico}).get_json()
    assert corpo == {"text": texto, "entryIds": [e["id"]]}
    pergunta, enviado, ferramentas = provedor.chamadas[0]
    assert pergunta == "Quem é o primeiro?"
    assert [t["from"] for t in enviado] == ["me", "neco"]
    assert "detalhar_solicitacao" in ferramentas and "historico" in ferramentas


def test_chat_cai_nas_palavras_chave_quando_o_modelo_falha(app_nova):
    cliente = com_provedor(app_nova, ProvedorFalso(erro=ProviderUnavailable("timeout")))
    corpo = cliente.post(f"{H}/neco/perguntar", json={"question": "Quantos casos A1 temos?"}).get_json()
    assert corpo["text"].startswith("Temos 29 casos A1")


def test_historico_que_nao_e_lista_e_recusado(app_nova):
    resposta = app_nova.test_client().post(f"{H}/neco/perguntar", json={"question": "oi", "history": "x"})
    assert resposta.status_code == 400


def test_ferramentas_do_chat_so_leem(app_nova):
    from app.neco_ia.chat import RULES_SUMMARY, build_tools

    snapshot = {**estado(app_nova).chat_snapshot(), "rules": RULES_SUMMARY}
    ferramentas = {f.__name__: f for f in build_tools(snapshot)}
    antes = [e["id"] for e in estado(app_nova).entries()]
    e = primeiro(app_nova, "A1")
    detalhe = ferramentas["detalhar_solicitacao"](e["id"].lower())
    assert detalhe["posicao"] == e["position"] and detalhe["logo_acima"] is None
    assert ferramentas["listar_fila"](classe="a1", limite=3)["total"] == 29
    assert ferramentas["buscar_pacientes"](e["name"].split()[0])["total"] >= 1
    assert "erro" in ferramentas["detalhar_solicitacao"]("SOL-0000-00000")
    assert [x["id"] for x in estado(app_nova).entries()] == antes


# --- ritmo de chamadas -------------------------------------------------------

def test_ritmo_deixa_passar_varias_chamadas_seguidas_dentro_do_limite():
    esperas = []
    portao = RateGate(per_minute=3, max_wait=3, clock=lambda: 0.0, sleep=esperas.append)
    for _ in range(3):
        portao.acquire()
    assert esperas == []


def test_ritmo_desiste_em_vez_de_travar_a_tela_quando_o_minuto_esta_cheio():
    portao = RateGate(per_minute=2, max_wait=3, clock=lambda: 0.0, sleep=lambda s: None)
    portao.acquire()
    portao.acquire()
    with pytest.raises(ProviderUnavailable):
        portao.acquire()


def test_ritmo_espera_pouco_quando_a_chamada_mais_antiga_esta_saindo_da_janela():
    agora = [0.0]
    esperas = []
    portao = RateGate(per_minute=1, max_wait=3, clock=lambda: agora[0], sleep=esperas.append)
    portao.acquire()
    agora[0] = 58.0
    portao.acquire()
    assert esperas == [2.0]
