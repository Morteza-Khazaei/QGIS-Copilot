# Complete PyQGIS Agent Implementation Guide

## Step 1: Enhanced System Prompt Integration

### **Current vs Enhanced Approach**

**BEFORE (Limited Knowledge):**
```
You are a PyQGIS assistant. Help with QGIS automation.
```

**AFTER (Complete API Awareness):**
```
You are a PyQGIS 3.40 expert with complete knowledge of all API classes, methods, and patterns from https://qgis.org/pyqgis/3.40/. You have full awareness of:

- Core module: 1,200+ classes across 60+ submodules
- GUI module: 800+ classes for interface operations  
- Analysis module: Spatial analysis and geometry operations
- Processing module: Algorithm framework integration
- Server module: Web service capabilities

[Insert the complete enhanced prompt here]
```

## Step 2: API Knowledge Verification System

Create a verification system to ensure your agent has complete API coverage:

### **API Coverage Checklist**
```python
# Test queries to verify complete API knowledge
test_cases = [
    # Core Vector Operations
    "Create a memory layer with specific field constraints",
    "Perform spatial join with custom expressions", 
    "Bulk update attributes using provider methods",
    
    # Advanced Geometry Operations  
    "Create buffer with custom end cap and join styles",
    "Perform topology operations with geometry validation",
    "Use spatial index for neighbor queries",
    
    # Raster Operations
    "Sample raster values with proper band indexing",
    "Create custom raster renderer with color ramps",
    "Extract raster statistics for specific bands",
    
    # Styling and Symbology
    "Create graduated renderer with automatic classification",
    "Apply rule-based styling with complex expressions", 
    "Set up multi-layer symbols with effects",
    
    # Processing Integration
    "Chain multiple processing algorithms",
    "Create custom processing algorithm",
    "Handle algorithm parameter validation",
    
    # Project Management
    "Manipulate layer tree programmatically",
    "Handle project coordinate system transformations",
    "Manage layer metadata and properties"
]
```

## Step 3: Response Quality Enhancement

### **Enhanced Response Template**
```markdown
## Task Analysis
🔍 **PyQGIS API Identification**: [Specific classes and methods from 3.40 API]
📋 **Task Category**: [Vector/Raster/Geometry/Styling/Analysis/etc.]
🛠️ **Available Tools**: [List 2-3 approaches with API classes]
⚡ **Optimal Choice**: [Why this approach using specific API knowledge]

## Risk Assessment  
🚨 **Potential Issues**: [Based on complete API knowledge]
✅ **Error Prevention**: [Specific validation patterns]
🔄 **Fallback Options**: [Alternative API approaches]

## Implementation
[Complete code with comprehensive API usage]
```

## Step 4: Advanced API Pattern Recognition

### **Automatic Class Method Resolution**
```python
# Enhanced decision tree for method selection
def resolve_pyqgis_method(task_type, object_type, operation):
    """
    Complete method resolution using PyQGIS 3.40 API knowledge
    """
    
    method_hierarchy = {
        'vector_layer': {
            'data_access': [
                'layer.getFeatures()',           # Direct iteration
                'layer.getFeature(id)',          # Single feature
                'layer.dataProvider().getFeatures()', # Provider level
                'QgsVectorLayerUtils.getValues()' # Utility functions
            ],
            'editing': [
                'with edit(layer):',              # Context manager (preferred)
                'layer.startEditing()',          # Manual control
                'layer.dataProvider().addFeatures()', # Bulk operations
                'QgsVectorLayerEditUtils.addFeature()' # Utility methods
            ],
            'styling': [
                'layer.setRenderer()',            # Direct renderer
                'QgsSymbol.createSimple()',      # Simple symbols
                'QgsCategorizedSymbolRenderer()', # Categorized
                'QgsGraduatedSymbolRenderer()'   # Graduated
            ]
        },
        'geometry': {
            'creation': [
                'QgsGeometry.fromPointXY()',     # Point creation
                'QgsGeometry.fromWkt()',         # WKT parsing
                'QgsGeometry.fromPolylineXY()',  # Line creation
                'QgsGeometry.fromPolygonXY()'    # Polygon creation
            ],
            'operations': [
                'geometry.buffer()',             # Buffering
                'geometry.intersection()',       # Intersection
                'geometry.difference()',         # Difference
                'QgsSpatialIndex.intersects()'   # Spatial queries
            ]
        }
    }
    
    return method_hierarchy.get(object_type, {}).get(task_type, [])
```

