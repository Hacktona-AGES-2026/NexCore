"""Testes de normalizar_dataset.py.

O end-to-end redireciona BASE/OUT do módulo para um tmp_path, então os CSVs
versionados em dataset/normalizado/ nunca são sobrescritos pela suíte.
"""
import json

import pytest

# Sem pandas, um erro de import aqui interromperia a coleta da suíte inteira e
# levaria embora também os testes do backend, que não dependem dele.
pytest.importorskip("pandas", reason="pandas: pip install -r dataset/requirements.txt")

import normalizar_dataset as nd  # noqa: E402  (depende do importorskip acima)


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


def test_inse_e_agregado_por_municipio_e_invertido_por_minmax():
    import pandas as pd

    reference = nd.build_socioeconomic_reference(pd.DataFrame([
        {"ano": "2021", "id_municipio": "0000001", "inse": "2.0"},
        {"ano": "2021", "id_municipio": "0000001", "inse": "4.0"},
        {"ano": "2021", "id_municipio": "0000002", "inse": "5.0"},
    ]))
    first = reference.set_index("id_municipio").loc["0000001"]
    second = reference.set_index("id_municipio").loc["0000002"]
    assert first.inse_medio == 3.0
    assert first.observacoes_inse == 2
    assert first.s_vulnerabilidade == 1.0
    assert second.s_vulnerabilidade == 0.0


def test_indicador_substituto_usa_ibge_e_fallback_explicito():
    import pandas as pd

    patients = pd.DataFrame([
        {"id_municipio": "0000001", "distancia_hospital_km": "75"},
        {"id_municipio": "9999999", "distancia_hospital_km": "0"},
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "4.0"},
    ])
    components = nd.calcular_componentes_s_substituto(patients, ibge)
    assert list(components.s_social) == [1.0, 0.5]
    assert list(components.s_geografico) == [0.5, 0.0]
    assert list(components.s_vulnerabilidade) == [0.9, 0.4]
    assert list(components.s_vulnerabilidade_imputada) == ["nao", "sim"]


def test_evfam_prevalece_sobre_ibge_e_usa_media_dos_itens_presentes():
    import pandas as pd

    patients = pd.DataFrame([
        {
            "id_municipio": "0000001",
            "distancia_hospital_km": "150",
            "evfam_dificuldade_financeira": "1",
            "evfam_ausencia_apoio_familiar": "0.5",
        }
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "4.0"},
    ])
    components = nd.calcular_componentes_s_substituto(patients, ibge)
    assert components.iloc[0].s_evfam == 0.75
    assert components.iloc[0].s_ibge == 1.0
    assert components.iloc[0].s_social == 0.75
    assert components.iloc[0].s_social_source == "evfam_br"
    assert components.iloc[0].s_vulnerabilidade == pytest.approx(0.8)


def test_distancia_e_limitada_e_ausencia_recebe_neutro():
    import pandas as pd

    patients = pd.DataFrame([
        {"id_municipio": "0000001", "distancia_hospital_km": "300"},
        {"id_municipio": "0000001", "distancia_hospital_km": ""},
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "4.0"},
    ])
    components = nd.calcular_componentes_s_substituto(patients, ibge)
    assert list(components.s_geografico) == [1.0, 0.5]
    assert list(components.s_distancia_imputada) == ["nao", "sim"]


def test_funcao_publica_retorna_s_entre_zero_e_um():
    import pandas as pd

    patients = pd.DataFrame([
        {"id_municipio": "0000001", "distancia_hospital_km": "1000"},
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "4.0"},
    ])
    result = nd.calcular_indicador_s_substituto(patients, ibge)
    assert result.name == "s_vulnerabilidade"
    assert result.between(0.0, 1.0).all()


def test_populacao_evfam_sintetica_e_deterministica_e_binaria():
    import pandas as pd

    patients = pd.DataFrame([
        {"solicitacao_id": "SOL-1", "id_municipio": "0000001", "idade": 30},
        {"solicitacao_id": "SOL-2", "id_municipio": "0000002", "idade": 80},
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "4.0"},
    ])
    first = nd.popular_evfam_sintetica(patients, ibge)
    second = nd.popular_evfam_sintetica(patients, ibge)
    columns = [
        "evfam_dificuldade_financeira",
        "evfam_uso_medicamentos_continuos",
        "evfam_sem_apoio_familiar",
        "evfam_vulnerabilidade_habitacional",
    ]
    assert first[columns].equals(second[columns])
    assert set(first[columns].stack()) <= {0, 1}
    assert set(first.evfam_dados_sinteticos) == {"sim"}


