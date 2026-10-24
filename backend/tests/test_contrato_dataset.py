"""Contrato entre o backend e os CSVs de dataset/normalizado/.

Estes testes rodam contra os dados reais e travam o que o código assume sobre
eles. Se o normalizador renomear ou remover uma coluna, a quebra aparece aqui
em vez de virar filtro que devolve lista vazia em silêncio.
"""
from app.data.repository import SEARCH_FIELDS, SORT_KEYS

CAMPOS_USADOS_NA_FILA = {
    "solicitacao_id", "paciente_id", "procedimento_id", "especialidade",
    "municipio_norm", "prioridade_regulacao_norm", "oncologico_cid",
    "flag_oncologico_norm", "dias_em_fila", "idade", "intensidade_dor_eva",
    "data_entrada_fila",
}
CAMPOS_USADOS_NOS_EVENTOS = {
    "evento_id", "solicitacao_id", "paciente_id", "data_evento", "tipo_evento_norm",
}


def test_fila_tem_as_colunas_que_o_backend_usa(repo):
    presentes = set(repo.queue[0])
    assert CAMPOS_USADOS_NA_FILA <= presentes
    assert set(SEARCH_FIELDS) <= presentes
    assert set(SORT_KEYS) <= presentes


def test_eventos_tem_as_colunas_que_o_backend_usa(repo):
    assert CAMPOS_USADOS_NOS_EVENTOS <= set(repo.events[0])


def test_catalogo_e_swalis_tem_as_colunas_usadas(repo):
    assert {"procedimento_id", "risco_cirurgico", "porte"} <= set(repo.procedures[0])
    assert {"classe", "prazo_maximo_dias"} <= set(repo.swalis[0])


def test_toda_solicitacao_tem_id_e_espera(repo):
    assert all(r["solicitacao_id"] for r in repo.queue)
    assert all(isinstance(r["dias_em_fila"], int) for r in repo.queue)


def test_ids_de_solicitacao_sao_unicos(repo):
    ids = [r["solicitacao_id"] for r in repo.queue]
    assert len(set(ids)) == len(ids)


def test_oncologico_cid_bate_com_o_prefixo_do_cid(repo):
    for registro in repo.queue:
        esperado = (registro.get("cid_principal_norm") or "").startswith("C")
        assert bool(registro["oncologico_cid"]) is esperado, registro["solicitacao_id"]


def test_booleanos_foram_convertidos_e_nao_sao_a_string_sim(repo):
    for registro in repo.queue:
        assert registro["oncologico_cid"] in (True, False)


def test_prioridade_normalizada_nao_tem_acento_nem_caixa_alta(repo):
    valores = {r["prioridade_regulacao_norm"] for r in repo.queue}
    assert valores <= {"alta", "media", "baixa", None}


def test_todo_procedimento_da_fila_existe_no_catalogo(repo):
    catalogo = {p["procedimento_id"] for p in repo.procedures}
    assert {r["procedimento_id"] for r in repo.queue} <= catalogo


def test_data_de_entrada_esta_em_iso(repo):
    for registro in repo.queue:
        data = registro["data_entrada_fila"]
        assert data is None or (len(data) == 10 and data[4] == data[7] == "-")


def test_eventos_orfaos_continuam_no_dataset(repo):
    """A análise registrou 9 eventos apontando para solicitações fora da fila."""
    orfaos = [e for e in repo.events if e.get("solicitacao_na_fila") is False]
    assert len(orfaos) == 9
    assert all(repo.get_request(e["solicitacao_id"]) is None for e in orfaos)


def test_duplicatas_nao_foram_removidas(repo):
    assert repo.statistics()["repeated_patient_procedure_pairs"] == 22
