"""PotentialBox sound engine.

Block-based numpy DSP:
  Synth 1  - mono virtual-analog synth (saw/square, sub, resonant filter)
  Synth 2  - mono wavetable synth (6 morphing tables, LFO, unison)
  Drums    - 16-pad sample player with a built-in synthesized kit
  FX       - tempo-synced ping-pong delay
"""
import math
import time
import os
import collections
APP = "PotentialBox"
CFG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), APP)
CFG_FILE = os.path.join(CFG_DIR, "state.json")

import numpy as np
from scipy.signal import sosfilt, lfilter

TWO_PI = 2.0 * math.pi
DIVISIONS = [("1/16", 0.25), ("1/8T", 1 / 3), ("1/8", 0.5), ("3/16", 0.75), ("1/4", 1.0), ("3/8", 1.5)]
BASE_TABLES = ["Analog", "Vowel", "Harmonic", "PWM", "FM Bell", "Digital"]
LFO_SHAPES = ["Sine", "Triangle", "Saw up", "Saw down", "Square", "Random", "Smooth random", "Step"]
STEP_SHAPE = LFO_SHAPES.index("Step")
LFO_SYNC = [("Free", None), ("4 bars", 16), ("2 bars", 8), ("1 bar", 4), ("1/2", 2), ("1/4", 1), ("1/8", 0.5),
            ("1/16", 0.25), ("1/32", 0.125), ("1/4T", 2 / 3), ("1/8T", 1 / 3), ("1/16T", 1 / 6)]
MOD_SOURCES = ["Off", "LFO 1", "LFO 2", "Mod env", "Amp env", "Velocity", "Note", "Random"]
MOD_DESTS = {"s1": ["Pitch", "Osc 2 pitch", "Cutoff", "Resonance", "Saw > Square", "Pulse width", "FM", "Ring mod",
                    "Noise", "Volume", "Pan", "Drive", "Supersaw", "Unison", "Distortion"],
             "s2": ["Pitch", "Cutoff", "Resonance", "Wave position", "Unison", "Sub osc", "Noise", "Volume", "Pan",
                    "Warp", "Distortion"]}
DEFAULT_ROUTES = {
    "s1": [("LFO 1", "Pitch"), ("LFO 1", "Cutoff"), ("LFO 2", "Pulse width"), ("Mod env", "Cutoff"),
           ("Velocity", "Cutoff"), ("LFO 2", "Pan"), ("Mod env", "Pitch"), ("LFO 2", "Volume"),
           ("Off", "Pitch"), ("Off", "Cutoff"), ("Off", "Volume"), ("Off", "Pan")],
    "s2": [("LFO 1", "Pitch"), ("LFO 1", "Cutoff"), ("LFO 2", "Wave position"), ("Mod env", "Wave position"),
           ("Velocity", "Cutoff"), ("LFO 2", "Pan"), ("Mod env", "Pitch"), ("LFO 2", "Volume"),
           ("Off", "Pitch"), ("Off", "Cutoff"), ("Off", "Volume"), ("Off", "Pan")]}
CHORDS = [("Off", (0,)), ("Octave", (0, 12)), ("Fifth", (0, 7)), ("Fifth + octave", (0, 7, 12)), ("Major", (0, 4, 7)),
          ("Minor", (0, 3, 7)), ("Sus2", (0, 2, 7)), ("Sus4", (0, 5, 7)), ("Major 7", (0, 4, 7, 11)),
          ("Minor 7", (0, 3, 7, 10)), ("Dominant 7", (0, 4, 7, 10)), ("Minor 9", (0, 3, 10, 14)), ("Stack", (0, 7, 12, 19))]
# v1.12: scale chords. The played note is the top of the chord and the notes under it are stacked in thirds from the
# key's scale, so a melody on Seq 2 turns into a chord progression that always fits the key (melody on top).
CHORDS += [("Scale triad", None), ("Scale 7th", None), ("Scale 9th", None)]
HARM_SCALES = {"Minor": (0, 2, 3, 5, 7, 8, 10), "Major": (0, 2, 4, 5, 7, 9, 11), "Dorian": (0, 2, 3, 5, 7, 9, 10),
               "Phrygian": (0, 1, 3, 5, 7, 8, 10), "Mixolydian": (0, 2, 4, 5, 7, 9, 10),
               "Harmonic minor": (0, 2, 3, 5, 7, 8, 11)}
HARM_SCALE_NAMES = list(HARM_SCALES)
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def scale_chord(note, key, scale, size, voicing=0):
    """Offsets (semitones from the played note) of a chord in the key with the played note on top: size 3, 4 or 5
    notes stacked down in scale thirds. Notes outside the scale are harmonised as the scale note just under them.
    voicing 1 = drop 2 (open), 2 = drop 2 and 4 (wide)."""
    pcs = sorted((key + iv) % 12 for iv in HARM_SCALES[scale])
    n = int(round(note))
    below = []
    m = n
    while len(below) < 2 * (size - 1) + 1:
        m -= 1
        if m % 12 in pcs:
            below.append(m)
    top = n if n % 12 in pcs else None
    offs = [0]
    k = 1 if top is not None else 2   # the scale note a third under the top (or under its in-scale stand-in)
    for i in range(size - 1):
        offs.append(below[k + 2 * i] - n)
    if voicing >= 1 and len(offs) >= 3:
        offs[1] -= 12
    if voicing >= 2 and len(offs) >= 4:
        offs[3] -= 12
    return offs


def lane_chord(note, key, scale, degree, size, voicing=0):
    """The chord the chord lane asked for (scale degree 1-7, as a triad / 7th / 9th), voiced close under the played
    note, which stays on top. A top note outside the chord adds colour (a 9th, 11th or 6th) over it."""
    sc = HARM_SCALES[scale]
    pcs = {(key + sc[(degree - 1 + 2 * i) % 7]) % 12 for i in range(size)}
    n = int(round(note))
    offs = [0]
    m = n
    while len(offs) < size and m > n - 30:
        m -= 1
        if m % 12 in pcs and n - m != 1:   # no semitone rub right under the melody
            offs.append(m - n)
    if voicing >= 1 and len(offs) >= 3:
        offs[1] -= 12
    if voicing >= 2 and len(offs) >= 4:
        offs[3] -= 12
    return offs

VOICINGS = ["Close", "Open", "Wide"]
FTYPES = ["LP 24", "LP 12", "HP 12", "Band-pass", "Notch", "Comb", "Formant"]
VOWELS = [(730, 1090, 2440), (530, 1840, 2480), (270, 2290, 3010), (570, 840, 2410), (300, 870, 2240)]
GLIDE_MODES = ["Slides only", "Always"]
# ---- v1.6
ARP_MODES = ["Off", "Up", "Down", "Up-down", "Random", "As played"]
ARP_RATES = [("1/4", 24), ("1/8", 12), ("1/8T", 8), ("1/16", 6), ("1/16T", 4), ("1/32", 3)]
ARP_ACCENTS = ["Off", "Every 2nd", "Every 3rd", "Every 4th"]
DRUM_CONDS = ["Always", "Fill only", "Not in fill", "1st of 2", "2nd of 2", "1st of 4", "2nd of 4", "3rd of 4",
              "4th of 4", "1st of 8", "8th of 8"]
DUCK_SOURCES = [f"Pad {i}" for i in range(1, 17)] + ["Every beat"]
GLUE_SPEEDS = [("Fast", 0.003, 0.06), ("Medium", 0.01, 0.15), ("Slow", 0.03, 0.4)]
# ---- v1.12: pro synth engine (unison, drive, distortion, synth FX, wavetable warp)
UNI_COUNTS = [1, 2, 3, 4, 5, 7]
UNI_POS = {1: (0.0,), 2: (-1.0, 1.0), 3: (-1.0, 0.0, 1.0), 4: (-1.0, -0.36, 0.33, 1.0),
           5: (-1.0, -0.47, 0.03, 0.52, 1.0), 7: (-1.0, -0.66, -0.3, 0.02, 0.31, 0.63, 1.0)}
SUB_TYPES = ["-1 oct, filtered", "-1 oct, clean", "Root, clean"]  # clean = added after the filter and distortion
DIST_TYPES = ["Off", "Tube", "Tape", "Fold", "Crush", "Hard clip"]
SYN_FX = ["Off", "Chorus", "Ensemble", "Dimension", "Phaser", "Flanger"]
WARPS = ["Off", "Bend +", "Bend -", "Mirror", "Sync", "Squeeze", "Phase FM", "Quantize"]
BOUNCE_STEMS = ("s1", "s2", "dr", "fx", "lp")  # v2.0: what CAPTURE > STEMS saves next to the mix
HIST_SECS = 34.0                      # v2.2 GRAB: always keeps this much (8 bars at 60 BPM + a little)
HIST_KEYS = ("mix",) + BOUNCE_STEMS


def bounce_stems(bnc):
    """Cut a finished bounce down to exactly its bars: {"mix": array, "s1": array, ...} (stereo float)."""
    a, n = bnc["bar_at"] or 0, bnc["need"]
    mix = np.concatenate([b[0] for b in bnc["buf"]])[a:a + n]
    out = {"mix": mix}
    for k in BOUNCE_STEMS:
        parts = [b[1][k] if k in b[1] else np.zeros((b[2], 2)) for b in bnc["buf"]]
        out[k] = np.concatenate(parts)[a:a + n]
    return out


PUNCH_FX = ["Repeat 1/8", "Repeat 1/16", "Roll 1/32", "Tape stop", "Reverse", "Filter sweep", "Gate 1/16", "Echo throw"]


def _load_akwf():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "akwf_tables.npz")
    try:
        d = np.load(path)
        return [str(x) for x in d["names"]], d["spectra"]
    except Exception:
        return [], None


AKWF_NAMES, AKWF_SPECTRA = _load_akwf()


def _load_user_wavetables():
    """Append single-cycle WAVs from %APPDATA%\\PotentialBox\\Wavetables (or state.json's wavetable_dir)."""
    global AKWF_NAMES, AKWF_SPECTRA
    try:
        import json
        folder = os.path.join(CFG_DIR, "Wavetables")
        if os.path.isfile(CFG_FILE):
            try:
                d = json.load(open(CFG_FILE))
                if isinstance(d, dict) and d.get("wavetable_dir"):
                    folder = d["wavetable_dir"]
            except Exception:
                pass
        if not folder or not os.path.isdir(folder):
            return
        names, spectra = [], []
        for fn in sorted(os.listdir(folder)):
            if not fn.lower().endswith(".wav"):
                continue
            try:
                from scipy.io import wavfile
                sr, data = wavfile.read(os.path.join(folder, fn))
                if isinstance(data, np.ndarray) and data.ndim > 1:
                    data = data.mean(axis=1)
                data = np.asarray(data, dtype=float)
                if data.size < 8:
                    continue
                data = data / max(float(np.max(np.abs(data))), 1e-9)
                X = np.fft.rfft(data, n=2048)
                X[0] = 0.0
                names.append(os.path.splitext(fn)[0])
                spectra.append(X[np.newaxis, :])
            except Exception:
                continue
        if not names:
            return
        AKWF_NAMES = list(AKWF_NAMES) + names
        arr = np.array(spectra)
        if AKWF_SPECTRA is None:
            AKWF_SPECTRA = arr
        else:
            AKWF_SPECTRA = np.concatenate([AKWF_SPECTRA, arr], axis=0)
    except Exception:
        pass


_load_user_wavetables()
TABLE_NAMES = BASE_TABLES + AKWF_NAMES  # 6 built-in + 24 AKWF (CC0) + user tables

KIT_NAMES = ["Kick", "808", "Snare", "Clap", "Closed Hat", "Open Hat", "Low Tom", "Mid Tom",
             "High Tom", "Rim", "Cowbell", "Clave", "Shaker", "Crash", "Zap", "Conga"]


# ----------------------------------------------------------------------------- parameters
class Param:
    def __init__(self, key, label, lo, hi, default, curve="lin", step=None, unit="", choices=None):
        self.key, self.label, self.lo, self.hi = key, label, lo, hi
        self.default, self.curve, self.step, self.unit, self.choices = default, curve, step, unit, choices

    def to_val(self, n):
        n = min(max(float(n), 0.0), 1.0)
        if self.curve == "exp":
            v = self.lo * (self.hi / self.lo) ** n
        else:
            v = self.lo + n * (self.hi - self.lo)
        if self.step:
            v = round(v / self.step) * self.step
        return v

    def to_norm(self, v):
        v = min(max(float(v), min(self.lo, self.hi)), max(self.lo, self.hi))
        if self.curve == "exp":
            return math.log(v / self.lo) / math.log(self.hi / self.lo)
        return (v - self.lo) / (self.hi - self.lo)

    def fmt(self, v):
        if self.choices:
            return self.choices[int(round(v))]
        u = self.unit
        if u == "Hz":
            return f"{v/1000:.1f} kHz" if v >= 1000 else f"{v:.0f} Hz"
        if u == "s":
            return f"{v:.2f} s" if v >= 1 else f"{v*1000:.0f} ms"
        if u == "%":
            return f"{v*100:.0f}%"
        if u == "+-%":
            return f"{v*100:+.0f}%"
        if u == "st":
            return f"{v:+.0f} st"
        if u == "oct":
            return f"{v:+.0f} oct"
        if u == "tilt":  # v2.1: drum tone, centre is flat
            if abs(v) < 0.02:
                return "Flat"
            return f"Darker {abs(v)*100:.0f}%" if v < 0 else f"Brighter {v*100:.0f}%"
        if u == "bip":  # DJ-style filter: centre is off
            if abs(v) < 0.02:
                return "Off"
            return f"Low-pass {abs(v)*100:.0f}%" if v < 0 else f"High-pass {v*100:.0f}%"
        if u == "djm":  # macro whose centre is "off"
            if abs(v - 0.5) < 0.02:
                return "Centre"
            return f"LP {(0.5 - v) * 200:.0f}%" if v < 0.5 else f"HP {(v - 0.5) * 200:.0f}%"
        if u == "pan":
            if abs(v) < 0.02:
                return "Centre"
            return f"L {abs(v)*100:.0f}%" if v < 0 else f"R {v*100:.0f}%"
        if u == "ct":
            return f"{v:.0f} cents"
        if u == "sw":
            return "Genre" if v <= 50.5 else f"{v:.0f}%"
        if u == "dB":
            return "0 dB" if abs(v) < 0.05 else f"{v:+.1f} dB"
        return f"{v:.2f}"


# ----------------------------------------------------------------------------- macros
# (name, short description, mode, [(param, amount in normalized units, shape), ...])
# Macros never overwrite your settings: they add an offset on top, so turning a macro back to
# zero (or centre for the DJ filter) returns every knob to exactly where you left it.
# shapes: lin = steady, late = only in the top half, early = all in the bottom half, sq = slow then fast
MACROS = [
    ("S1 Sweep", "Opens Synth 1, adds resonance, throws into delay near the top", "uni",
     [("s1.cutoff", 0.55, "lin"), ("s1.reso", 0.25, "lin"), ("s1.envamt", 0.15, "lin"), ("fx.s1", 0.35, "late")]),
    ("S2 Sweep", "Scans Synth 2's wavetable and filter, wobble at the top", "uni",
     [("s2.pos", 0.6, "lin"), ("s2.cutoff", 0.45, "lin"), ("s2.lfoamt", 0.35, "late")]),
    ("Acid", "Synth 1 squelch: resonance, envelope, drive and slide", "uni",
     [("s1.reso", 0.6, "lin"), ("s1.envamt", 0.5, "lin"), ("s1.fdecay", -0.25, "lin"), ("s1.drive", 0.6, "lin"),
      ("s1.glide", 0.3, "late")]),
    ("Wobble", "Synth 2 LFO wobble, deeper and faster", "uni",
     [("s2.lfoamt", 0.8, "early"), ("s2.lforate", 0.35, "lin"), ("s2.cutoff", 0.2, "lin")]),
    ("Bright", "Opens up both synths", "uni",
     [("s1.cutoff", 0.3, "lin"), ("s2.cutoff", 0.3, "lin"), ("s1.envamt", 0.2, "lin"), ("s2.envamt", 0.2, "lin")]),
    ("Pluck", "Both synths short and stabby", "uni",
     [("s1.decay", -0.45, "lin"), ("s2.decay", -0.45, "lin"), ("s1.sustain", -0.8, "early"),
      ("s2.sustain", -0.8, "early"), ("s1.release", -0.4, "lin"), ("s2.release", -0.4, "lin")]),
    ("Glide", "Both synths slide between notes", "uni", [("s1.glide", 0.7, "lin"), ("s2.glide", 0.7, "lin")]),
    ("Wide", "Detunes both synths into a fat chorus", "uni", [("s1.detune", 0.6, "lin"), ("s2.detune", 0.7, "lin")]),
    ("Dub Throw", "Delay sends up, repeats get longer and darker", "uni",
     [("fx.s1", 0.6, "lin"), ("fx.s2", 0.6, "lin"), ("fx.dr", 0.25, "late"), ("fx.fb", 0.45, "late"),
      ("fx.tone", -0.4, "lin")]),
    ("Space", "Reverb on everything, bigger room as it goes", "uni",
     [("rv.s1", 0.6, "lin"), ("rv.s2", 0.6, "lin"), ("rv.dr", 0.35, "lin"), ("rv.size", 0.5, "late")]),
    ("DJ Filter", "Centre = off. Left = low-pass, right = high-pass", "bip", [("m.filter", 1.0, "bip")]),
    ("Build-Up", "Riser: high-pass, reverb and repeats climb, kick drops out at the top", "uni",
     [("m.filter", 0.42, "sq"), ("rv.s1", 0.5, "lin"), ("rv.s2", 0.5, "lin"), ("rv.dr", 0.5, "lin"),
      ("fx.fb", 0.3, "late"), ("s1.cutoff", 0.3, "lin"), ("dr.p1.level", -0.9, "late"), ("dr.p2.level", -0.9, "late")]),
    ("Lo-Fi", "Bit-crush and dirt on the whole mix", "uni",
     [("m.crush", 0.85, "lin"), ("dr.filter", -0.3, "lin"), ("m.drive", 0.25, "lin")]),
    ("Drum Smash", "Heavy drum drive", "uni", [("dr.drive", 0.75, "lin"), ("dr.vol", 0.08, "lin"), ("m.drive", 0.15, "late")]),
    ("Tighten", "Hats, cymbals and snare get short", "uni",
     [("dr.p5.decay", -0.75, "lin"), ("dr.p6.decay", -0.85, "lin"), ("dr.p14.decay", -0.85, "lin"),
      ("dr.p3.decay", -0.45, "lin"), ("dr.p4.decay", -0.45, "lin"), ("rv.dr", -0.3, "lin")]),
    ("Glue", "Master saturation that pulls the mix together", "uni", [("m.drive", 0.5, "lin"), ("dr.drive", 0.15, "lin")]),
]


def _shape(name, m):
    if name == "late":
        return max(0.0, (m - 0.5) * 2.0)
    if name == "early":
        return min(1.0, m * 2.0)
    if name == "sq":
        return m * m
    if name == "bip":
        return (m - 0.5)  # +-0.5 of the target's 0..1 range: full sweep both ways
    return m


