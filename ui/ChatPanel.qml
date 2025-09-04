import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12

Rectangle {
    id: root
    width: 420
    height: 620
    color: "#f5f5f5"
    // Bubble sizing guidance relative to dialog
    property real minBubbleWidthFactor: 0.45   // 45% of dialog width (minimum)
    property real maxBubbleWidthFactor: 0.86   // 86% of dialog width (maximum)
    property real maxBubbleHeightFactor: 0.40  // 40% of dialog height (maximum visible before scrolling)

    // Provided by Python bridge; fallback to figures folder next to this QML
    property url assetsDir: Qt.resolvedUrl("../figures")   // e.g., file:///.../plugins/QGIS-Copilot/figures
    // AI identity shown in the sender line
    // Model name is displayed for the AI (e.g., "gpt-4o"); provider is used only as a fallback
    property string aiModelName: ""         // e.g., "gpt-4o"
    property string aiProviderName: "AI"    // e.g., "Ollama", "ChatGPT", "Gemini" (fallback only)

    signal copyRequested(string text)
    signal editRequested(string text)
    signal runRequested(string text)         // used for sending prompts/user messages
    signal runCodeRequested(string code)     // used for executing code blocks
    signal debugRequested(string code)       // used to trigger AI debug on last error

    // Simple message store
    ListModel { id: chatModel }

    // Split message text into blocks: [{kind:'text'|'code', body:string, lang:string}]
    function parseBlocks(src) {
        var s = src || "";
        var re = /(~~~|```)([a-zA-Z0-9_-]*)[ \t]*\r?\n([\s\S]*?)\r?\n?\1/gm;
        var out = [];
        var last = 0;
        var m;
        while ((m = re.exec(s)) !== null) {
            if (m.index > last) {
                out.push({ kind: 'text', body: s.substring(last, m.index) });
            }
            out.push({ kind: 'code', body: m[3], lang: (m[2]||'').toLowerCase() });
            last = re.lastIndex;
        }
        if (last < s.length) {
            out.push({ kind: 'text', body: s.substring(last) });
        }
        if (out.length === 0) {
            out.push({ kind: 'text', body: s });
        }
        return out;
    }

    function appendMessage(role, text, isoTimestamp) {
        chatModel.append({
            "role": role,
            "text": text,
            "timestamp": isoTimestamp && isoTimestamp.length ? isoTimestamp : new Date().toISOString()
        })
        Qt.callLater(function() { chatView.positionViewAtEnd(); });
    }

    Rectangle {
        height: 40
        width: parent.width
        color: "#ffffff"
        border.color: "#e0e0e0"
        anchors.top: parent.top

        Text {
            text: "QGIS Copilot"
            anchors.centerIn: parent
            font.pixelSize: 14
            font.bold: true
            color: "#333333"
        }
    }

    ListView {
        id: chatView
        anchors { top: parent.top; topMargin: 42; left: parent.left; right: parent.right; bottom: inputBar.top }
        model: chatModel
        spacing: 10
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        delegate: Item {
            id: row
            width: chatView.width
            height: signRow.implicitHeight + bubble.implicitHeight + (overflowControls.visible ? overflowControls.implicitHeight + 4 : 0) + 8

            readonly property bool isUser: role === "user"
            // Light role-specific colors: User (blue), AI (green), QGIS (gray)
            readonly property color bubbleColor: (role === 'user') ? "#d7ecff" : ((role === 'assistant') ? "#e8f6ec" : "#f1f3f5")
            readonly property color borderColor: "#d3d3d3"
            // Display model name for AI (fallback to provider/AI); You/QGIS for others
            readonly property string displayName: (role === 'user' ? 'You'
                                                    : (role === 'assistant'
                                                        ? ((root.aiModelName && root.aiModelName.length)
                                                            ? root.aiModelName
                                                            : ((root.aiProviderName && root.aiProviderName.length) ? root.aiProviderName : 'AI'))
                                                        : 'QGIS'))
            readonly property url displayIconPath: (role === 'user' ? (root.assetsDir + '/user.png') : (role === 'assistant' ? (root.assetsDir + '/copilot.png') : (root.assetsDir + '/qgis.png')))
            property var blocks: parseBlocks(model.text)
            property string roleName: role
            readonly property bool hasError: (model.text.indexOf("❌") >= 0) || (model.text.indexOf("Error") >= 0)
            // Measure the natural content width (no hard wrapping) to size bubble to text length
            readonly property real measuredContentWidth: measureColumn.implicitWidth

            // Sender sign outside bubble (icon + name + time)
            Row {
                id: signRow
                spacing: 8
                layoutDirection: row.isUser ? Qt.RightToLeft : Qt.LeftToRight
                anchors {
                    left: row.isUser ? undefined : parent.left
                    right: row.isUser ? parent.right : undefined
                    top: parent.top
                    leftMargin: 12
                    rightMargin: 12
                    topMargin: 2
                }
                HoverHandler { id: hoverSign; acceptedDevices: PointerDevice.Mouse }
                // Icon
                Image {
                    id: iconImg
                    source: row.displayIconPath
                    width: 32; height: 32
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                    visible: status === Image.Ready
                }
                // Name
                Text {
                    text: row.displayName
                    color: "#444"
                    font.pixelSize: 12
                    font.bold: true
                }
                // Time (short; shows exact ISO on hover)
                Text {
                    id: signTime
                    text: hoverSign.hovered ? model.timestamp : formatTime(model.timestamp)
                    color: "#666"
                    font.pixelSize: 11
                }
            }

            Rectangle {
                id: bubble
                radius: 12
                color: row.bubbleColor
                border.color: row.borderColor
                border.width: 1
                anchors {
                    left: row.isUser ? undefined : parent.left
                    right: row.isUser ? parent.right : undefined
                    leftMargin: 10
                    rightMargin: 10
                    top: signRow.bottom
                    topMargin: 4
                }
                // Size relative to text length and dialog size (no internal scroll)
                width: Math.max(root.width * root.minBubbleWidthFactor,
                                Math.min(root.width * root.maxBubbleWidthFactor, row.measuredContentWidth + 24))
                implicitHeight: contentClip.height + 12

                // Content clip for elegant expand/collapse
                Item {
                    id: contentClip
                    clip: true
                    anchors { left: parent.left; right: parent.right; top: parent.top; bottom: parent.bottom; leftMargin: 12; rightMargin: 12; topMargin: 8; bottomMargin: 8 }
                    // Expand/collapse height
                    property bool expanded: false
                    property real collapsedMaxHeight: root.height * root.maxBubbleHeightFactor
                    property bool isOverflowing: contentColumn.implicitHeight > collapsedMaxHeight
                    height: expanded ? contentColumn.implicitHeight : Math.min(contentColumn.implicitHeight, collapsedMaxHeight)

                    Column {
                        id: contentColumn
                        width: contentClip.width
                        spacing: 6

                        Repeater {
                            model: row.blocks
                            delegate: Item {
                                width: contentColumn.width
                                height: blkText.implicitHeight
                                property var entry: modelData

                                // Text block (Markdown)
                                Text {
                                    id: blkText
                                    visible: entry.kind === 'text'
                                    text: entry.body
                                    textFormat: Text.MarkdownText
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 13
                                    color: "#222222"
                                    width: parent.width
                                }

                                // Code block (monospace + actions)
                                Rectangle {
                                    id: codeBlock
                                    visible: entry.kind === 'code'
                                    width: parent.width
                                    radius: 6
                                    color: "#f5f5f5"
                                    border.color: "#dddddd"
                                    border.width: 1
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    // Height from code text + padding
                                    implicitHeight: codeText.implicitHeight + 28

                                    // Per-code-block actions (hover reveal)
                                    HoverHandler { id: codeHover; acceptedDevices: PointerDevice.Mouse }
                                    Row {
                                        spacing: 6
                                        visible: codeHover.hovered
                                        anchors { top: parent.top; right: parent.right; topMargin: 4; rightMargin: 6 }
                                        z: 10
                                    Repeater {
                                        // For AI messages: Copy/Edit/Run
                                        // For QGIS (system): Debug only when error and this is the logs block (no language)
                                        model: (row.roleName === 'assistant') ? [
                                                {label: "Copy",  kind: "copy"},
                                                {label: "Edit",  kind: "edit"},
                                                {label: "Run",   kind: "run"}
                                            ] : ((row.roleName === 'system' && row.hasError && (!entry.lang || entry.lang.length === 0)) ? [
                                                {label: "Debug", kind: "debug"}
                                            ] : [])
                                        delegate: Rectangle {
                                            height: 20
                                            radius: 10
                                            color: "#ffffff"
                                            border.color: "#cfcfcf"
                                            border.width: 1
                                            width: Math.max(lbl.implicitWidth + 14, 44)
                                            Text { id: lbl; text: modelData.label; anchors.centerIn: parent; font.pixelSize: 11; color: "#333333" }
                                            MouseArea {
                                                anchors.fill: parent
                                                onClicked: {
                                                    if (modelData.kind === 'copy')  root.copyRequested(entry.body);
                                                    if (modelData.kind === 'edit')  root.editRequested(entry.body);
                                                    if (modelData.kind === 'run')   root.runCodeRequested(entry.body);
                                                    if (modelData.kind === 'debug') root.debugRequested(entry.body);
                                                }
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                            }
                                        }
                                        }
                                    }

                                    Text {
                                        id: codeText
                                        text: entry.body
                                        textFormat: Text.PlainText
                                        wrapMode: Text.Wrap
                                        font.family: "monospace"
                                        font.pixelSize: 12
                                        color: "#333333"
                                        anchors { left: parent.left; right: parent.right; leftMargin: 8; rightMargin: 8; top: parent.top; topMargin: 22; bottom: parent.bottom; bottomMargin: 6 }
                                    }
                                }
                            }
                        }
                    }

                    // Subtle fade band when collapsed and overflowing
                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: (contentClip.isOverflowing && !contentClip.expanded) ? 18 : 0
                        visible: contentClip.isOverflowing && !contentClip.expanded
                        color: Qt.rgba(1,1,1,0.0)
                    }
                }

                // Hidden measurement column without forced widths to compute natural content width
                Column {
                    id: measureColumn
                    spacing: 6
                    visible: false
                    Repeater {
                        model: row.blocks
                        delegate: Item {
                            width: implicitWidth
                            height: implicitHeight
                            property var entry: modelData
                            Text {
                                visible: entry.kind === 'text'
                                text: entry.body
                                textFormat: Text.MarkdownText
                                wrapMode: Text.NoWrap
                                font.pixelSize: 13
                                color: "transparent"
                            }
                            Text {
                                visible: entry.kind === 'code'
                                text: entry.body
                                textFormat: Text.PlainText
                                wrapMode: Text.NoWrap
                                font.family: "monospace"
                                font.pixelSize: 12
                                color: "transparent"
                            }
                        }
                    }
                }
            // Show more / Show less control (outside bubble)
            Text {
                id: overflowControls
                text: contentClip.expanded ? "Show less" : "Show more"
                color: "#0b5ed7"
                font.pixelSize: 12
                visible: contentClip.isOverflowing
                anchors {
                    right: bubble.right
                    top: bubble.bottom
                    rightMargin: 4
                    topMargin: 4
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { contentClip.expanded = !contentClip.expanded }
                }
            }

        }

        onCountChanged: Qt.callLater(function(){ chatView.positionViewAtEnd() })
        Component.onCompleted: positionViewAtEnd()
    }

    // Floating composer: only two rounded controls (message box + send)
    Rectangle {
        id: inputBar
        height: 54
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            leftMargin: 10
            rightMargin: 10
            bottomMargin: 10
        }
        color: "transparent"
        border.color: "transparent"

        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            TextField {
                id: input
                Layout.fillWidth: true
                placeholderText: "Type a message…"
                font.pixelSize: 14
                onAccepted: sendBtn.clicked()
                // Rounded message box
                implicitHeight: 40
                background: Rectangle {
                    radius: 18
                    color: "#ffffff"
                    border.color: "#e0e0e0"
                    border.width: 1
                }
                leftPadding: 10
                rightPadding: 10
            }

            Button {
                id: sendBtn
                text: "Send"
                implicitHeight: 40
                implicitWidth: 80
                // Rounded send button
                background: Rectangle {
                    radius: 18
                    color: "#0b5ed7"
                    border.color: "#0a58ca"
                }
                contentItem: Text {
                    text: sendBtn.text
                    color: "#ffffff"
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    if (!input.text || !input.text.trim().length) return;
                    // Use runRequested as a submit signal to Python side;
                    // the main dialog will broadcast back the message to render.
                    root.runRequested(input.text.trim());
                    input.text = "";
                }
            }
        }
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n }
    function formatTime(iso) {
        var d = iso && iso.length ? new Date(iso) : new Date();
        if (isNaN(d.getTime())) d = new Date();
        var Y = d.getFullYear()
        var M = pad2(d.getMonth()+1)
        var D = pad2(d.getDate())
        var h = pad2(d.getHours())
        var m = pad2(d.getMinutes())
        return Y + "-" + M + "-" + D + " " + h + ":" + m
    }
}
