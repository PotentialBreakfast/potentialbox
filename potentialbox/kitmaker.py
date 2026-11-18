"""Kit Maker: build a 16-pad kit from every one-shot PotentialBox knows about, PotentialKits-style.

Pads keep PotentialBox's standard layout (so BeatStep patterns and the Beats tab carry over):
 1 Kick  2 Kick 2  3 Snare  4 Clap  5 Closed hat  6 Open hat  7-9 Toms  10 Rim  11 Cowbell  12 Clave
 13 Shaker  14 Cymbal  15 FX  16 Conga
A style says what each pad draws from, how it is tuned and how long it rings, and which machines or packs it
leans towards (by words in their folder names: "808", "SP-1200", "Jazz" ...).
"""
import math
import random

import numpy as np

from potentialbox.samples import TYPES

PAD_ROLE = ["Kick", "Kick 2", "Snare", "Clap", "Closed Hat", "Open Hat", "Low Tom", "Mid Tom", "High Tom", "Rim",
            "Cowbell", "Clave", "Shaker", "Cymbal", "FX", "Conga"]
BASE = ["Kick", "Kick", "Snare", "Clap", "Closed Hat", "Open Hat", "Tom", "Tom", "Tom", "Rim",
        "Cowbell|Perc", "Clave|Perc", "Shaker|Perc", "Cymbal", "FX|Vox|Stab", "Conga|Perc"]
FALLBACK = {"808": ["Kick"], "Kick": ["808"], "Snare": ["Clap", "Rim"], "Clap": ["Snare"],
            "Rim": ["Clave", "Perc", "Snare"], "Closed Hat": ["Open Hat", "Shaker", "Perc"],
            "Open Hat": ["Closed Hat", "Cymbal"], "Tom": ["Conga", "Perc", "Kick"], "Conga": ["Perc", "Tom"],
            "Shaker": ["Perc", "Closed Hat"], "Cowbell": ["Perc", "Clave"], "Clave": ["Perc", "Rim"],
            "Perc": ["Conga", "Shaker", "Clave", "Rim", "Cowbell"], "Cymbal": ["Open Hat"],
            "FX": ["Vox", "Stab", "Perc", "Other"], "Vox": ["FX", "Stab"], "Stab": ["FX", "Vox"],
            "Other": ["FX", "Perc"]}
WILD_POOL = ["Perc", "Conga", "Clave", "Cowbell", "Shaker", "Rim", "FX", "Vox", "Stab", "Tom", "Clap", "Snare",
             "Closed Hat", "Cymbal", "808", "Other"]
TOM_SPREAD = (-4, 0, 4)

