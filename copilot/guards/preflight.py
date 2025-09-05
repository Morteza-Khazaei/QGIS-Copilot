import ast
import difflib
from typing import Dict, List, Tuple

from ..manifest.qgis_oracle import load_manifest


def _index(manifest: dict):
    classes, methods = set(), set()
    for _modname, items in manifest.get("modules", {}).items():
        for cls, entry in items.items():
            kind = entry.get("kind")
            if kind == "class":
                classes.add(cls)
                attrs = (entry.get("attrs") or {}).keys()
                for a in attrs:
                    methods.add(f"{cls}.{a}")
            elif kind == "func":
                # ignore for now
                pass
    return classes, methods


def _collect_types(tree: ast.AST) -> Dict[str, str]:
    types: Dict[str, str] = {}
    for node in ast.walk(tree):
        # var: Class = ...
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            ann = node.annotation
            if hasattr(ann, "id"):
                types[node.target.id] = getattr(ann, "id", None)
        # x = Class(...)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = node.value.func
            if isinstance(callee, ast.Name):
                cname = callee.id
            elif isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                cname = callee.attr
            else:
                cname = None
            if cname:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        types.setdefault(tgt.id, cname)
    return types


def validate(code: str, cutoff: float = 0.72) -> Tuple[List[Tuple[str, str, str]], List[List[str]], Dict[str, str]]:
    """Validate agent code against live manifest.

    Returns (errors, tips, types) where:
      - errors: list of (var, cls, attr) that are unknown
      - tips: list of suggestion lists per error
      - types: inferred var->class mapping
    """
    tree = ast.parse(code)
    man = load_manifest()
    _classes, methods = _index(man)
    types = _collect_types(tree)
    errors, tips = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            var, attr = node.value.id, node.attr
            cls = types.get(var)
            if cls and f"{cls}.{attr}" not in methods:
                close = difflib.get_close_matches(f"{cls}.{attr}", list(methods), n=3, cutoff=cutoff)
                errors.append((var, cls, attr))
                tips.append(close)
    return errors, tips, types

