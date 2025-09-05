import ast
import inspect
import difflib
from typing import Dict, Any, List, Optional


class PyQGISAPIValidator:
    """Enhanced validator that checks code against the live PyQGIS API."""

    def __init__(self, globals_env: Dict[str, Any]):
        self.globals_env = globals_env or {}
        self.api_cache: Dict[str, Any] = {}
        self._built = False

    # -------- API cache --------
    def build_api_cache(self) -> None:
        if self._built:
            return
        try:
            import qgis.core as core
        except Exception:
            return
        for name in dir(core):
            if not name.startswith('Qgs'):
                continue
            try:
                cls = getattr(core, name)
            except Exception:
                continue
            if inspect.isclass(cls):
                self.api_cache[name] = self._analyze_class(cls)
        self._built = True

    def _analyze_class(self, cls) -> Dict[str, Any]:
        methods = {}
        for method_name in dir(cls):
            if method_name.startswith('_'):
                continue
            try:
                method = getattr(cls, method_name)
            except Exception:
                continue
            if callable(method):
                try:
                    sig = inspect.signature(method)
                except Exception:
                    sig = None
                methods[method_name] = {
                    'signature': sig,
                    'docstring': (inspect.getdoc(method) or '')
                }
        return {
            'methods': methods,
            'docstring': (inspect.getdoc(cls) or ''),
            'mro': [base.__name__ for base in getattr(cls, '__mro__', [])[1:]]
        }

    # -------- Validation --------
    def validate_code_comprehensively(self, code: str) -> Dict[str, Any]:
        self.build_api_cache()
        results: Dict[str, Any] = {
            'syntax_valid': True,
            'syntax_errors': [],
            'method_errors': [],
            'attribute_errors': [],
            'suggestions': [],
            'warnings': [],
            'corrected_code': None
        }
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            results['syntax_valid'] = False
            results['syntax_errors'].append(f"Line {getattr(e, 'lineno', 0)}: {e.msg}")
            return results

        # Attribute access on known classes/modules
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                base = node.value.id
                attr = node.attr
                obj = self.globals_env.get(base)
                if obj is not None:
                    try:
                        if not hasattr(obj, attr):
                            close = difflib.get_close_matches(attr, dir(obj), n=3, cutoff=0.6)
                            self._append_attr_error(results, node, base, attr, close)
                    except Exception:
                        pass

        # Simple instance type inference: var = QgsClass(...)
        var_types = self._infer_simple_types(tree)

        # Validate calls
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # instance method: var.method()
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                var_name = func.value.id
                method_name = func.attr
                cls = var_types.get(var_name)
                if cls and cls in self.api_cache:
                    class_info = self.api_cache[cls]
                    methods = class_info['methods']
                    if method_name not in methods:
                        close = difflib.get_close_matches(method_name, methods.keys(), n=3, cutoff=0.6)
                        self._append_method_error(results, node, f"{cls}.{method_name}() does not exist", close, list(methods.keys())[:12])
                    else:
                        self._validate_signature(node, methods[method_name], results, owner=f"{cls}", name=method_name, bound=True)
            # class/module attribute call: QgsProject.instance()
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                base = func.value.id
                method_name = func.attr
                obj = self.globals_env.get(base)
                if obj and hasattr(obj, method_name):
                    method = getattr(obj, method_name)
                    sig = None
                    try:
                        sig = inspect.signature(method)
                    except Exception:
                        pass
                    if sig is not None:
                        self._validate_signature(node, {'signature': sig}, results, owner=base, name=method_name, bound=False)

        return results

    def _infer_simple_types(self, tree) -> Dict[str, str]:
        types: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                callee = node.value.func
                class_name = None
                if isinstance(callee, ast.Name) and callee.id in self.api_cache:
                    class_name = callee.id
                elif isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                    # e.g., core.QgsFeature(...)
                    if callee.attr in self.api_cache:
                        class_name = callee.attr
                if class_name:
                    for t in targets:
                        types[t] = class_name
        return types

    def _validate_signature(self, node: ast.Call, method_info: Dict[str, Any], results: Dict[str, Any], owner: str, name: str, bound: bool):
        sig = method_info.get('signature')
        if sig is None:
            return
        params = list(sig.parameters.values())
        if bound and params:
            # drop self for instance methods
            params = params[1:]
        required_pos = [p for p in params if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD) and p.default is inspect._empty]
        provided_pos = len(node.args)
        if provided_pos < len(required_pos):
            results['method_errors'].append({
                'error': f"{owner}.{name}() missing required arguments",
                'line': getattr(node, 'lineno', 0),
                'expected': f"Required: {[p.name for p in required_pos]}",
                'provided': f"Got {provided_pos} positional args"
            })
        valid_kw = {p.name for p in params if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
        provided_kw = {kw.arg for kw in node.keywords if kw.arg}
        unknown = provided_kw - valid_kw
        for bad in unknown:
            close = difflib.get_close_matches(bad, list(valid_kw), n=1)
            hint = f" Did you mean '{close[0]}'?" if close else ""
            results['warnings'].append(f"Unknown keyword '{bad}' for {owner}.{name}(){hint}")

    def _append_attr_error(self, results, node, base, attr, suggestions: List[str]):
        results['attribute_errors'].append({
            'error': f"{base}.{attr} does not exist",
            'line': getattr(node, 'lineno', 0),
            'suggestions': suggestions
        })

    def _append_method_error(self, results, node, msg: str, suggestions: List[str], available: List[str]):
        results['method_errors'].append({
            'error': msg,
            'line': getattr(node, 'lineno', 0),
            'suggestions': suggestions,
            'available_methods': available,
        })

    # -------- AI Context --------
    def generate_ai_context(self, task: str) -> str:
        self.build_api_cache()
        classes = self._identify_relevant_classes(task)
        lines = ["AVAILABLE PYQGIS API (validated signatures):", "=" * 50]
        for cls in classes:
            info = self.api_cache.get(cls)
            if not info:
                continue
            lines.append(f"\n{cls}:")
            # List key methods with signatures
            count = 0
            for m, mi in info['methods'].items():
                if count >= 12:
                    break
                sig = mi.get('signature')
                if sig is not None:
                    doc = mi.get('docstring') or ''
                    first = doc.split('\n')[0] if doc else ''
                    lines.append(f"  .{m}{sig}")
                    if first:
                        lines.append(f"    # {first}")
                    count += 1
        return "\n".join(lines) + "\n"

    def _identify_relevant_classes(self, task: str) -> List[str]:
        task_lower = (task or '').lower()
        mapping = {
            'layout': ['QgsPrintLayout', 'QgsLayoutItemPage', 'QgsLayoutSize', 'QgsLayoutItem', 'QgsLayoutItemMap', 'QgsLayoutExporter'],
            'layer': ['QgsVectorLayer', 'QgsRasterLayer', 'QgsMapLayer'],
            'feature': ['QgsFeature', 'QgsGeometry', 'QgsField'],
            'project': ['QgsProject'],
            'map': ['QgsMapCanvas', 'QgsMapSettings'],
            'print': ['QgsPrintLayout', 'QgsLayoutExporter'],
            'symbol': ['QgsSymbol', 'QgsMarkerSymbol', 'QgsFillSymbol', 'QgsLineSymbol'],
            'render': ['QgsRenderer', 'QgsRenderContext'],
        }
        relevant = set(['QgsProject'])
        for k, classes in mapping.items():
            if k in task_lower:
                relevant.update(classes)
        return [c for c in relevant if c in self.api_cache]
