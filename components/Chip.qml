import QtQuick

// A pill: tabs, layout choices, effect names. `selected` fills it with the
// accent; `swatch` puts a colour dot (or a gradient bar) in front of the text.
Rectangle {
  id: root

  property string text: ""
  property bool selected: false
  property color fg: "#ffffff"
  property color accent: "#88ccff"
  property string fontFamily: ""
  property var swatch: null          // null, a colour, or an array of colours
  property int pad: 12
  property string hint: ""           // a key shown faintly after the label

  signal clicked()
  signal rightClicked()

  implicitHeight: 30
  implicitWidth: row.implicitWidth + pad * 2
  radius: height / 2
  color: selected ? Qt.rgba(accent.r, accent.g, accent.b, 0.22)
       : hover.hovered ? Qt.rgba(fg.r, fg.g, fg.b, 0.08) : Qt.rgba(fg.r, fg.g, fg.b, 0.04)
  border.width: 1
  border.color: selected ? Qt.rgba(accent.r, accent.g, accent.b, 0.7) : Qt.rgba(fg.r, fg.g, fg.b, 0.10)
  Behavior on color { ColorAnimation { duration: 120 } }

  HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }

  Row {
    id: row
    anchors.centerIn: parent
    spacing: 7

    Rectangle {
      visible: root.swatch !== null && !Array.isArray(root.swatch)
      width: 12; height: 12; radius: 6
      anchors.verticalCenter: parent.verticalCenter
      color: visible ? root.swatch : "transparent"
    }
    Row {
      visible: Array.isArray(root.swatch)
      anchors.verticalCenter: parent.verticalCenter
      Repeater {
        model: Array.isArray(root.swatch) ? root.swatch : []
        Rectangle {
          width: Math.max(2, 36 / Math.max(1, root.swatch.length)); height: 12
          color: modelData
          radius: index === 0 || index === root.swatch.length - 1 ? 3 : 0
        }
      }
    }
    Text {
      visible: root.text !== ""
      text: root.text
      color: root.selected ? root.fg : Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.8)
      font.family: root.fontFamily
      font.pixelSize: 12
      anchors.verticalCenter: parent.verticalCenter
    }
    Text {
      visible: root.hint !== ""
      text: root.hint
      color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.35)
      font.family: root.fontFamily
      font.pixelSize: 10
      anchors.verticalCenter: parent.verticalCenter
    }
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    onClicked: function(m) { if (m.button === Qt.RightButton) root.rightClicked(); else root.clicked() }
  }
}
