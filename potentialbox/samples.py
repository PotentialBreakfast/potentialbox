"""Every one-shot PotentialBox can use, sorted by type: the Drum Machine Collection plus any sample folders
(such as the DRUM ONE SHOTS folder MPC TOOLS makes on the MPC's SD card).

Drum machine samples are sorted with library.classify (tuned on the collection's short names such as "808bd01").
Samples in other folders are sorted by whole words in their folder and file names, the way MPC TOOLS' drumsort does:
the nearest folder that names a drum decides ("Kicks", "Hats", "Percs"), and the file name can make it more exact
("Open Hat", "Conga", "Rim"). Loops, phrases and long files are left out.

The index is cached (sample-index.json beside PotentialBox's settings) so only new or changed files are read again.
"""
import json
import os
import re
import struct
import threading
import time

from potentialbox.library import classify as machine_classify, CATEGORY_DIR

AUDIO_EXT = (".wav", ".aif", ".aiff")

TYPES = ["Kick", "808", "Snare", "Clap", "Rim", "Closed Hat", "Open Hat", "Tom", "Conga", "Shaker", "Cowbell",
         "Clave", "Perc", "Cymbal", "FX", "Vox", "Stab", "Other"]
SHORT = {"Closed Hat": "C.HAT", "Open Hat": "O.HAT", "Cowbell": "COWBL", "Cymbal": "CYMBL", "Shaker": "SHAKR"}

# pad editor groups: (name, set of types or None for all)
GROUPS = [("Kick", {"Kick"}), ("808 / Bass", {"808"}), ("Snare", {"Snare"}), ("Clap", {"Clap"}),
          ("Hats", {"Closed Hat", "Open Hat"}), ("Toms", {"Tom"}),
          ("Perc", {"Perc", "Conga", "Cowbell", "Clave", "Shaker", "Rim"}), ("Cymbal", {"Cymbal"}),
          ("FX / Vox", {"FX", "Vox", "Stab"}), ("All", None)]
PAD_GROUP = ["Kick", "Kick", "Snare", "Clap", "Hats", "Hats", "Toms", "Toms", "Toms", "Perc", "Perc", "Perc",
             "Perc", "Cymbal", "FX / Vox", "Perc"]


def group_of_type(t):
    for g, ts in GROUPS:
        if ts and t in ts:
            return g
    return "All"


# ---------------------------------------------------------------- words (for sample folders)
_W = {}


def _add(t, words):
    for w in words.split():
        _W[w] = t


_add("Kick", "kick kicks kik kck bd bassdrum kickdrum 808bd 909bd")
_add("Snare", "snare snares snr sd sn 808sd 909sd")
_add("Clap", "clap claps clp cp snap snaps fingersnap")
_add("Rim", "rim rims rimshot rimshots rs sidestick stick sticks")
_add("Hat", "hat hats hihat hihats hh hhs 808hh")
_add("Closed Hat", "chh ch closedhat closedhats clhh hhc 808ch")
_add("Open Hat", "ohh oh openhat openhats ophh hho 808oh")
_add("Cymbal", "cymbal cymbals cym crash crashes ride rides china splash cr 808cy")
_add("Tom", "tom toms floortom lt mt ht")
_add("Conga", "conga congas bongo bongos timbale timbales timbal djembe cajon tabla tablas surdo udu darbuka "
              "doumbek cuica quinto tumba")
_add("Shaker", "shaker shakers shake tamb tambourine tambo maraca maracas cabasa guiro")
_add("Cowbell", "cowbell cowbells cb agogo")
_add("Clave", "clave claves woodblock woodblocks block tok knock")
_add("Perc", "perc percs percussion triangle vibraslap chimes click clicks")
_add("Vox", "vocal vocals vox voice voices chant chants shout shouts hey yeah choir adlib adlibs")
_add("FX", "fx sfx riser risers sweep sweeps zap zaps laser impact impacts noise uplifter downlifter glitch "
           "glitches scratch scratches reverse")
_add("Stab", "stab stabs chord chords orch orchestra brass horn horns piano keys organ synth pluck plucks")
_add("808", "sub subs subbass bass basses bassline reese 808s")

NEVER = set("loop loops bpm break breaks breakbeat groove grooves fill fills phrase phrases song songs melody "
            "melodies beat beats top tops".split())
DRUM_TYPES = {"Kick", "Snare", "Clap", "Rim", "Hat", "Closed Hat", "Open Hat", "Cymbal", "Tom", "Conga", "Shaker",
              "Cowbell", "Clave", "Perc"}
