"""
QGIS Copilot Chat Dialog - Main UI for the chat interface
"""

import os
import json
import re
from datetime import datetime
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QSplitter, QLabel, QCheckBox, QGroupBox,
    QMessageBox, QTabWidget, QWidget, QTextBrowser, QProgressBar, QFileDialog,
    QComboBox
)
from qgis.PyQt.QtGui import QTextCursor
from qgis.core import QgsMessageLog, Qgis

from .gemini_api import GeminiAPI
from .openai_api import OpenAIAPI
from .pyqgis_executor import PyQGISExecutor


class CopilotChatDialog(QDialog):
    """Main dialog for QGIS Copilot chat interface"""
    
    def __init__(self, iface, parent=None):
        super(CopilotChatDialog, self).__init__(parent)
        self.iface = iface
        self.chat_history = []
        self.last_response = None

        # Initialize API handlers
        self.gemini_api = GeminiAPI()
        self.openai_api = OpenAIAPI()
        self.api_handlers = {
            "Google Gemini": self.gemini_api,
            "OpenAI ChatGPT": self.openai_api
        }

        self.setup_ui()

        # Set default API based on UI
        self.current_api_name = self.api_provider_combo.currentText()
        self.current_api = self.api_handlers[self.current_api_name]

        # Initialize executor
        self.pyqgis_executor = PyQGISExecutor(iface)

        # Connect signals
        self.connect_signals()

        # Load API key for the default provider
        self.load_current_api_key()
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("QGIS Copilot")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Chat tab
        chat_widget = self.create_chat_tab()
        self.tab_widget.addTab(chat_widget, "Chat")
        
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
        self.chat_display.setMinimumHeight(300)
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
        
        # Options
        options_layout = QHBoxLayout()
        
        self.include_context_cb = QCheckBox("Include QGIS Context")
        self.include_context_cb.setChecked(True)
        
        self.auto_execute_cb = QCheckBox("Auto-execute Code")
        self.auto_execute_cb.setChecked(False)
        
        options_layout.addWidget(self.include_context_cb)
        options_layout.addWidget(self.auto_execute_cb)
        options_layout.addStretch()
        
        chat_layout.addLayout(options_layout)
        
        # Chat management buttons
        chat_management_layout = QHBoxLayout()
        
        clear_chat_button = QPushButton("Clear Chat")
        clear_chat_button.clicked.connect(self.clear_chat)
        
        save_chat_button = QPushButton("Save Chat")
        save_chat_button.clicked.connect(self.save_chat)
        
        load_chat_button = QPushButton("Load Chat")
        load_chat_button.clicked.connect(self.load_chat)
        
        chat_management_layout.addWidget(clear_chat_button)
        chat_management_layout.addWidget(save_chat_button)
        chat_management_layout.addWidget(load_chat_button)
        chat_management_layout.addStretch()
        chat_layout.addLayout(chat_management_layout)
        
        chat_container.setLayout(chat_layout)
        splitter.addWidget(chat_container)
        
        # Right side - Execution results
        execution_container = QWidget()
        execution_layout = QVBoxLayout()
        
        execution_layout.addWidget(QLabel("Execution Results:"))
        
        self.execution_display = QTextEdit()
        self.execution_display.setMinimumWidth(300)
        self.execution_display.setReadOnly(True)
        execution_layout.addWidget(self.execution_display)
        
        # Clear execution button
        clear_exec_button = QPushButton("Clear Results")
        clear_exec_button.clicked.connect(self.execution_display.clear)
        execution_layout.addWidget(clear_exec_button)
        
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

        layout.addStretch()
        settings_widget.setLayout(layout)
        return settings_widget
    
    def setup_chat_display_style(self):
        """Setup styling for the chat display"""
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
                line-height: 1.4;
            }
        """)
    
    def connect_signals(self):
        """Connect all signals"""
        # API signals
        self.gemini_api.response_received.connect(self.handle_api_response)
        self.gemini_api.error_occurred.connect(self.handle_api_error)
        self.openai_api.response_received.connect(self.handle_api_response)
        self.openai_api.error_occurred.connect(self.handle_api_error)
        
        # Executor signals
        self.pyqgis_executor.execution_completed.connect(self.handle_execution_result)
        
        # UI signals
        self.api_provider_combo.currentTextChanged.connect(self.on_api_provider_changed)
        self.model_selection_combo.currentTextChanged.connect(self.on_model_changed)

    def on_api_provider_changed(self, provider_name):
        """Handle API provider change"""
        self.current_api_name = provider_name
        self.current_api = self.api_handlers[provider_name]
        self.update_api_settings_ui()
        self.load_current_api_key()

    def on_model_changed(self, model_name):
        """Handle AI model change"""
        if not model_name or self.model_selection_combo.signalsBlocked():
            return

        if hasattr(self.current_api, 'set_model'):
            self.current_api.set_model(model_name)

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
    
    def send_message(self):
        """Send a message to QGIS Copilot"""
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
        
        # Show progress
        self.show_progress(f"Getting response from {self.current_api_name}...")
        
        # Send to API
        self.current_api.send_message(message, context)
    
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
        
        self.pyqgis_executor.execute_gemini_response(response)

    def handle_execution_result(self, result, success):
        """Handle execution results"""
        color = "green" if success else "red"
        self.add_to_execution_results(result, color)
    
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
        
        # Add timestamp and sender
        # Format the message
        html_message = f"""
        <div style="margin-bottom: 10px; padding: 8px; border-left: 3px solid {color}; background-color: #f8f9fa;">
            <strong style="color: {color};">{sender}</strong> 
            <span style="color: #6c757d; font-size: 9pt;">({timestamp})</span><br>
            <div style="margin-top: 5px;">{self.format_message_content(message)}</div>
        </div>
        """
        
        cursor.insertHtml(html_message)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()

    def save_chat(self):
        """Save the current chat history to a JSON file."""
        if not self.chat_history:
            QMessageBox.information(self, "Info", "Chat history is empty. Nothing to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Chat History",
            "",
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
            code = match.group(1)
            return f'<pre style="background-color: #f8f9fa; padding: 8px; border: 1px solid #dee2e6; border-radius: 4px; font-family: monospace; font-size: 9pt; overflow-x: auto;"><code>{code}</code></pre>'
        
        # Format code blocks
        content = re.sub(r'```(?:python)?\s*\n(.*?)\n```', format_code_block, content, flags=re.DOTALL)
        
        # Format inline code
        content = re.sub(r'`([^`\n]+)`', r'<code style="background-color: #f8f9fa; padding: 2px 4px; border-radius: 2px; font-family: monospace; font-size: 9pt;">\1</code>', content)
        
        # Convert line breaks to HTML
        content = content.replace('\n', '<br>')
        
        return content
    
    def add_to_execution_results(self, message, color="black"):
        """Add message to execution results"""
        cursor = self.execution_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        if color != "black":
            cursor.insertHtml(f'<span style="color: {color};">{message}</span><br>')
        else:
            cursor.insertText(message + '\n')
        
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