import difflib


def safe_call(obj, name, *args, **kw):
    """Call an attribute safely with friendly hints if missing.

    Example: safe_call(shader, "setSourceColorRamp", ramp)
    """
    if not hasattr(obj, name):
        hint = difflib.get_close_matches(name, dir(obj), n=1)
        raise AttributeError(
            f"{type(obj).__name__}.{name} not found" + (f". Did you mean '{hint[0]}'?" if hint else "")
        )
    return getattr(obj, name)(*args, **kw)

