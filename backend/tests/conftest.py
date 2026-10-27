from pathlib import Path
import csv
import json

import pytest

from app import create_app

COLUNAS_FILA_NORM = [
    "solicitacao_id", "paciente_id", "nome_paciente", "sexo", "idade", "municipio",
    "uf", "distancia_hospital_km", "procedimento_id", "procedimento", "especialidade",
    "cid_principal", "cid_descricao", "cid_secundario", "asa", "comorbidades",
    "intensidade_dor_eva", "limitacao_funcional", "justificativa_clinica",
    "observacoes", "data_entrada_fila", "dias_em_fila", "prioridade_regulacao",
    "data_ultima_revisao_prioridade", "flag_oncologico", "flag_diabetico",
    "flag_piora_clinica", "hba1c_ultima", "data_hba1c_ultima",
    "avaliacao_pre_anestesica", "exames_pre_op_validos", "cid_principal_norm",
    "cid_secundario_norm", "oncologico_cid", "municipio_norm",
    "prioridade_regulacao_norm", "flag_oncologico_norm", "flag_diabetico_norm",
    "flag_piora_clinica_norm", "avaliacao_pre_anestesica_norm",
    "exames_pre_op_validos_norm", "limitacao_funcional_norm", "sexo_norm",
    "id_municipio", "inse_medio", "s_vulnerabilidade",
    "s_vulnerabilidade_imputada", "s_evfam", "s_ibge", "s_social",
    "s_social_source", "s_evfam_colunas_utilizadas", "s_geografico",
    "s_distancia_imputada", "s_distancia_teto_km",
]
COLUNAS_EVENTOS_NORM = [
    "evento_id", "solicitacao_id", "paciente_id", "data_evento", "tipo_evento",
    "resultado", "valor_numerico", "descricao", "origem", "tipo_evento_norm",
    "resultado_norm", "duplicata_conteudo", "solicitacao_na_fila",
    "paciente_coincide_fila",
]
COLUNAS_PROCS_NORM = [
    "procedimento_id", "procedimento", "especialidade", "porte", "risco_cirurgico",
    "duracao_media_min", "necessita_uti", "porte_norm", "necessita_uti_norm",
    "especialidade_norm",
]
COLUNAS_SWALIS_NORM = ["classe", "descricao", "prazo_maximo_dias", "exemplos", "classe_norm"]
# Os prazos de referencias/swalis.csv. A fila da regulação calcula o DPS ao criar a app,
# e o DPS recusa classe sem prazo: sem esta tabela a app nem sobe.
SWALIS_PADRAO = [
    {"classe": classe, "prazo_maximo_dias": prazo, "classe_norm": classe}
    for classe, prazo in (("A1", 15), ("A2", 21), ("B", 60), ("C", 180), ("D", 360))
]
COLUNAS_SOCIOECONOMIC_NORM = [
    "id_municipio", "inse_medio", "observacoes_inse", "s_vulnerabilidade",
    "source", "source_year", "source_version", "weight_method",
]
COLUNAS_DISEASE_BURDEN_NORM = [
    "cid_prefix_norm", "health_state", "disability_weight_norm", "source",
    "source_version", "mapping_method",
]


# --- aplicação sobre o dataset real --------------------------------------

@pytest.fixture(scope="session")
def app():
    return create_app("teste")


@pytest.fixture()
def cliente(app):
    return app.test_client()


@pytest.fixture(scope="session")
def repo(app):
    return app.extensions["repository"]


# --- dataset sintético, para controlar os valores exatos ------------------

def _escrever(caminho, colunas, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas)
        escritor.writeheader()
        for linha in linhas:
            completa = dict.fromkeys(colunas, "")
            completa.update({k: "" if v is None else str(v) for k, v in linha.items()})
            escritor.writerow(completa)


@pytest.fixture()
def dataset_sintetico(tmp_path):
    """Monta um diretório no formato de dataset/normalizado/ com linhas controladas."""

    def montar(
        fila=(),
        eventos=(),
        procedimentos=(),
        swalis=SWALIS_PADRAO,
        socioeconomic=None,
        disease_burden=None,
    ):
        destino = tmp_path / "normalizado"
        _escrever(destino / "fila_cirurgica_normalizada.csv", COLUNAS_FILA_NORM, fila)
        _escrever(destino / "eventos_clinicos_normalizados.csv", COLUNAS_EVENTOS_NORM, eventos)
        _escrever(destino / "procedimentos_normalizados.csv", COLUNAS_PROCS_NORM, procedimentos)
        _escrever(destino / "swalis_normalizado.csv", COLUNAS_SWALIS_NORM, swalis)
        if socioeconomic is not None:
            _escrever(
                destino / "socioeconomic_normalized.csv",
                COLUNAS_SOCIOECONOMIC_NORM,
                socioeconomic,
            )
        if disease_burden is not None:
            _escrever(
                destino / "disease_burden_normalized.csv",
                COLUNAS_DISEASE_BURDEN_NORM,
                disease_burden,
            )
        return destino

    return montar


@pytest.fixture()
def app_sintetico(dataset_sintetico):
    """Aplicação apontada para um dataset sintético."""

    def montar(**tabelas):
        destino = dataset_sintetico(**tabelas)
        return create_app(
            "teste",
            DATASET_DIR=Path(destino),
            VERIFIER_DATASET_DIR=Path(destino),
        )

    return montar


# --- canal WebSocket ------------------------------------------------------

class WsFalso:
    """Duplo do socket: entrega comandos de uma lista e guarda o que foi enviado.

    `channel.serve` só chama receive()/send(), então isso basta para exercitar o
    canal inteiro sem rede. receive() devolvendo None imita o cliente fechando.
    """

    def __init__(self, comandos=()):
        self.pendentes = [
            c if isinstance(c, str) else json.dumps(c) for c in comandos
        ]
        self.enviados = []

    def receive(self):
        return self.pendentes.pop(0) if self.pendentes else None

    def send(self, texto):
        self.enviados.append(json.loads(texto))

    # --- leitura dos frames recebidos ---

    @property
    def frames(self):
        """Tudo que o servidor mandou, menos o welcome inicial."""
        return [f for f in self.enviados if f["type"] != "welcome"]

    @property
    def welcome(self):
        return self.enviados[0]

    def tipos(self, tipo):
        return [f for f in self.frames if f["type"] == tipo]

    def primeiro(self, tipo):
        frames = self.tipos(tipo)
        assert frames, f"nenhum frame '{tipo}' em {[f['type'] for f in self.frames]}"
        return frames[0]

    def payload(self):
        return self.primeiro("result")["payload"]


@pytest.fixture()
def conversa(app):
    """Roda uma conversa inteira no canal e devolve o socket falso."""
    from app.realtime import limits
    from app.realtime.channel import serve

    def rodar(*comandos):
        ws = WsFalso(comandos)
        with app.app_context():
            serve(ws, app.extensions["repository"], limits(app.config))
        return ws

    return rodar


@pytest.fixture()
def pedir(conversa):
    """Atalho: manda uma ação e devolve o payload do result."""

    def chamar(action, **params):
        return conversa({"id": "c1", "action": action, "params": params}).payload()

    return chamar
