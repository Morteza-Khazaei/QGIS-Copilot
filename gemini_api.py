"""
Google Gemini API Integration for QGIS Copilot
"""

import json
import requests
from qgis.PyQt.QtCore import QSettings, QObject, pyqtSignal
from qgis.core import QgsMessageLog, Qgis, QgsProject


class GeminiAPI(QObject):
    """Handle Google Gemini API communication"""
    
    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.api_key = self.settings.value("qgis_copilot/api_key", "")
        self.model = "gemini-1.5-flash"
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
- Include necessary imports
- Provide executable, working code
- Consider error handling when appropriate

Available QGIS context:
- iface: QgsInterface object for GUI interaction
- QgsProject.instance(): Current project
- QgsApplication.instance(): QGIS application
- All qgis.core, qgis.gui, and qgis.analysis modules are available

Always prioritize safe operations and warn about potentially destructive actions.
Be conversational and helpful - you're a copilot, not just a code generator.
"""

    def set_api_key(self, api_key):
        """Set and save the Gemini API key"""
        self.api_key = api_key
        self.settings.setValue("qgis_copilot/api_key", api_key)
    
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
            
            # Current project info
            project = QgsProject.instance()
            if project:
                context_info.append(f"Project: {project.fileName()}")
                context_info.append(f"Project Title: {project.title()}")
                context_info.append(f"Project CRS: {project.crs().authid()}")
            
            # Active layer info
            active_layer = iface.activeLayer()
            if active_layer:
                context_info.append(f"Active Layer: {active_layer.name()} ({active_layer.type()})")
                if hasattr(active_layer, 'featureCount'):
                    context_info.append(f"Feature Count: {active_layer.featureCount()}")
                if hasattr(active_layer, 'selectedFeatures'):
                    selected_count = len(active_layer.selectedFeatures())
                    if selected_count > 0:
                        context_info.append(f"Selected Features: {selected_count}")
            
            # Map canvas info
            canvas = iface.mapCanvas()
            extent = canvas.extent()
            context_info.append(f"Map Extent: {extent.toString()}")
            context_info.append(f"Map CRS: {canvas.mapSettings().destinationCrs().authid()}")
            context_info.append(f"Map Scale: {canvas.scale():,.0f}")
            
            # Layer count and types
            layers = project.mapLayers()
            context_info.append(f"Total Layers: {len(layers)}")
            
            # Layer types summary
            layer_types = {}
            for layer in layers.values():
                layer_type = str(layer.type())
                layer_types[layer_type] = layer_types.get(layer_type, 0) + 1
            
            if layer_types:
                type_summary = ", ".join([f"{count} {type}" for type, count in layer_types.items()])
                context_info.append(f"Layer Types: {type_summary}")
            
            return "\n".join(context_info)
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting context: {str(e)}", 
                "QGIS Copilot", 
                level=Qgis.Warning
            )
            return "Context information unavailable"