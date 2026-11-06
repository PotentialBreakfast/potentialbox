"""Drum machine sample library: a folder of machine folders (e.g. "Roland TR-808"),
each holding WAVs directly, in kit subfolders, or in category subfolders (BD, Snare, Hats...).

classify() reads sample names ("808bd01", "TR909SN0", "Hat Closed", "SP CLHH1") and
map_kit() puts them on PotentialBox's standard 16-pad layout.
"""
import os
import re
import random

PAD_NAMES = ["Kick", "Kick 2", "Snare", "Clap", "Closed Hat", "Open Hat", "Low Tom", "Mid Tom",
             "High Tom", "Rim", "Cowbell", "Clave", "Shaker", "Cymbal", "FX", "Conga"]

MULTI_WORD_BRANDS = ["Ace Tone", "Electro Harmonix", "Sequential Circuits", "Sound Master", "Watford Electronics",
                     "Star-Instruments", "Deep Sky", "Hin Hong", "Virtual MPC", "Realistic Concertmate"]
BRAND_ALIAS = {"Korg-T1": "Korg", "Hohner-Rhythm": "Hohner", "Lel'": "Lel", "SoundMaster": "Sound Master",
               "Chroma": "Rhodes", "Rhythm": "Ace Tone", "MultiMoog": "Moog", "MG1": "Moog", "Sakata": "Jugg Box"}
MIN_BRAND = 3

CATEGORY_DIR = re.compile(
    r"^(bd|kick|kicks|bassdrum|bass ?drums?|sd|snare|snares|sn|cp|clap|claps|ch|oh|hh|hats?|hihats?|cy|cymbals?|"
    r"crash|ride|rs|rim|rimshot|rims|cb|cowbell|cl|clave|claves|ma|maracas|hc|mc|lc|ht|mt|lt|toms?|tomtoms|"
    r"perc|percussion|hit|hits|fx|sfx|conga|congas|shaker)$", re.I)
AUDIO = (".wav",)


def brand_of(machine):
    for b in MULTI_WORD_BRANDS:
        if machine.lower().startswith(b.lower()):
            return b
    first = machine.split()[0] if machine.split() else machine
    return BRAND_ALIAS.get(first, first)


def tokens(name):
    s = os.path.splitext(name)[0].lower()
    s = re.sub(r"[_\-\.\(\)\[\],+]", " ", s)
    s = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", s)
    return s, s.split()


def classify(name, context=""):
    """Return (category, tom_level) for a sample name. category is a PAD_NAMES-style key or None."""
    s, tk = tokens(name)
    ctx = context.lower()
    t = set(tk)
    has = lambda *ws: any(w in s for w in ws)  # noqa: E731
    tok = lambda *ws: any(w in t for w in ws)  # noqa: E731
    ends = lambda *ws: any(x.endswith(w) and len(x) <= 9 for x in tk for w in ws)  # noqa: E731

    hatish = tok("hh", "hat", "hats", "hihat", "hihats", "chh", "ohh", "clhh", "ophh", "hho", "hhc", "hhcd", "hhod",
                 "hhop", "hhcl", "clhat", "ophat", "ch", "oh", "hhx", "hhclose", "hhopen", "lhh", "phh") or has("hihat", "hi hat", "hhcl", "hhop", "hat") \
        or ends("hh")
    if tok("ohh", "ophh", "hho", "hhod", "hhop", "ophat", "oh", "hhopen", "openhat", "noizophh") or has("open", "ophh", "hhop") \
            or (hatish and tok("op", "o", "opn", "ophi")):
        return "Open Hat", None
    if hatish or has("closed", "clhh", "pedal", "chh"):
        return "Closed Hat", None
    if has("cowb", "cowbl", "agog", "cow") or tok("cb"):
        return "Cowbell", None
    if has("crash", "ride", "cym", "cyn", "china", "splash", "cshd", "rided") or tok("cy", "cup", "edge", "cr", "rd", "crs") \
            or ends("cy"):
        return "Cymbal", None
    if has("clap", "clp") or tok("cp", "claps") or (tok("hc") and "808" not in ctx and "cr-78" not in ctx):
        return "Clap", None
    if has("rim", "sidestick", "stick") or tok("rs", "sst", "ri"):
        return "Rim", None
    if has("kick", "bassdrum", "bass drum", "bass dr", "bdrum", "kik", "bassd") or tok("bd", "k", "kd", "thud") or ends("bd"):
        return "Kick", None
    if has("snare", "snr", "nare", "brush") or tok("sd", "sn", "s", "smack", "sr") or ends("sd", "sn"):
        return "Snare", None
    if has("tom") or tok("lt", "mt", "ht", "tlo", "tme", "thi", "t", "ton", "toms"):
        lvl = None
        sw = lambda *ws: any(x.startswith(w) for x in tk for w in ws)  # noqa: E731
        if tok("lt", "tlo", "lo", "low", "l", "floor", "lotom") or has("lotom", "lo tom", "low") or sw("lo", "xlo", "floor", "flr", "pwrfloor"):
            lvl = 0
        elif tok("mt", "tme", "mid", "med", "medium", "m", "midtom", "md") or has("midtom", "mid tom") or sw("md", "mid", "med"):
            lvl = 1
        elif tok("ht", "thi", "hi", "high", "h", "hitom") or has("hitom", "hi tom", "high") or sw("hi"):
            lvl = 2
        return "Tom", lvl
    if has("conga", "cng", "bongo", "bong", "timb", "tumba", "quinto") or tok("lc", "mc", "hc", "chi", "cme", "clo", "cg"):
        return "Conga", None
    if has("clave", "clav", "wood", "block", "blk") or tok("cl", "cla"):
        return "Clave", None
    if has("shak", "marac", "marc", "cabasa", "tamb", "guiro", "shkr", "cab") or tok("ma", "sh"):
        return "Shaker", None
    if has("zap", "laser", "fx", "scrt", "scratch", "efex", "noise", "noiz", "sweep", "hey", "voice", "vox", "scratch", "blip", "metal"):
        return "FX", None
    if has("perc", "triangle", "tri", "finger", "snap", "vibra", "hit", "tabla", "whistle", "slap", "bell", "gong") \
            or tok("prc", "pc", "per"):
        return "Perc", None
    return None, None


