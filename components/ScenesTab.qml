import QtQuick
import "../lib/Colors.js" as Colors

// Saved looks, and the effects built into the light itself.
Item {
  id: root
  property var app

  readonly property var caps: app.dev ? app.dev.caps : null
  readonly property var st: app.dev ? app.dev.state : null

  Flickable {
    anchors.fill: parent
    contentHeight: col.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    Column {
      id: col
      width: parent.width
      spacing: 12

      Text {
        text: "Saved"
        color: root.app.dim
        font.family: root.app.fontFamily
        font.pixelSize: 11
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
      }
      Text {
        visible: root.app.favorites.length === 0
        text: "Nothing saved yet. Make a gradient and press S to keep it here."
        color: root.app.dimmer
        font.family: root.app.fontFamily
        font.pixelSize: 12
      }
      Flow {
        width: parent.width
        spacing: 8
        Repeater {
          model: root.app.favorites
          Chip {
            text: modelData.name
            swatch: root.app.favoriteSwatch(modelData)
            fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
            onClicked: root.app.applyFavorite(modelData)
            onRightClicked: root.app.request("favorites.delete", { index: index }, null)
          }
        }
      }

      Item { width: 1; height: 6 }

      Text {
        visible: root.caps && root.caps.effects.length > 0
        text: "Built into the light"
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
          model: root.caps ? root.caps.effects : []
          Chip {
            text: modelData
            selected: root.st && root.st.mode === "effect" && root.st.effect === modelData
            fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
            onClicked: root.app.pickEffect(modelData)
          }
        }
      }
      Text {
        visible: root.app.favorites.length > 0
        text: "Right-click a saved look to delete it."
        color: root.app.dimmer
        font.family: root.app.fontFamily
        font.pixelSize: 11
      }
    }
  }
}
