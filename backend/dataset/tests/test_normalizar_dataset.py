"""Testes de normalizar_dataset.py.

O end-to-end redireciona BASE/OUT do módulo para um tmp_path, então os CSVs
versionados em dataset/normalizado/ nunca são sobrescritos pela suíte.
"""
import json

import pytest

import normalizar_dataset as nd


# --- helpers puros --------------------------------------------------------

@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("  texto  ", "texto"),
        ("", ""),
        ("ja limpo", "ja limpo"),
        ("\tcom tab\n", "com tab"),
    ],
)
def test_clean_remove_espacos_perifericos(entrada, esperado):
    assert nd.clean(entrada) == esperado


def test_clean_normaliza_para_nfc():
    decomposto = "Média"          # e + acento combinante
    composto = "Média"             # e-acute único
    assert decomposto != composto
    assert nd.clean(decomposto) == composto


def test_clean_converte_ausente_em_string_vazia():
    import pandas as pd

    assert nd.clean(pd.NA) == ""
    assert nd.clean(float("nan")) == ""


def test_clean_preserva_espacos_internos():
    assert nd.clean("  Cirurgia   Geral  ") == "Cirurgia   Geral"


# --- execução completa ----------------------------------------------------

@pytest.fixture()
def executar(tmp_path, monkeypatch, mini_dataset):
    def rodar(linhas_fila, linhas_eventos=()):
        base = mini_dataset(linhas_fila, linhas_eventos)
        saida = base / "normalizado"
        monkeypatch.setattr(nd, "BASE", base)
        monkeypatch.setattr(nd, "OUT", saida)
        nd.main()
        import pandas as pd

        ler = lambda nome: pd.read_csv(  # noqa: E731
            saida / nome, dtype=str, keep_default_na=False
        )
        return {
            "dir": saida,
            "fila": ler("fila_cirurgica_normalizada.csv"),
            "eventos": ler("eventos_clinicos_normalizados.csv"),
            "resumo": json.loads((saida / "analise_qualidade.json").read_text("utf-8")),
        }

    return rodar


def test_cid_fica_comparavel_sem_ponto(executar, fabrica_fila):
    r = executar([
        fabrica_fila(solicitacao_id="SOL-1", cid_principal="K40.9"),
        fabrica_fila(solicitacao_id="SOL-2", cid_principal="k409"),
    ])
    assert list(r["fila"].cid_principal_norm) == ["K409", "K409"]
    # a coluna de origem permanece intacta
    assert list(r["fila"].cid_principal) == ["K40.9", "k409"]


def test_oncologico_vem_do_cid_e_nao_da_flag(executar, fabrica_fila):
    r = executar([
        fabrica_fila(solicitacao_id="SOL-1", cid_principal="C50.4", flag_oncologico="nao"),
        fabrica_fila(solicitacao_id="SOL-2", cid_principal="K40.9", flag_oncologico="sim"),
    ])
    assert list(r["fila"].oncologico_cid) == ["sim", "nao"]
    assert r["resumo"]["oncologicos_por_cid"] == 1
    assert r["resumo"]["divergencia_flag_oncologica_vs_cid"] == 2


def test_prioridade_acentuada_e_caixa_viram_media(executar, fabrica_fila):
    r = executar([
        fabrica_fila(solicitacao_id="SOL-1", prioridade_regulacao="Média"),
        fabrica_fila(solicitacao_id="SOL-2", prioridade_regulacao="MEDIA"),
        fabrica_fila(solicitacao_id="SOL-3", prioridade_regulacao=" Alta "),
        fabrica_fila(solicitacao_id="SOL-4", prioridade_regulacao=""),
    ])
    assert list(r["fila"].prioridade_regulacao_norm) == ["media", "media", "alta", ""]


def test_municipio_com_grafia_inconsistente_converge(executar, fabrica_fila):
    r = executar([
        fabrica_fila(solicitacao_id="SOL-1", municipio="PORTO ALEGRE"),
        fabrica_fila(solicitacao_id="SOL-2", municipio="porto alegre"),
        fabrica_fila(solicitacao_id="SOL-3", municipio=" Porto Alegre "),
    ])
    assert set(r["fila"].municipio_norm) == {"Porto Alegre"}


