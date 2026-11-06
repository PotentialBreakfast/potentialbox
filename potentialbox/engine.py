"""PotentialBox sound engine.

Block-based numpy DSP:
  Synth 1  - mono virtual-analog synth (saw/square, sub, resonant filter)
  Synth 2  - mono wavetable synth (6 morphing tables, LFO, unison)
  Drums    - 16-pad sample player with a built-in synthesized kit
  FX       - tempo-synced ping-pong delay
"""
import math
import os
import collections

import numpy as np
from scipy.signal import sosfilt, lfilter

TWO_PI = 2.0 * math.pi
DIVISIONS = [("1/16", 0.25), ("1/8T", 1 / 3), ("1/8", 0.5), ("3/16", 0.75), ("1/4", 1.0), ("3/8", 1.5)]
BASE_TABLES = ["Analog", "Vowel", "Harmonic", "PWM", "FM Bell", "Digital"]
LFO_SHAPES = ["Sine", "Triangle", "Saw up", "Saw down", "Square", "Random", "Smooth random"]
LFO_SYNC = [("Free", None), ("4 bars", 16), ("2 bars", 8), ("1 bar", 4), ("1/2", 2), ("1/4", 1), ("1/8", 0.5),
            ("1/16", 0.25), ("1/32", 0.125), ("1/4T", 2 / 3), ("1/8T", 1 / 3), ("1/16T", 1 / 6)]
MOD_SOURCES = ["Off", "LFO 1", "LFO 2", "Mod env", "Amp env", "Velocity", "Note", "Random"]
MOD_DESTS = {"s1": ["Pitch", "Osc 2 pitch", "Cutoff", "Resonance", "Saw > Square", "Pulse width", "FM", "Ring mod",
                    "Noise", "Volume", "Pan", "Drive"],
             "s2": ["Pitch", "Cutoff", "Resonance", "Wave position", "Unison", "Sub osc", "Noise", "Volume", "Pan"]}
DEFAULT_ROUTES = {
    "s1": [("LFO 1", "Pitch"), ("LFO 1", "Cutoff"), ("LFO 2", "Pulse width"), ("Mod env", "Cutoff"),
           ("Velocity", "Cutoff"), ("LFO 2", "Pan"), ("Mod env", "Pitch"), ("LFO 2", "Volume")],
    "s2": [("LFO 1", "Pitch"), ("LFO 1", "Cutoff"), ("LFO 2", "Wave position"), ("Mod env", "Wave position"),
           ("Velocity", "Cutoff"), ("LFO 2", "Pan"), ("Mod env", "Pitch"), ("LFO 2", "Volume")]}
CHORDS = [("Off", (0,)), ("Octave", (0, 12)), ("Fifth", (0, 7)), ("Fifth + octave", (0, 7, 12)), ("Major", (0, 4, 7)),
          ("Minor", (0, 3, 7)), ("Sus2", (0, 2, 7)), ("Sus4", (0, 5, 7)), ("Major 7", (0, 4, 7, 11)),
          ("Minor 7", (0, 3, 7, 10)), ("Dominant 7", (0, 4, 7, 10)), ("Minor 9", (0, 3, 10, 14)), ("Stack", (0, 7, 12, 19))]
VOICINGS = ["Close", "Open", "Wide"]
FTYPES = ["LP 24", "LP 12", "HP 12", "Band-pass", "Notch"]
GLIDE_MODES = ["Slides only", "Always"]


def _load_akwf():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "akwf_tables.npz")
    try:
        d = np.load(path)
        return [str(x) for x in d["names"]], d["spectra"]
    except Exception:
        return [], None


