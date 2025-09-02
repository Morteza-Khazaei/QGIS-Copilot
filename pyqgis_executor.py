"""
Enhanced PyQGIS Code Executor - Safely execute PyQGIS code with detailed logging
and feedback loop for AI improvements
"""

import re
import shutil
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
    QgsFeature, QgsGeometry, QgsField, QgsPointXY, QgsCoordinateReferenceSystem,
    edit
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QObject, pyqtSignal, QVariant, QSettings


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
        # Sticky task file path for iterative improvements until reset
        self._current_task_file = None
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
            'edit': edit,
            
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
        """Check if code is safe to execute (supports relaxed mode)."""
        # Read relaxed mode preference
        try:
            relaxed = QSettings().value("qgis_copilot/prefs/relaxed_safety", False, type=bool)
        except Exception:
            relaxed = False

        if relaxed:
            disallowed_patterns = [
                (r'\bexec\s*\(', "Use of 'exec' is not allowed."),
                (r'\beval\s*\(', "Use of 'eval' is not allowed."),
                (r'__import__', "Use of '__import__' is not allowed."),
                (r'import\s+subprocess', "'subprocess' is not allowed."),
                (r'from\s+subprocess', "'subprocess' is not allowed."),
                (r'\.(system|popen|call)\s*\(', "Shell/system calls are not allowed."),
            ]
        else:
            # Strict, default protections
            disallowed_patterns = [
                (r'import\s+os', "Importing 'os' is not allowed for security reasons."),
                (r'import\s+subprocess', "Importing 'subprocess' is not allowed for security reasons."),
                (r'import\s+sys', "Importing 'sys' is not allowed. Use the provided environment."),
                (r'from\s+os', "Importing from 'os' is not allowed."),
                (r'from\s+subprocess', "Importing from 'subprocess' is not allowed."),
                (r'\bexec\s*\(', "Use of 'exec' is not allowed."),
                (r'\beval\s*\(', "Use of 'eval' is not allowed."),
                (r'__import__', "Use of '__import__' is not allowed."),
                (r'open\s*\(', "File I/O with 'open' is not allowed."),
                (r'file\s*\(', "File I/O with 'file' is not allowed."),
                (r'\bcompile\s*\(', "Use of 'compile' is not allowed."),
                (r'\bglobals\s*\(', "Accessing 'globals()' is not allowed."),
                (r'\blocals\s*\(', "Accessing 'locals()' is not allowed."),
                (r'\bvars\s*\(', "Accessing 'vars()' is not allowed."),
                (r'\bdir\s*\(', "Use of 'dir()' is not allowed."),
                (r'\bdelattr\s*\(', "Use of 'delattr' is not allowed."),
                (r'\bsetattr\s*\(', "Use of 'setattr' is not allowed."),
                (r'\bhasattr\s*\(', "Use of 'hasattr' is not allowed."),
                (r'\breload\s*\(', "Use of 'reload' is not allowed."),
                (r'\binput\s*\(', "Use of 'input()' is not allowed for security."),
                (r'\braw_input\s*\(', "Use of 'raw_input()' is not allowed for security."),
                (r'\.(system|popen|call)\s*\(', "Shell/system calls are not allowed."),
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
    
    def _slugify(self, text: str, default: str = "qgis_task") -> str:
        """Create a filesystem-friendly slug from text."""
        try:
            text = (text or "").strip().lower()
            if not text:
                return default
            # Replace non-alphanumerics with underscores
            text = re.sub(r"[^a-z0-9]+", "_", text)
            # Collapse duplicates and trim
            text = re.sub(r"_+", "_", text).strip("_")
            return text or default
        except Exception:
            return default

    def _build_task_filepath(self, workspace_dir: str, filename_hint: str = None) -> str:
        """Build a stable task file path (no timestamp) from hint.

        The file remains the same across iterations until reset_task_file() is called.
        """
        slug = self._slugify(filename_hint or "qgis_task")
        return os.path.join(workspace_dir, f"{slug}.py")

    def _ensure_task_file(self, filename_hint: str = None) -> str:
        """Return the sticky task file path, creating/setting it if needed."""
        if self._current_task_file and isinstance(self._current_task_file, str):
            return self._current_task_file
        workspace_dir = self.get_workspace_dir()
        fpath = self._build_task_filepath(workspace_dir, filename_hint)
        # Set sticky file; creation happens on first write
        self._current_task_file = fpath
        return fpath

    def reset_task_file(self):
        """Clear the sticky task file so the next run can choose a new one."""
        self._current_task_file = None

    def get_current_task_file(self):
        """Return the current sticky task file path, if any."""
        return self._current_task_file

    def finalize_task_as(self, filename_slug: str) -> str:
        """Copy the current task file to a final named file in the workspace.

        Returns the destination path. Raises if no current task file exists.
        """
        if not self._current_task_file or not os.path.exists(self._current_task_file):
            raise FileNotFoundError("No current task file to save.")
        workspace = self.get_workspace_dir()
        base_slug = self._slugify(filename_slug or "qgis_task")
        dest = os.path.join(workspace, f"{base_slug}.py")
        # Avoid overwriting: append numeric suffix
        if os.path.exists(dest):
            i = 1
            while True:
                alt = os.path.join(workspace, f"{base_slug}_{i}.py")
                if not os.path.exists(alt):
                    dest = alt
                    break
                i += 1
        shutil.copyfile(self._current_task_file, dest)
        return dest

    def save_response_to_task_file(self, response_text: str, filename_hint: str = None) -> str:
        """Merge response code blocks and save to the sticky task file.

        Returns the saved file path. Raises on failure.
        """
        code_blocks = self.extract_code_blocks(response_text)
        if not code_blocks:
            raise ValueError("No executable code found in the response.")
        fpath = self._ensure_task_file(filename_hint)
        merged = ("\n\n# --- QGIS Copilot code block separator ---\n\n").join(cb.strip() for cb in code_blocks).strip()
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(merged)
        # Log save event
        saved_log = ExecutionLog(
            code=f"# File saved: {fpath}",
            success=True,
            output=f"Saved task script to: {fpath}",
            execution_time=0,
        )
        self.add_to_history(saved_log)
        return fpath

    def execute_task_file(self, file_path: str):
        """Execute a script from the given file path via wrapper (reads file at runtime)."""
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                original_code = fh.read()
        except Exception as e:
            err = f"Failed to read script file: {e}"
            execution_log = ExecutionLog(
                code="",
                success=False,
                output="",
                error_msg=err,
                execution_time=0
            )
            self.add_to_history(execution_log)
            self.execution_completed.emit(err, False, execution_log)
            return

        # Best-effort: Open the script in the QGIS Python Console editor
        try:
            if self.iface and hasattr(self.iface, 'actionShowPythonDialog'):
                self.iface.actionShowPythonDialog().trigger()
        except Exception:
            pass
        try:
            import qgis.utils as qutils
            pc = None
            if hasattr(qutils, 'plugins') and isinstance(qutils.plugins, dict):
                pc = qutils.plugins.get('PythonConsole')
            for meth in ('openFileInEditor', 'loadScript', 'addToEditor', 'openScriptFile'):
                if pc and hasattr(pc, meth):
                    try:
                        getattr(pc, meth)(file_path)
                        break
                    except Exception:
                        pass
            # Best-effort: try to directly execute the script from the console plugin
            for run_meth in ('runScriptFile', 'execScriptFile', 'executeScriptFile', 'runFile'):
                if pc and hasattr(pc, run_meth):
                    try:
                        getattr(pc, run_meth)(file_path)
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        wrapper_cmd = (
            "from pathlib import Path\n"
            "import qgis\n"
            "from qgis.PyQt.QtCore import QVariant as _QVariant\n"
            "import qgis.core as _qcore\n"
            "setattr(_qcore, 'QVariant', _QVariant)\n"
            f"__code__ = Path(r'{file_path}').read_text()\n"
            f"exec(compile(__code__, r'{file_path}', 'exec'), globals())"
        )
        preface = (
            f"Executing saved script: {file_path}\n"
        )
        notice_log = ExecutionLog(code=f"# File: {file_path}", success=True, output=preface, execution_time=0)
        self.add_to_history(notice_log)
        self._execute_raw_with_wrapper(original_code=original_code, wrapper_code=wrapper_cmd)

    def execute_gemini_response(self, response_text, filename_hint: str = None):
        """Extract, save, and execute code from QGIS Copilot response.

        If multiple fenced code blocks are present, merge them into a single
        script to keep a single runnable output per response.
        """
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
        
        # Save merged code for this task under a distinct filename
        try:
            fpath = self._ensure_task_file(filename_hint)
            merged = ("\n\n# --- QGIS Copilot code block separator ---\n\n").join(cb.strip() for cb in code_blocks).strip()
            with open(fpath, 'w', encoding='utf-8') as fh:
                fh.write(merged)
            # Log save event
            saved_log = ExecutionLog(
                code=f"# File saved: {fpath}",
                success=True,
                output=f"Saved task script to: {fpath}",
                execution_time=0,
            )
            self.add_to_history(saved_log)
        except Exception:
            pass

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

    def execute_response_via_console(self, response_text, filename_hint: str = None):
        """Extract code, write to a task-named script, open in QGIS Python editor, and run via exec(Path(...).read_text())."""
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

        # Merge all code blocks to keep a single script file for iterative improvements
        merged = ("\n\n# --- QGIS Copilot code block separator ---\n\n").join(cb.strip() for cb in code_blocks).strip()
        # Light cleanup to avoid common pitfalls
        # - Remove incorrect iface import (iface is provided by QGIS and injected)
        merged = re.sub(r"^\s*from\s+qgis\.gui\s+import\s+iface\s*$", "", merged, flags=re.MULTILINE)
        merged_code = merged

        # Write to a stable file path in the workspace
        try:
            fpath = self._ensure_task_file(filename_hint)
            compat_header = (
                "# QGIS Copilot compatibility header (QVariant shim for QGIS 3)\n"
                "try:\n"
                "    import qgis\n"
                "    import qgis.core as _qcore\n"
                "    from qgis.PyQt.QtCore import QVariant as _QVariant\n"
                "    if not hasattr(_qcore, 'QVariant'):\n"
                "        setattr(_qcore, 'QVariant', _QVariant)\n"
                "except Exception:\n"
                "    pass\n\n"
            )
            with open(fpath, 'w', encoding='utf-8') as fh:
                fh.write(compat_header)
                fh.write(merged_code)

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
                for meth in ('openFileInEditor', 'loadScript', 'addToEditor', 'openScriptFile'):
                    if pc and hasattr(pc, meth):
                        try:
                            getattr(pc, meth)(fpath)
                            break
                        except Exception:
                            pass
                # Best-effort: try to directly execute the script from the console plugin
                for run_meth in ('runScriptFile', 'execScriptFile', 'executeScriptFile', 'runFile'):
                    if pc and hasattr(pc, run_meth):
                        try:
                            getattr(pc, run_meth)(fpath)
                            break
                        except Exception:
                            pass
                try:
                    console = getattr(pc, 'console', None)
                    if console and hasattr(console, 'runCommand'):
                        console.runCommand(f"from pathlib import Path; exec(Path(r'{fpath}').read_text())")
                except Exception:
                    pass
            except Exception:
                pass

            # Build and run the exec command with a QVariant shim
            wrapper_cmd = (
                "from pathlib import Path\n"
                "import qgis\n"
                "from qgis.PyQt.QtCore import QVariant as _QVariant\n"
                "import qgis.core as _qcore\n"
                "setattr(_qcore, 'QVariant', _QVariant)\n"
                f"__code__ = Path(r'{fpath}').read_text()\n"
                f"exec(compile(__code__, r'{fpath}', 'exec'), globals())"
            )
            preface = (
                f"Script saved to workspace: {fpath}\n"
                f"Executing via:\n{wrapper_cmd}\n"
            )
            separator_log = ExecutionLog(
                code=f"# File: {fpath}",
                success=True,
                output=preface,
                execution_time=0
            )
            self.add_to_history(separator_log)
            self._execute_raw_with_wrapper(original_code=merged_code, wrapper_code=wrapper_cmd)
        except Exception as e:
            err = f"Failed to write or execute script: {e}"
            execution_log = ExecutionLog(
                code=merged_code,
                success=False,
                output="",
                error_msg=err,
                execution_time=0
            )
            self.add_to_history(execution_log)
            self.execution_completed.emit(err, False, execution_log)

    def get_workspace_dir(self):
        """Get or create the workspace directory where scripts are saved."""
        try:
            settings = QSettings()
            configured = settings.value("qgis_copilot/workspace_dir", type=str)
            if configured and isinstance(configured, str) and configured.strip():
                path = configured
            else:
                # Default to a 'workspace' folder inside the plugin directory
                plugin_root = os.path.dirname(__file__)
                path = os.path.join(plugin_root, "workspace")
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            # Fallback to temp directory on any error
            return tempfile.gettempdir()

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
            # Execute the wrapper using a fully augmented environment
            env = dict(self.globals)
            env['iface'] = self.iface
            try:
                import qgis.core as _qcore
                env['core'] = _qcore  # allow scripts that erroneously reference core.QgsPointXY
            except Exception:
                pass
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