def _build_specs():
    S = []
    a = S.append
    for pre, name in (("s1", "Synth 1"), ("s2", "Synth 2")):
        if pre == "s1":
            a(Param("s1.wave", "Saw > Square", 0, 1, 0.0, unit="%"))
            a(Param("s1.supersaw", "Supersaw", 0, 1, 0.0, unit="%"))
            a(Param("s1.pw", "Pulse width", 0.05, 0.5, 0.5, unit="%"))
            a(Param("s1.detune", "Detune", 0, 50, 8, unit="ct"))
            a(Param("s1.sub", "Sub osc", 0, 1, 0.3, unit="%"))
            a(Param("s1.fdecay", "Filter decay", 0.01, 3, 0.25, "exp", unit="s"))
            a(Param("s1.drive", "Drive", 0, 1, 0.2, unit="%"))
            cut, res, env = 900, 0.3, 0.5
        else:
            a(Param("s2.table", "Wavetable", 0, len(TABLE_NAMES) - 1, 0, step=1, choices=TABLE_NAMES))
            a(Param("s2.pos", "Wave position", 0, 1, 0.3, unit="%"))
            a(Param("s2.posenv", "Env→Position", -1, 1, 0.3, unit="+-%"))
            a(Param("s2.lforate", "LFO speed", 0.05, 12, 0.5, "exp", unit="Hz"))
            a(Param("s2.lfoamt", "LFO→Position", 0, 1, 0.2, unit="%"))
            a(Param("s2.detune", "Unison", 0, 1, 0.2, unit="%"))
            cut, res, env = 4000, 0.2, 0.3
        a(Param(pre + ".octave", "Octave", -2, 2, -1 if pre == "s1" else 0, step=1, unit="oct"))
        a(Param(pre + ".cutoff", "Cutoff", 40, 16000, cut, "exp", unit="Hz"))
        a(Param(pre + ".reso", "Resonance", 0, 1, res, unit="%"))
        a(Param(pre + ".envamt", "Filter env", 0, 1, env, unit="%"))
        a(Param(pre + ".attack", "Attack", 0.001, 2, 0.002, "exp", unit="s"))
        a(Param(pre + ".decay", "Decay", 0.01, 4, 0.4 if pre == "s1" else 0.6, "exp", unit="s"))
        a(Param(pre + ".sustain", "Sustain", 0, 1, 0.6 if pre == "s1" else 0.5, unit="%"))
        a(Param(pre + ".decay2", "Decay 2", 0, 4, 0.0, unit="s"))
        a(Param(pre + ".sustain2", "Sustain 2", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".release", "Release", 0.005, 3, 0.15 if pre == "s1" else 0.4, "exp", unit="s"))
        a(Param(pre + ".glide", "Glide (slides)", 0.005, 1, 0.06, "exp", unit="s"))
        a(Param(pre + ".vol", name + " volume", 0, 1, 0.7, unit="%"))
        # v2.0: each sound's own level, so presets come out level-matched without moving your volume knob
        a(Param(pre + ".trim", "Sound level", -12, 12, 0.0, unit="dB"))
        # ---- v1.5: oscillator extras, chords, filter types, modulation (all neutral by default)
        if pre == "s1":
            a(Param("s1.osc2", "Osc 2 pitch", -24, 24, 0, step=1, unit="st"))
            a(Param("s1.fm", "FM (osc 2 > 1)", 0, 1, 0.0, unit="%"))
            a(Param("s1.ring", "Ring mod", 0, 1, 0.0, unit="%"))
            a(Param("s1.sync", "Hard sync", 0, 1, 0, step=1, choices=["Off", "On"]))
        else:
            a(Param("s2.sub", "Sub osc", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".noise", "Noise", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".chord", "Chord", 0, len(CHORDS) - 1, 0, step=1, choices=[c[0] for c in CHORDS]))
        a(Param(pre + ".voicing", "Chord voicing", 0, len(VOICINGS) - 1, 0, step=1, choices=VOICINGS))
        a(Param(pre + ".hkey", "Chord key", 0, 11, 0, step=1, choices=KEY_NAMES))
        a(Param(pre + ".hscale", "Chord scale", 0, len(HARM_SCALE_NAMES) - 1, 0, step=1, choices=HARM_SCALE_NAMES))
        a(Param(pre + ".lane", "Chord lane", 0, 1, 0, step=1, choices=["Off", "On"]))
        a(Param(pre + ".pan", "Pan", -1, 1, 0.0, unit="pan"))
        a(Param(pre + ".drift", "Analog drift", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".penv", "Pitch env", -24, 24, 0.0, unit="st"))
        a(Param(pre + ".pdec", "Pitch env time", 0.005, 2, 0.08, "exp", unit="s"))
        a(Param(pre + ".ftype", "Filter type", 0, len(FTYPES) - 1, 0, step=1, choices=FTYPES))
        a(Param(pre + ".keytrk", "Key tracking", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".velamp", "Velocity > volume", 0, 1, 0.65, unit="%"))
        a(Param(pre + ".glmode", "Glide mode", 0, 1, 0, step=1, choices=GLIDE_MODES))
        # ---- v1.12: unison, filter drive, distortion, synth FX (and wavetable warp on Synth 2)
        a(Param(pre + ".uni", "Unison voices", 0, len(UNI_COUNTS) - 1, 0 if pre == "s1" else 1, step=1,
                choices=[str(c) for c in UNI_COUNTS]))
        if pre == "s1":
            a(Param("s1.unidet", "Unison detune", 0, 1, 0.3, unit="%"))
            a(Param("s1.subtype", "Sub mode", 0, len(SUB_TYPES) - 1, 0, step=1, choices=SUB_TYPES))
        a(Param(pre + ".uniwid", "Unison width", 0, 1, 0.8 if pre == "s1" else 0.5, unit="%"))
        a(Param(pre + ".fdrive", "Filter drive", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".dist", "Distortion", 0, len(DIST_TYPES) - 1, 0, step=1, choices=DIST_TYPES))
        a(Param(pre + ".distamt", "Dist amount", 0, 1, 0.4, unit="%"))
        a(Param(pre + ".sfx", "Synth FX", 0, len(SYN_FX) - 1, 0, step=1, choices=SYN_FX))
        a(Param(pre + ".sfxamt", "Synth FX amount", 0, 1, 0.5, unit="%"))
        if pre == "s2":
            a(Param("s2.warp", "Warp", 0, len(WARPS) - 1, 0, step=1, choices=WARPS))
            a(Param("s2.warpamt", "Warp amount", 0, 1, 0.3, unit="%"))
        for L, (shape, rate) in ((1, (0, 2.0)), (2, (1, 0.5))):
            a(Param(f"{pre}.l{L}shape", f"LFO {L} shape", 0, len(LFO_SHAPES) - 1, shape, step=1, choices=LFO_SHAPES))
            a(Param(f"{pre}.l{L}rate", f"LFO {L} speed", 0.05, 20, rate, "exp", unit="Hz"))
            a(Param(f"{pre}.l{L}sync", f"LFO {L} sync", 0, len(LFO_SYNC) - 1, 0, step=1, choices=[x[0] for x in LFO_SYNC]))
            for st in range(16):
                a(Param(f"{pre}.l{L}step{st}", f"LFO {L} step {st + 1}", -1, 1, 0.0, unit="+-%"))
        a(Param(pre + ".mea", "Mod env attack", 0.001, 2, 0.005, "exp", unit="s"))
        a(Param(pre + ".med", "Mod env decay", 0.01, 4, 0.3, "exp", unit="s"))
        for j, (src, dst) in enumerate(DEFAULT_ROUTES[pre]):
            a(Param(f"{pre}.m{j+1}src", f"Slot {j+1} source", 0, len(MOD_SOURCES) - 1, MOD_SOURCES.index(src),
                    step=1, choices=MOD_SOURCES))
            a(Param(f"{pre}.m{j+1}dst", f"Slot {j+1} target", 0, len(MOD_DESTS[pre]) - 1, MOD_DESTS[pre].index(dst),
                    step=1, choices=MOD_DESTS[pre]))
            a(Param(f"{pre}.m{j+1}amt", f"Slot {j+1} amount", -1, 1, 0.0, unit="+-%"))
        # ---- v1.6: arpeggiator (part of the sound), ducking and EQ (part of the mix)
        a(Param(pre + ".arp", "Arp", 0, len(ARP_MODES) - 1, 0, step=1, choices=ARP_MODES))
        a(Param(pre + ".arprate", "Arp rate", 0, len(ARP_RATES) - 1, 3, step=1, choices=[r[0] for r in ARP_RATES]))
        a(Param(pre + ".arpoct", "Arp octaves", 0, 3, 0, step=1, choices=["1 octave", "2 octaves", "3 octaves", "4 octaves"]))
        a(Param(pre + ".arpgate", "Arp gate", 0.05, 1, 0.6, unit="%"))
        a(Param(pre + ".arpswing", "Arp swing", 0, 0.75, 0.0, unit="%"))
        a(Param(pre + ".arphold", "Arp hold", 0, 1, 0, step=1, choices=["Off", "On"]))
        a(Param(pre + ".arpchance", "Arp chance", 0, 1, 1.0, unit="%"))
        a(Param(pre + ".arpacc", "Arp accent", 0, len(ARP_ACCENTS) - 1, 0, step=1, choices=ARP_ACCENTS))
        a(Param("dk." + pre, "Duck " + name, 0, 1, 0.0, unit="%"))
        for band, lab in (("lo", "Low"), ("mid", "Mid"), ("hi", "High")):
            a(Param(f"eq.{pre}.{band}", f"{name} {lab}", -12, 12, 0.0, unit="dB"))
    for i in range(16):
        a(Param(f"dr.p{i+1}.tune", "Tune", -24, 24, 0, step=1, unit="st"))
        a(Param(f"dr.p{i+1}.decay", "Length", 0.02, 1, 1.0, unit="%"))
        a(Param(f"dr.p{i+1}.level", "Level", 0, 1, 0.8, unit="%"))
        a(Param(f"dr.p{i+1}.pan", "Pan", -1, 1, 0.0, unit="pan"))
        a(Param(f"dr.p{i+1}.chance", "Chance", 0, 1, 1.0, unit="%"))
        a(Param(f"dr.p{i+1}.cond", "Plays", 0, len(DRUM_CONDS) - 1, 0, step=1, choices=DRUM_CONDS))
        a(Param(f"dr.p{i+1}.choke", "Choke", 0, 8, 0, step=1, choices=["Off"] + [str(g) for g in range(1, 9)]))
    for band, lab in (("lo", "Low"), ("mid", "Mid"), ("hi", "High")):
        a(Param(f"eq.dr.{band}", f"Drums {lab}", -12, 12, 0.0, unit="dB"))
    for band, lab in (("lo", "Low"), ("mid", "Mid"), ("hi", "High")):
        a(Param(f"eq.m.{band}", f"Master {lab}", -12, 12, 0.0, unit="dB"))
    a(Param("eq.lof", "Low EQ freq", 60, 400, 150, "exp", unit="Hz"))
    a(Param("eq.hif", "High EQ freq", 2000, 12000, 6000, "exp", unit="Hz"))
    a(Param("dk.fx", "Duck FX returns", 0, 1, 0.0, unit="%"))
    a(Param("dk.src", "Duck from", 0, len(DUCK_SOURCES) - 1, 0, step=1, choices=DUCK_SOURCES))
    a(Param("dk.rel", "Duck release", 0.03, 0.8, 0.18, "exp", unit="s"))
    a(Param("m.glue", "Glue comp", 0, 1, 0.0, unit="%"))
    a(Param("m.gluespd", "Glue speed", 0, len(GLUE_SPEEDS) - 1, 1, step=1, choices=[g[0] for g in GLUE_SPEEDS]))
    a(Param("m.width", "Stereo width", 0, 2, 1.0, unit="%"))
    a(Param("sc.morph", "Scene morph", 0, 1, 0.0, unit="%"))
    a(Param("sc.src", "Scene from", 1, 8, 1, step=1, choices=[str(i) for i in range(1, 9)]))
    a(Param("sc.dst", "Scene to", 1, 8, 2, step=1, choices=[str(i) for i in range(1, 9)]))
    # ---- looper (v1.7)
    for t in range(1, 6):
        a(Param(f"lp.t{t}.vol", f"Track {t} level", 0, 1.2, 0.85, unit="%"))
        a(Param(f"lp.t{t}.fx", f"Track {t} FX", 0, 1, 0.0, unit="%"))
    a(Param("lp.in", "Input level", 0, 2, 1.0, unit="%"))
    a(Param("lp.mon", "Hear input", 0, 1, 1.0, unit="%"))
    a(Param("lp.vol", "Looper level", 0, 1.5, 1.0, unit="%"))
    a(Param("lp.fb", "Overdub keep", 0.3, 1, 1.0, unit="%"))
    a(Param("lp.filter", "Loop filter", -1, 1, 0.0, unit="bip"))
    a(Param("lp.duck", "Duck loops", 0, 1, 0.0, unit="%"))
    # ---- beats (v1.8)
    a(Param("bt.busy", "Random hits", -1, 1, 0.0, unit="+-%"))
    a(Param("bt.var", "Variation", 0, 1, 0.2, unit="%"))
    a(Param("bt.swing", "Swing", 50, 75, 50, unit="sw"))
    a(Param("bt.human", "Humanize", 0, 1, 0.3, unit="%"))
    a(Param("dr.filter", "Drum filter", 200, 20000, 20000, "exp", unit="Hz"))
    a(Param("dr.drive", "Drum drive", 0, 1, 0.0, unit="%"))
    # v2.1: the drum bus (SOUNDS > DRUMS > BUS). Each genre sets these when it loads its kit.
    a(Param("dr.comp", "Punch", 0, 1, 0.35, unit="%"))          # parallel compression: thicker, punchier
    a(Param("dr.room", "Room", 0, 1, 0.12, unit="%"))           # a short room on the whole kit
    a(Param("dr.roomsize", "Room size", 0, 1, 0.3, unit="%"))
    a(Param("dr.width", "Width", 0, 1, 0.7, unit="%"))          # spreads hats, toms and percussion like a real kit
    a(Param("dr.tone", "Tone", -1, 1, 0.0, unit="tilt"))        # darker <-> brighter
    a(Param("dr.crush", "Crush", 0, 1, 0.0, unit="%"))          # fewer bits and a lower sample rate (SP-1200 style)
    a(Param("dr.kittune", "Kit tune", -12, 12, 0, step=1, unit="st"))
    a(Param("dr.vol", "Drums volume", 0, 1, 0.8, unit="%"))
    a(Param("m.master", "Master", 0, 1, 0.8, unit="%"))
    a(Param("m.drive", "Master drive", 0, 1, 0.0, unit="%"))
    for pre, name in (("s1", "Synth 1"), ("s2", "Synth 2")):
        a(Param(f"{pre}.mute", f"{name} mute", 0, 1, 0, step=1, choices=["Off", "On"]))
        a(Param(f"{pre}.solo", f"{name} solo", 0, 1, 0, step=1, choices=["Off", "On"]))
    a(Param("dr.mute", "Drums mute", 0, 1, 0, step=1, choices=["Off", "On"]))
    a(Param("dr.solo", "Drums solo", 0, 1, 0, step=1, choices=["Off", "On"]))
    a(Param("fx.s1", "Delay: Synth 1", 0, 1, 0.0, unit="%"))
    a(Param("fx.s2", "Delay: Synth 2", 0, 1, 0.2, unit="%"))
    a(Param("fx.dr", "Delay: Drums", 0, 1, 0.0, unit="%"))
    a(Param("fx.time", "Delay time", 0, len(DIVISIONS) - 1, 3, step=1, choices=[d[0] for d in DIVISIONS]))
    a(Param("fx.fb", "Delay repeats", 0, 0.9, 0.4, unit="%"))
    a(Param("fx.tone", "Delay tone", 500, 12000, 3000, "exp", unit="Hz"))
    a(Param("rv.s1", "Reverb: Synth 1", 0, 1, 0.0, unit="%"))
    a(Param("rv.s2", "Reverb: Synth 2", 0, 1, 0.15, unit="%"))
    a(Param("rv.dr", "Reverb: Drums", 0, 1, 0.0, unit="%"))
    a(Param("rv.size", "Reverb size", 0, 1, 0.5, unit="%"))
    a(Param("rv.tone", "Reverb tone", 1000, 14000, 6000, "exp", unit="Hz"))
    a(Param("rv.level", "Reverb level", 0, 1, 0.8, unit="%"))
    a(Param("m.filter", "DJ filter", -1, 1, 0.0, unit="bip"))
    a(Param("m.crush", "Lo-fi crush", 0, 1, 0.0, unit="%"))
    a(Param("m.chorus", "Chorus", 0, 1, 0.0, unit="%"))
    a(Param("m.phaser", "Phaser", 0, 1, 0.0, unit="%"))
    a(Param("m.distortion", "Distortion", 0, 1, 0.0, unit="%"))
    a(Param("m.limiter", "Limiter", 0, 1, 0.0, unit="%"))
    a(Param("m.flanger", "Flanger", 0, 1, 0.0, unit="%"))
    a(Param("m.compressor", "Compressor", 0, 1, 0.0, unit="%"))
    for i, mc in enumerate(MACROS):
        a(Param(f"mc.{i+1}", mc[0], 0, 1, 0.5 if mc[2] == "bip" else 0.0, unit="djm" if mc[2] == "bip" else "%"))
    return {p.key: p for p in S}


SPECS = _build_specs()

