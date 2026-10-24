"""The thin layer over the socket: read a command, run it, write frames.

`serve` takes the socket as an argument and only ever calls `receive()` and
`send()` on it, so the tests drive it with a double instead of a real
connection. No business rule lives here — that is what actions.py is for.
"""
from ..errors import RequestError
from . import actions, protocol


def serve(ws, repository, limits, logger=None):
    """Answers one connection until the client goes away."""
    send(ws, protocol.welcome(
        repository.reference_date, repository.counts(), actions.names()
    ))
    while True:
        raw = ws.receive()
        if raw is None:  # client closed the connection
            return
        handle(ws, raw, repository, limits, logger)


def handle(ws, raw, repository, limits, logger=None):
    """Runs a single command, reporting failure as a frame.

    A bad command costs the client an error frame, never the connection: other
    work may be in flight on the same socket.
    """
    command_id = None
    action_name = None
    try:
        command_id, action_name, params = protocol.parse(raw)
        for kind, payload in actions.run(action_name, repository, params, limits):
            if kind == "progress":
                send(ws, protocol.progress(command_id, action_name, *payload))
            else:
                send(ws, protocol.result(command_id, action_name, payload))
    except RequestError as exc:
        send(ws, protocol.error(
            getattr(exc, "command_id", None) or command_id,
            action_name, exc.message, exc.status, exc.details,
        ))
    except Exception as exc:  # noqa: BLE001  (a bug must not kill the socket)
        if logger is not None:
            logger.exception("action '%s' failed: %s", action_name, exc)
        send(ws, protocol.error(
            command_id, action_name, "internal server error", 500
        ))


def send(ws, frame):
    ws.send(protocol.encode(frame))
