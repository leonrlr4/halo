import QtQuick
import qs.Ui

// First run, and adding lights later: sign in, scan, pick.
//
// Tapo lights will not talk to anything local without the owner's TP-Link
// account, so the account comes first. The password goes straight to the
// daemon, which keeps it in the desktop keyring; this view never stores it.
Item {
  id: root
  property var app

  property string account: app.account
  property bool busy: false
  property string error: ""
  property var found: []
  property bool scanned: false

  readonly property bool signedIn: app.account !== ""

  function signIn() {
    if (!emailField.text || !passField.text) { root.error = "Enter the email and password of your TP-Link (Tapo) account."; return }
    root.busy = true; root.error = ""
    root.app.request("setup.login", { account: emailField.text.trim(), password: passField.text }, function(r, err) {
      root.busy = false
      passField.text = ""
      if (err) { root.error = err; return }
      root.app.applyHello(r)
      root.scan()
    })
  }

  function scan() {
    root.busy = true; root.error = ""; root.found = []
    root.app.request("setup.scan", {}, function(r, err) {
      root.busy = false; root.scanned = true
      if (err) { root.error = err; return }
      var have = root.app.devices.map(function(d) { return d.host })
      root.found = r.filter(function(d) { return have.indexOf(d.host) < 0 })
    })
  }

  function add(d) {
    root.app.request("setup.add", { host: d.host, model: d.model, kind: d.kind }, function(r, err) {
      if (err) { root.error = err; return }
      root.found = root.found.filter(function(x) { return x.host !== d.host })
      root.app.upsertDevice(r)
      root.app.selectDevice(r.id)
    })
  }

  Column {
    anchors.centerIn: parent
    width: Math.min(parent.width, 460)
    spacing: 14

    Text {
      text: root.signedIn ? "Add a light" : "Connect your lights"
      color: root.app.fg
      font.family: root.app.fontFamily
      font.pixelSize: 22
      font.weight: Font.DemiBold
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      text: root.signedIn
        ? "Signed in as " + root.app.account + ". Scanning looks for TP-Link lights and plugs on this network; it takes about three seconds."
        : "Tapo lights only accept local control from their owner's account. Sign in with the email and password you use in the Tapo app. The password is kept in your desktop keyring and is only ever sent to your own lights."
      color: root.app.dim
      font.family: root.app.fontFamily
      font.pixelSize: 12
      lineHeight: 1.25
    }

    Column {
      width: parent.width
      spacing: 10
      visible: !root.signedIn
      TextField {
        id: emailField
        width: parent.width
        placeholderText: "Email"
        text: root.account
        onAccepted: passField.forceActiveFocus()
        Keys.onEscapePressed: root.app.dismissSetup()
      }
      TextField {
        id: passField
        width: parent.width
        placeholderText: "Password"
        password: true
        onAccepted: root.signIn()
        Keys.onEscapePressed: root.app.dismissSetup()
      }
      Chip {
        text: root.busy ? "Signing in…" : "Sign in"
        selected: true
        fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
        onClicked: if (!root.busy) root.signIn()
      }
    }

    Column {
      width: parent.width
      spacing: 8
      visible: root.signedIn

      Repeater {
        model: root.found
        Rectangle {
          width: parent.width
          height: 44
          radius: 10
          color: Qt.rgba(root.app.fg.r, root.app.fg.g, root.app.fg.b, 0.05)
          border.width: 1
          border.color: root.app.line
          Column {
            anchors.left: parent.left; anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            Text { text: modelData.model; color: root.app.fg; font.family: root.app.fontFamily; font.pixelSize: 13 }
            Text { text: modelData.host + " · " + modelData.kind; color: root.app.dimmer; font.family: root.app.fontFamily; font.pixelSize: 11 }
          }
          Chip {
            anchors.right: parent.right; anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: "Add"
            selected: true
            fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
            onClicked: root.add(modelData)
          }
        }
      }
      Text {
        visible: root.scanned && !root.busy && root.found.length === 0
        width: parent.width
        wrapMode: Text.WordWrap
        text: root.app.devices.length
          ? "No other TP-Link lights found."
          : "No TP-Link lights found. Check the light is powered, set up in the Tapo app, and on the same network as this computer."
        color: root.app.dim
        font.family: root.app.fontFamily
        font.pixelSize: 12
      }
      Row {
        spacing: 8
        Chip {
          text: root.busy ? "Scanning…" : (root.scanned ? "Scan again" : "Scan")
          fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
          onClicked: if (!root.busy) root.scan()
        }
        Chip {
          visible: root.app.devices.length > 0
          text: "Done"
          fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
          onClicked: root.app.showSetup = false
        }
      }
    }

    Text {
      visible: root.error !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      text: root.error
      color: root.app.urgent
      font.family: root.app.fontFamily
      font.pixelSize: 12
    }
  }

  Component.onCompleted: if (root.signedIn && root.app.devices.length === 0) root.scan()
}
