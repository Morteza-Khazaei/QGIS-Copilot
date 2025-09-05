QGIS Copilot UI/UX Story and Guide
==================================

Big picture
-----------

The chat experience is built in QML and embedded with **QQuickView** for smooth rendering. It pairs a clean conversation flow with code-centric actions and live execution logs while staying fast under heavy output.

Highlights
^^^^^^^^^^

- Pastel message bubbles with clear contrast and timestamps.
- Stable, hover-only action buttons, always at the top-right of content blocks.
- One-click Copy for any message; Copy/Edit/Run for code blocks; Debug for error logs.
- Composer with Send and a Clear icon, overlaid to maximize message space.
- Performance guards: fixed bubble sizing, batched logs, capped history.

Anatomy of the chat panel
-------------------------

- **Background**: white (matches QGIS default UI).
- **Bubbles**: light pastels that distinguish actors without distracting from the map canvas:

  - User: ``#eef2ff`` (lavender-blue)
  - Assistant: ``#fff0f6`` (blush pink)
  - QGIS/System: ``#e9fbf2`` / ``#f4f6fa`` (mint / cool gray)

- **Code**: black text on a soft gray block.
- **Timestamps**: left-aligned for user, right-aligned for others.
- **Header**: removed to maximize vertical space for conversation.

Hover actions (precise and steady)
----------------------------------

Actions appear only when the top-right **hotspot** is hovered, and stay visible while the cursor is on the buttons:

- Text blocks: **Copy**
- Assistant code blocks: **Copy · Edit · Run**
- QGIS/System error logs: **Debug**

Implementation details
^^^^^^^^^^^^^^^^^^^^^^

- Action rows are fixed overlays anchored inside the bubble (no layout jumps).
- Small, invisible hover catchers under the buttons keep them visible during cursor movement.

Composer
--------

- **Send**: press Enter (Shift+Enter for newline).
- **Clear**: broom icon next to Send; disabled when empty; enabled after the first message.
- The composer overlays the message list so the chat can occupy the full height beneath it.

Copying content
---------------

- Hover the top-right hotspot on any text block and click **Copy** to copy text to the clipboard.
- For code blocks, Copy sits next to Edit and Run.

Running and editing code
------------------------

- **Run** executes the fenced code block. If *Run in Console* is enabled, the code is saved as a task file and executed via the Python Console; otherwise it runs in memory.
- **Edit** saves the code into your workspace and opens it in the Python Console editor.

Logs, system messages, and debugging
-----------------------------------

- Logs stream into chat as **System** messages using fenced code formatting for readability.
- If a log looks like an error (Traceback, NameError, QgsProcessingException, etc.), a **Debug** button appears in the hotspot.
- **Debug** sends the logs—and, when available, the most recent assistant code block—back to the AI with a prompt asking for a brief diagnosis and a corrected script.

Performance notes
-----------------

- **QQuickView embedding** with ``createWindowContainer`` reduces main-thread overhead under heavy updates.
- **Batched logs**: executor log lines are merged within ~250 ms windows and flushed on completion to avoid message spam.
- **Bounded history**: the chat model keeps a soft cap (about 400 messages) and prunes the oldest items to protect memory.
- **Fixed bubble sizing**: avoids hidden RichText measurements on long content.

Keyboard & interaction
----------------------

- Enter → Send
- Shift+Enter → New line
- Hover → Reveal hotspot actions (top-right)

FAQ
---

Why can’t I drag-select text?
  QML ``Text`` doesn’t support mouse selection. The explicit **Copy** action offers a reliable, predictable workflow. If you prefer selection, we can render HTML into a read-only ``TextArea`` (with trade-offs).

Why don’t action buttons show for the whole bubble?
  Precision and stability. Hotspots prevent accidental reveals and keep the UI steady while you move onto the buttons.

Where did the separate QML dock go?
  The QML chat panel is fully integrated into the main Copilot dialog.

