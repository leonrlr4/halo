import QtQuick
import "../lib/Colors.js" as Colors

// Hue round the rim, saturation from the centre out. Hue 0 is east and hue
// increases clockwise, matching atan2 in screen coordinates, which is what
// hsAt uses to read a click back.
Item {
  id: root

  property var hs: [0, 0]
  property color ring: "#ffffff"
  signal picked(var hs)          // while dragging
  signal released(var hs)        // when the drag ends

  implicitWidth: 200
  implicitHeight: 200

  readonly property real r: Math.min(width, height) / 2

  Canvas {
    id: disc
    anchors.fill: parent
    antialiasing: true
    renderStrategy: Canvas.Cooperative
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
      var ctx = getContext("2d")
      var cx = width / 2, cy = height / 2, R = Math.min(cx, cy)
      ctx.reset()
      // Qt's conical gradient runs counter-clockwise from its start angle,
      // so stops go in with hue descending to come out clockwise on screen.
      var cone = ctx.createConicalGradient(cx, cy, 0)
      for (var i = 0; i <= 12; i++) {
        var c = Colors.hsToRgb([(360 - i * 30) % 360, 100])
        cone.addColorStop(i / 12, Qt.rgba(c[0], c[1], c[2], 1))
      }
      ctx.beginPath()
      ctx.arc(cx, cy, R, 0, Math.PI * 2, false)
      ctx.fillStyle = cone
      ctx.fill()
      var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R)
      g.addColorStop(0, "rgba(255,255,255,1)")
      g.addColorStop(1, "rgba(255,255,255,0)")
      ctx.beginPath()
      ctx.arc(cx, cy, R, 0, Math.PI * 2, false)
      ctx.fillStyle = g
      ctx.fill()
    }
  }

  // The knob, filled with the colour it points at.
  Rectangle {
    readonly property real a: root.hs[0] * Math.PI / 180
    readonly property real d: root.hs[1] / 100 * root.r
    width: 18; height: 18; radius: 9
    x: root.width / 2 + Math.cos(a) * d - width / 2
    y: root.height / 2 + Math.sin(a) * d - height / 2
    color: Colors.hsToHex(root.hs)
    border.width: 2
    border.color: root.ring
    Rectangle {
      anchors.fill: parent; anchors.margins: -3; radius: width / 2
      color: "transparent"; border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.45)
    }
  }

  function hsAt(x, y) {
    var dx = x - width / 2, dy = y - height / 2
    var h = Math.round((Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360)
    var s = Math.round(Math.min(1, Math.sqrt(dx * dx + dy * dy) / root.r) * 100)
    return [h, s]
  }

  MouseArea {
    anchors.fill: parent
    preventStealing: true
    onPressed: function(m) { root.picked(root.hsAt(m.x, m.y)) }
    onPositionChanged: function(m) { if (pressed) root.picked(root.hsAt(m.x, m.y)) }
    onReleased: function(m) { root.released(root.hsAt(m.x, m.y)) }
  }
}