# Each style: name, desc, kw (words in the sample's path to lean towards), tune / decay (whole-kit ranges) and
# pads {pad: (types or None, tune range or None, decay range or None)}.
STYLES = [
    {"name": "CLASSIC", "desc": "Straight drum kit", "kw": [], "pads": {}},
    {"name": "BOOM BAP", "desc": "SP-1200, MPC grit", "tune": (-1, 0),
     "kw": ["sp-1200", "sp1200", "sp 1200", "sp-12", "sp12", "mpc60", "mpc 60", "mpc-60", "mpc3000", "s950", "s900",
            "e-mu", "emu ", "boom", "dusty", "vinyl", "hip hop", "hiphop", "hip-hop", "funk"],
     "pads": {0: (None, (-3, 0), (0.7, 1.0)), 2: (None, (-2, 1), (0.6, 1.0)), 4: (None, None, (0.35, 0.7)),
              14: ("Vox|Stab|FX", None, None), 10: ("Perc|Cowbell", None, None)}},
    {"name": "LO-FI", "desc": "Tuned down, dusty", "tune": (-5, -1), "decay": (0.45, 0.85),
     "kw": ["lofi", "lo-fi", "lo fi", "dusty", "vinyl", "tape", "cassette", "vintage", "sp-1200", "sp1200", "sk-1",
            "casio", "rhythm", "ace tone", "maestro", "jazz"],
     "pads": {14: ("Vox|Stab|FX", (-7, -2), None), 13: (None, (-4, -1), (0.4, 0.7))}},
    {"name": "TRAP", "desc": "808s, crisp hats", "kw": ["808", "trap", "drill", "atl"],
     "pads": {1: ("808", (0, 0), (1.0, 1.0)), 4: (None, (0, 2), (0.25, 0.5)), 5: (None, None, (0.4, 0.7)),
              3: ("Clap|Snare", None, None), 6: ("Tom|808", None, None), 14: ("Vox|FX", None, None),
              11: ("Perc|Clave", None, None)}},
    {"name": "HOUSE", "desc": "909, 707, shakers", "kw": ["909", "707", "727", "house", "garage", "disco"],
     "pads": {4: (None, None, (0.5, 0.9)), 12: ("Shaker", None, None), 15: ("Conga", None, None),
              10: ("Cowbell|Perc", None, None)}},
    {"name": "TECHNO", "desc": "909, 606, tight", "decay": (0.55, 1.0),
     "kw": ["909", "606", "techno", "industrial", "rx5", "tr-8", "minimal", "tr8"],
     "pads": {0: (None, (-2, 0), (0.6, 1.0)), 4: (None, None, (0.3, 0.6)), 14: ("FX|Perc", None, None),
              10: ("Perc|Rim", None, None)}},
    {"name": "JUNGLE", "desc": "Breaks, high snares", "kw": ["break", "amen", "jungle", "dnb", "funk", "acoustic"],
     "pads": {2: (None, (1, 4), None), 3: ("Snare|Clap", (0, 3), None), 0: (None, (0, 2), (0.5, 0.9)),
              4: (None, (0, 2), (0.4, 0.8)), 1: ("808|Kick", None, None)}},
    {"name": "ELECTRO", "desc": "808, DMX, Linn, zaps",
     "kw": ["808", "dmx", "drumulator", "linn", "lm-1", "lm1", "cr-78", "cr78", "electro", "drumtraks", "sds",
            "simmons", "kraft"],
     "pads": {14: ("FX", None, None), 10: ("Cowbell", None, None), 11: ("Clave", None, None)}},
    {"name": "DUSTY JAZZ", "desc": "Brushes, rides", "tune": (-1, 0),
     "kw": ["jazz", "brush", "acoustic", "live", "ludwig", "gretsch", "vintage", "kit", "soul", "funk"],
     "pads": {13: ("Cymbal", None, None), 3: ("Rim|Snare", None, None), 9: ("Rim", None, None),
              14: ("Perc|Shaker", None, None), 4: (None, None, (0.5, 1.0))}},
    {"name": "PERCUSSION", "desc": "Congas, shakers", "kw": ["latin", "conga", "bongo", "afro", "world", "tabla"],
     "pads": {6: ("Conga|Perc", None, None), 7: ("Conga|Perc", None, None), 8: ("Conga|Perc", None, None),
              9: ("Clave|Rim", None, None), 13: ("Shaker|Perc", None, None), 14: ("Perc|Conga", None, None),
              3: ("Clap|Perc", None, None)}},
    {"name": "DUB", "desc": "Rims, toms, big FX", "kw": ["reggae", "dub", "dancehall", "roots", "steppers", "riddim"],
     "pads": {9: ("Rim", None, None), 2: ("Snare|Rim", None, None), 14: ("FX|Vox", None, None),
              13: (None, None, (0.6, 1.0))}},
    {"name": "WEIRD", "desc": "Anything goes", "tune": (-6, 6), "decay": (0.35, 1.0), "kw": [], "wild": 0.6,
     "pads": {}},
]
STYLE_NAMES = [s["name"] for s in STYLES]

# Beats tab genre -> style (GENRE KIT: MY SAMPLES)
GENRE_STYLE = {"Techno": "TECHNO", "House": "HOUSE", "Deep House": "HOUSE", "Minimal": "TECHNO", "UK Garage": "HOUSE",
               "Drum & Bass": "JUNGLE", "Jungle": "JUNGLE", "Dubstep": "DUB", "Grime": "TRAP", "UK Drill": "TRAP",
               "Trap": "TRAP", "Hip Hop": "BOOM BAP", "Boom Bap": "BOOM BAP", "Lo-fi": "LO-FI",
               "Reggae One Drop": "DUB", "Steppers": "DUB", "Dancehall": "DUB", "Reggaeton": "TRAP",
               "Afrobeats": "PERCUSSION", "Breakbeat": "JUNGLE", "Electro": "ELECTRO", "Disco": "HOUSE",
               "Funk": "DUSTY JAZZ", "Footwork": "TRAP"}

SCOPES = ["all", "machines", "folders"]
SCOPE_LABEL = {"all": "EVERYTHING", "machines": "DRUM MACHINES", "folders": "MY FOLDERS"}


def style_of(name):
    return next((s for s in STYLES if s["name"] == name), STYLES[0])


