import QtQuick
import qs.Commons

// A thick slider whose track shows what it controls: a ramp of the light's
// own colour for brightness, the blackbody range for temperature.
Item {
  id: root

  property real from: 0
  property real to: 100
  property real value: 50
  property real step: 1
  property string label: ""
  property string valueText: Math.round(value) + "%"
  property var stops: [Qt.rgba(1, 1, 1, 0.1), Qt.rgba(1, 1, 1, 0.9)]   // colours along the track
  property color fg: "#ffffff"
  property string fontFamily: ""
  property bool enabled2: true

  signal moved(real value)
  signal released(real value)

  implicitHeight: 44

  readonly property real frac: (value - from) / (to - from)

  Text {
    id: caption
    anchors.left: parent.left
    anchors.top: parent.top
    text: root.label
    color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.6)
    font.family: root.fontFamily
    font.pixelSize: 11
    font.letterSpacing: 1.2
    font.capitalization: Font.AllUppercase
  }
  Text {
    anchors.right: parent.right
    anchors.top: parent.top
    text: root.valueText
    color: root.fg
    font.family: root.fontFamily
    font.pixelSize: 11
  }

  Rectangle {
    id: track
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    height: 18
    radius: height / 2
    opacity: root.enabled2 ? 1 : 0.35
    color: "transparent"
    border.width: 1
    border.color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.12)

    Canvas {
      id: ramp
      anchors.fill: parent
      z: -1
      property var stops: root.stops
      onStopsChanged: requestPaint()
      onWidthChanged: requestPaint()
      onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var r = height / 2, n = stops.length
        var g = ctx.createLinearGradient(0, 0, width, 0)
        for (var i = 0; i < n; i++) g.addColorStop(n > 1 ? i / (n - 1) : 0, stops[i])
        ctx.beginPath()
        ctx.moveTo(r, 0); ctx.lineTo(width - r, 0)
        ctx.arc(width - r, r, r, -Math.PI / 2, Math.PI / 2, false)
        ctx.lineTo(r, height)
        ctx.arc(r, r, r, Math.PI / 2, Math.PI * 1.5, false)
        ctx.closePath()
        ctx.fillStyle = g
        ctx.fill()
      }
    }

    Rectangle {
      width: 22; height: 22; radius: 11
      anchors.verticalCenter: parent.verticalCenter
      x: Math.max(0, Math.min(track.width - width, root.frac * track.width - width / 2))
      color: "#ffffff"
      border.width: 2
      border.color: Qt.rgba(0, 0, 0, 0.35)
      Behavior on x { enabled: !area.pressed; NumberAnimation { duration: 120 } }
    }

    MouseArea {
      id: area
      anchors.fill: parent
      anchors.margins: -8
      enabled: root.enabled2
      preventStealing: true
      function valueAt(mx) {
        var f = Math.max(0, Math.min(1, (mx - 8) / track.width))
        var v = root.from + f * (root.to - root.from)
        return Math.round(v / root.step) * root.step
      }
      onPressed: function(m) { root.moved(valueAt(m.x)) }
      onPositionChanged: function(m) { if (pressed) root.moved(valueAt(m.x)) }
      onReleased: function(m) { root.released(valueAt(m.x)) }
      onWheel: function(w) {
        var v = Math.max(root.from, Math.min(root.to, root.value + (w.angleDelta.y > 0 ? 5 : -5) * root.step))
        root.moved(v); root.released(v)
      }
    }
  }
}
