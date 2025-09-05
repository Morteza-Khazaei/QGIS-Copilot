"""
Ollama Connectivity Diagnostic for QGIS Copilot

Run from the QGIS Python Console to validate Ollama daemon reachability,
available models, and a simple chat exchange. Also checks the plugin's
stored configuration (QSettings) and can optionally test via the plugin's
OllamaAPI implementation if available.

Usage (QGIS Python Console):

    from QGIS_Copilot.ollama_connectivity_diagnostic import run_diagnostic
    run_diagnostic()

Notes:
- This writes human‑readable results to the QGIS Message Log (Plugins »
  Python Console tab will also show prints).
- It uses the minimal chat payload that you confirmed works with curl.
"""

import json
import requests
from typing import Tuple

from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsMessageLog, Qgis


def _log(msg: str, level=Qgis.Info):
    try:
        QgsMessageLog.logMessage(msg, "QGIS Copilot Diagnostic", level)
    except Exception:
        # Fallback to print for environments where QgsMessageLog isn't available
        print(msg)


def _get_settings_snapshot() -> dict:
    s = QSettings()
    return {
        "provider": s.value("qgis_copilot/provider", "Ollama (Local)"),
        "ollama_base_url": s.value("qgis_copilot/ollama_base_url", "http://localhost:11434"),
        "ollama_model": s.value("qgis_copilot/ollama_model", "llama3.1:8b"),
        "prompt_file": s.value("qgis_copilot/system_prompt_file", ""),
        "workspace_dir": s.value("qgis_copilot/workspace_dir", ""),
    }


def _list_models(base_url: str) -> Tuple[bool, list, str]:
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=(3.0, 5.0))
        if resp.status_code != 200:
            return False, [], f"/api/tags returned {resp.status_code}: {resp.text}"
        data = resp.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return True, models, ""
    except requests.exceptions.ConnectionError:
        return False, [], "Cannot connect to Ollama daemon. Is it running (ollama serve)?"
    except requests.exceptions.Timeout:
        return False, [], "Connection to /api/tags timed out"
    except Exception as e:
        return False, [], f"Unexpected error: {e}"


def _chat_once(base_url: str, model: str, prompt: str, timeout: int = 30) -> Tuple[bool, str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/chat",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=(5.0, timeout),
        )
        if resp.status_code != 200:
            return False, f"/api/chat returned {resp.status_code}: {resp.text}"
        data = resp.json()
        content = (data.get("message", {}) or {}).get("content", "").strip()
        if not content:
            # Log available keys for debugging
            return False, f"Empty content. Response keys: {list(data.keys())}"
        return True, content
    except requests.exceptions.Timeout:
        return False, "Chat timed out (model may be loading)"
    except Exception as e:
        return False, f"Chat request failed: {e}"


def run_diagnostic():
    _log("=== QGIS Copilot • Ollama Diagnostic ===")
    cfg = _get_settings_snapshot()
    _log(f"Provider: {cfg['provider']}")
    _log(f"Base URL: {cfg['ollama_base_url']}")
    _log(f"Model: {cfg['ollama_model']}")
    if cfg.get("prompt_file"):
        _log(f"Prompt File: {cfg['prompt_file']}")
    if cfg.get("workspace_dir"):
        _log(f"Workspace: {cfg['workspace_dir']}")

    # Step 1 — server + models
    ok, models, err = _list_models(cfg["ollama_base_url"])
    if not ok:
        _log(f"Models check FAILED: {err}", Qgis.Critical)
        return False
    _log(f"Models available: {len(models)}")
    if models:
        _log("First models: " + ", ".join(models[:5]))
    else:
        _log("No models found. Pull one e.g. 'ollama pull llama3.1:8b'", Qgis.Warning)
        return False

    # Step 2 — pick model (prefer configured if present)
    model = cfg["ollama_model"] if cfg["ollama_model"] in models else models[0]
    _log(f"Testing chat with: {model}")

    ok, msg = _chat_once(cfg["ollama_base_url"], model, "Hello — please reply with 'Connection test successful!'")
    if ok:
        _log("Chat test OK.")
        return True
    else:
        _log("Chat test FAILED: " + msg, Qgis.Warning)

    # Optional: try via plugin API if available
    try:
        from ..providers.ollama_api import OllamaAPI

        _log("Trying plugin OllamaAPI.test_model() …")
        api = OllamaAPI()
        holder = {"done": False, "ok": False, "err": None}

        def _on_ok(_):
            holder["done"] = True
            holder["ok"] = True

        def _on_err(e):
            holder["done"] = True
            holder["err"] = e

        api.test_model(on_result=_on_ok, on_error=_on_err)
        # Note: this is async; for a pure console diagnostic you could add a brief wait or rely on logs.
        _log("Dispatched async plugin test. Check logs for completion.")
    except Exception as e:
        _log(f"Plugin API test skipped: {e}", Qgis.Warning)

    return False
