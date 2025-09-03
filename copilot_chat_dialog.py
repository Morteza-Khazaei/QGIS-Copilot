"""
Enhanced QGIS Copilot Chat Dialog - With execution logging and AI feedback loop
"""

import os
import json
import re
import html
from datetime import datetime
from qgis.PyQt.QtCore import Qt, QUrl, QTimer, QSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QLineEdit,
    QPushButton, QToolButton, QMenu, QSplitter, QLabel, QCheckBox, QGroupBox, QLayout,
    QMessageBox, QTabWidget, QWidget, QTextBrowser, QProgressBar, QFileDialog, QComboBox,
    QToolTip, QDockWidget, QSizePolicy
)
from qgis.PyQt.QtGui import QTextCursor, QCursor, QDesktopServices, QFont, QTextDocument, QGuiApplication
from qgis.core import QgsMessageLog, Qgis, QgsApplication

from .gemini_api import GeminiAPI
from .openai_api import OpenAIAPI
from .claude_api import ClaudeAPI
from .ollama_api import OllamaAPI
from .pyqgis_executor import EnhancedPyQGISExecutor
from . import web_kb


class CopilotChatDialog(QDialog):
    """Main dialog for QGIS Copilot chat interface"""
    
    def __init__(self, iface, parent=None):
        super(CopilotChatDialog, self).__init__(parent)
        self.iface = iface
        self.chat_history = []
        self.last_response = None
        self.auto_feedback_enabled = False
        self._normal_geometry = None  # used to restore size after fullscreen
        # Initialize API handlers
        self.gemini_api = GeminiAPI()
        self.openai_api = OpenAIAPI()
        self.claude_api = ClaudeAPI()
        self.ollama_api = OllamaAPI()
        # Order providers with Ollama first so it's the default in the UI
        self.api_handlers = {
            "Ollama (Local)": self.ollama_api,
            "Google Gemini": self.gemini_api,
            "OpenAI ChatGPT": self.openai_api,
            "Anthropic Claude": self.claude_api,
        }
        # Default to Ollama's prompt unless a custom prompt is saved
        self.default_system_prompt = self.ollama_api.system_prompt

        # Enable minimize/maximize buttons on the dialog
        try:
            self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
        except Exception:
            pass

        self.setup_ui()
        # Set a reasonable default size and minimum size for responsiveness
        self.resize(1000, 700)
        self.setMinimumSize(600, 500)

        # Select saved provider or default to Ollama (Local)
        try:
            settings = QSettings()
            saved_provider = settings.value("qgis_copilot/provider", "Ollama (Local)")
            if saved_provider in self.api_handlers:
                self.api_provider_combo.setCurrentText(saved_provider)
            else:
                self.api_provider_combo.setCurrentText("Ollama (Local)")
        except Exception:
            # Fall back silently if settings are unavailable
            self.api_provider_combo.setCurrentText("Ollama (Local)")

        # Set current API and update related UI
        self.current_api_name = self.api_provider_combo.currentText()
        self.current_api = self.api_handlers[self.current_api_name]
        try:
            self.update_api_settings_ui()
        except Exception:
            pass

        # Initialize enhanced executor
        self.pyqgis_executor = EnhancedPyQGISExecutor(iface)

        # Connect signals
        self.connect_signals()

        # Load API key for the default provider
        self.load_current_api_key()
        self.load_system_prompt()
        self.load_workspace_dir()
        self.load_preferences()
        
        # Timer for delayed AI feedback
        self.feedback_timer = QTimer()
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.request_ai_improvement)
        self.pending_failed_execution = None
        # Docked code editor (Copilot) tracking
        self._code_editor_dock = None
        self._code_editor_widget = None
        self._last_saved_task_path = None
        # Track save-prompting per task file
        self._last_prompted_task_file = None
        # Track last saved script path for Execute Last Code
        self._last_saved_task_path = None
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("QGIS Copilot")
        
        # Main layout
        main_layout = QVBoxLayout()

        # Top-right window controls (only if native buttons are unavailable)
        flags = self.windowFlags()
        has_native_minmax = bool(flags & Qt.WindowMinimizeButtonHint) or bool(flags & Qt.WindowMaximizeButtonHint)
        if not has_native_minmax:
            controls_layout = QHBoxLayout()
            controls_layout.addStretch()
            self.minimize_button = QPushButton("Minimize")
            self.minimize_button.setToolTip("Minimize this window")
            self.minimize_button.clicked.connect(self.minimize_window)
            self.fullscreen_button = QPushButton("Fullscreen")
            self.fullscreen_button.setToolTip("Toggle fullscreen")
            self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
            controls_layout.addWidget(self.minimize_button)
            controls_layout.addWidget(self.fullscreen_button)
            main_layout.addLayout(controls_layout)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Chat tab
        chat_widget = self.create_chat_tab()
        self.tab_widget.addTab(chat_widget, "Chat")
        
        # AI tab (provider, keys, model, prompt)
        ai_widget = self.create_ai_settings_tab()
        self.tab_widget.addTab(ai_widget, "AI")

        # Settings tab (workspace, execution prefs)
        settings_widget = self.create_settings_tab()
        self.tab_widget.addTab(settings_widget, "Settings")
        
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

        # Allow the dialog to be resizable by setting the layout's size constraint
        self.layout().setSizeConstraint(QLayout.SetNoConstraint)

    def minimize_window(self):
        """Minimize the dialog window."""
        try:
            self.showMinimized()
        except Exception:
            pass

    def toggle_fullscreen(self):
        """Toggle fullscreen mode for the dialog window."""
        try:
            if self.isFullScreen():
                self.showNormal()
                if self._normal_geometry:
                    self.restoreGeometry(self._normal_geometry)
                if hasattr(self, 'fullscreen_button'):
                    self.fullscreen_button.setText("Fullscreen")
            else:
                self._normal_geometry = self.saveGeometry()
                self.showFullScreen()
                if hasattr(self, 'fullscreen_button'):
                    self.fullscreen_button.setText("Exit Fullscreen")
        except Exception:
            pass
    
    def create_chat_tab(self):
        """Create the main chat interface tab"""
        chat_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create splitter (single pane now; logs go to QGIS Log Messages)
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - Chat interface
        chat_container = QWidget()
        chat_layout = QVBoxLayout()
        
        # Chat display area (fully resizable)
        self.chat_display = QTextBrowser()
        try:
            self.chat_display.setMinimumHeight(0)
            self.chat_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        self.setup_chat_display_style()
        chat_layout.addWidget(self.chat_display)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Ask your QGIS Copilot anything...")
        self.message_input.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        
        # Retry button: disabled until a failure happens
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self.on_retry_clicked)
        self.retry_button.setToolTip("Ask AI to fix the last failed run and retry")
        try:
            self.retry_button.setEnabled(False)
        except Exception:
            pass

        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        input_layout.addWidget(self.retry_button)
        
        chat_layout.addLayout(input_layout)
        
        # Preferences have been moved to Settings tab to reduce chat clutter
        
        # Chat management buttons
        chat_management_layout = QHBoxLayout()
        
        clear_all_button = QPushButton("Clear All")
        clear_all_button.setToolTip("Clear chat history and live logs")
        clear_all_button.clicked.connect(self.clear_all)

        chat_management_layout.addWidget(clear_all_button)
        chat_management_layout.addStretch()
        chat_layout.addLayout(chat_management_layout)
        
        chat_container.setLayout(chat_layout)
        splitter.addWidget(chat_container)
        
        # Right-side live log panel removed — logs now go to QGIS Log Messages
        
        # Set splitter behavior
        try:
            splitter.setChildrenCollapsible(False)
        except Exception:
            pass
        
        layout.addWidget(splitter)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        chat_widget.setLayout(layout)
        return chat_widget
    
    # Logs tab removed; live logs are displayed within the Chat tab
    
    def create_settings_tab(self):
        """Create the non-AI settings tab (workspace, execution prefs)"""
        settings_widget = QWidget()
        layout = QVBoxLayout()
        # Tighten overall vertical rhythm on Settings tab
        try:
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
        except Exception:
            pass

        # Workspace settings
        workspace_group = QGroupBox("Workspace (Script Save Location)")
        ws_layout = QVBoxLayout()
        try:
            ws_layout.setContentsMargins(8, 8, 8, 8)
            ws_layout.setSpacing(6)
        except Exception:
            pass
        ws_layout.addWidget(QLabel("Choose where QGIS Copilot saves and runs generated Python scripts:"))
        
        ws_row = QHBoxLayout()
        try:
            ws_row.setContentsMargins(0, 0, 0, 0)
            ws_row.setSpacing(6)
        except Exception:
            pass
        self.workspace_dir_input = QLineEdit()
        self.workspace_dir_input.setPlaceholderText("Select a folder to store generated scripts...")
        ws_browse_btn = QPushButton("Browse…")
        ws_browse_btn.clicked.connect(self.browse_workspace_dir)
        ws_open_btn = QPushButton("Open Folder")
        ws_open_btn.clicked.connect(self.open_workspace_dir)
        ws_save_btn = QPushButton("Save")
        ws_save_btn.clicked.connect(self.save_workspace_dir)
        ws_row.addWidget(self.workspace_dir_input)
        ws_row.addWidget(ws_browse_btn)
        ws_row.addWidget(ws_open_btn)
        ws_row.addWidget(ws_save_btn)
        ws_layout.addLayout(ws_row)

        ws_hint = QLabel("If unset, Copilot defaults to a 'workspace' folder inside the plugin directory.")
        ws_hint.setWordWrap(True)
        ws_layout.addWidget(ws_hint)

        workspace_group.setLayout(ws_layout)
        layout.addWidget(workspace_group)

        # Chat and Execution Preferences
        prefs_group = QGroupBox("Chat and Execution Preferences")
        prefs_layout = QVBoxLayout()
        try:
            prefs_layout.setContentsMargins(8, 8, 8, 8)
            prefs_layout.setSpacing(6)
        except Exception:
            pass

        # Organized grid for checkboxes (2 columns)
        grid = QGridLayout()
        try:
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(4)
        except Exception:
            pass

        # Chat context options (left column)
        self.include_context_cb = QCheckBox("Include QGIS Context")
        self.include_logs_cb = QCheckBox("Include Execution Logs in Context")
        self.include_logs_cb.setToolTip("Send recent execution logs to AI for better context")
        grid.addWidget(self.include_context_cb, 0, 0)
        grid.addWidget(self.include_logs_cb, 1, 0)

        # Startup behavior
        self.open_on_startup_cb = QCheckBox("Open panel on QGIS startup")
        self.open_on_startup_cb.setToolTip("Automatically open and dock the Copilot panel when QGIS starts.")
        grid.addWidget(self.open_on_startup_cb, 2, 0)

        # Execution behavior options (right column)
        self.auto_execute_cb = QCheckBox("Auto-execute Code")
        self.auto_feedback_cb = QCheckBox("Auto Request Improvements on Errors")
        self.auto_feedback_cb.setToolTip("Automatically ask AI to improve code when execution fails")
        self.auto_feedback_cb.toggled.connect(self.on_auto_feedback_toggled)
        grid.addWidget(self.auto_execute_cb, 0, 1)
        grid.addWidget(self.auto_feedback_cb, 1, 1)

        # Advanced: Relax safety checks (dangerous)
        self.relaxed_safety_cb = QCheckBox("Relax Safety Checks (advanced)")
        self.relaxed_safety_cb.setToolTip("Allows more operations in generated scripts (still blocks exec/eval/subprocess). Use with caution.")
        grid.addWidget(self.relaxed_safety_cb, 2, 1)

        # Console execution option spans both columns
        self.run_in_console_cb = QCheckBox("Run via QGIS Python Console (open editor + exec)")
        self.run_in_console_cb.setToolTip("Writes code to a file in your Workspace, opens it in the QGIS Python Editor, then executes it for native logging/tracebacks.")
        grid.addWidget(self.run_in_console_cb, 3, 0, 1, 2)

        # Include docs summary option
        self.include_docs_cb = QCheckBox("Include PyQGIS Docs Summary in Context")
        self.include_docs_cb.setToolTip("Scrapes the PyQGIS Developer Cookbook and adds a brief, relevant summary to the AI context.")
        grid.addWidget(self.include_docs_cb, 4, 0, 1, 2)

        prefs_layout.addLayout(grid)
        prefs_group.setLayout(prefs_layout)
        layout.addWidget(prefs_group)

        settings_widget.setLayout(layout)
        return settings_widget

    def create_ai_settings_tab(self):
        """Create a dedicated AI settings tab (provider, keys, model, prompt)"""
        ai_widget = QWidget()
        layout = QVBoxLayout()

        # API Provider selection
        provider_group = QGroupBox("API Provider")
        provider_layout = QVBoxLayout()
        provider_layout.addWidget(QLabel("Select your preferred AI provider:"))
        self.api_provider_combo = QComboBox()
        self.api_provider_combo.addItems(self.api_handlers.keys())
        provider_layout.addWidget(self.api_provider_combo)
        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # API Key section
        self.api_group = QGroupBox("API Configuration")
        api_layout = QVBoxLayout()

        self.api_key_label = QLabel("API Key:")
        api_layout.addWidget(self.api_key_label)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        api_layout.addWidget(self.api_key_input)

        api_button_layout = QHBoxLayout()

        self.save_key_button = QPushButton("Save API Key")
        self.save_key_button.clicked.connect(self.save_api_key)
        
        self.test_key_button = QPushButton("Test API Key")
        self.test_key_button.clicked.connect(self.test_api_key)
        
        api_button_layout.addWidget(self.save_key_button)
        api_button_layout.addWidget(self.test_key_button)
        api_button_layout.addStretch()

        api_layout.addLayout(api_button_layout)

        # Instructions
        self.instructions_label = QLabel()
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setOpenExternalLinks(True)
        api_layout.addWidget(self.instructions_label)

        self.api_group.setLayout(api_layout)
        layout.addWidget(self.api_group)

        # Ollama-specific configuration (shown only when provider is Ollama)
        self.ollama_group = QGroupBox("Ollama Configuration")
        ollama_layout = QVBoxLayout()
        ollama_layout.addWidget(QLabel("Base URL (daemon):"))
        self.ollama_base_url_input = QLineEdit()
        self.ollama_base_url_input.setPlaceholderText("http://localhost:11434")
        self.ollama_base_url_input.setText(self.ollama_api.get_base_url())
        ollama_layout.addWidget(self.ollama_base_url_input)

        ollama_btn_row = QHBoxLayout()
        self.ollama_save_url_btn = QPushButton("Save Base URL")
        self.ollama_save_url_btn.clicked.connect(self.on_save_ollama_base_url)
        self.ollama_check_btn = QPushButton("Check Connection")
        self.ollama_check_btn.clicked.connect(self.on_check_ollama_connection)
        self.ollama_refresh_models_btn = QPushButton("Refresh Models")
        self.ollama_refresh_models_btn.clicked.connect(self.on_refresh_ollama_models)
        ollama_btn_row.addWidget(self.ollama_save_url_btn)
        ollama_btn_row.addWidget(self.ollama_check_btn)
        ollama_btn_row.addWidget(self.ollama_refresh_models_btn)
        ollama_btn_row.addStretch()
        ollama_layout.addLayout(ollama_btn_row)

        self.ollama_group.setLayout(ollama_layout)
        layout.addWidget(self.ollama_group)

        # Model settings
        model_group = QGroupBox("Model Settings")
        model_layout = QVBoxLayout()

        model_layout.addWidget(QLabel("Select AI Model:"))
        self.model_selection_combo = QComboBox()
        model_layout.addWidget(self.model_selection_combo)

        model_info_label = QLabel("Select the AI model to use. If you get 'model not found' errors, try a different model. `gpt-4o` is recommended for OpenAI.")
        model_info_label.setWordWrap(True)
        model_layout.addWidget(model_info_label)

        # Test selected model (primarily for Ollama)
        test_row = QHBoxLayout()
        self.test_model_button = QPushButton("Test Selected Model")
        self.test_model_button.clicked.connect(self.on_test_ollama_model)
        test_row.addWidget(self.test_model_button)
        test_row.addStretch()
        model_layout.addLayout(test_row)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # System Prompt settings
        prompt_group = QGroupBox("System Prompt (Agent Behavior)")
        prompt_layout = QVBoxLayout()

        prompt_info_label = QLabel("This is the core instruction set for the AI agent. Edit with caution.")
        prompt_info_label.setWordWrap(True)
        prompt_layout.addWidget(prompt_info_label)

        # Prompt file controls
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Prompt File (Markdown):"))
        self.system_prompt_file_input = QLineEdit()
        self.system_prompt_file_input.setReadOnly(True)
        file_row.addWidget(self.system_prompt_file_input)
        browse_prompt_btn = QPushButton("Change…")
        browse_prompt_btn.clicked.connect(self.browse_system_prompt_file)
        open_prompt_btn = QPushButton("Open File")
        open_prompt_btn.clicked.connect(self.open_system_prompt_file)
        file_row.addWidget(browse_prompt_btn)
        file_row.addWidget(open_prompt_btn)
        prompt_layout.addLayout(file_row)

        # Prompt editor: single scrollbar inside the editor, buttons remain outside
        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setAcceptRichText(False)
        try:
            self.system_prompt_input.setMinimumHeight(60)
            self.system_prompt_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        self.system_prompt_input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.system_prompt_input.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        prompt_layout.addWidget(self.system_prompt_input)

        prompt_button_layout = QHBoxLayout()
        save_prompt_button = QPushButton("Save Prompt")
        save_prompt_button.clicked.connect(self.save_system_prompt)
        
        reset_prompt_button = QPushButton("Reset to Default")
        reset_prompt_button.clicked.connect(self.reset_system_prompt)

        prompt_button_layout.addWidget(save_prompt_button)
        prompt_button_layout.addWidget(reset_prompt_button)
        prompt_button_layout.addStretch()
        prompt_layout.addLayout(prompt_button_layout)

        prompt_group.setLayout(prompt_layout)
        layout.addWidget(prompt_group)

        ai_widget.setLayout(layout)
        return ai_widget
    
    def setup_chat_display_style(self):
        """Setup styling for the chat display (QGIS default-like)"""
        font_size = getattr(self, 'chat_font_size', '10pt')
        self.chat_display.setStyleSheet(f"""
            QTextBrowser {{
                background-color: #ffffff;
                border: none;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: {font_size};
                padding: 8px;
                line-height: 1.4;
            }}
        """)
        try:
            # Route link clicks to our handler (for copilot:// actions)
            self.chat_display.setOpenLinks(False)
            self.chat_display.setOpenExternalLinks(False)
        except Exception:
            pass
    
    def connect_signals(self):
        """Connect all signals"""
        # API signals
        self.gemini_api.response_received.connect(self.handle_api_response)
        self.gemini_api.error_occurred.connect(self.handle_api_error)
        self.openai_api.response_received.connect(self.handle_api_response)
        self.openai_api.error_occurred.connect(self.handle_api_error)
        self.claude_api.response_received.connect(self.handle_api_response)
        self.claude_api.error_occurred.connect(self.handle_api_error)
        self.ollama_api.response_received.connect(self.handle_api_response)
        self.ollama_api.error_occurred.connect(self.handle_api_error)
        
        # Executor signals
        self.pyqgis_executor.execution_completed.connect(self.handle_execution_completed)
        self.pyqgis_executor.logs_updated.connect(self.handle_logs_updated)
        self.pyqgis_executor.improvement_suggested.connect(self.handle_improvement_suggestion)
        
        # UI signals
        self.api_provider_combo.currentTextChanged.connect(self.on_api_provider_changed)
        self.model_selection_combo.currentTextChanged.connect(self.on_model_changed)
        self.chat_display.anchorClicked.connect(self.handle_anchor_click)
    
    def on_api_provider_changed(self, provider_name):
        """Handle API provider change"""
        self.current_api_name = provider_name
        self.current_api = self.api_handlers[provider_name]
        # Persist user's provider choice
        try:
            QSettings().setValue("qgis_copilot/provider", provider_name)
        except Exception:
            pass
        self.update_api_settings_ui()
        self.load_current_api_key()

    def on_auto_feedback_toggled(self, checked):
        """Handle toggling of auto-feedback checkbox"""
        self.auto_feedback_enabled = checked

    def on_model_changed(self, model_name):
        """Handle AI model change"""
        if not model_name or self.model_selection_combo.signalsBlocked():
            return

        if hasattr(self.current_api, 'set_model'):
            self.current_api.set_model(model_name)

    def handle_anchor_click(self, url):
        """Handle clicks on links in the chat display."""
        try:
            if url.scheme().lower() == 'copilot':
                action = (url.host() or '').lower()
                # Parse query
                from qgis.PyQt.QtCore import QUrlQuery
                q = QUrlQuery(url)
                mid = int(q.queryItemValue('mid')) if q.hasQueryItem('mid') else None
                idx = int(q.queryItemValue('i')) if q.hasQueryItem('i') else 0
                if action in ('run', 'open', 'copy') and mid is not None:
                    # Resolve code block
                    code = None
                    try:
                        blocks = getattr(self, '_code_blocks_by_msg', {}).get(mid) if hasattr(self, '_code_blocks_by_msg') else None
                        if (blocks is None or idx >= len(blocks)) and 0 <= mid-1 < len(self.chat_history):
                            raw = self.chat_history[mid-1].get('message')
                            blocks = self.pyqgis_executor.extract_code_blocks(raw)
                        if blocks and idx < len(blocks):
                            code = blocks[idx]
                    except Exception:
                        code = None
                    if not code:
                        QMessageBox.information(self, 'Run Code', 'No code block found for this action.')
                        return
                    if action == 'run':
                        self.add_to_execution_results('=' * 50)
                        self.add_to_execution_results(f'Executing code block #{idx+1} from AI response (message {mid})...')
                        self.add_to_execution_results('=' * 50)
                        self.pyqgis_executor.execute_code(code)
                    elif action == 'open':
                        # Prefer opening the saved script produced when the AI replied
                        try:
                            path = getattr(self, '_last_saved_task_path', None)
                            if path and os.path.exists(path):
                                self._open_file_in_python_console_editor(path)
                                return
                        except Exception:
                            pass
                        # Fallback: open the block content in the Copilot dock editor
                        self.ensure_code_editor_dock(code)
                    elif action == 'copy':
                        try:
                            QGuiApplication.clipboard().setText(code)
                            QMessageBox.information(self, 'Copy Code', 'Code block copied to clipboard.')
                        except Exception:
                            pass
                return
        except Exception:
            pass
        # Fallback: open external links
        QDesktopServices.openUrl(url)

    def _open_file_in_python_console_editor(self, file_path: str):
        """Open a .py file in the QGIS Python Console's code editor (best-effort)."""
        try:
            # Ensure Python Console is visible
            if self.iface and hasattr(self.iface, 'actionShowPythonDialog'):
                try:
                    self.iface.actionShowPythonDialog().trigger()
                except Exception:
                    pass
            import qgis.utils as qutils
            pc = None
            if hasattr(qutils, 'plugins') and isinstance(qutils.plugins, dict):
                pc = qutils.plugins.get('PythonConsole') or qutils.plugins.get('pythonconsole')
                if not pc:
                    for k, v in qutils.plugins.items():
                        if 'python' in k.lower() and 'console' in k.lower():
                            pc = v
                            break
            # Try to show the editor pane
            for act_name in ('actionShowEditor', 'actionEditor', 'toggleEditor', 'showEditor'):
                act = getattr(pc, act_name, None)
                if act:
                    try:
                        if hasattr(act, 'setChecked'):
                            act.setChecked(True)
                        if hasattr(act, 'trigger'):
                            act.trigger()
                    except Exception:
                        pass
            # Try the common open methods
            for meth in ('openFileInEditor', 'openScriptFile', 'loadScript', 'addToEditor'):
                fn = getattr(pc, meth, None)
                if callable(fn):
                    try:
                        fn(file_path)
                        return
                    except Exception:
                        pass
            # Final fallback: run a command in the console to open it
            console = getattr(pc, 'console', None)
            if console and hasattr(console, 'runCommand'):
                fp = str(file_path).replace('\\', '/').replace("'", "\'")
                cmd = (
                    "import qgis.utils as _qutils\n"
                    "_pc = _qutils.plugins.get('PythonConsole') or _qutils.plugins.get('pythonconsole')\n"
                    "for _m in ('openFileInEditor','openScriptFile','loadScript','addToEditor'):\n"
                    "    _fn = getattr(_pc, _m, None)\n"
                    "    if callable(_fn):\n"
                    f"        _fn(r'{fp}')\n"
                    "        break\n"
                )
                try:
                    console.runCommand(cmd)
                except Exception:
                    pass
        except Exception:
            pass

    def update_api_settings_ui(self):
        """Update settings UI based on selected provider"""
        provider_name = self.api_provider_combo.currentText()
        self.api_group.setTitle(f"{provider_name} API Configuration")
        self.api_key_label.setText(f"API Key for {provider_name}:")

        # Show/hide API key controls for local providers like Ollama
        is_local = (provider_name == "Ollama (Local)")
        self.api_key_label.setVisible(not is_local)
        self.api_key_input.setVisible(not is_local)
        self.save_key_button.setVisible(not is_local)
        self.test_key_button.setVisible(not is_local)
        # Ollama config group visibility
        self.ollama_group.setVisible(is_local)

        # Disconnect signal to prevent premature firing while we update the UI
        self.model_selection_combo.blockSignals(True)
        self.model_selection_combo.clear()

        if hasattr(self.current_api, 'AVAILABLE_MODELS'):
            models = []
            # Try to fetch dynamic models for Ollama
            if is_local and hasattr(self.current_api, 'list_models'):
                try:
                    models = self.current_api.list_models()
                except Exception as e:
                    QgsMessageLog.logMessage(f"Ollama models fetch failed: {e}", "QGIS Copilot", level=Qgis.Warning)
            if not models:
                models = getattr(self.current_api, 'AVAILABLE_MODELS', [])

            self.model_selection_combo.addItems(models)
            if hasattr(self.current_api, 'model'):
                # Select current model if present
                self.model_selection_combo.setCurrentText(self.current_api.model)
            # Always show the model list for Ollama; for others, hide if only one
            if is_local:
                self.model_selection_combo.setVisible(True)
            else:
                self.model_selection_combo.setVisible(len(models) > 1)

        self.model_selection_combo.blockSignals(False)
        # Show model test only for Ollama
        try:
            self.test_model_button.setVisible(is_local)
        except Exception:
            pass
        
        if provider_name == "Google Gemini":
            self.instructions_label.setText("""
<b>Welcome to QGIS Copilot!</b><br><br>
To get started, you need a free Google Gemini API key:<br>
1. Visit <a href="https://aistudio.google.com">Google AI Studio</a><br>
2. Sign in with your Google account and create an API key.<br>
3. Enter it above and click 'Save API Key'.
            """)
        elif provider_name == "OpenAI ChatGPT":
            self.instructions_label.setText("""
<b>Using OpenAI's ChatGPT</b><br><br>
To use ChatGPT, you need an OpenAI API key:<br>
1. Visit <a href="https://platform.openai.com/api-keys">OpenAI API Keys</a>.<br>
2. Sign in and create a new secret key.<br>
3. Enter it above and click 'Save API Key'.<br><br>
<i>Note: OpenAI API usage may incur costs.</i>
            """)
        elif provider_name == "Anthropic Claude":
            self.instructions_label.setText("""
<b>Using Anthropic's Claude</b><br><br>
To use Claude, you need an Anthropic API key:<br>
1. Visit <a href="https://console.anthropic.com/keys">Anthropic Console</a>.<br>
2. Sign in and create a new API key.<br>
3. Enter it above and click 'Save API Key'.<br><br>
<i>Note: Anthropic API usage may incur costs.</i>
            """)
        elif provider_name == "Ollama (Local)":
            self.instructions_label.setText("""
<b>Using Ollama (Local)</b><br><br>
Ollama runs models locally — no API key required. Install and start Ollama, then pull a model:<br>
<code>ollama run gpt-oss:20b</code><br><br>
Tip: Ensure the Ollama daemon is running on <code>http://localhost:11434</code>. You can change the model from the list above.
            """)

    # Ollama UI actions
    def on_save_ollama_base_url(self):
        url = self.ollama_base_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a valid base URL.")
            return
        try:
            self.ollama_api.set_base_url(url)
            QMessageBox.information(self, "Saved", f"Ollama base URL set to {url}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save base URL: {e}")

    def on_check_ollama_connection(self):
        # Run a richer diagnostic, echoing to Live Logs
        try:
            self.add_to_execution_results("=== Ollama Diagnostic ===")
            try:
                self.add_to_execution_results(f"Base URL: {self.ollama_api.get_base_url()}")
            except Exception:
                pass

            # Step 1: List models
            try:
                models = self.ollama_api.list_models()
                count = len(models)
                self.add_to_execution_results(f"Models available: {count}")
                if models:
                    preview = ", ".join(models[:5])
                    self.add_to_execution_results(f"First models: {preview}")
                    # Step 2: Chat test with selected/first model
                    test_model = self.ollama_api.model if self.ollama_api.model in models else models[0]
                    self.add_to_execution_results(f"Testing chat with: {test_model}")
                    ok, msg = self.ollama_api.chat_once(
                        "Hello, please respond with 'Connection test successful!'",
                        model=test_model,
                        timeout=20,
                    )
                    if ok:
                        self.add_to_execution_results("Chat test OK.")
                        QMessageBox.information(self, "Ollama Diagnostic", f"Connected. {count} model(s). Chat OK with '{test_model}'.")
                    else:
                        self.add_to_execution_results("Chat test FAILED.")
                        self.add_to_execution_results(msg)
                        QMessageBox.warning(self, "Ollama Diagnostic", f"Connected. {count} model(s). Chat failed: {msg}")
                else:
                    self.add_to_execution_results("No models found. Pull a model, e.g., 'ollama pull llama3.1:8b'")
                    QMessageBox.warning(self, "Ollama Diagnostic", "Connected but no models found. Pull a model first.")
            except Exception as e:
                self.add_to_execution_results(f"List models failed: {e}")
                QMessageBox.critical(self, "Ollama Diagnostic", f"Connection failed: {e}")
        except Exception as e:
            try:
                QMessageBox.critical(self, "Ollama Diagnostic", f"Unexpected error: {e}")
            except Exception:
                pass

    def on_refresh_ollama_models(self):
        try:
            models = self.ollama_api.list_models()
            self.model_selection_combo.blockSignals(True)
            self.model_selection_combo.clear()
            self.model_selection_combo.addItems(models)
            # Keep current selection if possible
            if self.ollama_api.model in models:
                self.model_selection_combo.setCurrentText(self.ollama_api.model)
            self.model_selection_combo.blockSignals(False)
            QMessageBox.information(self, "Ollama Models", f"Loaded {len(models)} model(s).")
        except Exception as e:
            QMessageBox.critical(self, "Ollama Models", f"Failed to load models: {e}")

    def on_test_ollama_model(self):
        """Test the currently selected Ollama model and show results in Live Logs."""
        try:
            # Print a single configuration snapshot (matches chat request header)
            try:
                self.log_provider_and_config()
            except Exception:
                pass

            def _ok(text: str):
                try:
                    self.add_to_execution_results("Test OK — model responded.")
                except Exception:
                    pass
                try:
                    QMessageBox.information(self, "Ollama Test", "Model responded successfully.")
                except Exception:
                    pass

            def _err(err: str):
                try:
                    self.add_to_execution_results("Test Failed — see error below:")
                    self.add_to_execution_results(str(err))
                except Exception:
                    pass
                try:
                    QMessageBox.critical(self, "Ollama Test", str(err))
                except Exception:
                    pass

            self.ollama_api.test_model(on_result=_ok, on_error=_err)
        except Exception as e:
            try:
                QMessageBox.critical(self, "Ollama Test", f"Failed to start test: {e}")
            except Exception:
                pass

    def load_current_api_key(self):
        """Load saved API key for the current provider"""
        api_key = self.current_api.get_api_key()
        if api_key:
            self.api_key_input.setText(api_key)
        else:
            self.api_key_input.clear()
    
    def save_api_key(self):
        """Save the API key for the current provider"""
        api_key = self.api_key_input.text().strip()
        if api_key:
            self.current_api.set_api_key(api_key)
            QMessageBox.information(self, "Success", f"{self.current_api_name} API key saved successfully!")
        else:
            QMessageBox.warning(self, "Warning", "Please enter a valid API key.")
    
    def test_api_key(self):
        """Test the API key connection for the current provider"""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key first.")
            return
        
        self.current_api.set_api_key(api_key)
        self.show_progress(f"Testing {self.current_api_name} API key...")
        self.current_api.send_message("Hello, this is a test message. Please respond with 'API test successful!'")
    
    def send_message(self, message=None, is_programmatic=False):
        """Send a message to QGIS Copilot. Can be called programmatically."""
        if not is_programmatic:
            message = self.message_input.text().strip()
            if not message:
                return

            # Add user message to chat
            self.add_to_chat("You", message, "#007bff")

            # Clear input
            self.message_input.clear()
            # Enable Retry so user can resend the last prompt if desired
            try:
                if hasattr(self, 'retry_button') and self.retry_button:
                    self.retry_button.setEnabled(True)
            except Exception:
                pass

        # Get QGIS context if requested
        context = None
        if self.include_context_cb.isChecked():
            context = self.current_api.get_qgis_context(self.iface)

        # Add execution history context if requested
        if self.include_logs_cb.isChecked():
            log_context = self.pyqgis_executor.get_execution_context_for_ai()
            if context:
                context += "\n\n" + log_context
            else:
                context = log_context

        # Add tool-identification guidance
        try:
            guidance = (
                "Tool Identification: First list the relevant PyQGIS classes, functions, "
                "and processing algorithms needed for this task and why. Then implement the simplest, "
                "most direct approach as a single complete Python script."
            )
            if context:
                context = guidance + "\n\n" + context
            else:
                context = guidance
        except Exception:
            pass

        # Add docs summary if requested
        if self.include_docs_cb.isChecked():
            try:
                summary = web_kb.get_relevant_summary(message)
                if summary:
                    if context:
                        context += "\n\n" + summary
                    else:
                        context = summary
            except Exception:
                pass

        # Log provider and key config details before sending
        try:
            self.log_provider_and_config()
        except Exception:
            pass

        # For Ollama, don't show a blocking progress bar; others keep it
        if self.current_api_name != "Ollama (Local)":
            self.show_progress(f"Getting response from {self.current_api_name}...")

        # Send to API
        self.current_api.send_message(message, context)
    
    def load_system_prompt(self):
        """Load the system prompt from a Markdown file (preferred) or settings.

        If no file exists yet, create one with the default prompt.
        """
        settings = QSettings()
        # Determine prompt file path
        path = settings.value("qgis_copilot/system_prompt_file", type=str)
        if not path:
            plugin_root = os.path.dirname(__file__)
            # Default to the root prompt file maintained with the plugin (prefer v3.5)
            candidate = os.path.join(plugin_root, "qgis_agent_v3.5.md")
            if not os.path.exists(candidate):
                candidate = os.path.join(plugin_root, "qgis_agent_v3.4.md")
            path = candidate
            settings.setValue("qgis_copilot/system_prompt_file", path)

        # Ensure the file exists; if not, seed from any saved setting or default
        prompt_text = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    prompt_text = f.read()
            except Exception:
                prompt_text = None

        if prompt_text is None:
            # Fall back to previously saved setting, then default
            prompt_text = settings.value("qgis_copilot/system_prompt", self.default_system_prompt)
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(prompt_text or "")
            except Exception:
                # If writing fails, continue with in-memory prompt
                pass

        # Reflect file path in UI and update editor + handlers
        try:
            self.system_prompt_file_input.setText(path)
        except Exception:
            pass
        self.system_prompt_input.setText(prompt_text)
        self.update_all_system_prompts(prompt_text)

    def load_preferences(self):
        """Load chat/execution preferences from QSettings and apply defaults."""
        settings = QSettings()
        self.include_context_cb.setChecked(settings.value("qgis_copilot/prefs/include_context", True, type=bool))
        self.include_logs_cb.setChecked(settings.value("qgis_copilot/prefs/include_logs", True, type=bool))
        self.auto_execute_cb.setChecked(settings.value("qgis_copilot/prefs/auto_execute", False, type=bool))
        self.auto_feedback_cb.setChecked(settings.value("qgis_copilot/prefs/auto_feedback", False, type=bool))
        self.run_in_console_cb.setChecked(settings.value("qgis_copilot/prefs/run_in_console", True, type=bool))
        self.relaxed_safety_cb.setChecked(settings.value("qgis_copilot/prefs/relaxed_safety", False, type=bool))
        self.include_docs_cb.setChecked(settings.value("qgis_copilot/prefs/include_docs", True, type=bool))
        self.open_on_startup_cb.setChecked(settings.value("qgis_copilot/prefs/open_on_startup", True, type=bool))
        self.auto_feedback_enabled = self.auto_feedback_cb.isChecked()

        # Persist on change
        self.include_context_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/include_context", v))
        self.include_logs_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/include_logs", v))
        self.auto_execute_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/auto_execute", v))
        self.auto_feedback_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/auto_feedback", v))
        self.run_in_console_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/run_in_console", v))
        self.relaxed_safety_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/relaxed_safety", v))
        self.include_docs_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/include_docs", v))
        self.open_on_startup_cb.toggled.connect(lambda v: QSettings().setValue("qgis_copilot/prefs/open_on_startup", v))

    def load_workspace_dir(self):
        """Load the workspace directory from settings into the UI."""
        settings = QSettings()
        ws = settings.value("qgis_copilot/workspace_dir", type=str)
        if not ws:
            # Show the computed default but do not persist until user saves
            plugin_root = os.path.dirname(__file__)
            ws = os.path.join(plugin_root, "workspace")
        self.workspace_dir_input.setText(ws)

    def save_system_prompt(self):
        """Save the custom system prompt to the Markdown file and settings."""
        prompt_text = self.system_prompt_input.toPlainText()
        settings = QSettings()
        # Always persist to settings for backward compatibility
        settings.setValue("qgis_copilot/system_prompt", prompt_text)
        # Write to file
        path = settings.value("qgis_copilot/system_prompt_file", type=str)
        if not path:
            plugin_root = os.path.dirname(__file__)
            candidate = os.path.join(plugin_root, "qgis_agent_v3.5.md")
            if not os.path.exists(candidate):
                candidate = os.path.join(plugin_root, "qgis_agent_v3.4.md")
            path = candidate
            settings.setValue("qgis_copilot/system_prompt_file", path)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(prompt_text)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to write prompt file: {e}")
        # Update all handlers
        self.update_all_system_prompts(prompt_text)
        QMessageBox.information(self, "Success", "System prompt saved to Markdown file.")

    def save_workspace_dir(self):
        """Persist the workspace directory to settings and ensure it exists."""
        path = self.workspace_dir_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Warning", "Please select a valid folder for the workspace.")
            return
        try:
            os.makedirs(path, exist_ok=True)
            settings = QSettings()
            settings.setValue("qgis_copilot/workspace_dir", path)
            QMessageBox.information(self, "Success", f"Workspace saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save workspace: {e}")

    def browse_workspace_dir(self):
        """Open a folder picker to choose the workspace directory."""
        current = self.workspace_dir_input.text().strip()
        folder = QFileDialog.getExistingDirectory(self, "Select Workspace Folder", current or os.path.expanduser("~"))
        if folder:
            self.workspace_dir_input.setText(folder)

    def open_workspace_dir(self):
        """Open the current workspace directory in the system file browser."""
        path = self.workspace_dir_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Warning", "Workspace folder is empty. Save a valid path first.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def reset_system_prompt(self):
        """Reset the system prompt to its default value."""
        reply = QMessageBox.question(self, 'Confirm Reset',
                                     "Are you sure you want to reset the system prompt to its default value?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return

        self.system_prompt_input.setText(self.default_system_prompt)
        settings = QSettings()
        settings.setValue("qgis_copilot/system_prompt", self.default_system_prompt)
        # Overwrite the file with the default prompt too
        path = settings.value("qgis_copilot/system_prompt_file", type=str)
        if path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.default_system_prompt)
            except Exception:
                pass
        self.update_all_system_prompts(self.default_system_prompt)
        QMessageBox.information(self, "Success", "System prompt has been reset and saved to file.")

    def update_all_system_prompts(self, prompt_text):
        """Update the system prompt for all API handlers."""
        for handler in self.api_handlers.values():
            handler.system_prompt = prompt_text

    def log_provider_and_config(self):
        """Write a one-shot snapshot of provider and key configuration to Live Logs."""
        try:
            self.add_to_execution_results("=== QGIS Copilot Request ===")
            self.add_to_execution_results(f"Provider: {self.current_api_name}")
            # Model if available
            try:
                model = getattr(self.current_api, 'model', None)
                if model:
                    self.add_to_execution_results(f"Model: {model}")
            except Exception:
                pass
            # Provider-specific endpoint
            try:
                if self.current_api_name == "Ollama (Local)" and hasattr(self.ollama_api, 'get_base_url'):
                    self.add_to_execution_results(f"Base URL: {self.ollama_api.get_base_url()}")
            except Exception:
                pass

            # Prompt source
            try:
                prompt_file = QSettings().value("qgis_copilot/system_prompt_file", type=str)
                if prompt_file:
                    self.add_to_execution_results(f"Prompt File: {prompt_file}")
            except Exception:
                pass

            # Preferences
            try:
                prefs = []
                prefs.append(f"Include Context: {self.include_context_cb.isChecked()}")
                prefs.append(f"Include Logs: {self.include_logs_cb.isChecked()}")
                prefs.append(f"Auto Execute: {self.auto_execute_cb.isChecked()}")
                prefs.append(f"Auto Feedback: {self.auto_feedback_cb.isChecked()}")
                prefs.append(f"Run in Console: {self.run_in_console_cb.isChecked()}")
                self.add_to_execution_results("Preferences: " + ", ".join(prefs))
            except Exception:
                pass

            # Workspace directory
            try:
                ws = QSettings().value("qgis_copilot/workspace_dir", type=str)
                if not ws:
                    plugin_root = os.path.dirname(__file__)
                    ws = os.path.join(plugin_root, "workspace")
                self.add_to_execution_results(f"Workspace: {ws}")
            except Exception:
                pass
        except Exception:
            pass

    # ---- Prompt file helpers ----
    def browse_system_prompt_file(self):
        """Let the user choose a different Markdown file for the system prompt."""
        try:
            current = self.system_prompt_file_input.text().strip()
        except Exception:
            current = ""
        from qgis.PyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Select System Prompt Markdown", current or os.path.expanduser("~"), "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)")
        if not path:
            return
        settings = QSettings()
        settings.setValue("qgis_copilot/system_prompt_file", path)
        try:
            self.system_prompt_file_input.setText(path)
        except Exception:
            pass
        # Reload content from the new file
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.system_prompt_input.setText(text)
            self.update_all_system_prompts(text)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Failed to load prompt file: {e}")

    def open_system_prompt_file(self):
        """Open the current prompt file in the system editor."""
        path = QSettings().value("qgis_copilot/system_prompt_file", type=str)
        if not path:
            QMessageBox.information(self, "Info", "No prompt file is configured.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def handle_api_response(self, response):
        """Handle response from the current API"""
        self.hide_progress()
        
        # Add response to chat
        self.add_to_chat(self.current_api_name, response, "#28a745")
        
        # Store last response for potential execution
        self.last_response = response
        # Standalone Run button removed; per-code-block Run is available in the response
        
        # Save the response code to a sticky workspace script so Execute Last Code can run it
        try:
            # Derive filename hint from last user message
            filename_hint = None
            for item in reversed(self.chat_history):
                if item.get('sender') == 'You':
                    filename_hint = (item.get('message') or '').strip().splitlines()[0][:80]
                    break
            saved_path = self.pyqgis_executor.save_response_to_task_file(response, filename_hint=filename_hint)
            self._last_saved_task_path = saved_path
            # Brief notice in logs panel
            self.add_to_execution_results(f"Saved response script: {saved_path}")
        except Exception:
            # Ignore if no code found; user can still execute normally
            pass
        
        # Do not mirror API responses to the Live Logs panel

        # Auto-execute if enabled
        if self.auto_execute_cb.isChecked():
            self.execute_code_from_response(response)
    
    def handle_api_error(self, error):
        """Handle errors from the current API"""
        self.hide_progress()

        # Try to parse for specific, user-friendly error messages
        user_friendly_error = None

        if self.current_api_name == "OpenAI ChatGPT":
            try:
                # The error string is often "API Error <code>: { ... JSON ... }"
                # Extract the JSON part
                json_str_start = error.find('{')
                if json_str_start != -1:
                    json_str = error[json_str_start:]
                    error_data = json.loads(json_str)
                    if error_data.get("error", {}).get("code") == "insufficient_quota":
                        user_friendly_error = (
                            "You have exceeded your OpenAI API quota. "
                            "Please check your plan and billing details on the OpenAI website. "
                            "You may need to add credits to your account to continue using this service."
                        )
            except (json.JSONDecodeError, IndexError):
                # Not a parsable JSON error, fall back to default
                pass
        elif self.current_api_name == "Google Gemini":
            try:
                # Gemini error strings often look like: "API Error 429: { ... JSON ... }"
                json_str_start = error.find('{')
                if json_str_start != -1:
                    json_str = error[json_str_start:]
                    data = json.loads(json_str)
                    err = data.get("error", {})
                    code = err.get("code")
                    status = err.get("status") or ""
                    message = err.get("message") or ""
                    details = err.get("details", []) or []

                    help_url = None
                    quota_value = None
                    quota_id = None
                    quota_metric = None
                    model_name = None
                    retry_after = None

                    for d in details:
                        t = d.get("@type", "")
                        if t.endswith("google.rpc.Help"):
                            links = d.get("links", [])
                            if links:
                                help_url = links[0].get("url")
                        elif t.endswith("google.rpc.QuotaFailure"):
                            vios = d.get("violations", [])
                            if vios:
                                v = vios[0]
                                quota_metric = v.get("quotaMetric")
                                quota_id = v.get("quotaId")
                                quota_value = v.get("quotaValue")
                                dims = v.get("quotaDimensions", {})
                                model_name = dims.get("model") or model_name
                        elif t.endswith("google.rpc.RetryInfo"):
                            retry_after = d.get("retryDelay")

                    # Compose a friendlier message
                    if code == 429 or status == "RESOURCE_EXHAUSTED":
                        parts = []
                        parts.append("You've hit a Google Gemini rate/quota limit.")
                        if model_name:
                            parts.append(f"Model: {model_name}.")
                        if quota_value:
                            parts.append(f"Daily free-tier limit: {quota_value} requests.")
                        if retry_after:
                            parts.append(f"Retry available in {retry_after}.")
                        if message:
                            parts.append(message)
                        if help_url:
                            parts.append(f"<a href=\"{help_url}\">Learn more about Gemini API quotas</a>.")
                        user_friendly_error = " ".join(parts)
                    elif message:
                        # Default to the server-provided message with any help link
                        suffix = f" <a href=\"{help_url}\">More info</a>." if help_url else ""
                        user_friendly_error = f"{message}{suffix}"
            except (json.JSONDecodeError, IndexError, TypeError):
                # Not a parsable JSON error, fall back to default
                pass
        elif self.current_api_name == "Anthropic Claude":
            pass  # Can add specific Claude error parsing here in the future
        
        final_error_message = user_friendly_error if user_friendly_error else error
        self.add_to_chat("System", f"Error from {self.current_api_name}: {final_error_message}", "#dc3545")
        QgsMessageLog.logMessage(f"QGIS Copilot API Error ({self.current_api_name}): {error}", "QGIS Copilot", level=Qgis.Critical)
        # Do not mirror API errors to the Live Logs panel
    
    # Removed: execute_last_code — replaced by per-code-block Run actions in chat
    
    def execute_code_from_response(self, response):
        """Execute code blocks found in the response"""
        self.add_to_execution_results("=" * 50)
        self.add_to_execution_results("Executing code from QGIS Copilot response...")
        self.add_to_execution_results("=" * 50)
        
        # Derive a filename hint from the last user message (task name)
        filename_hint = None
        try:
            for item in reversed(self.chat_history):
                if item.get('sender') == 'You':
                    # Use up to 80 chars of the user message as the filename hint
                    filename_hint = (item.get('message') or '').strip().splitlines()[0][:80]
                    break
        except Exception:
            filename_hint = None
        
        # Choose execution route
        if self.run_in_console_cb.isChecked():
            self.pyqgis_executor.execute_response_via_console(response, filename_hint=filename_hint)
        else:
            self.pyqgis_executor.execute_gemini_response(response, filename_hint=filename_hint)

    def handle_execution_completed(self, result_message, success, execution_log):
        """Handle the completion of a code execution."""
        # Notify in chat with a brief summary so the user sees outcomes inline
        summary_color = "#28a745" if success else "#dc3545"
        status_text = "succeeded" if success else "failed"
        self.add_to_chat(
            "System",
            f"Code execution {status_text}. See Log Messages panel for details.",
            summary_color,
        )

        # If execution failed, optionally trigger auto-feedback
        if not success:
            self.pending_failed_execution = execution_log
            if self.auto_feedback_enabled:
                # Delay to allow user to see the error before AI responds
                self.feedback_timer.start(1500)
            try:
                if hasattr(self, 'retry_button') and self.retry_button:
                    self.retry_button.setEnabled(True)
            except Exception:
                pass
        else:
            # On success, clear any previous failure; keep Retry enabled so user can retry query
            self.pending_failed_execution = None
            # Removed redundant post-success save prompt; script is already saved once per response

    def handle_logs_updated(self, formatted_log_entry):
        """Append new log entry to the live display."""
        self.add_to_execution_results(formatted_log_entry)

    def handle_improvement_suggestion(self, original_code, suggestion_prompt):
        self.add_to_chat("System", "Requesting improvement for the last failed script...", "#6c757d")
        self.send_message(message=suggestion_prompt, is_programmatic=True)
    
    def add_to_chat(self, sender, message, color):
        """Add a message to the chat display and history"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Store in history
        msg_id = (self.chat_history[-1]['id'] + 1) if self.chat_history else 1
        entry = {
            "sender": sender,
            "message": message,
            "color": color,
            "timestamp": timestamp,
            "id": msg_id,
        }
        self.chat_history.append(entry)
        # Cache code blocks for AI messages for per-block actions
        try:
            if sender not in ("You", "System"):
                if not hasattr(self, '_code_blocks_by_msg'):
                    self._code_blocks_by_msg = {}
                # Use auto-fenced markdown so unfenced scripts are detected as blocks
                fenced = None
                try:
                    fenced = self.auto_fence_code_blocks(message)
                except Exception:
                    fenced = message
                blocks = self.pyqgis_executor.extract_code_blocks(fenced or message)
                self._code_blocks_by_msg[msg_id] = blocks or []
        except Exception:
            pass
        
        # Add to display with the current message id available for header actions
        try:
            self._current_render_msg_id = msg_id
        except Exception:
            pass
        self.render_message(sender, message, color, timestamp)
        try:
            del self._current_render_msg_id
        except Exception:
            pass

    def render_message(self, sender, message, color, timestamp):
        """Render a single chat message using Qt's native Markdown support when appropriate."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        # Ensure a blank line separates every message
        try:
            if self.chat_display.toPlainText().strip():
                cursor.insertText("\n\n")
        except Exception:
            pass

        is_user = (sender == "You")
        is_system = (sender == "System")
        align = "right" if is_user else "left"

        # Bubble palettes (enhanced)
        if is_user:
            bubble_bg_color = "#e3f2fd"
            bubble_border_color = "#90caf9"
            bubble_shadow = "0 2px 4px rgba(25, 118, 210, 0.1)"
        elif is_system:
            bubble_bg_color = "#f5f5f5"
            bubble_border_color = "#e0e0e0"
            bubble_shadow = "0 1px 3px rgba(0, 0, 0, 0.1)"
        else:
            bubble_bg_color = "#f1f8e9"
            bubble_border_color = "#aed581"
            bubble_shadow = "0 2px 4px rgba(76, 175, 80, 0.1)"

        # Build content using Markdown for AI messages by default; fallback heuristic otherwise
        ai_message = (not is_user and not is_system)
        try:
            is_md = True if ai_message else (self.looks_like_markdown(message) if isinstance(message, str) else False)
        except Exception:
            is_md = ai_message

        formatted_content = None
        if is_md:
            try:
                # Auto-fence obvious code blocks so they render as code
                fenced_md = self.auto_fence_code_blocks(message)

                # Replace fenced blocks with stable placeholders so we can inject styled HTML later
                code_blocks = []
                def _sub_fence(m):
                    code = m.group(1)
                    code_blocks.append(code)
                    idx = len(code_blocks) - 1
                    return f"\nCOPILOT_CODE_BLOCK_{idx}__TOKEN__\n"

                import re as _re
                fenced_with_tokens = _re.sub(r"```(?:[a-zA-Z0-9_-]+)?\s*\n([\s\S]*?)\n```", _sub_fence, fenced_md)

                # Render Markdown normally
                temp_doc = QTextDocument()
                temp_doc.setMarkdown(fenced_with_tokens)
                html_content = temp_doc.toHtml()
                html_content = self.extract_body_content(html_content)

                # Apply general styling but disable its fallback appender (we will inject inline via tokens)
                mid = getattr(self, '_current_render_msg_id', None)
                if mid is None and self.chat_history:
                    try:
                        mid = self.chat_history[-1].get('id')
                    except Exception:
                        mid = None
                styled_html = self.style_markdown_html(html_content, mid=mid, use_fallback=False)

                # Build styled sections for each token and replace in place
                for i, cb in enumerate(code_blocks):
                    # Create the styled block (same visuals as primary path)
                    import html as _html
                    esc = _html.escape(cb)
                    run_href = f"copilot://run?mid={mid}&i={i}" if mid is not None else None
                    open_href = f"copilot://open?mid={mid}&i={i}" if mid is not None else None
                    copy_href = f"copilot://copy?mid={mid}&i={i}" if mid is not None else None
                    def _btn(href, bg, brd, label):
                        if not href:
                            return ''
                        return (
                            f'<a href="{href}" style="background:{bg}; color:#ffffff; padding:3px 6px; '
                            f'border-radius:4px; text-decoration:none; font-size:8pt; font-weight:500; border:1px solid {brd};">{label}</a>'
                        )
                    actions = (
                        _btn(run_href, '#28a745', '#1e7e34', '▶ Run') + '&nbsp;'
                        + _btn(copy_href, '#6c757d', '#545b62', '📋 Copy') + '&nbsp;'
                        + _btn(open_href, '#007bff', '#0056b3', '📝 Editor')
                    )
                    title = f'PyQGIS Code Block #{i+1}'
                    header = (
                        '<div style="background:linear-gradient(135deg,#f5f5f5 0%,#e9ecef 100%); color:#000000; padding:6px 10px; '
                        'border:1px solid #cccccc; border-bottom:none; border-top-left-radius:8px; border-top-right-radius:8px; '
                        'font-weight:bold; font-family:\'Segoe UI\', sans-serif; font-size:9pt;">'
                        '<table style="width:100%; border-collapse:collapse;" cellspacing="0" cellpadding="0">'
                        '<tr>'
                        f'<td style="vertical-align:middle;">{title}</td>'
                        f'<td style="vertical-align:middle; font-weight:normal;" align="right">{actions}</td>'
                        '</tr>'
                        '</table>'
                        '</div>'
                    )
                    pre = (
                        '<pre style="background-color:#1a1a1a; color:#f0f0f0; border:1px solid #333; padding:12px; '
                        'border-radius:0px; border-bottom-left-radius:8px; border-bottom-right-radius:8px; margin:0; '
                        'white-space:pre-wrap; word-break:break-word; font-family:Consolas,Monaco,Menlo,monospace; font-size:9pt; overflow-x:auto;">'
                        f'<code style="color:#f0f0f0; background:transparent; border:none; padding:0;">{esc}</code>'
                        '</pre>'
                    )
                    styled_section = (
                        f'<div style="margin:12px 0; border-radius:8px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.08);">{header}{pre}</div>'
                    )

                    token = f'COPILOT_CODE_BLOCK_{i}__TOKEN__'
                    # Prefer replacing a whole paragraph containing the token
                    styled_html, _n = _re.subn(rf'<p[^>]*>\s*{_re.escape(token)}\s*</p>', styled_section, styled_html, flags=_re.IGNORECASE)
                    if _n == 0:
                        # Fall back to a plain string replace
                        styled_html = styled_html.replace(token, styled_section)

                formatted_content = styled_html
            except Exception:
                formatted_content = None
        if not formatted_content:
            try:
                import html as _html
                formatted_content = _html.escape(str(message)).replace('\n', '<br>')
            except Exception:
                formatted_content = str(message)

        # Enhanced message bubble with header separator and shadow
        html = f"""
        <div style="margin: 8px 5px; text-align: {align};">
          <div style="display: inline-block; text-align: left; max-width: 90%; padding: 12px 16px; border-radius: 16px; background-color: {bubble_bg_color}; border: 1px solid {bubble_border_color}; box-shadow: {bubble_shadow}; margin: 8px 0; font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;">
            <div style="margin-bottom: 8px; border-bottom: 1px solid {bubble_border_color}; padding-bottom: 6px;">
              <strong style="color: {color}; font-size: 11pt;">{sender}</strong>
              <span style="color: #6c757d; font-size: 9pt; margin-left: 8px;">({timestamp})</span>
            </div>
            <div style="line-height: 1.5; color: #2c3e50;">
              {formatted_content}
            </div>
          </div>
        </div>
        """

        cursor.insertHtml(html)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def looks_like_markdown(self, text):
        """Check if text contains markdown formatting indicators."""
        try:
            import re
            if not isinstance(text, str):
                return False
            patterns = [
                r'^#{1,6}\s+',          # headers
                r'\*\*.*?\*\*',       # bold
                r'\*[^\*\n].*?\*',    # italic
                r'`[^`\n]+`',           # inline code
                r'```[\s\S]*?```',     # fenced code blocks
                r'^\s*[-*+]\s+',       # unordered lists
                r'^\s*\d+\.\s+',     # ordered lists
                r'^\s*>\s+',           # blockquotes
                r'\[[^\]]+\]\([^\)]+\)',  # links
                r'^(?:---+|\*\*\*+)$', # horizontal rules
            ]
            for pat in patterns:
                if re.search(pat, text, re.MULTILINE):
                    return True
            return False
        except Exception:
            return False

    def extract_body_content(self, html_text):
        """Extract content from HTML body tag, removing document wrapper."""
        try:
            import re
            m = re.search(r'<body[^>]*>([\s\S]*?)</body>', html_text, re.IGNORECASE)
            if m:
                content = m.group(1).strip()
                # Relax paragraph margins if Qt injects them
                content = re.sub(r'<p style=\"[^\"]*\">', '<p>', content)
                return content
            return html_text
        except Exception:
            return html_text

    def auto_fence_code_blocks(self, text: str) -> str:
        """Wrap obvious code sections in fenced Markdown blocks.

        This helps when AI outputs plain code without ``` fences or 4-space indentation.
        Heuristics: detect runs of >= 3 lines where most lines look like Python code
        (imports, defs, control flow, assignments, from qgis, etc.).
        """
        try:
            if not isinstance(text, str) or not text:
                return text
            # If already contains any fenced blocks, leave as-is
            if '```' in text or '~~~' in text:
                return text

            import re
            lines = text.splitlines()
            n = len(lines)
            i = 0
            out = []
            code_mode = False
            code_buf = []

            def looks_code(line: str) -> bool:
                s = line.rstrip()
                if not s:
                    return False
                if s.startswith(('from ', 'import ', 'def ', 'class ', 'try:', 'except', 'with ', 'for ', 'while ', 'if ', 'elif ', 'else:', '#')):
                    return True
                if re.search(r"\bQgs[A-Za-z_]+\b", s):
                    return True
                if re.search(r"\biface\b|\bproject\b|\bprocessing\b", s):
                    return True
                if re.search(r"[^\s] = [^=]", s):
                    return True
                if s.endswith((':', ')')) or '(' in s or ')' in s:
                    return True
                return False

            while i < n:
                line = lines[i]
                is_code = looks_code(line)
                if not code_mode:
                    # Start a potential code block when we see a run of code-like lines
                    if is_code:
                        # Look ahead to ensure a run
                        run_len = 0
                        j = i
                        while j < n and (looks_code(lines[j]) or not lines[j].strip()):
                            if lines[j].strip():
                                run_len += 1
                            j += 1
                        if run_len >= 2:
                            # Start code mode
                            code_mode = True
                            code_buf = []
                            # ensure a blank line before fenced block
                            if out and out[-1].strip():
                                out.append("")
                            out.append("```python")
                            # do not increment i here; fall through and collect line
                        else:
                            out.append(line)
                            i += 1
                            continue
                    else:
                        out.append(line)
                        i += 1
                        continue

                if code_mode:
                    # Accumulate until the run ends (allow blank lines inside)
                    if is_code or not line.strip():
                        code_buf.append(line)
                        i += 1
                        # If next line breaks the run, close
                        if i >= n or (lines[i].strip() and not looks_code(lines[i])):
                            out.extend(code_buf)
                            out.append("```")
                            # ensure a blank line after fenced block
                            out.append("")
                            code_mode = False
                            code_buf = []
                    else:
                        # Close and reprocess this non-code line in outer loop
                        out.extend(code_buf)
                        out.append("```")
                        out.append("")
                        code_mode = False
                        code_buf = []
                        # do not increment i to re-evaluate this line as non-code
                
            # If ended while still in code mode, close it
            if code_mode and code_buf:
                out.extend(code_buf)
                out.append("```")
                out.append("")

            return "\n".join(out) if out else text
        except Exception:
            return text

    def style_markdown_html(self, html_text: str, mid: int = None, use_fallback: bool = True) -> str:
        """Lightweight inline styling for Qt Markdown HTML to improve readability.

        Ensures fenced code blocks render as black code boxes and improves spacing and
        legibility of common elements (headings, lists, tables, blockquotes, links).
        """
        try:
            import re

            def ensure_style(tag: str, base_style: str, html_in: str) -> str:
                # Merge with existing style (ours last so it wins on conflicts)
                pattern_has = rf'<{tag}([^>]*?)style="([^"]*)"([^>]*)>'
                html_out = re.sub(
                    pattern_has,
                    lambda m: f'<{tag}{m.group(1)}style="{m.group(2)}; {base_style}"{m.group(3)}>',
                    html_in,
                    flags=re.IGNORECASE,
                )
                pattern_no = rf'<{tag}(?![^>]*style=)([^>]*)>'
                html_out = re.sub(
                    pattern_no,
                    rf'<{tag} \1 style="{base_style}">',
                    html_out,
                    flags=re.IGNORECASE,
                )
                return html_out

            styled = html_text

            # Headings
            h_style = 'margin:6px 0 4px; color:#222; font-weight:600;'
            for h in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                styled = ensure_style(h, h_style, styled)

            # Paragraphs and lists
            styled = ensure_style('p', 'margin:6px 0;', styled)
            styled = ensure_style('ul', 'margin:6px 0 6px 18px;', styled)
            styled = ensure_style('ol', 'margin:6px 0 6px 18px;', styled)
            styled = ensure_style('li', 'margin:3px 0;', styled)

            # Links and images
            styled = ensure_style('a', 'color:#0b5ed7; text-decoration:underline;', styled)
            styled = ensure_style('img', 'max-width:100%; height:auto; border-radius:4px;', styled)

            # Blockquotes and rules
            styled = ensure_style('blockquote', 'border-left:4px solid #d0d7de; padding-left:10px; margin:6px 0; color:#555; background:#f8f9fa; border-radius:4px;', styled)
            styled = ensure_style('hr', 'border:none; border-top:1px solid #e0e0e0; margin:8px 0;', styled)

            # Tables
            styled = ensure_style('table', 'border-collapse:collapse; margin:6px 0; width:auto;', styled)
            styled = ensure_style('th', 'border:1px solid #ddd; padding:4px 8px; background:#f1f3f5; text-align:left;', styled)
            styled = ensure_style('td', 'border:1px solid #ddd; padding:4px 8px;', styled)

            # Code blocks and inline code (enhanced styling)
            pre_style = 'background-color:#1a1a1a; color:#f0f0f0; border:1px solid #333; padding:12px; border-radius:0px; border-bottom-left-radius:8px; border-bottom-right-radius:8px; white-space:pre-wrap; word-break:break-word; font-family:Consolas,Monaco,Menlo,monospace; font-size:9pt; margin:0; overflow-x:auto;'
            code_style = 'background:#f0f2f5; color:#c7254e; padding:2px 5px; border-radius:3px; font-family:Consolas,Monaco,Menlo,monospace; font-size:9pt; border:1px solid #e1e5e9;'
            
            # Protect <pre> blocks while styling inline <code>
            pre_blocks = []
            def _stash_pre(m):
                pre_blocks.append(m.group(0))
                return f"__PRE_BLOCK_{len(pre_blocks)-1}__"
            protected = re.sub(r'<pre[\s\S]*?</pre>', _stash_pre, styled, flags=re.IGNORECASE)

            # Style inline code (outside pre)
            protected = ensure_style('code', code_style, protected)

            # Restore pre blocks and style them as black code boxes
            def _restore_pre(m):
                idx = int(m.group(1))
                return pre_blocks[idx]
            restored = re.sub(r'__PRE_BLOCK_(\d+)__', _restore_pre, protected)
            styled = ensure_style('pre', pre_style, restored)

            # Ensure nested <code> inside <pre> inherits light text and mono font
            # Merge when style exists
            styled = re.sub(
                r'(<pre[^>]*>\s*<code[^>]*?)style="([^"]*)"([^>]*>)',
                lambda m: f"{m.group(1)}style=\"{m.group(2)}; color:#f0f0f0; background:transparent; font-family:Consolas,Monaco,Menlo,monospace; font-size:9pt; border:none; padding:0;\"{m.group(3)}",
                styled,
                flags=re.IGNORECASE,
            )
            # Add when style missing on <code> inside <pre>
            styled = re.sub(
                r'(<pre[^>]*>\s*<code)(?![^>]*style=)([^>]*>)',
                r'\1 style="color:#f0f0f0; background:transparent; font-family:Consolas,Monaco,Menlo,monospace; font-size:9pt; border:none; padding:0;"\2',
                styled,
                flags=re.IGNORECASE,
            )

            # Wrap each <pre> with a simple header bar to differentiate code visually
            # Counter for code blocks in this message
            code_idx = {'i': 0}

            def _wrap_pre(m):
                pre_html = m.group(0)
                # Ensure top corners are square so the header sits flush and remove outer margins
                pre_html = re.sub(
                    r'<pre([^>]*)style="([^"]*)"',
                    lambda mm: f'<pre{mm.group(1)}style="{mm.group(2)}; margin:0; border-top-left-radius:0; border-top-right-radius:0;"',
                    pre_html,
                    flags=re.IGNORECASE,
                )
                idx = code_idx['i']
                code_idx['i'] += 1
                # Build header with actions when a message id is provided
                if mid is not None:
                    run_href = f"copilot://run?mid={mid}&i={idx}"
                    open_href = f"copilot://open?mid={mid}&i={idx}"
                    copy_href = f"copilot://copy?mid={mid}&i={idx}"
                    def btn(href, bg, brd, label):
                        return (
                            f'<a href="{href}" '
                            f'style="background:{bg}; color:#ffffff; padding:3px 6px; '
                            f'border-radius:4px; text-decoration:none; font-size:8pt; '
                            f'font-weight:500; border:1px solid {brd};">{label}</a>'
                        )
                    actions = (
                        btn(run_href, '#28a745', '#1e7e34', '▶ Run')
                        + '&nbsp;'
                        + btn(copy_href, '#6c757d', '#545b62', '📋 Copy')
                        + '&nbsp;'
                        + btn(open_href, '#007bff', '#0056b3', '📝 Editor')
                    )
                else:
                    actions = ''
                title = f'PyQGIS Code Block #{idx+1}'
                header = (
                    '<div style="background:linear-gradient(135deg,#f5f5f5 0%,#e9ecef 100%); color:#000000; padding:6px 10px; '
                    'border:1px solid #cccccc; border-bottom:none; border-top-left-radius:8px; border-top-right-radius:8px; '
                    'font-weight:bold; font-family:\'Segoe UI\', sans-serif; font-size:9pt;">'
                    '<table style="width:100%; border-collapse:collapse;" cellspacing="0" cellpadding="0">'
                    '<tr>'
                    f'<td style="vertical-align:middle;">{title}</td>'
                    f'<td style="vertical-align:middle; font-weight:normal;" align="right">{actions}</td>'
                    '</tr>'
                    '</table>'
                    '</div>'
                )
                return f'<div style="margin:12px 0; border-radius:8px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.08);">{header}{pre_html}</div>'

            styled = re.sub(r'<pre[\s\S]*?</pre>', _wrap_pre, styled, flags=re.IGNORECASE)

            # Fallback: if Qt did not emit any <pre> blocks but we have detected code blocks,
            # replace the original unstyled code in-place with styled sections. If no in-place
            # match can be found, append styled sections at the end without removing prose.
            try:
                if use_fallback and ('<pre' not in styled.lower()) and mid is not None and hasattr(self, '_code_blocks_by_msg'):
                    blocks = self._code_blocks_by_msg.get(mid) or []
                    if blocks:
                        import html as _html, re as _re
                        remaining_to_append = []
                        for i, cb in enumerate(blocks):
                            # Build styled section for this block
                            esc = _html.escape(cb)
                            run_href = f"copilot://run?mid={mid}&i={i}"
                            open_href = f"copilot://open?mid={mid}&i={i}"
                            copy_href = f"copilot://copy?mid={mid}&i={i}"
                            def btn(href, bg, brd, label):
                                return (
                                    f'<a href="{href}" '
                                    f'style="background:{bg}; color:#ffffff; padding:3px 6px; '
                                    f'border-radius:4px; text-decoration:none; font-size:8pt; '
                                    f'font-weight:500; border:1px solid {brd};">{label}</a>'
                                )
                            actions = (
                                btn(run_href, '#28a745', '#1e7e34', '▶ Run') + '&nbsp;'
                                + btn(copy_href, '#6c757d', '#545b62', '📋 Copy') + '&nbsp;'
                                + btn(open_href, '#007bff', '#0056b3', '📝 Editor')
                            )
                            title = f'PyQGIS Code Block #{i+1}'
                            header = (
                                '<div style="background:linear-gradient(135deg,#f5f5f5 0%,#e9ecef 100%); color:#000000; padding:6px 10px; '
                                'border:1px solid #cccccc; border-bottom:none; border-top-left-radius:8px; border-top-right-radius:8px; '
                                'font-weight:bold; font-family:\'Segoe UI\', sans-serif; font-size:9pt;">'
                                '<table style="width:100%; border-collapse:collapse;" cellspacing="0" cellpadding="0">'
                                '<tr>'
                                f'<td style="vertical-align:middle;">{title}</td>'
                                f'<td style="vertical-align:middle; font-weight:normal;" align="right">{actions}</td>'
                                '</tr>'
                                '</table>'
                                '</div>'
                            )
                            pre = (
                                '<pre style="background-color:#1a1a1a; color:#f0f0f0; border:1px solid #333; padding:12px; '
                                'border-radius:0px; border-bottom-left-radius:8px; border-bottom-right-radius:8px; margin:0; '
                                'white-space:pre-wrap; word-break:break-word; font-family:Consolas,Monaco,Menlo,monospace; font-size:9pt; overflow-x:auto;">'
                                f'<code style="color:#f0f0f0; background:transparent; border:none; padding:0;">{esc}</code>'
                                '</pre>'
                            )
                            styled_section = (
                                f'<div style="margin:12px 0; border-radius:8px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.08);">{header}{pre}</div>'
                            )

                            # Try direct block replacement
                            esc_cb = esc
                            replaced = False
                            if esc_cb in styled:
                                styled = styled.replace(esc_cb, styled_section, 1)
                                replaced = True
                            else:
                                # Try <br>-joined variant replacement
                                esc_lines = [ _html.escape(l) for l in cb.splitlines() if l.strip() ]
                                if esc_lines:
                                    br_join = r'(?:\s*<br\s*/?>\s*)'
                                    pat = br_join.join(_re.escape(l) for l in esc_lines)
                                    # Allow optional wrapping tags between lines (very loose)
                                    pat = pat.replace('\n', br_join)
                                    rx = _re.compile(pat, _re.IGNORECASE)
                                    if rx.search(styled):
                                        styled = rx.sub(styled_section, styled, count=1)
                                        replaced = True
                                # As a last inline attempt: replace from the first to last non-empty line across any HTML
                                if not replaced and len(esc_lines) >= 2:
                                    head = _re.escape(esc_lines[0])
                                    tail = _re.escape(esc_lines[-1])
                                    rx2 = _re.compile(head + r'.*?' + tail, _re.IGNORECASE | _re.DOTALL)
                                    if rx2.search(styled):
                                        styled = rx2.sub(styled_section, styled, count=1)
                                        replaced = True

                            if not replaced:
                                remaining_to_append.append(styled_section)

                        if remaining_to_append:
                            # Append any blocks we couldn't replace inline
                            styled = styled + "\n" + "\n".join(remaining_to_append)
            except Exception:
                pass

            return styled
        except Exception:
            return html_text

    # Removed: save_chat and load_chat (chat file I/O no longer supported)

    def clear_chat(self, confirm=True):
        """Clear the chat history and display."""
        if confirm:
            reply = QMessageBox.question(self, 'Confirm Clear', 
                                         "Are you sure you want to clear the chat history?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return
        
        self.chat_history.clear()
        self.chat_display.clear()
        self.last_response = None
        # Standalone Run button removed; nothing to disable here
        # Disable Retry; no failed context anymore
        try:
            self.pending_failed_execution = None
            if hasattr(self, 'retry_button') and self.retry_button:
                self.retry_button.setEnabled(False)
        except Exception:
            pass

    def clear_all(self):
        """Clear both chat history and live logs in one action."""
        reply = QMessageBox.question(
            self,
            'Confirm Clear All',
            "Clear chat history and live logs? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        # Clear chat without extra confirmation
        self.clear_chat(confirm=False)

        # Clear live logs UI and internal executor history
        try:
            self.execution_display.clear()
        except Exception:
            pass
        try:
            self.pyqgis_executor.clear_history()
        except Exception:
            pass
        # Reset sticky task file so next task uses a new filename
        try:
            self.pyqgis_executor.reset_task_file()
        except Exception:
            pass
        # Ensure Retry disabled
        try:
            self.pending_failed_execution = None
            if hasattr(self, 'retry_button') and self.retry_button:
                self.retry_button.setEnabled(False)
        except Exception:
            pass

    # Removed: repopulate_chat_display (previously used by load_chat)
    
    def format_message_content(self, content):
        """Format message content with syntax highlighting for code"""
        # Replace code blocks with formatted HTML
        def format_code_block(match):
            code_to_display = html.escape(match.group(1).strip())

            # Always render code in a solid black box for contrast
            header = (
                '<div style="background-color: #000000; color: #FFFFFF; padding: 6px 10px; '
                'border: 1px solid #000; border-bottom: none; border-top-left-radius: 6px; '
                'border-top-right-radius: 6px; font-family: \'Segoe UI\', sans-serif; font-size: 9pt;">'
                '<span style="font-weight: bold;">PyQGIS Code</span>'
                '</div>'
            )

            code_block = (
                f'<pre style="margin: 0; background-color: #000000; color: #EEEEEE; padding: 10px; '
                'border: 1px solid #000; border-top: none; border-radius: 0; '
                'border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; '
                'font-family: \'Consolas\', \'Menlo\', \'monospace\'; font-size: 9pt; '
                f'overflow-x: auto; white-space: pre-wrap; word-break: break-word;"><code>{code_to_display}</code></pre>'
            )

            return f'<div style="margin-top: 10px; margin-bottom: 10px;">{header}{code_block}</div>'
        
        # Format code blocks
        content = re.sub(r'```(?:python)?\s*\n(.*?)\n```', format_code_block, content, flags=re.DOTALL)
        
        # Format inline code
        content = re.sub(r'`([^`\n]+)`', r'<code style="background-color: #e9ecef; color: #c7254e; padding: 2px 4px; border-radius: 3px; font-family: monospace; font-size: 9pt;">\1</code>', content)
        
        return content
    
    def add_to_execution_results(self, message):
        """Send live log messages to QGIS Log Messages panel (no in-dialog panel)."""
        try:
            if message is None:
                return
            # Normalize to string and avoid trailing newlines duplication
            text = str(message).rstrip("\n")
            if not text:
                return
            QgsMessageLog.logMessage(text, "QGIS Copilot", level=Qgis.Info)
        except Exception:
            pass
    
    def show_progress(self, message="Processing..."):
        """Show progress bar with message"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.send_button.setEnabled(False)
        self.send_button.setText(message)
    
    def hide_progress(self):
        """Hide progress bar"""
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        self.send_button.setText("Send")
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Save any settings if needed
        event.accept()

    # Removed: logs tab utilities (refresh, clear history, export, statistics)

    def request_manual_improvement(self):
        """Manually trigger a request for AI to improve the last failed code."""
        self.request_ai_improvement()

    def on_retry_clicked(self):
        """Retry behavior: if a failed run exists, request improvement; otherwise resend last user query."""
        try:
            # If there's a failed execution context, prioritize improvement flow
            if self.pending_failed_execution:
                self.request_ai_improvement()
                return
            # Otherwise, find the last user message and resend it
            last_user_msg = None
            for item in reversed(self.chat_history):
                if item.get('sender') == 'You':
                    last_user_msg = (item.get('message') or '').strip()
                    if last_user_msg:
                        break
            if not last_user_msg:
                QMessageBox.information(self, "Retry", "No previous user query found to retry.")
                return
            # Reuse the normal send flow so all preferences/context apply
            try:
                self.message_input.setText(last_user_msg)
            except Exception:
                pass
            self.send_message()
        except Exception:
            pass

    def request_ai_improvement(self):
        """Ask the AI to improve the last failed code execution."""
        if self.pending_failed_execution:
            self.pyqgis_executor.suggest_improvement(self.pending_failed_execution)
            self.pending_failed_execution = None

    def on_dock_copilot_panel(self):
        """Dock the Copilot window as a tab alongside Log Messages and Python Console."""
        try:
            mainwin = self.iface.mainWindow() if self.iface else None
            if not mainwin:
                return
            # If already docked, just raise it
            if hasattr(self, '_copilot_main_dock') and self._copilot_main_dock:
                self._copilot_main_dock.raise_()
                return

            dock = QDockWidget("QGIS Copilot", mainwin)
            dock.setObjectName("QGISCopilotMainDock")
            # Make it movable/floatable/closable
            dock.setAllowedAreas(Qt.AllDockWidgetAreas)
            dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
            # Avoid enforcing minimums; let the splitter control size freely
            dock.setMinimumSize(0, 0)
            dock.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Ensure closing the dock does not delete it, so we can show it again
            dock.setAttribute(Qt.WA_DeleteOnClose, False)
            # No checkbox to sync; rely on plugin action to reopen hidden dock
            # Reparent this dialog into the dock
            self.setParent(dock)
            self.setWindowFlags(Qt.Widget)
            # Remove dialog minimums so users can freely resize the bottom area
            self.setMinimumSize(0, 0)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Loosen minimums on large inner widgets so the tab can shrink
            if hasattr(self, 'chat_display') and self.chat_display is not None:
                self.chat_display.setMinimumHeight(0)
                self.chat_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            if hasattr(self, 'execution_display') and self.execution_display is not None:
                self.execution_display.setMinimumHeight(0)
                self.execution_display.setMinimumWidth(0)
                self.execution_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Allow the System Prompt editor and tabs to expand with the dock height
            if hasattr(self, 'system_prompt_input') and self.system_prompt_input is not None:
                self.system_prompt_input.setMinimumHeight(0)
                self.system_prompt_input.setMaximumHeight(16777215)
                self.system_prompt_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            if hasattr(self, 'tab_widget') and self.tab_widget is not None:
                self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            dock.setWidget(self)
            # Integrate with QGIS docking system so users can drag/tab it like built-in panels
            # Choose initial area from user preference (default bottom)
            saved_area = int(QSettings().value("qgis_copilot/dock_area", int(Qt.BottomDockWidgetArea)))
            self.iface.addDockWidget(saved_area, dock)
            # Tabify with Log Messages and Python Console if present
            from qgis.PyQt.QtWidgets import QDockWidget as _QD
            docks = mainwin.findChildren(_QD)
            log_dock = next((d for d in docks if "Log" in d.windowTitle() and "Message" in d.windowTitle()), None)
            console_dock = next((d for d in docks if "Python" in d.windowTitle() and "Console" in d.windowTitle()), None)
            target = None
            if log_dock and mainwin.dockWidgetArea(log_dock) == saved_area:
                target = log_dock
            elif console_dock and mainwin.dockWidgetArea(console_dock) == saved_area:
                target = console_dock
            else:
                target = next((d for d in docks if d is not dock and mainwin.dockWidgetArea(d) == saved_area), None)
            if target:
                mainwin.tabifyDockWidget(target, dock)
            # Remember and show dock
            self._copilot_main_dock = dock
            dock.show()
            # Do not force an initial height here; let QGIS manage splitter sizes
            # If previously opened as a modal dialog, close the loop; otherwise ensure visible
            if hasattr(self, 'isModal') and self.isModal():
                self.accept()
            else:
                self.show()
        except Exception as e:
            QgsMessageLog.logMessage(f"Error docking Copilot panel: {e}", "QGIS Copilot", level=Qgis.Warning)

    def ensure_code_editor_dock(self, code_text: str = ""):
        """Ensure there is a docked code editor and tabify it with common docks."""
        try:
            mainwin = self.iface.mainWindow() if self.iface else None
            if not mainwin:
                return
            if not self._code_editor_dock:
                dock = QDockWidget("Copilot Code Editor", mainwin)
                editor = QTextEdit(dock)
                editor.setAcceptRichText(False)
                try:
                    editor.setFont(QFont("Consolas", 10))
                except Exception:
                    pass
                dock.setWidget(editor)
                dock.setObjectName("CopilotCodeEditorDock")
                mainwin.addDockWidget(Qt.BottomDockWidgetArea, dock)
                self._code_editor_dock = dock
                self._code_editor_widget = editor
                # Try to tabify with Log Messages or Python Console if found
                try:
                    from qgis.PyQt.QtWidgets import QDockWidget as _QD
                    docks = mainwin.findChildren(_QD)
                    log_dock = None
                    console_dock = None
                    for d in docks:
                        title = d.windowTitle() or ""
                        if "Log Messages" in title:
                            log_dock = d
                        if "Python Console" in title:
                            console_dock = d
                    if log_dock:
                        mainwin.tabifyDockWidget(log_dock, dock)
                    elif console_dock:
                        mainwin.tabifyDockWidget(console_dock, dock)
                except Exception:
                    pass
            # Update content and raise dock
            if self._code_editor_widget is not None and isinstance(code_text, str) and code_text:
                self._code_editor_widget.setPlainText(code_text)
            if self._code_editor_dock:
                self._code_editor_dock.raise_()
        except Exception:
            pass

    # Removed: on_open_in_editor — replaced by per-code-block Open in Editor actions
    
    def on_undock_copilot_panel(self):
        """Restore Copilot to its original floating dialog form."""
        try:
            mainwin = self.iface.mainWindow() if self.iface else None
            dock = getattr(self, '_copilot_main_dock', None)
            if dock and mainwin:
                try:
                    dock.hide()
                    dock.setWidget(None)
                    mainwin.removeDockWidget(dock)
                except Exception:
                    pass
                try:
                    dock.deleteLater()
                except Exception:
                    pass
                self._copilot_main_dock = None
            # Reparent to top-level and restore dialog flags/sizing
            try:
                self.setParent(None)
                self.setWindowFlags(Qt.Dialog | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
                self.setMinimumSize(600, 500)
                self.resize(1000, 700)
                # Ensure inner widgets are responsive
                try:
                    if hasattr(self, 'chat_display') and self.chat_display is not None:
                        self.chat_display.setMinimumHeight(0)
                        self.chat_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'execution_display') and self.execution_display is not None:
                        self.execution_display.setMinimumHeight(0)
                        self.execution_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                except Exception:
                    pass
                # Allow prompt editor to be fully resizable
                try:
                    if hasattr(self, 'system_prompt_input') and self.system_prompt_input is not None:
                        self.system_prompt_input.setMinimumHeight(60)
                        self.system_prompt_input.setMaximumHeight(16777215)
                        self.system_prompt_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                except Exception:
                    pass
                self.show()
            except Exception:
                pass
            # Reflect UI toggle if present
            try:
                if hasattr(self, 'dock_copilot_cb') and self.dock_copilot_cb is not None:
                    self.dock_copilot_cb.blockSignals(True)
                    self.dock_copilot_cb.setChecked(False)
                    self.dock_copilot_cb.blockSignals(False)
            except Exception:
                pass
        except Exception:
            pass
    # Removed: Dock toggle checkbox handlers (auto-docking is enabled)

    def on_dock_code_editor(self):
        """Open the current script in the QGIS Python Console code editor."""
        try:
            # Ensure there is a saved script; save from last response if needed
            if not getattr(self, '_last_saved_task_path', None) or not os.path.exists(self._last_saved_task_path):
                if hasattr(self, 'last_response') and self.last_response:
                    filename_hint = None
                    for item in reversed(self.chat_history):
                        if item.get('sender') == 'You':
                            filename_hint = (item.get('message') or '').strip().splitlines()[0][:80]
                            break
                    try:
                        self._last_saved_task_path = self.pyqgis_executor.save_response_to_task_file(
                            self.last_response, filename_hint=filename_hint
                        )
                    except Exception:
                        self._last_saved_task_path = None
            if not getattr(self, '_last_saved_task_path', None) or not os.path.exists(self._last_saved_task_path):
                QMessageBox.information(self, "Info", "No saved script available yet. Send a message to generate code first.")
                return

            # Show Python Console
            if self.iface and hasattr(self.iface, 'actionShowPythonDialog'):
                try:
                    self.iface.actionShowPythonDialog().trigger()
                except Exception:
                    pass

            # Try to load the file into the Python Console editor
            import qgis.utils as qutils
            pc = None
            if hasattr(qutils, 'plugins') and isinstance(qutils.plugins, dict):
                pc = qutils.plugins.get('PythonConsole') or qutils.plugins.get('pythonconsole')
                if not pc:
                    for k, v in qutils.plugins.items():
                        if 'python' in k.lower() and 'console' in k.lower():
                            pc = v
                            break
            # Ensure editor is visible
            for act_name in ('actionShowEditor', 'actionEditor', 'toggleEditor', 'showEditor'):
                act = getattr(pc, act_name, None)
                if act:
                    try:
                        if hasattr(act, 'setChecked'):
                            act.setChecked(True)
                        if hasattr(act, 'trigger'):
                            act.trigger()
                    except Exception:
                        pass
            # Try direct file open methods
            loaded = False
            for meth in ('openFileInEditor', 'openScriptFile', 'loadScript', 'addToEditor'):
                fn = getattr(pc, meth, None)
                if callable(fn):
                    try:
                        fn(self._last_saved_task_path)
                        loaded = True
                        break
                    except Exception:
                        pass
            # Final fallback: run a snippet inside console context to open the file
            if not loaded:
                console = getattr(pc, 'console', None)
                if console and hasattr(console, 'runCommand'):
                    fp = self._last_saved_task_path.replace('\\', '/').replace("'", "\'")
                    cmd = f"""# Copilot: open file in Python Console editor
import qgis.utils as _qutils
_pc = _qutils.plugins.get('PythonConsole') or _qutils.plugins.get('pythonconsole')
for _a in ('actionShowEditor','actionEditor','toggleEditor','showEditor'):
    _act = getattr(_pc, _a, None)
    if _act:
        getattr(_act, 'setChecked', lambda *_: None)(True)
        getattr(_act, 'trigger', lambda *_: None)()
for _m in ('openFileInEditor','openScriptFile','loadScript','addToEditor'):
    _fn = getattr(_pc, _m, None)
    if callable(_fn):
        try:
            _fn(r'{fp}')
            break
        except Exception:
            pass
"""
                    try:
                        console.runCommand(cmd)
                    except Exception:
                        pass
        except Exception:
            pass
