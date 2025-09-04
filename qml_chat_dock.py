import os
from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtCore import QObject, QUrl, pyqtSlot
from qgis.PyQt.QtGui import QGuiApplication
from qgis.PyQt.QtWidgets import QDockWidget, QWidget, QMessageBox


class QMLChatDock(QObject):
    """Experimental QML chat dock for QGIS Copilot.

    Wires QML hover actions (Copy/Edit/Run) to the existing executor/editor.
    """

    def __init__(self, iface, dialog):
        super().__init__()
        self.iface = iface
        self.dialog = dialog  # CopilotChatDialog instance for send/execute helpers
        self._dock = None
        self._root = None
        self._view = None

    def _detect_qml_backend(self):
        """Return 'quickview', 'quickwidget', or None depending on availability.

        Prefer QQuickView for stability (QQuickWidget is known to be crash‑prone on some Qt/OS combos).
        """
        # Prefer QQuickView via qgis shim
        try:
            from qgis.PyQt.QtQuick import QQuickView  # noqa: F401
            return 'quickview'
        except Exception:
            pass
        # Then try QQuickView via PyQt5
        try:
            from PyQt5.QtQuick import QQuickView  # noqa: F401
            return 'quickview'
        except Exception:
            pass
        # Fallback to QQuickWidget (embeds into QWidget but can be less stable)
        try:
            from qgis.PyQt.QtQuickWidgets import QQuickWidget  # noqa: F401
            return 'quickwidget'
        except Exception:
            pass
        try:
            from PyQt5.QtQuickWidgets import QQuickWidget  # noqa: F401
            return 'quickwidget'
        except Exception:
            pass
        return None

    def show(self):
        try:
            if self._dock:
                self._dock.show()
                self._dock.raise_()
                return
            main = self.iface.mainWindow()
            dock = QDockWidget("QGIS Copilot (QML)", main)
            backend = self._detect_qml_backend()

            widget = None
            root = None
            if backend == 'quickwidget':
                try:
                    try:
                        from qgis.PyQt.QtQuickWidgets import QQuickWidget
                    except Exception:
                        from PyQt5.QtQuickWidgets import QQuickWidget
                    qw = QQuickWidget()
                    qw.setResizeMode(QQuickWidget.SizeRootObjectToView)
                    qml_path = os.path.join(os.path.dirname(__file__), 'ui', 'ChatPanel.qml')
                    qw.setSource(QUrl.fromLocalFile(qml_path))
                    root = qw.rootObject()
                    # If root failed to load, present an inline error widget with details
                    if root is None:
                        err = getattr(qw, 'errors', lambda: [])()
                        msg = "Failed to load QML ChatPanel.qml.\n"
                        try:
                            if err:
                                msg += "\n".join([str(e.toString() if hasattr(e, 'toString') else e) for e in err])
                        except Exception:
                            pass
                        lbl = QtWidgets.QLabel(msg)
                        lbl.setWordWrap(True)
                        lbl.setStyleSheet("QLabel{padding:8px; color:#b00020;}")
                        widget = QtWidgets.QWidget()
                        lay = QtWidgets.QVBoxLayout(widget)
                        lay.addWidget(lbl)
                        dock.setWidget(widget)
                        main.addDockWidget(0x2, dock)
                        # Keep refs then bail early
                        self._dock = dock
                        self._view = widget
                        self._root = None
                        return
                    widget = qw  # already a QWidget
                except Exception as e:
                    QMessageBox.warning(main, 'QML Chat', f'Failed to load QML with QQuickWidget.\n{e}')
            elif backend == 'quickview':
                try:
                    try:
                        from qgis.PyQt.QtQuick import QQuickView
                    except Exception:
                        from PyQt5.QtQuick import QQuickView
                    qv = QQuickView()
                    qv.setResizeMode(QQuickView.SizeRootObjectToView)
                    qml_path = os.path.join(os.path.dirname(__file__), 'ui', 'ChatPanel.qml')
                    qv.setSource(QUrl.fromLocalFile(qml_path))
                    widget = QWidget.createWindowContainer(qv, dock)
                    root = qv.rootObject()
                    if root is None:
                        err = getattr(qv, 'errors', lambda: [])()
                        msg = "Failed to load QML ChatPanel.qml.\n"
                        try:
                            if err:
                                msg += "\n".join([str(e.toString() if hasattr(e, 'toString') else e) for e in err])
                        except Exception:
                            pass
                        lbl = QtWidgets.QLabel(msg)
                        lbl.setWordWrap(True)
                        lbl.setStyleSheet("QLabel{padding:8px; color:#b00020;}")
                        widget = QtWidgets.QWidget()
                        lay = QtWidgets.QVBoxLayout(widget)
                        lay.addWidget(lbl)
                        dock.setWidget(widget)
                        main.addDockWidget(0x2, dock)
                        self._dock = dock
                        self._view = widget
                        self._root = None
                        return
                except Exception as e:
                    QMessageBox.warning(main, 'QML Chat', f'Failed to load QML with QQuickView.\n{e}')
            else:
                # Fallback: enhanced QtWidgets chat so users still see a UI
                widget = _SimpleChatWidget(copy_cb=self.on_copy, edit_cb=self.on_edit, run_cb=self.on_run)
                widget.setToolTip('Qt Quick is not available; using basic chat UI.')

            dock.setWidget(widget)
            main.addDockWidget(0x2, dock)  # Qt.RightDockWidgetArea

            # Connect QML signals if we have a root object
            if root is not None:
                try:
                    root.copyRequested.connect(self.on_copy)
                    root.editRequested.connect(self.on_edit)
                    root.runRequested.connect(self.on_run)
                    if hasattr(root, 'runCodeRequested'):
                        root.runCodeRequested.connect(self.on_run_code)
                    if hasattr(root, 'debugRequested'):
                        root.debugRequested.connect(self.on_debug)
                except Exception:
                    pass

                # Provide assets directory (as a file URL) and initial AI model name
                try:
                    from qgis.PyQt.QtCore import QUrl as _QUrl
                    assets_dir = os.path.join(os.path.dirname(__file__), 'figures')
                    assets_url = _QUrl.fromLocalFile(assets_dir).toString()
                    if hasattr(root, 'assetsDir'):
                        root.setProperty('assetsDir', assets_url)
                except Exception:
                    pass
                try:
                    self._apply_ai_model_name()
                    self._apply_ai_provider_name()
                except Exception:
                    pass

            # Keep refs
            self._dock = dock
            self._view = widget
            self._root = root
        except Exception:
            pass

    @pyqtSlot(str)
    def on_debug(self, _code: str):
        """Ask Copilot to debug the last failed execution using logs."""
        try:
            # Use the dialog's existing manual improvement flow; it will use the
            # last failed execution context if available.
            if hasattr(self.dialog, 'request_manual_improvement'):
                self.dialog.request_manual_improvement()
            else:
                # Fallback: if not present, try immediate suggest_improvement if we can reach executor state
                pend = getattr(self.dialog, 'pending_failed_execution', None)
                if pend and hasattr(self.dialog.pyqgis_executor, 'suggest_improvement'):
                    self.dialog.pyqgis_executor.suggest_improvement(pend)
        except Exception:
            pass

    def _apply_ai_model_name(self):
        try:
            name = None
            try:
                model = getattr(self.dialog.current_api, 'model', None)
                if model:
                    name = str(model)
            except Exception:
                pass
            if not name:
                name = getattr(self.dialog, 'current_api_name', '') or 'AI'
            if self._root and hasattr(self._root, 'aiModelName'):
                self._root.setProperty('aiModelName', name)
        except Exception:
            pass

    def set_ai_model_name(self, name: str):
        try:
            if self._root and hasattr(self._root, 'aiModelName'):
                self._root.setProperty('aiModelName', name or '')
        except Exception:
            pass

    def _apply_ai_provider_name(self):
        try:
            prov = getattr(self.dialog, 'current_api_name', '') or ''
            prov = self._normalize_provider_name(prov)
            if self._root and hasattr(self._root, 'aiProviderName'):
                self._root.setProperty('aiProviderName', prov or 'AI')
        except Exception:
            pass

    def set_ai_provider_name(self, name: str):
        try:
            prov = self._normalize_provider_name(name or '')
            if self._root and hasattr(self._root, 'aiProviderName'):
                self._root.setProperty('aiProviderName', prov or 'AI')
        except Exception:
            pass

    def _normalize_provider_name(self, name: str) -> str:
        try:
            n = (name or '').lower()
            if 'ollama' in n:
                return 'Ollama'
            if 'openai' in n or 'chatgpt' in n:
                return 'ChatGPT'
            if 'gemini' in n or 'google' in n:
                return 'Gemini'
            if 'claude' in n or 'anthropic' in n:
                return 'Claude'
            return name or 'AI'
        except Exception:
            return name or 'AI'

    @pyqtSlot(str)
    def on_copy(self, text):
        try:
            QGuiApplication.clipboard().setText(text or "")
        except Exception:
            pass

    @pyqtSlot(str)
    def on_edit(self, text):
        # Save quietly and open in Python Console editor
        code = text or ""
        if not code.strip():
            return
        try:
            # Save to sticky task file with a generic hint
            fenced = f"```python\n{code}\n```"
            path = self.dialog.pyqgis_executor.save_response_to_task_file(fenced, filename_hint="qml_chat_task", quiet=True)
            if path and os.path.exists(path):
                self.dialog._open_file_in_python_console_editor(path)
                # Add system message to QML chat
                try:
                    self._root.appendMessage("system", f"Opened in editor: {path}", "")
                except Exception:
                    pass
        except Exception:
            pass

    @pyqtSlot(str)
    def on_run(self, text):
        """Heuristic: if text contains code fences, execute code; else treat as user prompt."""
        msg = (text or "").strip()
        if not msg:
            return
        try:
            # Detect code blocks using the executor's extractor
            blocks = self.dialog.pyqgis_executor.extract_code_blocks(msg)
            if blocks:
                code = "\n\n".join(b.strip() for b in blocks)
                # Honor Run-via-Console preference by executing via task file when enabled
                run_via_console = False
                try:
                    from qgis.PyQt.QtCore import QSettings
                    run_via_console = QSettings().value("qgis_copilot/prefs/run_in_console", True, type=bool)
                except Exception:
                    pass
                # Start capture to collate logs with the executed code
                self._begin_run_capture(code)
                if run_via_console:
                    try:
                        fenced = f"```python\n{code}\n```"
                        path = self.dialog.pyqgis_executor.save_response_to_task_file(fenced, filename_hint="qml_chat_task", quiet=True)
                        self.dialog.pyqgis_executor.execute_task_file(path)
                    except Exception:
                        self.dialog.pyqgis_executor.execute_code(code)
                else:
                    self.dialog.pyqgis_executor.execute_code(code)
                # Do not emit extra chat noise; detailed logs are mirrored via executor logs.
            else:
                # Treat as prompt when no explicit fenced code is present.
                # Show it in the main dialog chat and send programmatically to avoid UI coupling.
                try:
                    # Add the user message to the main dialog chat (mirrors to QML via signal)
                    if hasattr(self.dialog, 'add_to_chat'):
                        self.dialog.add_to_chat("You", msg, "#007bff")
                except Exception:
                    pass
                try:
                    # Send directly to the provider with all current options/context
                    self.dialog.send_message(msg, is_programmatic=True)
                except Exception:
                    pass
        except Exception:
            pass

    @pyqtSlot(str)
    def on_run_code(self, code_text: str):
        """Execute code text (from code block actions)."""
        code = (code_text or "").strip()
        if not code:
            return
        run_via_console = False
        try:
            from qgis.PyQt.QtCore import QSettings
            run_via_console = QSettings().value("qgis_copilot/prefs/run_in_console", True, type=bool)
        except Exception:
            pass
        try:
            # Start capture to collate logs with the executed code
            self._begin_run_capture(code)
            if run_via_console:
                fenced = f"```python\n{code}\n```"
                path = self.dialog.pyqgis_executor.save_response_to_task_file(fenced, filename_hint="qml_chat_task", quiet=True)
                self.dialog.pyqgis_executor.execute_task_file(path)
            else:
                self.dialog.pyqgis_executor.execute_code(code)
            # Do not add an extra 'Executing code…' message; executor will push logs.
        except Exception:
            pass

    # ---- Run capture helpers ----
    def _begin_run_capture(self, code: str):
        try:
            self._cap_active = True
            self._cap_logs = []
            self._cap_code = code or ""
            execu = getattr(self.dialog, 'pyqgis_executor', None)
            if not execu:
                self._cap_active = False
                return
            try:
                execu.logs_updated.connect(self._on_run_log)
            except Exception:
                pass
            try:
                execu.execution_completed.connect(self._on_run_completed)
            except Exception:
                pass
        except Exception:
            self._cap_active = False

    @pyqtSlot(str)
    def _on_run_log(self, text: str):
        try:
            if self._cap_active:
                self._cap_logs.append(text or "")
        except Exception:
            pass

    @pyqtSlot(str, bool, object)
    def _on_run_completed(self, result_message, success, execution_log):
        try:
            if not self._cap_active:
                return
            logs = "\n".join(self._cap_logs).strip()
            logs_md = f"```\n{logs}\n```" if logs else "(no logs)"
            status = "✅ Success" if success else "❌ Error"
            if success:
                # On success, only show logs once (no code, no debug needed)
                md = f"{status}\n\nQGIS Messages/Logs:\n{logs_md}"
            else:
                # On error, include the executed code as context
                code_md = f"```python\n{self._cap_code}\n```" if self._cap_code else "(no code captured)"
                md = f"{status}\n\nCode Executed:\n{code_md}\n\nQGIS Messages/Logs:\n{logs_md}"
            self.append_message('system', md, '')
        except Exception:
            pass
        finally:
            try:
                execu = getattr(self.dialog, 'pyqgis_executor', None)
                if execu:
                    try:
                        execu.logs_updated.disconnect(self._on_run_log)
                    except Exception:
                        pass
                    try:
                        execu.execution_completed.disconnect(self._on_run_completed)
                    except Exception:
                        pass
            except Exception:
                pass
            self._cap_active = False
            self._cap_logs = []
            self._cap_code = ""

    def _looks_like_code(self, s: str) -> bool:
        try:
            t = s.strip()
            if '\n' in t:
                # Multi-line scripts are likely code
                return True
            # Heuristics
            keys = ('Qgs', 'iface', 'import ', 'def ', 'class ', 'from ', '=')
            for k in keys:
                if k in t:
                    return True
            return False
        except Exception:
            return False

    def append_message(self, role: str, text: str, ts: str = ""):
        try:
            # Clean up system messages: drop leading [HH:MM:SS] timestamp which is redundant in chat
            msg = text or ""
            try:
                import re as _re
                if role == 'system':
                    msg = _re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', msg)
            except Exception:
                pass

            # Route to QML if available; else to fallback widget if present
            # Feed raw Markdown to QML (it renders Markdown natively); convert only for QWidget fallback
            if self._root and hasattr(self._root, 'appendMessage'):
                self._root.appendMessage(role, msg, ts)
            elif isinstance(self._view, _SimpleChatWidget):
                html_text = self._md_to_html(msg)
                self._view.appendMessage(role, html_text, ts)
        except Exception:
            pass

    def _md_to_html(self, text: str) -> str:
        """Very small Markdown→HTML for chat (handles fenced code + newlines)."""
        try:
            import re, html as _html
            s = text or ""
            out = []
            idx = 0
            pattern = re.compile(r'(?:```|~~~)(?:[a-zA-Z0-9_-]+)?[ \t]*\r?\n([\s\S]*?)\r?\n?(?:```|~~~)', re.MULTILINE)
            for m in pattern.finditer(s):
                # Non-code segment
                pre = s[idx:m.start()]
                if pre:
                    esc = _html.escape(pre)
                    esc = esc.replace('\n', '<br>')
                    out.append(esc)
                code = m.group(1)
                code_esc = _html.escape(code)
                out.append(f'<pre style="margin:6px 0; background:#f5f5f5; color:#000000; border:1px solid #ddd; padding:10px; border-radius:6px; white-space:pre-wrap;">{code_esc}</pre>')
                idx = m.end()
            # Tail
            tail = s[idx:]
            if tail:
                esc = _html.escape(tail)
                esc = esc.replace('\n', '<br>')
                out.append(esc)
            return ''.join(out) if out else _html.escape(s).replace('\n', '<br>')
        except Exception:
            return text or ""


