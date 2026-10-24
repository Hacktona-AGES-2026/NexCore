"""Registry of the calculations the channel can run.

An action is a function of (repository, params, limits) that returns the payload
to send back. A *long* action is a generator instead: it `yield Progress(...)`
as it advances and `return`s the payload when it finishes. `run` turns those
yields into progress frames, so a calculation never has to know that a socket
exists — it stays a pure function, testable without any transport.

Registering one is a single decorator; nothing in the channel changes:

    @action("queue.prioritize")
    def prioritize(repository, params, limits):
        for done, total in ...:
            yield Progress(done, total, "ranqueando")
        return {"data": ranked}
"""
from collections import namedtuple
import inspect

from ..errors import RequestError

#: One step of a long calculation. `label` is free text for the UI.
Progress = namedtuple("Progress", "completed total label", defaults=(None,))

_REGISTRY = {}


def action(name):
    """Registers a calculation under the name clients ask for."""

    def decorator(func):
        if name in _REGISTRY:
            raise RuntimeError(f"action '{name}' is already registered")
        _REGISTRY[name] = func
        return func

    return decorator


def names():
    return sorted(_REGISTRY)


def run(name, repository, params, limits):
    """Runs an action, yielding ("progress", Progress) then ("result", payload).

    A generator itself, so progress reaches the client while the calculation is
    still running instead of piling up until the end.
    """
    handler = _REGISTRY.get(name)
    if handler is None:
        raise RequestError(f"unknown action '{name}'", 404, {"actions": names()})

    outcome = handler(repository, params, limits)
    if not inspect.isgenerator(outcome):
        yield "result", outcome
        return

    while True:
        try:
            step = next(outcome)
        except StopIteration as stop:
            yield "result", stop.value
            return
        if not isinstance(step, Progress):
            raise TypeError(
                f"action '{name}' yielded {type(step).__name__}, expected Progress"
            )
        yield "progress", step