AKWF_NAMES, AKWF_SPECTRA = _load_akwf()
TABLE_NAMES = BASE_TABLES + AKWF_NAMES  # 6 built-in + 24 AKWF (CC0) tables

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
        a(Param(pre + ".release", "Release", 0.005, 3, 0.15 if pre == "s1" else 0.4, "exp", unit="s"))
        a(Param(pre + ".glide", "Glide (slides)", 0.005, 1, 0.06, "exp", unit="s"))
        a(Param(pre + ".vol", name + " volume", 0, 1, 0.7, unit="%"))
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
        a(Param(pre + ".pan", "Pan", -1, 1, 0.0, unit="pan"))
        a(Param(pre + ".drift", "Analog drift", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".penv", "Pitch env", -24, 24, 0.0, unit="st"))
        a(Param(pre + ".pdec", "Pitch env time", 0.005, 2, 0.08, "exp", unit="s"))
        a(Param(pre + ".ftype", "Filter type", 0, len(FTYPES) - 1, 0, step=1, choices=FTYPES))
        a(Param(pre + ".keytrk", "Key tracking", 0, 1, 0.0, unit="%"))
        a(Param(pre + ".velamp", "Velocity > volume", 0, 1, 0.65, unit="%"))
        a(Param(pre + ".glmode", "Glide mode", 0, 1, 0, step=1, choices=GLIDE_MODES))
        for L, (shape, rate) in ((1, (0, 2.0)), (2, (1, 0.5))):
            a(Param(f"{pre}.l{L}shape", f"LFO {L} shape", 0, len(LFO_SHAPES) - 1, shape, step=1, choices=LFO_SHAPES))
            a(Param(f"{pre}.l{L}rate", f"LFO {L} speed", 0.05, 20, rate, "exp", unit="Hz"))
            a(Param(f"{pre}.l{L}sync", f"LFO {L} sync", 0, len(LFO_SYNC) - 1, 0, step=1, choices=[x[0] for x in LFO_SYNC]))
        a(Param(pre + ".mea", "Mod env attack", 0.001, 2, 0.005, "exp", unit="s"))
        a(Param(pre + ".med", "Mod env decay", 0.01, 4, 0.3, "exp", unit="s"))
        for j, (src, dst) in enumerate(DEFAULT_ROUTES[pre]):
            a(Param(f"{pre}.m{j+1}src", f"Slot {j+1} source", 0, len(MOD_SOURCES) - 1, MOD_SOURCES.index(src),
                    step=1, choices=MOD_SOURCES))
            a(Param(f"{pre}.m{j+1}dst", f"Slot {j+1} target", 0, len(MOD_DESTS[pre]) - 1, MOD_DESTS[pre].index(dst),
                    step=1, choices=MOD_DESTS[pre]))
            a(Param(f"{pre}.m{j+1}amt", f"Slot {j+1} amount", -1, 1, 0.0, unit="+-%"))
    for i in range(16):
        a(Param(f"dr.p{i+1}.tune", "Tune", -24, 24, 0, step=1, unit="st"))
        a(Param(f"dr.p{i+1}.decay", "Length", 0.02, 1, 1.0, unit="%"))
        a(Param(f"dr.p{i+1}.level", "Level", 0, 1, 0.8, unit="%"))
    a(Param("dr.filter", "Drum filter", 200, 20000, 20000, "exp", unit="Hz"))
    a(Param("dr.drive", "Drum drive", 0, 1, 0.0, unit="%"))
    a(Param("dr.vol", "Drums volume", 0, 1, 0.8, unit="%"))
    a(Param("m.master", "Master", 0, 1, 0.8, unit="%"))
    a(Param("m.drive", "Master drive", 0, 1, 0.0, unit="%"))
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
    for i, mc in enumerate(MACROS):
        a(Param(f"mc.{i+1}", mc[0], 0, 1, 0.5 if mc[2] == "bip" else 0.0, unit="djm" if mc[2] == "bip" else "%"))
    return {p.key: p for p in S}


SPECS = _build_specs()