def _pad_spec(style, pad):
    types, tune, decay = style.get("pads", {}).get(pad, (None, None, None))
    return (types or BASE[pad]).split("|"), tune or style.get("tune", (0, 0)), decay or style.get("decay", (1.0, 1.0))


def _type_order(types, rng):
    first = types[0] if rng.random() < 0.65 or len(types) == 1 else rng.choice(types[1:])
    order = [first] + [t for t in types if t != first]
    for t in list(order):
        order += [f for f in FALLBACK.get(t, []) if f not in order]
    return order


def pick(index, types, rng, scope="all", kw=(), prefer_src=None, avoid=()):
    """One sample entry for a pad: the first type (with fallbacks) that has samples, leaning towards prefer_src
    or the style's words."""
    avoid = set(avoid)
    for t in _type_order(list(types), rng):
        cands = [e for e in index.of_type(t, scope) if e.path not in avoid]
        if not cands:
            continue
        pool = cands
        if prefer_src:
            same = [e for e in cands if e.src == prefer_src]
            if same and rng.random() < 0.9:
                pool = same
        if pool is cands and kw:
            m = [e for e in cands if any(k in e.path.lower() for k in kw)]
            if m and rng.random() < 0.75:
                pool = m
        return rng.choice(pool)
    return None


def _range(r, rng, integer=False):
    lo, hi = r
    if integer:
        return rng.randint(int(lo), int(hi))
    return round(rng.uniform(lo, hi), 3) if hi > lo else float(lo)


def _one_source(index, scope, rng, kw):
    """A machine or pack that has a kick, a snare and a hat, leaning towards the style's words."""
    def srcs(t):
        return {e.src for e in index.of_type(t, scope)}
    ok = srcs("Kick") & srcs("Snare") & (srcs("Closed Hat") | srcs("Open Hat"))
    if not ok:
        return None
    ok = sorted(ok)
    if kw:
        m = [s for s in ok if any(k in s.lower() for k in kw)]
        if m and rng.random() < 0.8:
            return rng.choice(m)
    return rng.choice(ok)


def pad_entry(e, tune=0, decay=1.0):
    return {"file": e.path, "label": e.label[:24], "type": e.type, "src": e.src, "tune": tune, "decay": decay}


def make_kit(index, style_name, locked=(), rng=None, scope="all", one_source=False, wild=0.0, tune_jitter=0,
             decay_jitter=0.0):
    """A new kit: 16 pad dicts (None for locked pads, which the caller keeps). Returns (pads, source used or None)."""
    rng = rng or random.Random()
    style = style_of(style_name)
    kw = [k.lower() for k in style.get("kw", [])]
    wild = max(wild, style.get("wild", 0.0))
    src = _one_source(index, scope, rng, kw) if one_source else None
    used = set()
    out = [None] * 16
    # toms: three from one source with low / mid / high marked, else one tom tuned three ways
    tom_pads = [p for p in (6, 7, 8) if p not in locked and _pad_spec(style, p)[0][0] == "Tom"]
    if len(tom_pads) == 3 and rng.random() >= wild:
        tset = _tom_set(index, scope, rng, kw, src)
        if tset:
            for p, (e, off) in zip(tom_pads, tset):
                _, tr, dr = _pad_spec(style, p)
                out[p] = pad_entry(e, _clip_tune(_range(tr, rng, True) + off + _jit(tune_jitter, rng)),
                                   _clip_dec(_range(dr, rng) * (1 - rng.uniform(0, decay_jitter))))
                used.add(e.path)
    for p in range(16):
        if p in locked or out[p] is not None:
            continue
        types, tr, dr = _pad_spec(style, p)
        tune_r = tr
        if wild and p not in (0, 2) and rng.random() < wild:
            types = [rng.choice(WILD_POOL)]
            tune_r = (-7, 7)
        e = pick(index, types, rng, scope, kw, src, used)
        if e is None:
            continue
        used.add(e.path)
        out[p] = pad_entry(e, _clip_tune(_range(tune_r, rng, True) + _jit(tune_jitter, rng)),
                           _clip_dec(_range(dr, rng) * (1 - rng.uniform(0, decay_jitter))))
    return out, src


def _jit(n, rng):
    return rng.randint(-n, n) if n else 0


def _clip_tune(t):
    return int(max(-24, min(24, t)))


def _clip_dec(d):
    return round(max(0.05, min(1.0, d)), 3)


