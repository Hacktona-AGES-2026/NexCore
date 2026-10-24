"""The push-only socket the front listens to (§6 of the contract).

The front never sends anything here: actions go over REST. This loop only
drains the connection's Subscription onto the socket. Like realtime.channel, it
takes the socket as an argument and only calls `send()` (plus reading the
`connected` flag simple-websocket keeps), so tests drive it with a double.
"""
import json

#: How often an idle loop wakes up to notice a client that went away.
POLL_SECONDS = 1.0


def encode(frame):
    return json.dumps(frame, ensure_ascii=False)


def serve(ws, subscription, poll_seconds=POLL_SECONDS):
    """Forwards frames until the client leaves or falls too far behind."""
    try:
        while not subscription.closed:
            frame = subscription.get(timeout=poll_seconds)
            if frame is None:
                if not getattr(ws, "connected", True):
                    return
                continue
            ws.send(encode(frame))
    except Exception:  # noqa: BLE001  (a closed socket ends the loop, nothing else)
        return
    finally:
        subscription.close()
