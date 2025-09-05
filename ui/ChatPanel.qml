import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12

Rectangle {
    id: root
    width: 920
    height: 640
    color: "#ffffff"            // match QGIS app background (white)

    // ---- Properties set by qml_chat_dock.py ----
    // Example: file:///.../plugins/QGIS-Copilot/figures
    property url assetsDir: Qt.resolvedUrl("../figures")
    property string aiModelName: ""      // e.g., "Llama 3.1 70B"
    property string aiProviderName: ""   // e.g., "Ollama (Local)"

    // ---- Role presentation ----
    readonly property var roleToIcon: ({
        "user": assetsDir + "/user.png",
        "assistant": assetsDir + "/copilot.png",  // assistant icon in your repo
        "qgis": assetsDir + "/qgis.png",
        "system": assetsDir + "/qgis.png"         // show system as QGIS
    })
    readonly property var roleToName: ({
        "user": "You",
        "assistant": aiModelName && aiModelName.length ? aiModelName :
                      (aiProviderName && aiProviderName.length ? aiProviderName : "AI Model"),
        "qgis": "QGIS",
        "system": "QGIS"   // rename system messages from PyQGIS to QGIS
    })
    readonly property var roleToBubble: ({
        // Softer, more modern pastels for better visual identity
        "user":     "#eef2ff",   // airy lavender‑blue
        "assistant": "#fff0f6",  // blush pink
        "qgis":     "#e9fbf2",   // mint green
        "system":   "#f4f6fa"    // cool light gray
    })
    readonly property color bubbleText:  "#1a1a1a"
    readonly property color faintText:   "#6e6e6e"
    readonly property color divider:     "#e2e4ea"

    // ---- Signals the dock connects ----
    signal copyRequested(string text)
    signal editRequested(string text)
    signal runRequested(string text)
    signal runCodeRequested(string code)
    signal debugRequested(string info)
    signal clearRequested()          // ask host to clear chat/logs

    // ---- Model the dock calls into via root.appendMessage(role, text, ts) ----
    ListModel { id: chatModel }

    // ---- Methods callable from Python (QMetaObject.invokeMethod) ----
    function appendMessage(role, text, ts) {
        // role: "user" | "assistant" | "qgis" | "system"
        var r = role || "assistant"
        var t = text || ""
        var iso = ts && ts.length ? ts : new Date().toISOString()
        // Lightweight de-duplication (prevents echoing the same user msg twice)
        if (chatModel.count > 0) {
            var last = chatModel.get(chatModel.count - 1)
            if (last && last.role === r && last.text === t) {
                return
            }
        }
        chatModel.append({ role: r, text: t, ts: iso })
        // Protect memory: prune oldest beyond a soft cap
        var cap = 400
        if (chatModel.count > cap) {
            var removeCount = chatModel.count - cap
            chatModel.remove(0, removeCount)
        }
        chatView.positionViewAtIndex(chatModel.count-1, ListView.End)
    }

    // Clear all chat messages (called from Python)
    function clearMessages() {
        chatModel.clear();
    }

    // ---- Markdown block parser (text vs fenced code) ----
    function parseBlocks(src) {
        var s = src || "";
        var re = /(~~~|```)([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)\r?\n?\1/gm;
        var out = [];
        var last = 0;
        var m;
        while ((m = re.exec(s)) !== null) {
            if (m.index > last) out.push({ kind: 'text', body: s.substring(last, m.index) });
            out.push({ kind: 'code', body: m[3], lang: (m[2]||'').toLowerCase() });
            last = re.lastIndex;
        }
        if (last < s.length) out.push({ kind: 'text', body: s.substring(last) });
        if (out.length === 0) out.push({ kind: 'text', body: s });
        return out;
    }

    // Header removed to maximize chat space

    // ---- Chat list ----
    ListView {
        id: chatView
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        // Let chat extend behind the composer to use more space
        anchors.bottom: parent.bottom
        anchors.margins: 8
        clip: true
        spacing: 10
        model: chatModel

        // Keep a small gap at the very end for readability while composer overlays
        footer: Item { height: 12 }

        ScrollBar.vertical: ScrollBar { }

        delegate: Item {
            id: rowRoot
            width: ListView.view.width
            // Height adapts to gutter + bubble + hover controls
            height: Math.max(leftGutter.implicitHeight, bubble.implicitHeight) + 10

            // Parse once
            // Avoid shadowing Text.text by capturing roles under different names
            property string messageRole: (typeof role !== 'undefined' && role ? role : "assistant")
            property string messageText: (typeof text !== 'undefined' ? text : "")
            property string messageTs: (typeof ts !== 'undefined' ? ts : "")
            property string roleNorm: (messageRole || "assistant").toLowerCase()
            property bool   isUser: roleNorm === "user"
            property bool   isAssistant: roleNorm === "assistant"
            property bool   isQgis: roleNorm === "qgis"
            property bool   isCode: /\x60\x60\x60/.test(messageText) // has ``` somewhere
            property string codeExtract: extractCode(messageText)
            property var    blocks: parseBlocks(messageText)
            function isErrorLog(txt) {
                if (!txt) return false;
                var s = txt.toLowerCase();
                var hints = [
                    "traceback", "error:", "exception", "failed", "not found",
                    "nameerror", "typeerror", "qgsprocessingexception", "valueerror"
                ];
                for (var i=0;i<hints.length;i++) { if (s.indexOf(hints[i]) !== -1) return true; }
                return false;
            }

            // Gutter (avatar + name). Right for user, left otherwise; contents centered.
            Column {
                id: leftGutter
                width: 80
                anchors.left: isUser ? undefined : parent.left
                anchors.right: isUser ? parent.right : undefined
                anchors.leftMargin: isUser ? 0 : 2
                anchors.rightMargin: isUser ? 2 : 0
                spacing: 3

                Rectangle {
                    id: avatarFrame
                    width: 36; height: 36; radius: 18
                    color: "#ffffff"
                    border.color: divider
                    clip: true
                    anchors.horizontalCenter: parent.horizontalCenter

                    Image {
                        anchors.fill: parent
                        source: roleToIcon[roleNorm] || (assetsDir + "/copilot.png")
                        sourceSize.width: 36
                        sourceSize.height: 36
                        fillMode: Image.PreserveAspectFit
                        antialiasing: true
                        smooth: true
                    }
                }

                Label {
                    text: roleToName[roleNorm] || "Participant"
                    font.pixelSize: 12
                    font.bold: true
                    color: "#3a3a3a"
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                }

                // Time is shown inside the message bubble footer; omit here to avoid duplication.
            }

            // Bubble rail: right for user, left for others
            Item {
                id: rail
                anchors.left: isUser ? parent.left : leftGutter.right
                anchors.right: isUser ? leftGutter.left : parent.right
                anchors.top: parent.top
                anchors.margins: 0
                height: bubble.implicitHeight

                Rectangle {
                    id: bubble
                    radius: 14
                    border.width: 1
                    border.color: "#00000010"
                    color: roleToBubble[roleNorm] || "#ffffff"

                    // Position: user -> right, others -> left
                    anchors.top: parent.top
                    anchors.margins: 0
                    anchors.right: isUser ? parent.right : undefined
                    anchors.left: !isUser ? parent.left : undefined

                    // Width clamp: fixed maximum to avoid expensive text measurement
                    property int maxW: Math.floor(parent.width * 0.82)
                    width: Math.min(parent.width, maxW)
                    implicitHeight: contentCol.implicitHeight + 24

                    // Content + footer time inside bubble
                    Column {
                        id: contentCol
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 6

                        // QGIS/system reply helper description and actions
                        Item {
                            id: sysHelper
                            visible: isQgis || roleNorm === 'system'
                            width: parent.width
                            height: visible ? (desc1.implicitHeight + desc2.implicitHeight + (dbgBtn.visible ? 28 : 0) + 6) : 0

                            Column {
                                spacing: 2
                                width: parent.width
                                Label { id: desc1; text: "QGIS Reply"; color: faintText; font.pixelSize: 12 }
                                Label { id: desc2; text: "These are logs and messages from executing your script."; color: faintText; font.pixelSize: 11 }
                                // Debug button moved to code block hover header for consistency
                            }
                        }

                        // Render message as blocks so code blocks can have per-block actions
                        Repeater {
                            model: blocks
                            delegate: Item {
                                width: contentCol.width
                                height: (blkText.visible ? blkText.implicitHeight
                                        : (codeWrap.visible ? codeWrap.implicitHeight : 0))
                                property var entry: modelData

                                // Text block (Markdown for assistant; plain for others)
                                Text {
                                    id: blkText
                                    visible: entry.kind === 'text'
                                    text: entry.body
                                    textFormat: isAssistant ? Text.MarkdownText : Text.PlainText
                                    color: bubbleText
                                    wrapMode: Text.WrapAnywhere
                                    width: parent.width
                                    font.pixelSize: 14
                                    onLinkActivated: function(url) { root.debugRequested("link:" + url) }
                                }

                                // Code block with per-block actions (assistant only)
                                Rectangle {
                                    id: codeWrap
                                    visible: entry.kind === 'code'
                                    width: parent.width
                                    radius: 6
                                    color: "#f5f5f5"
                                    border.color: "#dddddd"
                                    border.width: 1
                                    implicitHeight: codeText.implicitHeight + 28

                                    // Hover-only actions header
                                    MouseArea { id: codeHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                                    Row {
                                        spacing: 4
                                        anchors.top: parent.top
                                        anchors.right: parent.right
                                        anchors.topMargin: 4
                                        anchors.rightMargin: 6
                                        // Show on hover for both assistant (code actions)
                                        // and system/QGIS logs (debug action)
                                        visible: codeHover.containsMouse

                                        // Assistant actions
                                        Button {
                                            text: "Copy"
                                            padding: 4
                                            font.pixelSize: 10
                                            implicitHeight: 22
                                            implicitWidth: Math.max(36, contentItem.implicitWidth + 10)
                                            visible: isAssistant
                                            onClicked: root.copyRequested(entry.body)
                                        }
                                        Button {
                                            text: "Edit"
                                            padding: 4
                                            font.pixelSize: 10
                                            implicitHeight: 22
                                            implicitWidth: Math.max(36, contentItem.implicitWidth + 10)
                                            visible: isAssistant
                                            onClicked: root.editRequested(entry.body)
                                        }
                                        Button {
                                            text: "Run"
                                            padding: 4
                                            font.pixelSize: 10
                                            implicitHeight: 22
                                            implicitWidth: Math.max(36, contentItem.implicitWidth + 10)
                                            visible: isAssistant
                                            onClicked: root.runCodeRequested(entry.body)
                                        }
                                        // System/QGIS logs: Debug action
                                        Button {
                                            text: "Debug"
                                            padding: 4
                                            font.pixelSize: 10
                                            implicitHeight: 22
                                            implicitWidth: 56
                                            visible: (isQgis || roleNorm === 'system') && isErrorLog(messageText)
                                            onClicked: root.debugRequested(entry.body)
                                        }
                                    }

                                    Text {
                                        id: codeText
                                        text: entry.body
                                        textFormat: Text.PlainText
                                        wrapMode: Text.WrapAnywhere
                                        font.family: "monospace"
                                        font.pixelSize: 13
                                        color: "#000000"    // black code text for higher contrast
                                        anchors {
                                            left: parent.left; right: parent.right
                                            leftMargin: 8; rightMargin: 8
                                            top: parent.top; topMargin: 22
                                            bottom: parent.bottom; bottomMargin: 6
                                        }
                                    }
                                }
                            }
                        }

                        // Timestamp at bottom of bubble
                        Label {
                            id: bubbleTime
                            text: formatTs(messageTs)
                            color: faintText
                            font.pixelSize: 11
                            width: parent.width
                            horizontalAlignment: isUser ? Text.AlignLeft : Text.AlignRight
                        }
                    }

                    // Bubble-level actions removed in favor of per-code-block actions above
                }
            }

            // Util: code extraction (first fenced block; join multiple)
            function extractCode(txt) {
                if (!txt) return "";
                // Match ```lang?\n ... \n``` (multiline, global)
                var re = /```[a-zA-Z0-9_+-]*\s*([\s\S]*?)```/g;
                var m, parts = [];
                while ((m = re.exec(txt)) !== null) parts.push(m[1]);
                if (parts.length === 0) return "";
                return parts.join("\n\n").trim();
            }

            function formatTs(iso) {
                try {
                    // QML can format ISO strings in a friendly way
                    var d = new Date(iso);
                    var hh = ("0" + d.getHours()).slice(-2);
                    var mm = ("0" + d.getMinutes()).slice(-2);
                    return hh + ":" + mm;
                } catch(e) { return ""; }
            }
        }
    }

    // ---- Composer ----
    Rectangle {
        id: composer
        z: 10   // overlay above the chat list
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 64
        color: "transparent" // remove background strip
        border.width: 0

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

            TextArea {
                id: input
                Layout.fillWidth: true
                // Allow multi-line with scroll for long questions
                placeholderText: "Type a message…"
                Accessible.name: "Message input"
                wrapMode: TextEdit.Wrap
                clip: true
                hoverEnabled: true
                ScrollBar.vertical: ScrollBar { }
                // Send on Enter, newline on Shift+Enter
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        if (event.modifiers & Qt.ShiftModifier) {
                            // allow newline
                            return;
                        }
                        sendBtn.clicked();
                        event.accepted = true;
                    }
                }
                background: Rectangle {
                    radius: 18
                    color: input.hovered ? "#f8f9fb" : "#ffffff"
                    border.width: 1
                    border.color: input.activeFocus ? "#0b5ed7" : (input.hovered ? "#c7cfdd" : "#e2e6ee")
                    Behavior on color { ColorAnimation { duration: 120 } }
                    Behavior on border.color { ColorAnimation { duration: 120 } }
                }
            }

            Button {
                id: sendBtn
                text: ""
                Accessible.name: "Send message"
                enabled: (input.text || "").trim().length > 0
                hoverEnabled: true
                implicitWidth: 36
                implicitHeight: 36
                background: Rectangle {
                    radius: 18
                    color: !sendBtn.enabled ? "#b9d0f5"
                          : sendBtn.pressed ? "#0a58ca"
                          : sendBtn.hovered ? "#0b66f0"
                          : "#0b5ed7"
                    border.width: 1
                    border.color: !sendBtn.enabled ? "#9bb9e8" : "#0a58ca"
                    Behavior on color { ColorAnimation { duration: 100 } }
                }
                contentItem: Text {
                    // Paper-plane style arrow
                    text: "➤"
                    color: "#ffffff"
                    font.pixelSize: 16
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    var msg = (input.text || "").trim();
                    if (!msg.length) return;
                    // Echo immediately
                    root.appendMessage('user', msg, "");
                    // Forward to Python bridge
                    root.runRequested(msg);
                    input.text = "";
                }
            }

            // Clear-all icon button (appears after Send)
            Button {
                id: clearBtn
                text: "\ud83e\uddf9"   // broom emoji
                Accessible.name: "Clear chat"
                hoverEnabled: true
                implicitWidth: 36
                implicitHeight: 36
                enabled: chatModel.count > 0
                opacity: enabled ? 1.0 : 0.45
                ToolTip.visible: clearBtn.hovered
                ToolTip.text: "Clear chat"
                background: Rectangle {
                    radius: 18
                    color: !clearBtn.enabled ? "#f0f0f0" : (clearBtn.pressed ? "#e0e0e0" : (clearBtn.hovered ? "#ececec" : "#f5f5f5"))
                    border.width: 1
                    border.color: !clearBtn.enabled ? "#e0e0e0" : "#d0d0d0"
                }
                contentItem: Text {
                    text: clearBtn.text
                    color: clearBtn.enabled ? "#333333" : "#9a9a9a"
                    font.pixelSize: 16
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    if (!clearBtn.enabled) return;
                    // Clear locally for instant feedback
                    chatModel.clear();
                    // Ask host (Python) to clear history/logs as well
                    root.clearRequested();
                }
            }
        }
    }

    // Removed shadow so no box/strip appears behind composer
}