PAGES = collections.OrderedDict([
    ("Perform", ["s1.cutoff", "s1.reso", "s1.envamt", "s1.fdecay", "s2.pos", "s2.cutoff", "s2.envamt", "s2.decay",
                 "dr.p1.tune", "dr.p1.decay", "dr.p3.tune", "dr.p5.decay", "dr.filter", "s1.vol", "s2.vol", "dr.vol"]),
    ("Macros", [f"mc.{i}" for i in range(1, 17)]),
    ("Synth 1", ["s1.cutoff", "s1.reso", "s1.envamt", "s1.fdecay", "s1.wave", "s1.pw", "s1.detune", "s1.sub",
                 "s1.attack", "s1.decay", "s1.sustain", "s1.release", "s1.glide", "s1.octave", "s1.drive", "s1.vol"]),
    ("Synth 1 Osc+", ["s1.osc2", "s1.fm", "s1.ring", "s1.sync", "s1.noise", "s1.chord", "s1.voicing", "s1.pan",
                      "s1.ftype", "s1.keytrk", "s1.velamp", "s1.drift", "s1.penv", "s1.pdec", "s1.glmode", "s1.vol"]),
    ("Synth 1 Mod", ["s1.l1shape", "s1.l1rate", "s1.l1sync", "s1.l2shape", "s1.l2rate", "s1.l2sync", "s1.mea", "s1.med"]
                    + [f"s1.m{j}amt" for j in range(1, 9)]),
    ("Synth 2", ["s2.pos", "s2.posenv", "s2.lforate", "s2.lfoamt", "s2.cutoff", "s2.reso", "s2.envamt", "s2.table",
                 "s2.attack", "s2.decay", "s2.sustain", "s2.release", "s2.glide", "s2.octave", "s2.detune", "s2.vol"]),
    ("Synth 2 Osc+", ["s2.chord", "s2.voicing", "s2.sub", "s2.noise", "s2.pan", "s2.drift", "s2.penv", "s2.pdec",
                      "s2.ftype", "s2.keytrk", "s2.velamp", "s2.glmode", "s2.table", "s2.pos", "s2.cutoff", "s2.vol"]),
    ("Synth 2 Mod", ["s2.l1shape", "s2.l1rate", "s2.l1sync", "s2.l2shape", "s2.l2rate", "s2.l2sync", "s2.mea", "s2.med"]
                    + [f"s2.m{j}amt" for j in range(1, 9)]),
    ("Drums 1-8", [f"dr.p{i}.tune" for i in range(1, 9)] + [f"dr.p{i}.decay" for i in range(1, 9)]),
    ("Drums 9-16", [f"dr.p{i}.tune" for i in range(9, 17)] + [f"dr.p{i}.decay" for i in range(9, 17)]),
    ("Mix", ["s1.vol", "s2.vol", "dr.vol", "m.master", "dr.filter", "dr.drive", "m.drive", "m.filter"]
            + [f"dr.p{i}.level" for i in range(1, 9)]),
    ("FX", ["fx.s1", "fx.s2", "fx.dr", "fx.time", "fx.fb", "fx.tone", "m.filter", "m.crush",
            "rv.s1", "rv.s2", "rv.dr", "rv.size", "rv.tone", "rv.level", "dr.filter", "m.drive"]),
])

