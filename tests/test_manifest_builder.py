def test_manifest_contains_color_ramp_shader():
    from copilot.manifest.qgis_manifest_build import build_manifest
    from copilot.manifest.qgis_oracle import load_manifest
    path = build_manifest()
    assert path
    man = load_manifest()
    core = man["modules"]["qgis.core"]
    assert "QgsColorRampShader" in core
    attrs = core["QgsColorRampShader"]["attrs"]
    assert "setSourceColorRamp" in attrs

