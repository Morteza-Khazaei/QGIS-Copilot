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
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QSplitter, QLabel, QCheckBox, QGroupBox,
    QMessageBox, QTabWidget, QWidget, QTextBrowser, QProgressBar, QFileDialog, QComboBox,
    QToolTip
)
from qgis.PyQt.QtGui import QTextCursor, QCursor, QDesktopServices, QFont
from qgis.core import QgsMessageLog, Qgis, QgsApplication

from .gemini_api import GeminiAPI
from .openai_api import OpenAIAPI
from .claude_api import ClaudeAPI
from .pyqgis_executor import EnhancedPyQGISExecutor


class CopilotChatDialog(QDialog):
    """Main dialog for QGIS Copilot chat interface"""
    
    def __init__(self, iface, parent=None):
        super(CopilotChatDialog, self).__init__(parent)
        self.iface = iface
        self.chat_history = []
        self.last_response = None
        self.auto_feedback_enabled = False
        # Initialize API handlers
        self.gemini_api = GeminiAPI()
        self.openai_api = OpenAIAPI()
        self.claude_api = ClaudeAPI()
        self.api_handlers = {
            "Google Gemini": self.gemini_api,
            "OpenAI ChatGPT": self.openai_api,
            "Anthropic Claude": self.claude_api
        }
        self.default_system_prompt = self.gemini_api.system_prompt

        self.setup_ui()

        # Set default API based on UI
        self.current_api_name = self.api_provider_combo.currentText()
        self.current_api = self.api_handlers[self.current_api_name]

        # Initialize enhanced executor
        self.pyqgis_executor = EnhancedPyQGISExecutor(iface)

        # Connect signals
        self.connect_signals()

        # Load API key for the default provider
        self.load_current_api_key()
        self.load_system_prompt()
        
        # Timer for delayed AI feedback
        self.feedback_timer = QTimer()
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.request_ai_improvement)
        self.pending_failed_execution = None
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("QGIS Copilot - Enhanced with Execution Logging")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Chat tab
        chat_widget = self.create_chat_tab()
        self.tab_widget.addTab(chat_widget, "Chat")
        
        # Execution Logs tab
        logs_widget = self.create_logs_tab()
        self.tab_widget.addTab(logs_widget, "Execution Logs")
        
        # Settings tab
        settings_widget = self.create_settings_tab()
        self.tab_widget.addTab(settings_widget, "Settings")
        
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)
    
    def create_chat_tab(self):
        """Create the main chat interface tab"""
        chat_widget = QWidget()
        layout = QVBoxLayout()
        
        # Create splitter for chat and execution results
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side - Chat interface
        chat_container = QWidget()
        chat_layout = QVBoxLayout()
        
        # Chat display area
        self.chat_display = QTextBrowser()
        self.chat_display.setMinimumHeight(350)
        self.setup_chat_display_style()
        chat_layout.addWidget(self.chat_display)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Ask your QGIS Copilot anything...")
        self.message_input.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        
        self.execute_button = QPushButton("Execute Last Code")
        self.execute_button.clicked.connect(self.execute_last_code)
        self.execute_button.setEnabled(False)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        input_layout.addWidget(self.execute_button)
        
        chat_layout.addLayout(input_layout)
        
        # Enhanced options
        options_layout = QVBoxLayout()
        
        # First row of options
        options_row1 = QHBoxLayout()
        self.include_context_cb = QCheckBox("Include QGIS Context")
        self.include_context_cb.setChecked(True)
        
        self.auto_execute_cb = QCheckBox("Auto-execute Code")
        self.auto_execute_cb.setChecked(False)
        
        options_row1.addWidget(self.include_context_cb)
        options_row1.addWidget(self.auto_execute_cb)
        options_row1.addStretch()
        
        # Second row of options
        options_row2 = QHBoxLayout()
        self.include_logs_cb = QCheckBox("Include Execution Logs in Context")
        self.include_logs_cb.setChecked(True)
        self.include_logs_cb.setToolTip("Send recent execution logs to AI for better context")
        
        self.auto_feedback_cb = QCheckBox("Auto Request Improvements on Errors")
        self.auto_feedback_cb.setChecked(False)
        self.auto_feedback_cb.setToolTip("Automatically ask AI to improve code when execution fails")
        self.auto_feedback_cb.toggled.connect(self.on_auto_feedback_toggled)
        
        # Run mode option
        self.run_in_console_cb = QCheckBox("Run via QGIS Python Console (open editor + exec)")
        self.run_in_console_cb.setChecked(True)
        self.run_in_console_cb.setToolTip("Writes code to a temp file, opens it in QGIS Python Editor, and runs using exec(Path(file).read_text()) for native logging/tracebacks.")

        options_row2.addWidget(self.include_logs_cb)
        options_row2.addWidget(self.auto_feedback_cb)
        options_row2.addWidget(self.run_in_console_cb)
        options_row2.addStretch()
        
        options_layout.addLayout(options_row1)
        options_layout.addLayout(options_row2)
        chat_layout.addLayout(options_layout)
        
        # Chat management buttons
        chat_management_layout = QHBoxLayout()
        
        clear_chat_button = QPushButton("Clear Chat")
        clear_chat_button.clicked.connect(self.clear_chat)
        
        save_chat_button = QPushButton("Save Chat")
        save_chat_button.clicked.connect(self.save_chat)
        
        load_chat_button = QPushButton("Load Chat")
        load_chat_button.clicked.connect(self.load_chat)
        
        improve_last_button = QPushButton("Request Improvement")
        improve_last_button.clicked.connect(self.request_manual_improvement)
        improve_last_button.setToolTip("Ask AI to improve the last failed code execution")
        
        chat_management_layout.addWidget(clear_chat_button)
        chat_management_layout.addWidget(save_chat_button)
        chat_management_layout.addWidget(load_chat_button)
        chat_management_layout.addWidget(improve_last_button)
        chat_management_layout.addStretch()
        chat_layout.addLayout(chat_management_layout)
        
        chat_container.setLayout(chat_layout)
        splitter.addWidget(chat_container)
        
        # Right side - Execution results with enhanced display
        execution_container = QWidget()
        execution_layout = QVBoxLayout()
        
        # Execution results header with buttons
        exec_header_layout = QHBoxLayout()
        exec_header_layout.addWidget(QLabel("Live Execution Results:"))

        # Create the display widget before connecting signals to it
        self.execution_display = QTextEdit()
        self.execution_display.setMinimumWidth(350)
        self.execution_display.setReadOnly(True)
        self.execution_display.setFont(QFont("Consolas", 9))

        clear_exec_button = QPushButton("Clear Results")
        clear_exec_button.clicked.connect(self.execution_display.clear)
        
        show_stats_button = QPushButton("Show Statistics")
        show_stats_button.clicked.connect(self.show_execution_statistics)
        
        exec_header_layout.addWidget(show_stats_button)
        exec_header_layout.addWidget(clear_exec_button)
        exec_header_layout.addStretch()
        
        execution_layout.addLayout(exec_header_layout)
        execution_layout.addWidget(self.execution_display)
        
        execution_container.setLayout(execution_layout)
        splitter.addWidget(execution_container)
        
        # Set splitter sizes
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        chat_widget.setLayout(layout)
        return chat_widget
    
    def create_logs_tab(self):
        """Create the execution logs tab"""
        logs_widget = QWidget()
        layout = QVBoxLayout()
        
        # Header with controls
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Detailed Execution History:"))
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_logs_display)
        
        clear_logs_button = QPushButton("Clear History")
        clear_logs_button.clicked.connect(self.clear_execution_history)
        
        export_logs_button = QPushButton("Export Logs")
        export_logs_button.clicked.connect(self.export_execution_logs)
        
        header_layout.addWidget(refresh_button)
        header_layout.addWidget(export_logs_button)
        header_layout.addWidget(clear_logs_button)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Statistics display
        self.stats_display = QLabel("No execution statistics available.")
        self.stats_display.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
                font-family: monospace;
                font-size: 9pt;
            }
        """)
        layout.addWidget(self.stats_display)
        
        # Full logs display
        self.full_logs_display = QTextEdit()
        self.full_logs_display.setReadOnly(True)
        self.full_logs_display.setFont(QFont("Consolas", 9))
        self.full_logs_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)
        layout.addWidget(self.full_logs_display)
        
        logs_widget.setLayout(layout)
        return logs_widget
    
    def create_settings_tab(self):
        """Create the settings tab"""
        settings_widget = QWidget()
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
        
        save_key_button = QPushButton("Save API Key")
        save_key_button.clicked.connect(self.save_api_key)
        
        test_key_button = QPushButton("Test API Key")
        test_key_button.clicked.connect(self.test_api_key)
        
        api_button_layout.addWidget(save_key_button)
        api_button_layout.addWidget(test_key_button)
        api_button_layout.addStretch()
        
        api_layout.addLayout(api_button_layout)
        
        # Instructions
        self.instructions_label = QLabel()
        self.instructions_label.setWordWrap(True)
        self.instructions_label.setOpenExternalLinks(True)
        api_layout.addWidget(self.instructions_label)
        
        self.api_group.setLayout(api_layout)
        layout.addWidget(self.api_group)
        
        # Model settings
        model_group = QGroupBox("Model Settings")
        model_layout = QVBoxLayout()

        model_layout.addWidget(QLabel("Select AI Model:"))
        self.model_selection_combo = QComboBox()
        model_layout.addWidget(self.model_selection_combo)

        model_info_label = QLabel("Select the AI model to use. If you get 'model not found' errors, try a different model. `gpt-4o` is recommended for OpenAI.")
        model_info_label.setWordWrap(True)
        model_layout.addWidget(model_info_label)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # System Prompt settings
        prompt_group = QGroupBox("System Prompt (Agent Behavior)")
        prompt_layout = QVBoxLayout()

        prompt_info_label = QLabel("This is the core instruction set for the AI agent. Edit with caution.")
        prompt_info_label.setWordWrap(True)
        prompt_layout.addWidget(prompt_info_label)

        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setAcceptRichText(False)
        self.system_prompt_input.setMinimumHeight(150)
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

        layout.addStretch()
        settings_widget.setLayout(layout)
        return settings_widget
    
    def setup_chat_display_style(self):
        """Setup styling for the chat display"""
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #ffffff;
                border: none;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
                padding: 5px;
            }
        """)
    
    def connect_signals(self):
        """Connect all signals"""
        # API signals
        self.gemini_api.response_received.connect(self.handle_api_response)
        self.gemini_api.error_occurred.connect(self.handle_api_error)
        self.openai_api.response_received.connect(self.handle_api_response)
        self.openai_api.error_occurred.connect(self.handle_api_error)
        self.claude_api.response_received.connect(self.handle_api_response)
        self.claude_api.error_occurred.connect(self.handle_api_error)
        
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
        # Open external links in a browser
        QDesktopServices.openUrl(url)

    def update_api_settings_ui(self):
        """Update settings UI based on selected provider"""
        provider_name = self.api_provider_combo.currentText()
        self.api_group.setTitle(f"{provider_name} API Configuration")
        self.api_key_label.setText(f"API Key for {provider_name}:")

        # Disconnect signal to prevent premature firing while we update the UI
        self.model_selection_combo.blockSignals(True)
        self.model_selection_combo.clear()

        if hasattr(self.current_api, 'AVAILABLE_MODELS'):
            self.model_selection_combo.addItems(self.current_api.AVAILABLE_MODELS)
            self.model_selection_combo.setCurrentText(self.current_api.model)
            self.model_selection_combo.setVisible(len(self.current_api.AVAILABLE_MODELS) > 1)

        self.model_selection_combo.blockSignals(False)
        
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

        # Show progress
        self.show_progress(f"Getting response from {self.current_api_name}...")

        # Send to API
        self.current_api.send_message(message, context)
    
    def load_system_prompt(self):
        """Load the system prompt from settings or use default."""
        settings = QSettings()
        saved_prompt = settings.value("qgis_copilot/system_prompt", self.default_system_prompt)
        self.system_prompt_input.setText(saved_prompt)
        self.update_all_system_prompts(saved_prompt)

    def save_system_prompt(self):
        """Save the custom system prompt to settings."""
        prompt_text = self.system_prompt_input.toPlainText()
        settings = QSettings()
        settings.setValue("qgis_copilot/system_prompt", prompt_text)
        self.update_all_system_prompts(prompt_text)
        QMessageBox.information(self, "Success", "System prompt saved successfully!")

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
        self.update_all_system_prompts(self.default_system_prompt)
        QMessageBox.information(self, "Success", "System prompt has been reset to default.")

    def update_all_system_prompts(self, prompt_text):
        """Update the system prompt for all API handlers."""
        for handler in self.api_handlers.values():
            handler.system_prompt = prompt_text

    def handle_api_response(self, response):
        """Handle response from the current API"""
        self.hide_progress()
        
        # Add response to chat
        self.add_to_chat(self.current_api_name, response, "#28a745")
        
        # Store last response for potential execution
        self.last_response = response
        self.execute_button.setEnabled(True)
        
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
        elif self.current_api_name == "Anthropic Claude":
            pass  # Can add specific Claude error parsing here in the future
        
        final_error_message = user_friendly_error if user_friendly_error else error
        self.add_to_chat("System", f"Error from {self.current_api_name}: {final_error_message}", "#dc3545")
        QgsMessageLog.logMessage(f"QGIS Copilot API Error ({self.current_api_name}): {error}", "QGIS Copilot", level=Qgis.Critical)
    
    def execute_last_code(self):
        """Execute code from the last response"""
        if hasattr(self, 'last_response'):
            self.execute_code_from_response(self.last_response)
        else:
            QMessageBox.information(self, "Info", "No code to execute. Send a message first.")
    
    def execute_code_from_response(self, response):
        """Execute code blocks found in the response"""
        self.add_to_execution_results("=" * 50)
        self.add_to_execution_results("Executing code from QGIS Copilot response...")
        self.add_to_execution_results("=" * 50)
        
        # Choose execution route
        if self.run_in_console_cb.isChecked():
            self.pyqgis_executor.execute_response_via_console(response)
        else:
            self.pyqgis_executor.execute_gemini_response(response)

    def handle_execution_completed(self, result_message, success, execution_log):
        """Handle the completion of a code execution."""
        # Notify in chat with a brief summary so the user sees outcomes inline
        summary_color = "#28a745" if success else "#dc3545"
        status_text = "succeeded" if success else "failed"
        self.add_to_chat(
            "System",
            f"Code execution {status_text}. See 'Live Execution Results' and 'Execution Logs' for details.",
            summary_color,
        )

        # If execution failed, optionally trigger auto-feedback
        if not success:
            self.pending_failed_execution = execution_log
            if self.auto_feedback_enabled:
                # Delay to allow user to see the error before AI responds
                self.feedback_timer.start(1500)

    def handle_logs_updated(self, formatted_log_entry):
        """Append new log entry to the live display."""
        self.add_to_execution_results(formatted_log_entry)
        # Keep the 'Execution Logs' tab in sync automatically
        self.refresh_logs_display()

    def handle_improvement_suggestion(self, original_code, suggestion_prompt):
        self.add_to_chat("System", "Requesting improvement for the last failed script...", "#6c757d")
        self.send_message(message=suggestion_prompt, is_programmatic=True)
    
    def add_to_chat(self, sender, message, color):
        """Add a message to the chat display and history"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Store in history
        self.chat_history.append({
            "sender": sender,
            "message": message,
            "color": color,
            "timestamp": timestamp
        })
        
        # Add to display
        self.render_message(sender, message, color, timestamp)

    def render_message(self, sender, message, color, timestamp):
        """Renders a single message to the chat display"""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)

        is_user = (sender == "You")
        align = "right" if is_user else "left"
        
        bubble_bg_color = "#e7f5ff" if is_user else "#f8f9fa"
        bubble_border_color = "#cce5ff" if is_user else "#dee2e6"

        # Main div for alignment
        html = f'<div style="margin: 0 5px; text-align: {align};">'
        
        # The bubble
        html += f"""
        <div style="
            display: inline-block;
            text-align: left;
            max-width: 85%;
            padding: 8px 12px;
            border-radius: 12px;
            background-color: {bubble_bg_color};
            border: 1px solid {bubble_border_color};
            margin-top: 5px;
            margin-bottom: 5px;
        ">
            <div>
                <strong style="color: {color};">{sender}</strong> 
                <span style="color: #6c757d; font-size: 8pt;">({timestamp})</span>
            </div>
            <div style="margin-top: 5px; white-space: pre-wrap; word-wrap: break-word;">{self.format_message_content(message)}</div>
        </div>
        </div>"""

        cursor.insertHtml(html)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def save_chat(self):
        """Save the current chat history to a JSON file."""
        if not self.chat_history:
            QMessageBox.information(self, "Info", "Chat history is empty. Nothing to save.")
            return

        # Generate a default filename with a timestamp
        timestamp = datetime.now().strftime("%b %d, %Y, %I_%M_%S %p")
        default_filename = f"QGIS Copilot Chat {timestamp}"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Chat History",
            default_filename,
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.chat_history, f, indent=4)
                QMessageBox.information(self, "Success", f"Chat history saved to {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save chat history: {e}")

    def load_chat(self):
        """Load a chat history from a JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Chat History",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    loaded_history = json.load(f)
                
                if not isinstance(loaded_history, list) or not all('sender' in item and 'message' in item for item in loaded_history):
                    raise ValueError("Invalid chat history file format.")

                self.clear_chat(confirm=False)
                self.chat_history = loaded_history
                self.repopulate_chat_display()
                QMessageBox.information(self, "Success", f"Chat history loaded from {os.path.basename(file_path)}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load chat history: {e}")

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
        self.execute_button.setEnabled(False)

    def repopulate_chat_display(self):
        """Repopulate the chat display from the chat_history list."""
        self.chat_display.clear()
        for item in self.chat_history:
            self.render_message(
                item.get('sender'),
                item.get('message'),
                item.get('color', '#000000'),
                item.get('timestamp', '')
            )
        
        # Find the last AI response to enable the execute button
        for item in reversed(self.chat_history):
            if item.get('sender') not in ("You", "System"):
                self.last_response = item.get('message')
                self.execute_button.setEnabled(True)
                break
        else:
            self.last_response = None
            self.execute_button.setEnabled(False)
    
    def format_message_content(self, content):
        """Format message content with syntax highlighting for code"""
        # Replace code blocks with formatted HTML
        def format_code_block(match):
            code_to_display = html.escape(match.group(1).strip())

            header = (
                '<div style="background-color: #3c3f41; color: #bbbbbb; padding: 6px 10px; '
                'border: 1px solid #555; border-bottom: none; border-top-left-radius: 6px; '
                'border-top-right-radius: 6px; font-family: \'Segoe UI\', sans-serif; font-size: 9pt;">'
                '<span style="font-weight: bold;">PyQGIS Code</span>'
                '</div>'
            )
            
            code_block = (
                f'<pre style="margin: 0; background-color: #2b2b2b; color: #a9b7c6; padding: 10px; '
                'border: 1px solid #555; border-top: none; border-radius: 0; '
                'border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; '
                'font-family: \'Consolas\', \'Menlo\', \'monospace\'; font-size: 9pt; '
                f'overflow-x: auto; white-space: pre;"><code>{code_to_display}</code></pre>'
            )

            return f'<div style="margin-top: 10px; margin-bottom: 10px;">{header}{code_block}</div>'
        
        # Format code blocks
        content = re.sub(r'```(?:python)?\s*\n(.*?)\n```', format_code_block, content, flags=re.DOTALL)
        
        # Format inline code
        content = re.sub(r'`([^`\n]+)`', r'<code style="background-color: #e9ecef; color: #c7254e; padding: 2px 4px; border-radius: 3px; font-family: monospace; font-size: 9pt;">\1</code>', content)
        
        return content
    
    def add_to_execution_results(self, message):
        """Add message to execution results"""
        cursor = self.execution_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        # Ensure each message ends with a newline for readability
        if message and not message.endswith("\n"):
            message = message + "\n"
        cursor.insertText(message)
        
        self.execution_display.setTextCursor(cursor)
        self.execution_display.ensureCursorVisible()
    
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

    def refresh_logs_display(self):
        """Refresh the full logs and statistics display."""
        self.full_logs_display.setText(self.pyqgis_executor.get_all_logs_formatted())
        self.stats_display.setText(self.pyqgis_executor.get_statistics())

    def clear_execution_history(self):
        """Clear all execution history."""
        reply = QMessageBox.question(self, 'Confirm Clear History',
                                     "Are you sure you want to clear all execution history? This cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.pyqgis_executor.clear_history()
            self.refresh_logs_display()
            self.execution_display.clear()
            QMessageBox.information(self, "Success", "Execution history has been cleared.")

    def export_execution_logs(self):
        """Export all execution logs to a text file."""
        logs = self.pyqgis_executor.get_all_logs_formatted()
        if "No execution logs" in logs:
            QMessageBox.information(self, "Info", "No logs to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Export Logs", "qgis_copilot_logs.txt", "Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(logs)
                QMessageBox.information(self, "Success", f"Logs exported to {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export logs: {e}")

    def show_execution_statistics(self):
        """Show execution statistics in a message box."""
        stats = self.pyqgis_executor.get_statistics()
        QMessageBox.information(self, "Execution Statistics", stats)

    def request_manual_improvement(self):
        """Manually trigger a request for AI to improve the last failed code."""
        self.request_ai_improvement()

    def request_ai_improvement(self):
        """Ask the AI to improve the last failed code execution."""
        if self.pending_failed_execution:
            self.pyqgis_executor.suggest_improvement(self.pending_failed_execution)
            self.pending_failed_execution = None
