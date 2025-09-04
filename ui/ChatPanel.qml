import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12

Rectangle {
    id: root
    width: 920
    height: 640
    color: "#f6f7fb"            // light chat background

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
        "system": assetsDir + "/copilot.png"
    })
    readonly property var roleToName: ({
        "user": "You",
        "assistant": aiModelName && aiModelName.length ? aiModelName :
                      (aiProviderName && aiProviderName.length ? aiProviderName : "AI Model"),
        "qgis": "QGIS",
        "system": "System"
    })
    readonly property var roleToBubble: ({
        "user":    "#e7f3ff",   // light blue
        "assistant": "#fff1e6", // light peach
        "qgis":    "#eaf7ea",   // light green
        "system":  "#eef0f3"    // neutral light gray
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
        chatView.positionViewAtIndex(chatModel.count-1, ListView.End)
    }

    // ---- Header ----
    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        height: 56
        color: "#ffffff"
        border.color: divider
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 12

            Label {
                text: "QGIS Copilot"
                font.pixelSize: 18
                font.bold: true
                color: "#2a2a2a"
                Layout.alignment: Qt.AlignVCenter
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    // ---- Chat list ----
    ListView {
        id: chatView
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: composer.top
        anchors.margins: 8
        clip: true
        spacing: 10
        model: chatModel

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

            // Gutter (avatar + name + time). Right for user, left otherwise.
            Column {
                id: leftGutter
                width: 92
                anchors.left: isUser ? undefined : parent.left
                anchors.right: isUser ? parent.right : undefined
                anchors.leftMargin: isUser ? 0 : 4
                anchors.rightMargin: isUser ? 4 : 0
                spacing: 4

                Rectangle {
                    id: avatarFrame
                    width: 36; height: 36; radius: 18
                    color: "#ffffff"
                    border.color: divider
                    clip: true
                    anchors.left: isUser ? undefined : parent.left
                    anchors.right: isUser ? parent.right : undefined

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
                    horizontalAlignment: isUser ? Text.AlignRight : Text.AlignLeft
                }

                // Time is shown inside the message bubble footer; omit here to avoid duplication.
            }

            // Bubble rail: right for user, left for others
            Item {
                id: rail
                anchors.left: isUser ? parent.left : leftGutter.right
                anchors.right: isUser ? leftGutter.left : parent.right
                anchors.top: parent.top
                anchors.margins: 2
                height: bubble.implicitHeight

                Rectangle {
                    id: bubble
                    radius: 14
                    border.width: 1
                    border.color: "#00000010"
                    color: roleToBubble[roleNorm] || "#ffffff"

                    // Position: user -> right, others -> left
                    anchors.top: parent.top
                    anchors.margins: 2
                    anchors.right: isUser ? parent.right : undefined
                    anchors.left: !isUser ? parent.left : undefined

                    // Width clamp
                    // Measure natural (unwrapped) text width, then clamp to rail
                    property int maxW: Math.floor(parent.width * 0.66)
                    width: Math.min(measureText.implicitWidth + 24, maxW)
                    implicitHeight: contentCol.implicitHeight + 24

                    // Invisible measurer to compute natural content width
                    Text {
                        id: measureText
                        visible: false
                        text: messageText
                        textFormat: Text.RichText
                        wrapMode: Text.NoWrap
                        font.pixelSize: 14
                    }

                    // Content + footer time inside bubble
                    Column {
                        id: contentCol
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 6

                        // Rich text to support HTML (plugin sometimes appends html_text)
                        Text {
                            id: textContent
                            text: messageText
                            // Render AI replies as Markdown; others as plain text
                            textFormat: isAssistant ? Text.MarkdownText : Text.PlainText
                            color: bubbleText
                            // Wrap anywhere to keep all content inside the bubble
                            wrapMode: Text.WrapAnywhere
                            width: parent.width
                            font.pixelSize: 14
                            onLinkActivated: function(url) {
                                // Let Python side handle anchors if needed
                                root.debugRequested("link:" + url)
                            }
                        }

                        // Timestamp at bottom of bubble
                        Label {
                            id: bubbleTime
                            text: formatTs(messageTs)
                            color: faintText
                            font.pixelSize: 11
                            width: parent.width
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    // Hover actions (Copy / Edit / Run when code present)
                    MouseArea {
                        id: hover
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }

                    Row {
                        id: actions
                        spacing: 6
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 6
                        visible: hover.containsMouse

                        Button {
                            id: copyBtn
                            text: "Copy"
                            padding: 6
                            font.pixelSize: 11
                            visible: (isAssistant || isQgis)
                            onClicked: root.copyRequested(isCode && codeExtract.length ? codeExtract : messageText)
                        }
                        Button {
                            id: editBtn
                            text: "Edit"
                            padding: 6
                            font.pixelSize: 11
                            onClicked: root.editRequested(isCode && codeExtract.length ? codeExtract : messageText)
                        }
                        Button {
                            id: runBtn
                            text: "Run"
                            padding: 6
                            font.pixelSize: 11
                            visible: isCode
                            onClicked: {
                                if (isCode && codeExtract.length) root.runCodeRequested(codeExtract)
                                else root.runRequested(messageText)
            }
        }
                    }
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
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 64
        color: "#ffffff"
        border.color: divider
        border.width: 1

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
        }
    }
}
