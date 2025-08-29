"""
QGIS Copilot Plugin Initialization
"""

def classFactory(iface):
    """Load QGISCopilotPlugin class from file copilot_plugin.
    
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .copilot_plugin import QGISCopilotPlugin
    return QGISCopilotPlugin(iface)