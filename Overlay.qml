import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import "lib/Colors.js" as Colors
import "components"

// Halo: the lights in the room, from a hotkey.
//
// This file owns the connection to the daemon (halo/daemon.py) and the state
// every tab reads. The daemon is started when the panel opens and the socket
// is dropped when it closes, so the daemon can exit a minute later: while the
// panel is closed, nothing of Halo is running.
Item {
  id: root

  property var shell: null

  readonly property string pluginDir: Quickshell.env("HOME") + "/.config/omarchy/plugins/leonrlr4.halo"
  readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || ("/run/user/" + Quickshell.env("UID"))

  // ---- state ---------------------------------------------------------------
  property bool opened: false
  property var devices: []
  property string selId: ""                 // a device id, or "all"
  property string account: ""
  property var theme: ({ follow: false, source: "theme", layout: "gradient", vivid: true })
  property var favorites: []
  property bool helloDone: false
  property bool showSetup: false
  property int tab: 0
  property var stops: Colors.evenStops(Colors.presets[0].colors)

  // Local edits win over what the daemon reports for a moment: its events
  // describe the light as of the last command it finished, which during a
  // drag is always a step behind the pointer.
  property var localUntil: ({})

  readonly property var dev: {
    if (root.devices.length === 0) return null
    for (var i = 0; i < root.devices.length; i++)
      if (root.devices[i].id === root.selId) return root.devices[i]
    return root.devices[0]
  }
  readonly property int segmentCount: root.dev ? Math.max(1, root.dev.caps.segments) : 50
  readonly property bool ready: root.dev !== null && root.dev.status === "ready"

  // ---- theme ---------------------------------------------------------------
  readonly property color bg: Color.menu.background
  readonly property color fg: Color.menu.text
  readonly property color accent: Color.accent
  readonly property color urgent: Color.urgent
  readonly property color line: Qt.rgba(fg.r, fg.g, fg.b, 0.10)
  readonly property color dim: Qt.rgba(fg.r, fg.g, fg.b, 0.58)
  readonly property color dimmer: Qt.rgba(fg.r, fg.g, fg.b, 0.36)
  readonly property string fontFamily: Style.font.menuFamily

  // ---- lifecycle -------------------------------------------------------------
  function open(payloadJson) {
    root.opened = true
    root.connectDaemon()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }
  function close() {
    root.opened = false
    root.showSetup = false
    sock.connected = false
    retry.stop()
  }
  function toggle() { if (root.opened) root.close(); else root.open("{}") }

  // Escape from the setup view goes back to the lights when there are any,
  // and closes the panel when there is nothing to go back to.
  function dismissSetup() {
    if (root.showSetup && root.devices.length) {
      root.showSetup = false
      keyCatcher.forceActiveFocus()
    } else {
      root.close()
    }
  }

  // ---- the daemon connection ------------------------------------------------
  property int nextId: 1
  property var callbacks: ({})
  property int attempts: 0

  function connectDaemon() {
    if (sock.connected) { root.request("hello", {}, root.applyHello); return }
    root.attempts = 0
    starter.running = true
    retry.start()
  }

  // Detached with setsid, so the daemon is not a child of the shell: it must
  // outlive this panel, and die on its own schedule, not the shell's.
  Process {
    id: starter
    command: ["bash", "-c", 'setsid -f "$0" daemon >/dev/null 2>&1 </dev/null', root.pluginDir + "/bin/halo"]
  }

  Timer {
    id: retry
    interval: 120
    repeat: true
    onTriggered: {
      if (sock.connected || !root.opened) { stop(); return }
      if (++root.attempts > 60) { stop(); return }
      sock.connected = true
    }
  }

  Socket {
    id: sock
    path: root.runtimeDir + "/leonrlr4.halo.sock"
    parser: SplitParser { onRead: function(line) { root.onLine(line) } }
    onConnectionStateChanged: {
      if (connected) {
        retry.stop()
        root.request("hello", {}, root.applyHello)
      } else if (root.opened) {
        root.helloDone = false
        root.attempts = 0
        starter.running = true
        retry.start()
      }
    }
  }

  function request(op, params, cb) {
    if (!sock.connected) { if (cb) cb(null, "Not connected to the Halo daemon"); return }
    var id = root.nextId++
    if (cb) root.callbacks[id] = cb
    var msg = Object.assign({ id: id, op: op }, params || {})
    sock.write(JSON.stringify(msg) + "\n")
    sock.flush()
  }

  function onLine(line) {
    var msg
    try { msg = JSON.parse(line) } catch (e) { return }
    if (msg.event === "device") { root.upsertDevice(msg.device, true); return }
    if (msg.event === "theme") { root.theme = msg.theme; return }
    if (msg.event === "favorites") { root.favorites = msg.favorites; return }
    var cb = root.callbacks[msg.id]
    if (!cb) return
    delete root.callbacks[msg.id]
    cb(msg.ok ? msg.result : null, msg.ok ? "" : msg.error)
  }

  function applyHello(h) {
    if (!h) return
    root.account = h.account
    root.theme = h.theme
    root.favorites = h.favorites
    root.devices = h.devices
    if (!root.selId && h.devices.length) root.selId = h.devices.length > 1 ? "all" : h.devices[0].id
    root.helloDone = true
    if (h.needsSetup) root.showSetup = true
  }

  function upsertDevice(d, fromDaemon) {
    var list = root.devices.slice()
    var found = false
    for (var i = 0; i < list.length; i++) {
      if (list[i].id !== d.id) continue
      found = true
      if (fromDaemon && Date.now() < (root.localUntil[d.id] || 0)) {
        // Keep what the user just did on screen; take everything else.
        d = Object.assign({}, d, { state: list[i].state })
      }
      list[i] = d
    }
    if (!found) list.push(d)
    root.devices = list
  }

  function selectDevice(id) { root.selId = id }

  // ---- edits -----------------------------------------------------------------
  function targets() {
    if (root.selId === "all") return root.devices
    return root.dev ? [root.dev] : []
  }

  function editLocal(patch) {
    var now = Date.now()
    var until = Object.assign({}, root.localUntil)
    var list = root.devices.map(function(d) {
      var hit = root.selId === "all" || d.id === (root.dev && root.dev.id)
      if (!hit) return d
      until[d.id] = now + 900
      return Object.assign({}, d, { state: Object.assign({}, d.state, patch) })
    })
    root.localUntil = until
    root.devices = list
  }

  function send(params) {
    var p = Object.assign({ device: root.selId === "all" ? "all" : (root.dev ? root.dev.id : "all") }, params)
    root.request("set", p, null)
  }

  function pickColor(hs) {
    hs = [Math.round(hs[0]) % 360, Math.round(hs[1])]
    root.editLocal({ mode: "solid", hs: hs, on: true, effect: null })
    root.send({ hs: hs })
  }
  function pickTemp(k) {
    root.editLocal({ mode: "temp", temp: Math.round(k), on: true, effect: null })
    root.send({ temp: Math.round(k) })
  }
  function pickEffect(name) {
    root.editLocal({ mode: "effect", effect: name, on: true })
    root.send({ effect: name })
  }
  function setBrightness(v) {
    root.editLocal({ brightness: Math.round(v), on: true })
    root.send({ brightness: Math.round(v) })
  }
  function nudgeBrightness(d) {
    if (!root.dev) return
    root.setBrightness(Math.max(1, Math.min(100, root.dev.state.brightness + d)))
  }
  function togglePower() {
    if (!root.dev) return
    var on = !root.dev.state.on
    root.editLocal({ on: on })
    root.send({ power: on })
  }
  function setStops(stops) {
    root.stops = stops
    var cells = Colors.gradientAt(stops, root.segmentCount)
    root.editLocal({ mode: "segments", segments: cells, on: true, effect: null })
    root.send({ segments: cells })
  }
  function applyTheme() {
    root.request("theme.apply", { device: root.selId === "all" ? "all" : (root.dev ? root.dev.id : "all") }, null)
  }

  function saveFavorite() {
    var cells = Colors.gradientAt(root.stops, root.segmentCount)
    root.request("favorites.save", { favorite: {
      name: "Look " + (root.favorites.length + 1), segments: cells, stops: root.stops } }, null)
    toast.show("Saved to Scenes")
  }
  function applyFavorite(f) {
    if (f.stops) { root.setStops(f.stops); return }
    if (f.segments) {
      root.editLocal({ mode: "segments", segments: f.segments, on: true, effect: null })
      root.send({ segments: f.segments })
      return
    }
    if (f.hs) root.pickColor(f.hs)
  }
  function favoriteSwatch(f) {
    var cells = f.stops ? Colors.gradientAt(f.stops, 8)
              : f.segments ? f.segments.filter(function(_, i) { return i % Math.max(1, Math.floor(f.segments.length / 8)) === 0 })
              : [f.hs]
    return cells.map(function(c) { return Colors.hsToHex(c) })
  }

  // ---- what the strip shows -----------------------------------------------------
  function kelvinRamp(from, to) {
    var out = []
    for (var i = 0; i <= 6; i++) {
      var c = Colors.kelvinToRgb(from + (to - from) * i / 6)
      out.push(Qt.rgba(c[0], c[1], c[2], 1))
    }
    return out
  }

  function stripColors(d) {
    if (!d) return []
    var s = d.state, n = Math.max(1, d.caps.segments)
    if (s.mode === "segments" && s.segments && s.segments.length)
      return s.segments.map(function(c) { return Colors.hsToHex(c) })
    var one
    if (s.mode === "temp" && s.temp) {
      var k = Colors.kelvinToRgb(s.temp)
      one = Qt.rgba(k[0], k[1], k[2], 1)
    } else if (d.caps.color) {
      one = Colors.hsToHex(s.hs)
    } else {
      one = "#fff2d6"
    }
    var out = []
    for (var i = 0; i < n; i++) out.push(one)
    return out
  }

  // The light's own dominant colour, for the accents that follow it.
  readonly property color lightColor: {
    var c = root.stripColors(root.dev)
    return c.length ? c[Math.floor(c.length / 2)] : root.accent
  }

  // ---- the surface ---------------------------------------------------------------
  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-halo"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle { anchors.fill: parent; color: Color.menu.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.close() }

    Rectangle {
      id: card
      width: Math.min(Style.space(780), panel.width - Style.gapsOut * 2)
      height: Math.min(Style.space(640), panel.height - Style.gapsOut * 2)
      anchors.centerIn: parent
      color: root.bg
      radius: Math.max(Style.cornerRadius, 14)
      border.width: 1
      border.color: Qt.rgba(root.lightColor.r, root.lightColor.g, root.lightColor.b, root.dev && root.dev.state.on ? 0.35 : 0.1)
      clip: true
      Behavior on border.color { ColorAnimation { duration: 300 } }

      MouseArea { anchors.fill: parent; onClicked: keyCatcher.forceActiveFocus() }

      // Light from the strip, washing down the top of the card.
      Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 230
        opacity: root.dev && root.dev.state.on ? 0.10 + 0.14 * root.dev.state.brightness / 100 : 0
        Behavior on opacity { NumberAnimation { duration: 300 } }
        gradient: Gradient {
          GradientStop { position: 0; color: root.lightColor }
          GradientStop { position: 1; color: "transparent" }
        }
      }

      Item {
        id: keyCatcher
        anchors.fill: parent
        anchors.margins: 26
        focus: true

        Keys.onPressed: function(event) {
          if (!keyCatcher.activeFocus) return
          switch (event.key) {
          case Qt.Key_Escape:
          case Qt.Key_Q:
            if (root.showSetup) root.dismissSetup()
            else root.close()
            event.accepted = true; return
          case Qt.Key_1: root.tab = 0; event.accepted = true; return
          case Qt.Key_2: root.tab = 1; event.accepted = true; return
          case Qt.Key_3: root.tab = 2; event.accepted = true; return
          case Qt.Key_4: root.tab = 3; event.accepted = true; return
          case Qt.Key_Space: root.togglePower(); event.accepted = true; return
          case Qt.Key_Left:
          case Qt.Key_H:
            root.nudgeBrightness(event.modifiers & Qt.ShiftModifier ? -1 : -5); event.accepted = true; return
          case Qt.Key_Right:
          case Qt.Key_L:
            root.nudgeBrightness(event.modifiers & Qt.ShiftModifier ? 1 : 5); event.accepted = true; return
          case Qt.Key_S:
            if (root.tab === 1) { root.saveFavorite(); event.accepted = true }
            return
          case Qt.Key_T:
            root.applyTheme(); event.accepted = true; return
          case Qt.Key_Return:
          case Qt.Key_Enter:
            if (root.tab === 2) { root.applyTheme(); event.accepted = true }
            return
          case Qt.Key_Tab:
            if (root.devices.length > 1) {
              var ids = ["all"].concat(root.devices.map(function(d) { return d.id }))
              root.selId = ids[(ids.indexOf(root.selId) + 1) % ids.length]
            }
            event.accepted = true; return
          }
        }

        // ---- waiting for the daemon ------------------------------------------
        Column {
          anchors.centerIn: parent
          spacing: 10
          visible: !root.helloDone
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.attempts > 50 ? "The Halo daemon did not start." : "Waking the lights…"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: 14
          }
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.attempts > 50
            text: "Run " + root.pluginDir + "/scripts/setup --check in a terminal to see why."
            color: root.dimmer
            font.family: root.fontFamily
            font.pixelSize: 11
          }
        }

        SetupView {
          anchors.fill: parent
          app: root
          visible: root.helloDone && root.showSetup
        }

        // ---- the panel --------------------------------------------------------
        Item {
          anchors.fill: parent
          visible: root.helloDone && !root.showSetup && root.dev !== null

          // Header: which light, how it is, and its power.
          Item {
            id: header
            width: parent.width
            height: 46

            Rectangle {
              id: dot
              width: 12; height: 12; radius: 6
              anchors.left: parent.left
              anchors.top: parent.top; anchors.topMargin: 8
              color: !root.dev ? root.dimmer
                   : root.dev.status === "error" ? root.urgent
                   : root.dev.status === "connecting" ? root.dim
                   : root.dev.state.on ? root.lightColor : root.dimmer
              SequentialAnimation on opacity {
                running: root.opened && root.dev !== null && root.dev.status === "connecting"
                loops: Animation.Infinite
                NumberAnimation { to: 0.3; duration: 500 }
                NumberAnimation { to: 1; duration: 500 }
              }
            }
            Column {
              anchors.left: dot.right; anchors.leftMargin: 12
              anchors.top: parent.top
              spacing: 3
              Text {
                text: root.selId === "all" ? "All lights" : (root.dev ? root.dev.name : "")
                color: root.fg
                font.family: root.fontFamily
                font.pixelSize: 19
                font.weight: Font.DemiBold
              }
              Text {
                text: !root.dev ? ""
                    : root.dev.status === "error" ? "Unreachable · " + root.dev.error + " · retrying"
                    : root.dev.status === "connecting" ? "Connecting to " + root.dev.host + "…"
                    : root.dev.model + " · " + root.dev.host
                      + (root.dev.state.mode === "effect" ? " · " + root.dev.state.effect : "")
                color: root.dev && root.dev.status === "error" ? root.urgent : root.dimmer
                font.family: root.fontFamily
                font.pixelSize: 11
                elide: Text.ElideRight
                width: header.width - 220
              }
            }

            Row {
              anchors.right: parent.right
              anchors.top: parent.top
              spacing: 10

              Chip {
                text: "+"
                fg: root.fg; accent: root.accent; fontFamily: root.fontFamily
                onClicked: root.showSetup = true
              }

              // Power.
              Rectangle {
                id: power
                width: 58; height: 30; radius: 15
                readonly property bool on: root.dev ? root.dev.state.on : false
                color: on ? Qt.rgba(root.lightColor.r, root.lightColor.g, root.lightColor.b, 0.85)
                          : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.10)
                Behavior on color { ColorAnimation { duration: 180 } }
                Rectangle {
                  width: 24; height: 24; radius: 12
                  y: 3
                  x: power.on ? power.width - width - 3 : 3
                  color: "#ffffff"
                  Behavior on x { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                MouseArea { anchors.fill: parent; onClicked: root.togglePower() }
              }
            }
          }

          // Several lights: pick one, or all of them at once.
          Row {
            id: picker
            anchors.top: header.bottom
            anchors.topMargin: root.devices.length > 1 ? 4 : 0
            height: root.devices.length > 1 ? 30 : 0
            visible: root.devices.length > 1
            spacing: 8
            Chip {
              text: "All"; hint: "Tab"
              selected: root.selId === "all"
              fg: root.fg; accent: root.accent; fontFamily: root.fontFamily
              onClicked: root.selId = "all"
            }
            Repeater {
              model: root.devices
              Chip {
                text: modelData.name
                selected: root.selId === modelData.id
                swatch: modelData.status === "ready" && modelData.state.on ? root.stripColors(modelData)[0] : root.dimmer
                fg: root.fg; accent: root.accent; fontFamily: root.fontFamily
                onClicked: root.selId = modelData.id
              }
            }
          }

          // The strip itself.
          StripPreview {
            id: hero
            anchors.top: picker.bottom
            anchors.topMargin: 22
            width: parent.width
            height: 30
            colors: root.stripColors(root.dev)
            on: root.dev ? root.dev.state.on : false
            effect: root.dev && root.dev.state.mode === "effect" ? (root.dev.state.effect || "") : ""
            level: root.dev ? root.dev.state.brightness / 100 : 0
            base: root.bg
            radius: 8
            opacity: root.ready ? 1 : 0.5
          }

          LightSlider {
            id: brightness
            anchors.top: hero.bottom
            anchors.topMargin: 26
            width: parent.width
            label: "Brightness"
            from: 1; to: 100
            value: root.dev ? root.dev.state.brightness : 0
            fg: root.fg
            fontFamily: root.fontFamily
            stops: [Qt.rgba(root.lightColor.r * 0.15, root.lightColor.g * 0.15, root.lightColor.b * 0.15, 1), root.lightColor]
            enabled2: root.ready
            onMoved: function(v) { root.setBrightness(v) }
          }

          // Tabs.
          Row {
            id: tabs
            anchors.top: brightness.bottom
            anchors.topMargin: 22
            spacing: 8
            Repeater {
              model: {
                var t = [["Color", "1"]]
                t.push(["Gradient", "2"])
                t.push(["Theme", "3"])
                t.push(["Scenes", "4"])
                return t
              }
              Chip {
                text: modelData[0]; hint: modelData[1]
                selected: root.tab === index
                opacity: index === 1 && root.segmentCount <= 1 ? 0.35 : 1
                fg: root.fg; accent: root.accent; fontFamily: root.fontFamily
                onClicked: root.tab = index
              }
            }
          }

          Item {
            id: body
            anchors.top: tabs.bottom
            anchors.topMargin: 20
            anchors.bottom: footer.top
            anchors.bottomMargin: 12
            width: parent.width
            opacity: root.ready ? 1 : 0.45
            enabled: root.ready

            ColorTab { anchors.fill: parent; app: root; visible: root.tab === 0 }
            GradientTab { anchors.fill: parent; app: root; visible: root.tab === 1 && root.segmentCount > 1 }
            Text {
              visible: root.tab === 1 && root.segmentCount <= 1
              anchors.centerIn: parent
              text: "This light shows one color at a time, so it has no gradient."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: 13
            }
            ThemeTab { anchors.fill: parent; app: root; visible: root.tab === 2 }
            ScenesTab { anchors.fill: parent; app: root; visible: root.tab === 3 }
          }

          Text {
            id: footer
            anchors.bottom: parent.bottom
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "Space power   ←/→ brightness   1–4 tabs   T theme   Esc close"
            color: root.dimmer
            font.family: root.fontFamily
            font.pixelSize: 10
          }
        }

        // Transient confirmation, bottom right.
        Rectangle {
          id: toast
          property string message: ""
          function show(m) { message = m; opacity = 1; toastTimer.restart() }
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          width: toastText.implicitWidth + 24; height: 28; radius: 14
          color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)
          opacity: 0
          Behavior on opacity { NumberAnimation { duration: 200 } }
          Text { id: toastText; anchors.centerIn: parent; text: toast.message; color: root.fg; font.family: root.fontFamily; font.pixelSize: 11 }
          Timer { id: toastTimer; interval: 1600; onTriggered: toast.opacity = 0 }
        }
      }
    }
  }
}