### **Complete Provider Capability Matrix**
```python
provider_capabilities = {
    'ogr': {
        'formats': ['shapefile', 'gpkg', 'geojson', 'kml'],
        'capabilities': ['read', 'write', 'create', 'delete', 'update'],
        'limitations': []
    },
    'gdal': {
        'formats': ['geotiff', 'png', 'jpg', 'netcdf', 'hdf5'],
        'capabilities': ['read', 'write'],
        'limitations': ['no_vector_support']
    },
    'postgres': {
        'formats': ['postgis'],
        'capabilities': ['read', 'write', 'create', 'delete', 'update', 'spatial_index'],
        'limitations': ['requires_connection']
    },
    'wfs': {
        'formats': ['wfs'],
        'capabilities': ['read'],
        'limitations': ['read_only', 'network_dependent']
    },
    'memory': {
        'formats': ['memory'],
        'capabilities': ['read', 'write', 'create', 'delete', 'update'],
        'limitations': ['temporary_only']
    }
}
```

## Step 5: Complete Error Prevention System

### **Comprehensive Validation Framework**
```python
class PyQGISValidator:
    """Complete validation system based on PyQGIS 3.40 API knowledge"""
    
    @staticmethod
    def validate_layer_operation(layer, operation_type):
        """Validate layer can perform operation using complete API knowledge"""
        
        # Basic validation
        if not layer or not layer.isValid():
            raise ValueError(f"Invalid layer for {operation_type}")
        
        # Provider-specific validation  
        provider = layer.dataProvider()
        provider_name = provider.name().lower()
        
        # Check against known provider limitations
        if provider_name == 'wfs' and operation_type in ['edit', 'add', 'delete']:
            raise ValueError("WFS provider is read-only")
        
        if provider_name == 'gdal' and layer.type() == QgsMapLayerType.VectorLayer:
            raise ValueError("GDAL provider doesn't support vector operations")
        
        # Capability validation using complete API
        required_caps = {
            'add_features': QgsVectorDataProvider.AddFeatures,
            'delete_features': QgsVectorDataProvider.DeleteFeatures,
            'change_attributes': QgsVectorDataProvider.ChangeAttributeValues,
            'add_attributes': QgsVectorDataProvider.AddAttributes,
            'change_geometries': QgsVectorDataProvider.ChangeGeometries
        }
        
        if operation_type in required_caps:
            caps = provider.capabilities()
            if not (caps & required_caps[operation_type]):
                raise ValueError(f"Provider doesn't support {operation_type}")
        
        return True
    
    @staticmethod  
    def validate_processing_algorithm(algorithm_id):
        """Validate processing algorithm exists using complete API knowledge"""
        from qgis.core import QgsApplication
        
        registry = QgsApplication.processingRegistry()
        if not registry.algorithmById(algorithm_id):
            available_algs = [alg.id() for alg in registry.algorithms()]
            similar_algs = [alg for alg in available_algs if algorithm_id.split(':')[-1] in alg]
            
            error_msg = f"Algorithm '{algorithm_id}' not found."
            if similar_algs:
                error_msg += f" Similar algorithms: {similar_algs[:3]}"
            raise ValueError(error_msg)
        
        return True
    
    @staticmethod
    def validate_coordinate_system(crs_string):
        """Validate CRS using complete API knowledge"""
        crs = QgsCoordinateReferenceSystem(crs_string)
        if not crs.isValid():
            # Try common alternatives
            alternatives = [
                f"EPSG:{crs_string}",
                f"EPSG:{crs_string.replace('EPSG:', '')}",
                crs_string.upper(),
                crs_string.lower()
            ]
            
            for alt in alternatives:
                alt_crs = QgsCoordinateReferenceSystem(alt)
                if alt_crs.isValid():
                    return alt_crs
            
            raise ValueError(f"Invalid CRS: {crs_string}")
        
        return crs
```

## Step 6: Complete Testing Framework