PRESETS = {
    "s1": [
        ("Acid Bass", dict(wave=0, octave=-1, detune=0, sub=0, cutoff=300, reso=0.8, envamt=0.65, fdecay=0.18,
                           attack=0.001, decay=0.3, sustain=0.7, release=0.05, glide=0.08, drive=0.5)),
        ("Fat Saw Lead", dict(wave=0, octave=0, detune=18, sub=0.2, cutoff=2500, reso=0.25, envamt=0.3, fdecay=0.4,
                              attack=0.005, decay=0.8, sustain=0.8, release=0.25, glide=0.05, drive=0.2)),
        ("Square Bass", dict(wave=1, pw=0.5, octave=-1, detune=5, sub=0.6, cutoff=700, reso=0.3, envamt=0.4,
                             fdecay=0.2, attack=0.001, decay=0.25, sustain=0.5, release=0.08, drive=0.3)),
        ("Pluck", dict(wave=0.3, octave=0, detune=10, sub=0, cutoff=600, reso=0.35, envamt=0.75, fdecay=0.12,
                       attack=0.001, decay=0.25, sustain=0, release=0.2, drive=0.1)),
        ("Sub Bass", dict(wave=1, pw=0.5, octave=-1, detune=0, sub=0.9, cutoff=200, reso=0.1, envamt=0.1,
                          attack=0.003, decay=0.5, sustain=0.9, release=0.1, drive=0.1)),
        ("Soft Lead", dict(wave=0.5, pw=0.3, octave=0, detune=12, cutoff=1500, reso=0.2, envamt=0.2, fdecay=0.5,
                           attack=0.08, decay=1.0, sustain=0.7, release=0.6, glide=0.15, drive=0.05)),
        ("Sync Lead", dict(wave=0, sync=1, osc2=12, octave=0, cutoff=3200, reso=0.2, envamt=0.3, fdecay=0.4,
                           attack=0.003, decay=0.6, sustain=0.7, release=0.2, glide=0.08, mea=0.001, med=0.35,
                           m7dst=1, m7amt=0.6, drive=0.15)),
        ("FM Bass", dict(wave=0, fm=0.55, osc2=0, octave=-1, detune=0, sub=0.3, cutoff=800, reso=0.25, envamt=0.45,
                         fdecay=0.2, attack=0.001, decay=0.3, sustain=0.5, release=0.08, drive=0.4)),
        ("Wobble Bass", dict(wave=0.6, octave=-1, sub=0.6, ftype=1, cutoff=250, reso=0.55, envamt=0.1, l1sync=6,
                             m2amt=0.55, attack=0.002, decay=0.5, sustain=0.9, release=0.1, drive=0.5)),
        ("Minor 7 Stab", dict(chord=9, voicing=1, wave=0.3, octave=0, cutoff=900, reso=0.3, envamt=0.6, fdecay=0.15,
                              attack=0.001, decay=0.3, sustain=0, release=0.25, drift=0.3, drive=0.1)),
    ],
    "s2": [
        ("Glass Bell", dict(table=4, pos=0.4, posenv=0.3, lfoamt=0.1, cutoff=9000, reso=0.1, envamt=0.2,
                            attack=0.002, decay=1.2, sustain=0.2, release=1.0, detune=0.15, octave=1)),
        ("Vowel Lead", dict(table=1, pos=0.2, posenv=0, lforate=0.6, lfoamt=0.7, cutoff=6000, reso=0.1,
                            envamt=0.1, attack=0.02, decay=0.8, sustain=0.8, release=0.3, detune=0.2, octave=0)),
        ("Digital Bass", dict(table=5, octave=-1, pos=0.3, posenv=0.5, lfoamt=0, cutoff=1500, reso=0.4,
                              envamt=0.5, attack=0.001, decay=0.3, sustain=0.6, release=0.1, detune=0.05)),
        ("PWM Strings", dict(table=3, pos=0.2, posenv=0, lforate=0.3, lfoamt=0.6, cutoff=3000, reso=0.1,
                             envamt=0.1, attack=0.3, decay=1.5, sustain=0.8, release=1.2, detune=0.4, octave=0)),
        ("Harmonic Sweep", dict(table=2, pos=0, posenv=0.8, lfoamt=0, cutoff=8000, reso=0.1, envamt=0.1,
                                attack=0.01, decay=0.6, sustain=0.3, release=0.5, detune=0.25, octave=0)),
        ("Warm Pad", dict(table=0, pos=0.35, posenv=0, lforate=0.2, lfoamt=0.3, cutoff=1800, reso=0.15,
                          envamt=0.1, attack=0.6, decay=2, sustain=0.9, release=2, detune=0.5, octave=0)),
        ("Chord Pad", dict(table=0, pos=0.4, posenv=0, chord=8, voicing=1, attack=0.5, decay=2, sustain=0.85,
                           release=1.6, cutoff=2500, reso=0.1, envamt=0.1, detune=0.4, drift=0.4, l2shape=6, l2rate=0.3,
                           m3amt=0.35, m6amt=0.3, octave=0)),
        ("Chip Lead", dict(table=12, pos=0.2, posenv=0, lfoamt=0, cutoff=9000, reso=0.1, envamt=0.1, attack=0.001,
                           decay=0.25, sustain=0.7, release=0.1, glide=0.03, glmode=1, octave=1, l1rate=5.5,
                           m1amt=0.02, detune=0.05)),
        ("Voice Choir", dict(table=9, pos=0.5, posenv=0, lforate=0.2, lfoamt=0.3, chord=3, attack=0.4, decay=1.5,
                             sustain=0.8, release=1.2, cutoff=5000, reso=0.1, envamt=0.1, detune=0.5, drift=0.6,
                             octave=0)),
        ("Granular Drone", dict(table=10, pos=0.3, posenv=0, lfoamt=0, l2shape=6, l2rate=0.15, m3amt=0.7, attack=1.0,
                                decay=3, sustain=1, release=2.5, cutoff=3000, reso=0.3, envamt=0.1, detune=0.6, sub=0.3,
                                octave=-1)),
    ],
}


