"""
Ollama (Local) API Integration for QGIS Copilot
"""

import json
import requests
from qgis.PyQt.QtCore import QSettings, QObject, pyqtSignal, QThread
from qgis.core import QgsMessageLog, Qgis, QgsProject, QgsMapLayer


class OllamaAPI(QObject):
    """Handle Ollama local API communication"""

    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    # A small, sensible default set; users can run any local model
    AVAILABLE_MODELS = [
        "gpt-oss:20b",
        "llama3.1:8b",
        "llama3.1:70b",
        "mistral",
    ]

    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        # No API key required for local Ollama
        self.api_key = ""
        self.model = self.settings.value("qgis_copilot/ollama_model", self.AVAILABLE_MODELS[0])
        # Allow overriding base URL if needed, default local daemon
        self.base_url = self.settings.value("qgis_copilot/ollama_base_url", "http://localhost:11434")

        # Load system prompt from plugin root, prefer v3.5 then v3.4
        try:
            import os
            plugin_root = os.path.dirname(__file__)
            loaded = False
            for fname in ("qgis_agent_v3.5.md", "qgis_agent_v3.4.md"):
                prompt_path = os.path.join(plugin_root, fname)
                if os.path.exists(prompt_path):
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        self.system_prompt = f.read()
                    loaded = True
                    break
            if not loaded:
                raise FileNotFoundError("No agent prompt file found")
        except Exception:
            # Minimal fallback; do not embed the full agent here
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

    # API-key methods are no-ops to fit existing UI flows
    def set_api_key(self, api_key):
        self.api_key = ""  # ignored

    def get_api_key(self):
        return ""

    def set_model(self, model_name):
        self.model = model_name
        self.settings.setValue("qgis_copilot/ollama_model", model_name)

    def set_base_url(self, url):
        """Set and save the Ollama base URL (e.g., http://localhost:11434)"""
        self.base_url = url
        self.settings.setValue("qgis_copilot/ollama_base_url", url)

    def get_base_url(self):
        return self.base_url

    def list_models(self):
        """Query the local Ollama daemon for available models.

        Returns a list of model names or raises an exception.
        """
        url = f"{self.base_url.rstrip('/')}/api/tags"
        # Keep this snappy so the UI can fail fast if daemon is down
        resp = requests.get(url, timeout=(3.0, 5.0))
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama tags API error {resp.status_code}: {resp.text}")
        data = resp.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return models

    class _Worker(QThread):
        """Background worker to call Ollama without blocking UI."""
        result = pyqtSignal(str)
        failed = pyqtSignal(str)

        def __init__(self, base_url, payload, timeout_connect=5.0, timeout_read=120.0):
            super().__init__()
            self.base_url = base_url.rstrip('/')
            self.payload = payload
            self.timeout = (timeout_connect, timeout_read)

        def run(self):
            try:
                # Choose endpoint based on payload shape
                is_chat = isinstance(self.payload, dict) and 'messages' in self.payload
                endpoint = "/api/chat" if is_chat else "/api/generate"
                url = f"{self.base_url}{endpoint}"
                resp = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=self.payload,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = None
                    if is_chat and isinstance(data.get("message"), dict):
                        content = data.get("message", {}).get("content")
                    if not content:
                        content = data.get("response")
                    if content and isinstance(content, str) and content.strip():
                        self.result.emit(content.strip())
                    else:
                        try:
                            # Log raw response for debugging
                            QgsMessageLog.logMessage(
                                f"Ollama returned empty content. Raw keys: {list(data.keys())}",
                                "QGIS Copilot",
                                level=Qgis.Warning,
                            )
                        except Exception:
                            pass
                        # Fallback: if chat returned empty, try generate once
                        if is_chat:
                            try:
                                # Build a generate payload from chat messages
                                msgs = self.payload.get('messages', [])
                                sys_msg = next((m.get('content') for m in msgs if m.get('role') == 'system'), None)
                                user_msg = next((m.get('content') for m in reversed(msgs) if m.get('role') == 'user'), None)
                                gen_payload = {
                                    'model': self.payload.get('model'),
                                    'prompt': user_msg or '',
                                    'system': sys_msg or '',
                                    'stream': False,
                                    'options': self.payload.get('options', {}),
                                }
                                gen_resp = requests.post(
                                    f"{self.base_url}/api/generate",
                                    headers={"Content-Type": "application/json"},
                                    json=gen_payload,
                                    timeout=self.timeout,
                                )
                                if gen_resp.status_code == 200:
                                    gen_data = gen_resp.json()
                                    gen_content = (gen_data.get('response') or '').strip()
                                    if gen_content:
                                        self.result.emit(gen_content)
                                    else:
                                        self.failed.emit("No response generated by Ollama.")
                                else:
                                    self.failed.emit(f"API Error {gen_resp.status_code}: {gen_resp.text}")
                            except Exception:
                                self.failed.emit("No response generated by Ollama.")
                        else:
                            self.failed.emit("No response generated by Ollama.")
                else:
                    # Provide friendlier messages for common issues
                    txt = resp.text
                    if resp.status_code == 404 and 'model' in txt.lower():
                        self.failed.emit("Model not found on Ollama. Pull it with 'ollama run <model>' or select another model.")
                    else:
                        self.failed.emit(f"API Error {resp.status_code}: {txt}")
            except requests.exceptions.ConnectTimeout:
                self.failed.emit("Connection to Ollama timed out. Is the daemon running at the configured Base URL?")
            except requests.exceptions.ReadTimeout:
                self.failed.emit("Ollama took too long to respond. Try a smaller model or reduce num_predict.")
            except Exception as e:
                self.failed.emit(f"Request to Ollama failed: {str(e)}")

    def send_message(self, message, context=None):
        """Send a message to local Ollama using a background thread."""
        user_content = message
        if context:
            user_content = f"Current QGIS Context:\n{context}\n\nUser Question: {message}"

        # Send exactly like the working curl example: chat with a single user message
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": user_content}
            ],
            "stream": False,
        }

        # Launch in a worker to avoid blocking the UI thread
        worker = OllamaAPI._Worker(self.base_url, payload, timeout_connect=5.0, timeout_read=180.0)
        # Ensure worker object survives until finished by attaching to self
        self._current_worker = worker
        worker.result.connect(self.response_received.emit)
        worker.failed.connect(self.error_occurred.emit)
        worker.finished.connect(lambda: setattr(self, "_current_worker", None))
        worker.start()

    def get_qgis_context(self, iface):
        """Extract current QGIS context information (same shape as other providers)."""
        try:
            context_info = []
            project = QgsProject.instance()
            if project:
                context_info.append(f"Project: {project.fileName() or 'Unsaved Project'}")
                if project.title():
                    context_info.append(f"Project Title: {project.title()}")
                context_info.append(f"Project CRS: {project.crs().authid()}")

            if iface:
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

                try:
                    layer_types = {l_type.name: 0 for l_type in QgsMapLayer.LayerType.values()}
                    for layer in layers:
                        layer_types[layer.type().name] += 1
                    type_summary = ", ".join([f"{count} {l_type}" for l_type, count in layer_types.items() if count > 0])
                    if type_summary:
                        context_info.append(f"Layer Types: {type_summary}")
                except Exception:
                    pass

            return "\n".join(context_info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error getting context: {str(e)}", "QGIS Copilot", level=Qgis.Warning)
            return "Context information unavailable"

    def test_model(self, on_result=None, on_error=None, prompt: str = None):
        """Quickly test the currently selected Ollama model.

        Runs a small non-blocking generation to verify that the daemon and model
        are responsive. Calls the provided callbacks in the GUI thread.
        """
        test_prompt = prompt or "Connection test successful!"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": test_prompt}
            ],
            "stream": False,
        }
        worker = OllamaAPI._Worker(self.base_url, payload, timeout_connect=5.0, timeout_read=30.0)
        self._current_worker = worker

        if on_result:
            worker.result.connect(on_result)
        else:
            worker.result.connect(self.response_received.emit)
        if on_error:
            worker.failed.connect(on_error)
        else:
            worker.failed.connect(self.error_occurred.emit)
        worker.finished.connect(lambda: setattr(self, "_current_worker", None))
        worker.start()

    def chat_once(self, prompt: str, model: str = None, timeout: int = 30):
        """Send a single chat-style request synchronously for diagnostics.

        Returns (ok: bool, message: str).
        """
        use_model = model or self.model
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": use_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        try:
            resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)
            if resp.status_code != 200:
                return False, f"Chat request failed ({resp.status_code}): {resp.text}"
            data = resp.json()
            content = (data.get("message", {}) or {}).get("content", "").strip()
            if not content:
                return False, "Empty response from model"
            return True, content
        except requests.exceptions.Timeout:
            return False, "Chat request timed out (model may be loading)"
        except Exception as e:
            return False, f"Chat test failed: {e}"
