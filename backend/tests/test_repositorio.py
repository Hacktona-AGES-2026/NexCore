"""Testes do repositório com dataset sintético, para fixar os valores exatos."""
import pytest

from app.data.repository import Repository

TRES_CASOS = [
    {
        "solicitacao_id": "SOL-A", "paciente_id": "PAC-1", "nome_paciente": "Ana Lima",
        "procedimento_id": "PROC011", "procedimento": "Mastectomia",
        "especialidade": "Mastologia",
        "cid_principal": "C50.4", "cid_principal_norm": "C504", "oncologico_cid": "sim",
        "flag_oncologico_norm": "nao", "prioridade_regulacao_norm": "baixa",
        "municipio_norm": "Porto Alegre", "idade": "70", "dias_em_fila": "600",
        "intensidade_dor_eva": "5", "data_entrada_fila": "2025-02-23",
        "justificativa_clinica": "Carcinoma ductal invasivo.",
    },
    {
        "solicitacao_id": "SOL-B", "paciente_id": "PAC-2", "nome_paciente": "Bruno Sá",
        "procedimento_id": "PROC002", "procedimento": "Herniorrafia",
        "especialidade": "Cirurgia Geral",
        "cid_principal": "K40.9", "cid_principal_norm": "K409", "oncologico_cid": "nao",
        "flag_oncologico_norm": "nao", "prioridade_regulacao_norm": "alta",
        "municipio_norm": "Pelotas", "idade": "40", "dias_em_fila": "1200",
        "intensidade_dor_eva": "8", "data_entrada_fila": "2023-06-01",
        "justificativa_clinica": "Hernia com dor.",
    },
    {
        "solicitacao_id": "SOL-C", "paciente_id": "PAC-3", "nome_paciente": "Clara Rocha",
        "procedimento_id": "PROC001", "procedimento": "Facectomia",
        "especialidade": "Oftalmologia",
        "cid_principal": "H25.1", "cid_principal_norm": "H251", "oncologico_cid": "nao",
        "flag_oncologico_norm": "sim", "prioridade_regulacao_norm": "media",
        "municipio_norm": "Canoas", "idade": "80", "dias_em_fila": "100",
        "intensidade_dor_eva": "", "data_entrada_fila": "2026-07-15",
        "justificativa_clinica": "Catarata madura.",
    },
]


@pytest.fixture()
def repo_mini(dataset_sintetico):
    destino = dataset_sintetico(
        fila=TRES_CASOS,
        eventos=[
            {"evento_id": "EVT-3", "solicitacao_id": "SOL-A", "paciente_id": "PAC-1",
             "data_evento": "2026-03-01", "tipo_evento": "biopsia",
             "tipo_evento_norm": "biopsia", "resultado_norm": "positivo",
             "solicitacao_na_fila": "sim"},
            {"evento_id": "EVT-1", "solicitacao_id": "SOL-A", "paciente_id": "PAC-1",
             "data_evento": "2025-05-10", "tipo_evento": "pronto_socorro",
             "tipo_evento_norm": "pronto_socorro", "solicitacao_na_fila": "sim"},
            {"evento_id": "EVT-2", "solicitacao_id": "SOL-A", "paciente_id": "PAC-1",
             "data_evento": "2026-01-20", "tipo_evento": "hba1c",
             "tipo_evento_norm": "hba1c", "valor_numerico": "8.4",
             "solicitacao_na_fila": "sim"},
            {"evento_id": "EVT-4", "solicitacao_id": "SOL-FORA", "paciente_id": "PAC-9",
             "data_evento": "2026-02-02", "tipo_evento": "falta",
             "tipo_evento_norm": "falta", "solicitacao_na_fila": "nao"},
        ],
        procedimentos=[
            {"procedimento_id": "PROC011", "procedimento": "Mastectomia",
             "risco_cirurgico": "3", "necessita_uti": "nao", "necessita_uti_norm": "nao"},
        ],
        swalis=[{"classe": "A1", "prazo_maximo_dias": "15", "classe_norm": "A1"}],
    )
    return Repository(destino, "2026-10-23")


# --- índices e junções ----------------------------------------------------

def test_contagens(repo_mini):
    assert repo_mini.counts() == {
        "fila": 3, "eventos": 4, "procedimentos": 1, "swalis": 1
    }


def test_obtem_solicitacao_por_id(repo_mini):
    assert repo_mini.get_request("SOL-B")["procedimento"] == "Herniorrafia"
    assert repo_mini.get_request("SOL-INEXISTENTE") is None


def test_procedimento_sem_catalogo_devolve_none(repo_mini):
    assert repo_mini.get_procedure("PROC011") is not None
    assert repo_mini.get_procedure("PROC002") is None


def test_eventos_vem_ordenados_por_data(repo_mini):
    datas = [e["data_evento"] for e in repo_mini.events_for_request("SOL-A")]
    assert datas == ["2025-05-10", "2026-01-20", "2026-03-01"]


def test_eventos_de_solicitacao_sem_evento(repo_mini):
    assert repo_mini.events_for_request("SOL-B") == []


def test_evento_orfao_fica_acessivel_pelo_paciente(repo_mini):
    assert len(repo_mini.events_for_patient("PAC-9")) == 1


# --- filtros --------------------------------------------------------------

def ids(registros):
    return sorted(r["solicitacao_id"] for r in registros)


def test_filtro_vazio_devolve_tudo(repo_mini):
    assert ids(repo_mini.filter({})) == ["SOL-A", "SOL-B", "SOL-C"]