SUBPAGES = {"Synth 1": ["Synth 1", "Synth 1 Osc+", "Synth 1 Mod"], "Synth 2": ["Synth 2", "Synth 2 Osc+", "Synth 2 Mod"]}
SUBPAGE_NAMES = ["Main", "Osc+", "Mod"]
HIDDEN_PAGES = {p for subs in SUBPAGES.values() for p in subs[1:]}


class ParamStore:
    """Holds every parameter as a normalized 0..1 value plus a cached real value."""

    # norm = your setting (0..1), mod = what the macros add on top, val = the real value the
    # engine plays (setting + macros). Presets, saves and the knob pages work on norm.
    def __init__(self):
        self.norm = {}
        self.val = {}
        self.mod = {}
        for k, p in SPECS.items():
            self.set_val(k, p.default)

    def shown(self, key):
        return min(max(self.norm[key] + self.mod.get(key, 0.0), 0.0), 1.0)

    def base_val(self, key):
        return SPECS[key].to_val(self.norm[key])

    def _apply(self, key):
        self.val[key] = SPECS[key].to_val(self.shown(key))

    def set_norm(self, key, n):
        n = min(max(float(n), 0.0), 1.0)
        self.norm[key] = n
        self._apply(key)
        if key.startswith("mc."):
            self.recompute_macros()

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
        if p.step:
            self.set_val(key, self.val[key] + direction * p.step)
        else:
            self.set_norm(key, self.norm[key] + direction / 20.0)

    def apply_preset(self, pre, values):
        for k, p in SPECS.items():
            if k.startswith(pre + ".") and not k.endswith(".vol"):
                self.set_val(k, p.default)
        for k, v in values.items():
            self.set_val(f"{pre}.{k}", v)

    def randomize(self, pre, rng=None):
        rng = rng or np.random.default_rng()
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
    def __init__(self, sr):
        self.sr = sr
        self.v = 0.0
        self.stage = 0  # 0 idle, 1 attack, 2 decay/sustain, 3 release

    def gate_on(self):
        self.stage = 1

    def gate_off(self):
        if self.stage:
            self.stage = 3

    def render(self, n, a, d, s, r):
        out = np.empty(n)
        i, sr = 0, self.sr
        while i < n:
            if self.stage == 0:
                out[i:] = 0.0
                self.v = 0.0
                break
            if self.stage == 1:
                inc = 1.0 / max(a * sr, 1.0)
                m = min(int(math.ceil((1.0 - self.v) / inc)), n - i)
                if m <= 0:
                    self.v, self.stage = 1.0, 2
                    continue
                seg = np.minimum(self.v + inc * np.arange(1, m + 1), 1.0)
                out[i:i + m] = seg
                self.v = float(seg[-1])
                i += m
                if self.v >= 1.0 - 1e-9:
                    self.v, self.stage = 1.0, 2
            elif self.stage == 2:
                k = math.exp(-4.6 / max(d * sr, 1.0))
                seg = s + (self.v - s) * k ** np.arange(1, n - i + 1)
                out[i:] = seg
                self.v = float(seg[-1])
                break
            else:
                k = math.exp(-4.6 / max(r * sr, 1.0))
                seg = self.v * k ** np.arange(1, n - i + 1)
                out[i:] = seg
                self.v = float(seg[-1])
                if self.v < 1e-5:
                    self.v, self.stage = 0.0, 0
                break
        return out


