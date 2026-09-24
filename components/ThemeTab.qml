import QtQuick
import "../lib/Colors.js" as Colors

// The strip in the colours of the current Omarchy theme or wallpaper, and the
// switch that keeps it that way when the theme changes.
Item {
  id: root
  property var app

  readonly property var opts: app.theme
  property var preview: ({ colors: [], segments: [] })
  readonly property var previewColors: (root.preview && root.preview.colors) || []
  readonly property var previewSegments: (root.preview && root.preview.segments) || []

  function refresh() {
    root.app.request("theme.preview", { options: root.opts, segments: root.app.segmentCount },
                     function(r) { if (r) root.preview = r })
  }
  function setOpt(k, v) {
    var patch = {}; patch[k] = v
    root.app.request("theme.options", { options: patch }, function(t) {
      root.app.theme = t
      root.refresh()
    })
  }

  onOptsChanged: refresh()
  onVisibleChanged: if (visible) refresh()
  Component.onCompleted: refresh()

  Column {
    anchors.fill: parent
    spacing: 16

    Row {
      spacing: 10
      Text {
        text: "Colors from"
        color: root.app.dim
        font.family: root.app.fontFamily
        font.pixelSize: 11
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
        anchors.verticalCenter: parent.verticalCenter
        width: 110
      }
      Chip { text: "Theme"; selected: root.opts.source === "theme"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.setOpt("source", "theme") }
      Chip { text: "Wallpaper"; selected: root.opts.source === "wallpaper"; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.setOpt("source", "wallpaper") }
    }

    Row {
      spacing: 10
      Text {
        text: "Layout"
        color: root.app.dim
        font.family: root.app.fontFamily
        font.pixelSize: 11
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
        anchors.verticalCenter: parent.verticalCenter
        width: 110
      }
      Repeater {
        model: [["gradient", "Gradient"], ["mirror", "Mirror"], ["blocks", "Blocks"], ["solid", "Accent only"]]
        Chip {
          text: modelData[1]
          selected: root.opts.layout === modelData[0]
          fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
          onClicked: root.setOpt("layout", modelData[0])
        }
      }
    }

    Row {
      spacing: 10
      Text {
        text: "Saturation"
        color: root.app.dim
        font.family: root.app.fontFamily
        font.pixelSize: 11
        font.letterSpacing: 1.2
        font.capitalization: Font.AllUppercase
        anchors.verticalCenter: parent.verticalCenter
        width: 110
      }
      Chip { text: "Vivid"; selected: root.opts.vivid; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.setOpt("vivid", true) }
      Chip { text: "As in theme"; selected: !root.opts.vivid; fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily; onClicked: root.setOpt("vivid", false) }
    }

    // What the strip would look like.
    Column {
      width: parent.width
      spacing: 8
      Row {
        spacing: 6
        Repeater {
          model: root.previewColors
          Rectangle { width: 22; height: 22; radius: 11; color: modelData }
        }
        Text {
          visible: root.previewColors.length === 0
          text: "This " + root.opts.source + " has no color a light can show: it is all grays."
          color: root.app.dim
          font.family: root.app.fontFamily
          font.pixelSize: 12
        }
      }
      StripPreview {
        width: parent.width
        height: 26
        colors: root.previewSegments
        base: root.app.bg
        radius: 6
        visible: root.previewSegments.length > 0
      }
    }

    Row {
      spacing: 12
      Chip {
        text: "Apply now"; hint: "Enter"
        selected: true
        fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
        opacity: root.previewColors.length ? 1 : 0.4
        onClicked: root.app.applyTheme()
      }
      Chip {
        text: root.opts.follow ? "Following theme changes" : "Follow theme changes"
        selected: root.opts.follow
        swatch: root.opts.follow ? root.app.accent : null
        fg: root.app.fg; accent: root.app.accent; fontFamily: root.app.fontFamily
        onClicked: root.setOpt("follow", !root.opts.follow)
      }
    }
    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      visible: root.opts.follow
      text: "Every time you switch Omarchy themes, the lights change with it, even with this panel closed."
      color: root.app.dimmer
      font.family: root.app.fontFamily
      font.pixelSize: 11
    }
  }
}
