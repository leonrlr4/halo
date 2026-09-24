import QtQuick
import "../lib/Colors.js" as Colors

// One colour for the whole light, or white at a temperature.
Item {
  id: root
  property var app

  readonly property var st: app.dev ? app.dev.state : null
  readonly property var caps: app.dev ? app.dev.caps : null
  readonly property var hs: st && st.mode === "solid" ? st.hs : [0, 0]

  Row {
    anchors.fill: parent
    spacing: 28

    HueWheel {
      id: wheel
      width: Math.min(parent.height, 220); height: width
      visible: root.caps && root.caps.color
      hs: root.hs
      ring: root.app.fg
      onPicked: function(hs) { root.app.pickColor(hs) }
      onReleased: function(hs) { root.app.pickColor(hs) }
    }

    Column {
      width: parent.width - (wheel.visible ? wheel.width + 28 : 0)
      spacing: 18

      LightSlider {
        width: parent.width
        visible: root.caps && root.caps.color
        label: "Saturation"
        from: 0; to: 100
        value: root.hs[1]
        valueText: Math.round(value) + "%"
        fg: root.app.fg
        fontFamily: root.app.fontFamily
        stops: ["#ffffff", Colors.hsToHex([root.hs[0], 100])]
        onMoved: function(v) { root.app.pickColor([root.hs[0], v]) }
      }

      LightSlider {
        id: temp
        width: parent.width
        visible: root.caps && root.caps.tempRange
        label: "White"
        from: root.caps && root.caps.tempRange ? root.caps.tempRange[0] : 2500
        to: root.caps && root.caps.tempRange ? root.caps.tempRange[1] : 6500
        step: 50
        value: root.st && root.st.mode === "temp" && root.st.temp ? root.st.temp : (from + to) / 2
        valueText: root.st && root.st.mode === "temp" ? Math.round(value) + " K" : ""
        fg: root.app.fg
        fontFamily: root.app.fontFamily
        stops: root.app.kelvinRamp(from, to)
        onMoved: function(v) { root.app.pickTemp(v) }
      }

      Text {
        text: "Quick colors"
        color: root.app.dim
        font.family: root.app.fontFamily
        font.pixelSize: 11
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
        visible: root.caps && root.caps.color
      }
      Flow {
        width: parent.width
        spacing: 8
        visible: root.caps && root.caps.color
        Repeater {
          model: Colors.swatches
          Rectangle {
            width: 30; height: 30; radius: 15
            color: Colors.hsToHex(modelData)
            readonly property bool current: root.st && root.st.mode === "solid"
              && Math.abs(root.hs[0] - modelData[0]) < 3 && Math.abs(root.hs[1] - modelData[1]) < 3
            border.width: current ? 2 : 0
            border.color: root.app.fg
            scale: hov.hovered ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: 100 } }
            HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
            MouseArea { anchors.fill: parent; onClicked: root.app.pickColor(modelData) }
          }
        }
        Repeater {
          model: root.caps && root.caps.tempRange ? [2700, 4000, 6500] : []
          Rectangle {
            width: 30; height: 30; radius: 15
            readonly property var rgb: Colors.kelvinToRgb(modelData)
            color: Qt.rgba(rgb[0], rgb[1], rgb[2], 1)
            border.width: root.st && root.st.mode === "temp" && Math.abs(root.st.temp - modelData) < 60 ? 2 : 0
            border.color: root.app.fg
            Text {
              anchors.centerIn: parent
              text: Math.round(modelData / 100) / 10 + "k"
              font.pixelSize: 9
              font.family: root.app.fontFamily
              color: "#333333"
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            MouseArea { anchors.fill: parent; onClicked: root.app.pickTemp(modelData) }
          }
        }
      }
    }
  }
}
