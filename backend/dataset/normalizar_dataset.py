"""Gera cópias normalizadas e um relatório sem alterar os arquivos de origem."""
from pathlib import Path
import hashlib
import json
import unicodedata

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
OUT = BASE / "normalizado"

EVFAM_FIELDS = {
    "dificuldade_financeira": (
        "evfam_dificuldade_financeira", "dificuldade_financeira",
    ),
    "uso_continuo_medicamentos": (
        "evfam_uso_medicamentos_continuos",
        "evfam_uso_continuo_medicamentos",
        "uso_continuo_medicamentos",
    ),
    "ausencia_apoio_familiar": (
        "evfam_sem_apoio_familiar",
        "evfam_ausencia_apoio_familiar",
        "ausencia_apoio_familiar",
    ),
    "vulnerabilidade_habitacional": (
        "evfam_vulnerabilidade_habitacional", "vulnerabilidade_habitacional",
    ),
}
SOCIAL_WEIGHT = 0.8
GEOGRAPHIC_WEIGHT = 0.2
DEFAULT_DISTANCE_CEILING_KM = 150.0
NEUTRAL_FALLBACK = 0.5
SYNTHETIC_EVFAM_SEED = "nexcore-evfam-homologacao-v1"
SYNTHETIC_EVFAM_VERSION = "correlated-inse-v1"