# ----------------------------------------------------------------------------- modulation
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
        self.ptime = 10 ** 9
        self.drift_val = np.zeros(self.MAXV)
        self.drift_tgt = self.rng.uniform(-1, 1, self.MAXV)
        self.active = 0.0

    # ---- notes
    def note_on(self, note, vel):
        v = self.eng.p.val
        legato = bool(self.held) and self.amp.stage in (1, 2)
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
            self.ptime = 0
            self.amp.gate_on()
            self.fenv.gate_on()
            self.menv.gate_on()
        self.active = 1.0

    def note_off(self, note):
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
        v = self.eng.p.val
        ints = list(CHORDS[int(v[self.pre + ".chord"])][1])
        voicing = int(v[self.pre + ".voicing"])
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
        for j in range(1, 9):
            amt = v[f"{pre}.m{j}amt"]
            si = int(v[f"{pre}.m{j}src"])
            if si == 0 or abs(amt) < 1e-4:
                continue
            name = MOD_SOURCES[si]
            if name.startswith("LFO"):
                L = int(name[-1]) - 1
                if lfo[L] is None:
                    lfo[L] = self.lfos[L].render(n, self.sr, self.lfo_hz(L + 1), int(v[f"{pre}.l{L+1}shape"]))
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

    def filt(self, x, fe, mods):
        v = self.eng.p.val
        pre = self.pre
        ftype = int(v[pre + ".ftype"])
        if ftype != self.ftype:
            self.zi = np.zeros_like(self.zi)
            self.ftype = ftype
        reso0 = v[pre + ".reso"]
        base = v[pre + ".cutoff"] * 2.0 ** ((self.cur - 60.0) / 12.0 * v[pre + ".keytrk"])
        amt = v[pre + ".envamt"] * 7.0
        mc = mods.get("Cutoff", 0.0)
        mr = mods.get("Resonance", 0.0)
        y = np.empty_like(x)
        n = len(x)
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

    def envs(self, n, fdecay):
        v = self.eng.p.val
        pre = self.pre
        a = v[pre + ".attack"]
        ae = self.amp.render(n, a, v[pre + ".decay"], v[pre + ".sustain"], v[pre + ".release"])
        fe = self.fenv.render(n, a, fdecay, 0.0, fdecay)
        me = self.menv.render(n, v[pre + ".mea"], v[pre + ".med"], 0.0, v[pre + ".med"])
        return ae, fe, me

    def idle(self, n):
        for L in (0, 1):
            self.lfos[L].ph = (self.lfos[L].ph + n * self.lfo_hz(L + 1) / self.sr) % 1.0

    def finish(self, y, ae, mods, vol_key):
        """Velocity, volume, tremolo and pan -> stereo (n, 2)."""
        v = self.eng.p.val
        pre = self.pre
        va = v[pre + ".velamp"]
        gain = ae * ((1.0 - va + va * self.vel_raw) * v[vol_key] * 0.6)
        if "Volume" in mods:
            gain = gain * np.clip(1.0 + mods["Volume"], 0.0, 2.0)
        pan = np.clip(v[pre + ".pan"] + mods.get("Pan", 0.0), -1.0, 1.0)
        th = (pan + 1.0) * (math.pi / 4.0)
        gl = np.cos(th) * math.sqrt(2.0)
        gr = np.sin(th) * math.sqrt(2.0)
        if y.ndim == 1:
            return np.stack([y * gain * gl, y * gain * gr], axis=1)
        return np.stack([y[:, 0] * gain * gl, y[:, 1] * gain * gr], axis=1)


def _osc(t, d, wave, pw):
    saw = 2.0 * t - 1.0 - polyblep(t, d)
    if not isinstance(wave, np.ndarray) and wave <= 0.001:
        return saw
    pulse = np.where(t < pw, 1.0, -1.0) + polyblep(t, d) - polyblep((t - pw) % 1.0, d) - (2 * pw - 1)
    return (1 - wave) * saw + wave * pulse


