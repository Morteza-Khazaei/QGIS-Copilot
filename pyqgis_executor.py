"""
Enhanced PyQGIS Code Executor - Safely execute PyQGIS code with detailed logging
and feedback loop for AI improvements
"""

import re
import sys
import traceback
import time
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
import tempfile
import os
from pathlib import Path

from qgis.core import (
    QgsProject, QgsApplication, QgsMessageLog, Qgis,
    QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsWkbTypes,
    QgsFeature, QgsGeometry, QgsField, QgsPointXY, QgsCoordinateReferenceSystem
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal, QVariant


class ExecutionLog:
    """Class to store execution details"""
    def __init__(self, code, success, output, error_msg=None, execution_time=0):
        self.timestamp = datetime.now()
        self.code = code
        self.success = success
        self.output = output
        self.error_msg = error_msg
        self.execution_time = execution_time
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'code': self.code,
            'success': self.success,
            'output': self.output,
            'error_msg': self.error_msg,
            'execution_time': self.execution_time
        }
    
    def get_formatted_log(self):
        """Get a formatted log entry for display"""
        status = "✅ SUCCESS" if self.success else "❌ ERROR"
        time_str = self.timestamp.strftime("%H:%M:%S")
        
        log = f"[{time_str}] {status} (execution time: {self.execution_time:.3f}s)\n"
        
        if self.code:
            log += f"CODE:\n{self.code}\n"
        
        if self.output:
            log += f"OUTPUT:\n{self.output}\n"
        
        if not self.success and self.error_msg:
            log += f"ERROR:\n{self.error_msg}\n"
        
        log += "-" * 50 + "\n"
        return log