PAGES = collections.OrderedDict([
    # v2.0: JAM > KNOBS shows what the BeatStep knobs do on JAM > PROJECTS too (the same 16)
    ("Perform", ["s1.cutoff", "s1.reso", "s1.envamt", "s1.drive", "s2.cutoff", "s2.pos", "s2.envamt", "s2.decay",
                 "dr.p1.tune", "dr.p3.tune", "dr.filter", "dr.drive", "fx.s2", "rv.s2", "m.crush", "m.master"]),
    ("Projects", ["s1.cutoff", "s1.reso", "s1.envamt", "s1.drive", "s2.cutoff", "s2.pos", "s2.envamt", "s2.decay",
                  "dr.p1.tune", "dr.p3.tune", "dr.filter", "dr.drive", "fx.s2", "rv.s2", "m.crush", "m.master"]),
    ("Beats", ["bt.busy", "bt.var", "bt.swing", "bt.human", "dr.vol", "dr.filter", "dr.drive", "rv.dr",
               "dr.p1.level", "dr.p2.level", "dr.p3.level", "dr.p4.level", "dr.p5.level", "dr.p6.level",
               "dr.p13.level", "dr.p1.tune"]),
    ("Live", ["sc.morph", "m.filter", "mc.12", "mc.9", "mc.10", "mc.13", "m.glue", "m.master",
              "s1.cutoff", "s1.reso", "s2.cutoff", "s2.pos", "dk.s1", "dk.s2", "fx.fb", "rv.size"]),
    ("Loop", ["lp.t1.vol", "lp.t2.vol", "lp.t3.vol", "lp.t4.vol", "lp.t5.vol", "lp.in", "lp.mon", "lp.vol",
              "lp.t1.fx", "lp.t2.fx", "lp.t3.fx", "lp.t4.fx", "lp.t5.fx", "lp.fb", "lp.filter", "lp.duck"]),
    ("Macros", [f"mc.{i}" for i in range(1, 17)]),
    ("Synth 1", ["s1.cutoff", "s1.reso", "s1.envamt", "s1.fdecay", "s1.wave", "s1.pw", "s1.detune", "s1.sub",
                 "s1.attack", "s1.decay", "s1.sustain", "s1.release", "s1.glide", "s1.octave", "s1.drive", "s1.vol"]),
    # v2.0: the knobs under each synth's sound browser (BeatStep knobs 1-16 there): the moves that matter most
    ("Synth 1 Quick", ["s1.cutoff", "s1.reso", "s1.envamt", "s1.fdecay", "s1.attack", "s1.decay", "s1.sustain",
                       "s1.release", "s1.unidet", "s1.fdrive", "s1.distamt", "s1.sfxamt", "s1.glide", "fx.s1", "rv.s1",
                       "s1.vol"]),
    ("Synth 2 Quick", ["s2.pos", "s2.posenv", "s2.cutoff", "s2.reso", "s2.envamt", "s2.attack", "s2.decay",
                       "s2.release", "s2.detune", "s2.warpamt", "s2.distamt", "s2.sfxamt", "s2.lfoamt", "fx.s2", "rv.s2",
                       "s2.vol"]),
    ("Synth 1 Osc+", ["s1.osc2", "s1.fm", "s1.ring", "s1.sync", "s1.noise", "s1.ftype", "s1.keytrk", "s1.velamp",
                      "s1.chord", "s1.voicing", "s1.hkey", "s1.hscale", "s1.lane", "s1.penv", "s1.pdec", "s1.glmode"]),
    ("Synth 1 Uni+FX", ["s1.uni", "s1.unidet", "s1.uniwid", "s1.supersaw", "s1.fdrive", "s1.drive", "s1.dist",
                        "s1.distamt", "s1.sfx", "s1.sfxamt", "s1.cutoff", "s1.reso", "s1.ftype", "s1.sub", "s1.subtype",
                        "s1.vol"]),
    ("Synth 1 Mod", ["s1.l1shape", "s1.l1rate", "s1.l1sync", "s1.l2shape", "s1.l2rate", "s1.l2sync", "s1.mea", "s1.med"]
                    + [f"s1.m{j}amt" for j in range(1, 9)]),
    ("Synth 1 Mod 2", [f"s1.m{j}amt" for j in range(9, 13)] + ["s1.l1shape", "s1.l1rate", "s1.l1sync", "s1.mea",
                      "s1.l2shape", "s1.l2rate", "s1.l2sync", "s1.med", "s1.keytrk", "s1.velamp", "s1.drift", "s1.pan"]),
    ("Synth 2", ["s2.pos", "s2.posenv", "s2.lforate", "s2.lfoamt", "s2.cutoff", "s2.reso", "s2.envamt", "s2.table",
                 "s2.attack", "s2.decay", "s2.sustain", "s2.release", "s2.glide", "s2.octave", "s2.detune", "s2.vol"]),
    ("Synth 2 Osc+", ["s2.chord", "s2.voicing", "s2.sub", "s2.noise", "s2.pan", "s2.drift", "s2.penv", "s2.pdec",
                      "s2.ftype", "s2.keytrk", "s2.velamp", "s2.glmode", "s2.hkey", "s2.hscale", "s2.lane", "s2.vol"]),
    ("Synth 2 Uni+FX", ["s2.uni", "s2.detune", "s2.uniwid", "s2.sub", "s2.warp", "s2.warpamt", "s2.table", "s2.pos",
                        "s2.fdrive", "s2.dist", "s2.distamt", "s2.sfx", "s2.sfxamt", "s2.cutoff", "s2.reso", "s2.vol"]),
    ("Synth 2 Mod", ["s2.l1shape", "s2.l1rate", "s2.l1sync", "s2.l2shape", "s2.l2rate", "s2.l2sync", "s2.mea", "s2.med"]
                    + [f"s2.m{j}amt" for j in range(1, 9)]),
    ("Synth 2 Mod 2", [f"s2.m{j}amt" for j in range(9, 13)] + ["s2.l1shape", "s2.l1rate", "s2.l1sync", "s2.mea",
                      "s2.l2shape", "s2.l2rate", "s2.l2sync", "s2.med", "s2.keytrk", "s2.velamp", "s2.drift", "s2.pan"]),
    ("Synth 1 Arp", ["s1.arp", "s1.arprate", "s1.arpoct", "s1.arpgate", "s1.arpswing", "s1.arphold", "s1.arpchance",
                     "s1.arpacc", "dk.s1", "eq.s1.lo", "eq.s1.mid", "eq.s1.hi", "s1.pan", "fx.s1", "rv.s1", "s1.vol"]),
    ("Synth 1 Env", ["s1.attack", "s1.decay", "s1.sustain", "s1.release", "s1.decay2", "s1.sustain2", "s1.fdecay", "s1.envamt",
                    "s1.mea", "s1.med", "s1.penv", "s1.pdec", "s1.glide", "s1.glmode", "s1.velamp", "s1.trim"]),
    ("Synth 1 LFO1 Steps", [f"s1.l1step{i}" for i in range(16)]),
    ("Synth 1 LFO2 Steps", [f"s1.l2step{i}" for i in range(16)]),
    ("Synth 2 Arp", ["s2.arp", "s2.arprate", "s2.arpoct", "s2.arpgate", "s2.arpswing", "s2.arphold", "s2.arpchance",
                     "s2.arpacc", "dk.s2", "eq.s2.lo", "eq.s2.mid", "eq.s2.hi", "s2.pan", "fx.s2", "rv.s2", "s2.vol"]),
    ("Synth 2 Env", ["s2.attack", "s2.decay", "s2.sustain", "s2.release", "s2.decay2", "s2.sustain2", "s2.posenv", "s2.envamt",
                    "s2.mea", "s2.med", "s2.penv", "s2.pdec", "s2.glide", "s2.glmode", "s2.velamp", "s2.trim"]),
    ("Synth 2 LFO1 Steps", [f"s2.l1step{i}" for i in range(16)]),
    ("Synth 2 LFO2 Steps", [f"s2.l2step{i}" for i in range(16)]),
    ("Drums", [f"dr.p{i}.tune" for i in range(1, 9)] + [f"dr.p{i}.decay" for i in range(1, 9)]),
    # v2.1: the drum bus
    ("Drums Bus", ["dr.comp", "dr.room", "dr.roomsize", "dr.width", "dr.tone", "dr.drive", "dr.crush", "dr.filter",
                   "dr.kittune", "dr.p1.level", "dr.p3.level", "dr.p4.level", "dr.p5.level", "fx.dr", "rv.dr", "dr.vol"]),
    ("Drums 1-8", [f"dr.p{i}.tune" for i in range(1, 9)] + [f"dr.p{i}.decay" for i in range(1, 9)]),
    ("Drums 1-8 Mix", [f"dr.p{i}.level" for i in range(1, 9)] + [f"dr.p{i}.pan" for i in range(1, 9)]),
    ("Drums 1-8 Groove", [f"dr.p{i}.chance" for i in range(1, 9)] + [f"dr.p{i}.cond" for i in range(1, 9)]),
    ("Drums 9-16", [f"dr.p{i}.tune" for i in range(9, 17)] + [f"dr.p{i}.decay" for i in range(9, 17)]),
    ("Drums 9-16 Mix", [f"dr.p{i}.level" for i in range(9, 17)] + [f"dr.p{i}.pan" for i in range(9, 17)]),
    ("Drums 9-16 Groove", [f"dr.p{i}.chance" for i in range(9, 17)] + [f"dr.p{i}.cond" for i in range(9, 17)]),
    ("Drums Choke", [f"dr.p{i}.choke" for i in range(1, 17)]),
    # v2.0: CAPTURE > STEMS. While you bounce, the BeatStep knobs ride the levels and sends
    ("Capture", ["s1.vol", "s2.vol", "dr.vol", "lp.vol", "fx.s1", "fx.s2", "fx.dr", "m.master",
                 "s1.cutoff", "s2.cutoff", "dr.filter", "m.filter", "rv.s1", "rv.s2", "rv.dr", "m.crush"]),
    ("Mix", ["s1.vol", "s2.vol", "dr.vol", "m.master", "dr.filter", "dr.drive", "m.drive", "m.filter",
             "dk.s1", "dk.s2", "dk.fx", "dk.src", "dk.rel", "m.glue", "m.gluespd", "m.width"]),
    ("Mix EQ", ["eq.s1.lo", "eq.s1.mid", "eq.s1.hi", "eq.s2.lo", "eq.s2.mid", "eq.s2.hi", "eq.lof", "eq.hif",
                "eq.dr.lo", "eq.dr.mid", "eq.dr.hi", "eq.m.lo", "eq.m.mid", "eq.m.hi", "s1.pan", "s2.pan"]),
    ("Arrangement", ["s1.vol", "s2.vol", "dr.vol", "lp.vol", "fx.s1", "fx.s2", "fx.dr", "m.master",
                     "s1.cutoff", "s2.cutoff", "dr.filter", "m.filter", "rv.s1", "rv.s2", "rv.dr", "m.drive"]),
    ("Track Mute/Solo", ["s1.mute", "s2.mute", "dr.mute", "s1.solo", "s2.solo", "dr.solo", "lp.vol", "m.master",
                        "s1.vol", "s2.vol", "dr.vol", "s1.pan", "s2.pan", "m.width", "m.glue", "m.drive"]),
    ("FX", ["fx.s1", "fx.s2", "fx.dr", "fx.time", "fx.fb", "fx.tone", "m.filter", "m.crush",
            "rv.s1", "rv.s2", "rv.dr", "rv.size", "rv.tone", "rv.level", "dr.filter", "m.limiter"]),
    ("Master FX", ["m.chorus", "m.flanger", "m.phaser", "m.distortion", "m.limiter", "m.compressor", "m.drive", "m.filter",
                   "m.crush", "m.glue", "m.gluespd", "m.width", "m.master", "rv.level", "rv.size", "rv.tone"]),
])

from potentialbox.presets import PRESETS, PRESET_CAT, PRESET_CATS  # noqa: E402  (v2.0: its own file)


# tab -> [(sub-page button, page)]; tapping a tab again goes to its next sub-page
SUBPAGES = {
    "Synth 1": [("Main", "Synth 1"), ("Osc+", "Synth 1 Osc+"), ("Uni+FX", "Synth 1 Uni+FX"), ("Mod", "Synth 1 Mod"), ("Mod2", "Synth 1 Mod 2"), ("Arp+", "Synth 1 Arp"), ("Env", "Synth 1 Env"),
                ("LFO1 Steps", "Synth 1 LFO1 Steps"), ("LFO2 Steps", "Synth 1 LFO2 Steps")],
    "Synth 2": [("Main", "Synth 2"), ("Osc+", "Synth 2 Osc+"), ("Uni+FX", "Synth 2 Uni+FX"), ("Mod", "Synth 2 Mod"), ("Mod2", "Synth 2 Mod 2"), ("Arp+", "Synth 2 Arp"), ("Env", "Synth 2 Env"),
                ("LFO1 Steps", "Synth 2 LFO1 Steps"), ("LFO2 Steps", "Synth 2 LFO2 Steps")],
    # v2.0: one Drums tab for all 16 pads
    "Drums": [("Bus", "Drums Bus"), ("Tune 1-8", "Drums 1-8"), ("Tune 9-16", "Drums 9-16"), ("Mix 1-8", "Drums 1-8 Mix"),
              ("Mix 9-16", "Drums 9-16 Mix"), ("Groove 1-8", "Drums 1-8 Groove"), ("Groove 9-16", "Drums 9-16 Groove"),
              ("Choke", "Drums Choke")],
    "Mix": [("Main", "Mix"), ("EQ", "Mix EQ"), ("Mute/Solo", "Track Mute/Solo")],
    "FX": [("Sends", "FX"), ("Master", "Master FX")],
}
HIDDEN_PAGES = {p for subs in SUBPAGES.values() for _, p in subs[1:]}
NOT_LOCKABLE = ("mc.", "sc.", "m.master")


class ParamStore:
    """Holds every parameter as a normalized 0..1 value plus a cached real value."""

    # norm = your setting (0..1), mod = what the macros add on top, val = the real value the
    # engine plays (setting + macros). Presets, saves and the knob pages work on norm.
    def __init__(self):
        self.norm = {}
        self.val = {}
        self.mod = {}
        # step locks: {key: {step 0-15: norm}}. While lock_step is set (the GUI's lock mode), knob moves
        # are stored as locks for that step instead of changing your setting.
        self.locks = {}
        self.lock_step = None
        self._locked_now = set()
        self._undo = []
        self._redo = []
        self._undoing = False
        self._last_change = 0.0
        # scenes: two snapshots of every setting; the Scene morph knob blends the ones that differ
        self.scenes = {str(i): None for i in range(1, 9)}
        self.scene_keys = []
        for k, p in SPECS.items():
            self.set_val(k, p.default)

    @staticmethod
    def lockable(key):
        return not key.startswith(NOT_LOCKABLE)

    def cur_norm(self, key):
        """What the knob shows: the lock for the selected step in lock mode, otherwise your setting."""
        if self.lock_step is not None:
            d = self.locks.get(key)
            if d and self.lock_step in d:
                return d[self.lock_step]
        return self.norm[key]

    def apply_step(self, step):
        """Audio thread, at each new 16th step while the BeatStep plays (None = stopped)."""
        now = set()
        if step is not None:
            for key, d in list(self.locks.items()):
                n = d.get(step)
                if n is not None:
                    self.val[key] = SPECS[key].to_val(min(max(n + self.mod.get(key, 0.0), 0.0), 1.0))
                    now.add(key)
        for key in self._locked_now - now:
            if key in self.norm:
                self._apply(key)
        self._locked_now = now

    def clear_locks(self, keys=None, step=None):
        for key in list(self.locks) if keys is None else [k for k in keys if k in self.locks]:
            if step is None:
                self.locks.pop(key, None)
            else:
                self.locks[key].pop(step, None)
                if not self.locks[key]:
                    self.locks.pop(key)
            if key in self.norm:
                self._apply(key)

    def save_scene(self, slot):
        slot = str(slot)
        self.scenes[slot] = {k: n for k, n in self.norm.items() if self.lockable(k)}
        self._scene_keys()

    def scene_pair(self):
        """The two scene slots the morph goes between ("1".."8")."""
        return str(int(round(self.val.get("sc.src", 1)))), str(int(round(self.val.get("sc.dst", 2))))

    def _scene_keys(self):
        src, dst = self.scene_pair()
        A, B = self.scenes.get(src), self.scenes.get(dst)
        self.scene_keys = [k for k in A if k in B and k in self.norm and abs(A[k] - B[k]) > 1e-6] if A and B else []

    def apply_morph(self):
        src, dst = self.scene_pair()
        A, B = self.scenes.get(src), self.scenes.get(dst)
        if not (A and B):
            return
        x = self.norm["sc.morph"]
        for k in self.scene_keys:
            self.norm[k] = A[k] + (B[k] - A[k]) * x
            self._apply(k)

    def shown(self, key):
        return min(max(self.norm[key] + self.mod.get(key, 0.0), 0.0), 1.0)

    def base_val(self, key):
        return SPECS[key].to_val(self.norm[key])

    def _apply(self, key):
        self.val[key] = SPECS[key].to_val(self.shown(key))

    def set_norm(self, key, n):
        n = min(max(float(n), 0.0), 1.0)
        if self.lock_step is not None and self.lockable(key):
            self.locks.setdefault(key, {})[self.lock_step] = n
            self.val[key] = SPECS[key].to_val(min(max(n + self.mod.get(key, 0.0), 0.0), 1.0))  # hear it
            return
        if not self._undoing and key in self.norm and abs(self.norm[key] - n) > 1e-9 and not key.startswith("sc."):
            # one undo step per gesture: a knob turn, a sound load or a scene load is a burst of changes,
            # so only the first change after a 0.6 s pause takes a snapshot
            now = time.monotonic()
            if now - self._last_change > 0.6:
                self._undo.append(dict(self.norm))
                if len(self._undo) > 50:
                    self._undo.pop(0)
                self._redo.clear()
            self._last_change = now
        self.norm[key] = n
        self._apply(key)
        if key.startswith("mc."):
            self.recompute_macros()
        elif key == "sc.morph":
            self.apply_morph()
        elif key in ("sc.src", "sc.dst"):
            self._scene_keys()

    def undo(self):
        if not self._undo:
            return False
        self._undoing = True
        self._last_change = 0.0
        self._redo.append(dict(self.norm))
        snap = self._undo.pop()
        self.norm.clear()
        self.norm.update(snap)
        for k in list(self.norm):
            self._apply(k)
        self.recompute_macros()
        self._undoing = False
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undoing = True
        self._last_change = 0.0
        self._undo.append(dict(self.norm))
        snap = self._redo.pop()
        self.norm.clear()
        self.norm.update(snap)
        for k in list(self.norm):
            self._apply(k)
        self.recompute_macros()
        self._undoing = False
        return True

    def recompute_macros(self):
        mod = {}
        for i, (name, desc, mode, targets) in enumerate(MACROS):
            m = self.norm.get(f"mc.{i+1}")
            if m is None:
                continue
            for key, amt, shape in targets:
                mod[key] = mod.get(key, 0.0) + amt * _shape(shape, m)
        old = set(self.mod)
        self.mod = {k: v for k, v in mod.items() if abs(v) > 1e-9}
        for key in old | set(self.mod):
            if key in self.norm:
                self._apply(key)

    def set_val(self, key, v):
        self.set_norm(key, SPECS[key].to_norm(v))

    def nudge(self, key, direction):
        p = SPECS[key]
        base = self.cur_norm(key)
        if p.step:
            self.set_val(key, p.to_val(base) + direction * p.step)
        else:
            self.set_norm(key, base + direction / 20.0)

    def apply_preset(self, pre, values):
        ls, self.lock_step = self.lock_step, None  # loading a sound never writes step locks
        try:
            self._apply_preset(pre, values)
        finally:
            self.lock_step = ls

    def _apply_preset(self, pre, values):
        for k, p in SPECS.items():
            if k.startswith(pre + ".") and not k.endswith(".vol"):
                self.set_val(k, p.default)
        for k, v in values.items():
            self.set_val(f"{pre}.{k}", v)

    def randomize(self, pre, rng=None):
        ls, self.lock_step = self.lock_step, None
        try:
            self._randomize(pre, rng)
        finally:
            self.lock_step = ls

    def _randomize(self, pre, rng=None):
        rng = rng or np.random.default_rng()
        self.set_val(pre + ".trim", 0.0)   # a random sound starts at its natural level, not the last preset's
        for k in PAGES["Synth 1" if pre == "s1" else "Synth 2"]:
            if not k.endswith(".vol") and not k.endswith(".octave"):
                self.set_norm(k, rng.random())
        # keep it playable: short-ish attack, audible cutoff
        self.set_norm(pre + ".attack", rng.random() * 0.4)
        self.set_norm(pre + ".cutoff", 0.35 + rng.random() * 0.6)
        self.set_norm(pre + ".sustain", 0.3 + rng.random() * 0.7)


# ----------------------------------------------------------------------------- DSP helpers
def lp_coeffs(fc, q, sr):
    fc = min(max(fc, 20.0), 0.45 * sr)
    w0 = TWO_PI * fc / sr
    alpha = math.sin(w0) / (2.0 * q)
    c = math.cos(w0)
    a0 = 1.0 + alpha
    return [(1 - c) / 2 / a0, (1 - c) / a0, (1 - c) / 2 / a0, 1.0, -2 * c / a0, (1 - alpha) / a0]


def polyblep(t, dt):
    out = np.zeros_like(t)
    m = t < dt
    if m.any():
        x = t[m] / dt[m]
        out[m] = x + x - x * x - 1.0
    m = t > 1.0 - dt
    if m.any():
        x = (t[m] - 1.0) / dt[m]
        out[m] = x * x + x + x + 1.0
    return out


class ADSR:
    """Attack -> decay -> sustain (optionally decay 2 -> sustain 2) -> release.
    Every stage starts from the level the last one reached, so nothing ever jumps (no clicks)."""
    IDLE, ATTACK, DECAY, DECAY2, RELEASE = 0, 1, 2, 3, 5

    def __init__(self, sr):
        self.sr = sr
        self.v = 0.0
        self.t = 0
        self.stage = 0

    def held(self):
        """True while the key is down (attack, decay or sustain)."""
        return self.stage in (1, 2, 3)

    def gate_on(self):
        self.stage = 1
        self.t = 0

    def gate_off(self):
        if self.stage:
            self.stage = 5
            self.t = 0

    def render(self, n, a, d, s, r, d2=None, s2=None):
        out = np.empty(n)
        i, sr = 0, self.sr
        multi = d2 is not None and d2 > 1e-3
        while i < n:
            st = self.stage
            if st == 0:
                out[i:] = 0.0
                self.v = 0.0
                break
            if st == 1:  # linear attack up to 1
                inc = 1.0 / max(a * sr, 1.0)
                m = min(int(math.ceil((1.0 - self.v) / inc)), n - i)
                if m <= 0:
                    self.v, self.stage, self.t = 1.0, 2, 0
                    continue
                seg = np.minimum(self.v + inc * np.arange(1, m + 1), 1.0)
                out[i:i + m] = seg
                self.v = float(seg[-1])
                i += m
                if self.v >= 1.0 - 1e-9:
                    self.v, self.stage, self.t = 1.0, 2, 0
            elif st == 2 or st == 3:  # exponential glide towards the sustain level (never jumps)
                if st == 2:
                    tgt, k = s, math.exp(-4.6 / max(d * sr, 1.0))
                    m = n - i
                    if multi:  # after `decay` seconds, decay 2 takes over from wherever the level is
                        m = min(m, max(int(d * sr) - self.t, 0))
                        if m == 0:
                            self.stage, self.t = 3, 0
                            continue
                else:
                    tgt, k = (s2 if multi else s), math.exp(-4.6 / max((d2 if multi else d) * sr, 1.0))
                    m = n - i
                seg = tgt + (self.v - tgt) * k ** np.arange(1, m + 1)
                out[i:i + m] = seg
                self.v = float(seg[-1])
                self.t += m
                i += m
            else:  # release
                k = math.exp(-4.6 / max(r * sr, 1.0))
                seg = self.v * k ** np.arange(1, n - i + 1)
                out[i:] = seg
                self.v = float(seg[-1])
                if self.v < 1e-5:
                    self.v, self.stage, self.t = 0.0, 0, 0
                break
        return out