class _SimpleChatWidget(QtWidgets.QWidget):
    """Enhanced QWidget-based chat fallback (no QML dependency).

    - Right/left bubbles with light colors
    - Timestamps
    - Hover actions: Copy · Edit · Run
    """
    def __init__(self, parent=None, copy_cb=None, edit_cb=None, run_cb=None):
        super().__init__(parent)
        self._list = QtWidgets.QListWidget()
        self._list.setWordWrap(True)
        self._list.setStyleSheet(
            """
            QListWidget{ background:#f5f5f5; border:none; }
            QListWidget::item{ border:none; }
            """
        )
        # Composer (input + send)
        self._input = QtWidgets.QLineEdit()
        self._input.setPlaceholderText("Type a message…")
        self._send = QtWidgets.QPushButton("Send")
        self._send.setFixedHeight(36)
        comp = QtWidgets.QHBoxLayout()
        comp.setContentsMargins(10, 10, 10, 10)
        comp.setSpacing(8)
        comp.addWidget(self._input, 1)
        comp.addWidget(self._send, 0)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._list)
        lay.addLayout(comp)
        # callbacks
        self._copy_cb = copy_cb
        self._edit_cb = edit_cb
        self._run_cb = run_cb

        # Wire send behavior
        self._send.clicked.connect(self._send_msg)
        self._input.returnPressed.connect(self._send.click)

        # Rounded visual styles (no extra container visuals)
        self._input.setStyleSheet(
            "QLineEdit{background:#ffffff; border:1px solid #e0e0e0; border-radius:18px; padding:6px 10px; font-size:12pt;}"
        )
        self._send.setStyleSheet(
            "QPushButton{background:#0b5ed7; color:#fff; border:1px solid #0a58ca; border-radius:18px; padding:6px 16px; font-size:12pt;}"
            "QPushButton:hover{background:#0a58ca;}"
        )

    def appendMessage(self, role, text, ts=""):
        it = QtWidgets.QListWidgetItem()
        bubble = _Bubble(role=role, text=text, ts=ts, copy_cb=self._copy_cb, edit_cb=self._edit_cb, run_cb=self._run_cb)
        # Cap width to ~78%
        bubble.setMaximumWidth(int(self._list.viewport().width() * 0.78))
        self._list.addItem(it)
        self._list.setItemWidget(it, bubble)
        it.setSizeHint(bubble.sizeHint())
        # Align right for user, left for assistant/system
        align = QtCore.Qt.AlignRight if role == "user" else QtCore.Qt.AlignLeft
        try:
            self._list.setItemAlignment(it, align)
        except Exception:
            pass
        self._list.scrollToBottom()

    def _send_msg(self):
        msg = (self._input.text() or "").strip()
        if not msg:
            return
        # Clear input; message will arrive via broadcast from Copilot
        self._input.clear()
        # Forward to Copilot via run callback (acts as submit)
        if callable(self._run_cb):
            try:
                self._run_cb(msg)
            except Exception:
                pass


