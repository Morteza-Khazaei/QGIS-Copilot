"""
Anthropic Claude API Integration for QGIS Copilot
"""

import json
import requests
from qgis.PyQt.QtCore import QSettings, QObject, pyqtSignal
from qgis.core import QgsMessageLog, Qgis, QgsProject, QgsMapLayer


class ClaudeAPI(QObject):
    """Handle Anthropic Claude API communication"""

    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    AVAILABLE_MODELS = [
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307"
    ]

    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.api_key = self.settings.value("qgis_copilot/claude_api_key", "")
        self.model = self.settings.value("qgis_copilot/claude_model", self.AVAILABLE_MODELS[1])  # Sonnet as default
        self.base_url = "https://api.anthropic.com/v1"

        # System prompt for PyQGIS context (mirrors other APIs)
        self.system_prompt = """
You are QGIS Copilot, an intelligent assistant that helps users work with QGIS through the PyQGIS API.
You are knowledgeable, helpful, and always provide practical solutions.

When providing code solutions:
- Always use PyQGIS API calls
- Explain what the code does in plain language
- Format code with proper Python syntax
- Provide executable, working code
- Consider error handling when appropriate
- Do not use functions that require user input in the middle of a script, like `input()`. The user provides input through the chat interface.

Available QGIS context:
- iface: QgsInterface object for GUI interaction
- project: The current QgsProject instance (`QgsProject.instance()`)
- canvas: The map canvas (`iface.mapCanvas()`)
- The following modules are already imported and available: `core`, `gui`, `analysis`, `processing`.
- Many common QGIS classes are available directly (e.g., `QgsVectorLayer`, `QgsProject`).
- For other classes, use the module prefix (e.g., `core.QgsDistanceArea`).
- Do not include `import` statements for `qgis` modules, as they are blocked. You can import other standard Python libraries if they are not on the blocked list.

Common Operations Guide:
- To get the active layer: `layer = iface.activeLayer()`
- To get selected features: `features = layer.selectedFeatures()`
- To open an attribute table for a layer: `iface.showAttributeTable(layer)`. Do NOT try to import or instantiate `QgsAttributeTable`.
- To add a layer to the project: `project.addMapLayer(layer)`
- To run a processing algorithm: `processing.run("native:buffer", {'INPUT': ..., 'DISTANCE': ..., 'OUTPUT': 'memory:'})`
- To edit attributes, use standard Python types (int, str, float). Avoid using `QVariant` as it is largely unnecessary in QGIS 3.

Always prioritize safe operations and warn about potentially destructive actions.
Be conversational and helpful - you're a copilot, not just a code generator.
"""

    def set_api_key(self, api_key):
        """Set and save the Claude API key"""
        self.api_key = api_key
        self.settings.setValue("qgis_copilot/claude_api_key", api_key)

    def set_model(self, model_name):
        """Set and save the Claude model"""
        if model_name in self.AVAILABLE_MODELS:
            self.model = model_name
            self.settings.setValue("qgis_copilot/claude_model", model_name)

    def get_api_key(self):
        """Get the stored API key"""
        return self.settings.value("qgis_copilot/claude_api_key", "")

    def send_message(self, message, context=None):
        """Send a message to Claude API with QGIS context"""
        if not self.api_key:
            self.error_occurred.emit("No Claude API key configured")
            return

        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        system_content = self.system_prompt
        if context:
            system_content += f"\n\nCurrent QGIS Context:\n{context}"

        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "system": system_content,
            "messages": [
                {"role": "user", "content": message}
            ]
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=45)

            if response.status_code == 200:
                data = response.json()
                if "content" in data and len(data["content"]) > 0:
                    text_content = "".join(
                        block.get("text", "") for block in data["content"] if block.get("type") == "text"
                    )
                    self.response_received.emit(text_content.strip())
                else:
                    self.error_occurred.emit(f"No response generated. Payload: {data}")
            else:
                error_msg = f"API Error {response.status_code}: {response.text}"
                self.error_occurred.emit(error_msg)
                QgsMessageLog.logMessage(error_msg, "QGIS Copilot", level=Qgis.Critical)

        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            self.error_occurred.emit(error_msg)
            QgsMessageLog.logMessage(error_msg, "QGIS Copilot", level=Qgis.Critical)

    def get_qgis_context(self, iface):
        """Extract current QGIS context information"""
        try:
            context_info = []
            project = QgsProject.instance()
            if project:
                context_info.append(f"Project: {project.fileName() or 'Unsaved Project'}")
                context_info.append(f"Project CRS: {project.crs().authid()}")

            active_layer = iface.activeLayer()
            if active_layer:
                context_info.append(f"Active Layer: {active_layer.name()} ({active_layer.type()})")
                if hasattr(active_layer, 'featureCount'):
                    context_info.append(f"Feature Count: {active_layer.featureCount()}")
                if hasattr(active_layer, 'selectedFeatureCount'):
                    selected_count = active_layer.selectedFeatureCount()
                    if selected_count > 0:
                        context_info.append(f"Selected Features: {selected_count}")

            canvas = iface.mapCanvas()
            extent = canvas.extent()
            context_info.append(f"Map Extent: {extent.toString()}")
            context_info.append(f"Map CRS: {canvas.mapSettings().destinationCrs().authid()}")
            context_info.append(f"Map Scale: 1:{canvas.scale():,.0f}")

            layers = project.mapLayers().values()
            context_info.append(f"Total Layers: {len(layers)}")

            layer_types = {l_type.name: 0 for l_type in QgsMapLayer.LayerType.values()}
            for layer in layers:
                layer_types[layer.type().name] += 1

            type_summary = ", ".join([f"{count} {l_type}" for l_type, count in layer_types.items() if count > 0])
            context_info.append(f"Layer Types: {type_summary}")

            return "\n".join(context_info)

        except Exception as e:
            QgsMessageLog.logMessage(f"Error getting context: {str(e)}", "QGIS Copilot", level=Qgis.Warning)
            return "Context information unavailable"