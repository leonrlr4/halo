import QtQuick
import "../lib/Colors.js" as Colors

// Lay colours along the strip. The bar is the strip at full resolution; the
// knobs under it are the colour stops. Drag a knob to move it, click the bar
// to add one there, right-click a knob to remove it. The wheel edits
// whichever knob is selected. Every change goes to the light as it happens.
Item {
  id: root
  property var app

  readonly property var stops: app.stops
  readonly property int n: app.segmentCount
  readonly property var cells: Colors.gradientAt(stops, n)
  property int sel: 0

  function commit(stops) { root.app.setStops(stops) }

  function update(i, patch) {
    var s = root.stops.map(function(x) { return { pos: x.pos, hs: x.hs } })
    for (var k in patch) s[i][k] = patch[k]
    root.commit(s)
  }

  function addAt(pos) {
    var s = root.stops.map(function(x) { return { pos: x.pos, hs: x.hs } })
    var here = Colors.gradientAt(s, 101)[Math.round(pos * 100)]
    s.push({ pos: pos, hs: here })
    root.commit(s)
    root.sel = s.length - 1
  }

  function removeAt(i) {
    if (root.stops.length <= 1) return
    var s = root.stops.filter(function(_, k) { return k !== i })
    root.sel = Math.min(root.sel, s.length - 1)
    root.commit(s)
  }

  function reverse() {
    root.commit(root.stops.map(function(x) { return { pos: 1 - x.pos, hs: x.hs } }))
  }

  // Folds the gradient so it runs out and back: both ends of the strip end up
  // the same colour, which hides the join on a strip run round a room.
  function mirror() {
    var s = root.stops.map(function(x) { return { pos: x.pos / 2, hs: x.hs } })
    var back = root.stops.filter(function(x) { return x.pos < 1 })
      .map(function(x) { return { pos: 1 - x.pos / 2, hs: x.hs } })
    root.commit(s.concat(back))
  }

  function spread() {
    var s = root.stops.slice().sort(function(a, b) { return a.pos - b.pos })
    root.commit(Colors.evenStops(s.map(function(x) { return x.hs })))
  }

  Column {
    anchors.fill: parent
    spacing: 14

    // ---- the bar and its knobs ------------------------------------------
    Item {
      id: editor
      width: parent.width
      height: 78

      Row {
        id: bar
        width: parent.width
        height: 44
        spacing: 1
        Repeater {
          model: root.cells.length
          Rectangle {
            width: (bar.width - (root.cells.length - 1)) / root.cells.length
            height: bar.height
            radius: index === 0 || index === root.cells.length - 1 ? 8 : 1
            color: Colors.hsToHex(root.cells[index])
          }
        }
        MouseArea {
          width: bar.width; height: bar.height
          cursorShape: Qt.CrossCursor
          onClicked: function(m) { root.addAt(Math.max(0, Math.min(1, m.x / bar.width))) }
        }
      }

      Repeater {
        model: root.stops.length
        Item {
          id: knob
          readonly property var stop: root.stops[index]
          width: 26; height: 30
          x: stop.pos * editor.width - width / 2
          y: bar.height + 4
          // The notch that points at the stop's place on the bar.
          Rectangle {
            width: 2; height: 6; anchors.horizontalCenter: parent.horizontalCenter
            y: -4; color: root.app.fg; opacity: 0.6
          }
          Rectangle {
            width: 22; height: 22; radius: 11
            anchors.horizontalCenter: parent.horizontalCenter
            y: 3
            color: Colors.hsToHex(knob.stop.hs)
            border.width: root.sel === index ? 3 : 1
            border.color: root.sel === index ? root.app.fg : Qt.rgba(0, 0, 0, 0.4)
          }
          MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            preventStealing: true
            cursorShape: Qt.SizeHorCursor
            onPressed: function(m) {
              if (m.button === Qt.RightButton) { root.removeAt(index); return }
              root.sel = index
            }
            onPositionChanged: function(m) {
              if (!(m.buttons & Qt.LeftButton)) return
              var p = mapToItem(editor, m.x, m.y)
              root.update(index, { pos: Math.max(0, Math.min(1, p.x / editor.width)) })
            }
          }
        }
      }
    }

    // ---- the selected stop, and whole-gradient actions ---------------------
    Row {
      width: parent.width
      height: parent.height - editor.height - parent.spacing
      spacing: 24

      HueWheel {
        width: Math.min(parent.height, 170); height: width
        hs: root.stops.length ? root.stops[Math.min(root.sel, root.stops.length - 1)].hs : [0, 0]
        ring: root.app.fg
        onPicked: function(hs) { root.update(Math.min(root.sel, root.stops.length - 1), { hs: hs }) }
      }

      Column {
        width: parent.width - 170 - 24
        spacing: 12

        Flow {
          width: parent.width
          spacing: 8
          Chip { text: "Reverse"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.reverse() }
          Chip { text: "Mirror"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.mirror() }
          Chip { text: "Even out"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.spread() }
          Chip {
            text: "Remove stop"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
            opacity: root.stops.length > 1 ? 1 : 0.4
            onClicked: root.removeAt(root.sel)
          }
          Chip {
            text: "Save"; hint: "S"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
            onClicked: root.app.saveFavorite()
          }
        }

        Text {
          text: "Start from"
          color: root.app.dim
          font.family: root.app.fontFamily
          font.pixelSize: 11
          font.letterSpacing: 1.2
          font.capitalization: Font.AllUppercase
        }
        Flow {
          width: parent.width
          spacing: 8
          Repeater {
            model: Colors.presets
            Chip {
              text: modelData.name
              swatch: modelData.colors.map(function(c) { return Colors.hsToHex(c) })
              fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
              onClicked: { root.sel = 0; root.commit(Colors.evenStops(modelData.colors)) }
            }
          }
        }
        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "Click the bar to add a stop · drag a stop to move it · right-click to remove"
          color: root.app.dimmer
          font.family: root.app.fontFamily
          font.pixelSize: 11
        }
      }
    }
  }
}
