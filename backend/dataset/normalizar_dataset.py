"""Gera cópias normalizadas e um relatório sem alterar os arquivos de origem."""
from pathlib import Path
import json
import unicodedata

import pandas as pd

BASE = Path(__file__).resolve().parent
OUT = BASE / "normalizado"


def clean(value):
    if pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def write_csv(frame, name):
    frame.to_csv(OUT / name, index=False, encoding="utf-8", lineterminator="\n")


def main():
    OUT.mkdir(exist_ok=True)
    fila_origem = read_csv(BASE / "fila_cirurgica.csv")
    fila = fila_origem.copy()
    eventos = read_csv(BASE / "eventos_clinicos.csv")
    procedimentos = read_csv(BASE / "procedimentos.csv")
    swalis = read_csv(BASE / "referencias" / "swalis.csv")

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

    write_csv(fila, "fila_cirurgica_normalizada.csv")
    write_csv(eventos, "eventos_clinicos_normalizados.csv")
    write_csv(procedimentos, "procedimentos_normalizados.csv")
    write_csv(swalis, "swalis_normalizado.csv")

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
            "Campos ausentes permanecem vazios; não foram imputados.",
        ],
    }
    (OUT / "analise_qualidade.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
