"""Cálculo de prioridade do Neco (versão de referência, só biblioteca padrão).

É o mesmo cálculo que o backend simulado do front usa e que está descrito em
docs/CONTRATO_BACKEND.md (seção 4). O backend pode importar este módulo.
"""
import csv
import datetime as dt
import os

REF = dt.date(2026, 10, 23)
PRAZO = {"A1": 15, "A2": 21, "B": 60, "C": 180, "D": 360}
RANK = {"A1": 5, "A2": 4, "B": 3, "C": 2, "D": 1}
ROTULO = {"A1": "Muito urgente", "A2": "Urgente", "B": "Prioritário", "C": "Moderado", "D": "Eletivo"}
PONTOS_CLASSE = {"A1": 40, "A2": 34, "B": 22, "C": 12, "D": 4}
PONTOS_LIMITACAO = {"grave": 4, "moderada": 2.5, "leve": 1}


def _num(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def carregar(pasta):
    """Lê fila e eventos normalizados. Ignora eventos duplicados."""
    with open(os.path.join(pasta, "fila_cirurgica_normalizada.csv"), encoding="utf-8") as f:
        fila = list(csv.DictReader(f))
    with open(os.path.join(pasta, "eventos_clinicos_normalizados.csv"), encoding="utf-8") as f:
        eventos = [e for e in csv.DictReader(f) if e["duplicata_conteudo"] != "sim"]
    por_solicitacao = {}
    for e in eventos:
        por_solicitacao.setdefault(e["solicitacao_id"], []).append(e)
    for lista in por_solicitacao.values():
        lista.sort(key=lambda e: e["data_evento"])
    return fila, eventos, por_solicitacao


def calcular(f, eventos):
    """Classe, fatores e índice de uma solicitação."""
    onco = f["oncologico_cid"] == "sim"
    cid = f["cid_principal_norm"]
    biopsia = any(e["tipo_evento_norm"] == "biopsia" and e["resultado_norm"] == "positivo" for e in eventos)
    progressao = any(e["tipo_evento_norm"] == "exame_imagem" and e["resultado_norm"] == "progressao" for e in eventos)
    recentes = [e for e in eventos if (REF - dt.date.fromisoformat(e["data_evento"])).days <= 180]
    ps = [e for e in recentes if e["tipo_evento_norm"] in ("pronto_socorro", "internacao")]
    piora = [e for e in recentes if e["resultado_norm"] in ("piora", "relata_piora")]
    dor = _num(f["intensidade_dor_eva"])
    lim = f["limitacao_funcional_norm"]
    incerto = "D37" <= cid[:3] <= "D48" or cid.startswith("R91")

    if onco and (progressao or ps):
        classe, motivo = "A1", f"neoplasia maligna (CID {f['cid_principal']}) com piora recente"
    elif onco:
        classe, motivo = "A2", f"neoplasia maligna (CID {f['cid_principal']})"
    elif biopsia:
        classe, motivo = "A2", f"biópsia positiva com CID {f['cid_principal']} ainda não maligno"
    elif incerto:
        classe, motivo = "B", f"lesão de comportamento incerto (CID {f['cid_principal']})"
    elif dor and dor >= 7:
        classe, motivo = "B", f"dor intensa (EVA {dor:.0f})"
    elif lim == "grave":
        classe, motivo = "B", "limitação funcional grave"
    elif len(ps) >= 2:
        classe, motivo = "B", "idas repetidas ao PS ou internações recentes"
    elif dor and dor >= 4:
        classe, motivo = "C", f"dor moderada (EVA {dor:.0f})"
    elif lim == "moderada":
        classe, motivo = "C", "limitação funcional moderada"
    elif ps:
        classe, motivo = "C", "uma ida recente ao PS"
    else:
        classe, motivo = "D", "sem dor, limitação ou piora relevantes"

    dias = int(f["dias_em_fila"])
    razao = dias / PRAZO[classe]
    fatores = {
        "urgency": PONTOS_CLASSE[classe],
        "wait": round(min(25, 25 * min(razao, 2) / 2), 1),
        "events": min(20, 6 * len(ps) + 4 * len(piora) + (8 if progressao else 0) + (6 if biopsia and not onco else 0)),
        "symptoms": round((dor or 0) * 0.8 + PONTOS_LIMITACAO.get(lim, 0), 1),
    }
    eventos_txt = []
    if ps:
        eventos_txt.append(f"{len(ps)} PS/internação em 180 dias")
    if piora:
        eventos_txt.append(f"{len(piora)} relato(s) de piora")
    if progressao:
        eventos_txt.append("imagem com progressão")
    return {
        "classe": classe,
        "motivo": motivo,
        "fatores": fatores,
        "indice": round(sum(fatores.values()), 1),
        "dias": dias,
        "eventos_txt": eventos_txt,
        "onco": onco,
    }


def priorizar(pasta):
    """Devolve a fila inteira ordenada pelo Neco, com cálculo e posição."""
    fila, eventos, por_solicitacao = carregar(pasta)
    linhas = []
    for f in fila:
        c = calcular(f, por_solicitacao.get(f["solicitacao_id"], []))
        linhas.append({**f, **c})
    linhas.sort(key=lambda r: (-RANK[r["classe"]], -r["indice"], -r["dias"]))
    for i, r in enumerate(linhas, 1):
        r["posicao"] = i
    return linhas, eventos


def _br(n):
    return f"{n:g}".replace(".", ",")


def justificativa(r, notas=()):
    """Texto curto e auditável para a coluna `justificativa` da entrega."""
    prazo = PRAZO[r["classe"]]
    atraso = r["dias"] - prazo
    partes = [f"Classe {r['classe']} ({ROTULO[r['classe']]}, SWALIS adaptado): {r['motivo']}."]
    if r["eventos_txt"]:
        partes.append("Eventos: " + "; ".join(r["eventos_txt"]) + ".")
    partes.append(f"Espera de {r['dias']} dias" + (f", {atraso} além do prazo de {prazo}." if atraso > 0 else f", dentro do prazo de {prazo}."))
    fz = r["fatores"]
    partes.append(
        f"Índice {_br(r['indice'])}/97 (urgência {_br(fz['urgency'])}, espera {_br(fz['wait'])}, "
        f"eventos {_br(fz['events'])}, sintomas {_br(fz['symptoms'])})."
    )
    partes.extend(notas)
    return " ".join(partes)
