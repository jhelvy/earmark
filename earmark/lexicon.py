"""Data tables used by :mod:`earmark.clean`.

Everything here is data, not logic. Adding a new abbreviation or unit should
never require touching ``clean.py``.
"""

from __future__ import annotations

# Abbreviations whose trailing period confuses both listeners and sentence
# splitters. Expanding these before sentence splitting is what lets us get away
# without a heavyweight sentence tokenizer.
#
# Personal titles (Dr., Prof., Mr., St.) are deliberately absent: espeak-ng
# pronounces them correctly, and expanding them gains nothing.
ABBREVIATIONS: dict[str, str] = {
    "e.g.": "for example",
    "i.e.": "that is",
    "et al.": "and others",
    "etc.": "and so on",
    "cf.": "compare",
    "viz.": "namely",
    "vs.": "versus",
    "approx.": "approximately",
    "ca.": "about",
    "w.r.t.": "with respect to",
    "w/": "with",
    "w/o": "without",
    "Fig.": "Figure",
    "Figs.": "Figures",
    "Eq.": "Equation",
    "Eqs.": "Equations",
    "Tab.": "Table",
    "Sec.": "Section",
    "Secs.": "Sections",
    "Ref.": "Reference",
    "Refs.": "References",
    "Ch.": "Chapter",
    "p.": "page",
    "pp.": "pages",
    "No.": "Number",
    "vol.": "volume",
}

# Units expanded when they stand alone as a token or follow a number.
# Weighted toward energy and transportation, since that is what gets read here.
UNITS: dict[str, str] = {
    "%": "percent",
    "°C": "degrees Celsius",
    "°F": "degrees Fahrenheit",
    "km": "kilometers",
    "km/h": "kilometers per hour",
    "kg": "kilograms",
    "kW": "kilowatts",
    "kWh": "kilowatt hours",
    "MW": "megawatts",
    "MWh": "megawatt hours",
    "GW": "gigawatts",
    "TWh": "terawatt hours",
    "mpg": "miles per gallon",
    "mph": "miles per hour",
    "CO2": "C O 2",
    "GHG": "greenhouse gas",
    "EV": "E V",
    "EVs": "E Vs",
    "BEV": "battery electric vehicle",
    "BEVs": "battery electric vehicles",
    "PHEV": "plug-in hybrid",
    "PHEVs": "plug-in hybrids",
    "ICE": "internal combustion engine",
    "USD": "U S dollars",
}

# Headings that mark the start of matter nobody wants narrated. Matched
# case-insensitively against the heading text, anchored at the start.
REFERENCE_HEADINGS: tuple[str, ...] = (
    "references",
    "reference list",
    "bibliography",
    "works cited",
    "literature cited",
)

# Magnitude suffixes in money expressions: $1.2M -> "1.2 million dollars".
MONEY_SUFFIXES: dict[str, str] = {
    "K": "thousand",
    "M": "million",
    "B": "billion",
    "T": "trillion",
}
