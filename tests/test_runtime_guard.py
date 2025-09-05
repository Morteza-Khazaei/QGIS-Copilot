import pytest


def test_safe_call_suggests_fix():
    from copilot.guards.runtime import safe_call
    class Dummy:
        def setSourceColorRamp(self):
            return "ok"
    d = Dummy()
    with pytest.raises(AttributeError) as ei:
        safe_call(d, "setSourceRamp")
    assert "Did you mean 'setSourceColorRamp'" in str(ei.value)

