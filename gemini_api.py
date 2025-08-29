"""
Google Gemini API Integration for QGIS Copilot
"""

import json
import requests
from qgis.PyQt.QtCore import QSettings, QObject, pyqtSignal
from qgis.core import QgsMessageLog, Qgis, QgsProject, QgsMapLayer


class GeminiAPI(QObject):
    """Handle Google Gemini API communication"""
    
    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    AVAILABLE_MODELS = ["gemini-1.5-flash"]

    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.api_key = self.settings.value("qgis_copilot/gemini_api_key", "")
        self.model = self.settings.value("qgis_copilot/gemini_model", self.AVAILABLE_MODELS[0])
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        # System prompt for PyQGIS context
        self.system_prompt = """
You are QGIS Copilot, an intelligent assistant that helps users work with QGIS through the PyQGIS API.
You are knowledgeable, helpful, and always provide practical solutions.

You can help users with:
- Layer management (adding, removing, styling layers)
- Spatial analysis and processing
- Map canvas operations
- Project management
- Data import/export
- Geometric operations
- Attribute operations
- Processing algorithms
- Map visualization and cartography

When providing code solutions:
- Always use PyQGIS API calls
- Explain what the code does in plain language
- Format code with proper Python syntax
- Provide executable, working code
- Consider error handling when appropriate
- Do not use functions that require user input in the middle of a script, like `input()`. The user provides input through the chat interface.

Execution Environment & Rules:
- **CRITICAL**: Do NOT include `import qgis` or `from qgis import ...` statements. The necessary QGIS modules and classes are already available in the execution environment and these imports will cause the code to fail.
- You can import standard Python libraries like `random` or `math`.

Available Globals:
- `iface`, `project`, `canvas`
- `QgsProject`, `QgsApplication`, `QgsVectorLayer`, `QgsRasterLayer`, `QgsMapLayer`, `QgsMessageLog`, `QgsWkbTypes`, `Qgis`
- Modules: `core`, `gui`, `analysis`, `processing`

How to use classes:
- Use global classes like `QgsVectorLayer` directly.
- For most other QGIS classes, use the `core` prefix. For example: `core.QgsFeature()`, `core.QgsGeometry.fromWkt(...)`, `core.QgsField(...)`.

Example of **CORRECT** code for creating points:
```python
# No QGIS imports needed!
import random

extent = iface.mapCanvas().extent()
layer = QgsVectorLayer("Point?crs=" + project.crs().authid(), "random_points", "memory")
provider = layer.dataProvider()

# Add a field for ID.
provider.addAttributes([core.QgsField("id", 2)]) # 2 is for integer type
layer.updateFields()

# Create 10 random points
features = []
for i in range(10):
    x = random.uniform(extent.xMinimum(), extent.xMaximum())
    y = random.uniform(extent.yMinimum(), extent.yMaximum())
    point = core.QgsPointXY(x, y)
    feature = core.QgsFeature()
    feature.setGeometry(core.QgsGeometry.fromPointXY(point))
    feature.setAttributes([i])
    features.append(feature)

provider.addFeatures(features)
project.addMapLayer(layer)
```

Common Operations Guide:
- To get the active layer: `layer = iface.activeLayer()`
- To get selected features: `features = layer.selectedFeatures()`
- To open an attribute table for a layer: `iface.showAttributeTable(layer)`. Do NOT try to import or instantiate `QgsAttributeTable`.
- To add a layer to the project: `project.addMapLayer(layer)`
- To run a processing algorithm: `processing.run("native:buffer", {'INPUT': ..., 'DISTANCE': ..., 'OUTPUT': 'memory:'})`
- To edit attributes, use standard Python types (int, str, float). Avoid using `QVariant` as it is largely unnecessary in QGIS 3.
- To create a new temporary layer (e.g., for random points), create a "memory" layer. Example: `QgsVectorLayer("Point?crs=epsg:4326", "temporary_points", "memory")`

Be Proactive: If a user's request is slightly ambiguous, make a reasonable assumption and generate code that performs a first version of the task. Always create new layers as temporary memory layers. After providing the code, you can ask clarifying questions to help the user refine the result. For example, if a user asks to 'create random points', assume a reasonable number (e.g., 10) within the current map view, create them on a memory layer, and then ask if they want a different quantity or extent.

Follow-up Suggestions: After providing code, especially code that creates a new layer, always suggest a few potential next steps. Assume the code will be executed successfully. For example, if your code creates a buffer layer, you could then ask the user: "The code above will create a temporary buffer layer. Once it's created, would you like to change its style, run an analysis on it, or save it to a permanent file?" This makes your response more interactive and helpful.

Always prioritize safe operations and warn about potentially destructive actions.
Be conversational and helpful - you're a copilot, not just a code generator.
"""

    def set_api_key(self, api_key):
        """Set and save the Gemini API key"""
        self.api_key = api_key
        self.settings.setValue("qgis_copilot/gemini_api_key", api_key)
    
    def set_model(self, model_name):
        """Set and save the Gemini model"""
        if model_name in self.AVAILABLE_MODELS:
            self.model = model_name
            self.settings.setValue("qgis_copilot/gemini_model", model_name)
    
    def get_api_key(self):
        """Get the stored API key"""
        return self.settings.value("qgis_copilot/gemini_api_key", "")
    
    def send_message(self, message, context=None):
        """Send a message to Gemini API with QGIS context"""
        if not self.api_key:
            self.error_occurred.emit("No API key configured")
            return
        
        # Prepare the request
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        
        # Build the full prompt with context
        full_prompt = self.system_prompt
        if context:
            full_prompt += f"\n\nCurrent QGIS Context:\n{context}"
        full_prompt += f"\n\nUser Question: {message}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": full_prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 2048,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
        
        try:
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    self.response_received.emit(content)
                else:
                    self.error_occurred.emit("No response generated")
            else:
                error_msg = f"API Error {response.status_code}: {response.text}"
                self.error_occurred.emit(error_msg)
                QgsMessageLog.logMessage(
                    error_msg, 
                    "QGIS Copilot", 
                    level=Qgis.Critical
                )
                
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            self.error_occurred.emit(error_msg)
            QgsMessageLog.logMessage(
                error_msg, 
                "QGIS Copilot", 
                level=Qgis.Critical
            )
    
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

            if layer_types:
                type_summary = ", ".join([f"{count} {l_type}" for l_type, count in layer_types.items() if count > 0])
                context_info.append(f"Layer Types: {type_summary}")

            return "\n".join(context_info)

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting context: {str(e)}",
                "QGIS Copilot",
                level=Qgis.Warning
            )
            return "Context information unavailable"