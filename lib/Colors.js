.pragma library

// Colour helpers for the panel. A colour is [hue 0-359, saturation 0-100],
// the same shape the daemon uses; brightness is separate and never baked in.
// gradientAt mirrors halo/palette.py's gradient_at so that what the editor
// draws is what the strip gets.

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)) }

function hsToRgb(hs, value) {
  var h = ((hs[0] % 360) + 360) % 360 / 60
  var s = clamp(hs[1], 0, 100) / 100
  var v = value === undefined ? 1 : value
  var c = v * s, x = c * (1 - Math.abs(h % 2 - 1)), m = v - c
  var rgb = h < 1 ? [c, x, 0] : h < 2 ? [x, c, 0] : h < 3 ? [0, c, x]
          : h < 4 ? [0, x, c] : h < 5 ? [x, 0, c] : [c, 0, x]
  return [rgb[0] + m, rgb[1] + m, rgb[2] + m]
}

function hsToHex(hs) {
  var rgb = hsToRgb(hs)
  return "#" + rgb.map(function(c) {
    var s = Math.round(c * 255).toString(16)
    return s.length < 2 ? "0" + s : s
  }).join("")
}

function hexToHs(hex) {
  var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "")
  if (!m) return [0, 0]
  var r = parseInt(m[1], 16) / 255, g = parseInt(m[2], 16) / 255, b = parseInt(m[3], 16) / 255
  var max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min
  var h = 0
  if (d > 0) {
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
  }
  h = Math.round(h * 60)
  if (h < 0) h += 360
  return [h % 360, Math.round(max === 0 ? 0 : d / max * 100)]
}

// An approximation of blackbody colour, good enough to tint a preview:
// Tanner Helland's fit, valid from 1000 K to 40000 K.
function kelvinToRgb(k) {
  var t = k / 100, r, g, b
  if (t <= 66) {
    r = 255
    g = 99.4708025861 * Math.log(t) - 161.1195681661
    b = t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307
  } else {
    r = 329.698727446 * Math.pow(t - 60, -0.1332047592)
    g = 288.1221695283 * Math.pow(t - 60, -0.0755148492)
    b = 255
  }
  return [clamp(r, 0, 255) / 255, clamp(g, 0, 255) / 255, clamp(b, 0, 255) / 255]
}

function lerpHs(a, b, t) {
  var d = ((b[0] - a[0]) % 360 + 360) % 360
  if (d > 180) d -= 360
  return [Math.round(((a[0] + d * t) % 360 + 360) % 360), Math.round(a[1] + (b[1] - a[1]) * t)]
}

// stops: [{pos: 0-1, hs: [h, s]}]
function gradientAt(stops, n) {
  if (!stops || stops.length === 0) return []
  var s = stops.slice().sort(function(a, b) { return a.pos - b.pos })
  var out = []
  for (var i = 0; i < n; i++) {
    var x = n > 1 ? i / (n - 1) : 0
    if (x <= s[0].pos) { out.push(s[0].hs); continue }
    if (x >= s[s.length - 1].pos) { out.push(s[s.length - 1].hs); continue }
    for (var k = 0; k < s.length - 1; k++) {
      if (s[k].pos <= x && x <= s[k + 1].pos) {
        var span = s[k + 1].pos - s[k].pos
        out.push(lerpHs(s[k].hs, s[k + 1].hs, span === 0 ? 0 : (x - s[k].pos) / span))
        break
      }
    }
  }
  return out
}

function evenStops(colors) {
  var n = colors.length
  return colors.map(function(hs, i) { return { pos: n > 1 ? i / (n - 1) : 0, hs: hs } })
}

// Starting points for the gradient editor. Saturations are high on purpose:
// on an LED, anything much under 60% already reads as tinted white.
var presets = [
  { name: "Sunset",   colors: [[340, 90], [15, 95], [38, 100]] },
  { name: "Ocean",    colors: [[190, 100], [215, 95], [250, 85]] },
  { name: "Aurora",   colors: [[150, 90], [175, 95], [270, 80]] },
  { name: "Neon",     colors: [[300, 100], [260, 100], [185, 100]] },
  { name: "Forest",   colors: [[95, 85], [130, 90], [60, 80]] },
  { name: "Candy",    colors: [[330, 70], [280, 60], [200, 65]] },
  { name: "Ember",    colors: [[0, 100], [18, 100], [0, 100]] },
  { name: "Rainbow",  colors: [[0, 100], [60, 100], [120, 100], [180, 100], [240, 100], [300, 100]] }
]

// Quick picks on the colour tab.
var swatches = [
  [0, 100], [20, 100], [38, 100], [55, 100], [90, 90], [130, 90],
  [175, 95], [200, 95], [225, 90], [265, 85], [290, 90], [325, 90]
]