class EnhancedPyQGISExecutor(QObject):
    """Enhanced executor with detailed logging and AI feedback capabilities"""
    
    execution_completed = pyqtSignal(str, bool, object)  # result, success, execution_log
    logs_updated = pyqtSignal(str)  # formatted log string
    improvement_suggested = pyqtSignal(str, str)  # original_code, suggested_improvement
    
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.execution_history = []  # Store ExecutionLog objects
        self.max_history = 50  # Keep last 50 executions
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
            'QgsFeature': QgsFeature,
            'QgsGeometry': QgsGeometry,
            'QgsField': QgsField,
            'QgsPointXY': QgsPointXY,
            'QgsCoordinateReferenceSystem': QgsCoordinateReferenceSystem,
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
        disallowed_patterns = [
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
        """Execute PyQGIS code safely with detailed logging"""
        original_code = code
        # Pre-process code to remove redundant/incorrect QGIS imports that the AI might add.
        # The execution environment provides all necessary QGIS modules and classes globally,
        # so these imports are unnecessary and can sometimes be incorrect (e.g., from qgis.core import QVariant).
        lines = code.split('\n')
        cleaned_lines = []
        in_qgis_import_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('from qgis.') and 'import' in stripped:
                if stripped.endswith('('):
                    in_qgis_import_block = True
                # This is a qgis import line, skip it
                continue
            
            if in_qgis_import_block:
                if ')' in stripped:
                    in_qgis_import_block = False
                # This is inside a qgis import block, skip it
                continue

            if stripped == 'import qgis':
                continue
            
            cleaned_lines.append(line)
        code = '\n'.join(cleaned_lines)

        start_time = time.time()
        
        # Check if code is safe
        is_safe, safety_msg = self.is_safe_code(code)
        if not is_safe:
            execution_log = ExecutionLog(
                code=original_code,
                success=False,
                output="",
                error_msg=f"Execution blocked. {safety_msg}",
                execution_time=0
            )
            self.add_to_history(execution_log)
            self.execution_completed.emit(
                f"Execution blocked. {safety_msg}",
                False,
                execution_log
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
            
            execution_time = time.time() - start_time
            
            # Prepare result message
            result = "Code executed successfully.\n"
            output_text = ""
            
            if stdout_output:
                result += f"Output:\n{stdout_output}\n"
                output_text += stdout_output
            if stderr_output:
                result += f"Warnings/Errors:\n{stderr_output}\n"
                output_text += f"\nWarnings: {stderr_output}" if stdout_output else stderr_output
            
            # Create execution log
            execution_log = ExecutionLog(
                code=original_code,
                success=True,
                output=output_text,
                execution_time=execution_time
            )
            
            self.add_to_history(execution_log)
            
            # Refresh map canvas if available
            if self.iface:
                self.iface.mapCanvas().refresh()
            
            self.execution_completed.emit(result, True, execution_log)
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution error: {str(e)}\n"
            error_msg += f"Traceback:\n{traceback.format_exc()}"
            
            # Create execution log
            execution_log = ExecutionLog(
                code=original_code,
                success=False,
                output="",
                error_msg=error_msg,
                execution_time=execution_time
            )
            
            self.add_to_history(execution_log)
            self.execution_completed.emit(error_msg, False, execution_log)
            
        finally:
            # Restore stdout and stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def add_to_history(self, execution_log):
        """Add execution log to history and emit update signal"""
        self.execution_history.append(execution_log)
        
        # Keep only recent history
        if len(self.execution_history) > self.max_history:
            self.execution_history = self.execution_history[-self.max_history:]
        
        # Emit log update
        self.logs_updated.emit(execution_log.get_formatted_log())
    
    def get_execution_context_for_ai(self, last_n_executions=3):
        """Get execution context to send back to AI for improvements"""
        if not self.execution_history:
            return "No previous execution history available."
        
        recent_logs = self.execution_history[-last_n_executions:]
        context = "RECENT EXECUTION HISTORY:\n"
        context += "=" * 50 + "\n"
        
        for i, log in enumerate(recent_logs, 1):
            context += f"EXECUTION #{i}:\n"
            context += f"Timestamp: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            context += f"Success: {'Yes' if log.success else 'No'}\n"
            context += f"Execution Time: {log.execution_time:.3f}s\n"
            context += f"Code:\n{log.code}\n"
            
            if log.output:
                context += f"Output:\n{log.output}\n"
            
            if not log.success and log.error_msg:
                context += f"Error Details:\n{log.error_msg}\n"
            
            context += "-" * 30 + "\n"
        
        # Add analysis of common issues
        failed_executions = [log for log in recent_logs if not log.success]
        if failed_executions:
            context += "\nCOMMON ISSUES DETECTED:\n"
            error_patterns = {}
            for log in failed_executions:
                if log.error_msg:
                    # Extract error type
                    error_lines = log.error_msg.split('\n')
                    for line in error_lines:
                        if 'Error:' in line or 'Exception:' in line:
                            error_type = line.split(':')[0].strip().split()[-1]
                            error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
            
            for error_type, count in error_patterns.items():
                context += f"- {error_type}: {count} occurrence(s)\n"
        
        return context
    
    def get_all_logs_formatted(self):
        """Get all execution logs as formatted string"""
        if not self.execution_history:
            return "No execution logs available."
        
        all_logs = ""
        for log in self.execution_history:
            all_logs += log.get_formatted_log()
        
        return all_logs
    
    def get_statistics(self):
        """Get execution statistics"""
        if not self.execution_history:
            return "No execution statistics available."
        
        total = len(self.execution_history)
        successful = len([log for log in self.execution_history if log.success])
        failed = total - successful
        
        avg_time = sum(log.execution_time for log in self.execution_history) / total
        
        stats = f"EXECUTION STATISTICS:\n"
        stats += f"Total Executions: {total}\n"
        stats += f"Successful: {successful} ({successful/total*100:.1f}%)\n"
        stats += f"Failed: {failed} ({failed/total*100:.1f}%)\n"
        stats += f"Average Execution Time: {avg_time:.3f}s\n"
        
        if self.execution_history:
            last_execution = self.execution_history[-1]
            stats += f"Last Execution: {last_execution.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            stats += f"Last Status: {'Success' if last_execution.success else 'Failed'}\n"
        
        return stats
    
    def clear_history(self):
        """Clear execution history"""
        self.execution_history.clear()
        self.logs_updated.emit("Execution history cleared.\n")
    
    def execute_gemini_response(self, response_text):
        """Extract and execute code from QGIS Copilot response"""
        code_blocks = self.extract_code_blocks(response_text)
        
        if not code_blocks:
            execution_log = ExecutionLog(
                code="",
                success=False,
                output="",
                error_msg="No executable code found in the response.",
                execution_time=0
            )
            self.execution_completed.emit(
                "No executable code found in the response.", 
                False,
                execution_log
            )
            return
        
        # Execute each code block
        for i, code in enumerate(code_blocks):
            if len(code_blocks) > 1:
                result_msg = f"Executing code block {i+1}/{len(code_blocks)}:\n"
                # Create a simple log for the block separator
                separator_log = ExecutionLog(
                    code=f"# Block {i+1}/{len(code_blocks)}",
                    success=True,
                    output=result_msg,
                    execution_time=0
                )
                self.execution_completed.emit(result_msg, True, separator_log)
            
            self.execute_code(code.strip())

    def execute_response_via_console(self, response_text):
        """Extract code, write to temp files, open in QGIS Python editor, and run via exec(Path(...).read_text())."""
        code_blocks = self.extract_code_blocks(response_text)

        if not code_blocks:
            execution_log = ExecutionLog(
                code="",
                success=False,
                output="",
                error_msg="No executable code found in the response.",
                execution_time=0
            )
            self.execution_completed.emit(
                "No executable code found in the response.",
                False,
                execution_log
            )
            return

        for i, code in enumerate(code_blocks):
            # Write to temp file
            try:
                tmp_dir = tempfile.gettempdir()
                fname = f"qgis_copilot_{int(time.time()*1000)}_{i+1}.py"
                fpath = os.path.join(tmp_dir, fname)
                with open(fpath, 'w', encoding='utf-8') as fh:
                    fh.write(code.strip())

                # Try to open the Python console and load the script in the editor (best-effort)
                try:
                    if self.iface and hasattr(self.iface, 'actionShowPythonDialog'):
                        self.iface.actionShowPythonDialog().trigger()
                except Exception as e:
                    QgsMessageLog.logMessage(f"Could not open Python Console automatically: {e}", "QGIS Copilot", level=Qgis.Warning)

                # Attempt to open in console editor via internal plugin if exposed
                try:
                    import qgis.utils as qutils
                    pc = None
                    if hasattr(qutils, 'plugins') and isinstance(qutils.plugins, dict):
                        pc = qutils.plugins.get('PythonConsole')
                    # Try common method names defensively
                    for meth in ('openFileInEditor', 'loadScript', 'addToEditor', 'openScriptFile'):
                        if pc and hasattr(pc, meth):
                            try:
                                getattr(pc, meth)(fpath)
                                break
                            except Exception:
                                pass
                except Exception:
                    pass

                # Build and run the exec command to mirror console behavior
                wrapper_cmd = f"from pathlib import Path\nexec(Path(r'{fpath}').read_text())"
                # Informative preface entry for logs/live panel
                preface = (
                    f"Temp script created: {fpath}\n"
                    f"Executing via:\n{wrapper_cmd}\n"
                )
                separator_log = ExecutionLog(
                    code=f"# File: {fpath}",
                    success=True,
                    output=preface,
                    execution_time=0
                )
                self.add_to_history(separator_log)
                # Execute using the standard executor but bypass import cleanup and keep original code in logs
                self._execute_raw_with_wrapper(original_code=code, wrapper_code=wrapper_cmd)
            except Exception as e:
                err = f"Failed to write or execute temp script: {e}"
                execution_log = ExecutionLog(
                    code=code,
                    success=False,
                    output="",
                    error_msg=err,
                    execution_time=0
                )
                self.add_to_history(execution_log)
                self.execution_completed.emit(err, False, execution_log)

    def _execute_raw_with_wrapper(self, original_code, wrapper_code):
        """Execute wrapper_code with stdout/stderr capture while logging original_code as CODE."""
        start_time = time.time()

        # Safety check against dangerous ops based on the original code
        is_safe, safety_msg = self.is_safe_code(original_code)
        if not is_safe:
            execution_log = ExecutionLog(
                code=original_code,
                success=False,
                output="",
                error_msg=f"Execution blocked. {safety_msg}",
                execution_time=0
            )
            self.add_to_history(execution_log)
            self.execution_completed.emit(
                f"Execution blocked. {safety_msg}",
                False,
                execution_log
            )
            return

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            # Execute the wrapper using a minimally augmented environment
            env = {'iface': self.iface}
            exec(wrapper_code, env)

            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()

            execution_time = time.time() - start_time
            result = "Code executed successfully.\n"
            output_text = ""
            if stdout_output:
                result += f"Output:\n{stdout_output}\n"
                output_text += stdout_output
            if stderr_output:
                result += f"Warnings/Errors:\n{stderr_output}\n"
                output_text += f"\nWarnings: {stderr_output}" if stdout_output else stderr_output

            execution_log = ExecutionLog(
                code=original_code,
                success=True,
                output=output_text,
                execution_time=execution_time
            )
            self.add_to_history(execution_log)
            if self.iface:
                self.iface.mapCanvas().refresh()
            self.execution_completed.emit(result, True, execution_log)
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution error: {str(e)}\n"
            error_msg += f"Traceback:\n{traceback.format_exc()}"
            execution_log = ExecutionLog(
                code=original_code,
                success=False,
                output="",
                error_msg=error_msg,
                execution_time=execution_time
            )
            self.add_to_history(execution_log)
            self.execution_completed.emit(error_msg, False, execution_log)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    
    def suggest_improvement(self, failed_execution_log):
        """Analyze failed execution and suggest improvements to AI"""
        if not failed_execution_log or failed_execution_log.success:
            return
        
        # Create improvement suggestion based on error pattern
        suggestion = "The previous code execution failed. Please analyze the error and provide a complete, corrected, and executable script.\n\n"
        suggestion += f"Failed Code:\n```python\n{failed_execution_log.code}\n```\n\n"
        suggestion += f"Error Details:\n```\n{failed_execution_log.error_msg}\n```\n\n"
        suggestion += "Your task is to provide a new version of the script that fixes the error. Do not just explain the problem."
        
        self.improvement_suggested.emit(failed_execution_log.code, suggestion)
    
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
