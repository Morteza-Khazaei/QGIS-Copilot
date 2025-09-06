"""
Enhanced PyQGIS Code Executor - Safely execute PyQGIS code with detailed logging
and feedback loop for AI improvements
"""

import re
import ast
import difflib
import shutil
import sys
import traceback
import time
import inspect
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
from qgis.PyQt.QtCore import QObject, pyqtSignal, QVariant, QSettings
import json
from .ai.utils.pyqgis_api_validator import PyQGISAPIValidator
# Lightweight local log no-ops to avoid external deps
def _log_info(*a, **k):
    return None
def _log_warn(*a, **k):
    return None


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
        # Build validator using the execution globals
        try:
            self.validator = PyQGISAPIValidator(self.globals)
            self.validator.build_api_cache()
        except Exception:
            self.validator = None
    
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
            # Guarded call helper (local)
            'safe_call': self._safe_call,
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
        # Look for code blocks marked with ```python/```/~~~ with permissive newlines
        fence = r"```|~~~"
        python_code_pattern = rf'(?:{fence})(?:python|py)?[ \t]*\r?\n([\s\S]*?)\r?\n?(?:{fence})'
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

    # Removed: _extract_json_spec_from_response, render_layout_spec (DSL removed)
    
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
        # Pre-process QGIS imports consistently
        code = self._clean_qgis_imports(code)

        # Manifest preflight removed — proceed to API validation only

        # Run API validation and optionally gate execution (Strict Mode)
        try:
            if self.validator:
                res = self.validator.validate_code_comprehensively(code)
                strict = QSettings().value("qgis_copilot/prefs/strict_validation", False, type=bool)
                msgs = []
                if not res.get('syntax_valid', True):
                    for m in res.get('syntax_errors', []):
                        msgs.append(f"Syntax: {m}")
                for e in res.get('attribute_errors', []):
                    base = e.get('error', '')
                    sugg = e.get('suggestions') or []
                    hint = f" — try: {', '.join(sugg)}" if sugg else ""
                    msgs.append(f"Attribute: {base}{hint}")
                for e in res.get('method_errors', []):
                    base = e.get('error', '')
                    sugg = e.get('suggestions') or []
                    hint = f" — suggestions: {', '.join(sugg)}" if sugg else ""
                    msgs.append(f"Method: {base}{hint}")
                for w in res.get('warnings', []):
                    msgs.append(f"Warning: {w}")
                if msgs:
                    out = "Pre-execution validation:\n" + "\n".join(msgs)
                    self.add_to_history(ExecutionLog(code="", success=True, output=out, execution_time=0))
                # If Strict Mode and there are real errors, block execution
                if strict and (not res.get('syntax_valid', True) or res.get('attribute_errors') or res.get('method_errors')):
                    msg = "Execution blocked by Strict Validation. Fix issues and retry."
                    self.add_to_history(ExecutionLog(code=original_code, success=False, output="", error_msg=msg, execution_time=0))
                    self.execution_completed.emit(msg, False, self.execution_history[-1])
                    return
        except Exception:
            pass

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
        
        # Capture stdout and stderr and execute compiled code with a proper filename
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        # Use the current task file, if any, for better tracebacks
        try:
            code_filename = self._current_task_file or '<in-memory>'
        except Exception:
            code_filename = '<in-memory>'

        try:
            compiled = compile(code, code_filename, 'exec')
        except SyntaxError as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution error: {e}\nTraceback:\n{traceback.format_exc()}"
            execution_log = ExecutionLog(
                code=original_code,
                success=False,
                output="",
                error_msg=error_msg,
                execution_time=execution_time
            )
            self.add_to_history(execution_log)
            self.execution_completed.emit(error_msg, False, execution_log)
            return

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(compiled, self.globals)

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
            
            # Avoid forced canvas refresh to keep UI responsive; user can refresh as needed
            
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
        
        # Emit log update (redacted: do not include the full code in UI logs)
        try:
            self.logs_updated.emit(self.format_log_for_ui(execution_log))
        except Exception:
            # Fallback to minimal status line
            status = "✅ SUCCESS" if execution_log.success else "❌ ERROR"
            self.logs_updated.emit(f"{status} (execution time: {execution_log.execution_time:.3f}s)\n" + "-" * 50 + "\n")

    def format_log_for_ui(self, log: ExecutionLog) -> str:
        """Format a log entry for the UI/Log Messages without including the Python code body."""
        parts = []
        status = "✅ SUCCESS" if log.success else "❌ ERROR"
        parts.append(f"{status} (execution time: {log.execution_time:.3f}s)")
        if log.output:
            parts.append(f"OUTPUT:\n{log.output}")
        if not log.success and log.error_msg:
            parts.append(f"ERROR:\n{log.error_msg}")
        parts.append("-" * 50)
        return "\n".join(parts) + "\n"

    def _clean_qgis_imports(self, code: str) -> str:
        """Remove redundant/incorrect qgis imports; env already provides QGIS classes.

        - Drops any 'from qgis.* import ...' lines (including parenthesized blocks)
        - Drops plain 'import qgis' lines
        """
        lines = code.split('\n')
        cleaned_lines = []
        in_qgis_import_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('from qgis.') and 'import' in stripped:
                if stripped.endswith('('):
                    in_qgis_import_block = True
                # Skip this import line
                continue
            if in_qgis_import_block:
                if ')' in stripped:
                    in_qgis_import_block = False
                # Skip lines inside import block
                continue
            if stripped == 'import qgis':
                continue
            cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

    def _safe_call(self, obj, method, *args, **kw):
        """Local safe_call helper: provides a hint when a method is missing."""
        try:
            import difflib as _difflib
        except Exception:
            _difflib = None
        if not hasattr(obj, method):
            hint = []
            try:
                if _difflib is not None:
                    hint = _difflib.get_close_matches(method, dir(obj), n=1)
            except Exception:
                hint = []
            msg = f"{type(obj).__name__}.{method} not found."
            if hint:
                msg += f" Did you mean '{hint[0]}'?"
            raise AttributeError(msg)
        return getattr(obj, method)(*args, **kw)

    # Removed: _extract_header_json, _index_manifest (manifest removed)

    def _static_validate_code(self, code: str):
        """Lightweight static checks using live PyQGIS API via introspection.

        - Verifies attribute accesses like 'QgsFoo.Bar' against actual objects in self.globals
        - Flags obvious invalid imports still present
        - Notes unknown top-level names which are not provided by env/builtins
        Returns list of strings with findings.
        """
        findings = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            findings.append(f"Syntax error at L{e.lineno}: {e.msg}")
            return findings

        env = dict(self.globals)
        # Collect builtins for name resolution
        builtin_names = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))

        # Check imports of qgis.* still present
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] == 'qgis':
                        findings.append(f"Warning: redundant import '{alias.name}' will be ignored; QGIS objects are preloaded.")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ''
                if mod.startswith('qgis.'):
                    names = ', '.join(a.name for a in node.names)
                    findings.append(f"Warning: redundant import from '{mod}' ({names}) will be ignored; use preloaded classes.")

        # Attribute checks like 'QgsLayoutItemMap.attemptSetSize'
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                base = node.value.id
                attr = node.attr
                if base in env:
                    obj = env.get(base)
                    # Only check attributes on modules/classes, avoid instance-unknowns
                    try:
                        if hasattr(obj, '__mro__') or hasattr(obj, '__dict__') or hasattr(obj, '__spec__'):
                            if not hasattr(obj, attr):
                                # Suggest closest match
                                close = difflib.get_close_matches(attr, dir(obj), n=2)
                                hint = f" Did you mean '{close[0]}'?" if close else ""
                                findings.append(f"Error: '{base}.{attr}' does not exist.{hint}")
                    except Exception:
                        pass

        # Unknown top-level names used in Call contexts
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                    if name not in env and name not in builtin_names:
                        # Might be user-defined earlier in script; try to see if it's assigned before.
                        # Heuristic: only warn when name starts with 'Qgs' (likely API) or looks like module/class.
                        if name.startswith('Qgs'):
                            findings.append(f"Warning: '{name}' not found in environment; ensure it is defined or imported correctly.")

        # Simple type inference: x = QgsClass(...)
        var_types = self._infer_simple_types(tree, env)

        # Validate method calls and their signatures
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Instance method: var.method(...)
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                var_name = func.value.id
                method_name = func.attr
                cls = var_types.get(var_name)
                if cls is not None:
                    if not hasattr(cls, method_name):
                        close = difflib.get_close_matches(method_name, dir(cls), n=2)
                        hint = f" Did you mean '{close[0]}'?" if close else ""
                        findings.append(f"Error: '{cls.__name__}.{method_name}' does not exist.{hint}")
                        continue
                    method_obj = getattr(cls, method_name)
                    findings.extend(self._validate_call_signature(node, method_obj, bound_instance=True, owner_name=cls.__name__))
            # Class/module attribute call: QgsProject.instance(...)
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                base = func.value.id
                method_name = func.attr
                if base in env:
                    obj = env[base]
                    if hasattr(obj, method_name):
                        method_obj = getattr(obj, method_name)
                        findings.extend(self._validate_call_signature(node, method_obj, bound_instance=False, owner_name=base))

        return findings

    def _infer_simple_types(self, tree, env):
        """Infer variable names assigned from known QGIS class constructors.

        Returns dict: var_name -> class_object
        """
        var_types = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if not targets:
                    continue
                callee = node.value.func
                cls_obj = None
                if isinstance(callee, ast.Name) and callee.id in env:
                    cand = env.get(callee.id)
                    try:
                        if inspect.isclass(cand):
                            cls_obj = cand
                    except Exception:
                        pass
                elif isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                    base = callee.value.id
                    if base in env:
                        try:
                            cand = getattr(env[base], callee.attr, None)
                            if inspect.isclass(cand):
                                cls_obj = cand
                        except Exception:
                            pass
                if cls_obj is not None:
                    for n in targets:
                        var_types[n] = cls_obj
        return var_types

    def _validate_call_signature(self, call_node: ast.Call, method_obj, bound_instance: bool, owner_name: str):
        """Validate ast.Call against an inspectable signature.

        - bound_instance: True if method will be invoked on an instance (drop leading self)
        Returns list of issue strings.
        """
        issues = []
        try:
            sig = inspect.signature(method_obj)
        except Exception:
            return issues

        params = list(sig.parameters.values())
        if bound_instance and params and params[0].kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            # Drop 'self' for instance-bound calls
            params = params[1:]

        # Required positional params without defaults
        required_pos = [p for p in params
                        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                        and p.default is inspect._empty]
        provided_pos = len(call_node.args)

        # Keyword-only params
        required_kwonly = [p for p in params if p.kind == inspect.Parameter.KEYWORD_ONLY and p.default is inspect._empty]
        provided_kw_names = {kw.arg for kw in call_node.keywords if kw.arg}

        if provided_pos < len(required_pos):
            issues.append(
                f"Warning: '{owner_name}.{getattr(method_obj, '__name__', str(method_obj))}' expects at least {len(required_pos)} positional argument(s) (excluding self); got {provided_pos}."
            )

        valid_kw_names = {p.name for p in params if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
        unknown = provided_kw_names - valid_kw_names
        for bad in unknown:
            close = difflib.get_close_matches(bad, list(valid_kw_names), n=1)
            hint = f" Did you mean '{close[0]}'?" if close else ""
            issues.append(f"Warning: unknown keyword '{bad}' for '{owner_name}.{getattr(method_obj, '__name__', str(method_obj))}'.{hint}")

        missing_kwonly = [p.name for p in required_kwonly if p.name not in provided_kw_names]
        if missing_kwonly:
            issues.append(
                f"Warning: missing required keyword-only argument(s) {missing_kwonly} for '{owner_name}.{getattr(method_obj, '__name__', str(method_obj))}'."
            )

        return issues
    
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

    def save_response_to_task_file(self, response_text: str, filename_hint: str = None, quiet: bool = False) -> str:
        """Merge response code blocks and save to the sticky task file.

        - Returns the saved file path. Raises on failure if no code found.
        - If `quiet` is True, suppresses save logs and "up-to-date" notices.
        - Writes only when content changed to avoid unnecessary saves.
        """
        code_blocks = self.extract_code_blocks(response_text)
        if not code_blocks:
            raise ValueError("No executable code found in the response.")
        fpath = self._ensure_task_file(filename_hint)
        merged = ("\n\n# --- QGIS Copilot code block separator ---\n\n").join(cb.strip() for cb in code_blocks).strip()

        # Only write if file is missing or content changed
        need_write = True
        try:
            if os.path.exists(fpath):
                with open(fpath, 'r', encoding='utf-8') as fh:
                    existing = fh.read()
                need_write = (existing != merged)
        except Exception:
            need_write = True

        if need_write:
            with open(fpath, 'w', encoding='utf-8') as fh:
                fh.write(merged)
            if not quiet:
                saved_log = ExecutionLog(
                    code=f"# File saved: {fpath}",
                    success=True,
                    output=f"Saved task script to: {fpath}",
                    execution_time=0,
                )
                self.add_to_history(saved_log)
        else:
            if not quiet:
                info_log = ExecutionLog(
                    code=f"# File up-to-date: {fpath}",
                    success=True,
                    output=f"Task script already up-to-date: {fpath}",
                    execution_time=0,
                )
                self.add_to_history(info_log)

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

        # Pre-validate and optionally gate execution
        try:
            if self.validator:
                res = self.validator.validate_code_comprehensively(original_code)
                strict = QSettings().value("qgis_copilot/prefs/strict_validation", False, type=bool)
                msgs = []
                if not res.get('syntax_valid', True):
                    for m in res.get('syntax_errors', []):
                        msgs.append(f"Syntax: {m}")
                for e in res.get('attribute_errors', []):
                    base = e.get('error', '')
                    sugg = e.get('suggestions') or []
                    hint = f" — try: {', '.join(sugg)}" if sugg else ""
                    msgs.append(f"Attribute: {base}{hint}")
                for e in res.get('method_errors', []):
                    base = e.get('error', '')
                    sugg = e.get('suggestions') or []
                    hint = f" — suggestions: {', '.join(sugg)}" if sugg else ""
                    msgs.append(f"Method: {base}{hint}")
                for w in res.get('warnings', []):
                    msgs.append(f"Warning: {w}")
                if msgs:
                    self.add_to_history(ExecutionLog(code="", success=True, output="Pre-execution validation:\n"+"\n".join(msgs), execution_time=0))
                if strict and (not res.get('syntax_valid', True) or res.get('attribute_errors') or res.get('method_errors')):
                    msg = f"Execution blocked by Strict Validation for file: {file_path}"
                    self.add_to_history(ExecutionLog(code=original_code, success=False, output="", error_msg=msg, execution_time=0))
                    self.execution_completed.emit(msg, False, self.execution_history[-1])
                    return
        except Exception:
            pass

        # Do not open the QGIS Python Console editor automatically — avoid UI overhead

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

    # Removed: execute_gemini_response (unused)
    def execute_gemini_response(self, *args, **kwargs):
        raise NotImplementedError("execute_gemini_response is removed")

    def execute_response_via_console(self, *args, **kwargs):
        raise NotImplementedError("execute_response_via_console is removed")

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
            # Avoid forced canvas refresh to keep UI responsive
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
            # Streams auto-restored by context managers
            pass
    
    def suggest_improvement(self, failed_execution_log):
        """Analyze failed execution and suggest improvements to AI"""
        if not failed_execution_log or failed_execution_log.success:
            return
        # Create improvement suggestion with API context when available
        error_msg = failed_execution_log.error_msg or ""
        code = failed_execution_log.code or ""

        api_help = ""
        try:
            if self.validator:
                # Heuristic: extract Class and attribute from common error patterns
                import re as _re
                m = _re.search(r"'(?P<class>Qgs\w+)' object has no attribute '(?P<attr>\w+)'", error_msg)
                if not m:
                    m = _re.search(r"(?P<class>Qgs\w+)\.(?P<attr>\w+)\(\) does not exist", error_msg)
                if m:
                    cls = m.group('class')
                    attr = m.group('attr')
                    # Build API cache if needed
                    self.validator.build_api_cache()
                    info = self.validator.api_cache.get(cls)
                    if info:
                        methods = info.get('methods', {})
                        # If exact method exists, include its signature; else show close suggestions
                        if attr in methods and methods[attr].get('signature') is not None:
                            sig = methods[attr]['signature']
                            doc = methods[attr].get('docstring') or ''
                            first = doc.split('\n')[0] if doc else ''
                            api_help = f"CORRECT API USAGE:\n{cls}.{attr}{sig}\n"
                            if first:
                                api_help += f"\nNote: {first}\n"
                        else:
                            close = difflib.get_close_matches(attr, methods.keys(), n=3, cutoff=0.6)
                            if close:
                                api_help = "Method not found. Did you mean:\n  - " + "\n  - ".join(close) + "\n"
        except Exception:
            pass

        suggestion = "SPECIFIC FIX NEEDED:\n\n"
        if api_help:
            suggestion += api_help + "\n"
        suggestion += f"Error Details:\n```\n{error_msg}\n```\n\n"
        suggestion += f"FAILED CODE:\n```python\n{code}\n```\n\n"
        suggestion += "TASK: Provide corrected code using the correct PyQGIS API methods and signatures. Return a complete, runnable script."

        self.improvement_suggested.emit(code, suggestion)
    
    # Removed: get_available_functions (unused)