class OscSynth(MonoSynth):
    def __init__(self, eng, pre="s1"):
        super().__init__(eng, pre, 1)
        self.ph = np.zeros((self.MAXV, 3))

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
        x = np.zeros(n)
        use_fm = isinstance(fm, np.ndarray) or fm > 0.001
        use_ring = isinstance(ring, np.ndarray) or ring > 0.001
        for vi, iv in enumerate(ints):
            ph = self.ph[vi]
            f1 = 440.0 * 2.0 ** ((sem + iv + drift[vi] - 69.0) / 12.0)
            dt1 = f1 / self.sr
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
            mix = (o1 + o2) * 0.5
            if use_ring:
                mix = mix * (1.0 - ring) + o1 * o2 * ring
            if sub > 0.001:
                ts = (ph[2] + np.cumsum(dt1 * 0.5)) % 1.0
                ph[2] = ts[-1]
                mix = mix + sub * np.sin(TWO_PI * ts)
            x += mix
        if len(ints) > 1:
            x /= math.sqrt(len(ints))
        noise = v["s1.noise"] + _mean(mods.get("Noise", 0.0))
        if noise > 0.001:
            x += min(noise, 1.0) * 0.8 * self.rng.uniform(-1.0, 1.0, n)
        y = self.filt(x, fe, mods)
        drv = min(max(v["s1.drive"] + _mean(mods.get("Drive", 0.0)), 0.0), 1.0)
        g = 1.0 + 4.0 * drv
        y = np.tanh(y * g) / math.tanh(g) * 0.8
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
        self.lfo = 0.0

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
        det = min(max(v["s2.detune"] + _mean(mods.get("Unison", 0.0)), 0.0), 1.0) * 30.0
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
        ints = self.chord()
        drift = self.drift(n)
        L = np.zeros(n)
        R = np.zeros(n)
        for vi, iv in enumerate(ints):
            ph = self.ph[vi]
            f = 440.0 * 2.0 ** ((sem + iv + drift[vi] - 69.0) / 12.0)
            chans = []
            for idx, cents in enumerate((-det, det)):
                dt = f * 2.0 ** (cents / 1200.0) / self.sr
                p = (ph[idx] + np.cumsum(dt)) % 1.0
                ph[idx] = p[-1]
                hmax = 0.45 / max(float(dt.max()), 1e-9)
                li = next((i for i, hh in enumerate(self.levels) if hh <= hmax), len(self.levels) - 1)
                tb = tables[li]
                x = p * self.N
                xi = x.astype(np.int64)
                xf = x - xi
                a = tb[fi, xi] * (1 - xf) + tb[fi, xi + 1] * xf
                b = tb[fi + 1, xi] * (1 - xf) + tb[fi + 1, xi + 1] * xf
                chans.append(a * (1 - ff) + b * ff)
            L += chans[0] * 0.75 + chans[1] * 0.25
            R += chans[0] * 0.25 + chans[1] * 0.75
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
        y = self.filt(x, fe, mods)
        y = np.tanh(y * 1.2)
        return self.finish(y, ae, mods, "s2.vol")


def load_wav(path, sr):
    from scipy.io import wavfile
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


