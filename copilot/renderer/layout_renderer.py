"""Minimal spec-first renderer for layouts and raster styling.

This avoids the agent writing PyQGIS calls directly; only trusted code here
interacts with PyQGIS and can be audited/whitelisted.
"""
from typing import Dict, List, Tuple

from qgis.core import (
    QgsProject, QgsRasterLayer, QgsColorRampShader, QgsRasterShader,
    QgsSingleBandPseudoColorRenderer, QgsPrintLayout, QgsLayoutItemMap,
    QgsLayoutSize, QgsUnitTypes, QgsLayoutPoint, QgsLayoutExporter
)
from qgis.PyQt.QtGui import QColor


def _as_layer(layer_spec) -> QgsRasterLayer:
    """Load a raster layer by path or by current project layer name."""
    if isinstance(layer_spec, QgsRasterLayer):
        return layer_spec
    if isinstance(layer_spec, str):
        # Try existing project layer by name
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == layer_spec and isinstance(lyr, QgsRasterLayer):
                return lyr
        # Otherwise try as file path
        lyr = QgsRasterLayer(layer_spec, layer_spec)
        if lyr.isValid():
            QgsProject.instance().addMapLayer(lyr)
            return lyr
    raise ValueError("Raster layer not found or invalid: %r" % (layer_spec,))


def _build_color_ramp_shader(stops: List[Tuple[float, str]]) -> QgsColorRampShader:
    items = []
    for val, color in stops:
        items.append(QgsColorRampShader.ColorRampItem(float(val), QColor(color)))
    shader = QgsColorRampShader()
    shader.setColorRampItemList(items)
    shader.setColorRampType(QgsColorRampShader.Interpolated)
    return shader


def apply_raster_style(spec: Dict) -> QgsRasterLayer:
    data = spec or {}
    layer = _as_layer(data.get("layer"))
    shader_spec = data.get("shader") or {}
    if shader_spec.get("type") == "color_ramp":
        stops = shader_spec.get("stops") or []
        color_shader = _build_color_ramp_shader(stops)
        rshader = QgsRasterShader()
        rshader.setRasterShaderFunction(color_shader)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, rshader)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
    return layer


def export_layout(map_layer: QgsRasterLayer, export: Dict):
    proj = QgsProject.instance()
    layout = QgsPrintLayout(proj)
    layout.initializeDefaults()
    map_item = QgsLayoutItemMap(layout)
    # Prefer setting scene rect if available
    try:
        from qgis.PyQt.QtCore import QRectF
        map_item.attemptSetSceneRect(QRectF(0, 0, 200, 130))
    except Exception:
        # Will be positioned via move/resize below
        pass
    map_item.setFrameEnabled(True)
    map_item.setExtent(map_layer.extent())
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(10, 10, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(190, 120, QgsUnitTypes.LayoutMillimeters))
    exporter = QgsLayoutExporter(layout)
    if export.get("pdf"):
        exporter.exportToPdf(export["pdf"], QgsLayoutExporter.PdfExportSettings())
    if export.get("png"):
        ps = QgsLayoutExporter.ImageExportSettings()
        dpi = int(export.get("dpi", 300))
        ps.dpi = dpi
        exporter.exportToImage(export["png"], ps)


def render_layout(spec: Dict):
    """Render a layout from a spec dict.

    Schema (minimum):
      {
        "name": "NDVI map",
        "raster_style": { ... },
        "export": {"pdf": "out.pdf", "png": "out.png", "dpi": 300}
      }
    """
    raster = None
    if spec.get("raster_style"):
        raster = apply_raster_style(spec.get("raster_style"))
    if raster is not None and spec.get("export"):
        export_layout(raster, spec.get("export"))
    return {"ok": True, "details": "Rendered layout", "layer": raster.name() if raster else None}