def test_populacao_evfam_preserva_coluna_existente():
    import pandas as pd

    patients = pd.DataFrame([
        {
            "solicitacao_id": "SOL-1",
            "id_municipio": "0000001",
            "evfam_dificuldade_financeira": 0,
        }
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "4.0"},
    ])
    result = nd.popular_evfam_sintetica(patients, ibge)
    assert result.iloc[0].evfam_dificuldade_financeira == 0


def test_probabilidade_evfam_aumenta_com_vulnerabilidade_inse():
    import pandas as pd

    patients = pd.DataFrame([
        {"solicitacao_id": f"V-{i}", "id_municipio": "0000001"}
        for i in range(1000)
    ] + [
        {"solicitacao_id": f"R-{i}", "id_municipio": "0000002"}
        for i in range(1000)
    ])
    ibge = pd.DataFrame([
        {"id_municipio": "0000001", "inse": "2.0"},
        {"id_municipio": "0000002", "inse": "8.0"},
    ])
    result = nd.popular_evfam_sintetica(patients, ibge)
    vulnerable = result.iloc[:1000].evfam_dificuldade_financeira.mean()
    affluent = result.iloc[1000:].evfam_dificuldade_financeira.mean()
    assert vulnerable > affluent + 0.5


def test_mudanca_na_origem_normaliza_recalcula_e_publica(
    mini_dataset, fabrica_fila, fabrica_evento, tmp_path
):
    from app.data.repository import Repository
    from app.data.ingestion import DatasetIngestion
    from app.realtime.dpss_live import ReactiveDpss

    swalis = [
        {"classe": cls, "descricao": cls, "prazo_maximo_dias": days, "exemplos": ""}
        for cls, days in (("A1", 15), ("A2", 21), ("B", 60), ("C", 180), ("D", 360))
    ]
    base = mini_dataset([fabrica_fila()], swalis=swalis)
    output = tmp_path / "normalizado-live"
    nd.main(base=base, output=output)
    repository = Repository(output, "2026-10-23")
    live = ReactiveDpss(
        repository,
        "hsl",
        source_directory=base,
        normalizer=nd.main,
    )
    subscription = live.subscribe()
    before = subscription.get(0)
    assert before["data"][0]["swalis_class"] == "D"

    ingestion = DatasetIngestion(base, live)
    accepted = ingestion.create_event(
        fabrica_evento(
            evento_id="EVT-LIVE",
            tipo_evento="exame_imagem",
            resultado="progressao",
        )
    )
    assert accepted["accepted"] is True
    assert accepted["recalculated"] is True
    after = subscription.get(0)
    assert after["reason"] == "source_normalized"
    assert after["data"][0]["swalis_class"] == "A2"
    assert len(repository.events) == 1

    created = ingestion.create_request(
        {
            "solicitacao_id": "SOL-LIVE-2",
            "paciente_id": "PAC-LIVE-2",
            "nome_paciente": "Paciente nova",
            "municipio": "Porto Alegre",
            "uf": "RS",
            "distancia_hospital_km": 30,
            "procedimento_id": "PROC001",
            "procedimento": "Procedimento Teste",
            "especialidade": "Cirurgia Geral",
            "cid_principal": "K40.9",
            "data_entrada_fila": "2026-01-01",
            "intensidade_dor_eva": 2,
            "limitacao_funcional": "nenhuma",
            "evfam_dificuldade_financeira": 1,
            "evfam_uso_medicamentos_continuos": 0,
            "evfam_sem_apoio_familiar": 1,
            "evfam_vulnerabilidade_habitacional": 0,
        }
    )
    assert created["queue_total"] == 2
    new_record = repository.get_request("SOL-LIVE-2")
    assert new_record["s_social_source"] == "evfam_br"
    assert new_record["evfam_dados_sinteticos"] == "nao"
    assert new_record["s_vulnerabilidade"] == pytest.approx(
        0.8 * 0.5 + 0.2 * (30 / 150)
    )


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
            "socioeconomic": ler("socioeconomic_normalized.csv"),
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
    assert set(r["fila"].id_municipio) == {"4314902"}
    assert set(r["fila"].s_vulnerabilidade_imputada) == {"nao"}


def test_municipio_sem_codigo_ainda_recebe_evfam_sintetica(executar, fabrica_fila):
    r = executar([fabrica_fila(municipio="Cidade Inexistente")])
    row = r["fila"].iloc[0]
    assert row.s_social_source == "evfam_br"
    assert row.evfam_dados_sinteticos == "sim"
    assert row.s_vulnerabilidade_imputada == "nao"
    assert r["resumo"]["solicitacoes_socioeconomico_fallback_0_5"] == 0


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
