"""Gera o entregável oficial (fila_priorizada.csv), roda o verificador do
desafio na fila do Neco e na fila manual de hoje, e monta o painel de impacto.

Uso (da raiz do repositório; o verificador precisa de pandas):
    python entrega/gerar_entrega.py
    python entrega/gerar_entrega.py --front   # também atualiza os dados do mock do front
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict

import neco

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(RAIZ, "backend", "dataset")
NORMALIZADO = os.path.join(DATASET, "normalizado")
SAIDA = os.path.join(RAIZ, "entrega")
FRONT_MOCK = os.path.join(RAIZ, "frontend", "src", "mock")

PRIORIDADE_MANUAL = {"alta": 3, "media": 2, "baixa": 1}


def notas_de_qualidade(linhas, eventos):
    """Observações que entram na justificativa: o que o Neco contornou nos dados."""
    notas = defaultdict(list)
    pares = defaultdict(list)
    for r in linhas:
        if r["flag_oncologico_norm"] != r["oncologico_cid"]:
            notas[r["solicitacao_id"]].append("Flag oncológica do cadastro diverge do CID; usado o CID.")
        pares[(r["paciente_id"], r["procedimento_id"])].append(r["solicitacao_id"])
    for ids in pares.values():
        if len(ids) > 1:
            for sid in ids:
                outras = ", ".join(x for x in ids if x != sid)
                notas[sid].append(f"Possível duplicata de {outras}; mantida até revisão humana.")
    for e in eventos:
        if e["resultado_norm"] == "informou_cirurgia_outro_servico":
            notas[e["solicitacao_id"]].append("Call center informou cirurgia em outro serviço; confirmar antes de retirar.")
        elif e["resultado_norm"] == "desistiu":
            notas[e["solicitacao_id"]].append("Call center registrou desistência; confirmar antes de retirar.")
    return {k: list(dict.fromkeys(v)) for k, v in notas.items()}


def fila_manual(linhas):
    """Fila de referência de hoje: prioridade manual da regulação, desempate pelo tempo de espera."""
    ordem = sorted(linhas, key=lambda r: (-PRIORIDADE_MANUAL.get(r["prioridade_regulacao_norm"], 0), -r["dias"]))
    return {r["solicitacao_id"]: i for i, r in enumerate(ordem, 1)}


def escrever(caminho, linhas):
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["solicitacao_id", "posicao", "justificativa"])
        w.writerows(linhas)


def verificar(arquivo):
    """Roda o verificador oficial e devolve (ok, saída, indicadores)."""
    p = subprocess.run(
        [sys.executable, os.path.join(DATASET, "verificar_fila_priorizada.py"), arquivo, "--dataset", DATASET],
        capture_output=True, text=True, encoding="utf-8",
    )
    saida = p.stdout.strip().replace(RAIZ + os.sep, "")
    if p.returncode not in (0, 1) or not saida:
        raise SystemExit(f"Verificador falhou:\n{p.stderr}")

    def achar(padrao, conv=int):
        m = re.search(padrao, saida)
        return conv(m.group(1)) if m else None

    return p.returncode == 0, saida, {
        "violacoes": achar(r"REGRA DE OURO VIOLADA: (\d+)") or 0,
        "medianaOnco": achar(r"posição mediana dos oncológicos: (\d+)"),
        "oncoPrimeiroTerco": achar(r"oncológicos no primeiro terço: (\d+)%"),
        "psPrimeiraMetade": achar(r"últimos 180 dias na primeira metade: (\d+)%"),
        "calmosUltimoTerco": achar(r"sem urgência clínica no último terço: (\d+)%"),
    }


def iniciais(nome):
    return "".join(p[0] + "." for p in nome.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--front", action="store_true", help="atualiza os dados do mock do front")
    a = ap.parse_args()

    linhas, eventos = neco.priorizar(NORMALIZADO)
    notas = notas_de_qualidade(linhas, eventos)
    manual = fila_manual(linhas)

    oficial = os.path.join(SAIDA, "fila_priorizada.csv")
    escrever(oficial, [(r["solicitacao_id"], r["posicao"], neco.justificativa(r, notas.get(r["solicitacao_id"], []))) for r in linhas])
    os.makedirs(os.path.join(SAIDA, "comparacao"), exist_ok=True)
    referencia = os.path.join(SAIDA, "comparacao", "fila_manual_referencia.csv")
    escrever(referencia, sorted(
        ((r["solicitacao_id"], manual[r["solicitacao_id"]], f"Prioridade manual: {r['prioridade_regulacao_norm'] or 'vazia'}; {r['dias']} dias em fila.") for r in linhas),
        key=lambda x: x[1]))

    ok_neco, saida_neco, ind_neco = verificar(oficial)
    ok_manual, saida_manual, ind_manual = verificar(referencia)
    with open(os.path.join(SAIDA, "verificacao.txt"), "w", encoding="utf-8") as f:
        f.write(saida_neco + "\n")
    with open(os.path.join(SAIDA, "comparacao", "verificacao_fila_manual.txt"), "w", encoding="utf-8") as f:
        f.write(saida_manual + "\n")

    # Matriz classe do Neco x prioridade manual
    matriz = Counter((r["classe"], r["prioridade_regulacao_norm"] or "vazia") for r in linhas)
    por_classe = Counter(r["classe"] for r in linhas)
    graves = [r for r in linhas if r["classe"] in ("A1", "A2")]
    movidos = sorted(linhas, key=lambda r: r["posicao"] - manual[r["solicitacao_id"]])[:6]

    impacto = {
        "total": len(linhas),
        "baseline": "Fila de hoje: prioridade manual da regulação (alta, média, baixa), com desempate pelo maior tempo de espera.",
        "verifier": {
            "neco": {"ok": ok_neco, "output": saida_neco, **ind_neco},
            "manual": {"ok": ok_manual, "output": saida_manual, **ind_manual},
        },
        "matrix": [{"cls": c, **{p: matriz[(c, p)] for p in ("alta", "media", "baixa", "vazia")}} for c in ("A1", "A2", "B", "C", "D")],
        "headline": {
            "a1Total": por_classe["A1"],
            "a1Low": matriz[("A1", "baixa")] + matriz[("A1", "vazia")],
            "urgentTotal": len(graves),
            "urgentLow": sum(1 for r in graves if r["prioridade_regulacao_norm"] in ("baixa", "")),
            "dTotal": por_classe["D"],
            "dHigh": matriz[("D", "alta")],
        },
        "movers": [{
            "id": r["solicitacao_id"], "initials": iniciais(r["nome_paciente"]), "procedure": r["procedimento"],
            "cls": r["classe"], "reason": r["motivo"], "manualPriority": r["prioridade_regulacao_norm"] or "vazia",
            "manualPosition": manual[r["solicitacao_id"]], "necoPosition": r["posicao"],
        } for r in movidos],
    }
    with open(os.path.join(SAIDA, "impacto.json"), "w", encoding="utf-8") as f:
        json.dump(impacto, f, ensure_ascii=False, indent=1)

    print(f"fila_priorizada.csv: {len(linhas)} linhas")
    print(f"Verificador | Neco: {'OK' if ok_neco else 'ERRO'} ({ind_neco['violacoes']} violações) | manual: {'OK' if ok_manual else 'ERRO'} ({ind_manual['violacoes']} violações)")

    if a.front:
        shutil.copy(oficial, os.path.join(FRONT_MOCK, "fila_priorizada.csv"))
        shutil.copy(os.path.join(SAIDA, "impacto.json"), os.path.join(FRONT_MOCK, "impacto.json"))
        # Alinha as posições da amostra do mock com a entrega oficial.
        pos = {r["solicitacao_id"]: r["posicao"] for r in linhas}
        caminho_seed = os.path.join(FRONT_MOCK, "seed.json")
        with open(caminho_seed, encoding="utf-8") as f:
            seed = json.load(f)
        for row in seed["rows"]:
            row["pos"] = pos[row["id"]]
        with open(caminho_seed, "w", encoding="utf-8") as f:
            json.dump(seed, f, ensure_ascii=False, indent=1)
        caminho_stats = os.path.join(FRONT_MOCK, "stats.json")
        with open(caminho_stats, encoding="utf-8") as f:
            stats = json.load(f)
        stats["summary"]["top"] = [{
            "position": r["posicao"], "id": r["solicitacao_id"], "initials": iniciais(r["nome_paciente"]),
            "procedure": r["procedimento"], "cls": r["classe"], "days": r["dias"],
        } for r in linhas[:12]]
        with open(caminho_stats, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=1)
        print("Dados do mock do front atualizados.")


if __name__ == "__main__":
    main()
