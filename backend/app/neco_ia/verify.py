"""The guard between the model's text and the screen: no invented numbers.

Positions, days, scores and deadlines come from the deterministic ranking. The
model only writes about them, so every number it writes must be one it was
given. A text with a number that is not in its facts is dropped and the
rule-based text is shown instead.
"""
import re

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _canonical(token):
    value = float(token.replace(",", "."))
    return str(int(value)) if value.is_integer() else f"{value:g}"


def numbers_in(value):
    """Every number inside `value` (str, number, list or dict), canonicalised."""
    found = set()
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, (int, float)):
        found.add(_canonical(str(value)))
    elif isinstance(value, str):
        found.update(_canonical(t) for t in NUMBER.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            found |= numbers_in(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found |= numbers_in(item)
    return found


def invented_numbers(text, facts):
    """Numbers in `text` that appear nowhere in `facts`; empty means the text is safe."""
    return numbers_in(text) - numbers_in(facts)
