"""
Brand constants for the forecaster's own identity.

WHY A SEPARATE IDENTITY FROM GOVALLECITO
The site and the forecaster want different things. A tourism brand has a
structural incentive to say "come"; a forecaster sometimes has to say the pass
is bad, the lake is at 40% and the ramps are out, or it will be smoke all week.
Wolf Creek and Purgatory cannot say "don't come" -- that is what a marketing
arm is. If the forecaster IS the tourism brand, every honest bad-news post
costs the other side, and over a season the honest posts get softer. So: one
site, two front doors.

NAME is one constant. Change it here and it changes everywhere -- card,
front matter, and the site footer.
"""

NAME = "Up the Pine Weather"
SHORT = "Up the Pine"
TAGLINE = "Vallecito · Bayfield · Durango — by elevation"
SITE = "govallecito.com/weather"
# What the honesty covenant reduces to on a card. Deliberately not a slogan.
FOOTER_NOTE = "Ranges, not point values. Sources named. Misses posted."

# Palette. Cool and legible, readable in a feed at thumbnail size, and
# deliberately NOT the alarm-red/amber of broadcast weather graphics -- the
# whole voice rule is that urgency raises precision, never volume.
INK = (17, 24, 33)
INK_SOFT = (92, 105, 120)
PAPER = (247, 249, 251)
SKY_TOP = (196, 216, 236)
SKY_BOTTOM = (232, 240, 247)
TERRAIN = (74, 92, 106)
TERRAIN_LIGHT = (108, 128, 143)
SNOW_ZONE = (222, 235, 247)
SNOW_ACCENT = (38, 92, 152)
RAIN_ACCENT = (74, 124, 118)
LINE = (204, 63, 46)          # the snow line itself: the one place colour shouts
RULE = (216, 223, 230)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = f"{FONT_DIR}/DejaVuSans-Bold.ttf"
FONT_REG = f"{FONT_DIR}/DejaVuSans.ttf"
FONT_MONO = f"{FONT_DIR}/DejaVuSansMono.ttf"
