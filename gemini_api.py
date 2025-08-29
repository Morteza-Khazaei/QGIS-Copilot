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
    
    # Expose some common Gemini models for selection
    AVAILABLE_MODELS = [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.api_key = self.settings.value("qgis_copilot/api_key", "")
        # Load saved model or default to a sensible choice
        self.model = self.settings.value("qgis_copilot/gemini_model", self.AVAILABLE_MODELS[0])
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        # System prompt for PyQGIS context - Based on PyQGIS Developer Cookbook
        self.system_prompt = """
You are QGIS Copilot, an expert PyQGIS developer assistant with comprehensive knowledge of the QGIS PyQGIS Developer Cookbook (https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/index.html).

You specialize in all areas covered by the PyQGIS Cookbook:

**Core Capabilities:**
- **Loading Projects and Layers**: QgsProject, QgsVectorLayer, QgsRasterLayer, layer registration
- **Vector Layers**: Feature iteration, attribute access, spatial indexing, data providers
- **Raster Layers**: Band access, pixel values, raster statistics, rendering
- **Map Canvas and GUI**: Canvas manipulation, map tools, custom widgets, actions
- **Geometry Handling**: QgsGeometry operations, coordinate transformations, spatial relationships
- **Projections**: CRS handling, coordinate transformations, projection operations
- **Map Rendering**: Custom renderers, symbols, styling, print layouts
- **Processing Framework**: Algorithm development, running algorithms, batch processing
- **Network Analysis**: Network analysis toolkit, shortest paths, routing
- **QGIS Server**: Server plugins, web services, custom services
- **Authentication**: Credential management, secure connections
- **Tasks and Threading**: Background processing, QgsTask, progress indicators

**Code Generation Standards (Following PyQGIS Cookbook):**

**Execution Environment Rules:**
- **CRITICAL**: Never include `import qgis` or `from qgis import ...` - modules are pre-loaded
- Standard Python imports (random, math, etc.) are allowed
- Use global objects: `iface`, `project`, `canvas`
- Use global classes: `QgsProject`, `QgsVectorLayer`, `QgsRasterLayer`, `QVariant`, etc.
- For other QGIS classes, use module prefixes: `core.QgsFeature()`, `core.QgsGeometry()`

**PyQGIS Best Practices (Per Cookbook):**
1. **Layer Creation**: Always use proper URI format for memory layers
   ```python
   layer = QgsVectorLayer("Point?crs=EPSG:4326", "layer_name", "memory")
   ```

2. **Feature Handling**: Use QgsFeature properly with geometry and attributes
   ```python
   feature = core.QgsFeature()
   feature.setGeometry(core.QgsGeometry.fromPointXY(point))
   feature.setAttributes([value1, value2])
   ```

3. **Data Provider Operations**: Use dataProvider() for field and feature management
   ```python
   provider = layer.dataProvider()
   provider.addAttributes([core.QgsField("name", QVariant.String)])
   layer.updateFields()
   ```

4. **Geometry Operations**: Leverage QgsGeometry methods for spatial operations
   ```python
   geom = feature.geometry()
   buffered = geom.buffer(100, 8)  # 100 units, 8 segments
   ```

5. **Processing Integration**: Use processing.run() for complex operations
   ```python
   result = processing.run("native:buffer", {
       'INPUT': layer,
       'DISTANCE': 100,
       'OUTPUT': 'memory:'
   })
   ```

6. **Error Handling**: Always check for valid objects and handle exceptions
   ```python
   if layer and layer.isValid():
       # Perform operations
   else:
       print("Layer is not valid")
   ```

7. **CRS Management**: Handle coordinate reference systems properly
   ```python
   crs = core.QgsCoordinateReferenceSystem("EPSG:4326")
   transform = core.QgsCoordinateTransform(source_crs, dest_crs, project)
   ```

**Advanced Patterns from Cookbook:**

**Custom Expressions**: Register custom expression functions
**Map Tools**: Create interactive map tools for user input
**Symbols and Renderers**: Custom styling and categorized renderers
**Layout Management**: Programmatic map composition and export
**Plugin Development**: Hook into QGIS plugin architecture
**Server Plugins**: Extend QGIS Server functionality

**Field Type Constants (Use These for QgsField):**
- String fields: `QVariant.String`
- Integer fields: `QVariant.Int`
- Double fields: `QVariant.Double`
- Date fields: `QVariant.Date`

**Common Cookbook Patterns:**

1. **Iterate Features**: 
   ```python
   for feature in layer.getFeatures():
       # Process feature
   ```

2. **Spatial Selection**:
   ```python
   request = core.QgsFeatureRequest().setFilterRect(extent)
   features = layer.getFeatures(request)
   ```

3. **Attribute Updates**:
   ```python
   with layer.edit():
       for feature in layer.getFeatures():
           feature.setAttribute(field_index, new_value)
           layer.updateFeature(feature)
   ```

4. **Layer Styling**:
   ```python
   symbol = core.QgsMarkerSymbol.createSimple({'color': 'red', 'size': '5'})
   renderer = core.QgsSingleSymbolRenderer(symbol)
   layer.setRenderer(renderer)
   ```

**Proactive Development Approach:**
- Make reasonable assumptions for ambiguous requests
- Create memory layers for temporary results
- Provide working examples that demonstrate cookbook concepts
- Suggest follow-up actions after successful code execution
- Always explain the PyQGIS concepts being used

**Iterative Development:**
- If "Previous Script Content" is provided in the context, your task is to modify or improve that script based on the user's new request.
- Do not just provide a snippet; provide the complete, updated script that can be executed.
- For example, if the previous script created a layer, and the user now asks to "change its color to red", you should provide the full script including layer creation and the new styling code.

**Debugging and Refinement:**
- If "Last Execution Log" is provided, it contains the output or error from the previous script execution.
- Analyze this log to understand what went wrong or what the output was.
- Your primary goal is to fix any errors reported in the log or to modify the script based on the output and the user's new request.
- Provide a complete, corrected, and executable script. Do not just explain the error.

**Safety and Best Practices:**
- Validate layer existence and validity before operations
- Use edit sessions for layer modifications
- Handle coordinate system transformations correctly
- Provide informative error messages
- Warn about potentially destructive operations

Remember: You're following the official PyQGIS Developer Cookbook patterns and best practices. Your code should be production-ready and demonstrate proper PyQGIS usage as documented in the official QGIS documentation.
"""

    def set_api_key(self, api_key):
        """Set and save the Gemini API key"""
        self.api_key = api_key
        self.settings.setValue("qgis_copilot/api_key", api_key)
    
    def set_model(self, model_name):
        """Set and save the Gemini model"""
        if model_name in self.AVAILABLE_MODELS:
            self.model = model_name
            self.settings.setValue("qgis_copilot/gemini_model", model_name)
    
    def get_api_key(self):
        """Get the stored API key"""
        return self.settings.value("qgis_copilot/api_key", "")
    
    def send_message(self, message, context=None):
        """Send a message to Gemini API with QGIS context"""
        if not self.api_key:
            self.error_occurred.emit("No API key configured")
            return
        
        # Prepare the request
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        
        # Prepare user content with context
        user_content = message
        if context:
            user_content = f"Current QGIS Context:\n{context}\n\nUser Question: {message}"
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": user_content
                        }
                    ]
                }
            ],
            "system_instruction": {
                "parts": [
                    {"text": self.system_prompt}
                ]
            },
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
                if project.title():
                    context_info.append(f"Project Title: {project.title()}")
                context_info.append(f"Project CRS: {project.crs().authid()}")

            active_layer = iface.activeLayer()
            if active_layer:
                context_info.append(f"Active Layer: {active_layer.name()} ({active_layer.type().name})")
                if hasattr(active_layer, 'featureCount'):
                    context_info.append(f"Feature Count: {active_layer.featureCount()}")
                if hasattr(active_layer, 'selectedFeatureCount'):
                    selected_count = active_layer.selectedFeatureCount()
                    if selected_count > 0:
                        context_info.append(f"Selected Features: {selected_count}")

            canvas = iface.mapCanvas()
            if canvas:
                extent = canvas.extent()
                context_info.append(f"Map Extent: {extent.toString()}")
                context_info.append(f"Map CRS: {canvas.mapSettings().destinationCrs().authid()}")
                context_info.append(f"Map Scale: 1:{canvas.scale():,.0f}")

            if project:
                layers = project.mapLayers().values()
                context_info.append(f"Total Layers: {len(layers)}")

                layer_types = {l_type.name: 0 for l_type in QgsMapLayer.LayerType.values()}
                for layer in layers:
                    layer_types[layer.type().name] += 1

                type_summary = ", ".join([f"{count} {l_type}" for l_type, count in layer_types.items() if count > 0])
                if type_summary:
                    context_info.append(f"Layer Types: {type_summary}")

            return "\n".join(context_info)
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting context: {str(e)}",
                "QGIS Copilot",
                level=Qgis.Warning
            )
            return "Context information unavailable"
