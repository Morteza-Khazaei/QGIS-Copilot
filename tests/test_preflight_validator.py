def test_preflight_suggests_correct_method():
    from copilot.guards.preflight import validate
    code = (
        "# {\n"
        "#   \"vars\": {\"color_shader\": \"QgsColorRampShader\"}\n"
        "# }\n"
        "from qgis.core import QgsColorRampShader\n"
        "color_shader: QgsColorRampShader = QgsColorRampShader()\n"
        "color_shader.setSourceRamp(None)\n"
    )
    errors, tips, _ = validate(code)
    assert errors, "Expected an error for wrong method name"
    flat = ",".join([",".join(t) for t in tips if t])
    assert "QgsColorRampShader.setSourceColorRamp" in flat