def _list_wavs(folder):
    try:
        return sorted(f for f in os.listdir(folder) if f.lower().endswith(AUDIO))
    except OSError:
        return []


def _collect(folder):
    """WAVs in folder plus those in category-named subfolders (recursive)."""
    out = [os.path.join(folder, f) for f in _list_wavs(folder)]
    others = []
    try:
        subs = sorted(d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d)))
    except OSError:
        subs = []
    for d in subs:
        p = os.path.join(folder, d)
        if CATEGORY_DIR.match(d.strip()):
            for root, dirs, files in os.walk(p):
                dirs.sort()
                out += [os.path.join(root, f) for f in sorted(files) if f.lower().endswith(AUDIO)]
        else:
            others.append(p)
    return out, others


def scan_machine(machine_dir):
    """Return list of kits: [{"name":..., "path": folder, "files": [paths]}]."""
    kits = []
    stack = [machine_dir]
    while stack:
        folder = stack.pop(0)
        files, others = _collect(folder)
        if files:
            rel = os.path.relpath(folder, machine_dir)
            kits.append({"name": "Main kit" if rel == "." else rel.replace(os.sep, " / "), "path": folder, "files": files})
        stack[0:0] = others
    return kits


class Library:
    def __init__(self, root):
        self.root = root
        self.machines = []
        self.brands = {}
        self._kits = {}
        self.refresh()

    def ok(self):
        return bool(self.root and os.path.isdir(self.root) and self.machines)

    def refresh(self):
        self.machines, self.brands, self._kits = [], {}, {}
        if not self.root or not os.path.isdir(self.root):
            return
        try:
            names = sorted((d for d in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, d))
                            and not d.startswith(("_", "."))), key=str.lower)
        except OSError:
            names = []
        self.machines = names
        counts = {}
        for m in names:
            counts.setdefault(brand_of(m), []).append(m)
        other = []
        for b, ms in sorted(counts.items(), key=lambda x: x[0].lower()):
            if len(ms) >= MIN_BRAND:
                self.brands[b] = ms
            else:
                other += ms
        if other:
            self.brands["Other"] = sorted(other, key=str.lower)

    def kits(self, machine):
        if machine not in self._kits:
            self._kits[machine] = scan_machine(os.path.join(self.root, machine))
        return self._kits[machine]

    def random_kit(self, rng=random):
        for _ in range(30):
            m = rng.choice(self.machines)
            ks = self.kits(m)
            if ks:
                return m, rng.randrange(len(ks))
        return None, None