def test_datas_saem_em_iso_e_invalida_vira_vazio(executar, fabrica_fila):
    r = executar([
        fabrica_fila(solicitacao_id="SOL-1", data_entrada_fila="2025-01-02"),
        fabrica_fila(solicitacao_id="SOL-2", data_entrada_fila="sem data"),
    ])
    assert list(r["fila"].data_entrada_fila) == ["2025-01-02", ""]


def test_campo_vazio_nao_e_imputado(executar, fabrica_fila):
    r = executar([fabrica_fila(solicitacao_id="SOL-1", asa="", intensidade_dor_eva="")])
    linha = r["fila"].iloc[0]
    assert linha.asa == ""
    assert linha.intensidade_dor_eva == ""


def test_evento_duplicado_e_sinalizado_sem_ser_removido(executar, fabrica_fila, fabrica_evento):
    r = executar(
        [fabrica_fila(solicitacao_id="SOL-1")],
        [
            fabrica_evento(evento_id="EVT-1", solicitacao_id="SOL-1"),
            fabrica_evento(evento_id="EVT-2", solicitacao_id="SOL-1"),
        ],
    )
    assert len(r["eventos"]) == 2
    assert list(r["eventos"].duplicata_conteudo) == ["nao", "sim"]
    assert r["resumo"]["eventos_duplicados_por_conteudo"] == 1


def test_evento_orfao_e_sinalizado_sem_ser_removido(executar, fabrica_fila, fabrica_evento):
    r = executar(
        [fabrica_fila(solicitacao_id="SOL-1")],
        [
            fabrica_evento(evento_id="EVT-1", solicitacao_id="SOL-1"),
            fabrica_evento(evento_id="EVT-2", solicitacao_id="SOL-FORA"),
        ],
    )
    assert len(r["eventos"]) == 2
    assert list(r["eventos"].solicitacao_na_fila) == ["sim", "nao"]
    assert list(r["eventos"].paciente_coincide_fila) == ["sim", "sem_solicitacao_ativa"]
    assert r["resumo"]["eventos_sem_solicitacao_ativa"] == 1


def test_paciente_divergente_em_solicitacao_ativa(executar, fabrica_fila, fabrica_evento):
    r = executar(
        [fabrica_fila(solicitacao_id="SOL-1", paciente_id="PAC-1")],
        [fabrica_evento(evento_id="EVT-1", solicitacao_id="SOL-1", paciente_id="PAC-OUTRO")],
    )
    assert list(r["eventos"].paciente_coincide_fila) == ["nao"]
    assert r["resumo"]["paciente_evento_divergente_em_solicitacao_ativa"] == 1


def test_par_paciente_procedimento_repetido_e_contado(executar, fabrica_fila):
    r = executar([
        fabrica_fila(solicitacao_id="SOL-1", paciente_id="PAC-1", procedimento_id="PROC001"),
        fabrica_fila(solicitacao_id="SOL-2", paciente_id="PAC-1", procedimento_id="PROC001"),
        fabrica_fila(solicitacao_id="SOL-3", paciente_id="PAC-2", procedimento_id="PROC001"),
    ])
    assert len(r["fila"]) == 3
    assert r["resumo"]["solicitacoes_paciente_procedimento_repetidas"] == 1


def test_nenhuma_linha_nem_coluna_de_origem_e_perdida(executar, fabrica_fila, colunas_fila):
    r = executar([fabrica_fila(solicitacao_id=f"SOL-{i}") for i in range(5)])
    assert len(r["fila"]) == 5
    assert set(colunas_fila).issubset(set(r["fila"].columns))


def test_resumo_registra_regras_e_data_de_referencia(executar, fabrica_fila):
    r = executar([fabrica_fila(solicitacao_id="SOL-1")])
    assert r["resumo"]["data_referencia"] == "2026-10-23"
    assert any("oncologico_cid" in regra for regra in r["resumo"]["regras"])


def test_execucao_e_idempotente(executar, fabrica_fila):
    linhas = [fabrica_fila(solicitacao_id="SOL-1", municipio="PORTO ALEGRE")]
    primeira = executar(linhas)
    conteudo = (primeira["dir"] / "fila_cirurgica_normalizada.csv").read_text("utf-8")
    nd.main()
    assert (primeira["dir"] / "fila_cirurgica_normalizada.csv").read_text("utf-8") == conteudo
