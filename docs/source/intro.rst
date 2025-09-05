Overview
========

QGIS Copilot embeds an AI‑assisted chat panel inside QGIS to help you draft, run, and iterate on PyQGIS code. The UI is designed to stay readable and responsive while keeping essential actions close at hand.

Key ideas
---------

- One integrated chat tab (QML) in the main Copilot dialog.
- Fixed, hover‑only action overlays that never move content.
- Logs stream into the chat and can be sent back to the AI for debugging.
- Performance tuned for long sessions (QQuickView, batched logs, capped history).

Quick start
-----------

1. Open QGIS Copilot from the Plugins menu or toolbar.
2. Type a request in the composer and press Enter (Shift+Enter for newline).
3. Hover the top‑right of a block to Copy / Edit / Run / Debug.
4. Use the broom icon to clear the chat once it accumulates messages.