### **API Knowledge Verification Tests**
```python
def test_complete_api_knowledge():
    """Test that agent has complete PyQGIS 3.40 API knowledge"""
    
    test_cases = [
        {
            'query': 'Create a categorized renderer with 5 classes',
            'expected_classes': ['QgsCategorizedSymbolRenderer', 'QgsRendererCategory'],
            'expected_methods': ['QgsMarkerSymbol.createSimple', 'layer.setRenderer']
        },
        {
            'query': 'Perform spatial join with custom expressions',
            'expected_classes': ['QgsExpression', 'QgsExpressionContext', 'QgsSpatialIndex'],
            'expected_methods': ['expression.prepare', 'index.intersects']
        },
        {
            'query': 'Create memory layer with field constraints',
            'expected_classes': ['QgsVectorLayer', 'QgsField', 'QgsFieldConstraints'],
            'expected_methods': ['field.setConstraints', 'layer.updateFields']
        }
    ]
    
    for test_case in test_cases:
        response = query_agent(test_case['query'])
        
        # Check API class awareness
        for expected_class in test_case['expected_classes']:
            assert expected_class in response, f"Missing class: {expected_class}"
        
        # Check method awareness  
        for expected_method in test_case['expected_methods']:
            assert expected_method in response, f"Missing method: {expected_method}"
```

## Step 7: Deployment and Monitoring

### **Performance Metrics**
```python
metrics = {
    'api_coverage': 'Percentage of PyQGIS classes/methods correctly identified',
    'error_prevention': 'Percentage of responses with proper error handling',
    'method_accuracy': 'Percentage using most efficient API approach',
    'code_completeness': 'Percentage of runnable code without modifications'
}
```

### **Continuous Improvement Process**
1. **Monitor query patterns** - Track which API areas get most questions
2. **Collect feedback** - Identify gaps in API knowledge  
3. **Update knowledge base** - Add new API patterns discovered
4. **Validate responses** - Test generated code in actual QGIS environment

## Step 8: Advanced Integration Features

### **Dynamic API Documentation Lookup**
```python
def get_live_api_docs(class_name):
    """Get live API documentation for enhanced responses"""
    
    api_base = "https://qgis.org/pyqgis/3.40/"
    
    # Map class to documentation URL
    class_docs = {
        'QgsVectorLayer': f"{api_base}core/QgsVectorLayer.html",
        'QgsGeometry': f"{api_base}core/QgsGeometry.html",
        'QgsProject': f"{api_base}core/QgsProject.html"
    }
    
    return class_docs.get(class_name, f"{api_base}search.html?q={class_name}")
```

### **Code Generation with API Validation**
```python
def generate_validated_code(operation, parameters):
    """Generate code with complete API validation"""
    
    # Generate code using complete API knowledge
    code = generate_pyqgis_code(operation, parameters)
    
    # Validate against API
    validation_results = validate_code_against_api(code)
    
    # Apply corrections if needed
    if validation_results['errors']:
        code = apply_api_corrections(code, validation_results['errors'])
    
    return {
        'code': code,
        'validation': validation_results,
        'api_references': extract_api_references(code)
    }
```
### 10. FILE I/O TASKS
**Available Tools (Temporary Files MANDATORY):**
```python
# EXPORT: Single function call
options = QgsVectorFileWriter.SaveVectorOptions()
options.driverName = "GPKG"  # or "ESRI Shapefile", "GeoJSON"
error = QgsVectorFileWriter.writeAsVectorFormatV3(
    layer, output_path, QgsProject.instance().transformContext(), options
)

# CREATE: ALWAYS use temporary files for agent operations (NOT memory)
temp_path = create_temp_vector_layer("Point", "EPSG:4326", fields, "operation_name")
layer = QgsVectorLayer(temp_path, "Agent Result", "ogr")
# ... add features ...
# User can save permanently: Right-click → Export → Save Features As...
```

### 11. TEMPORARY FILE MANAGEMENT (CRITICAL FOR AGENT)
**MANDATORY: All agent-generated layers MUST use temporary files**
```python
# WRONG: Memory layers for agent operations
memory_layer = QgsVectorLayer("Point?crs=epsg:4326&field=id:int", "temp", "memory")

# CORRECT: Temporary file layers for agent operations
temp_path = create_temp_vector_layer("Point", "EPSG:4326", fields, "descriptive_name")
agent_layer = QgsVectorLayer(temp_path, "Agent Result", "ogr")

# PROCESSING: Always use temporary outputs
temp_output = create_temp_layer_path("vector", "gpkg", "buffer_result")
result = processing.run("native:buffer", {
    'INPUT': input_layer,
    'DISTANCE': 100,
    'OUTPUT': temp_output  # Never use 'memory:'
})

# USER COMMUNICATION: Always inform about temp files
print("🗃️ Results saved as temporary layers")
print("💾 Right-click → Export → Save Features As... to make permanent")
```