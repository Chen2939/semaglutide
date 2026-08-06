"""Shared display conventions for the manuscript figures.

Three things live here because two or more figure scripts need them and a second
copy would be free to drift:

  * ``COUNTRY_DISPLAY_NAMES`` -- long FAOSTAT names shortened for axis labels.
  * ``FOOD_GROUP_COLORS`` -- one base colour per ``final_food_group``.
  * ``PT`` and the page constants -- point sizes and the print width the figures
    are built at.

**The country mapping is display-only.** It is applied at render time, to a list
of label strings on their way to ``set_yticklabels``, and nowhere else. No join
key, ISO code, filter, groupby or lookup may reference a shortened form -- every
one of those keys off ``ISO`` or off the unmodified ``Country`` column. If
shortening a name ever changes a computed value, the mapping has been wired into
a data path and that is a defect, not a display choice.

Figures are built at final print dimensions with real point sizes, NOT built
large and downscaled. A figure drawn at 483 mm and placed at 183 mm takes every
label down by a factor of 0.38, which puts 7.5 pt type under 3 pt on the page.
For the same reason the figure scripts do not save with
``bbox_inches="tight"``: that recomputes the bounding box at save time, so the
PNG stops being the size the figure was designed at. Margins are set explicitly
on the GridSpec instead.
"""

from __future__ import annotations

import colorsys

import matplotlib.colors as mcolors

# ── Page geometry ─────────────────────────────────────────────────────

MM_PER_IN = 25.4
DOUBLE_COLUMN_MM = 183.0          # Nature Food double-column width
DOUBLE_COLUMN_IN = DOUBLE_COLUMN_MM / MM_PER_IN     # 7.2047 in
MAX_HEIGHT_MM = 230.0             # beyond this a caption will not fit the page
DPI = 400


def mm(inches: float) -> float:
    """Inches -> millimetres, for reporting figure dimensions."""
    return inches * MM_PER_IN


# ── Point sizes ───────────────────────────────────────────────────────
#
# Floor is 5 pt for any text on the page; tick and country labels are held at
# 6 pt or above. These are real point sizes at the final print width, so what is
# written here is what a reader measures on paper.

PT = {
    "suptitle": 9.0,
    "panel_title": 7.5,
    "row_label": 7.0,
    "axis_label": 6.5,
    "tick": 6.0,
    "country": 6.0,
    "value": 5.5,
    "value_small": 5.0,
    "legend": 5.5,
    "annotation": 5.5,
    "note": 5.5,
}


# ── Country display names ─────────────────────────────────────────────
#
# Keys are the exact FAOSTAT `Country` strings the pipeline emits. Values are
# what a reader sees on an axis. Every entry is here because the long form
# crowds its axis at 183 mm, and the saving is given so the choice is auditable.
#
#   52 -> 2    United Kingdom of Great Britain and Northern Ireland
#   28 -> 11   Netherlands (Kingdom of the)
#   25 -> 6    China, Taiwan Province of        (never plotted -- no price index)
#   24 -> 3    United States of America
#   21 -> 16   Saint Kitts and Nevis
#   20 -> 3    United Arab Emirates
#   19 -> 17   Trinidad and Tobago
#   19 -> 17   Antigua and Barbuda
#   17 -> 11   Republic of Korea
#
# The longest remaining label in any plotted set is "South Korea" at 11
# characters, which is what sets the left margin.
COUNTRY_DISPLAY_NAMES = {
    "United States of America": "USA",
    "United Kingdom of Great Britain and Northern Ireland": "UK",
    "Netherlands (Kingdom of the)": "Netherlands",
    "United Arab Emirates": "UAE",
    "Republic of Korea": "South Korea",
    "China, Taiwan Province of": "Taiwan",
    "Saint Kitts and Nevis": "St Kitts & Nevis",
    "Trinidad and Tobago": "Trinidad & Tobago",
    "Antigua and Barbuda": "Antigua & Barbuda",
}


def display_country(name: str) -> str:
    """One label. Unmapped names pass through unchanged."""
    return COUNTRY_DISPLAY_NAMES.get(name, name)


def display_countries(names) -> list[str]:
    """A list of labels, for handing straight to ``set_yticklabels``."""
    return [display_country(n) for n in names]


# ── Food-group colours ────────────────────────────────────────────────
#
# One base colour per group. The dashboard's stacked breakdown uses these
# directly; the rebound figure derives a light/mid/dark triple from each so its
# three columns are distinguishable within a row while every row stays keyed to
# its group.

FOOD_GROUP_COLORS = {
    "Meat": "#c1272d",
    "Dairy": "#f5a623",
    "Cereals": "#d4a74a",
    "Fish": "#4a90d9",
    "Eggs": "#7ecdc1",
    "Fats and oils": "#9b7ab8",
    "Fruit and vegetables": "#5cb85c",
    "Sweets, confectionery, and sweetened beverages": "#e07b91",
    "Other": "#8c8c8c",
}

FOOD_GROUP_FALLBACK = "#8c8c8c"

# Display-only, on exactly the same terms as COUNTRY_DISPLAY_NAMES: applied to a
# label string on its way to the page and to nothing else. Every groupby, filter
# and reindex keys off the unmodified `final_food_group` value.
#
# The rebound figure draws these rotated 90 degrees in a row 17 mm tall, so the
# label's length is a vertical dimension. "Sweets, confectionery, and sweetened
# beverages" at 7 pt is 57 mm long and ran through three neighbouring rows.
# Wrapping to two short lines turns that length into width, where there is room.
FOOD_GROUP_DISPLAY_NAMES = {
    "Fats and oils": "Fats &\noils",
    "Fruit and vegetables": "Fruit &\nveg",
    "Sweets, confectionery, and sweetened beverages": "Sweets &\nbevs",
}


def display_food_group(group: str) -> str:
    """One row label. Unmapped groups pass through unchanged."""
    return FOOD_GROUP_DISPLAY_NAMES.get(group, group)


def food_group_shades(group: str) -> list[str]:
    """[light, mid, dark] for one food group; mid is the base colour exactly.

    The lightness factors reproduce the hand-picked triples the rebound figure
    used for Meat, Dairy and Cereals to within a couple of hex points, which is
    why they are 1.42 and 0.70 rather than round numbers -- the figure keeps the
    look it had when it covered three groups, and the other six fall in line
    with it instead of being picked by hand.
    """
    base = FOOD_GROUP_COLORS.get(group, FOOD_GROUP_FALLBACK)
    r, g, b = mcolors.to_rgb(base)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    light = colorsys.hls_to_rgb(h, min(0.90, l * 1.42), s)
    dark = colorsys.hls_to_rgb(h, l * 0.70, s)
    return [mcolors.to_hex(light), base, mcolors.to_hex(dark)]