class Drums:
    CHOKE = {4: [5]}  # closed hat (pad 5) chokes open hat (pad 6)

    def __init__(self, eng):
        self.eng, self.sr = eng, eng.sr
        self.voices = []
        self.zi = np.zeros((1, 2, 2))
        self.active = [0.0] * 16
        self.kit_index = 0
        self.kit_name = ""
        self.load_factory(0)

    # Each pad remembers where its sound came from, so any kit (and any edit) can be saved and rebuilt:
    #   {"factory": kit_index, "pad": n}  or  {"file": path, "label": name}
    def load_factory(self, index):
        from potentialbox import kits
        names, samples = kits.build(index, self.sr)
        self.kit_index = int(index) % len(kits.KITS)
        self.kit_name = kits.NAMES[self.kit_index]
        self.samples, self.names = list(samples), list(names)
        self.sources = [{"factory": self.kit_index, "pad": i} for i in range(16)]

    def use_builtin(self):
        self.load_factory(0)

    def _read(self, path):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return load_wav(path, self.sr)

    def load_sources(self, sources, name):
        """Rebuild a kit from 16 source entries (custom kits, My Kits). Returns pads loaded from files."""
        from potentialbox import kits
        samples, names, srcs, n = [], [], [], 0
        for i in range(16):
            src = sources[i] if i < len(sources) and isinstance(sources[i], dict) else {"factory": 0, "pad": i}
            if "file" in src:
                try:
                    samples.append(self._read(src["file"]))
                    names.append(src.get("label") or os.path.splitext(os.path.basename(src["file"]))[0][:14])
                    srcs.append(dict(src))
                    n += 1
                    continue
                except Exception:
                    src = {"factory": 0, "pad": i}
            k, p = int(src.get("factory", 0)), int(src.get("pad", i)) % 16
            fn, fs = kits.build(k, self.sr)
            samples.append(fs[p])
            names.append(fn[p])
            srcs.append({"factory": k, "pad": p})
        self.samples, self.names, self.sources, self.kit_name = samples, names, srcs, name
        return n

    def set_pad(self, pad, path, label):
        """Put one WAV on one pad. Raises if the file can't be read."""
        x = self._read(path)
        pad %= 16
        samples, names, sources = list(self.samples), list(self.names), list(self.sources)
        samples[pad], names[pad] = x, label
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

    def trigger(self, pad, vel):
        pad %= 16
        for c in self.CHOKE.get(pad, []):
            for v in self.voices:
                if v[0] == c:
                    v[5] = True
        val = self.eng.p.val
        rate = 2.0 ** (val[f"dr.p{pad+1}.tune"] / 12.0)
        dec = val[f"dr.p{pad+1}.decay"]
        M = len(self.samples[pad])
        if dec >= 0.99:
            k = 1.0
        else:
            tau = max(dec * dec * M / 2.0 / rate, 0.004 * self.sr)
            k = math.exp(-1.0 / tau)
        gain = val[f"dr.p{pad+1}.level"] * (vel / 127.0) ** 1.2
        # [pad, pos, rate, gain, env, choking, k]
        self.voices.append([pad, 0.0, rate, gain, 1.0, False, k])
        if len(self.voices) > 32:
            self.voices.pop(0)
        self.active[pad] = 1.0

    def render(self, n):
        if not self.voices:
            return None
        out = np.zeros((n, 2))
        ar = np.arange(n)
        alive = []
        for v in self.voices:
            pad, pos, rate, gain, e, choking, k = v
            s = self.samples[pad]
            M = len(s) - 1
            m = min(n, int(math.ceil((M - pos) / rate)))
            if m <= 0:
                continue
            p = pos + rate * ar[:m]
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
            out[:m, 0] += y
            out[:m, 1] += y
            v[1] = pos + rate * n
            v[4] = e
            if m == n and e > 1e-4:
                alive.append(v)
        self.voices = alive
        val = self.eng.p.val
        fc = val["dr.filter"]
        if fc < 19000:
            sos = np.array([lp_coeffs(fc, 0.9, self.sr)])
            out, self.zi = sosfilt(sos, out, axis=0, zi=self.zi)
        d = val["dr.drive"]
        if d > 0.01:
            g = 1 + 6 * d
            out = np.tanh(out * g) / math.tanh(g)
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
        self.events = collections.deque()
        self.bpm = 120.0
        self.peak = 0.0

    # thread-safe entry points (MIDI / GUI threads)
    def note_on(self, target, note, vel=100):
        self.events.append((target, "on", note, vel))

    def note_off(self, target, note):
        self.events.append((target, "off", note, 0))

    def panic(self):
        self.events.append(("all", "panic", 0, 0))

    def _dispatch(self):
        ev = self.events
        while ev:
            target, kind, note, vel = ev.popleft()
            if kind == "panic":
                self.s1.all_off()
                self.s2.all_off()
                self.drums.voices = []
                continue
            if target == "dr":
                if kind == "on" and vel > 0:
                    self.drums.trigger(note, vel)
                continue
            syn = self.s1 if target == "s1" else self.s2
            if kind == "on" and vel > 0:
                syn.note_on(note, vel)
            else:
                syn.note_off(note)

    def render(self, n):
        self._dispatch()
        v = self.p.val
        out = np.zeros((n, 2))
        send = np.zeros((n, 2))
        rsend = np.zeros((n, 2))
        a = self.s1.render(n)
        if a is not None:
            out += a
            send += a * v["fx.s1"]
            rsend += a * v["rv.s1"]
        b = self.s2.render(n)
        if b is not None:
            out += b
            send += b * v["fx.s2"]
            rsend += b * v["rv.s2"]
        c = self.drums.render(n)
        if c is not None:
            out += c
            send += c * v["fx.dr"]
            rsend += c * v["rv.dr"]
        secs = DIVISIONS[int(v["fx.time"])][1] * 60.0 / max(self.bpm, 30.0)
        d = self.delay.process(send, secs, v["fx.fb"], v["fx.tone"])
        out += d
        rsend += d * 0.3
        r = self.reverb.process(rsend, v["rv.size"], v["rv.tone"], v["rv.level"])
        if r is not None:
            out += r
        out = self.master.process(out, v["m.filter"], v["m.crush"])
        g = 1.0 + 4.0 * v["m.drive"]
        out = np.tanh(out * (v["m.master"] * g)) if g > 1.01 else np.tanh(out * v["m.master"])
        pk = float(np.max(np.abs(out))) if n else 0.0
        self.peak = max(pk, self.peak * 0.9)
        return out.astype(np.float32)