class _Bubble(QtWidgets.QFrame):
    def __init__(self, role: str, text: str, ts: str, copy_cb=None, edit_cb=None, run_cb=None):
        super().__init__()
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setStyleSheet("QFrame{background:transparent;}")
        self._copy_cb = copy_cb
        self._edit_cb = edit_cb
        self._run_cb = run_cb

        # Colors
        bg = "#d7ecff" if role == "user" else "#e8f6ec"
        border = "#d3d3d3"

        # Bubble panel
        bubble = QtWidgets.QFrame()
        bubble.setStyleSheet(
            f"QFrame{{background:{bg}; border:1px solid {border}; border-radius:12px;}}"
        )
        # Header row inside bubble: sender + time
        head_w = QtWidgets.QWidget()
        head_l = QtWidgets.QHBoxLayout(head_w)
        head_l.setContentsMargins(8, 8, 8, 0)
        head_l.setSpacing(6)
        sender = 'You' if role == 'user' else ('AI' if role == 'assistant' else 'QGIS')
        sender_lbl = QtWidgets.QLabel(sender)
        sender_lbl.setStyleSheet("QLabel{color:#444; font-weight:600; font-size:9pt;}")
        dot = QtWidgets.QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet("QLabel{background:#bbb; border-radius:3px;}")
        time_lbl = QtWidgets.QLabel(self._format_ts(ts))
        time_lbl.setStyleSheet("QLabel{color:#666; font-size:8pt;}")
        head_l.addWidget(sender_lbl)
        head_l.addWidget(dot)
        head_l.addWidget(time_lbl)
        head_l.addStretch(1)

        text_lbl = QtWidgets.QLabel(text)
        text_lbl.setWordWrap(True)
        text_lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        text_lbl.setStyleSheet("QLabel{color:#222; font-size:9.5pt;}")
        text_lbl.setMargin(8)

        # Hover action row
        actions = QtWidgets.QWidget()
        actions_l = QtWidgets.QHBoxLayout(actions)
        actions_l.setContentsMargins(0, 0, 0, 0)
        actions_l.setSpacing(6)
        btn_style = "QPushButton{background:#fff; border:1px solid #cfcfcf; border-radius:11px; padding:2px 8px;} QPushButton:hover{background:#f3f3f3;}"
        copy_btn = QtWidgets.QPushButton("Copy"); copy_btn.setStyleSheet(btn_style)
        edit_btn = QtWidgets.QPushButton("Edit"); edit_btn.setStyleSheet(btn_style)
        run_btn = QtWidgets.QPushButton("Run"); run_btn.setStyleSheet(btn_style)
        actions_l.addWidget(copy_btn); actions_l.addWidget(edit_btn); actions_l.addWidget(run_btn)
        actions.setFixedHeight(28)
        actions.setVisible(True)

        # Timestamp
        ts_lbl = QtWidgets.QLabel(self._format_ts(ts))
        ts_lbl.setStyleSheet("QLabel{color:#7a7a7a; font-size:10pt;}")

        # Layout
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        bub_lay = QtWidgets.QVBoxLayout(bubble)
        bub_lay.setContentsMargins(0, 0, 0, 0)
        bub_lay.addWidget(head_w)
        bub_lay.addWidget(text_lbl)
        outer.addWidget(actions, 0, QtCore.Qt.AlignRight)
        outer.addWidget(bubble)
        # timestamp now lives in header; remove footer ts

        self.setAttribute(QtCore.Qt.WA_Hover, True)
        actions.setAttribute(QtCore.Qt.WA_Hover, True)
        bubble.installEventFilter(self)
        text_lbl.installEventFilter(self)
        actions.installEventFilter(self)
        copy_btn.installEventFilter(self)
        edit_btn.installEventFilter(self)
        run_btn.installEventFilter(self)

        # Button actions
        copy_btn.clicked.connect(lambda: self._copy_cb(text) if callable(self._copy_cb) else None)
        edit_btn.clicked.connect(lambda: self._edit_cb(text) if callable(self._edit_cb) else None)
        run_btn.clicked.connect(lambda: self._run_cb(text) if callable(self._run_cb) else None)

        self._actions = actions
        self._actions_btns = [copy_btn, edit_btn, run_btn]
        for _b in self._actions_btns:
            _b.setVisible(False)
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(150)
        self._hide_timer.timeout.connect(self._maybe_hide_actions)

    def eventFilter(self, obj, event):
        et = event.type()
        if et in (QtCore.QEvent.HoverEnter, QtCore.QEvent.Enter):
            self._hide_timer.stop()
            for _b in getattr(self, "_actions_btns", []):
                _b.setVisible(True)
        elif et in (QtCore.QEvent.HoverLeave, QtCore.QEvent.Leave):
            self._hide_timer.start()
        return super().eventFilter(obj, event)

    def _maybe_hide_actions(self):
        try:
            if self.underMouse() or (self._actions and self._actions.underMouse()):
                return
            for _b in getattr(self, "_actions_btns", []):
                _b.setVisible(False)
        except Exception:
            pass

    def _format_ts(self, iso: str) -> str:
        # Very small formatter: use local time if parse fails
        try:
            from datetime import datetime
            d = datetime.fromisoformat(iso) if iso else datetime.now()
            return d.strftime('%Y-%m-%d %H:%M')
        except Exception:
            return ''
