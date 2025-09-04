"""
QGIS Copilot Plugin - Main Plugin File
"""

import os
from qgis.PyQt.QtCore import QTranslator, QCoreApplication, QSettings, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsApplication
from .copilot_chat_dialog import CopilotChatDialog


class QGISCopilotPlugin:
    """QGIS Copilot Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.
        
        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        
        # Initialize plugin directory
        locale = QgsApplication.locale()
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            f'QGISCopilot_{locale}.qm'
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr('&QGIS Copilot')
        self.first_start = None
        self.dialog = None
        self.qml_dock = None

    def tr(self, message):
        """Get the translation for a string using Qt translation API."""
        return QCoreApplication.translate('QGISCopilot', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
        """Add a toolbar icon to the toolbar."""
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)
        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = os.path.join(self.plugin_dir, 'figures/copilot.png')
        
        self.add_action(
            icon_path,
            text=self.tr('Open QGIS Copilot'),
            callback=self.run,
            parent=self.iface.mainWindow(),
            status_tip=self.tr('Chat with your QGIS Copilot assistant'),
            whats_this=self.tr('Opens the QGIS Copilot chat interface for natural language GIS operations'))

        # Experimental QML chat panel (lazy-imported on demand to avoid QtQuick dependency at startup)
        self.add_action(
            icon_path,
            text=self.tr('Open Copilot QML Chat (experimental)'),
            callback=self.open_qml_chat,
            parent=self.iface.mainWindow(),
            status_tip=self.tr('Opens the QML-based chat dock for Copilot'),
            whats_this=self.tr('Experimental QML chat panel with bubbles, timestamps, and hover actions'))

        # Will be set False in run()
        self.first_start = True

        # Auto-open on startup if configured
        settings = QSettings()
        if settings.value("qgis_copilot/prefs/open_on_startup", True, type=bool):
            # Use a timer to ensure the QGIS GUI is fully loaded before docking
            QTimer.singleShot(200, self.run)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr('&QGIS Copilot'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""
        
        # Create dialog once
        if self.first_start:
            self.first_start = False
            self.dialog = CopilotChatDialog(self.iface)
            # Open as a dock by default so users can drag/resize like other panels
            try:
                self.dialog.on_dock_copilot_panel()
                return
            except Exception:
                pass

        # If Copilot is docked, just show/raise the dock and return without modal exec
        try:
            dock = getattr(self.dialog, '_copilot_main_dock', None)
            if dock is not None:
                dock.show()
                try:
                    dock.raise_()
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Check if any API key is configured
        try:
            if (not self.dialog.gemini_api.get_api_key() and
                not self.dialog.openai_api.get_api_key() and
                not self.dialog.claude_api.get_api_key()):
                QMessageBox.information(
                    self.iface.mainWindow(),
                    "Welcome to QGIS Copilot!",
                    "Welcome to QGIS Copilot! To get started, please configure an API key (e.g., for Google Gemini, OpenAI, or Anthropic Claude) in the AI tab."
                )
        except Exception:
            pass

        # Show as modal dialog when not docked
        self.dialog.show()
        try:
            self.dialog.exec_()
        except Exception:
            # Fallback: non-modal if exec_ not appropriate
            pass

    def open_qml_chat(self):
        """Open the experimental QML chat dock and wire it to the existing dialog/executor."""
        # Ensure the main dialog exists so we can reuse its executor/context
        try:
            if not self.dialog:
                self.run()
        except Exception:
            pass
        try:
            # Lazy import to avoid ModuleNotFoundError when QtQuick is missing
            if not self.qml_dock:
                try:
                    from .qml_chat_dock import QMLChatDock  # noqa: F401
                except Exception as e:
                    from qgis.PyQt.QtWidgets import QMessageBox
                    QMessageBox.warning(self.iface.mainWindow(), 'QML Chat', f'Qt Quick is not available in this QGIS build.\\n{e}')
                    return
                from .qml_chat_dock import QMLChatDock
                self.qml_dock = QMLChatDock(self.iface, self.dialog)
            self.qml_dock.show()

            # Mirror chat messages into the dock
            try:
                if hasattr(self.dialog, 'chat_message_added'):
                    # Avoid multiple connections by trying a blind disconnect
                    try:
                        self.dialog.chat_message_added.disconnect()
                    except Exception:
                        pass
                    self.dialog.chat_message_added.connect(lambda role, text, ts: self.qml_dock.append_message(role, text, ts))
            except Exception:
                pass

            # Mirror executor logs into the dock as system messages
            try:
                execu = getattr(self.dialog, 'pyqgis_executor', None)
                if execu and hasattr(execu, 'logs_updated'):
                    try:
                        execu.logs_updated.disconnect()
                    except Exception:
                        pass
                    execu.logs_updated.connect(lambda text: self.qml_dock.append_message('system', text, ''))
            except Exception:
                pass

            # Keep AI model and provider names in sync for the QML dock header
            try:
                # Initial apply
                name = None
                try:
                    model = getattr(self.dialog.current_api, 'model', None)
                    if model:
                        name = str(model)
                except Exception:
                    pass
                if not name:
                    name = getattr(self.dialog, 'current_api_name', '') or 'AI'
                if hasattr(self.qml_dock, 'set_ai_model_name'):
                    self.qml_dock.set_ai_model_name(name)

                # Update on provider/model changes
                try:
                    self.dialog.api_provider_combo.currentTextChanged.connect(lambda v: (
                        self.qml_dock.set_ai_model_name(getattr(self.dialog.current_api, 'model', None) or v),
                        hasattr(self.qml_dock, 'set_ai_provider_name') and self.qml_dock.set_ai_provider_name(v)
                    ))
                except Exception:
                    pass
                try:
                    self.dialog.model_selection_combo.currentTextChanged.connect(lambda v: self.qml_dock.set_ai_model_name(v or getattr(self.dialog, 'current_api_name', 'AI')))
                except Exception:
                    pass
                # Initial provider set
                try:
                    if hasattr(self.qml_dock, 'set_ai_provider_name'):
                        self.qml_dock.set_ai_provider_name(getattr(self.dialog, 'current_api_name', 'AI'))
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
