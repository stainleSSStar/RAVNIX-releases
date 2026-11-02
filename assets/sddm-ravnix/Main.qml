/***************************************************************************
* RAVNIX SDDM greeter theme.
*
* Derived from the SDDM "maldives" theme (Abdurrahman AVCI, MIT licence).
* The layout is unchanged; the panel, the colours and the branding are RAVNIX.
*
***************************************************************************/

import QtQuick 2.0
import SddmComponents 2.0

Rectangle {
    id: container
    width: 640
    height: 480

    // RAVNIX Purple Neon palette.
    property color ravnixBase: "#1a1423"
    property color ravnixPanel: "#221b2d"
    property color ravnixPink: "#f472b6"
    property color ravnixGreen: "#a6f28a"
    property color ravnixPurple: "#a78bfa"
    property color ravnixText: "#ece6f5"

    LayoutMirroring.enabled: Qt.locale().textDirection == Qt.RightToLeft
    LayoutMirroring.childrenInherit: true

    property int sessionIndex: session.index

    TextConstants { id: textConstants }

    Connections {
        target: sddm

        function onLoginSucceeded() {
            errorMessage.color = ravnixGreen
            errorMessage.text = textConstants.loginSucceeded
        }
        function onLoginFailed() {
            password.text = ""
            errorMessage.color = ravnixPink
            errorMessage.text = textConstants.loginFailed
        }
        function onInformationMessage(message) {
            errorMessage.color = ravnixPink
            errorMessage.text = message
        }
    }

    Background {
        anchors.fill: parent
        source: Qt.resolvedUrl(config.background)
        fillMode: Image.PreserveAspectCrop
        onStatusChanged: {
            var defaultBackground = Qt.resolvedUrl(config.defaultBackground)
            if (status == Image.Error && source != defaultBackground) {
                source = defaultBackground
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"

        Clock {
            id: clock
            anchors.margins: 14
            anchors.top: parent.top; anchors.right: parent.right

            color: ravnixText
            timeFont.family: "Hack"
        }

        Rectangle {
            id: panel
            anchors.centerIn: parent
            width: Math.max(340, mainColumn.implicitWidth + 56)
            height: Math.max(360, mainColumn.implicitHeight + 56)

            color: Qt.rgba(0.10, 0.078, 0.14, 0.88)
            radius: 14
            border.width: 1
            border.color: Qt.rgba(0.64, 0.45, 0.71, 0.55)

            Column {
                id: mainColumn
                anchors.centerIn: parent
                spacing: 12

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: ravnixPink
                    verticalAlignment: Text.AlignVCenter
                    height: text.implicitHeight
                    width: parent.width
                    text: "RAVNIX"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 34
                    font.bold: true
                    font.family: "Hack"
                    font.letterSpacing: 6
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: ravnixText
                    verticalAlignment: Text.AlignVCenter
                    height: text.implicitHeight
                    width: parent.width
                    text: textConstants.welcomeText.arg(sddm.hostName)
                    wrapMode: Text.WordWrap
                    font.pixelSize: 16
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                Rectangle {
                    width: parent.width * 0.5
                    height: 2
                    color: ravnixGreen
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Column {
                    width: parent.width
                    spacing: 4
                    Text {
                        id: lblName
                        width: parent.width
                        text: textConstants.userName
                        color: ravnixPurple
                        font.bold: true
                        font.pixelSize: 12
                    }

                    TextBox {
                        id: name
                        width: parent.width; height: 30
                        text: userModel.lastUser
                        font.pixelSize: 14

                        KeyNavigation.backtab: rebootButton; KeyNavigation.tab: password

                        Keys.onPressed: function (event) {
                            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                sddm.login(name.text, password.text, sessionIndex)
                                event.accepted = true
                            }
                        }
                    }
                }

                Column {
                    width: parent.width
                    spacing: 4
                    Text {
                        id: lblPassword
                        width: parent.width
                        text: textConstants.password
                        color: ravnixPurple
                        font.bold: true
                        font.pixelSize: 12
                    }

                    PasswordBox {
                        id: password
                        width: parent.width; height: 30
                        font.pixelSize: 14

                        KeyNavigation.backtab: name; KeyNavigation.tab: session

                        Keys.onPressed: function (event) {
                            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                sddm.login(name.text, password.text, sessionIndex)
                                event.accepted = true
                            }
                        }
                    }
                }

                Row {
                    spacing: 4
                    width: parent.width / 2
                    z: 100

                    Column {
                        z: 100
                        width: parent.width * 1.3
                        spacing: 4
                        anchors.bottom: parent.bottom

                        Text {
                            id: lblSession
                            width: parent.width
                            text: textConstants.session
                            color: ravnixPurple
                            wrapMode: TextEdit.WordWrap
                            font.bold: true
                            font.pixelSize: 12
                        }

                        ComboBox {
                            id: session
                            width: parent.width; height: 30
                            font.pixelSize: 14

                            arrowIcon: Qt.resolvedUrl("angle-down.png")

                            model: sessionModel
                            index: sessionModel.lastIndex

                            KeyNavigation.backtab: password; KeyNavigation.tab: layoutBox
                        }
                    }

                    Column {
                        z: 101
                        width: parent.width * 0.7
                        spacing: 4
                        anchors.bottom: parent.bottom

                        visible: keyboard.enabled && keyboard.layouts.length > 0

                        Text {
                            id: lblLayout
                            width: parent.width
                            text: textConstants.layout
                            color: ravnixPurple
                            wrapMode: TextEdit.WordWrap
                            font.bold: true
                            font.pixelSize: 12
                        }

                        LayoutBox {
                            id: layoutBox
                            width: parent.width; height: 30
                            font.pixelSize: 14

                            arrowIcon: Qt.resolvedUrl("angle-down.png")

                            KeyNavigation.backtab: session; KeyNavigation.tab: loginButton
                        }
                    }
                }

                Column {
                    width: parent.width
                    Text {
                        id: errorMessage
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: textConstants.prompt
                        color: ravnixText
                        font.pixelSize: 10
                    }
                }

                Row {
                    spacing: 4
                    anchors.horizontalCenter: parent.horizontalCenter
                    property int btnWidth: Math.max(loginButton.implicitWidth,
                                                    shutdownButton.implicitWidth,
                                                    rebootButton.implicitWidth, 80) + 8
                    Button {
                        id: loginButton
                        text: textConstants.login
                        width: parent.btnWidth

                        onClicked: sddm.login(name.text, password.text, sessionIndex)

                        KeyNavigation.backtab: layoutBox; KeyNavigation.tab: shutdownButton
                    }

                    Button {
                        id: shutdownButton
                        text: textConstants.shutdown
                        width: parent.btnWidth

                        onClicked: sddm.powerOff()

                        KeyNavigation.backtab: loginButton; KeyNavigation.tab: rebootButton
                    }

                    Button {
                        id: rebootButton
                        text: textConstants.reboot
                        width: parent.btnWidth

                        onClicked: sddm.reboot()

                        KeyNavigation.backtab: shutdownButton; KeyNavigation.tab: name
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        if (name.text == "")
            name.focus = true
        else
            password.focus = true
    }
}
