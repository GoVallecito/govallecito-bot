"""
Small hand-drawn brand icons for the daily conditions card.

Why this exists instead of just using the real emoji glyphs (which is what the
Facebook *caption text* uses): PIL can only render Noto Color Emoji at its one
native embedded strike size (109px) on this Linux stack, and GitHub Actions'
ubuntu-latest runner doesn't ship that font at all -- it would need an
`apt-get install fonts-noto-color-emoji` step, and Ubuntu's emoji font
packaging has shifted before. That's an extra moving part this project doesn't
need. Drawing the icons ourselves with plain shapes means zero font
dependency, zero risk of "tofu boxes" showing up in six months after some
runner image update, and we get to use the site's actual brand colors instead
of generic Unicode-emoji yellow/orange.

Every function draws centered at (cx, cy) and takes a "size" that roughly
matches the icon's bounding box.
"""

import math


def draw_droplet(draw, cx, cy, size, color):
    """Water droplet: a circle with a pinched point on top. Used for lake level."""
    r = size * 0.34
    circle_cy = cy + size * 0.12
    draw.ellipse(
        [cx - r, circle_cy - r, cx + r, circle_cy + r],
        fill=color,
    )
    apex = (cx, cy - size * 0.5)
    left = (cx - r * 0.92, circle_cy - r * 0.05)
    right = (cx + r * 0.92, circle_cy - r * 0.05)
    draw.polygon([apex, left, right], fill=color)


def draw_thermometer(draw, cx, cy, size, color):
    """Simple capsule thermometer. Used for weather/temperature."""
    stem_w = size * 0.22
    bulb_r = size * 0.26
    stem_top = cy - size * 0.5
    stem_bottom = cy + size * 0.18

    draw.rounded_rectangle(
        [cx - stem_w / 2, stem_top, cx + stem_w / 2, stem_bottom],
        radius=stem_w / 2,
        fill=color,
    )
    draw.ellipse(
        [cx - bulb_r, cy + size * 0.5 - bulb_r * 2, cx + bulb_r, cy + size * 0.5],
        fill=color,
    )


def draw_flame(draw, cx, cy, size, outer_color, inner_color=None):
    """Two-tone flame built from the same teardrop shape as the droplet,
    just proportioned wider and (optionally) with a brighter inner tongue.
    Used for fire status."""
    r = size * 0.36
    circle_cy = cy + size * 0.16
    draw.ellipse(
        [cx - r, circle_cy - r, cx + r, circle_cy + r],
        fill=outer_color,
    )
    apex = (cx, cy - size * 0.52)
    left = (cx - r * 0.95, circle_cy - r * 0.1)
    right = (cx + r * 0.95, circle_cy - r * 0.1)
    draw.polygon([apex, left, right], fill=outer_color)

    if inner_color:
        r2 = r * 0.55
        circle_cy2 = cy + size * 0.24
        draw.ellipse(
            [cx - r2, circle_cy2 - r2, cx + r2, circle_cy2 + r2],
            fill=inner_color,
        )
        apex2 = (cx, cy - size * 0.12)
        left2 = (cx - r2 * 0.95, circle_cy2 - r2 * 0.1)
        right2 = (cx + r2 * 0.95, circle_cy2 - r2 * 0.1)
        draw.polygon([apex2, left2, right2], fill=inner_color)


def draw_wave(draw, cx, cy, size, color, num_waves=2):
    """Stacked sine-wave lines. Used for streamflow."""
    width = size * 0.9
    amp = size * 0.09
    line_w = max(3, int(size * 0.09))
    spacing = size * 0.28
    start_y = cy - (spacing * (num_waves - 1)) / 2

    for i in range(num_waves):
        y0 = start_y + i * spacing
        points = []
        steps = 24
        for s in range(steps + 1):
            t = s / steps
            x = cx - width / 2 + t * width
            y = y0 + amp * math.sin(t * 2 * math.pi)
            points.append((x, y))
        draw.line(points, fill=color, width=line_w, joint="curve")
        # round the line caps so it doesn't look chopped off at the ends
        cap_r = line_w / 2
        for (x, y) in (points[0], points[-1]):
            draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r], fill=color)


def draw_badge_circle(draw, cx, cy, r, fill):
    """Background badge circle that icons sit inside of."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def draw_alert(draw, cx, cy, size, color, mark_color=(0x1D, 0x3B, 0x2F)):
    """Warning triangle with an exclamation mark. Used for emergency alert
    rows (flood/fire/evacuation/disaster) -- the one new icon this project
    needed for the emergency-alert feature, added the same way every other
    icon here is built (plain PIL primitives, no font/emoji dependency).

    mark_color defaults to PINE (the brand's dark green, hardcoded as a
    literal here rather than imported -- render_card.py already imports
    THIS module, so importing back would be circular) instead of requiring
    every caller to pass a matching badge color: a dark mark on the
    triangle's own fill stays legible regardless of which badge color
    (DANGER, WARN, ...) the row happens to use."""
    r = size * 0.52
    top = (cx, cy - r)
    bottom_left = (cx - r * 0.95, cy + r * 0.72)
    bottom_right = (cx + r * 0.95, cy + r * 0.72)
    draw.polygon([top, bottom_left, bottom_right], fill=color)

    dash_w = size * 0.11
    dash_top = cy - r * 0.42
    dash_bottom = cy + r * 0.12
    draw.rounded_rectangle(
        [cx - dash_w / 2, dash_top, cx + dash_w / 2, dash_bottom],
        radius=dash_w / 2,
        fill=mark_color,
    )
    dot_r = dash_w * 0.62
    dot_cy = cy + r * 0.38
    draw.ellipse([cx - dot_r, dot_cy - dot_r, cx + dot_r, dot_cy + dot_r], fill=mark_color)
