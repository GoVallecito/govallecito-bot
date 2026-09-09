"""
Strip the tells that mark text as machine-written.

The em dash is the big one. A model reaches for it constantly, and a hyperlocal
weather page that uses one in every post reads as generated even when the
substance is sound. The prompt asks for none; this guarantees it, because a
prompt rule is a request and this is a fact.

Handled as a transform rather than a block on purpose. Blocking would hold
every draft over punctuation while the actual content was fine, and during the
review period that noise would train someone to skim the gate.
"""

import re

# Ranges must become hyphens, not commas. "8-14 inches" is the voice;
# "8, 14 inches" is nonsense, and this is a forecast full of ranges.
_RANGE = re.compile(r"(\d)\s*[—–]\s*(\d)")
# A dash between a time and a time, same reasoning: 2pm-5pm.
_TIME_RANGE = re.compile(r"(\d\s*(?:am|pm))\s*[—–]\s*(\d)", re.IGNORECASE)
_DASH = re.compile(r"\s*[—–]\s*")
# The double hyphen, which the model started producing once it could no longer
# produce an em dash. The 2026-09-08 draft: "All the models agree on this one --
# Euro, GFS, ICON and GEM". It learned it from the data brief, which used `--`
# throughout its own annotations, and a model imitates the punctuation of its
# context. The brief was cleaned; this is the guarantee.
#
# Range-safe like the em dash rules: "4--8" becomes "4-8", not "4, 8".
_DOUBLE_TIME_RANGE = re.compile(r"(\d\s*(?:am|pm))\s*--\s*(\d)", re.IGNORECASE)
_DOUBLE_RANGE = re.compile(r"(\d)\s*--\s*(\d)")
_DOUBLE = re.compile(r"\s+--+\s+")
_DOUBLE_TIGHT = re.compile(r"(?<=[A-Za-z0-9])--+(?=[A-Za-z0-9])")
_TIDY = [
    (re.compile(r",\s*,"), ","),
    (re.compile(r",\s*([.!?])"), r"\1"),
    (re.compile(r"\s+,"), ","),
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r"^\s*,\s*", re.MULTILINE), ""),
]


def strip_dashes(text):
    """Em and en dashes out, without mangling ranges."""
    if not text:
        return text
    text = _TIME_RANGE.sub(r"\1-\2", text)
    text = _RANGE.sub(r"\1-\2", text)
    text = _DOUBLE_TIME_RANGE.sub(r"\1-\2", text)
    text = _DOUBLE_RANGE.sub(r"\1-\2", text)
    text = _DOUBLE.sub(", ", text)
    text = _DOUBLE_TIGHT.sub(", ", text)
    # Everything else becomes a comma, which is what the dash was standing in
    # for in this voice almost every time: an aside or an apposition.
    text = _DASH.sub(", ", text)
    for pat, rep in _TIDY:
        text = pat.sub(rep, text)
    return text


# Other small giveaways worth removing while we are here.
_REPLACEMENTS = [
    (re.compile(r"’"), "'"),      # curly apostrophe
    (re.compile(r"[“”]"), '"'),
    (re.compile(r"…"), "..."),    # ellipsis character
    (re.compile(r" "), " "),      # non-breaking space
]


def clean(text):
    """Full pass. Idempotent, so running it twice is harmless."""
    text = strip_dashes(text)
    for pat, rep in _REPLACEMENTS:
        text = pat.sub(rep, text)
    return text.strip()


def has_tells(text):
    """What survived, for the guardrail to complain about."""
    found = []
    if re.search(r"[—–]", text or ""):
        found.append("em or en dash")
    if re.search(r"(?<!\S)--+(?!\S)|(?<=[A-Za-z])--+(?=[A-Za-z])", text or ""):
        found.append("double hyphen standing in for a dash")
    if re.search(r"[‘’“”…]", text or ""):
        found.append("smart quotes or ellipsis character")
    return found