RANK = {t: 2 for t in DRUM_TYPES}
RANK.update({"Vox": 1, "FX": 1, "Stab": 1, "808": 0})
FAMILY = {"Hat": "Hat", "Closed Hat": "Hat", "Open Hat": "Hat", "Perc": "Perc", "Conga": "Perc", "Shaker": "Perc",
          "Cowbell": "Perc", "Clave": "Perc", "Rim": "Perc"}
GENERIC_DIRS = {"drums", "drum", "samples", "sample", "one shots", "oneshots", "one-shots", "one shot", "sounds", "sound",
                "wav", "wavs", "audio", "kit", "kits", "drum kits", "drum hits", "acoustic", "electronic", "processed",
                "dry", "wet", "drum one shots"}
_GUARD_TOM = {"bottom", "custom", "phantom", "atom", "tomorrow"}
_GUARD_RIDE = {"override", "pride", "bride", "stride"}


def words(s):
    """Lower-case words of a name, also split at letter/digit edges ("808BD" -> 808bd, 808, bd)."""
    out = []
    for w in re.findall(r"[a-z0-9#]+", s.lower()):
        out.append(w)
        parts = re.findall(r"[a-z#]+|[0-9]+", w)
        if len(parts) > 1:
            out += parts
    return out


def classify_words(name):
    """(type or None, never, tom_level) from a file or folder name, by whole words. The strongest kind of word wins
    (a drum word beats an FX word beats a bass word); among equals the later word wins ("Snare Rim" -> Rim)."""
    tk = words(name)
    best, rank, never, lvl = None, -1, False, None
    for i, w in enumerate(tk):
        if w in NEVER:
            never = True
        t = _W.get(w)
        if t is None:  # a drum word inside a longer word: "popkick", "realclaps", "brushlotom"
            if w.endswith("tom") and w not in _GUARD_TOM and len(w) <= 12:
                t = "Tom"
            elif w.endswith("ride") and w not in _GUARD_RIDE and len(w) <= 10:
                t = "Cymbal"
            else:
                for k in ("kick", "snare", "clap", "hihat", "cymbal", "conga", "shaker", "cowbell", "crash", "perc"):
                    if k in w and len(w) <= len(k) + 8:
                        t = {"hihat": "Hat", "crash": "Cymbal"}.get(k, _W.get(k))
                        break
        if w == "bass" and ((i + 1 < len(tk) and tk[i + 1] in ("drum", "drums")) or
                            (i > 0 and tk[i - 1] in ("drum", "drums", "and", "n"))):
            t = "Kick" if i + 1 < len(tk) and tk[i + 1] in ("drum", "drums") else None
        if w == "hi" and i + 1 < len(tk) and tk[i + 1] in ("hat", "hats"):
            t = "Hat"
        if w in ("open", "opn") and i + 1 < len(tk) and tk[i + 1] in ("hat", "hats", "hh", "hihat"):
            t = "Open Hat"
        if w in ("closed", "close", "cl", "pedal") and i + 1 < len(tk) and tk[i + 1] in ("hat", "hats", "hh", "hihat"):
            t = "Closed Hat"
        if t is None:
            continue
        if t == "Hat" and best in ("Open Hat", "Closed Hat"):
            continue
        r = RANK.get(t, 0)
        if r >= rank:
            best, rank = t, r
    if best == "Hat":
        if any(w in ("open", "opn", "op", "o") for w in tk):
            best = "Open Hat"
        elif any(w in ("closed", "close", "cl", "c", "pedal", "tight") for w in tk):
            best = "Closed Hat"
    if best == "Tom":
        s = set(tk)
        if s & {"lt", "low", "lo", "floor", "floortom", "l"}:
            lvl = 0
        elif s & {"mt", "mid", "med", "m"}:
            lvl = 1
        elif s & {"ht", "high", "hi", "h"}:
            lvl = 2
    if best is None and "808" in tk:
        best = "808"
    return best, never, lvl


def sort_folder_sample(fname, dirs, secs):
    """Type of a sample in a sample folder from its file name and the folders above it (nearest last)."""
    base = os.path.splitext(fname)[0]
    ft, never, lvl = classify_words(base.split(" - ", 1)[1] if " - " in base else base)
    if ft is None and " - " in base:
        ft, never2, lvl = classify_words(base)
        never = never or never2
    dt = None
    for d in reversed(dirs):
        t, dnever, dl = classify_words(d)
        if t:
            dt = t
            break
    if never:
        return None, None
    if dt is None:
        t = ft
    elif ft is None:
        t = dt
    elif ft == dt or (FAMILY.get(ft) and FAMILY.get(ft) == FAMILY.get(dt)) or (dt == "Snare" and ft == "Rim"):
        t = dt if ft in ("Hat", "Perc") and dt not in ("Hat", "Perc") else ft
    else:
        t = dt
    if t == "Hat":
        t = "Open Hat" if (secs or 0) > 0.45 else "Closed Hat"
    return t or "Other", lvl