class LFO:
    """Free-running LFO. Random shapes pick a new value every cycle (Random) or glide between them (Smooth)."""

    def __init__(self, seed):
        self.ph = 0.0
        self.rng = np.random.default_rng(seed)
        self.a = float(self.rng.uniform(-1, 1))
        self.b = float(self.rng.uniform(-1, 1))

    def render(self, n, sr, hz, shape):
        ph = self.ph + np.arange(1, n + 1) * (hz / sr)
        t = ph % 1.0
        if shape == 0:
            out = np.sin(TWO_PI * t)
        elif shape == 1:
            out = 1.0 - 4.0 * np.abs(t - 0.5)
        elif shape == 2:
            out = 2.0 * t - 1.0
        elif shape == 3:
            out = 1.0 - 2.0 * t
        elif shape == 4:
            out = np.where(t < 0.5, 1.0, -1.0)
        else:
            k = np.floor(ph).astype(np.int64)
            kmax = int(k[-1])
            A = np.empty(kmax + 1)
            Bv = np.empty(kmax + 1)
            A[0], Bv[0] = self.a, self.b
            for j in range(1, kmax + 1):
                A[j] = Bv[j - 1]
                Bv[j] = self.rng.uniform(-1, 1)
            if shape == 5:
                out = A[k]
            else:
                ss = t * t * (3 - 2 * t)
                out = A[k] + (Bv[k] - A[k]) * ss
            self.a, self.b = float(A[kmax]), float(Bv[kmax])
        self.ph = float(ph[-1] % 1.0)
        return out


def _at(m, i):
    return m[i] if isinstance(m, np.ndarray) else m


def _mean(m):
    return float(m.mean()) if isinstance(m, np.ndarray) else float(m)


PASS = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def bp_coeffs(fc, q, sr):
    fc = min(max(fc, 20.0), 0.45 * sr)
    w0 = TWO_PI * fc / sr
    alpha = math.sin(w0) / (2.0 * q)
    c = math.cos(w0)
    a0 = 1.0 + alpha
    return [alpha / a0, 0.0, -alpha / a0, 1.0, -2 * c / a0, (1 - alpha) / a0]


def notch_coeffs(fc, q, sr):
    fc = min(max(fc, 20.0), 0.45 * sr)
    w0 = TWO_PI * fc / sr
    alpha = math.sin(w0) / (2.0 * q)
    c = math.cos(w0)
    a0 = 1.0 + alpha
    return [1 / a0, -2 * c / a0, 1 / a0, 1.0, -2 * c / a0, (1 - alpha) / a0]


def filter_sections(ftype, fc, reso, sr):
    q2 = 0.707 + (reso ** 2) * 11.0
    if ftype == 0:
        return [lp_coeffs(fc, 0.707, sr), lp_coeffs(fc, q2, sr)]
    if ftype == 1:
        return [lp_coeffs(fc, q2, sr), PASS]
    if ftype == 2:
        return [hp_coeffs(fc, q2, sr), PASS]
    if ftype == 3:
        return [bp_coeffs(fc, 0.6 + reso * 6.0, sr), PASS]
    return [notch_coeffs(fc, 0.5 + reso * 4.0, sr), PASS]