def test_filtro_oncologico_usa_o_cid_e_ignora_a_flag(repo_mini):
    assert ids(repo_mini.filter({"oncologico": True})) == ["SOL-A"]
    assert ids(repo_mini.filter({"oncologico": False})) == ["SOL-B", "SOL-C"]


def test_filtro_por_especialidade_normalizada(repo_mini):
    assert ids(repo_mini.filter({"especialidade": "cirurgia geral"})) == ["SOL-B"]


def test_filtro_por_prioridade(repo_mini):
    assert ids(repo_mini.filter({"prioridade": "media"})) == ["SOL-C"]


def test_filtro_por_municipio_e_procedimento(repo_mini):
    assert ids(repo_mini.filter({"municipio": "pelotas"})) == ["SOL-B"]
    assert ids(repo_mini.filter({"procedimento_id": "PROC001"})) == ["SOL-C"]


def test_filtro_por_faixa_de_espera(repo_mini):
    assert ids(repo_mini.filter({"dias_minimo": 500})) == ["SOL-A", "SOL-B"]
    assert ids(repo_mini.filter({"dias_maximo": 500})) == ["SOL-C"]
    assert ids(repo_mini.filter({"dias_minimo": 200, "dias_maximo": 800})) == ["SOL-A"]


def test_filtro_por_idade_minima(repo_mini):
    assert ids(repo_mini.filter({"idade_minima": 70})) == ["SOL-A", "SOL-C"]


def test_filtros_combinam_com_e_logico(repo_mini):
    assert ids(repo_mini.filter({"oncologico": False, "dias_minimo": 1000})) == ["SOL-B"]
    assert repo_mini.filter({"oncologico": True, "dias_minimo": 1000}) == []


def test_busca_cobre_texto_livre_e_cid(repo_mini):
    assert ids(repo_mini.filter({"busca": "carcinoma"})) == ["SOL-A"]
    assert ids(repo_mini.filter({"busca": "k40.9"})) == ["SOL-B"]
    assert ids(repo_mini.filter({"busca": "pac-3"})) == ["SOL-C"]


def test_busca_ignora_acento_do_dado(repo_mini):
    assert ids(repo_mini.filter({"busca": "bruno sa"})) == ["SOL-B"]


# --- ordenação ------------------------------------------------------------

def test_ordena_por_espera_decrescente(repo_mini):
    ordenado = repo_mini.sort(repo_mini.queue, "dias_em_fila", True)
    assert [r["solicitacao_id"] for r in ordenado] == ["SOL-B", "SOL-A", "SOL-C"]


def test_ordena_por_idade_crescente(repo_mini):
    ordenado = repo_mini.sort(repo_mini.queue, "idade", False)
    assert [r["solicitacao_id"] for r in ordenado] == ["SOL-B", "SOL-A", "SOL-C"]


def test_campo_de_ordenacao_desconhecido_cai_para_id(repo_mini):
    ordenado = repo_mini.sort(repo_mini.queue, "inventado", False)
    assert [r["solicitacao_id"] for r in ordenado] == ["SOL-A", "SOL-B", "SOL-C"]


def test_ordenacao_trata_nulo_sem_quebrar(repo_mini):
    ordenado = repo_mini.sort(repo_mini.queue, "intensidade_dor_eva", True)
    assert ordenado[-1]["solicitacao_id"] == "SOL-C"


# --- agregações -----------------------------------------------------------

def test_estatisticas_do_mini_dataset(repo_mini):
    e = repo_mini.statistics()
    assert e["total_solicitacoes"] == 3
    assert e["oncologicos_por_cid"] == 1
    assert e["flag_oncologica_divergente"] == 2
    assert e["espera_dias"] == {
        "minima": 100, "maxima": 1200, "media": 633.3, "acima_de_365": 2
    }
    assert e["por_prioridade"] == {"alta": 1, "baixa": 1, "media": 1}
    assert e["eventos_por_tipo"] == {
        "biopsia": 1, "pronto_socorro": 1, "hba1c": 1, "falta": 1
    }


def test_pares_repetidos_sao_contados(dataset_sintetico):
    destino = dataset_sintetico(fila=[
        {"solicitacao_id": "SOL-1", "paciente_id": "PAC-1", "procedimento_id": "PROC001"},
        {"solicitacao_id": "SOL-2", "paciente_id": "PAC-1", "procedimento_id": "PROC001"},
        {"solicitacao_id": "SOL-3", "paciente_id": "PAC-2", "procedimento_id": "PROC001"},
    ])
    repo = Repository(destino, "2026-10-23")
    assert repo.statistics()["pares_paciente_procedimento_repetidos"] == 1
    assert repo.counts()["fila"] == 3


def test_prioridade_vazia_conta_como_indefinido(dataset_sintetico):
    destino = dataset_sintetico(fila=[
        {"solicitacao_id": "SOL-1", "prioridade_regulacao_norm": ""},
        {"solicitacao_id": "SOL-2", "prioridade_regulacao_norm": "alta"},
    ])
    repo = Repository(destino, "2026-10-23")
    assert repo.statistics()["por_prioridade"] == {"indefinido": 1, "alta": 1}


def test_fila_vazia_nao_divide_por_zero(dataset_sintetico):
    repo = Repository(dataset_sintetico(fila=[]), "2026-10-23")
    e = repo.statistics()
    assert e["total_solicitacoes"] == 0
    assert e["espera_dias"]["media"] == 0
    assert repo.specialties() == []


def test_listas_de_referencia_sao_ordenadas_e_sem_vazio(repo_mini):
    assert repo_mini.specialties() == ["Cirurgia Geral", "Mastologia", "Oftalmologia"]
    assert repo_mini.priorities() == ["alta", "baixa", "media"]
