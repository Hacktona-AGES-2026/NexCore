"""Cliente de linha de comando para conversar com o canal à mão.

    python tools/ws_client.py                                  # modo interativo
    python tools/ws_client.py stats.summary                     # um comando e sai
    python tools/ws_client.py queue.list size=3 oncological=true
    python tools/ws_client.py queue.prioritize --raw | jq .     # JSON cru

Usa o `simple-websocket` que já vem com o flask-sock, então não pede nada novo.
O parsing e a formatação são funções puras — é o que os testes exercitam.
"""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_URL = "ws://127.0.0.1:5000/ws"
TIMEOUT = 30


def parse_params(pairs):
    """["size=3", "oncological=true"] -> {"size": 3, "oncological": True}

    Converte o que parece número e booleano, porque o canal aceita JSON de
    verdade; o resto vai como texto. `chave=` manda string vazia, que é como se
    testa que parâmetro vazio é ignorado.
    """
    params = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"esperava chave=valor, recebi {pair!r}")
        chave, valor = pair.split("=", 1)
        params[chave.strip()] = _convert(valor.strip())
    return params


def _convert(valor):
    baixo = valor.lower()
    if baixo in {"true", "false"}:
        return baixo == "true"
    if baixo == "null":
        return None
    try:
        return int(valor)
    except ValueError:
        pass
    try:
        return float(valor)
    except ValueError:
        return valor


def describe(frame):
    """Uma linha legível por frame. Não levanta: frame desconhecido vira texto."""
    tipo = frame.get("type")
    if tipo == "welcome":
        dataset = frame.get("dataset", {})
        return (
            f"conectado · protocolo {frame.get('protocol')} · "
            f"ref {frame.get('reference_date')} · "
            f"{dataset.get('queue')} solicitações · "
            f"{len(frame.get('actions', []))} ações"
        )
    if tipo == "progress":
        return (
            f"  ... {frame.get('completed')}/{frame.get('total')}"
            f" ({frame.get('percent')}%) {frame.get('label') or ''}".rstrip()
        )
    if tipo == "result":
        return f"ok {frame.get('action')} · {summarize(frame.get('payload'))}"
    if tipo == "error":
        erro = frame.get("error", {})
        return f"erro {erro.get('status')} em {frame.get('action')}: {erro.get('message')}"
    return f"frame desconhecido: {json.dumps(frame, ensure_ascii=False)[:120]}"


def summarize(payload):
    """Resume o payload sem despejar 941 registros no terminal."""
    if not isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)[:120]
    partes = []
    if isinstance(payload.get("data"), list):
        partes.append(f"{len(payload['data'])} registros")
    if isinstance(payload.get("pagination"), dict):
        partes.append(f"total {payload['pagination'].get('total')}")
    if payload.get("provisional"):
        partes.append(f"PROVISÓRIO ({payload.get('strategy')})")
    if not partes:
        partes.append(", ".join(list(payload)[:6]))
    return " · ".join(partes)


# --- rede ----------------------------------------------------------------

def conversar(cliente, action, params, raw, saida):
    """Manda um comando e imprime os frames até o result/error. Devolve o frame final."""
    cliente.send(json.dumps({"id": "cli", "action": action, "params": params}))
    while True:
        frame = json.loads(cliente.receive(timeout=TIMEOUT))
        if raw:
            print(json.dumps(frame, ensure_ascii=False), file=saida)
        else:
            print(describe(frame), file=saida)
        if frame.get("type") in {"result", "error"}:
            return frame


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", nargs="?", help="ex.: queue.list (vazio = interativo)")
    parser.add_argument("params", nargs="*", help="pares chave=valor")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--raw", action="store_true", help="JSON cru, um frame por linha")
    args = parser.parse_args(argv)

    import simple_websocket

    try:
        cliente = simple_websocket.Client(args.url)
    except Exception as exc:
        print(f"não conectou em {args.url}: {exc}", file=sys.stderr)
        print("o servidor está rodando? python wsgi.py", file=sys.stderr)
        return 2

    welcome = json.loads(cliente.receive(timeout=TIMEOUT))
    print(json.dumps(welcome, ensure_ascii=False) if args.raw else describe(welcome))

    try:
        if args.action:
            frame = conversar(
                cliente, args.action, parse_params(args.params), args.raw, sys.stdout
            )
            return 1 if frame.get("type") == "error" else 0

        print("ações:", ", ".join(welcome.get("actions", [])))
        print("digite: <ação> [chave=valor ...]   (ctrl-d para sair)")
        while True:
            try:
                linha = input("> ").strip()
            except EOFError:
                return 0
            if not linha:
                continue
            action, *pares = linha.split()
            try:
                params = parse_params(pares)
            except ValueError as exc:
                print(exc, file=sys.stderr)
                continue
            conversar(cliente, action, params, args.raw, sys.stdout)
    finally:
        cliente.close()


if __name__ == "__main__":
    sys.exit(main())