def clean(value):
    if pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def write_csv(frame, name, output=None):
    output = OUT if output is None else Path(output)
    target = output / name
    temporary = target.with_suffix(target.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n")
    temporary.replace(target)


def build_socioeconomic_reference(ibge):
    """Mean INSE by municipality, inverted with global min-max scaling."""
    required = {"id_municipio", "inse"}
    missing = required - set(ibge.columns)
    if missing:
        raise ValueError(
            "IBGE.csv sem colunas obrigatorias: " + ", ".join(sorted(missing))
        )

    rows = ibge.copy()
    rows["id_municipio"] = (
        rows["id_municipio"].map(clean).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    )
    rows["inse"] = pd.to_numeric(
        rows["inse"].map(clean).str.replace(",", ".", regex=False), errors="coerce"
    )
    valid = rows.dropna(subset=["inse"])
    valid = valid[valid.id_municipio.str.fullmatch(r"\d{7}", na=False)]
    if valid.empty:
        raise ValueError("IBGE.csv nao possui valores validos de id_municipio e inse")

    grouped = valid.groupby("id_municipio", as_index=False).agg(
        inse_medio=("inse", "mean"),
        observacoes_inse=("inse", "size"),
    )
    minimum = grouped.inse_medio.min()
    maximum = grouped.inse_medio.max()
    if pd.isna(minimum) or pd.isna(maximum) or maximum <= minimum:
        raise ValueError("INSE municipal nao possui variacao para normalizacao min-max")
    grouped["s_vulnerabilidade"] = (
        (maximum - grouped.inse_medio) / (maximum - minimum)
    ).clip(0.0, 1.0)
    years = sorted({value for value in valid.get("ano", pd.Series(dtype=str)).map(clean) if value})
    grouped["source"] = "IBGE.csv"
    grouped["source_year"] = ";".join(years)
    grouped["source_version"] = "INSE-" + ("-".join(years) if years else "sem-ano")
    grouped["weight_method"] = "mean_by_municipality_then_inverted_global_minmax"
    return grouped


def attach_municipality_id(queue, municipalities):
    """Attach the seven-digit IBGE id through a validated municipality merge."""
    mapping = municipalities.copy()
    mapping["id_municipio"] = mapping["id_municipio"].map(clean).str.zfill(7)
    if mapping.duplicated(["municipio_norm", "uf"]).any():
        raise ValueError("mapeamento municipal possui municipio_norm + uf duplicado")
    return queue.merge(
        mapping[["municipio_norm", "uf", "id_municipio"]],
        on=["municipio_norm", "uf"],
        how="left",
        validate="many_to_one",
    )


def _stable_uniform(request_id, field, seed=SYNTHETIC_EVFAM_SEED):
    """Return a reproducible pseudo-random value without global RNG state."""
    payload = f"{seed}|{request_id}|{field}".encode("utf-8")
    integer = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return integer / 2**64


def popular_evfam_sintetica(
    df_pacientes,
    df_ibge,
    seed=SYNTHETIC_EVFAM_SEED,
    referencia_ibge=None,
):
    """Fill missing EVFAM columns/cells for synthetic homologation only.

    Existing canonical columns or compatible aliases are preserved. Generated
    binary values are deterministic per request and positively correlated with
    the municipal vulnerability derived from INSE.
    """
    if "id_municipio" not in df_pacientes:
        raise ValueError("df_pacientes deve conter id_municipio")
    result = df_pacientes.copy()
    reference = (
        referencia_ibge.copy()
        if referencia_ibge is not None
        else build_socioeconomic_reference(df_ibge)
    )
    vulnerability_by_city = reference.set_index("id_municipio")[
        "s_vulnerabilidade"
    ]
    municipality = (
        result.id_municipio.map(clean)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(7)
    )
    territorial = municipality.map(vulnerability_by_city).fillna(NEUTRAL_FALLBACK)
    age = pd.to_numeric(
        result.get("idade", pd.Series(index=result.index)), errors="coerce"
    )
    diabetic_raw = result.get(
        "flag_diabetico_norm",
        result.get("flag_diabetico", pd.Series("", index=result.index)),
    )
    diabetic = diabetic_raw.map(clean).str.casefold().isin({"sim", "true", "1"})

    probabilities = {
        "evfam_dificuldade_financeira": 0.08 + 0.70 * territorial,
        "evfam_uso_medicamentos_continuos": (
            0.10 + 0.40 * territorial + 0.15 * diabetic + 0.10 * age.ge(65)
        ),
        "evfam_sem_apoio_familiar": (
            0.06 + 0.35 * territorial + 0.12 * age.ge(75)
        ),
        "evfam_vulnerabilidade_habitacional": 0.04 + 0.65 * territorial,
    }
    canonical_aliases = {
        aliases[0]: aliases for aliases in EVFAM_FIELDS.values()
    }
    generated_any = pd.Series(False, index=result.index)
    identifiers = result.get(
        "solicitacao_id", pd.Series(result.index.astype(str), index=result.index)
    ).map(clean)
    for canonical, probability in probabilities.items():
        source_column = next(
            (name for name in canonical_aliases[canonical] if name in result),
            None,
        )
        existing = (
            _normalized_evfam(result[source_column])
            if source_column is not None
            else pd.Series(np.nan, index=result.index)
        )
        thresholds = probability.clip(0.01, 0.95)
        draws = pd.Series(
            [
                _stable_uniform(request_id, canonical, seed)
                for request_id in identifiers
            ],
            index=result.index,
        )
        generated = draws.lt(thresholds).astype(int)
        missing = existing.isna()
        result[canonical] = existing.where(~missing, generated)
        generated_any |= missing

    result["evfam_dados_sinteticos"] = np.where(generated_any, "sim", "nao")
    result["evfam_sintese_versao"] = np.where(
        generated_any, SYNTHETIC_EVFAM_VERSION, ""
    )
    return result


def _normalized_evfam(series):
    """Parse a pre-normalized 0..1 EVFAM item without inventing invalid values."""
    text = series.map(clean).str.casefold()
    categorical = text.map(
        {
            "sim": 1.0,
            "true": 1.0,
            "1": 1.0,
            "nao": 0.0,
            "não": 0.0,
            "false": 0.0,
            "0": 0.0,
        }
    )
    numeric = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
    values = categorical.combine_first(numeric)
    return values.where(values.between(0.0, 1.0))


def calcular_componentes_s_substituto(
    df_pacientes,
    df_ibge,
    distancia_teto_km=DEFAULT_DISTANCE_CEILING_KM,
):
    """Calculate EVFAM/INSE social layer, distance layer and final S evidence."""
    try:
        distance_ceiling = float(distancia_teto_km)
    except (TypeError, ValueError):
        raise ValueError("distancia_teto_km deve ser um numero positivo")
    if not np.isfinite(distance_ceiling) or distance_ceiling <= 0:
        raise ValueError("distancia_teto_km deve ser um numero positivo")
    if "id_municipio" not in df_pacientes:
        raise ValueError("df_pacientes deve conter id_municipio")

    reference = build_socioeconomic_reference(df_ibge)
    lookup = df_pacientes[["id_municipio"]].copy()
    lookup["id_municipio"] = (
        lookup.id_municipio.map(clean).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    )
    lookup["_row_order"] = np.arange(len(lookup))
    merged = lookup.merge(
        reference[["id_municipio", "inse_medio", "s_vulnerabilidade"]],
        on="id_municipio",
        how="left",
        validate="many_to_one",
    ).sort_values("_row_order")

    result = pd.DataFrame(index=df_pacientes.index)
    result["inse_medio"] = merged.inse_medio.to_numpy()
    result["s_ibge"] = merged.s_vulnerabilidade.to_numpy()

    evfam_columns = {
        item: next(
            (column for column in aliases if column in df_pacientes),
            None,
        )
        for item, aliases in EVFAM_FIELDS.items()
    }
    evfam_columns = {
        item: column for item, column in evfam_columns.items() if column is not None
    }
    if evfam_columns:
        normalized = pd.DataFrame(
            {
                item: _normalized_evfam(df_pacientes[column])
                for item, column in evfam_columns.items()
            },
            index=df_pacientes.index,
        )
        result["s_evfam"] = normalized.mean(axis=1, skipna=True)
    else:
        result["s_evfam"] = np.nan

    result["s_social"] = (
        result.s_evfam.combine_first(result.s_ibge).fillna(NEUTRAL_FALLBACK)
    ).clip(0.0, 1.0)
    result["s_social_source"] = np.select(
        [result.s_evfam.notna(), result.s_ibge.notna()],
        ["evfam_br", "ibge_inse"],
        default="fallback_0.5",
    )
    result["s_vulnerabilidade_imputada"] = np.where(
        result.s_social_source == "fallback_0.5", "sim", "nao"
    )
    result["s_evfam_colunas_utilizadas"] = ";".join(evfam_columns.values())

    if "distancia_hospital_km" in df_pacientes:
        distance = pd.to_numeric(
            df_pacientes.distancia_hospital_km.map(clean).str.replace(",", ".", regex=False),
            errors="coerce",
        )
    else:
        distance = pd.Series(np.nan, index=df_pacientes.index)
    invalid_distance = distance.isna() | (distance < 0)
    geographic = (distance / distance_ceiling).clip(0.0, 1.0)
    result["s_geografico"] = geographic.mask(invalid_distance, NEUTRAL_FALLBACK)
    result["s_distancia_imputada"] = np.where(invalid_distance, "sim", "nao")
    result["s_distancia_teto_km"] = distance_ceiling
    result["s_vulnerabilidade"] = (
        SOCIAL_WEIGHT * result.s_social
        + GEOGRAPHIC_WEIGHT * result.s_geografico
    ).clip(0.0, 1.0)
    return result


def calcular_indicador_s_substituto(
    df_pacientes,
    df_ibge,
    distancia_teto_km=DEFAULT_DISTANCE_CEILING_KM,
):
    """Return the hybrid EVFAM/INSE + distance indicator used by DPSS."""
    return calcular_componentes_s_substituto(
        df_pacientes,
        df_ibge,
        distancia_teto_km=distancia_teto_km,
    )["s_vulnerabilidade"]


def main(base=None, output=None):
    base = BASE if base is None else Path(base)
    output = OUT if output is None else Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fila_origem = read_csv(base / "fila_cirurgica.csv")
    fila = fila_origem.copy()
    eventos = read_csv(base / "eventos_clinicos.csv")
    procedimentos = read_csv(base / "procedimentos.csv")
    swalis = read_csv(base / "referencias" / "swalis.csv")
    ibge = read_csv(base / "IBGE.csv")
    municipios_ibge = read_csv(base / "referencias" / "municipios_ibge.csv")

    for frame in (fila, eventos, procedimentos, swalis):
        for column in frame.columns:
            frame[column] = frame[column].map(clean)

    fila["cid_principal_norm"] = fila.cid_principal.str.upper().str.replace(".", "", regex=False).str.replace(" ", "", regex=False)
    fila["cid_secundario_norm"] = fila.cid_secundario.str.upper().str.replace(".", "", regex=False).str.replace(" ", "", regex=False)
    fila["oncologico_cid"] = fila.cid_principal_norm.str.startswith("C").map({True: "sim", False: "nao"})
    fila["municipio_norm"] = fila.municipio.str.casefold().str.strip().str.title()
    fila["prioridade_regulacao_norm"] = fila.prioridade_regulacao.str.casefold().str.strip()
    fila["prioridade_regulacao_norm"] = fila.prioridade_regulacao_norm.replace(
        {"média": "media", "m�dia": "media", "m?dia": "media"}
    )
    for column in (
        "flag_oncologico", "flag_diabetico", "flag_piora_clinica",
        "avaliacao_pre_anestesica", "exames_pre_op_validos",
        "limitacao_funcional", "sexo",
    ):
        fila[f"{column}_norm"] = fila[column].str.casefold().str.strip()
    for column in ("data_entrada_fila", "data_ultima_revisao_prioridade", "data_hba1c_ultima"):
        fila[column] = pd.to_datetime(fila[column], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")

    eventos["data_evento"] = pd.to_datetime(eventos.data_evento, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    eventos["tipo_evento_norm"] = eventos.tipo_evento.str.casefold().str.strip()
    eventos["resultado_norm"] = eventos.resultado.str.casefold().str.strip()
    eventos["duplicata_conteudo"] = eventos.duplicated(
        subset=[column for column in eventos.columns if column != "evento_id"], keep="first"
    ).map({True: "sim", False: "nao"})
    fila_ids = set(fila.solicitacao_id)
    eventos["solicitacao_na_fila"] = eventos.solicitacao_id.isin(fila_ids).map({True: "sim", False: "nao"})
    paciente_por_sol = fila.set_index("solicitacao_id").paciente_id.to_dict()
    def conferir_paciente(row):
        paciente = paciente_por_sol.get(row.solicitacao_id)
        if paciente is None:
            return "sem_solicitacao_ativa"
        return "sim" if paciente == row.paciente_id else "nao"
    eventos["paciente_coincide_fila"] = eventos.apply(conferir_paciente, axis=1)

    for column in ("porte", "necessita_uti", "especialidade"):
        procedimentos[f"{column}_norm"] = procedimentos[column].str.casefold().str.strip()
    swalis["classe_norm"] = swalis.classe.str.upper().str.strip()

    socioeconomic = build_socioeconomic_reference(ibge)
    fila = attach_municipality_id(fila, municipios_ibge)
    fila = popular_evfam_sintetica(
        fila,
        ibge,
        referencia_ibge=socioeconomic,
    )
    social_components = calcular_componentes_s_substituto(fila, ibge)
    for column in social_components:
        fila[column] = social_components[column]

    write_csv(fila, "fila_cirurgica_normalizada.csv", output)
    write_csv(eventos, "eventos_clinicos_normalizados.csv", output)
    write_csv(procedimentos, "procedimentos_normalizados.csv", output)
    write_csv(swalis, "swalis_normalizado.csv", output)
    write_csv(socioeconomic, "socioeconomic_normalized.csv", output)

    cid_norm = fila.cid_principal_norm
    vazio = {column: int((fila_origem[column] == "").sum()) for column in fila_origem.columns if (fila_origem[column] == "").any()}
    resumo = {
        "data_referencia": "2026-10-23",
        "fila_linhas": len(fila),
        "eventos_linhas": len(eventos),
        "procedimentos_linhas": len(procedimentos),
        "solicitacao_id_duplicado": int(fila.solicitacao_id.duplicated().sum()),
        "eventos_sem_solicitacao_ativa": int((eventos.solicitacao_na_fila == "nao").sum()),
        "eventos_duplicados_por_conteudo": int((eventos.duplicata_conteudo == "sim").sum()),
        "paciente_evento_divergente_em_solicitacao_ativa": int((eventos.paciente_coincide_fila == "nao").sum()),
        "solicitacoes_paciente_procedimento_repetidas": int(fila.duplicated(["paciente_id", "procedimento_id"]).sum()),
        "ids_procedimento_sem_catalogo": int((~fila.procedimento_id.isin(set(procedimentos.procedimento_id))).sum()),
        "oncologicos_por_cid": int(cid_norm.str.startswith("C").sum()),
        "divergencia_flag_oncologica_vs_cid": int(((fila.flag_oncologico.str.casefold() == "sim") != cid_norm.str.startswith("C")).sum()),
        "municipios_inse": len(socioeconomic),
        "inse_municipal_min": float(socioeconomic.inse_medio.min()),
        "inse_municipal_max": float(socioeconomic.inse_medio.max()),
        "solicitacoes_socioeconomico_fallback_0_5": int((fila.s_vulnerabilidade_imputada == "sim").sum()),
        "solicitacoes_s_por_evfam": int((fila.s_social_source == "evfam_br").sum()),
        "solicitacoes_s_por_ibge": int((fila.s_social_source == "ibge_inse").sum()),
        "solicitacoes_evfam_sintetica": int((fila.evfam_dados_sinteticos == "sim").sum()),
        "evfam_sintetica_versao": SYNTHETIC_EVFAM_VERSION,
        "prevalencia_evfam_sintetica": {
            column: float(pd.to_numeric(fila[column], errors="coerce").mean())
            for column in (
                "evfam_dificuldade_financeira",
                "evfam_uso_medicamentos_continuos",
                "evfam_sem_apoio_familiar",
                "evfam_vulnerabilidade_habitacional",
            )
        },
        "solicitacoes_distancia_fallback_0_5": int((fila.s_distancia_imputada == "sim").sum()),
        "valores_prioridade_manual_origem": fila_origem.prioridade_regulacao.value_counts().to_dict(),
        "campos_vazios_na_fila_origem": vazio,
        "preparo_pre_operatorio": "Campos opcionais mantidos; fora do escopo avaliativo do desafio.",
        "regras": [
            "Arquivos de origem preservados; nenhuma linha removida.",
            "Espaços periféricos removidos e Unicode normalizado para NFC.",
            "Colunas *_norm adicionadas para comparação e agrupamento.",
            "CID comparável sem ponto em cid_principal_norm/cid_secundario_norm.",
            "oncologico_cid é derivado do CID, não da flag manual.",
            "Eventos duplicados, órfãos e com paciente divergente são sinalizados e mantidos.",
            "Campos clínicos ausentes permanecem vazios; apenas S possui fallback explícito 0.5.",
            "Camada social usa média EVFAM-BR quando disponível, senão INSE municipal invertido.",
            "Na base sintética de homologação, colunas EVFAM ausentes são geradas de forma determinística e correlacionada ao INSE.",
            "Dados EVFAM existentes nunca são sobrescritos pela rotina sintética.",
            "Camada social sem EVFAM-BR e sem INSE recebe fallback explícito 0.5.",
            "S final combina 80% da camada social e 20% da distância normalizada por 150 km.",
            "Distância ausente ou negativa recebe fator geográfico neutro 0.5 e flag explícita.",
        ],
    }
    quality = output / "analise_qualidade.json"
    quality_temporary = quality.with_suffix(quality.suffix + ".tmp")
    quality_temporary.write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    quality_temporary.replace(quality)


if __name__ == "__main__":
    main()
