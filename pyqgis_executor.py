"""
PyQGIS Code Executor - Safely execute PyQGIS code from QGIS Copilot responses
"""

import re
import sys
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

from qgis.core import (
    QgsProject, QgsApplication, QgsMessageLog, Qgis,
    QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsWkbTypes
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal, QVariant


class PyQGISExecutor(QObject):
    """Execute PyQGIS code safely with proper context"""
    
    execution_completed = pyqtSignal(str, bool)  # result, success
    
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setup_execution_environment()
    
    def setup_execution_environment(self):
        """Setup the execution environment with QGIS objects"""
        self.globals = {
            # Core QGIS objects
            'iface': self.iface,
            'project': QgsProject.instance(),
            'canvas': self.iface.mapCanvas() if self.iface else None,
            'app': QgsApplication.instance(),
            
            # Common QGIS imports
            'QgsProject': QgsProject,
            'QgsApplication': QgsApplication,
            'QgsVectorLayer': QgsVectorLayer,
            'QgsRasterLayer': QgsRasterLayer,
            'QgsMapLayer': QgsMapLayer,
            'QgsMessageLog': QgsMessageLog,
            'QgsWkbTypes': QgsWkbTypes,
            'Qgis': Qgis,
            'QVariant': QVariant,
            
            # Python built-ins (safe subset)
            'print': print,
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'sorted': sorted,
            'max': max,
            'min': min,
            'sum': sum,
            'abs': abs,
            'round': round,
        }
        
        # Import commonly used QGIS modules
        try:
            from qgis import core, gui, analysis, processing
            self.globals.update({
                'core': core,
                'gui': gui,
                'analysis': analysis,
                'processing': processing,
            })
        except ImportError as e:
            QgsMessageLog.logMessage(
                f"Could not import QGIS modules: {e}",
                "QGIS Copilot",
                level=Qgis.Warning
            )
    
    def extract_code_blocks(self, text):
        """Extract Python code blocks from QGIS Copilot response"""
        # Look for code blocks marked with ```python or ```
        python_code_pattern = r'```(?:python)?\s*\n(.*?)\n```'
        code_blocks = re.findall(python_code_pattern, text, re.DOTALL)
        
        if not code_blocks:
            # Look for single-line code snippets
            single_line_pattern = r'`([^`\n]+)`'
            single_lines = re.findall(single_line_pattern, text)
            # Only include lines that look like Python code
            code_blocks = [line for line in single_lines 
                          if any(keyword in line for keyword in 
                               ['iface', 'project', 'layer', 'canvas', 'Qgs', '=', 'def', 'import'])]
        
        return code_blocks
    
    def is_safe_code(self, code):
        """Check if code is safe to execute"""
        # List of potentially dangerous operations
        # (pattern, message)
        disallowed_patterns = [
            (r'import\s+qgis', "Do not import 'qgis' modules; they are pre-loaded."),
            (r'from\s+qgis', "Do not import from 'qgis' modules; they are pre-loaded."),
            (r'import\s+os', "Importing 'os' is not allowed for security reasons."),
            (r'import\s+subprocess', "Importing 'subprocess' is not allowed for security reasons."),
            (r'import\s+sys', "Importing 'sys' is not allowed. Use the provided environment."),
            (r'from\s+os', "Importing from 'os' is not allowed."),
            (r'from\s+subprocess', "Importing from 'subprocess' is not allowed."),
            (r'exec\s*\(', "Use of 'exec' is not allowed."),
            (r'eval\s*\(', "Use of 'eval' is not allowed."),
            (r'__import__', "Use of '__import__' is not allowed."),
            (r'open\s*\(', "File I/O with 'open' is not allowed."),
            (r'file\s*\(', "File I/O with 'file' is not allowed."),
            (r'compile\s*\(', "Use of 'compile' is not allowed."),
            (r'globals\s*\(', "Accessing 'globals()' is not allowed."),
            (r'locals\s*\(', "Accessing 'locals()' is not allowed."),
            (r'vars\s*\(', "Accessing 'vars()' is not allowed."),
            (r'dir\s*\(', "Use of 'dir()' is not allowed."),
            (r'delattr', "Use of 'delattr' is not allowed."),
            (r'setattr', "Use of 'setattr' is not allowed."),
            (r'hasattr', "Use of 'hasattr' is not allowed."),
            (r'reload', "Use of 'reload' is not allowed."),
            (r'input\s*\(', "Use of 'input()' is not allowed for security."),
            (r'raw_input\s*\(', "Use of 'raw_input()' is not allowed for security."),
            (r'\.system\s*\(', "Calling 'system' is not allowed."),
            (r'\.popen\s*\(', "Calling 'popen' is not allowed."),
            (r'\.call\s*\(', "Calling 'call' is not allowed."),
        ]
        
        for pattern, msg in disallowed_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Disallowed operation: {msg}"
        
        return True, "Code appears safe"
    
    def execute_code(self, code):
        """Execute PyQGIS code safely"""
        # Check if code is safe
        is_safe, safety_msg = self.is_safe_code(code)
        if not is_safe:
            self.execution_completed.emit(
                f"Execution blocked. {safety_msg}",
                False
            )
            return
        
        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        try:
            # Redirect output
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # Execute the code
            exec(code, self.globals)
            
            # Get the captured output
            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()
            
            # Prepare result message
            result = "Code executed successfully.\n"
            if stdout_output:
                result += f"Output:\n{stdout_output}\n"
            if stderr_output:
                result += f"Warnings/Errors:\n{stderr_output}\n"
            
            # Refresh map canvas if available
            if self.iface:
                self.iface.mapCanvas().refresh()
            
            self.execution_completed.emit(result, True)
            
        except Exception as e:
            error_msg = f"Execution error: {str(e)}\n"
            error_msg += f"Traceback:\n{traceback.format_exc()}"
            self.execution_completed.emit(error_msg, False)
            
        finally:
            # Restore stdout and stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def execute_gemini_response(self, response_text):
        """Extract and execute code from QGIS Copilot response"""
        code_blocks = self.extract_code_blocks(response_text)
        
        if not code_blocks:
            self.execution_completed.emit(
                "No executable code found in the response.", 
                False
            )
            return
        
        # Execute each code block
        for i, code in enumerate(code_blocks):
            if len(code_blocks) > 1:
                result_msg = f"Executing code block {i+1}/{len(code_blocks)}:\n"
                self.execution_completed.emit(result_msg, True)
            
            self.execute_code(code.strip())
    
    def get_available_functions(self):
        """Get list of available QGIS functions for context"""
        functions = []
        
        # Add iface methods
        if self.iface:
            iface_methods = [method for method in dir(self.iface) 
                           if not method.startswith('_') and callable(getattr(self.iface, method))]
            functions.extend([f"iface.{method}" for method in iface_methods[:10]])  # Limit for brevity
        
        # Add project methods
        project = QgsProject.instance()
        project_methods = [method for method in dir(project) 
                          if not method.startswith('_') and callable(getattr(project, method))]
        functions.extend([f"project.{method}" for method in project_methods[:10]])
        
        return functions