"""
The elevation cross-section card. This is the forecaster's signature graphic.

WHY THIS SHAPE AND NOT A SNOWFALL MAP
The research says the hand-drawn snowfall map is the most-shared object in
hyperlocal weather, and it is -- for a forecaster covering a whole state. Ours
covers three towns inside one grid cell, so a map of that area would be a
nearly-blank rectangle with three dots on it. The information that actually
varies here is VERTICAL: a ~5,000 ft spread from the Animas Valley floor to the
Weminuche, with a snow line cutting across it. So the graphic is a side view,
not a top view -- terrain rising left to right, the four bands marked at their
real heights, and one red line drawn across the whole thing at the snow level.

Nobody publishes this, and it makes the product's entire argument in one image
without a word of explanation: your town and the lake are not the same weather.

LAYOUT IS FIXED. Text is shortened to fit the card; the card never grows to fit
the text. Same discipline as the existing conditions-card renderer, and for the
same reason -- a caption and an image that disagree is worse than either alone.
"""

import os

from PIL import Image, ImageDraw, ImageFont

from . import brand as BR
from . import constants as C

W, H = 1080, 1350
MARGIN = 64
CHART_TOP = 340
CHART_BOTTOM = 1080
ELEV_MIN, ELEV_MAX = 5800, 11800


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _y_for(elev):
    """Elevation -> pixel row. Clamped so a bad input can't draw off-card."""
    e = max(ELEV_MIN, min(ELEV_MAX, elev))
    frac = (e - ELEV_MIN) / (ELEV_MAX - ELEV_MIN)
    return int(CHART_BOTTOM - frac * (CHART_BOTTOM - CHART_TOP))


