"""
Renders the branded 1080x1080 "conditions card" image that goes out with
every post. Pure PIL (+ numpy for the smart-crop math below), no browser/
Chromium dependency -- deliberately, so this runs fast and identically every
time in GitHub Actions without needing to install or launch a browser just to
draw some text over a color.

Brand colors below are pulled directly from claude/facebook-brand-foundation.md
(the same palette already live on the Facebook Page and the website's own
CSS) -- nothing here is a new invented color.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

import icons

# ---- brand palette (see facebook-brand-foundation.md) ----------------------
PINE = (0x1D, 0x3B, 0x2F)
PINE_2 = (0x2A, 0x5A, 0x45)
LAKE = (0x2C, 0x7F, 0x95)
LAKE_2 = (0x46, 0xA5, 0xBD)
MINT = (0x9F, 0xE6, 0xD6)
SAND = (0xEA, 0xDF, 0xC9)
WHITE = (0xFF, 0xFF, 0xFF)
DANGER = (0xD9, 0x2C, 0x04)
WARN = (0xD9, 0x82, 0x0F)
OK = (0x33, 0x87, 0x5A)
INFO = (0x42, 0x79, 0xA3)

FONT_DIR = "/usr/share/fonts/truetype/liberation"
FONT_BOLD = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
FONT_REG = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")

W = H = 1080
MARGIN = 68


_FONT_CACHE = {}
_MISSING_FONT_WARNED = set()


def _font(path, size):
    key = (path, size)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        font = ImageFont.truetype(path, size)
    except OSError:
        if path not in _MISSING_FONT_WARNED:
            print(f"[render_card] font file not found or unreadable: {path}; falling back to PIL's built-in default font")
            _MISSING_FONT_WARNED.add(path)
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _vertical_gradient(w, h, top_color, bottom_color):
    """Simple top-to-bottom linear gradient as a background."""
    base = Image.new("RGB", (1, h), color=0)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = round(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = round(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = round(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        base.putpixel((0, y), (r, g, b))
    return base.resize((w, h))


def _draw_wordmark(draw, x, y, size=30):
    """'Go' + 'Vallecito' lockup, matching the site/profile-pic dual-color
    treatment: white + mint, for use on a dark background."""
    font = _font(FONT_BOLD, size)
    draw.text((x, y), "Go", font=font, fill=WHITE)
    go_w = draw.textbbox((0, 0), "Go", font=font)[2]
    draw.text((x + go_w, y), "Vallecito", font=font, fill=MINT)


def _wrap_text(draw, text, font, max_width):
    """Greedy word wrap using actual glyph measurement."""
    words = (text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        w = draw.textbbox((0, 0), candidate, font=font)[2]
        if w <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


MAX_COVER_FIT_PIXELS = 40_000_000  # sanity cap on the intermediate resize buffer

# How wide/tall (whichever axis is being scored) the downscaled thumbnail
# used for content-detection is. Kept small on purpose -- this only needs
# to find roughly WHERE the detail is, not resolve fine structure, and a
# small thumbnail keeps _smart_crop_offset fast even on a large source photo.
CONTENT_PROFILE_SIZE = 120

# **UPDATE 2026-07-26**: this whole section was rewritten after a second,
# differently-shaped version of the same class of bug David originally
# reported 2026-07-24 (bird's head cut off) showed up again in a real live
# post -- this time as "bird positioned low enough that the photo band's own
# text overlay covers it," not a test render. Root-caused directly against
# the actual photo that produced that report, down to THREE separate,
# independent problems, not the one thing the 2026-07-24 fix addressed:
#
# 1. A genuine bug unrelated to priors or weighting: PIL's
#    ImageFilter.FIND_EDGES can't filter its outermost 1px border (a 3x3
#    kernel needs neighbors past the edge) and instead just copies the
#    ORIGINAL pixel brightness there. A bright sky/background at the very
#    top or bottom row of the downscaled thumbnail therefore reads as a
#    massive fake "edge" with zero relation to real content. Confirmed
#    directly: even a perfectly flat, featureless test image scores its
#    first/last row ~60x higher than every real (correctly ~0) interior
#    row. This alone fully explains the specific bad crop reported
#    2026-07-26 -- the old window-sum search was simply chasing a
#    measurement artifact at the photo's own top edge (it picked an offset
#    of 0, i.e. "start the crop at the very top," on a photo where that
#    put the bird's eye 81px past where the text overlay begins). Fixed by
#    discarding a 1px border on all four sides of the edge map before
#    scoring anything -- see _interest_profile.
# 2. The 2026-07-24 fix's own diagnosis was half right: summing edge
#    magnitude across an entire row/column rewards WIDTH (one wide, uniform
#    high-contrast feature, e.g. that fix's own example of a feeder rim)
#    over a small, sharp, genuinely interesting one (an eye, a feather
#    edge) -- it rewards "how much total edge-y stuff is in this row," not
#    "how sharp is the sharpest small detail here." Confirmed with a
#    controlled synthetic test (a wide bright bar vs. a small high-contrast
#    cluster, positioned so only one is the "correct" choice, with zero
#    positional weighting applied to either): plain per-row summing picked
#    the bar; scoring each row/column by the MEAN of just its own top
#    TOP_K_FRAC brightest cells picked the small cluster correctly, on
#    content alone. See _interest_profile.
# 3. Even with (1) and (2) fixed, a photo can have OTHER genuinely sharp
#    detail away from the actual subject -- confirmed against the live
#    photo itself: the dry curled leaves and crossing twigs below the bird
#    measured sharper/higher-contrast than the bird's own damp, fluffed-up
#    feathers that day. No amount of edge-magnitude cleverness
#    distinguishes "sharp because it's the subject" from "sharp because
#    it's a dry leaf" -- that needs actual subject detection, still out of
#    proportion for this project (see the 2026-07-24 comment this
#    replaces). Rather than fight that fight semantically, this leans
#    harder on the same positional assumption the 2026-07-24 fix already
#    made (these specific curated wildlife/nature categories conventionally
#    frame the subject upper-to-upper-middle, habitat/perch/background
#    below) -- but as a monotonic decay that keeps discouraging content the
#    whole way down the frame, replacing the old Gaussian BUMP centered on
#    one specific peak row, which only weakly discouraged content far from
#    that peak and did nothing to stop a strong enough lower-frame signal
#    from winning outright (which is exactly what let the twigs/leaves win).
#    See VERTICAL_DECAY_SCALE below, tuned empirically against BOTH the
#    live bad-crop photo and the original 2026-07-24 good-crop photo
#    together -- confirming this isn't just re-fitting to the newest single
#    anecdote the way a re-tuned Gaussian peak/spread would be (that is
#    literally what happened last time: tuned against one bad photo, then
#    failed differently on the next one).
#
# None of this makes the crop "always right" -- it can't be without a real
# subject-detection model, which remains deliberately out of scope (see
# point 3). What changed is narrower but real: given a photo where the
# actual subject is reasonably sharp on its own (true of essentially any
# photo worth using here -- an out-of-focus subject would have been a bad
# candidate regardless), the search no longer has a measurement artifact
# to chase, no longer systematically favors width over sharpness, and is
# now decisively (not just gently) biased toward keeping the upper part of
# the frame over the lower part.
TOP_K_FRAC = 0.15   # each row/column's score = the MEAN of its own top 15%
                     # brightest edge-pixels, not the sum of all of them --
                     # see point 2 above.
SMOOTH_WINDOW = 5    # light smoothing over the profile before use -- guards
                     # against single-thumbnail-pixel noise winning the
                     # argmax, without blurring away genuinely small
                     # subjects (5 of ~120 thumbnail cells is still narrow).

# Vertical axis only -- see point 3 above for why, and HORIZONTAL_DECAY_SCALE
# below for why this doesn't apply sideways. Applied as
# exp(-position_frac / VERTICAL_DECAY_SCALE): at 0.5, content at the very
# top of the frame keeps full weight, content 50% down is already
# discounted to ~14%, and content past 70-80% down is down to low single
# digits. Empirically tested at 0.35/0.5/0.7/1.0 against both the live
# bad-crop photo and the 2026-07-24 good-crop photo: 0.35-0.7 correctly
# clear the text zone on BOTH photos; 1.0 and above reproduces the live bad
# crop (not decisive enough to overcome the twig/leaf detail). 0.5 sits in
# the middle of the confirmed-good range with margin on both sides, rather
# than at either edge of it.
VERTICAL_DECAY_SCALE = 0.5

# Horizontal cropping only happens when a source photo is wider than this
# card's very wide 1080x460 band -- rare for typical wildlife/nature
# photography (see the note this section replaces). There's no equivalent
# "stuff below here gets covered" hazard on that axis (the credit line is
# small text tucked in one bottom corner, not a wide overlay band), so it
# stays pure content-quality-driven. None disables the decay weighting
# entirely, rather than e.g. a large number -- explicit about intent
# instead of relying on "big enough to not matter."
HORIZONTAL_DECAY_SCALE = None


def _interest_profile(photo_gray, axis):
    """Returns a smoothed 1-D numpy array scoring 'how much does this
    row (axis="vertical") or column (axis="horizontal") look like the
    point of interest', computed from a small downscaled edge-detected copy
    of photo_gray.

    Trims a 1px border off the edge map before scoring -- see point 1 in
    the module-level comment above TOP_K_FRAC for why (PIL's FIND_EDGES
    leaves that border unfiltered, and it can otherwise dominate the whole
    profile with a pure measurement artifact). Scores each row/column by
    the MEAN of its own top TOP_K_FRAC brightest cells rather than a sum
    over all of them -- see point 2 in that same comment."""
    w, h = photo_gray.size
    if axis == "vertical":
        small_w = CONTENT_PROFILE_SIZE
        small_h = max(3, round(h * (CONTENT_PROFILE_SIZE / w)))
    else:
        small_h = CONTENT_PROFILE_SIZE
        small_w = max(3, round(w * (CONTENT_PROFILE_SIZE / h)))
    small = photo_gray.resize((small_w, small_h), Image.LANCZOS)
    edges = np.asarray(small.filter(ImageFilter.FIND_EDGES), dtype=np.float64)
    if axis == "horizontal":
        edges = edges.T  # score columns the same way rows are scored below
    edges = edges[1:-1, 1:-1]  # drop the unfiltered artifact border (both axes)

    n_cells, n_other = edges.shape
    if n_cells <= 0 or n_other <= 0:
        return np.zeros(max(n_cells, 1))  # degenerately tiny thumbnail --
                                           # let the caller's no-signal
                                           # fallback handle it
    k = max(1, round(n_other * TOP_K_FRAC))
    top_k = np.partition(edges, n_other - k, axis=1)[:, n_other - k:]
    profile = top_k.mean(axis=1)

    if SMOOTH_WINDOW > 1 and len(profile) >= SMOOTH_WINDOW:
        kernel = np.ones(SMOOTH_WINDOW) / SMOOTH_WINDOW
        profile = np.convolve(profile, kernel, mode="same")
    return profile


def _smart_crop_offset(photo_gray, full_len, target_len, axis):
    """Picks WHERE along `axis` (the axis with cover-fit overflow) to
    place the target_len-sized crop window, favoring the position that
    keeps the most (weighted) point-of-interest content inside it. See
    _interest_profile and the TOP_K_FRAC/VERTICAL_DECAY_SCALE comments
    above for the reasoning -- better per-row/column scoring, plus (on the
    vertical axis) an explicit, decisive positional bias tied to this
    card's own text-overlay geometry, replacing the gentler statistical
    prior from the original 2026-07-24 fix.

    Falls back to a dead-center offset if the profile has no real signal
    (a flat/near-flat image -- centering is as good a guess as any) or if
    anything else about the detection step fails. A slightly-off crop
    position is a cosmetic issue; a crash here must never take down the
    whole post (same fail-open-to-a-safe-default philosophy as the rest of
    this file's photo handling).
    """
    center_fallback = max(0, (full_len - target_len) // 2)
    if full_len <= target_len:
        return 0
    try:
        profile = _interest_profile(photo_gray, axis)
        n = len(profile)
        window = max(1, round(n * target_len / full_len))
        if window >= n:
            return center_fallback

        signal_range = float(profile.max() - profile.min()) if n else 0.0
        if signal_range < 1e-6:
            return center_fallback  # nothing to target -- center is as good as any guess

        decay_scale = VERTICAL_DECAY_SCALE if axis == "vertical" else HORIZONTAL_DECAY_SCALE
        if decay_scale:
            position_frac = np.arange(n) / n
            profile = profile * np.exp(-position_frac / decay_scale)

        prefix = np.concatenate([[0.0], np.cumsum(profile)])
        window_sums = prefix[window:] - prefix[:-window]
        best_start = int(np.argmax(window_sums))
        offset = round(best_start * full_len / n)
        return max(0, min(offset, full_len - target_len))
    except Exception as exc:
        print(f"[render_card] smart crop offset failed ({exc}); falling back to a center crop")
        return center_fallback


def _cover_fit(photo, target_w, target_h):
    """Resize + content-aware crop a photo to exactly fill target_w x
    target_h, same idea as CSS background-size: cover -- except WHERE the
    crop window lands is chosen by _smart_crop_offset() rather than always
    dead-center (see that function's docstring, and the TOP_K_FRAC /
    VERTICAL_DECAY_SCALE comments above, for why plain center-crop was
    cutting subjects' heads off and why plain content-energy alone wasn't a
    sufficient fix either).
    Falls back to a plain center crop on any failure in the smart-crop step."""
    src_w, src_h = photo.size
    if src_w <= 0 or src_h <= 0:
        raise ValueError(f"photo has invalid dimensions {src_w}x{src_h}")
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    if new_w * new_h > MAX_COVER_FIT_PIXELS:
        raise ValueError(
            f"cover-fit resize of {src_w}x{src_h} -> {new_w}x{new_h} exceeds the "
            f"{MAX_COVER_FIT_PIXELS}-pixel sanity cap (likely an extreme "
            "aspect-ratio source image) -- refusing rather than risking an OOM"
        )
    resized = photo.resize((new_w, new_h), Image.LANCZOS)

    if new_h > target_h:
        left = (new_w - target_w) // 2
        top = _smart_crop_offset(resized.convert("L"), new_h, target_h, axis="vertical")
    elif new_w > target_w:
        top = (new_h - target_h) // 2
        left = _smart_crop_offset(resized.convert("L"), new_w, target_w, axis="horizontal")
    else:
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


PHOTO_BAND_H = 460


def _draw_photo_band(img, draw, featured_image):
    """Draws the top photo band for a 'grounded' seasonal post: the photo
    itself (cover-fit), a bottom gradient wash for legibility, an eyebrow
    label, headline + fact text, and a small credit line. Returns the y
    coordinate where the band ends so the caller knows where to resume
    drawing the rest of the card."""
    photo = Image.open(featured_image["path"]).convert("RGB")
    fitted = _cover_fit(photo, W, PHOTO_BAND_H)
    img.paste(fitted, (0, 0))

    # Bottom gradient wash, pine-tinted, so white text stays legible over
    # whatever the photo looks like -- same technique proven on the cover photo.
    wash_top = PHOTO_BAND_H - 260
    for yy in range(wash_top, PHOTO_BAND_H):
        t = (yy - wash_top) / (PHOTO_BAND_H - wash_top)
        alpha = t ** 1.4
        overlay = Image.new("RGB", (W, 1), PINE)
        row = Image.blend(img.crop((0, yy, W, yy + 1)), overlay, alpha)
        img.paste(row, (0, yy))
    # re-bind draw context in case any PIL versions need it after paste
    draw = ImageDraw.Draw(img)

    eyebrow_font = _font(FONT_BOLD, 20)
    draw.text((MARGIN, PHOTO_BAND_H - 214), "SEASONAL NOTE", font=eyebrow_font, fill=MINT)

    photo_band_text_w = W - 2 * MARGIN

    headline_font = _font(FONT_BOLD, 40)
    all_headline_lines = _wrap_text(draw, featured_image.get("headline", ""), headline_font, photo_band_text_w)
    headline_lines = all_headline_lines[:2]
    if len(all_headline_lines) > 2 and headline_lines:
        # Backstop only -- generate_post_text.py already condenses the
        # headline to fit in 2 lines before it ever gets here. This just
        # makes sure an unexpectedly-long headline (a future almanac entry
        # added without going through that condensing) is visibly cut off
        # rather than silently dropped, same principle as _draw_rows below.
        last = headline_lines[-1]
        while len(last) > 1 and draw.textbbox((0, 0), last + "…", font=headline_font)[2] > photo_band_text_w:
            last = last[:-1].rstrip()
        headline_lines[-1] = last + "…"
    ty = PHOTO_BAND_H - 182
    for line in headline_lines:
        draw.text((MARGIN, ty), line, font=headline_font, fill=WHITE)
        ty += 48

    fact_font = _font(FONT_BOLD, 21)
    # A 2-line headline already eats into the band's vertical room, so cap
    # fact text a little tighter in that case -- otherwise the fact text and
    # the credit line below it can overlap (see credit_y below).
    max_fact_lines = 2 if len(headline_lines) > 1 else 3
    all_fact_lines = _wrap_text(draw, featured_image.get("fact", ""), fact_font, photo_band_text_w)
    fact_lines = all_fact_lines[:max_fact_lines]
    if len(all_fact_lines) > max_fact_lines and fact_lines:
        # Same backstop as the headline above -- generate_post_text.py
        # condenses the fact text first, so this shouldn't normally trigger.
        last = fact_lines[-1]
        while len(last) > 1 and draw.textbbox((0, 0), last + "…", font=fact_font)[2] > photo_band_text_w:
            last = last[:-1].rstrip()
        fact_lines[-1] = last + "…"
    ty += 8
    for line in fact_lines:
        draw.text((MARGIN, ty), line, font=fact_font, fill=SAND)
        ty += 28

    credit = featured_image.get("credit_text", "")
    if credit:
        credit_font = _font(FONT_REG if os.path.exists(FONT_REG) else FONT_BOLD, 16)
        credit_w = draw.textbbox((0, 0), credit, font=credit_font)[2]
        # Anchor below wherever the fact text actually ended rather than a
        # fixed offset from the band bottom -- a fixed offset overlaps the
        # fact text whenever the headline wraps to 2 lines (all 4 current
        # almanac entries sit close enough to 2 lines to risk this).
        credit_y = max(ty + 6, PHOTO_BAND_H - 30)
        draw.text((W - MARGIN - credit_w, credit_y), credit, font=credit_font, fill=SAND)

    return PHOTO_BAND_H


def _draw_rows(draw, rows, y, footer_zone_top, compact=False):
    """Draws the icon/label/value data rows starting at y, within the space
    up to footer_zone_top. Shared by both card variants.

    compact=True is used when a photo band has already eaten into the
    vertical space (the "grounded" seasonal variant) -- smaller fonts/badges
    so up to 4 rows still comfortably fit below a photo.

    Row heights are based on each row's OWN measured text -- a row whose
    value wraps to 2 lines gets more room than a 1-line row, rather than
    every row getting an equal slice regardless of content. An earlier
    version divided the space evenly and a long Fire Status line would
    overlap the row below it whenever the photo band left less room to
    work with. Measure first, then lay out, so overlap isn't possible.
    """
    if not rows:
        return

    label_font = _font(FONT_BOLD, 20 if compact else 22)
    value_font = _font(FONT_BOLD, 30 if compact else 38)
    badge_r = 38 if compact else 46
    line_h = 36 if compact else 44
    base_row_h = 92 if compact else 120
    max_row_h = 130 if compact else 168

    text_x = MARGIN + badge_r * 2 + 32
    text_max_w = W - MARGIN - text_x

    measured = []
    for row in rows:
        all_value_lines = _wrap_text(draw, row.get("value", ""), value_font, text_max_w)
        value_lines = all_value_lines[:2]
        if len(all_value_lines) > 2 and value_lines:
            # Make truncation visible rather than silently dropping content
            # -- matters most for fire-restriction text, which must never
            # look complete in the image when the caption says more.
            last = value_lines[-1]
            while len(last) > 1 and draw.textbbox((0, 0), last + "…", font=value_font)[2] > text_max_w:
                last = last[:-1].rstrip()
            value_lines[-1] = last + "…"
        extra_lines = max(0, len(value_lines) - 1)
        required_h = base_row_h + extra_lines * line_h
        measured.append((row, value_lines, required_h))

    available_h = footer_zone_top - y
    total_required = sum(m[2] for m in measured)

    if total_required <= available_h:
        slack = (available_h - total_required) / len(rows)
        row_heights = [min(m[2] + slack, max_row_h + (m[2] - base_row_h)) for m in measured]
        # re-center any leftover slack from the max_row_h cap above
        leftover = available_h - sum(row_heights)
        y += max(0, leftover / 2)
    else:
        # More content than room (rare: would need several rows to
        # simultaneously wrap to 2 lines). Scale down rather than overlap --
        # dense is an acceptable look, overlapping text is not.
        scale = available_h / total_required
        row_heights = [m[2] * scale for m in measured]

    for (row, value_lines, _), row_h in zip(measured, row_heights):
        row_cy = y + row_h / 2
        badge_cx = MARGIN + badge_r
        icons.draw_badge_circle(draw, badge_cx, row_cy, badge_r, row.get("badge", MINT))

        icon_kind = row.get("icon")
        icon_color = row.get("icon_color", WHITE)
        icon_size = badge_r * 1.55
        if icon_kind == "droplet":
            icons.draw_droplet(draw, badge_cx, row_cy, icon_size, icon_color)
        elif icon_kind == "thermo":
            icons.draw_thermometer(draw, badge_cx, row_cy, icon_size, icon_color)
        elif icon_kind == "flame":
            inner = row.get("flame_inner", (255, 224, 130))
            icons.draw_flame(draw, badge_cx, row_cy, icon_size, icon_color, inner)
        elif icon_kind == "wave":
            icons.draw_wave(draw, badge_cx, row_cy, icon_size, icon_color)
        elif icon_kind == "alert":
            icons.draw_alert(draw, badge_cx, row_cy, icon_size, icon_color)

        label_color = SAND if not row.get("muted") else PINE_2
        value_color = WHITE if not row.get("muted") else SAND
        label_text = row.get("label", "") or ""
        if draw.textbbox((0, 0), label_text, font=label_font)[2] > text_max_w:
            # Labels are single-line UI chrome, not wrappable content -- an
            # unexpectedly long one (hand-edited config, future new label)
            # should truncate rather than run off the card's right edge.
            while label_text and draw.textbbox((0, 0), label_text + "…", font=label_font)[2] > text_max_w:
                label_text = label_text[:-1].rstrip()
            label_text = (label_text + "…") if label_text else ""

        label_y = row_cy - (16 if len(value_lines) < 2 else 16 + line_h / 2)
        draw.text((text_x, label_y), label_text, font=label_font, fill=label_color)

        vy = label_y + (24 if compact else 30)
        for vline in value_lines:
            draw.text((text_x, vy), vline, font=value_font, fill=value_color)
            vy += line_h

        y += row_h


def render_card(data, output_path):
    """
    data = {
        "date_label": "WEDNESDAY, JULY 22",
        "hook_line": "Good morning, Vallecito.",
        "rows": [
            {"icon": "droplet", "label": "LAKE LEVEL", "value": "53% of full pool  ·  elev. 7,642 ft",
             "badge": MINT, "icon_color": LAKE},
            {"icon": "thermo", "label": "WEATHER", "value": "74°F now, high 81°",
             "badge": INFO, "icon_color": WHITE},
            {"icon": "flame", "label": "FIRE STATUS", "value": "Stage 2: no campfires or charcoal",
             "badge": DANGER, "icon_color": WHITE, "flame": True},
            {"icon": "wave", "label": "STREAMFLOW", "value": "data delayed",
             "badge": LAKE_2, "icon_color": WHITE, "muted": True},
        ],
        "footer_text": "govallecito.com",
    }
    """
    img = _vertical_gradient(W, H, PINE_2, PINE)
    draw = ImageDraw.Draw(img)

    featured_image = data.get("featured_image")
    used_featured_image = False
    y = None

    if featured_image:
        # Photo band carries the "headline moment" for a grounded/seasonal
        # post -- the usual big rotating hook_line is deliberately skipped
        # here so the card isn't saying two different "headlines" at once.
        #
        # Attempted on a COPY of the canvas and only committed on full
        # success -- a bad/missing photo file, the extreme-aspect-ratio OOM
        # guard, or any other failure partway through would otherwise leave
        # the real canvas half-drawn with no clean way to fall back.
        try:
            attempt_img = img.copy()
            attempt_draw = ImageDraw.Draw(attempt_img)
            _draw_photo_band(attempt_img, attempt_draw, featured_image)
            mast_y = PHOTO_BAND_H + 20
            _draw_wordmark(attempt_draw, MARGIN, mast_y, size=26)
            date_font = _font(FONT_BOLD, 22)
            date_text = data.get("date_label", "")
            date_w = attempt_draw.textbbox((0, 0), date_text, font=date_font)[2]
            attempt_draw.text((W - MARGIN - date_w, mast_y + 3), date_text, font=date_font, fill=SAND)
            divider_y = mast_y + 40
            attempt_draw.line([(MARGIN, divider_y), (W - MARGIN, divider_y)], fill=PINE_2, width=2)
            img, draw = attempt_img, attempt_draw
            y = divider_y + 26
            used_featured_image = True
        except Exception as exc:
            print(f"[render_card] featured image failed ({exc}); falling back to the no-photo layout")

    if not used_featured_image:
        # -- masthead --
        _draw_wordmark(draw, MARGIN, 56, size=32)
        date_font = _font(FONT_BOLD, 24)
        date_text = data.get("date_label", "")
        date_w = draw.textbbox((0, 0), date_text, font=date_font)[2]
        draw.text((W - MARGIN - date_w, 62), date_text, font=date_font, fill=SAND)

        divider_y = 118
        draw.line([(MARGIN, divider_y), (W - MARGIN, divider_y)], fill=PINE_2, width=2)

        # -- headline / hook line --
        headline_font = _font(FONT_BOLD, 54)
        hook_lines = _wrap_text(draw, data.get("hook_line", ""), headline_font, W - 2 * MARGIN)[:2]
        y = divider_y + 34
        for line in hook_lines:
            draw.text((MARGIN, y), line, font=headline_font, fill=WHITE)
            y += 64
        y += 20

    # -- data rows --
    rows = data.get("rows", [])
    footer_zone_top = H - 120
    _draw_rows(draw, rows, y, footer_zone_top, compact=used_featured_image)

    # -- footer --
    footer_y = H - 88
    draw.line([(MARGIN, footer_y), (W - MARGIN, footer_y)], fill=PINE_2, width=2)
    footer_font = _font(FONT_BOLD, 30)
    footer_text = data.get("footer_text", "govallecito.com")
    draw.text((MARGIN, footer_y + 24), footer_text, font=footer_font, fill=MINT)
    arrow_font = _font(FONT_BOLD, 30)
    footer_w = draw.textbbox((0, 0), footer_text, font=footer_font)[2]
    draw.text((MARGIN + footer_w + 12, footer_y + 24), "→", font=arrow_font, fill=MINT)

    img.save(output_path)
    return output_path


if __name__ == "__main__":
    # Quick local preview with the same illustrative numbers used in the
    # style guide's example posts, for eyeballing the design.
    demo = {
        "date_label": "WEDNESDAY, JULY 22",
        "hook_line": "Good morning, Vallecito.",
        "rows": [
            {"icon": "droplet", "label": "LAKE LEVEL", "value": "53% of full pool  ·  elev. 7,642 ft",
             "badge": MINT, "icon_color": LAKE},
            {"icon": "thermo", "label": "WEATHER", "value": "74°F now · high 81°, clear",
             "badge": INFO, "icon_color": WHITE},
            {"icon": "flame", "label": "FIRE STATUS", "value": "Stage 2: no campfires or charcoal",
             "badge": DANGER, "icon_color": WHITE, "flame_inner": (255, 224, 130)},
            {"icon": "wave", "label": "STREAMFLOW", "value": "data delayed — check back this afternoon",
             "badge": LAKE_2, "icon_color": WHITE, "muted": True},
        ],
        "footer_text": "govallecito.com",
    }
    render_card(demo, "/tmp/card_preview.png")
    print("wrote /tmp/card_preview.png")

    demo_featured = dict(demo)
    demo_featured["rows"] = demo["rows"][:3]  # drop streamflow, same as generate_post_text would on a grounded day
    demo_featured["featured_image"] = {
        "path": "/tmp/test_photo.jpg",
        "headline": "The hummingbirds are moving through.",
        "fact": ("Rufous hummingbirds pass through the San Juans in July and August on their "
                 "southbound migration -- one of the longest migrations relative to body size of any bird."),
        "credit_text": "Photo: Wikimedia Commons / Public domain",
    }
    if os.path.exists("/tmp/test_photo.jpg"):
        render_card(demo_featured, "/tmp/card_preview_featured.png")
        print("wrote /tmp/card_preview_featured.png")
