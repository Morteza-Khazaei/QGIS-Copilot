def test_header_symbols_planned_known():
    from copilot.manifest.qgis_manifest_build import build_manifest
    from copilot.manifest.qgis_oracle import load_manifest
    path = build_manifest()
    assert path
    man = load_manifest()
    # Ensure known method is in manifest
    core = man["modules"]["qgis.core"]
    assert "QgsRasterShader" in core
    assert "setRasterShaderFunction" in core["QgsRasterShader"]["attrs"]

