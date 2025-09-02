"""
Lightweight web knowledge fetcher for PyQGIS Developer Cookbook.

Fetches the PyQGIS cookbook index and a few linked pages, caches a
compact summary, and provides a helper to include relevant snippets in
the agent context. Network failures fall back to cached data.
"""

import os
import re
import json
import time
from datetime import datetime, timedelta

import requests
from qgis.core import QgsMessageLog, Qgis


BASE_URL = "https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/index.html"
CACHE_FILE = "pyqgis_cookbook_cache.json"
CACHE_TTL_DAYS = 7


def _plugin_root():
    return os.path.dirname(__file__)


def _cache_path():
    cache_dir = os.path.join(_plugin_root(), "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, CACHE_FILE)


def _is_cache_fresh(path):
    try:
        ts = os.path.getmtime(path)
        return (datetime.now() - datetime.fromtimestamp(ts)) < timedelta(days=CACHE_TTL_DAYS)
    except Exception:
        return False


def _absolute_url(href):
    if href.startswith("http://") or href.startswith("https://"):
        return href
    base = "https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/"
    if href.startswith("../"):
        href = href.replace("../", "")
    return base + href


def _extract_text(html):
    # Remove scripts/styles
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    # Replace tags with spaces
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_sections(html, page_url):
    sections = []
    # Capture headings and short following snippets
    for m in re.finditer(r"<(h[1-3])[^>]*>(.*?)</\1>", html, flags=re.IGNORECASE | re.DOTALL):
        level = m.group(1).lower()
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not title:
            continue
        # Grab following 400 chars of text from end of heading
        idx = m.end()
        snippet = _extract_text(html[idx : idx + 1200])[:400]
        sections.append({
            "level": level,
            "title": title,
            "snippet": snippet,
            "url": page_url,
        })
    return sections


def fetch_and_cache(max_link_pages=8):
    """Fetch index and up to N linked pages; cache compact section summaries."""
    try:
        resp = requests.get(BASE_URL, timeout=(5, 15))
        resp.raise_for_status()
        html = resp.text
        data = {"source": BASE_URL, "fetched_at": time.time(), "pages": []}
        sections = _extract_sections(html, BASE_URL)
        data["pages"].append({"url": BASE_URL, "sections": sections})

        # Collect a few internal links from the index
        links = re.findall(r"href=\"([^\"]+)\"", html)
        picked = []
        for href in links:
            if not href or href.startswith("#"):
                continue
            if not href.endswith(".html"):
                continue
            if "pyqgis_developer_cookbook" not in href:
                continue
            url = _absolute_url(href)
            if url in picked or url == BASE_URL:
                continue
            picked.append(url)
            if len(picked) >= max_link_pages:
                break

        for url in picked:
            try:
                r = requests.get(url, timeout=(5, 15))
                r.raise_for_status()
                sec = _extract_sections(r.text, url)
                data["pages"].append({"url": url, "sections": sec})
            except Exception as e:
                QgsMessageLog.logMessage(f"Docs fetch failed for {url}: {e}", "QGIS Copilot", level=Qgis.Warning)

        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        QgsMessageLog.logMessage(f"Docs fetch failed: {e}", "QGIS Copilot", level=Qgis.Warning)
        return False


def _ensure_cache():
    path = _cache_path()
    if os.path.exists(path) and _is_cache_fresh(path):
        return True
    return fetch_and_cache()


def _load_cache():
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"pages": []}


def get_relevant_summary(query: str, max_sections: int = 6, max_chars: int = 1200) -> str:
    """Return a compact, relevant summary from cached docs for the given query."""
    if not query or not isinstance(query, str):
        return ""
    _ensure_cache()
    data = _load_cache()
    q = query.lower()

    scored = []
    for page in data.get("pages", []):
        for sec in page.get("sections", []):
            hay = (sec.get("title", "") + " " + sec.get("snippet", "")).lower()
            # Simple keyword score
            score = 0
            for token in re.findall(r"[a-z0-9_]+", q):
                if token and token in hay:
                    score += 1
            if score > 0:
                scored.append((score, sec.get("title", ""), sec.get("snippet", ""), sec.get("url", page.get("url", ""))))

    if not scored:
        return ""

    scored.sort(key=lambda x: (-x[0], x[1]))
    parts = []
    for _, title, snippet, url in scored[:max_sections]:
        url_part = f" ({url})" if url else ""
        parts.append(f"- {title}{url_part}: {snippet}")
    text = "PyQGIS Docs Hints:\n" + "\n".join(parts)
    return text[:max_chars]