def _fit(draw, text, font, max_w):
    """Shorten to fit. Never let the layout stretch."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return (text.rstrip() + ell) if text else ell


def _sky(img):
    d = ImageDraw.Draw(img)
    for y in range(CHART_TOP, CHART_BOTTOM):
        f = (y - CHART_TOP) / max(1, CHART_BOTTOM - CHART_TOP)
        d.line([(0, y), (W, y)],
               fill=tuple(int(BR.SKY_TOP[i] + f * (BR.SKY_BOTTOM[i] - BR.SKY_TOP[i]))
                          for i in range(3)))


def _terrain(draw, bands):
    """A silhouette rising left to right through the real band elevations.

    Not a survey profile -- a readable schematic that puts each band at its
    true height. Interpolated with a smooth step so it reads as a mountainside
    rather than a bar chart.
    """
    xs = [MARGIN + i * ((W - 2 * MARGIN) / (len(bands) - 1)) for i in range(len(bands))]
    pts = []
    for i in range(len(bands) - 1):
        x0, x1 = xs[i], xs[i + 1]
        e0, e1 = bands[i]["elevation_ft"], bands[i + 1]["elevation_ft"]
        steps = 40
        for s in range(steps + 1):
            t = s / steps
            smooth = t * t * (3 - 2 * t)          # smoothstep
            pts.append((x0 + (x1 - x0) * t, _y_for(e0 + (e1 - e0) * smooth)))
    poly = [(0, pts[0][1])] + pts + [(W, pts[-1][1]), (W, CHART_BOTTOM), (0, CHART_BOTTOM)]
    draw.polygon(poly, fill=BR.TERRAIN)
    draw.line([(0, pts[0][1])] + pts + [(W, pts[-1][1])], fill=BR.TERRAIN_LIGHT, width=3)
    return xs


def render(data, out_path):
    """`data` comes from card_data_from_bundle(). Returns out_path.

    Required keys: stamp, bands (list of {key,label,elevation_ft,amount,type}).
    Optional: snow_line_ft, snow_line_trend, headline, sources.
    """
    img = Image.new("RGB", (W, H), BR.PAPER)
    d = ImageDraw.Draw(img)

    f_brand = _font(BR.FONT_BOLD, 46)
    f_tag = _font(BR.FONT_REG, 25)
    f_stamp = _font(BR.FONT_MONO, 25)
    f_head = _font(BR.FONT_BOLD, 40)
    f_band = _font(BR.FONT_BOLD, 31)
    f_sub = _font(BR.FONT_REG, 24)
    f_amt = _font(BR.FONT_BOLD, 35)
    f_line = _font(BR.FONT_BOLD, 28)
    f_foot = _font(BR.FONT_REG, 21)

    # --- header ---------------------------------------------------------
    d.text((MARGIN, 52), BR.NAME, font=f_brand, fill=BR.INK)
    d.text((MARGIN, 112), BR.TAGLINE, font=f_tag, fill=BR.INK_SOFT)
    stamp = data.get("stamp", "")
    d.text((W - MARGIN - d.textlength(stamp, font=f_stamp), 60), stamp,
           font=f_stamp, fill=BR.INK_SOFT)
    d.line([(MARGIN, 168), (W - MARGIN, 168)], fill=BR.RULE, width=2)

    headline = _fit(d, data.get("headline", ""), f_head, W - 2 * MARGIN)
    d.text((MARGIN, 205), headline, font=f_head, fill=BR.INK)

    # --- chart ----------------------------------------------------------
    _sky(img)
    d = ImageDraw.Draw(img)

    line_ft = data.get("snow_line_ft")
    if line_ft:
        # Everything above the line gets a cool wash. The eye reads "snow up
        # there, rain down here" before it reads a single word.
        #
        # Guarded: a snow line at or above the top of the chart (a bad freezing
        # level, or one clamped to ELEV_MAX) leaves a zero-height band, and
        # compositing a 1px wash onto a 0px crop raises ValueError. The height
        # is computed once and both images are built from it.
        y = _y_for(line_ft)
        wash_h = y - CHART_TOP
        if wash_h > 0:
            region = img.crop((0, CHART_TOP, W, CHART_TOP + wash_h)).convert("RGBA")
            wash = Image.new("RGBA", region.size, BR.SNOW_ZONE + (120,))
            img.paste(Image.alpha_composite(region, wash).convert("RGB"),
                      (0, CHART_TOP))
        d = ImageDraw.Draw(img)

    xs = _terrain(d, C.BANDS)

    # --- snow line, then labels that dodge it ------------------------------
    # Everything below is placed with real collision avoidance. An earlier
    # version anchored labels above/below the marker by parity, which put
    # Durango's text on dark terrain in dark ink (invisible) and dropped the
    # snow-line badge straight through it. Labels now always sit on a light
    # plate, always in reading order, and always move rather than overlap.
    occupied = []

    def _collides(rect):
        ax0, ay0, ax1, ay1 = rect
        for bx0, by0, bx1, by1 in occupied:
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                return True
        return False

    if line_ft:
        y = _y_for(line_ft)
        for x in range(0, W, 26):
            d.line([(x, y), (x + 15, y)], fill=BR.LINE, width=5)
        label = f"SNOW LINE  {line_ft:,} ft"
        trend = data.get("snow_line_trend")
        if trend and trend != "steady":
            label += f"  ({trend})"
        tw = d.textlength(label, font=f_line)
        # Right-anchored: the left side is where the low-elevation band labels
        # live, and they are the ones with the least room to move.
        bx1 = W - MARGIN + 12
        bx0 = bx1 - tw - 30
        by0 = y - 46
        d.rectangle([bx0, by0, bx1, by0 + 40], fill=BR.LINE)
        d.text((bx0 + 15, by0 + 6), label, font=f_line, fill=(255, 255, 255))
        occupied.append((bx0 - 10, by0 - 10, bx1 + 10, by0 + 50))

    for i, band in enumerate(C.BANDS):
        info = (data.get("bands") or {}).get(band["key"], {})
        x, y = xs[i], _y_for(band["elevation_ft"])
        amount = info.get("amount", "")
        ptype = (info.get("type") or "").lower()
        colour = BR.SNOW_ACCENT if "snow" in ptype and "either" not in ptype \
            else BR.RAIN_ACCENT if "rain" in ptype and "either" not in ptype \
            else BR.INK_SOFT

        short = _fit(d, info.get("short") or band["label"], f_band, 430)
        elev_s = f"{band['elevation_ft']:,} ft"
        block_w = max(d.textlength(short, font=f_band),
                      d.textlength(elev_s, font=f_sub),
                      d.textlength(amount, font=f_amt)) + 26
        block_h = 106 if amount else 72

        # Centre on the marker, then clamp inside the card.
        tx = min(max(MARGIN - 13, x - block_w / 2), W - MARGIN + 13 - block_w)
        ty = y - block_h - 26                      # always ABOVE the marker,
        while ty > CHART_TOP + 8 and _collides((tx, ty, tx + block_w, ty + block_h)):
            ty -= block_h + 10                     # ...climbing until it is clear
        ty = max(CHART_TOP + 8, ty)

        # A light plate so the text is legible over sky OR terrain. This is the
        # fix for dark labels landing on the dark hillside.
        # Integer geometry computed ONCE and reused for both the crop and the
        # plate -- deriving them separately from floats rounds differently and
        # alpha_composite rejects the mismatched sizes.
        ix0, iy0 = int(tx), int(ty)
        ix1, iy1 = min(W, ix0 + int(block_w)), min(H, iy0 + int(block_h))
        if ix1 > ix0 and iy1 > iy0:
            region = img.crop((ix0, iy0, ix1, iy1)).convert("RGBA")
            plate = Image.new("RGBA", region.size, BR.PAPER + (232,))
            img.paste(Image.alpha_composite(region, plate).convert("RGB"), (ix0, iy0))
        d = ImageDraw.Draw(img)

        d.text((tx + 13, ty + 6), short, font=f_band, fill=BR.INK)
        d.text((tx + 13, ty + 42), elev_s, font=f_sub, fill=BR.INK_SOFT)
        if amount:
            d.text((tx + 13, ty + 70), _fit(d, amount, f_amt, block_w - 26),
                   font=f_amt, fill=colour)

        # Leader line from the plate down to the marker, so the pairing is
        # unambiguous once a label has climbed away from its point.
        d.line([(x, ty + block_h), (x, y - 10)], fill=BR.INK_SOFT, width=2)
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=BR.PAPER, outline=BR.INK, width=4)
        occupied.append((tx - 8, ty - 8, tx + block_w + 8, ty + block_h + 8))

    # --- footer ---------------------------------------------------------
    d.rectangle([0, H - 168, W, H], fill=BR.PAPER)
    d.line([(MARGIN, H - 168), (W - MARGIN, H - 168)], fill=BR.RULE, width=2)
    d.text((MARGIN, H - 142), BR.FOOTER_NOTE, font=f_foot, fill=BR.INK_SOFT)
    src = _fit(d, "Sources: " + ", ".join(data.get("sources", [])[:4]),
               f_foot, W - 2 * MARGIN)
    d.text((MARGIN, H - 108), src, font=f_foot, fill=BR.INK_SOFT)
    d.text((MARGIN, H - 66), BR.SITE, font=_font(BR.FONT_BOLD, 25), fill=BR.INK)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


SHORT_LABELS = {
    "durango": "Durango / the Valley",
    "bayfield": "Bayfield / the Pine",
    "vallecito": "Vallecito / the Florida",
    "weminuche": "The Weminuche",
}


def card_data_from_bundle(bundle):
    """Bundle -> card data. Never invents a number the bundle does not carry."""
    sl = bundle.get("snow_line") or {}
    types = bundle.get("precip_type_by_band") or {}
    bands = {}
    for key in C.BAND_ORDER:
        b = (bundle.get("bands") or {}).get(key) or {}
        s = b.get("summary") or {}
        t = (types.get(key) or {}).get("precip_type", "")
        snow = s.get("total_snow_in")
        liquid = s.get("total_precip_in")
        if snow is not None and snow >= 0.5 and "rain" not in t:
            lo, hi = max(0, round(snow * 0.6)), round(snow * 1.5)
            amount = f'{lo}-{hi}"' if hi > lo else f'{hi}"'
        elif liquid:
            amount = f'{liquid:.2f}" liquid'
        else:
            amount = "dry"
        bands[key] = {"amount": amount, "type": t, "short": SHORT_LABELS.get(key, key)}

    alerts = bundle.get("alerts") or []
    if alerts:
        headline = alerts[0]["event"]
    elif sl.get("representative_ft"):
        headline = f"Snow line near {sl['representative_ft']:,} ft"
    else:
        headline = "No precipitation expected"

    sources = sorted({(v or {}).get("source", "").split(" ")[0]
                      for v in (bundle.get("sources") or {}).values()
                      if (v or {}).get("source")})

    return {
        "stamp": (bundle.get("generated_at") or "")[:16].replace("T", "  "),
        "headline": headline,
        "snow_line_ft": sl.get("representative_ft"),
        "snow_line_trend": sl.get("trend"),
        "bands": bands,
        "sources": [s for s in sources if s][:4],
    }
