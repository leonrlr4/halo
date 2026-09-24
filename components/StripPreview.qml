import QtQuick
import QtQuick.Effects

// The strip as it is lit: one cell per segment, with the light it throws
// drawn as a blurred copy underneath. `colors` is an array of CSS colours,
// one per cell; a single-segment light gets one long cell.
Item {
  id: root

  property var colors: []
  property bool on: true
  // Built-in effects run on the light itself and report no colours, so the
  // preview animates a stand-in rather than pretending to show them.
  property string effect: ""
  property real level: 1.0          // brightness 0-1, dims the glow
  property color base: "#000000"
  property real radius: 6
  // Set while the colours are a preview of something not yet sent.
  property bool pending: false

  readonly property int count: Math.max(1, colors ? colors.length : 0)
  readonly property real gap: count > 20 ? 1 : 3

  function cellColor(i) {
    if (!root.on) return Qt.rgba(1, 1, 1, 0.05)
    if (root.effect) {
      var h = ((i / root.count) + shimmer.phase) % 1
      return Qt.hsva(h, 0.85, 1, 1)
    }
    return root.colors && root.colors.length ? root.colors[Math.min(i, root.colors.length - 1)] : root.base
  }

  QtObject {
    id: shimmer
    property real phase: 0
  }
  NumberAnimation {
    target: shimmer; property: "phase"; from: 0; to: 1; duration: 6000
    loops: Animation.Infinite; running: root.effect !== "" && root.on && root.visible
  }

  // The glow is a blurred copy of the cells, drawn first so it sits behind
  // them. A separate copy rather than the visible row as the effect's
  // source: layering the row that is also on screen draws it only once,
  // through the effect.
  // Cells are placed by hand rather than by a Row: a Row's height comes
  // from its children, and these children take their height from it.
  readonly property real cellWidth: (width - gap * (count - 1)) / count

  Item {
    id: glowSource
    anchors.fill: parent
    visible: false
    layer.enabled: true
    Repeater {
      model: root.count
      Rectangle {
        x: index * (root.cellWidth + root.gap)
        width: root.cellWidth
        height: glowSource.height
        color: root.cellColor(index)
      }
    }
  }

  MultiEffect {
    source: glowSource
    anchors.fill: glowSource
    autoPaddingEnabled: true
    blurEnabled: true
    blur: 1.0
    blurMax: 64
    blurMultiplier: 1.6
    brightness: 0.1
    saturation: 0.35
    opacity: root.on ? 0.45 + 0.55 * root.level : 0
    Behavior on opacity { NumberAnimation { duration: 250 } }
  }

  Item {
    id: cells
    anchors.fill: parent
    Repeater {
      model: root.count
      Rectangle {
        x: index * (root.cellWidth + root.gap)
        width: root.cellWidth
        height: cells.height
        radius: index === 0 || index === root.count - 1 ? root.radius : Math.min(2, root.radius)
        color: root.cellColor(index)
        Behavior on color { enabled: !root.effect; ColorAnimation { duration: 180 } }
      }
    }
  }

  Rectangle {
    anchors.fill: parent
    visible: root.pending
    color: "transparent"
    radius: root.radius
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.35)
  }
}
