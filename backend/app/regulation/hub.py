"""Fan-out of server frames to every connected admin.

Each socket gets a Subscription (a bounded queue); `publish` only enqueues, so
a slow client never blocks the request that changed the queue. A client that
falls too far behind is dropped: its socket closes, the front reconnects and
resynchronizes from the `queue.snapshot` it gets on connect.
"""
import queue
import threading

MAX_PENDING = 1000


class Subscription:
    def __init__(self, hub, max_pending=MAX_PENDING):
        self._hub = hub
        self._frames = queue.Queue(maxsize=max_pending)
        self.closed = False

    def put(self, frame):
        if self.closed:
            return
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            self.close()

    def get(self, timeout=None):
        """Next frame, or None when nothing arrived within `timeout` seconds."""
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self.closed = True
        self._hub.remove(self)


class Hub:
    def __init__(self, max_pending=MAX_PENDING):
        self._lock = threading.Lock()
        self._subscriptions = set()
        self._max_pending = max_pending

    def subscribe(self):
        subscription = Subscription(self, self._max_pending)
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def remove(self, subscription):
        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, frame):
        with self._lock:
            targets = list(self._subscriptions)
        for subscription in targets:
            subscription.put(frame)

    def __len__(self):
        with self._lock:
            return len(self._subscriptions)
