"""
QGIS Copilot Chat Dialog - Main UI for the chat interface
"""

import os
from datetime import datetime
from qgis.PyQt.QtCore import Qt, QThread, pyqtSlot
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QSplitter, QLabel, QCheckBox, QGroupBox,
    QScrollArea, QMessageBox, QInputDialog, QTabWidget,
    QWidget, QTextBrowser, QProgressBar
)
from qgis.PyQt.QtGui import QFont, QTextCursor, QColor, QPalette
from qgis.core import QgsMessageLog, Qgis

from .gemini_api import GeminiAPI
from .pyqgis_executor import PyQGISExecutor


class CopilotChatDialog(QDialog):
    """Main dialog for QGIS Copilot chat interface"""
    
    def __init__(self, iface, parent=None):
        super(CopilotChatDialog, self).__init__(parent)
        self.iface = iface
        self.setup_ui()
        
        # Initialize API and executor
        self.gemini_api = GeminiAPI()
        self.pyqgis_executor = PyQGISExecutor(iface)
        
        # Connect signals
        self.connect_signals()
        
        # Load API key if available
        self.load_api_key()
    
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
        
        # API Key section
        api_group = QGroupBox("Google Gemini API Configuration")
        api_layout = QVBoxLayout()
        
        api_layout.addWidget(QLabel("API Key:"))
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
        instructions = QLabel("""
<b>Welcome to QGIS Copilot!</b><br><br>
To get started, you need a free Google Gemini API key:<br>
1. Visit <a href="https://aistudio.google.com">Google AI Studio</a><br>
2. Sign in with your Google account<br>
3. Create an API key<br>
4. Enter it above and click 'Save API Key'<br>
5. Test the connection with 'Test API Key'<br><br>
Then start chatting with your QGIS Copilot!
        """)
        instructions.setWordWrap(True)
        instructions.setOpenExternalLinks(True)
        api_layout.addWidget(instructions)
        
        api_group.setLayout(api_layout)
        layout.addWidget(api_group)
        
        # Model settings
        model_group = QGroupBox("Model Settings")
        model_layout = QVBoxLayout()
        
        model_layout.addWidget(QLabel("Currently using: Gemini 1.5 Flash"))
        model_layout.addWidget(QLabel("This provides the best balance of speed and capability for QGIS tasks."))
        
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
        self.gemini_api.response_received.connect(self.handle_gemini_response)
        self.gemini_api.error_occurred.connect(self.handle_gemini_error)
        
        # Executor signals
        self.pyqgis_executor.execution_completed.connect(self.handle_execution_result)
    
    def load_api_key(self):
        """Load saved API key"""
        api_key = self.gemini_api.get_api_key()
        if api_key:
            self.api_key_input.setText(api_key)
    
    def save_api_key(self):
        """Save the API key"""
        api_key = self.api_key_input.text().strip()
        if api_key:
            self.gemini_api.set_api_key(api_key)
            QMessageBox.information(self, "Success", "API key saved successfully!")
        else:
            QMessageBox.warning(self, "Warning", "Please enter a valid API key.")
    
    def test_api_key(self):
        """Test the API key connection"""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key first.")
            return
        
        self.gemini_api.set_api_key(api_key)
        self.show_progress("Testing API key...")
        self.gemini_api.send_message("Hello, this is a test message. Please respond with 'API test successful!'")
    
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
            context = self.gemini_api.get_qgis_context(self.iface)
        
        # Show progress
        self.show_progress("Getting response from QGIS Copilot...")
        
        # Send to API
        self.gemini_api.send_message(message, context)
    
    def handle_gemini_response(self, response):
        """Handle response from Gemini API"""
        self.hide_progress()
        
        # Add response to chat
        self.add_to_chat("QGIS Copilot", response, "#28a745")
        
        # Store last response for potential execution
        self.last_response = response
        self.execute_button.setEnabled(True)
        
        # Auto-execute if enabled
        if self.auto_execute_cb.isChecked():
            self.execute_code_from_response(response)
    
    def handle_gemini_error(self, error):
        """Handle errors from Gemini API"""
        self.hide_progress()
        self.add_to_chat("System", f"Error: {error}", "#dc3545")
        QgsMessageLog.logMessage(f"QGIS Copilot API Error: {error}", "QGIS Copilot", level=Qgis.Critical)
    
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
        """Add a message to the chat display"""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Add timestamp and sender
        timestamp = datetime.now().strftime("%H:%M:%S")
        
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
    
    def format_message_content(self, content):
        """Format message content with syntax highlighting for code"""
        import re
        
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