def pack_name(fname, dirs, root_name):
    """Where a sample comes from, for the screen: MPC TOOLS names its copies "<pack> - <name>"."""
    base = os.path.splitext(fname)[0]
    if " - " in base:
        return base.split(" - ", 1)[0].strip()[:40]
    for d in reversed(dirs):
        t, _, _ = classify_words(d)
        if d.lower().strip() not in GENERIC_DIRS and t is None:
            return d[:40]
    return root_name[:40]


def nice_label(fname):
    base = os.path.splitext(fname)[0]
    if " - " in base:
        base = base.split(" - ", 1)[1]
    return base.strip()[:28]


# ---------------------------------------------------------------- file headers
def header_seconds(path):
    """Length in seconds from a WAV or AIFF header without reading the audio. None if it can't tell."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if len(head) < 12:
                return None
            if head[:4] in (b"RIFF", b"RF64") and head[8:12] == b"WAVE":
                rate = blk = 0
                while True:
                    ch = f.read(8)
                    if len(ch) < 8:
                        return None
                    cid, size = ch[:4], struct.unpack("<I", ch[4:])[0]
                    if cid == b"fmt ":
                        fmt = f.read(size + (size & 1))
                        if len(fmt) < 16:
                            return None
                        _, _, rate, _, blk = struct.unpack("<HHIIH", fmt[:14])
                        continue
                    if cid == b"data":
                        if size == 0xFFFFFFFF:
                            size = max(0, os.path.getsize(path) - f.tell())
                        return size / float(rate * blk) if rate and blk else None
                    f.seek(size + (size & 1), 1)
            if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
                while True:
                    ch = f.read(8)
                    if len(ch) < 8:
                        return None
                    cid, size = ch[:4], struct.unpack(">I", ch[4:])[0]
                    if cid == b"COMM":
                        c = f.read(size + (size & 1))
                        frames = struct.unpack(">I", c[2:6])[0]
                        rate = _ext80(c[8:18])
                        return frames / rate if rate else None
                    f.seek(size + (size & 1), 1)
    except (OSError, struct.error, ValueError):
        return None
    return None


def _ext80(b):
    """IEEE 754 80-bit extended float (AIFF sample rate)."""
    if len(b) < 10:
        return 0.0
    exp = ((b[0] & 0x7F) << 8) | b[1]
    mant = int.from_bytes(b[2:10], "big")
    if exp == 0 and mant == 0:
        return 0.0
    return mant * 2.0 ** (exp - 16383 - 63)


# ---------------------------------------------------------------- the index
class Entry:
    __slots__ = ("path", "type", "lvl", "src", "label", "secs", "kind")

    def __init__(self, path, type_, lvl, src, label, secs, kind):
        self.path, self.type, self.lvl, self.src, self.label, self.secs, self.kind = \
            path, type_, lvl, src, label, secs, kind

    def tup(self):
        """(source, path, group-type, label): the shape the pad editor lists."""
        return (self.src, self.path, self.type, self.label)


MAX_SECS = {"Closed Hat": 8.0, "Open Hat": 8.0, "Cymbal": 8.0, "Tom": 4.0, "Conga": 4.0, "Perc": 4.0, "Shaker": 4.0,
            "808": 6.0, "FX": 6.0, "Vox": 4.0, "Stab": 4.0, "Other": 2.5}


class SampleIndex:
    """All usable one-shots. roots: [{"path":..., "kind": "machines"|"folder"}]."""

    def __init__(self, cache_file=None):
        self.cache_file = cache_file
        self.entries = []
        self.by_type = {}
        self.by_path = {}
        self.roots = []
        self.counts = {}       # root path -> number of samples
        self.skipped = 0
        self.ready = False
        self.busy = False
        self.progress = ""
        self._cache = {}
        self._lock = threading.Lock()
        self.load_cache()

    # cache: path -> [size, mtime, secs]
    def load_cache(self):
        if not self.cache_file:
            return
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("v") == 1:
                self._cache = {k: v for k, v in d.get("files", {}).items() if isinstance(v, list) and len(v) == 3}
        except Exception:
            self._cache = {}

    def save_cache(self):
        if not self.cache_file:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            tmp = self.cache_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"v": 1, "files": self._cache}, f)
            os.replace(tmp, self.cache_file)
        except Exception:
            pass

    def _secs(self, path, st):
        c = self._cache.get(path)
        if c and c[0] == st.st_size and c[1] == int(st.st_mtime):
            return c[2]
        s = header_seconds(path)
        self._cache[path] = [st.st_size, int(st.st_mtime), s]
        return s

    def scan(self, roots, stop=None):
        """Read every root (slow part: one header per new file). Safe to call from a worker thread."""
        self.busy = True
        entries, counts, skipped = [], {}, 0
        seen = set()
        try:
            for r in roots:
                path, kind = r.get("path"), r.get("kind", "folder")
                if not path or not os.path.isdir(path):
                    counts[path] = 0
                    continue
                n0 = len(entries)
                if kind == "machines":
                    sk = self._scan_machines(path, entries, seen, stop)
                else:
                    sk = self._scan_folder(path, entries, seen, stop)
                skipped += sk
                counts[path] = len(entries) - n0
                if stop and stop():
                    break
        finally:
            by = {}
            for e in entries:
                by.setdefault(e.type, []).append(e)
            with self._lock:
                self.entries, self.by_type, self.counts, self.skipped = entries, by, counts, skipped
                self.by_path = {e.path: e for e in entries}
                self.roots = [dict(r) for r in roots]
                self.ready = True
                self.busy = False
                self.progress = ""
            self.save_cache()
        return len(entries)

    def _walk(self, top):
        for root, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")))
            yield root, sorted(f for f in files if f.lower().endswith(AUDIO_EXT) and not f.startswith("._"))

    def _scan_machines(self, top, out, seen, stop):
        skipped = 0
        try:
            machines = sorted(d for d in os.listdir(top) if os.path.isdir(os.path.join(top, d))
                              and not d.startswith(("_", ".")))
        except OSError:
            return 0
        for m in machines:
            self.progress = m
            for root, files in self._walk(os.path.join(top, m)):
                parent = os.path.basename(root)
                for f in files:
                    p = os.path.join(root, f)
                    if p in seen:
                        continue
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    secs = self._secs(p, st)
                    if secs is not None and secs > 10:
                        skipped += 1
                        continue
                    cat, lvl = machine_classify(f, m)
                    if cat is None and CATEGORY_DIR.match(parent.strip()):
                        cat, lvl = machine_classify(parent, m)
                    if cat == "FX" and classify_words(f)[0] == "Vox":
                        cat = "Vox"
                    seen.add(p)
                    out.append(Entry(p, cat or "Other", lvl, m, os.path.splitext(f)[0][:28], secs, "m"))
            if stop and stop():
                break
        return skipped

    def _scan_folder(self, top, out, seen, stop):
        skipped = 0
        top = os.path.normpath(top)
        root_name = os.path.basename(top) or top
        for root, files in self._walk(top):
            rel = os.path.relpath(root, top)
            dirs = [root_name] + ([] if rel == "." else rel.split(os.sep))
            self.progress = dirs[-1]
            for f in files:
                p = os.path.join(root, f)
                if p in seen:
                    continue
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                secs = self._secs(p, st)
                t, lvl = sort_folder_sample(f, dirs, secs)
                if t is None or (secs is not None and secs > MAX_SECS.get(t, 2.5)) or secs == 0:
                    skipped += 1
                    continue
                seen.add(p)
                out.append(Entry(p, t, lvl, pack_name(f, dirs, root_name), nice_label(f), secs, "f"))
            if stop and stop():
                break
        return skipped

    def scan_async(self, roots, done=None):
        if self.busy:
            return False
        self.busy = True

        def work():
            try:
                self.scan(roots)
            finally:
                self.busy = False
                if done:
                    done()
        threading.Thread(target=work, daemon=True).start()
        return True

    # ---------------------------------------------------------------- queries
    def of_type(self, t, scope="all"):
        lst = self.by_type.get(t, [])
        if scope == "machines":
            return [e for e in lst if e.kind == "m"]
        if scope == "folders":
            return [e for e in lst if e.kind == "f"]
        return lst

    def type_counts(self):
        return {t: len(self.by_type.get(t, [])) for t in TYPES}

    def find(self, path):
        return self.by_path.get(path)

    def filter(self, group, source=None):
        """Pad editor list: [(source, path, type, label)] for a GROUPS name, optionally one source only."""
        types = dict(GROUPS).get(group)
        out = [e.tup() for e in self.entries if (types is None or e.type in types) and (source is None or e.src == source)]
        return out


def default_roots(library_root, folders):
    roots = []
    if library_root:
        roots.append({"path": library_root, "kind": "machines"})
    for f in folders or []:
        if f and f != library_root:
            roots.append({"path": f, "kind": "folder"})
    return roots


if __name__ == "__main__":  # quick check: python -m potentialbox.samples <folder>
    import sys
    ix = SampleIndex()
    t0 = time.time()
    n = ix.scan([{"path": p, "kind": "folder"} for p in sys.argv[1:]])
    print(n, "samples in", round(time.time() - t0, 2), "s;", ix.skipped, "left out")
    for t, c in ix.type_counts().items():
        print(f"  {t:11s} {c}")