class MonoSynth:
    """Mono voice handling shared by both synths, plus the modulation system.
    Tied/slid BeatStep steps arrive as overlapping notes -> legato with glide, no envelope retrigger.
    Chord mode stacks up to 4 oscillator voices on each note through one filter and envelope."""

    SUB = 32
    MAXV = 4

    def __init__(self, eng, pre, channels):
        self.eng, self.pre, self.sr = eng, pre, eng.sr
        self.held = []
        self.cur = self.tgt = 48.0
        self.sliding = False
        self.vel_raw = 0.8
        self.rnd = 0.0
        self.amp = ADSR(self.sr)
        self.fenv = ADSR(self.sr)
        self.menv = ADSR(self.sr)
        self.lfos = [LFO(11 if pre == "s1" else 21), LFO(12 if pre == "s1" else 22)]
        self.rng = np.random.default_rng(31 if pre == "s1" else 41)
        self.channels = channels
        self.zi = np.zeros((2, 2, channels)) if channels > 1 else np.zeros((2, 2))
        self.ftype = 0
        self.reset_extra_filters()
        self.step_val = [0.0, 0.0]
        self.ptime = 10 ** 9
        self.drift_val = np.zeros(self.MAXV)
        self.drift_tgt = self.rng.uniform(-1, 1, self.MAXV)
        self.active = 0.0
        # arpeggiator state (times in samples since the arp started)
        self.arp_phys = []      # notes held on the BeatStep right now
        self.arp_notes = []     # notes the arp plays from (stays after release when Arp hold is on)
        self.arp_running = False
        self.arp_t = 0
        self.arp_next = 0
        self.arp_off = None
        self.arp_k = 0
        self.arp_cur = None
        self.arp_vel = 100
        self.arp_seq = []
        self.arp_last_stop = -10 ** 12
        self.arp_rng = np.random.default_rng(51 if pre == "s1" else 61)
        self.sfx_units = None   # chorus / ensemble / dimension / phaser / flanger, made the first time one is used
        self.lane_deg = None    # chord lane: the scale degree (1-7) of the chord the BeatStep asked for
        self.crush_hold = 0.0

    # ---- notes (the arpeggiator sits in front of the voice)
    def note_on(self, note, vel):
        if self.eng.p.val[self.pre + ".arp"] >= 0.5:
            self._arp_on(note, vel)
        else:
            if self.arp_running:
                self.arp_stop()
            self._play_on(note, vel)

    def note_off(self, note):
        if self.arp_running or note in self.arp_phys:
            self._arp_off(note)
        else:
            self._play_off(note)

    def _arp_on(self, note, vel):
        hold = self.eng.p.val[self.pre + ".arphold"] >= 0.5
        if not self.arp_phys:  # first key of a new phrase
            if hold or not self.arp_running:
                self.arp_notes = []
        if note not in self.arp_phys:
            self.arp_phys.append(note)
        if note not in self.arp_notes:
            self.arp_notes.append(note)
        if not self.arp_running:
            self.arp_running = True
            self.arp_t = 0
            self.arp_next = 0
            self.arp_off = None
            # short BeatStep steps restart the arp on every step: carry on through the pattern instead
            if self.eng.samples - self.arp_last_stop > 2 * self.step_len():
                self.arp_k = 0
            self.arp_vel = vel

    def _arp_off(self, note):
        if note in self.arp_phys:
            self.arp_phys.remove(note)
        hold = self.eng.p.val[self.pre + ".arphold"] >= 0.5
        if not hold and note in self.arp_notes:
            self.arp_notes.remove(note)
        if not self.arp_notes:
            self.arp_stop()

    def arp_stop(self):
        if self.arp_running:
            self.arp_last_stop = self.eng.samples
        if self.arp_cur is not None:
            self._play_off(self.arp_cur)
        self.arp_cur = None
        self.arp_running = False
        self.arp_notes = []
        self.arp_phys = []

    def arp_pool(self):
        v = self.eng.p.val
        pre = self.pre
        ci = int(v[pre + ".chord"])
        base = []
        for nt in self.arp_notes:
            ints = CHORDS[ci][1]
            if ints is None:
                size = {"Scale triad": 3, "Scale 7th": 4, "Scale 9th": 5}[CHORDS[ci][0]]
                key, scale = int(v[pre + ".hkey"]), HARM_SCALE_NAMES[int(v[pre + ".hscale"])]
                if v[pre + ".lane"] >= 0.5 and self.lane_deg:
                    ints = lane_chord(nt, key, scale, self.lane_deg, size)
                else:
                    ints = scale_chord(nt, key, scale, size)
            for iv in ints:
                if nt + iv not in base:
                    base.append(nt + iv)
        octs = int(v[pre + ".arpoct"]) + 1
        mode = ARP_MODES[int(v[pre + ".arp"])]
        if mode != "As played":
            base = sorted(base)
        pool = [nt + 12 * o for o in range(octs) for nt in base]
        if mode == "Down":
            pool = pool[::-1]
        elif mode == "Up-down" and len(pool) > 2:
            pool = pool + pool[-2:0:-1]
        return pool, mode

    def step_len(self):
        ticks = ARP_RATES[int(self.eng.p.val[self.pre + ".arprate"])][1]
        return ticks / 24.0 * 60.0 / max(self.eng.bpm, 30.0) * self.sr

    def arp_events(self):
        """Run every arp event due at the current arp time."""
        v = self.eng.p.val
        pre = self.pre
        if v[pre + ".arp"] < 0.5:
            self.arp_stop()
            return
        if self.arp_off is not None and self.arp_t >= self.arp_off:
            if self.arp_cur is not None:
                self._play_off(self.arp_cur)
                self.arp_cur = None
            self.arp_off = None
        if self.arp_t >= self.arp_next:
            L = self.step_len()
            pool, mode = self.arp_pool()
            k = self.arp_k
            if pool and self.arp_rng.random() <= v[pre + ".arpchance"] + 1e-9:
                nt = pool[int(self.arp_rng.integers(len(pool)))] if mode == "Random" else pool[k % len(pool)]
                acc = int(v[pre + ".arpacc"])
                vel = self.arp_vel
                if acc:
                    vel = min(127, vel + 30) if k % (acc + 1) == 0 else max(1, int(vel * 0.7))
                gate = v[pre + ".arpgate"]
                if gate >= 0.98 and self.arp_cur is not None:  # full gate: slide into the next note
                    old = self.arp_cur
                    self._play_on(nt, vel)
                    if old != nt:
                        self._play_off(old)
                else:
                    if self.arp_cur is not None:
                        self._play_off(self.arp_cur)
                    self._play_on(nt, vel)
                self.arp_cur = nt
                self.arp_off = None if gate >= 0.98 else self.arp_t + max(int(gate * L), 32)
            self.arp_k = k + 1
            swing = v[pre + ".arpswing"]
            nxt = (self.arp_k + (0.5 * swing if self.arp_k % 2 else 0.0)) * L
            # keep timing steady if the tempo changes: schedule from this step, not from zero
            here = (k + (0.5 * swing if k % 2 else 0.0)) * L
            self.arp_next = self.arp_t + max(int(round(nxt - here)), 1)

    def render_block(self, n):
        """render() with arp events placed at their exact sample."""
        if not self.arp_running:
            return self.render(n)
        parts = []
        done = 0
        any_sound = False
        while done < n:
            self.arp_events()
            if not self.arp_running:
                y = self.render(n - done)
                parts.append(y if y is not None else np.zeros((n - done, 2)))
                any_sound = any_sound or y is not None
                break
            due = [t for t in (self.arp_next, self.arp_off) if t is not None]
            m = int(min(n - done, max(1, min(due) - self.arp_t)))
            y = self.render(m)
            if y is not None:
                any_sound = True
            parts.append(y if y is not None else np.zeros((m, 2)))
            self.arp_t += m
            done += m
        return np.concatenate(parts) if any_sound else None

    def _play_on(self, note, vel):
        v = self.eng.p.val
        legato = bool(self.held) and self.amp.held()
        if note in self.held:
            self.held.remove(note)
        self.held.append(note)
        self.tgt = float(note)
        if legato:
            self.sliding = True
        else:
            always = v[self.pre + ".glmode"] >= 0.5 and self.amp.stage != 0
            self.sliding = always
            if not always:
                self.cur = self.tgt
            self.vel_raw = vel / 127.0
            self.rnd = float(self.rng.uniform(-1, 1))
            uph = getattr(self, "uph", None)
            if uph is not None and UNI_COUNTS[int(v[self.pre + ".uni"])] > 1:
                uph[:] = self.rng.random(uph.shape)
            self.ptime = 0
            self.amp.gate_on()
            self.fenv.gate_on()
            self.menv.gate_on()
        self.active = 1.0

    def _play_off(self, note):
        if note in self.held:
            self.held.remove(note)
        if self.held:
            self.tgt = float(self.held[-1])
            self.sliding = True
        else:
            self.amp.gate_off()
            self.fenv.gate_off()
            self.menv.gate_off()

    def all_off(self):
        self.arp_running = False
        self.arp_cur = None
        self.arp_notes = []
        self.arp_phys = []
        self.held = []
        self.amp.gate_off()
        self.fenv.gate_off()
        self.menv.gate_off()

    # ---- pitch
    def pitch(self, n):
        """Semitone array (glide + octave + pitch envelope)."""
        v = self.eng.p.val
        pre = self.pre
        if self.sliding and abs(self.tgt - self.cur) > 1e-4:
            k = math.exp(-3.0 / max(v[pre + ".glide"] * self.sr, 1.0))
            sem = self.tgt + (self.cur - self.tgt) * k ** np.arange(1, n + 1)
            self.cur = float(sem[-1])
        else:
            self.cur = self.tgt
            sem = np.full(n, self.tgt)
        sem = sem + 12.0 * v[pre + ".octave"]
        pe = v[pre + ".penv"]
        if abs(pe) > 0.01 and self.ptime < self.sr * 10:
            tau = max(v[pre + ".pdec"] * self.sr / 3.0, 1.0)
            sem = sem + pe * np.exp(-(self.ptime + np.arange(n)) / tau)
        self.ptime += n
        return sem

    def chord(self):
        if self.arp_running:  # the arp plays the chord one note at a time
            return [0]
        v = self.eng.p.val
        voicing = int(v[self.pre + ".voicing"])
        ci = int(v[self.pre + ".chord"])
        if CHORDS[ci][1] is None:
            size = {"Scale triad": 3, "Scale 7th": 4, "Scale 9th": 5}[CHORDS[ci][0]]
            key, scale = int(v[self.pre + ".hkey"]), HARM_SCALE_NAMES[int(v[self.pre + ".hscale"])]
            if v[self.pre + ".lane"] >= 0.5 and self.lane_deg:
                return lane_chord(self.tgt, key, scale, self.lane_deg, min(size, self.MAXV), voicing)
            return scale_chord(self.tgt, key, scale, size, voicing)[: self.MAXV]
        ints = list(CHORDS[ci][1])
        if voicing >= 1 and len(ints) >= 3:
            ints[1] += 12
        if voicing >= 2 and len(ints) >= 4:
            ints[3] += 12
        return ints[: self.MAXV]

    def drift(self, n):
        amt = self.eng.p.val[self.pre + ".drift"]
        if amt <= 0.001:
            return np.zeros(self.MAXV)
        step = min(1.0, n / self.sr * 1.5)
        self.drift_val += (self.drift_tgt - self.drift_val) * step
        done = np.abs(self.drift_tgt - self.drift_val) < 0.05
        if done.any():
            self.drift_tgt[done] = self.rng.uniform(-1, 1, int(done.sum()))
        return self.drift_val * (amt * 0.3)  # up to +-30 cents

    # ---- modulation
    def lfo_hz(self, L):
        v = self.eng.p.val
        beats = LFO_SYNC[int(v[f"{self.pre}.l{L}sync"])][1]
        if beats is None:
            return v[f"{self.pre}.l{L}rate"]
        return self.eng.bpm / 60.0 / beats

    def modulation(self, n, ae, me):
        """Sum of the 8 mod slots, per destination name (arrays or numbers in -1..1 per unit of amount)."""
        v = self.eng.p.val
        pre = self.pre
        lfo = [None, None]
        out = {}
        for j in range(1, 13):
            amt = v[f"{pre}.m{j}amt"]
            si = int(v[f"{pre}.m{j}src"])
            if si == 0 or abs(amt) < 1e-4:
                continue
            name = MOD_SOURCES[si]
            if name.startswith("LFO"):
                L = int(name[-1]) - 1
                sh = int(v[f"{pre}.l{L+1}shape"])
                if sh == STEP_SHAPE:
                    if lfo[L] is None:
                        lfo[L] = self.step_lfo(L, n)
                    s = lfo[L]
                else:
                    if lfo[L] is None:
                        lfo[L] = self.lfos[L].render(n, self.sr, self.lfo_hz(L + 1), sh)
                    s = lfo[L]
            elif name == "Mod env":
                s = me
            elif name == "Amp env":
                s = ae
            elif name == "Velocity":
                s = self.vel_raw * 2.0 - 1.0
            elif name == "Note":
                s = max(-1.0, min(1.0, (self.cur - 60.0) / 24.0))
            else:
                s = self.rnd
            dst = MOD_DESTS[pre][int(v[f"{pre}.m{j}dst"])]
            out[dst] = out.get(dst, 0.0) + amt * s
        for L in (0, 1):  # keep unused LFOs running so their timing stays steady
            if lfo[L] is None:
                self.lfos[L].ph = (self.lfos[L].ph + n * self.lfo_hz(L + 1) / self.sr) % 1.0
        return out

    def step_lfo(self, L, n):
        """Step LFO: the 16 step knobs, one per 16th. Follows the BeatStep's steps while it plays and the
        LFO's own speed/sync when it's stopped. Each change glides over ~3 ms so steps don't click."""
        v = self.eng.p.val
        step = self.eng.step
        if step is None:
            self.lfos[L].ph = (self.lfos[L].ph + n * self.lfo_hz(L + 1) / self.sr) % 1.0
            step = int(self.lfos[L].ph * 16) % 16
        tgt = v[f"{self.pre}.l{L + 1}step{step % 16}"]
        prev = self.step_val[L]
        m = max(1, int(0.003 * self.sr))
        out = np.full(n, tgt, dtype=float)
        k = min(m, n)
        out[:k] = prev + (tgt - prev) * (np.arange(1, k + 1) / m)
        self.step_val[L] = float(out[-1])
        return out

    def filt(self, x, fe, mods):
        v = self.eng.p.val
        pre = self.pre
        ftype = int(v[pre + ".ftype"])
        if ftype != self.ftype:
            self.zi = np.zeros_like(self.zi)
            self.ftype = ftype
            self.reset_extra_filters()
        reso0 = v[pre + ".reso"]
        base = v[pre + ".cutoff"] * 2.0 ** ((self.cur - 60.0) / 12.0 * v[pre + ".keytrk"])
        amt = v[pre + ".envamt"] * 7.0
        mc = mods.get("Cutoff", 0.0)
        mr = mods.get("Resonance", 0.0)
        n = len(x)
        # ---- Comb: feedback delay tuned to the cutoff (a metallic resonator) ----
        if ftype == 5:
            fc = base * 2.0 ** (amt * float(fe[n // 2]) + 6.0 * _mean(mc))
            return self.comb(x, fc, reso0 + _mean(mr))
        # ---- Formant: three vowel peaks; the cutoff knob sweeps A > E > I > O > U ----
        if ftype == 6:
            pos = math.log2(max(base, 40.0) / 40.0) / math.log2(16000.0 / 40.0)
            pos = pos + 0.25 * (amt * float(fe[n // 2]) / 7.0 + _mean(mc))
            return self.formant(x, pos, reso0 + _mean(mr))
        # ---- standard SOS filters ----
        y = np.empty_like(x)
        for j in range(0, n, self.SUB):
            e = j + self.SUB
            m = min(j + self.SUB // 2, n - 1)
            fc = base * 2.0 ** (amt * fe[m] + 6.0 * _at(mc, m))
            reso = min(max(reso0 + _at(mr, m), 0.0), 1.0)
            sos = np.array(filter_sections(ftype, fc, reso, self.sr))
            y[j:e], self.zi = sosfilt(sos, x[j:e], axis=0, zi=self.zi)
        if ftype <= 1:
            y = y / (1.0 + 0.6 * reso0)
        elif ftype == 3:
            y = y * 2.5  # band-pass removes most of the energy: make-up gain
        return y

    COMB_LEN = 8192

    def reset_extra_filters(self):
        shape = (self.COMB_LEN,) if self.channels == 1 else (self.COMB_LEN, self.channels)
        self.comb_buf = np.zeros(shape)   # past outputs of the comb (ring buffer)
        self.comb_w = 0
        zshape = (1, 2) if self.channels == 1 else (1, 2, self.channels)
        self.formant_zi = [np.zeros(zshape) for _ in range(3)]

    def comb(self, x, fc, reso):
        """y[i] = x[i] + fb * y[i - D]. Works for mono and stereo and any block size; the delay can
        change between blocks without clearing the buffer (no clicks when notes change)."""
        n = len(x)
        L = self.COMB_LEN
        D = int(min(max(self.sr / max(fc, 30.0), 2), 2000))
        fb = min(max(reso, 0.0), 1.0) * 0.92
        buf, w = self.comb_buf, self.comb_w
        y = np.empty_like(x)
        if D >= 96:  # long delay: whole chunks of D samples at a time
            j = 0
            while j < n:
                m = min(D, n - j)
                idx = (w + j - D + np.arange(m)) % L
                y[j:j + m] = x[j:j + m] + fb * buf[idx]
                buf[(w + j + np.arange(m)) % L] = y[j:j + m]
                j += m
        else:  # short delay: a recursive filter whose state is the last D outputs
            a = np.zeros(D + 1)
            a[0], a[D] = 1.0, -fb
            zi = fb * buf[(w - D + np.arange(D)) % L]
            y, _ = lfilter([1.0], a, x, axis=0, zi=zi)
            buf[(w + np.arange(n)) % L] = y
        self.comb_w = (w + n) % L
        return y * math.sqrt(1.0 - fb)

    def formant(self, x, pos, reso):
        """Three band-pass peaks in parallel. `pos` 0..1 glides smoothly through the vowels."""
        pos = min(max(pos, 0.0), 1.0) * (len(VOWELS) - 1)
        i0 = min(int(pos), len(VOWELS) - 2)
        f = pos - i0
        q = 2.0 + min(max(reso, 0.0), 1.0) * 10.0
        y = np.zeros_like(x)
        for k, g in enumerate((1.0, 0.7, 0.45)):
            fk = VOWELS[i0][k] * (1.0 - f) + VOWELS[i0 + 1][k] * f
            sos = np.array([bp_coeffs(fk, q, self.sr)])
            yk, self.formant_zi[k] = sosfilt(sos, x, axis=0, zi=self.formant_zi[k])
            y += g * yk
        return y * 1.6

    def envs(self, n, fdecay):
        v = self.eng.p.val
        pre = self.pre
        a = v[pre + ".attack"]
        ae = self.amp.render(n, a, v[pre + ".decay"], v[pre + ".sustain"],
                             v[pre + ".release"], v[pre + ".decay2"], v[pre + ".sustain2"])
        fe = self.fenv.render(n, a, fdecay, 0.0, fdecay)
        me = self.menv.render(n, v[pre + ".mea"], v[pre + ".med"], 0.0, v[pre + ".med"])
        return ae, fe, me

    def idle(self, n):
        for L in (0, 1):
            self.lfos[L].ph = (self.lfos[L].ph + n * self.lfo_hz(L + 1) / self.sr) % 1.0

    def pre_drive(self, x):
        """Filter drive: saturate what goes into the filter (a driven ladder's grit and thickness)."""
        fd = self.eng.p.val[self.pre + ".fdrive"]
        if fd <= 0.001:
            return x
        g = 1.0 + 7.0 * fd
        return np.tanh(x * g) / math.tanh(g) * (1.0 + 0.4 * fd)

    def distortion(self, y, mods):
        v = self.eng.p.val
        kind = int(v[self.pre + ".dist"])
        amt = min(max(v[self.pre + ".distamt"] + _mean(mods.get("Distortion", 0.0)), 0.0), 1.0)
        if kind == 0 or amt <= 0.001:
            return y
        if y.ndim == 2:  # distort the middle, keep the unison's width clean: stays solid in mono
            mid = 0.5 * (y[:, 0] + y[:, 1])
            side = 0.5 * (y[:, 0] - y[:, 1])
            md = distort(mid, DIST_TYPES[kind], amt, self)
            trim = 1.0 - 0.3 * amt
            return np.stack([md + side * 0.8, md - side * 0.8], axis=1) * trim
        return distort(y, DIST_TYPES[kind], amt, self) * (1.0 - 0.3 * amt)

    def synth_fx(self, out):
        v = self.eng.p.val
        k = int(v[self.pre + ".sfx"])
        if k <= 0:
            return out
        if self.sfx_units is None:
            self.sfx_units = [None, Chorus(self.sr), Ensemble(self.sr), Dimension(self.sr), Phaser(self.sr),
                              Flanger(self.sr)]
        return self.sfx_units[k].process(out, v[self.pre + ".sfxamt"])

    def unison(self, mods, det_key, scale):
        """Unison voices for this block: (positions -1..1, detune in semitones for position 1, width)."""
        v = self.eng.p.val
        U = UNI_COUNTS[int(v[self.pre + ".uni"])]
        if len(self.chord()) > 1:
            U = max(1, min(U, 8 // len(self.chord())))  # chords x unison stays within 8 oscillators
            U = max(k for k in UNI_POS if k <= U)
        det = min(max(v[det_key] + _mean(mods.get("Unison", 0.0)), 0.0), 1.0)
        return UNI_POS[U], scale(det), v[self.pre + ".uniwid"]

    def finish(self, y, ae, mods, vol_key):
        """Velocity, volume, tremolo and pan -> stereo (n, 2)."""
        v = self.eng.p.val
        pre = self.pre
        va = v[pre + ".velamp"]
        trim = v[pre + ".trim"]
        gain = ae * ((1.0 - va + va * self.vel_raw) * v[vol_key] * 0.6 * (10.0 ** (trim / 20.0) if trim else 1.0))
        if "Volume" in mods:
            gain = gain * np.clip(1.0 + mods["Volume"], 0.0, 2.0)
        pan = np.clip(v[pre + ".pan"] + mods.get("Pan", 0.0), -1.0, 1.0)
        th = (pan + 1.0) * (math.pi / 4.0)
        gl = np.cos(th) * math.sqrt(2.0)
        gr = np.sin(th) * math.sqrt(2.0)
        if y.ndim == 1:
            out = np.stack([y * gain * gl, y * gain * gr], axis=1)
        else:
            out = np.stack([y[:, 0] * gain * gl, y[:, 1] * gain * gr], axis=1)
        return self.synth_fx(out)


def _osc(t, d, wave, pw):
    saw = 2.0 * t - 1.0 - polyblep(t, d)
    if not isinstance(wave, np.ndarray) and wave <= 0.001:
        return saw
    pulse = np.where(t < pw, 1.0, -1.0) + polyblep(t, d) - polyblep((t - pw) % 1.0, d) - (2 * pw - 1)
    return (1 - wave) * saw + wave * pulse


def _pan_lr(pan):
    th = (pan + 1.0) * (math.pi / 4.0)
    return math.cos(th) * math.sqrt(2.0), math.sin(th) * math.sqrt(2.0)


def distort(y, kind, amt, owner=None):
    """Synth distortion, roughly level-matched so turning it up adds grit rather than volume."""
    if kind == "Tube":  # asymmetric: even harmonics, warm
        g = 1.0 + 9.0 * amt
        b = 0.35 * amt
        return (np.tanh(g * y + b) - math.tanh(b)) / math.tanh(g) * (1.0 - 0.15 * amt)
    if kind == "Tape":  # soft, rounded
        g = 1.0 + 6.0 * amt
        return np.arctan(g * y) / math.atan(g)
    if kind == "Fold":  # wavefolder: harmonics fold back in, metallic and buzzy
        g = 1.0 + 5.0 * amt
        return np.sin(np.clip(y * g, -40.0, 40.0) * (math.pi / 2.0)) * (0.85 + 0.15 * (1.0 - amt))
    if kind == "Crush":  # fewer bits and a lower sample rate
        bits = 12.0 - 9.0 * amt
        q = 2.0 ** (1.0 - bits)
        ds = 1 + int(amt * 14)
        if ds > 1:
            idx = (np.arange(len(y)) // ds) * ds
            y = y[idx]
        return np.round(y / q) * q
    if kind == "Hard clip":
        g = 1.0 + 8.0 * amt
        return np.clip(y * g, -1.0, 1.0) * (0.9 - 0.2 * amt)
    return y


def warp_phase(p, kind, a):
    """Synth 2's warp modes: reshape the read position through the wave (0..1)."""
    if kind == "Bend +":
        p = p ** (1.0 + 4.0 * a)
    elif kind == "Bend -":
        p = 1.0 - (1.0 - p) ** (1.0 + 4.0 * a)
    elif kind == "Mirror":
        m = np.where(p < 0.5, 2.0 * p, 2.0 - 2.0 * p)
        p = (1.0 - a) * p + a * m
    elif kind == "Sync":
        p = (p * (1.0 + 7.0 * a)) % 1.0
    elif kind == "Squeeze":
        p = np.minimum(p / (1.0 - 0.85 * a), 1.0)
    elif kind == "Phase FM":
        p = (p + a * 0.4 * np.sin(TWO_PI * 2.0 * p)) % 1.0
    elif kind == "Quantize":
        st = max(4.0, 96.0 - 90.0 * a)
        p = np.floor(p * st) / st
    return np.minimum(p, 1.0 - 1e-9)


WARP_BANDLIMIT = {"Sync": 6.0, "Squeeze": 4.0, "Bend +": 2.5, "Bend -": 2.5, "Phase FM": 2.0, "Mirror": 1.5}


class OscSynth(MonoSynth):
    SS_SPREAD = (-1.0, -0.58, -0.18, 0.19, 0.6, 0.98)  # JP-8000 style uneven spacing (x detune)

    def __init__(self, eng, pre="s1"):
        super().__init__(eng, pre, 2)
        self.ph = np.zeros((self.MAXV, 3))
        self.uph = np.random.default_rng(9).random((self.MAXV, 7, 2))  # unison voices' own phases
        # supersaw: 6 extra saws per voice, each with its own phase, detuned around the main one
        self.ssph = np.random.default_rng(7).random((self.MAXV, len(self.SS_SPREAD)))

    def render(self, n):
        if self.amp.stage == 0:
            self.idle(n)
            return None
        v = self.eng.p.val
        ae, fe, me = self.envs(n, v["s1.fdecay"])
        mods = self.modulation(n, ae, me)
        sem = self.pitch(n)
        if "Pitch" in mods:
            sem = sem + 12.0 * mods["Pitch"]
        wave = v["s1.wave"] + mods.get("Saw > Square", 0.0)
        wave = np.clip(wave, 0.0, 1.0) if isinstance(wave, np.ndarray) else min(max(wave, 0.0), 1.0)
        ss = v["s1.supersaw"] + mods.get("Supersaw", 0.0)
        ss = np.clip(ss, 0.0, 1.0) if isinstance(ss, np.ndarray) else min(max(ss, 0.0), 1.0)
        pw = v["s1.pw"] + 0.45 * mods.get("Pulse width", 0.0)
        pw = np.clip(pw, 0.05, 0.5) if isinstance(pw, np.ndarray) else min(max(pw, 0.05), 0.5)
        fm = mods.get("FM", 0.0) + v["s1.fm"]
        fm = np.clip(fm, 0.0, 1.0) if isinstance(fm, np.ndarray) else min(max(fm, 0.0), 1.0)
        ring = mods.get("Ring mod", 0.0) + v["s1.ring"]
        ring = np.clip(ring, 0.0, 1.0) if isinstance(ring, np.ndarray) else min(max(ring, 0.0), 1.0)
        o2st = v["s1.osc2"] + v["s1.detune"] / 100.0 + 12.0 * mods.get("Osc 2 pitch", 0.0)
        sync = v["s1.sync"] >= 0.5
        sub = v["s1.sub"]
        ints = self.chord()
        drift = self.drift(n)
        pos, det, wid = self.unison(mods, "s1.unidet", lambda d: 0.55 * d ** 1.5)
        x = np.zeros((n, 2))
        subtype = int(v["s1.subtype"])
        clean = 0.0
        use_fm = isinstance(fm, np.ndarray) or fm > 0.001
        use_ring = isinstance(ring, np.ndarray) or ring > 0.001
        for vi, iv in enumerate(ints):
            ph = self.ph[vi]
            f1 = 440.0 * 2.0 ** ((sem + iv + drift[vi] - 69.0) / 12.0)
            dt1 = f1 / self.sr
            if len(pos) == 1:
                dt2 = dt1 * 2.0 ** (o2st / 12.0)
                t1 = (ph[0] + np.cumsum(dt1)) % 1.0
                ph[0] = t1[-1]
                if sync:
                    t2 = (t1 * (dt2 / dt1)) % 1.0
                else:
                    t2 = (ph[1] + np.cumsum(dt2)) % 1.0
                    ph[1] = t2[-1]
                o2 = _osc(t2, dt2, wave, pw)
                t1m = (t1 + fm * 0.5 * np.sin(TWO_PI * t2)) % 1.0 if use_fm else t1
                o1 = _osc(t1m, dt1, wave, pw)
                if isinstance(ss, np.ndarray) or ss > 0.001:
                    # real supersaw: detuned saws (own phases) blended in; more Supersaw = wider and louder stack
                    spread = 0.06 + 0.5 * _mean(ss)  # semitones for the outer saws
                    stack = np.zeros(n)
                    sph = self.ssph[vi]
                    for j, off in enumerate(self.SS_SPREAD):
                        dtj = dt1 * 2.0 ** (off * spread / 12.0)
                        tj = (sph[j] + np.cumsum(dtj)) % 1.0
                        sph[j] = tj[-1]
                        stack += 2.0 * tj - 1.0 - polyblep(tj, dtj)
                    saw1 = 2.0 * t1 - 1.0 - polyblep(t1, dt1)
                    stack = (stack + saw1) * (1.0 / math.sqrt(7.0))
                    o1 = (1.0 - ss) * o1 + ss * stack * 1.4
                mix = (o1 + o2) * 0.5
                if use_ring:
                    mix = mix * (1.0 - ring) + o1 * o2 * ring
                x += mix[:, None]
            else:
                # unison: each voice is a full osc 1 + osc 2 pair, detuned and spread across the stereo field
                norm = 1.0 / math.sqrt(len(pos))
                for u, pu in enumerate(pos):
                    up = self.uph[vi, u]
                    du = dt1 * 2.0 ** (pu * det / 12.0)
                    d2 = du * 2.0 ** (o2st / 12.0)
                    t1 = (up[0] + np.cumsum(du)) % 1.0
                    up[0] = t1[-1]
                    if sync:
                        t2 = (t1 * (d2 / du)) % 1.0
                    else:
                        t2 = (up[1] + np.cumsum(d2)) % 1.0
                        up[1] = t2[-1]
                    o2 = _osc(t2, d2, wave, pw)
                    t1m = (t1 + fm * 0.5 * np.sin(TWO_PI * t2)) % 1.0 if use_fm else t1
                    o1 = _osc(t1m, du, wave, pw)
                    mix = (o1 + o2) * 0.5
                    if use_ring:
                        mix = mix * (1.0 - ring) + o1 * o2 * ring
                    gl, gr = _pan_lr(wid * pu)
                    x[:, 0] += mix * (gl * norm)
                    x[:, 1] += mix * (gr * norm)
            if sub > 0.001:  # the sub stays in the middle, under the unison
                ts = (ph[2] + np.cumsum(dt1 * (1.0 if subtype == 2 else 0.5))) % 1.0
                ph[2] = ts[-1]
                if subtype == 0:
                    x += (sub * np.sin(TWO_PI * ts))[:, None]
                else:  # clean sub: a pure sine that skips the filter, drive and distortion (solid, deep low end)
                    clean = clean + sub * 0.62 * np.sin(TWO_PI * ts)
        if len(ints) > 1:
            x /= math.sqrt(len(ints))
        noise = v["s1.noise"] + _mean(mods.get("Noise", 0.0))
        if noise > 0.001:
            x += (min(noise, 1.0) * 0.8 * self.rng.uniform(-1.0, 1.0, n))[:, None]
        y = self.filt(self.pre_drive(x), fe, mods)
        drv = min(max(v["s1.drive"] + _mean(mods.get("Drive", 0.0)), 0.0), 1.0)
        g = 1.0 + 4.0 * drv
        y = np.tanh(y * g) / math.tanh(g) * 0.8
        y = self.distortion(y, mods)
        if isinstance(clean, np.ndarray):
            if len(ints) > 1:
                clean = clean / math.sqrt(len(ints))
            y = y + clean[:, None]
        return self.finish(y, ae, mods, "s1.vol")




def _build_wavetables(N=2048, F=16):
    harm_levels = [512, 256, 128, 64, 32, 16, 8, 4, 2, 1]
    K = N // 2 + 1
    k = np.arange(K, dtype=float)
    kk = np.maximum(k, 1)
    rng = np.random.default_rng(7)
    rphase = np.exp(1j * rng.uniform(0, TWO_PI, K))
    t = np.arange(N) / N

    def sine_coeffs(a):  # waveform sum a_k sin -> rfft coefficients
        return -1j * a * N / 2

    odd = (k % 2 == 1)
    shapes = {
        "sine": np.where(k == 1, 1.0, 0.0),
        "tri": np.where(odd, 8 / math.pi ** 2 * (-1.0) ** ((k - 1) // 2) / kk ** 2, 0.0),
        "saw": np.where(k >= 1, 2 / math.pi * (-1.0) ** (k + 1) / kk, 0.0),
        "sqr": np.where(odd, 4 / (math.pi * kk), 0.0),
    }
    vowels = [(730, 1090, 2440), (530, 1840, 2480), (270, 2290, 3010), (570, 840, 2410), (300, 870, 2240)]
    dig_keys = []
    for _ in range(6):
        a = rng.random(K) ** 3 / kk ** 0.8 * (rng.random(K) > 0.5)
        a[0] = 0
        a[1] = 1
        a[600:] = 0
        dig_keys.append(a)

    def spectrum(set_i, p):
        if set_i == 0:
            seq = [shapes["sine"], shapes["tri"], shapes["saw"], shapes["sqr"]]
            x = p * 3
            i = min(int(x), 2)
            f = x - i
            return sine_coeffs((1 - f) * seq[i] + f * seq[i + 1])
        if set_i == 1:
            x = p * 4
            i = min(int(x), 3)
            f = x - i
            fm = [(1 - f) * vowels[i][j] + f * vowels[i + 1][j] for j in range(3)]
            a = 0.04 / kk ** 0.5
            for c, g, bw in zip(fm, (1.0, 0.6, 0.35), (1.6, 2.5, 3.5)):
                a = a + g * np.exp(-((k - c / 130.0) / bw) ** 2)
            a[0] = 0
            return a * rphase * N / 2
        if set_i == 2:
            c = 1 + p * 40
            a = np.exp(-((k - c) / (2 + p * 6)) ** 2) + 0.3 * np.where(k == 1, 1, 0)
            a[0] = 0
            return a * rphase * N / 2
        if set_i == 3:
            pw = 0.5 - p * 0.46
            X = N * (1 - np.exp(-2j * math.pi * k * pw)) / (2j * math.pi * kk)
            X[0] = 0
            return X
        if set_i == 4:
            y = np.sin(TWO_PI * t + p * 5 * np.sin(TWO_PI * 3 * t))
            X = np.fft.rfft(y)
            X[0] = 0
            return X
        if set_i == 5:
            x = p * (len(dig_keys) - 1)
            i = min(int(x), len(dig_keys) - 2)
            f = x - i
            return ((1 - f) * dig_keys[i] + f * dig_keys[i + 1]) * rphase * N / 2
        # AKWF sets: 16 stored frames, linear morph between neighbours
        spec = AKWF_SPECTRA[set_i - len(BASE_TABLES)]
        nf = spec.shape[0]
        x = p * (nf - 1)
        i = min(int(x), nf - 2)
        f = x - i
        h = (1 - f) * spec[i] + f * spec[i + 1]
        X = np.zeros(K, dtype=complex)
        X[1:1 + len(h)] = h
        return X

    bank = []
    for s in range(len(TABLE_NAMES)):
        arr = np.zeros((len(harm_levels), F, N + 1), dtype=np.float32)
        for fi in range(F):
            X = spectrum(s, fi / (F - 1))
            full = np.fft.irfft(np.where(k <= harm_levels[0], X, 0), N)
            norm = 1.0 / max(np.max(np.abs(full)), 1e-9)
            for li, Hh in enumerate(harm_levels):
                y = np.fft.irfft(np.where(k <= Hh, X, 0), N) * norm
                arr[li, fi, :N] = y
                arr[li, fi, N] = y[0]
        bank.append(arr)
    return bank, harm_levels


_WT_CACHE = {}


class WaveSynth(MonoSynth):
    N = 2048

    def __init__(self, eng, pre="s2"):
        super().__init__(eng, pre, 2)
        if "bank" not in _WT_CACHE:
            _WT_CACHE["bank"] = _build_wavetables(self.N)
        self.bank, self.levels = _WT_CACHE["bank"]
        self.ph = np.zeros((self.MAXV, 3))
        self.uph = np.random.default_rng(13).random((self.MAXV, 7))  # unison voices' own phases
        self.lfo = 0.0
        self.dc_zi = np.zeros((1, 2))   # v2.0: DC blocker state (warped waves can sit off centre)

    def render(self, n):
        v = self.eng.p.val
        if self.amp.stage == 0:
            self.lfo = (self.lfo + n * v["s2.lforate"] / self.sr) % 1.0
            self.idle(n)
            return None
        ae, fe, me = self.envs(n, v["s2.decay"])
        mods = self.modulation(n, ae, me)
        sem = self.pitch(n)
        if "Pitch" in mods:
            sem = sem + 12.0 * mods["Pitch"]
        lfo_ph = self.lfo + np.arange(1, n + 1) * (v["s2.lforate"] / self.sr)
        self.lfo = float(lfo_ph[-1] % 1.0)
        pos = v["s2.pos"] + v["s2.posenv"] * fe + v["s2.lfoamt"] * 0.5 * np.sin(TWO_PI * lfo_ph)
        if "Wave position" in mods:
            pos = pos + mods["Wave position"]
        pos = np.clip(pos, 0.0, 1.0)
        tables = self.bank[min(int(v["s2.table"]), len(self.bank) - 1)]
        F = tables.shape[1]
        fpos = pos * (F - 1)
        fi = np.minimum(fpos.astype(np.int64), F - 2)
        ff = fpos - fi
        sub = min(max(v["s2.sub"] + _mean(mods.get("Sub osc", 0.0)), 0.0), 1.0)
        warp = WARPS[int(v["s2.warp"])]
        wa = min(max(v["s2.warpamt"] + _mean(mods.get("Warp", 0.0)), 0.0), 1.0)
        if warp == "Off" or wa <= 0.001:
            warp = None
        bl = 1.0 + (WARP_BANDLIMIT.get(warp, 1.0) - 1.0) * wa if warp else 1.0
        ints = self.chord()
        drift = self.drift(n)
        upos, det, wid = self.unison(mods, "s2.detune", lambda d: d * 0.3)
        norm = 0.8 / math.sqrt(len(upos)) if len(upos) > 1 else 1.0  # 2 voices = the level Synth 2 always had
        L = np.zeros(n)
        R = np.zeros(n)
        for vi, iv in enumerate(ints):
            ph = self.ph[vi]
            f = 440.0 * 2.0 ** ((sem + iv + drift[vi] - 69.0) / 12.0)
            for u, pu in enumerate(upos):
                dt = f * 2.0 ** (pu * det / 12.0) / self.sr
                p = (self.uph[vi, u] + np.cumsum(dt)) % 1.0
                self.uph[vi, u] = p[-1]
                if warp:
                    p = warp_phase(p, warp, wa)
                hmax = 0.45 / max(float(dt.max()) * bl, 1e-9)
                li = next((i for i, hh in enumerate(self.levels) if hh <= hmax), len(self.levels) - 1)
                tb = tables[li]
                x = p * self.N
                xi = x.astype(np.int64)
                xf = x - xi
                a = tb[fi, xi] * (1 - xf) + tb[fi, xi + 1] * xf
                b = tb[fi + 1, xi] * (1 - xf) + tb[fi + 1, xi + 1] * xf
                w = a * (1 - ff) + b * ff
                if len(upos) == 1:
                    L += w
                    R += w
                else:
                    gl, gr = _pan_lr(wid * pu)
                    L += w * (gl * norm)
                    R += w * (gr * norm)
            if sub > 0.001:
                ts = (ph[2] + np.cumsum(f * 0.5 / self.sr)) % 1.0
                ph[2] = ts[-1]
                s = sub * 0.8 * np.sin(TWO_PI * ts)
                L += s
                R += s
        if len(ints) > 1:
            L /= math.sqrt(len(ints))
            R /= math.sqrt(len(ints))
        noise = v["s2.noise"] + _mean(mods.get("Noise", 0.0))
        if noise > 0.001:
            nz = min(noise, 1.0) * 0.6 * self.rng.uniform(-1.0, 1.0, n)
            L += nz
            R += nz
        x = np.stack([L, R], axis=1)
        x, self.dc_zi = lfilter([1.0, -1.0], [1.0, -0.9985], x, axis=0, zi=self.dc_zi)  # ~10 Hz high-pass
        y = self.filt(self.pre_drive(x), fe, mods)
        y = np.tanh(y * 1.2)
        y = self.distortion(y, mods)
        return self.finish(y, ae, mods, "s2.vol")


def read_aiff(path):
    """(rate, samples) from an AIFF / AIFF-C file (8/16/24/32-bit PCM, big or little endian ("sowt"), or float)."""
    import struct
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"FORM" or data[8:12] not in (b"AIFF", b"AIFC"):
        raise ValueError("not an AIFF file")
    pos, ch, frames, bits, rate, comp, snd = 12, 1, 0, 16, 44100.0, b"NONE", None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"COMM":
            ch, frames, bits = struct.unpack(">hIh", body[:8])
            exp = ((body[8] & 0x7F) << 8) | body[9]
            rate = int.from_bytes(body[10:18], "big") * 2.0 ** (exp - 16383 - 63)
            if len(body) >= 22:
                comp = body[18:22]
        elif cid == b"SSND":
            off = struct.unpack(">I", body[:4])[0]
            snd = body[8 + off:]
        pos += 8 + size + (size & 1)
    if snd is None or ch < 1:
        raise ValueError("no audio in AIFF")
    nb = (bits + 7) // 8
    if comp in (b"fl32", b"FL32"):
        x = np.frombuffer(snd[:frames * ch * 4], dtype=">f4").astype(np.float64)
    elif comp in (b"fl64", b"FL64"):
        x = np.frombuffer(snd[:frames * ch * 8], dtype=">f8").astype(np.float64)
    else:
        le = comp == b"sowt"
        raw = np.frombuffer(snd[:frames * ch * nb], dtype=np.uint8).reshape(-1, nb)
        if le:
            raw = raw[:, ::-1]
        v = np.zeros(len(raw), dtype=np.int64)
        for k in range(nb):
            v = (v << 8) | raw[:, k]
        v = np.where(v >= 1 << (nb * 8 - 1), v - (1 << (nb * 8)), v)
        x = v / float(1 << (nb * 8 - 1))
    x = x[: len(x) // ch * ch].reshape(-1, ch)
    return int(round(rate)), x


def load_wav(path, sr):
    from scipy.io import wavfile
    if path.lower().endswith((".aif", ".aiff")):
        fs, x = read_aiff(path)
    else:
        fs, x = wavfile.read(path)
    if x.dtype.kind == "i":
        x = x / float(np.iinfo(x.dtype).max)
    elif x.dtype.kind == "u":
        x = (x.astype(np.float64) - 128) / 128.0
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if fs != sr and len(x) > 1:
        n = int(len(x) * sr / fs)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    x = trim_start(x[: sr * 20], sr)
    return np.append(x, 0.0).astype(np.float32)


def trim_start(x, sr, rel_db=-40.0, preroll_ms=0.5):
    """Cut silence before the hit: find the first sample above peak-40 dB, keep 0.5 ms before it
    (so the attack isn't clipped) and fade that pre-roll in to avoid a click."""
    if len(x) < 2:
        return x
    a = np.abs(x)
    pk = float(a.max())
    if pk <= 1e-6:
        return x
    onset = int(np.argmax(a > pk * 10 ** (rel_db / 20.0)))
    start = max(0, onset - int(preroll_ms * 1e-3 * sr))
    if start == 0:
        return x
    y = x[start:].copy()
    n = min(onset - start, len(y))
    if n > 1:
        y[:n] *= np.linspace(0.0, 1.0, n)
    return y


def load_folder(folder, sr, max_pads=16):
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".wav"))[:max_pads]
    out = []
    for f in files:
        try:
            out.append((os.path.splitext(f)[0][:14], load_wav(os.path.join(folder, f), sr)))
        except Exception:
            continue
    return out


class DrumDrive:
    """v2.1.1: a musical drive for the drum bus (the Drum drive knob).

    The old one put up to 7x gain into a hard tanh and normalised it, so past about half way the kit became a
    flat, fizzy square wave and jumped in level. This one:
    - raises the gain on a curve (about +3 dB at 25%, +8 dB at 50%, +18 dB at 100%), so the top is crunch, not wreckage
    - saturates slightly asymmetrically (a tube / tape-like curve) for warm even harmonics
    - uses antiderivative anti-aliasing, so the high end stays smooth instead of fizzing
    - keeps most of the kick's sub out of the saturation, so the low end stays solid
    - blends the clean kit back under it (parallel drive), so hits keep their punch
    - smooths the very top a little more as it's pushed, like an analog circuit
    - matches the level, so the knob adds character, not volume
    """

    def __init__(self, sr):
        self.sr = sr
        self.prev_in = np.zeros(2)    # last sample into the saturator, before gain (anti-aliasing memory)
        self.amt = 0.0                # the knob, glided so jumps don't click
        self.last = (0.9, 0.0, 1.0, 0.0)   # gain, bias, level and sub kept clean, last block: ramped from
        self.lo_zi = np.zeros((1, 2))
        self.top_zi = np.zeros((1, 2))
        self.dc_zi = np.zeros((1, 2))
        self.mix = 0.0                # blend from the last block, faded per sample so moving the knob never clicks

    @staticmethod
    def _F(u):
        """Antiderivative of tanh: log(cosh(u)), computed without overflow."""
        a = np.abs(u)
        return a + np.log1p(np.exp(-2.0 * a)) - math.log(2.0)

    def _sat(self, u, u_prev):
        """tanh with first-order antiderivative anti-aliasing; u_prev = the last block's final sample at this
        block's gain, so a gain change never makes a jump."""
        prev = np.vstack([u_prev[None, :], u[:-1]])
        du = u - prev
        small = np.abs(du) < 1e-6
        safe = np.where(small, 1.0, du)
        y = (self._F(u) - self._F(prev)) / safe
        mid = np.tanh(0.5 * (u + prev))
        return np.where(small, mid, y)

    def process(self, x, target):
        # glide the knob (0 -> 1 in about 60 ms) so turning it fast never clicks
        amt = self.amt + max(-0.1, min(0.1, target - self.amt))
        self.amt = amt
        sr = self.sr
        if amt <= 0.0 and self.mix <= 0.0:   # fully off: keep the memories warm, pass the kit through
            a = math.exp(-TWO_PI * 110.0 / sr)
            _, self.lo_zi = lfilter([1 - a], [1, -a], x, axis=0, zi=self.lo_zi)
            self.prev_in = x[-1].copy()
            return x
        g = 10.0 ** ((18.0 * amt ** 1.4) / 20.0)          # input gain: 0 -> +18 dB on a curve
        bias = 0.12 * amt                                 # asymmetry -> even harmonics (warmth)
        n = len(x)
        k0, b0, l0, c0 = self.last
        k1, b1, l1, c1 = g * 0.9, bias, 1.0 / (g ** 0.78), 0.6 * amt   # level: divide tanh's gain back out
        self.last = (k1, b1, l1, c1)
        ramp = lambda v0, v1: (np.linspace(v0, v1, n, endpoint=False)[:, None] if v0 != v1 else v1)  # noqa: E731
        kv, bv, lv, keep = ramp(k0, k1), ramp(b0, b1), ramp(l0, l1), ramp(c0, c1)
        # keep most of the sub out of the drive
        a = math.exp(-TWO_PI * 110.0 / sr)
        lo, self.lo_zi = lfilter([1 - a], [1, -a], x, axis=0, zi=self.lo_zi)
        drive_in = x - keep * lo
        y = self._sat(drive_in * kv + bv, self.prev_in * k0 + b0) - np.tanh(bv)
        self.prev_in = drive_in[-1].copy()
        y, self.dc_zi = lfilter([1.0, -1.0], [1.0, -0.9995], y, axis=0, zi=self.dc_zi)   # asymmetry's DC out
        # the very top rounds off a little as it's pushed
        fc = 20000.0 - 11000.0 * amt
        b = math.exp(-TWO_PI * fc / sr)
        y, self.top_zi = lfilter([1 - b], [1, -b], y, axis=0, zi=self.top_zi)
        y = y * lv
        wet = y + keep * lo
        target = min(1.0, 1.25 * amt)                     # the clean kit stays under it until 80%: keeps the punch
        mix = np.linspace(self.mix, target, len(x), endpoint=False)[:, None] if target != self.mix else target
        self.mix = target
        return x * (1.0 - mix) + wet * mix


class Drums:
    CHOKE = {4: [5]}  # closed hat (pad 5) chokes open hat (pad 6)

    def __init__(self, eng):
        self.eng, self.sr = eng, eng.sr
        self.voices = []
        self.zi = np.zeros((1, 2, 2))
        self.active = [0.0] * 16
        self.rr = [0] * 16
        self.kit_index = 0
        self.kit_name = ""
        self.pans = [0.0] * 16        # v2.1: each pad's place in the stereo field (scaled by Width)
        self.load_factory(0)
        # v2.1 drum bus state
        self.comp_env = 0.0
        self.tone_zi = np.zeros((1, 2))
        self.room = Reverb(eng.sr)
        self.room_zi = np.zeros((1, 2))
        self.drive = DrumDrive(eng.sr)   # v2.1.1
        self.crush_hold = np.zeros(2)
        self.crush_ph = 0

    # Each pad remembers where its sound came from, so any kit (and any edit) can be saved and rebuilt:
    #   {"factory": kit_index, "pad": n}  or  {"file": path, "label": name}
    def load_factory(self, index):
        from potentialbox import kits
        names, samples = kits.build(index, self.sr)
        self.kit_index = int(index) % len(kits.KITS)
        self.kit_name = kits.NAMES[self.kit_index]
        self.samples, self.names = [[s] for s in samples], list(names)
        self.sources = [{"factory": self.kit_index, "pad": i} for i in range(16)]
        self.pans = [kits.pan_of(self.kit_index, i) for i in range(16)]

    def use_builtin(self):
        self.load_factory(0)

    _cache = collections.OrderedDict()   # (path, sr, mtime) -> samples, shared by every engine (Kit Maker rolls)
    _cache_bytes = 0
    CACHE_MAX = 160 * 1024 * 1024

    def _read(self, path):
        import warnings
        try:
            key = (path, self.sr, os.path.getmtime(path))
        except OSError:
            key = None
        c = Drums._cache
        if key in c:
            c.move_to_end(key)
            return c[key]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            x = load_wav(path, self.sr)
        if key is not None:
            c[key] = x
            Drums._cache_bytes += x.nbytes
            while Drums._cache_bytes > self.CACHE_MAX and len(c) > 1:
                _, old = c.popitem(last=False)
                Drums._cache_bytes -= old.nbytes
        return x

    def load_sources(self, sources, name):
        """Rebuild a kit from 16 source entries (custom kits, My Kits). Returns pads loaded from files."""
        from potentialbox import kits
        samples, names, srcs, n = [], [], [], 0
        for i in range(16):
            src = sources[i] if i < len(sources) and isinstance(sources[i], dict) else {"factory": 0, "pad": i}
            if "file" in src:
                try:
                    samples.append([self._read(src["file"])])
                    names.append(src.get("label") or os.path.splitext(os.path.basename(src["file"]))[0][:14])
                    srcs.append(dict(src))
                    n += 1
                    continue
                except Exception:
                    src = {"factory": 0, "pad": i}
            k, p = int(src.get("factory", 0)), int(src.get("pad", i)) % 16
            fn, fs = kits.build(k, self.sr)
            samples.append([fs[p]])
            names.append(fn[p])
            srcs.append({"factory": k, "pad": p})
        self.samples, self.names, self.sources, self.kit_name = samples, names, srcs, name
        # a factory sound keeps its own place in the stereo field wherever it's moved; your samples sit where
        # that pad's role does
        self.pans = [kits.pan_of(s["factory"], s["pad"]) if "factory" in s else kits.pan_of(0, i)
                     for i, s in enumerate(srcs)]
        return n

    def set_pad(self, pad, path, label):
        """Put one WAV on one pad. Raises if the file can't be read."""
        x = self._read(path)
        pad %= 16
        samples, names, sources = [list(s) for s in self.samples], list(self.names), list(self.sources)
        samples[pad] = [x]
        names[pad] = label
        sources[pad] = {"file": path, "label": label}
        self.samples, self.names, self.sources = samples, names, sources

    def load_folder(self, folder, base_index=0):
        """First 16 WAVs (A-Z) go on pads 1-16; any empty pads keep the factory kit sounds."""
        try:
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".wav"))[:16]
        except OSError:
            return 0
        srcs = [{"file": os.path.join(folder, f), "label": os.path.splitext(f)[0][:14]} for f in files]
        srcs += [{"factory": base_index, "pad": i} for i in range(len(srcs), 16)]
        n = self.load_sources(srcs, os.path.basename(os.path.normpath(folder)))
        return n

    def load_mapped(self, pads, name):
        """pads: 16 (path or None, label) from library.map_kit. Missing/unreadable pads use the Potential kit."""
        srcs = [{"file": p, "label": l} if p else {"factory": 0, "pad": i} for i, (p, l) in enumerate(pads[:16])]
        return self.load_sources(srcs, name)

    def trigger(self, pad, vel, offset=0):
        pad %= 16
        for c in self.CHOKE.get(pad, []):
            for v in self.voices:
                if v[0] == c:
                    v[5] = True
        val = self.eng.p.val
        grp = int(val[f"dr.p{pad+1}.choke"])
        if grp > 0:
            for j in range(16):
                if j == pad:
                    continue
                if int(val[f"dr.p{j+1}.choke"]) == grp:
                    for v in self.voices:
                        if v[0] == j:
                            v[5] = True
        rate = 2.0 ** ((val[f"dr.p{pad+1}.tune"] + val["dr.kittune"]) / 12.0)
        dec = val[f"dr.p{pad+1}.decay"]
        layers = self.samples[pad] if isinstance(self.samples[pad], list) else [self.samples[pad]]
        if not layers:
            layers = [np.zeros(2)]
        if len(layers) > 1:
            idx = self.rr[pad] % len(layers)
            self.rr[pad] += 1
        else:
            idx = 0
        sample = layers[idx]
        M = len(sample) - 1
        if dec >= 0.99:
            k = 1.0
        else:
            tau = max(dec * dec * M / 2.0 / rate, 0.004 * self.sr)
            k = math.exp(-1.0 / tau)
        gain = val[f"dr.p{pad+1}.level"] * (vel / 127.0) ** 1.2
        pan = min(1.0, max(-1.0, val[f"dr.p{pad+1}.pan"] + self.pans[pad] * val["dr.width"]))
        th = (pan + 1.0) * (math.pi / 4.0)
        # [pad, pos, rate, gain, env, choking, k, left, right]
        # a negative position = starts `offset` samples into the next block
        self.voices.append([pad, -float(offset) * rate, rate, gain, 1.0, False, k,
                            math.cos(th) * math.sqrt(2.0), math.sin(th) * math.sqrt(2.0), sample])
        if len(self.voices) > 32:
            self.voices.pop(0)
        self.active[pad] = 1.0

    def render(self, n):
        if not self.voices:
            if self.room.idle or self.eng.p.val["dr.room"] <= 0.01:
                return None
            return self.bus(np.zeros((n, 2)))   # let the room ring out
        out = np.zeros((n, 2))
        ar = np.arange(n)
        alive = []
        for v in self.voices:
            pad, pos, rate, gain, e, choking, k, gl, gr, sample = v
            s = sample
            M = len(s) - 1
            st = 0
            if pos < 0:
                st = int(math.ceil(-pos / rate - 1e-9))
                if st >= n:
                    v[1] = pos + rate * n
                    alive.append(v)
                    continue
            p0 = pos + rate * st
            m = min(n - st, int(math.ceil((M - p0) / rate)))
            if m <= 0:
                continue
            p = p0 + rate * ar[:m]
            i = p.astype(np.int64)
            np.minimum(i, M - 1, out=i)
            fr = p - i
            y = s[i] * (1 - fr) + s[i + 1] * fr
            kk = 0.997 if choking else k
            if kk < 1.0:
                ev = e * kk ** np.arange(1, m + 1)
                y = y * ev
                e = float(ev[-1])
            y *= gain
            out[st:st + m, 0] += y * gl
            out[st:st + m, 1] += y * gr
            v[1] = pos + rate * n
            v[4] = e
            if st + m == n and e > 1e-4:
                alive.append(v)
        self.voices = alive
        return self.bus(out)

    def bus(self, out):
        """v2.1 drum bus: crush -> tone -> punch (parallel compression) -> filter -> drive -> room."""
        val = self.eng.p.val
        n = len(out)
        cr = val["dr.crush"]
        if cr > 0.01:
            hold = 1 + int(cr * 4.5)                     # 44.1 kHz down to ~8 kHz (sample and hold)
            if hold > 1:
                idx = np.arange(n)
                starts = (self.crush_ph + idx) % hold == 0
                last = np.maximum.accumulate(np.where(starts, idx, -1))
                held = out[np.maximum(last, 0)]
                held[last < 0] = self.crush_hold
                self.crush_hold = held[-1].copy()
                self.crush_ph = (self.crush_ph + n) % hold
                out = held
            q = 2.0 ** (15 - cr * 8)                      # 16 bits down to 8
            out = np.round(out * q) / q
        tone = val["dr.tone"]
        a = math.exp(-TWO_PI * 900.0 / self.sr)          # tilt around ~900 Hz
        low, self.tone_zi = lfilter([1 - a], [1, -a], out, axis=0, zi=self.tone_zi)
        if abs(tone) > 0.02:
            high = out - low
            out = low * (1 - 0.6 * tone) + high * (1 + 0.9 * tone) if tone > 0 else \
                low * (1 - 0.25 * tone) + high * (1 + 0.85 * tone)
        pc = val["dr.comp"]
        if pc > 0.01:
            # fast peak follower on the summed kit; heavy compression blended in under the dry kit
            lvl = np.abs(out).max(axis=1)
            att, rel = math.exp(-1.0 / (0.002 * self.sr)), math.exp(-1.0 / (0.09 * self.sr))
            env = np.empty(n)
            e = self.comp_env
            # a block is short: follow with a coarse 32-sample stride to keep it cheap
            for j in range(0, n, 32):
                pk = float(lvl[j:j + 32].max())
                k = att ** 32 if pk > e else rel ** 32
                e = pk + (e - pk) * k
                env[j:j + 32] = e
            self.comp_env = e
            thr = 0.08
            gain = np.where(env > thr, (thr / np.maximum(env, 1e-9)) ** 0.8, 1.0)  # ~5:1
            squashed = out * gain[:, None] * 3.2
            out = out + pc * 0.9 * squashed
            out = out / (1 + 0.45 * pc)
        fc = val["dr.filter"]
        if fc < 19000:
            sos = np.array([lp_coeffs(fc, 0.9, self.sr)])
            out, self.zi = sosfilt(sos, out, axis=0, zi=self.zi)
        out = self.drive.process(out, val["dr.drive"])
        rm = val["dr.room"]
        if rm > 0.01:
            ar = math.exp(-TWO_PI * 250.0 / self.sr)     # keep the kick's low end out of the room
            lo, self.room_zi = lfilter([1 - ar], [1, -ar], out, axis=0, zi=self.room_zi)
            wet = self.room.process(out - lo, val["dr.roomsize"] * 0.12, 7000.0, 1.0)
            if wet is not None:
                out = out + wet * (rm * 0.9)
        return out * (val["dr.vol"] * 0.8)


class Delay:
    def __init__(self, sr):
        self.sr = sr
        self.L = int(sr * 4)
        self.buf = np.zeros((self.L, 2))
        self.w = 0
        self.zi = np.zeros((1, 2))

    def process(self, x, seconds, fb, tone):
        n = len(x)
        D = int(min(max(seconds * self.sr, n), self.L - n - 1))
        ar = np.arange(n)
        d = self.buf[(self.w - D + ar) % self.L]
        a = math.exp(-TWO_PI * tone / self.sr)
        d, self.zi = lfilter([1 - a], [1, -a], d, axis=0, zi=self.zi)
        wi = (self.w + ar) % self.L
        self.buf[wi, 0] = (x[:, 0] + x[:, 1]) * 0.5 + fb * d[:, 1]
        self.buf[wi, 1] = fb * d[:, 0]
        self.w = (self.w + n) % self.L
        return d


class Reverb:
    """8-line feedback delay network, processed a block at a time (every line is longer than a block)."""
    LENGTHS = (1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617)

    def __init__(self, sr):
        self.sr = sr
        f = sr / 44100.0
        self.L = np.array([int(l * f) for l in self.LENGTHS])
        self.B = int(self.L.max() + 4096)
        self.buf = np.zeros((8, self.B))
        self.w = 0
        self.zi = np.zeros((8, 1))
        self.signs = np.array([1, -1, 1, -1, 1, -1, 1, -1], dtype=float)
        self.idle = True

    def process(self, x, size, tone, level):
        n = len(x)
        if self.idle and not np.any(x):
            return None
        out = np.zeros((n, 2))
        step = int(self.L.min())
        t60 = 0.4 + size * 5.6
        g = 10 ** (-3.0 * self.L / (t60 * self.sr))
        a = math.exp(-TWO_PI * tone / self.sr)
        for j in range(0, n, step):
            m = min(step, n - j)
            ar = np.arange(m)
            idx = (self.w - self.L[:, None] + ar[None, :]) % self.B
            y = self.buf[np.arange(8)[:, None], idx]
            y, self.zi = lfilter([1 - a], [1, -a], y, axis=1, zi=self.zi)
            y = y * g[:, None]
            mixed = y - (2.0 / 8.0) * y.sum(axis=0, keepdims=True)  # Householder matrix
            inp = (x[j:j + m, 0] + x[j:j + m, 1]) * 0.5
            wi = (self.w + ar) % self.B
            self.buf[:, wi] = mixed + self.signs[:, None] * inp[None, :] * 0.35
            self.w = (self.w + m) % self.B
            out[j:j + m, 0] = y[0::2].sum(axis=0)
            out[j:j + m, 1] = y[1::2].sum(axis=0)
        e = float(np.abs(out).max())
        self.idle = e < 1e-5 and not np.any(x)
        return out * (level * 0.5)


def hp_coeffs(fc, q, sr):
    fc = min(max(fc, 20.0), 0.45 * sr)
    w0 = TWO_PI * fc / sr
    alpha = math.sin(w0) / (2.0 * q)
    c = math.cos(w0)
    a0 = 1.0 + alpha
    return [(1 + c) / 2 / a0, -(1 + c) / a0, (1 + c) / 2 / a0, 1.0, -2 * c / a0, (1 - alpha) / a0]


class _ModDelay:
    """Shared ring buffer for chorus and flanger. The buffer is longer than the biggest audio block plus the
    longest delay, so every read lands on audio that is already written, whatever the buffer size."""
    L = 16384

    def __init__(self, sr):
        self.sr = sr
        self.buf = np.zeros((self.L, 2))
        self.w = 0
        self.ph = 0.0
        self.on = False

    def _lfo(self, n, hz):
        ph = self.ph + np.arange(1, n + 1) * (hz / self.sr)
        self.ph = float(ph[-1] % 1.0)
        return ph

    def _read(self, pos):
        """Fractional read at absolute positions `pos` (float, may be negative -> wraps)."""
        i0 = np.floor(pos)
        fr = pos - i0
        i0 = i0.astype(np.int64) % self.L
        i1 = (i0 + 1) % self.L
        fr = fr[:, None]
        return self.buf[i0] * (1.0 - fr) + self.buf[i1] * fr

    def _wake(self, amt):
        """Bypassed below 0.5 %. Coming back on starts from a clean buffer (no burst of old audio)."""
        if amt <= 0.005:
            self.on = False
            return False
        if not self.on:
            self.buf[:] = 0.0
            self.on = True
        return True


class Chorus(_ModDelay):
    """Stereo chorus: two voices per side, delays swept by slow sines a quarter-cycle apart."""

    def process(self, x, amt):
        if not self._wake(amt):
            return x
        n = len(x)
        ar = np.arange(n)
        self.buf[(self.w + ar) % self.L] = x
        ph = self._lfo(n, 0.35 + 0.9 * amt)
        base, depth = 0.011 * self.sr, (0.002 + 0.004 * amt) * self.sr
        now = self.w + ar
        wet = np.empty_like(x)
        for ch, off in ((0, 0.0), (1, 0.25)):
            d1 = base + depth * (0.5 + 0.5 * np.sin(TWO_PI * (ph + off)))
            d2 = base * 1.6 + depth * (0.5 + 0.5 * np.sin(TWO_PI * (ph + off + 0.5)))
            wet[:, ch] = 0.5 * (self._read(now - d1)[:, ch] + self._read(now - d2)[:, 1 - ch])
        self.w = (self.w + n) % self.L
        mix = 0.6 * amt
        return x * (1.0 - 0.35 * mix) + wet * mix


class Flanger(_ModDelay):
    """Flanger: 0.5-6 ms swept delay with feedback. Done in chunks shorter than the shortest delay so the
    feedback is exact at any buffer size."""
    CH = 16

    def process(self, x, amt):
        if not self._wake(amt):
            return x
        n = len(x)
        ph = self._lfo(n, 0.08 + 0.5 * amt)
        sw = 0.5 + 0.5 * np.sin(TWO_PI * ph)
        lo, span = 0.0006 * self.sr, (0.0015 + 0.004 * amt) * self.sr  # never shorter than CH samples
        dl = lo + span * sw
        dr = lo + span * (0.5 + 0.5 * np.sin(TWO_PI * (ph + 0.18)))
        fb = 0.25 + 0.5 * amt
        wet = np.empty_like(x)
        for j in range(0, n, self.CH):
            m = min(self.CH, n - j)
            now = self.w + np.arange(m)
            yl = self._read(now - dl[j:j + m])[:, 0]
            yr = self._read(now - dr[j:j + m])[:, 1]
            wet[j:j + m, 0], wet[j:j + m, 1] = yl, yr
            idx = now % self.L
            self.buf[idx, 0] = x[j:j + m, 0] + fb * yl
            self.buf[idx, 1] = x[j:j + m, 1] + fb * yr
            self.w = (self.w + m) % self.L
        mix = 0.5 * min(1.0, amt * 1.5)
        return x * (1.0 - mix) + wet * mix


class Ensemble(_ModDelay):
    """String-machine ensemble: three delay taps per side, each swept by a slow and a fast sine at different
    phases. Big, lush and wide (the sound of a Solina or a Juno pad)."""

    def __init__(self, sr):
        super().__init__(sr)
        self.ph2 = 0.0

    def process(self, x, amt):
        if not self._wake(amt):
            return x
        n = len(x)
        ar = np.arange(n)
        self.buf[(self.w + ar) % self.L] = x
        ph = self._lfo(n, 0.62)
        ph2 = self.ph2 + np.arange(1, n + 1) * (5.4 / self.sr)
        self.ph2 = float(ph2[-1] % 1.0)
        base, slow, fast = 0.008 * self.sr, (0.0015 + 0.002 * amt) * self.sr, 0.00035 * self.sr
        now = self.w + ar
        wet = np.zeros_like(x)
        for k, (gl, gr) in enumerate(((1.0, 0.35), (0.35, 1.0), (0.7, 0.7))):
            off = k / 3.0
            d = base + slow * (0.5 + 0.5 * np.sin(TWO_PI * (ph + off))) + fast * np.sin(TWO_PI * (ph2 + off))
            tap = self._read(now - d)
            wet[:, 0] += tap[:, 0] * gl
            wet[:, 1] += tap[:, 1] * gr
        self.w = (self.w + n) % self.L
        mix = 0.7 * amt
        return x * (1.0 - 0.45 * mix) + wet * (mix * 0.4)


class Dimension(_ModDelay):
    """Subtle, wide stereo chorus in the style of the Roland Dimension D: two short delays, slow and shallow,
    each fed from the other side. Thickens without sounding like a chorus."""

    def process(self, x, amt):
        if not self._wake(amt):
            return x
        n = len(x)
        ar = np.arange(n)
        self.buf[(self.w + ar) % self.L] = x
        ph = self._lfo(n, 0.25 + 0.25 * amt)
        base, depth = 0.0045 * self.sr, (0.0006 + 0.0012 * amt) * self.sr
        now = self.w + ar
        dl = base + depth * np.sin(TWO_PI * ph)
        dr = base - depth * np.sin(TWO_PI * ph)
        wet = np.empty_like(x)
        wet[:, 0] = self._read(now - dl)[:, 1]
        wet[:, 1] = self._read(now - dr)[:, 0]
        self.w = (self.w + n) % self.L
        mix = 0.55 * amt
        return x * (1.0 - 0.25 * mix) + wet * mix


class Phaser:
    """4-stage phaser (two all-pass biquads) swept from 200 Hz to 3.2 kHz, with a little feedback-free
    resonance. Coefficients move every 32 samples; the filter state carries over, so it's click-free."""
    S = 32

    def __init__(self, sr):
        self.sr = sr
        self.ph = 0.0
        self.zi = np.zeros((2, 2, 2))
        self.on = False

    def process(self, x, amt):
        if amt <= 0.005:
            self.on = False
            return x
        if not self.on:
            self.zi[:] = 0.0
            self.on = True
        n = len(x)
        hz = 0.12 + 0.9 * amt
        y = np.empty_like(x)
        for j in range(0, n, self.S):
            m = min(self.S, n - j)
            self.ph = (self.ph + m * hz / self.sr) % 1.0
            sw = 0.5 - 0.5 * math.cos(TWO_PI * self.ph)
            fc = 200.0 * 16.0 ** sw
            t = math.tan(math.pi * fc / self.sr)
            a = (t - 1.0) / (t + 1.0)
            sec = [a * a, 2 * a, 1.0, 1.0, 2 * a, a * a]
            y[j:j + m], self.zi = sosfilt(np.array([sec, sec]), x[j:j + m], axis=0, zi=self.zi)
        mix = 0.5 * min(1.0, amt * 1.4)
        return x * (1.0 - mix) + y * mix


def _ramp_gains(prev, g, S, n):
    """Per-chunk gains -> a per-sample curve that ramps from the last block's gain (no steps at block edges)."""
    k = len(g)
    pts = np.concatenate([[prev], g])
    xs = np.concatenate([[0.0], (np.arange(k) + 1) * S])
    return np.interp(np.arange(1, n + 1), xs, pts)


class Compressor:
    """Master compressor. More = lower threshold, higher ratio, auto make-up. 5 ms attack, 150 ms release."""
    S = 32

    def __init__(self, sr):
        self.sr = sr
        self.env = 0.0
        self.g = 1.0

    def process(self, x, amt):
        if amt <= 0.005:
            self.env, self.g = 0.0, 1.0
            return x
        n, S = len(x), self.S
        k = -(-n // S)
        lv = np.abs(x).max(axis=1)
        if k * S != n:
            lv = np.concatenate([lv, np.zeros(k * S - n)])
        peaks = lv.reshape(k, S).max(axis=1)
        ca, cr = math.exp(-S / (0.005 * self.sr)), math.exp(-S / (0.15 * self.sr))
        thr = 10 ** ((-3.0 - 27.0 * amt) / 20.0)
        ratio = 1.5 + 8.5 * amt
        makeup = (1.0 / thr) ** ((1.0 - 1.0 / ratio) * 0.6)
        g = np.empty(k)
        e = self.env
        for i in range(k):
            pk = peaks[i]
            e = pk + (e - pk) * (ca if pk > e else cr)
            g[i] = ((e / thr) ** (1.0 / ratio - 1.0) if e > thr else 1.0) * makeup
        self.env = e
        gs = _ramp_gains(self.g, g, S, n)
        self.g = float(g[-1])
        return x * gs[:, None]


class Limiter:
    """Look-ahead limiter for the very end of the chain. More = up to +12 dB pushed into a 0.95 ceiling.
    It sees 1 ms ahead (that much delay while it's on), so the gain is already down when a peak arrives:
    no clipping, no clicks. Recovers over ~80 ms."""
    CEIL = 0.95
    S = 16

    def __init__(self, sr):
        self.sr = sr
        self.W = max(8, int(0.001 * sr))
        self.on = False
        self.reset()

    def reset(self):
        W = self.W
        self.xh = np.zeros((W, 2))      # delayed audio
        self.th = np.ones(2 * W)        # gain targets of the last 2W samples
        self.r = 1.0                    # release envelope

    def process(self, x, amt):
        if amt <= 0.005:
            self.on = False
            return None
        if not self.on:
            self.reset()
            self.on = True
        n, W, S = len(x), self.W, self.S
        x = x * 10 ** (12.0 * amt / 20.0)
        pk = np.abs(x).max(axis=1)
        tg = np.minimum(1.0, self.CEIL / np.maximum(pk, 1e-9))
        T = np.concatenate([self.th, tg])
        gmin = np.lib.stride_tricks.sliding_window_view(T, W).min(axis=1)        # min over the next W samples
        g = np.lib.stride_tricks.sliding_window_view(gmin, W).mean(axis=1)[1:n + 1]  # smoothed over W
        X = np.concatenate([self.xh, x])
        self.xh, self.th = X[n:], T[n:]
        # slow release: per 16-sample chunk the gain may only rise by a set amount
        k = -(-n // S)
        gp = np.concatenate([g, np.full(k * S - n, g[-1])]) if k * S != n else g
        c = gp.reshape(k, S).min(axis=1)
        rise = math.exp(S / (0.08 * self.sr) * 2.3)  # ~ +20 dB per 80 ms at most
        r = np.empty(k)
        e = self.r
        for i in range(k):
            e = min(c[i], e * rise)
            r[i] = e
        rs = _ramp_gains(self.r, r, S, n)
        self.r = float(r[-1])
        return np.clip(X[:n] * np.minimum(g, rs)[:, None], -0.999, 0.999)


class MasterFX:
    """DJ filter (centre off, left low-pass, right high-pass) and lo-fi crusher on the whole mix."""

    def __init__(self, sr):
        self.sr = sr
        self.zi = np.zeros((1, 2, 2))
        self.mode = 0
        self.hold = np.zeros(2)

    def process(self, out, filt, crush):
        if abs(filt) >= 0.02:
            mode = -1 if filt < 0 else 1
            if mode != self.mode:
                self.zi = np.zeros((1, 2, 2))
                self.mode = mode
            if mode < 0:
                fc = 20000.0 * 2.0 ** (filt * 9.0)
                sos = np.array([lp_coeffs(fc, 1.1, self.sr)])
            else:
                fc = 20.0 * 2.0 ** (filt * 8.6)
                sos = np.array([hp_coeffs(fc, 1.1, self.sr)])
            out, self.zi = sosfilt(sos, out, axis=0, zi=self.zi)
        else:
            self.mode = 0
        if crush > 0.01:
            hold = 1 + int(crush * 11)
            if hold > 1:
                out = np.repeat(out[::hold], hold, axis=0)[: len(out)]
            q = 2 ** (15 - crush * 10.0)
            out = np.round(out * q) / q
        return out


def shelf_peak_sos(lo, mid, hi, lof, hif, sr):
    """Low shelf, mid peak (1 kHz) and high shelf, gains in dB (RBJ cookbook)."""
    out = []
    for kind, f, g in (("ls", lof, lo), ("pk", 1000.0, mid), ("hs", hif, hi)):
        A = 10 ** (g / 40.0)
        w0 = TWO_PI * min(f, 0.45 * sr) / sr
        c, sn = math.cos(w0), math.sin(w0)
        if kind == "pk":
            al = sn / (2 * 0.8)
            b0, b1, b2, a0, a1, a2 = 1 + al * A, -2 * c, 1 - al * A, 1 + al / A, -2 * c, 1 - al / A
        else:
            al = sn / 2 * math.sqrt(2.0)
            r = 2 * math.sqrt(A) * al
            if kind == "ls":
                b0, b1, b2 = A * ((A + 1) - (A - 1) * c + r), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - r)
                a0, a1, a2 = (A + 1) + (A - 1) * c + r, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - r
            else:
                b0, b1, b2 = A * ((A + 1) + (A - 1) * c + r), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - r)
                a0, a1, a2 = (A + 1) - (A - 1) * c + r, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - r
        out.append([b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0])
    return np.array(out)


class EQ3:
    def __init__(self, sr):
        self.sr = sr
        self.zi = np.zeros((3, 2, 2))
        self.key = None
        self.sos = None

    def process(self, x, lo, mid, hi, lof, hif):
        if abs(lo) < 0.05 and abs(mid) < 0.05 and abs(hi) < 0.05:
            if self.key is not None:
                self.zi[:] = 0.0
                self.key = None
            return x
        key = (round(lo, 2), round(mid, 2), round(hi, 2), round(lof), round(hif))
        if key != self.key:
            self.sos = shelf_peak_sos(lo, mid, hi, lof, hif, self.sr)
            self.key = key
        y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
        return y


class Glue:
    """Bus compressor on the master. One knob: more = lower threshold, higher ratio, auto make-up."""
    S = 32

    def __init__(self, sr):
        self.sr = sr
        self.env = 0.0
        self.gr = 1.0

    def process(self, x, amt, speed):
        if amt < 0.01:
            self.env, self.gr, self.glast = 0.0, 1.0, 1.0
            return x
        n = len(x)
        S = self.S
        k = -(-n // S)
        lv = np.abs(x).max(axis=1)
        if k * S != n:
            lv = np.concatenate([lv, np.zeros(k * S - n)])
        peaks = lv.reshape(k, S).max(axis=1)
        _, att, rel = GLUE_SPEEDS[int(speed)]
        ca, cr = math.exp(-S / (att * self.sr)), math.exp(-S / (rel * self.sr))
        thr = 10 ** ((-2.0 - 22.0 * amt) / 20.0)
        ratio = 2.0 + 4.0 * amt
        g = np.empty(k)
        e = self.env
        for i in range(k):
            pk = peaks[i]
            e = pk + (e - pk) * (ca if pk > e else cr)
            g[i] = (e / thr) ** (1.0 / ratio - 1.0) if e > thr else 1.0
        self.env = e
        makeup = (1.0 / thr) ** ((1.0 - 1.0 / ratio) * 0.5)
        gs = _ramp_gains(getattr(self, "glast", 1.0), g, S, n)
        self.glast = float(g[-1])
        self.gr = float(g.min())
        return x * (gs * makeup)[:, None]


class PunchFX:
    """Hold-to-play performance effects on the whole mix (EP-133 style).
    One buffer effect at a time (repeat, roll, tape stop, reverse: the last one pressed wins),
    plus filter sweep, gate and echo throw, which can be stacked on top."""
    BUF = ("Repeat 1/8", "Repeat 1/16", "Roll 1/32", "Tape stop", "Reverse")

    def __init__(self, sr):
        self.sr = sr
        self.L = int(sr * 8)
        self.buf = np.zeros((self.L, 2))
        self.abs = 0
        self.held = set()
        self.bfx = None      # [name, start abs, wet, releasing]
        self.sweep = None    # [start abs, fc now, releasing]
        self.gate = None     # start abs
        self.gate_g = 1.0
        self.fzi = np.zeros((1, 2, 2))
        self.echo = Delay(sr)
        self.echo_on = False
        self.echo_live = 0.0

    def press(self, i, on):
        name = PUNCH_FX[i % len(PUNCH_FX)]
        if on:
            self.held.add(name)
            if name in self.BUF:
                self.bfx = [name, self.abs, 0.0, False]
            elif name == "Filter sweep":
                self.sweep = [self.abs, 18000.0, False]
                self.fzi = np.zeros((1, 2, 2))
            elif name == "Gate 1/16":
                self.gate = self.abs
            else:
                self.echo_on = True
        else:
            self.held.discard(name)
            if self.bfx and self.bfx[0] == name:
                self.bfx[3] = True
            elif name == "Filter sweep" and self.sweep:
                self.sweep[2] = True
            elif name == "Gate 1/16":
                self.gate = None
            elif name == "Echo throw":
                self.echo_on = False

    def busy(self):
        return bool(self.bfx or self.sweep or self.gate is not None or self.echo_on or self.echo_live > 1e-5
                    or self.gate_g < 0.999)

    def process(self, x, bpm):
        n = len(x)
        base = self.abs
        idx = (base + np.arange(n)) % self.L
        self.buf[idx] = x
        self.abs += n
        if not self.busy():
            return x
        beat = 60.0 / max(bpm, 30.0) * self.sr
        y = x
        if self.bfx:
            name, start, wet, rel = self.bfx
            t = base - start + np.arange(n)
            if name in ("Repeat 1/8", "Repeat 1/16", "Roll 1/32"):
                Ls = max(int(beat * {"Repeat 1/8": 0.5, "Repeat 1/16": 0.25}.get(name, 0.125)), 64)
                ph = t % Ls
                src = np.where(t < Ls, base + np.arange(n), start + ph)
                g = np.minimum(1.0, (Ls - ph) / 48.0)
                g = np.where(t >= Ls, np.minimum(g, ph / 48.0 + 0.0), g)
                sig = self.buf[src % self.L] * np.clip(g, 0.0, 1.0)[:, None]
            elif name == "Tape stop":
                T = beat
                tt = np.minimum(t, T).astype(float)
                pos = tt - tt * tt / (2.0 * T)
                fpos = start + pos
                i0 = np.floor(fpos).astype(np.int64)
                fr = (fpos - i0)[:, None]
                sig = self.buf[i0 % self.L] * (1 - fr) + self.buf[(i0 + 1) % self.L] * fr
                sig = sig * np.clip((T - t) / (0.15 * T), 0.0, 1.0)[:, None]
            else:  # Reverse
                src = start - 1 - np.minimum(t, self.L - n - 2)
                sig = self.buf[src % self.L]
            ramp = np.clip(wet + (np.arange(1, n + 1) / 96.0) * (-1.0 if rel else 1.0), 0.0, 1.0)
            y = x * (1.0 - ramp)[:, None] + sig * ramp[:, None]
            self.bfx[2] = float(ramp[-1])
            if rel and ramp[-1] <= 0.0:
                self.bfx = None
        if self.sweep:
            start, fc, rel = self.sweep
            out = np.empty_like(y)
            for j in range(0, n, 32):
                e = min(j + 32, n)
                if rel:
                    fc = min(fc * 2.0 ** (32.0 / (0.12 * self.sr) * 7.0), 20000.0)
                else:
                    tt = (base - start + j) / (2.0 * beat)
                    fc = 18000.0 * (250.0 / 18000.0) ** min(tt, 1.0)
                sos = np.array([lp_coeffs(fc, 3.0, self.sr)])
                out[j:e], self.fzi = sosfilt(sos, y[j:e], axis=0, zi=self.fzi)
            y = out
            self.sweep[1] = fc
            if rel and fc >= 19999.0:
                self.sweep = None
        if self.gate is not None or self.gate_g < 0.999:
            if self.gate is not None:
                S = beat / 4.0
                t = base - self.gate + np.arange(n)
                ph = (t % S) / S
                tgt = np.where(ph < 0.5, 1.0, 0.0)
            else:
                tgt = np.ones(n)
            a = math.exp(-1.0 / (0.002 * self.sr))
            g, _ = lfilter([1 - a], [1, -a], tgt, zi=[self.gate_g * a])
            self.gate_g = float(g[-1])
            y = y * g[:, None]
        if self.echo_on or self.echo_live > 1e-5:
            inp = y if self.echo_on else np.zeros_like(y)
            d = self.echo.process(inp, beat * 0.75 / self.sr, 0.62, 4000.0)
            self.echo_live = float(np.abs(d).max())
            y = y + d * 0.8
        return y


class Engine:
    def __init__(self, sr, params=None):
        self.sr = int(sr)
        self.p = params or ParamStore()
        self.s1 = OscSynth(self)
        self.s2 = WaveSynth(self)
        self.drums = Drums(self)
        self.delay = Delay(self.sr)
        self.reverb = Reverb(self.sr)
        self.master = MasterFX(self.sr)
        self.chorus = Chorus(self.sr)
        self.flanger = Flanger(self.sr)
        self.phaser = Phaser(self.sr)
        self.comp = Compressor(self.sr)
        self.limiter = Limiter(self.sr)
        self.eqs = {k: EQ3(self.sr) for k in ("s1", "s2", "dr", "m")}
        self.glue = Glue(self.sr)
        self.punch = PunchFX(self.sr)
        self.events = collections.deque()
        self.bpm = 120.0
        self.peak = 0.0
        self.samples = 0
        self.load = 0.0
        # transport from the BeatStep's clock: 24 ticks per beat, 16th step = 6 ticks
        self.tick = -1
        self.playing = False
        self.step = None
        self.fill = False
        self.cond_rng = np.random.default_rng(71)
        self.duck_e = 0.0
        self.duck_hit = None
        self.beat_ph = 0.0
        self.recorder = None
        self.capture = None
        self.bounce = None   # v2.0 CAPTURE: bar-locked stems (mix + synth 1 + synth 2 + drums + fx + looper)
        self.hist = None     # v2.2 GRAB: the last HIST_SECS of the mix and every stem, always running
        self.hist_marks = collections.deque(maxlen=64)   # where bars started (absolute sample counts)
        self.cb_t = 0.0
        self.cb_prev = 0.0
        self.blk_n = 256
        from potentialbox.looper import Looper
        from potentialbox.beats import BeatPlayer
        self.looper = Looper(self)
        self.beats = BeatPlayer(self)

    # thread-safe entry points (MIDI / GUI threads)
    def note_on(self, target, note, vel=100):
        self.events.append((target, "on", note, vel))

    def note_off(self, target, note):
        self.events.append((target, "off", note, 0))

    def panic(self):
        self.events.append(("all", "panic", 0, 0))

    def clock(self, kind, ts=0.0):  # "tick", "start", "stop", "cont"; ts = time.perf_counter() when it arrived
        self.events.append(("clk", kind, 0, ts))

    def punch_fx(self, i, on):
        self.events.append(("pf", "on" if on else "off", i, 0))

    def set_fill(self, on):
        self.events.append(("fill", "on" if on else "off", 0, 0))

    def bar(self):
        return max(self.tick + 2, 0) // 96 if self.playing else 0

    def cond_ok(self, pad):
        v = self.p.val
        ch = v[f"dr.p{pad+1}.chance"]
        if ch < 0.999 and self.cond_rng.random() > ch:
            return False
        c = DRUM_CONDS[int(v[f"dr.p{pad+1}.cond"])]
        if c == "Always":
            return True
        if c == "Fill only":
            return self.fill
        if c == "Not in fill":
            return not self.fill
        k, of = c.split(" of ")
        return self.bar() % int(of) == int(k[:-2]) - 1

    def _hist_write(self, out, stems, n):
        """v2.2 GRAB: keep writing the mix and the stems into a ring buffer, so the last bars can be saved
        after you've played them."""
        h = self.hist
        if h is None or h["sr"] != self.sr:
            size = int(HIST_SECS * self.sr)
            h = self.hist = {"sr": self.sr, "size": size, "start": self.samples, "end": self.samples,
                             "buf": {k: np.zeros((size, 2), np.float32) for k in HIST_KEYS}}
        if not n:
            return
        size = h["size"]
        i = self.samples % size
        j = min(n, size - i)
        for k in HIST_KEYS:
            x = out if k == "mix" else stems.get(k)
            b = h["buf"][k]
            if x is None:
                b[i:i + j] = 0.0
                if j < n:
                    b[:n - j] = 0.0
            else:
                b[i:i + j] = x[:j]
                if j < n:
                    b[:n - j] = x[j:n]
        h["end"] = self.samples + n

    def hist_room(self, slack=0):
        """(first, end): the absolute samples that can safely be copied out of the history now. `slack`
        lets it reach a little before the very first sample (silence) while the buffer hasn't wrapped."""
        h = self.hist
        if h is None:
            return 0, 0
        wrap = h["end"] - h["size"] + 8192
        return max(h["start"] - slack, wrap), h["end"]

    def hist_cut(self, start, end, slack=0):
        """Copy [start, end) out of the history: {"mix": array, "s1": array, ...}, or None if it's gone."""
        h = self.hist
        first, last = self.hist_room(slack)
        if h is None or start < first or end > last or end <= start:
            return None
        idx = np.arange(start, end) % h["size"]
        return {k: h["buf"][k][idx].astype(np.float64) for k in HIST_KEYS}

    def tick_offset(self, ts):
        """Where in this block a tick that arrived at `ts` belongs: events from the last block period are
        spread over this block in the same spacing, so timing jitter becomes a small fixed delay."""
        a, b = self.cb_prev, self.cb_t
        if not ts or b <= a:
            return 0
        return int(min(max((ts - a) / (b - a), 0.0), 0.999) * self.blk_n)

    def _clock(self, kind, ts=0.0):
        p = self.p
        if kind == "start":
            self.tick = -1
            self.playing = True
            self.step = 0
            p.apply_step(0)
            self.looper.on_start()
            self.beats.on_start()
        elif kind == "cont":
            self.playing = True
        elif kind == "stop":
            self.playing = False
            self.step = None
            p.apply_step(None)
            self.looper.on_stop()
            self.beats.on_stop()
        elif kind == "tick":
            self.tick += 1
            if not self.playing:
                return
            t = self.tick
            if t >= 0 and t % 96 == 0:
                self.hist_marks.append(self.samples)   # block start: never after a note that came with it
            if t > 0 and t % 96 == 0:
                self.looper.on_bar()
            if t >= 0:
                self.beats.on_tick(t, self.tick_offset(ts))
            if t % 6 == 5:  # one tick early: the BeatStep may send the step's note before its clock
                self.step = ((t + 1) // 6) % 16
                p.apply_step(self.step)
            if t % 24 == 0 and int(p.val["dk.src"]) == 16:
                self.duck_hit = 0
            for cap in (self.capture, self.bounce):
                if cap and cap["state"] == "wait" and t % 96 == 94:
                    cap["state"] = "rec"
                if cap and cap["state"] == "rec" and cap.get("bar_at") is None and t % 96 == 0:
                    cap["bar_at"] = cap["got"]

    def _dispatch(self):
        ev = self.events
        while ev:
            target, kind, note, vel = ev.popleft()
            if kind == "panic":
                self.s1.all_off()
                self.s2.all_off()
                self.drums.voices = []
                continue
            if target == "clk":
                self._clock(kind, vel)
                continue
            if target == "pf":
                self.punch.press(note, kind == "on")
                continue
            if target == "fill":
                self.fill = kind == "on"
                continue
            if target == "dr":
                if kind == "on" and vel > 0 and self.cond_ok(note % 16):
                    self.drums.trigger(note, vel)
                    if note % 16 == int(self.p.val["dk.src"]):
                        self.duck_hit = 0
                continue
            syn = self.s1 if target == "s1" else self.s2
            if kind == "on" and vel > 0:
                syn.note_on(note, vel)
            else:
                syn.note_off(note)

    def duck_env(self, n):
        """Side-chain envelope (0..1): jumps up when the chosen pad plays (or on every beat), then falls."""
        v = self.p.val
        hit, self.duck_hit = self.duck_hit, None
        if max(v["dk.s1"], v["dk.s2"], v["dk.fx"]) < 0.005:
            self.duck_e = 0.0
            return None
        if int(v["dk.src"]) == 16 and not self.playing:  # every beat from the tempo when the BeatStep is stopped
            spb = 60.0 / max(self.bpm, 30.0) * self.sr
            first = spb - self.beat_ph
            if first < n:
                hit = int(first)
            self.beat_ph = (self.beat_ph + n) % spb
        tau = max(v["dk.rel"] * self.sr / 3.0, 1.0)
        t = np.arange(n, dtype=float)
        e0 = self.duck_e
        if hit is None:
            env = e0 * np.exp(-(t + 1.0) / tau)
        else:
            A = 0.003 * self.sr
            env = np.empty(n)
            env[:hit] = e0 * np.exp(-(t[:hit] + 1.0) / tau)
            eh = env[hit - 1] if hit > 0 else e0
            u = t[hit:] - hit
            env[hit:] = np.where(u < A, eh + (1.0 - eh) * (u / A), np.exp(-(u - A) / tau))
        self.duck_e = float(env[-1])
        return env

    def render(self, n, inp=None):
        t0 = time.perf_counter()
        out = self._render(n, inp)
        # how much of the buffer's time the sound took to make (shown on the Setup tab)
        used = (time.perf_counter() - t0) * self.sr / max(n, 1)
        self.load = max(used, self.load * 0.97)
        return out

    def _render(self, n, inp=None):
        now = time.perf_counter()
        self.cb_prev = self.cb_t if self.cb_t else now - n / self.sr
        self.cb_t = now
        self.blk_n = n
        self._dispatch()
        v = self.p.val
        out = np.zeros((n, 2))
        send = np.zeros((n, 2))
        rsend = np.zeros((n, 2))
        duck = self.duck_env(n)
        lof, hif = v["eq.lof"], v["eq.hif"]
        stems = {}  # v2.2: always, for the GRAB history (only references, no copies)
        solo_active = (v["s1.solo"] >= 0.5 or v["s2.solo"] >= 0.5 or v["dr.solo"] >= 0.5)
        def track_plays(mute, solo):
            if solo_active:
                return solo >= 0.5
            return mute < 0.5
        for key, syn in (("s1", self.s1), ("s2", self.s2)):
            a = syn.render_block(n)  # muted tracks still run, so notes, arp and envelopes stay in time
            if a is None or not track_plays(v[f"{key}.mute"], v[f"{key}.solo"]):
                continue
            a = self.eqs[key].process(a, v[f"eq.{key}.lo"], v[f"eq.{key}.mid"], v[f"eq.{key}.hi"], lof, hif)
            if duck is not None and v["dk." + key] > 0.005:
                a = a * (1.0 - v["dk." + key] * duck)[:, None]
            out += a
            send += a * v["fx." + key]
            rsend += a * v["rv." + key]
            if stems is not None:
                stems[key] = a
        self.beats.render_hits(n)
        c = self.drums.render(n)
        if track_plays(v["dr.mute"], v["dr.solo"]):
            if c is not None:
                c = self.eqs["dr"].process(c, v["eq.dr.lo"], v["eq.dr.mid"], v["eq.dr.hi"], lof, hif)
                out += c
                send += c * v["fx.dr"]
                rsend += c * v["rv.dr"]
                if stems is not None:
                    stems["dr"] = c
        secs = DIVISIONS[int(v["fx.time"])][1] * 60.0 / max(self.bpm, 30.0)
        d = self.delay.process(send, secs, v["fx.fb"], v["fx.tone"])
        rsend += d * 0.3
        r = self.reverb.process(rsend, v["rv.size"], v["rv.tone"], v["rv.level"])
        fx = d if r is None else d + r
        if duck is not None and v["dk.fx"] > 0.005:
            fx = fx * (1.0 - v["dk.fx"] * duck)[:, None]
        out += fx
        if stems is not None:
            stems["fx"] = fx
        # looper: records the interface input and/or this mix, plays its loops into the mix before the master FX
        lp = self.looper
        loops = lp.process(n, inp, out, duck)  # always: its clock must keep running
        if loops is not None:
            out = out + loops
            if stems is not None:
                stems["lp"] = loops
        if inp is not None and v["lp.mon"] > 0.005:
            out = out + inp * (v["lp.in"] * v["lp.mon"])
        out = self.chorus.process(out, v["m.chorus"])
        out = self.flanger.process(out, v["m.flanger"])
        out = self.phaser.process(out, v["m.phaser"])
        out = self.comp.process(out, v["m.compressor"])
        amt = v["m.distortion"]
        if amt > 0.005:  # blended in, so turning it up from zero doesn't jump in level
            drive = 1.0 + amt * 9.0
            out = out + amt * (np.tanh(out * drive) / math.tanh(drive) - out)
        out = self.master.process(out, v["m.filter"], v["m.crush"])
        out = self.eqs["m"].process(out, v["eq.m.lo"], v["eq.m.mid"], v["eq.m.hi"], lof, hif)
        out = self.glue.process(out, v["m.glue"], v["m.gluespd"])
        w = v["m.width"]
        if abs(w - 1.0) > 0.01:
            mid = (out[:, 0] + out[:, 1]) * 0.5
            side = (out[:, 0] - out[:, 1]) * 0.5 * w
            out = np.stack([mid + side, mid - side], axis=1)
        out = self.punch.process(out, self.bpm)
        g = 1.0 + 4.0 * v["m.drive"]
        lim = self.limiter.process(out * (v["m.master"] * g), v["m.limiter"])  # None while it's off
        if lim is not None:  # the limiter replaces the soft clip at the very end
            out = lim
        else:
            out = np.tanh(out * (v["m.master"] * g)) if g > 1.01 else np.tanh(out * v["m.master"])
        pk = float(np.max(np.abs(out))) if n else 0.0
        self.peak = max(pk, self.peak * 0.9)
        try:
            self._hist_write(out, stems, n)
        except Exception:
            pass
        self.samples += n
        if self.recorder is not None:
            try:
                self.recorder.push(out, stems)
            except Exception:
                pass
        bnc = self.bounce
        if bnc and bnc["state"] == "rec":
            bnc["buf"].append((out.copy(), {k: stems[k].copy() for k in BOUNCE_STEMS if k in stems}, n))
            bnc["got"] += n
            if bnc.get("bar_at") is not None and bnc["got"] >= bnc["bar_at"] + bnc["need"]:
                bnc["state"] = "done"
        cap = self.capture
        if cap and cap["state"] == "rec":
            src = cap["src"]
            if src == "all":
                x = out
            else:
                x = np.zeros((n, 2))
                for k in (("s1", "s2") if src == "synths" else (src,)):
                    if k in stems:
                        x = x + stems[k]
            cap["buf"].append(x.copy())
            cap["got"] += n
            if cap.get("bar_at") is not None and cap["got"] >= cap["bar_at"] + cap["need"]:
                cap["state"] = "done"
        return out.astype(np.float32)
