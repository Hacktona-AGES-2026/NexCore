"""Wire format of the WebSocket channel.

Every frame the server sends carries a `type`, so a TypeScript client can
discriminate on it and let the compiler check exhaustiveness:

    type ServerFrame = Welcome | Result | Progress | ServerError

A command from the client is `{id, action, params}`. The `id` is echoed back on
every frame produced by that command, so the client can correlate a long
calculation's progress with the request that started it. It is opaque to us.

Pure module: no Flask, no socket. The channel turns these dicts into JSON.
Field names are English, like the rest of our code; the values inside `params`
and the records we return keep the dataset's Portuguese terms.
"""
import json

from ..errors import RequestError

PROTOCOL_VERSION = 1


class ProtocolError(RequestError):
    """A RequestError that remembers which command it came from.

    Once `id` has been read off the frame we want it echoed on the error, so the
    client can settle the right pending promise. Before that we cannot know it.
    """

    def __init__(self, message, status=400, details=None, command_id=None):
        super().__init__(message, status, details)
        self.command_id = command_id


def parse(raw):
    """Text frame from the client -> (command_id, action, params).

    Raises RequestError, which the channel reports as an `error` frame without
    dropping the connection: one malformed command must not cost the client its
    socket (and the progress of whatever else is running on it).
    """
    if isinstance(raw, (bytes, bytearray)):
        raise RequestError("binary frames are not accepted, send JSON text")
    try:
        command = json.loads(raw)
    except (TypeError, ValueError):
        raise RequestError("frame is not valid JSON")
    if not isinstance(command, dict):
        raise RequestError("frame must be a JSON object")

    command_id = command.get("id")
    if command_id is not None and not isinstance(command_id, (str, int)):
        raise RequestError("'id' must be a string or a number")

    action = command.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ProtocolError("'action' is required", command_id=command_id)

    params = command.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ProtocolError("'params' must be an object", command_id=command_id)

    return command_id, action.strip(), params


def welcome(reference_date, counts, actions):
    """First frame on every connection: what this server is and what it answers."""
    return {
        "type": "welcome",
        "protocol": PROTOCOL_VERSION,
        "reference_date": reference_date,
        "dataset": counts,
        "actions": list(actions),
    }


def result(command_id, action, payload):
    """Final frame of a command. `payload`'s shape depends on the action."""
    return {"type": "result", "id": command_id, "action": action, "payload": payload}


def progress(command_id, action, completed, total, label=None):
    """Intermediate frame of a long calculation."""
    return {
        "type": "progress",
        "id": command_id,
        "action": action,
        "completed": completed,
        "total": total,
        "percent": round(100 * completed / total, 1) if total else 100.0,
        "label": label,
    }


def error(command_id, action, message, status=400, details=None):
    """Terminal frame of a failed command. The connection stays open."""
    frame = {
        "type": "error",
        "id": command_id,
        "action": action,
        "error": {"message": message, "status": status},
    }
    if details:
        frame["error"]["details"] = details
    return frame


def encode(frame):
    return json.dumps(frame, ensure_ascii=False)