def map_kit(files, context=""):
    """Choose up to 16 files for the standard pad layout. Returns list of 16 (path or None, label)."""
    buckets = {}
    toms = []
    unknown = []
    for f in files:
        parent = os.path.basename(os.path.dirname(f))
        cat, lvl = classify(os.path.basename(f), context)
        if cat is None and CATEGORY_DIR.match(parent.strip()):
            cat, lvl = classify(parent, context)
        if cat == "Tom":
            toms.append((lvl, f))
        elif cat:
            buckets.setdefault(cat, []).append(f)
        else:
            unknown.append(f)
    pads = [None] * 16
    used = set()

    def put(i, f):
        if f and pads[i] is None and f not in used:
            pads[i] = f
            used.add(f)
            return True
        return False

    def first(cat, n=0):
        lst = [f for f in buckets.get(cat, []) if f not in used]
        return lst[n] if len(lst) > n else None

    put(0, first("Kick"))
    put(2, first("Snare"))
    put(3, first("Clap"))
    put(4, first("Closed Hat"))
    put(5, first("Open Hat"))
    for lvl, slot in ((0, 6), (1, 7), (2, 8)):
        put(slot, next((f for l, f in toms if l == lvl and f not in used), None))
    for slot in (6, 7, 8):  # toms with no level: fill remaining tom pads in order
        if pads[slot] is None:
            put(slot, next((f for l, f in toms if f not in used), None))
    put(9, first("Rim"))
    put(10, first("Cowbell"))
    put(11, first("Clave"))
    put(12, first("Shaker"))
    put(13, first("Cymbal"))
    put(14, first("FX") or first("Perc"))
    put(15, first("Conga") or first("Perc"))
    put(1, first("Kick"))  # second kick
    # leftovers fill empty pads: variety first, unknown names last
    order = ["Snare", "Perc", "Conga", "Clap", "Cymbal", "Shaker", "Closed Hat", "Open Hat", "FX", "Kick", "Rim",
             "Cowbell", "Clave"]
    leftovers = [f for c in order for f in buckets.get(c, []) if f not in used]
    leftovers += [f for _, f in toms if f not in used] + unknown
    for i in range(16):
        if pads[i] is None and leftovers:
            put(i, leftovers.pop(0))
    out = []
    for i, f in enumerate(pads):
        if f is None:
            out.append((None, PAD_NAMES[i]))
        else:
            cat, _ = classify(os.path.basename(f), context)
            std = {0: "Kick", 1: "Kick", 2: "Snare", 3: "Clap", 4: "Closed Hat", 5: "Open Hat", 9: "Rim",
                   10: "Cowbell", 11: "Clave", 12: "Shaker", 13: "Cymbal"}.get(i)
            label = PAD_NAMES[i] if (std and cat == std) or (i in (6, 7, 8) and cat == "Tom") else \
                os.path.splitext(os.path.basename(f))[0][:14]
            out.append((f, label))
    return out


# ---------------------------------------------------------------- one-shot index (pad editor)
GROUPS = [("Kick", {"Kick"}), ("Snare", {"Snare"}), ("Clap", {"Clap"}), ("Hats", {"Closed Hat", "Open Hat"}),
          ("Toms", {"Tom"}), ("Perc", {"Perc", "Conga", "Cowbell", "Clave", "Shaker", "Rim"}),
          ("Cymbal", {"Cymbal"}), ("FX", {"FX"}), ("All", None)]
PAD_GROUP = ["Kick", "Kick", "Snare", "Clap", "Hats", "Hats", "Toms", "Toms", "Toms", "Perc", "Perc", "Perc",
             "Perc", "Cymbal", "FX", "Perc"]


def build_index(lib):
    """Every WAV in the collection as (machine, path, category, label), sorted by machine then name."""
    out = []
    for m in lib.machines:
        base = os.path.join(lib.root, m)
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")))
            parent = os.path.basename(root)
            for f in sorted(files):
                if not f.lower().endswith(AUDIO):
                    continue
                cat, _ = classify(f, m)
                if cat is None and CATEGORY_DIR.match(parent.strip()):
                    cat, _ = classify(parent, m)
                out.append((m, os.path.join(root, f), cat, os.path.splitext(f)[0][:24]))
    return out


def filter_index(index, group, machine=None):
    cats = dict(GROUPS).get(group)
    return [e for e in index if (cats is None or e[2] in cats) and (machine is None or e[0] == machine)]
