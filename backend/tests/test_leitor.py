"""Testes da conversão de tipos na leitura dos CSVs."""
import pytest

from app.data import reader


@pytest.mark.parametrize(
    "entrada, esperado",
    [("7", 7), (" 42 ", 42), ("-3", -3), ("", None), (None, None),
     ("abc", None), ("3.9", None)],
)
def test_para_inteiro(entrada, esperado):
    assert reader.to_int(entrada) == esperado


@pytest.mark.parametrize(
    "entrada, esperado",
    [("7.4", 7.4), ("7,4", 7.4), (" 8 ", 8.0), ("", None), (None, None), ("x", None)],
)
def test_para_decimal(entrada, esperado):
    assert reader.to_float(entrada) == esperado


@pytest.mark.parametrize(
    "entrada, esperado",
    [("2026-10-23", "2026-10-23"), ("2026-10-23 00:00:00", "2026-10-23"),
     ("", None), (None, None), ("23/10/2026", None), ("2026-13-45", None)],
)
def test_para_data(entrada, esperado):
    resultado = reader.to_date(entrada)
    assert (resultado.isoformat() if resultado else None) == esperado


@pytest.mark.parametrize(
    "entrada, esperado",
    [("sim", True), ("SIM", True), ("true", True), ("1", True),
     ("nao", False), ("não", False), ("false", False), ("0", False),
     ("", None), (None, None), ("sem_solicitacao_ativa", None)],
)
def test_para_booleano(entrada, esperado):
    assert reader.to_bool(entrada) is esperado


@pytest.mark.parametrize(
    "entrada, esperado",
    [("Média", "media"), ("SÃO LEOPOLDO", "sao leopoldo"),
     ("Coloproctologia", "coloproctologia"), ("", ""), (None, "")],
)
def test_sem_acento_tambem_baixa_a_caixa(entrada, esperado):
    assert reader.strip_accents(entrada) == esperado


def test_campo_vazio_vira_none_e_nao_string_vazia(tmp_path):
    arquivo = tmp_path / "t.csv"
    arquivo.write_text("solicitacao_id,asa,observacoes\nSOL-1,,\n", encoding="utf-8")
    linha = reader.read_csv(arquivo)[0]
    assert linha["asa"] is None
    assert linha["observacoes"] is None


def test_tipos_sao_convertidos_por_nome_de_coluna(tmp_path):
    arquivo = tmp_path / "t.csv"
    arquivo.write_text(
        "solicitacao_id,idade,dias_em_fila,hba1c_ultima,data_entrada_fila,oncologico_cid\n"
        "SOL-1,70,607,8.4,2025-02-23,sim\n",
        encoding="utf-8",
    )
    linha = reader.read_csv(arquivo)[0]
    assert linha["idade"] == 70
    assert linha["dias_em_fila"] == 607
    assert linha["hba1c_ultima"] == 8.4
    assert linha["data_entrada_fila"] == "2025-02-23"
    assert linha["oncologico_cid"] is True
    assert linha["solicitacao_id"] == "SOL-1"


def test_valor_numerico_invalido_nao_derruba_a_leitura(tmp_path):
    arquivo = tmp_path / "t.csv"
    arquivo.write_text("evento_id,valor_numerico\nEVT-1,indefinido\n", encoding="utf-8")
    assert reader.read_csv(arquivo)[0]["valor_numerico"] is None


def test_arquivo_ausente_tem_erro_explicito(tmp_path):
    with pytest.raises(reader.DatasetUnavailable, match="arquivo nao encontrado"):
        reader.read_csv(tmp_path / "nao-existe.csv")


def test_diretorio_ausente_sugere_o_comando(tmp_path):
    with pytest.raises(reader.DatasetUnavailable, match="normalizar_dataset.py"):
        reader.load(tmp_path / "nao-existe")


def test_carregar_le_as_quatro_tabelas(dataset_sintetico):
    destino = dataset_sintetico(
        fila=[{"solicitacao_id": "SOL-1"}],
        eventos=[{"evento_id": "EVT-1"}],
        procedimentos=[{"procedimento_id": "PROC001"}],
        swalis=[{"classe": "A1"}],
    )
    tabelas = reader.load(destino)
    assert set(tabelas) == {"fila", "eventos", "procedimentos", "swalis"}
    assert len(tabelas["fila"]) == 1