def _tom_set(index, scope, rng, kw, src):
    toms = index.of_type("Tom", scope)
    if not toms:
        return None
    by_src = {}
    for e in toms:
        if e.lvl is not None:
            by_src.setdefault(e.src, {}).setdefault(e.lvl, []).append(e)
    full = [s for s, d in by_src.items() if len(d) == 3]
    if src in full and rng.random() < 0.9:
        s = src
    elif full and rng.random() < 0.8:
        m = [s for s in full if kw and any(k in s.lower() for k in kw)]
        s = rng.choice(m or full)
    else:
        s = None
    if s:
        return [(rng.choice(by_src[s][lvl]), 0) for lvl in (0, 1, 2)]
    pool = [e for e in toms if src and e.src == src] or toms
    if kw:
        m = [e for e in pool if any(k in e.path.lower() for k in kw)]
        pool = m if m and rng.random() < 0.75 else pool
    e = rng.choice(pool)
    return [(e, off) for off in TOM_SPREAD]


def roll_mild(index, current, locked=(), rng=None, scope="all", count=4):
    """Up to `count` unlocked pads get another sample of the same type (their tune and length stay)."""
    rng = rng or random.Random()
    free = [p for p in range(16) if p not in locked]
    rng.shuffle(free)
    out = [None] * 16
    used = {c.get("file") for c in current if c}
    for p in free[:max(1, rng.randint(max(1, count - 2), count))]:
        cur = current[p] or {}
        t = cur.get("type") or _pad_spec(STYLES[0], p)[0][0]
        e = pick(index, [t], rng, scope, (), None, used | {cur.get("file")})
        if e:
            used.add(e.path)
            out[p] = pad_entry(e, cur.get("tune", 0), cur.get("decay", 1.0))
    return out


def reroll_pad(index, pad, type_, current=None, rng=None, scope="all", kit=()):
    """A new sound of one type for one pad: not one already on another pad if there's a choice."""
    rng = rng or random.Random()
    cur = current or {}
    others = {c.get("file") for c in kit if c} | {cur.get("file")}
    e = pick(index, [type_], rng, scope, (), None, others) or pick(index, [type_], rng, scope, (), None,
                                                                   {cur.get("file")})
    if e is None:
        return None
    keep = cur.get("type") == type_
    return pad_entry(e, cur.get("tune", 0) if keep else 0, cur.get("decay", 1.0) if keep else 1.0)


# ---------------------------------------------------------------- levels
TYPE_TRIM_DB = {"Kick": 0.0, "808": 0.0, "Snare": -1.0, "Clap": -2.0, "Rim": -5.0, "Closed Hat": -7.0, "Open Hat": -7.0,
                "Tom": -2.0, "Conga": -4.0, "Shaker": -8.0, "Cowbell": -6.0, "Clave": -6.0, "Perc": -5.0,
                "Cymbal": -9.0, "FX": -6.0, "Vox": -4.0, "Stab": -5.0, "Other": -5.0}


def loudness_db(x, sr):
    """Short-term loudness: the loudest 30 ms RMS in the first second."""
    x = np.asarray(x[: sr], dtype=np.float64)
    if len(x) < 8:
        return -90.0
    w = max(8, int(0.03 * sr))
    if len(x) <= w:
        r = math.sqrt(float(np.mean(x * x)))
    else:
        c = np.cumsum(np.concatenate([[0.0], x * x]))
        r = math.sqrt(max(0.0, float(np.max(c[w:] - c[:-w])) / w))
    return 20 * math.log10(max(r, 1e-6))


def match_levels(samples, types, sr):
    """Pad levels (0-1) that even out loud and quiet pads, with hats and cymbals sitting a bit lower than kicks."""
    want = []
    for x, t in zip(samples, types):
        if x is None or len(x) < 8:
            want.append(None)
            continue
        want.append(10 ** ((TYPE_TRIM_DB.get(t or "Other", -5.0) - loudness_db(x, sr)) / 20.0))
    vals = sorted((g for g in want if g), reverse=True)
    if not vals:
        return [None] * len(samples)
    scale = 0.95 / vals[min(1, len(vals) - 1)]  # the pad that needs the most lift (but one) goes near full
    return [None if g is None else round(max(0.05, min(1.0, g * scale)), 3) for g in want]


__all__ = ["STYLES", "STYLE_NAMES", "PAD_ROLE", "TYPES", "make_kit", "roll_mild", "reroll_pad", "match_levels",
           "GENRE_STYLE", "SCOPES", "SCOPE_LABEL", "style_of"]
