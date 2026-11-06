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
TABLE_NAMES = ["Analog", "Vowel", "Harmonic", "PWM", "FM Bell", "Digital"]
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
    ("Synth 2", ["s2.pos", "s2.posenv", "s2.lforate", "s2.lfoamt", "s2.cutoff", "s2.reso", "s2.envamt", "s2.table",
                 "s2.attack", "s2.decay", "s2.sustain", "s2.release", "s2.glide", "s2.octave", "s2.detune", "s2.vol"]),
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
    ],
}


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
        for k in SPECS:
            if k.startswith(pre + ".") and not k.endswith(".vol") and not k.endswith(".octave"):
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


class MonoSynth:
    """Mono voice handling shared by both synths. Tied/slid steps from the BeatStep Pro
    arrive as overlapping notes -> legato with glide, no envelope retrigger."""

    SUB = 32

    def __init__(self, eng, pre, channels):
        self.eng, self.pre, self.sr = eng, pre, eng.sr
        self.held = []
        self.cur = self.tgt = 48.0
        self.sliding = False
        self.vel = 1.0
        self.amp = ADSR(self.sr)
        self.fenv = ADSR(self.sr)
        self.zi = np.zeros((2, 2, channels)) if channels > 1 else np.zeros((2, 2))
        self.active = 0.0  # for GUI activity light

    def note_on(self, note, vel):
        legato = bool(self.held) and self.amp.stage in (1, 2)
        if note in self.held:
            self.held.remove(note)
        self.held.append(note)
        self.tgt = float(note)
        if legato:
            self.sliding = True
        else:
            self.cur = self.tgt
            self.sliding = False
            self.vel = 0.35 + 0.65 * (vel / 127.0)
            self.amp.gate_on()
            self.fenv.gate_on()
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

    def all_off(self):
        self.held = []
        self.amp.gate_off()
        self.fenv.gate_off()

    def pitch(self, n):
        v = self.eng.p.val
        if self.sliding and abs(self.tgt - self.cur) > 1e-4:
            k = math.exp(-3.0 / max(v[self.pre + ".glide"] * self.sr, 1.0))
            sem = self.tgt + (self.cur - self.tgt) * k ** np.arange(1, n + 1)
            self.cur = float(sem[-1])
        else:
            self.cur = self.tgt
            sem = np.full(n, self.tgt)
        sem = sem + 12.0 * v[self.pre + ".octave"]
        return 440.0 * 2.0 ** ((sem - 69.0) / 12.0)

    def filt(self, x, fe):
        v = self.eng.p.val
        pre = self.pre
        q2 = 0.707 + (v[pre + ".reso"] ** 2) * 11.0
        base = v[pre + ".cutoff"]
        amt = v[pre + ".envamt"] * 7.0
        y = np.empty_like(x)
        n = len(x)
        for j in range(0, n, self.SUB):
            e = j + self.SUB
            fc = base * 2.0 ** (amt * fe[min(j + self.SUB // 2, n - 1)])
            sos = np.array([lp_coeffs(fc, 0.707, self.sr), lp_coeffs(fc, q2, self.sr)])
            y[j:e], self.zi = sosfilt(sos, x[j:e], axis=0, zi=self.zi)
        return y / (1.0 + 0.6 * v[pre + ".reso"])

    def envs(self, n, fdecay):
        v = self.eng.p.val
        pre = self.pre
        a = v[pre + ".attack"]
        ae = self.amp.render(n, a, v[pre + ".decay"], v[pre + ".sustain"], v[pre + ".release"])
        fe = self.fenv.render(n, a, fdecay, 0.0, fdecay)
        return ae, fe


class OscSynth(MonoSynth):
    def __init__(self, eng, pre="s1"):
        super().__init__(eng, pre, 1)
        self.ph = np.zeros(3)

    def render(self, n):
        if self.amp.stage == 0:
            return None
        v = self.eng.p.val
        f = self.pitch(n)
        dt = f / self.sr
        dt2 = dt * 2.0 ** (v["s1.detune"] / 1200.0)
        out = []
        for idx, d in enumerate((dt, dt2, dt * 0.5)):
            ph = (self.ph[idx] + np.cumsum(d)) % 1.0
            self.ph[idx] = ph[-1]
            out.append(ph)
        wave, pw = v["s1.wave"], v["s1.pw"]

        def osc(t, d):
            saw = 2.0 * t - 1.0 - polyblep(t, d)
            if wave <= 0.001:
                return saw
            pulse = np.where(t < pw, 1.0, -1.0) + polyblep(t, d) - polyblep((t - pw) % 1.0, d) - (2 * pw - 1)
            return (1 - wave) * saw + wave * pulse

        x = 0.5 * (osc(out[0], dt) + osc(out[1], dt2)) + v["s1.sub"] * np.sin(TWO_PI * out[2])
        ae, fe = self.envs(n, v["s1.fdecay"])
        y = self.filt(x, fe)
        g = 1.0 + 4.0 * v["s1.drive"]
        y = np.tanh(y * g) / math.tanh(g) * 0.8
        return y * ae * (self.vel * v["s1.vol"] * 0.6)


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
        x = p * (len(dig_keys) - 1)
        i = min(int(x), len(dig_keys) - 2)
        f = x - i
        return ((1 - f) * dig_keys[i] + f * dig_keys[i + 1]) * rphase * N / 2

    bank = []
    for s in range(len(TABLE_NAMES)):
        arr = np.zeros((len(harm_levels), F, N + 1), dtype=np.float32)
        for fi in range(F):
            X = spectrum(s, fi / (F - 1))
            full = np.fft.irfft(np.where(k <= harm_levels[0], X, 0), N)
            norm = 1.0 / max(np.max(np.abs(full)), 1e-9)
            for li, H in enumerate(harm_levels):
                y = np.fft.irfft(np.where(k <= H, X, 0), N) * norm
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
        self.ph = np.zeros(2)
        self.lfo = 0.0

    def render(self, n):
        if self.amp.stage == 0:
            self.lfo = (self.lfo + n * self.eng.p.val["s2.lforate"] / self.sr) % 1.0
            return None
        v = self.eng.p.val
        f = self.pitch(n)
        det = v["s2.detune"] * 30.0
        ae, fe = self.envs(n, v["s2.decay"])
        lfo_ph = self.lfo + np.arange(1, n + 1) * (v["s2.lforate"] / self.sr)
        self.lfo = float(lfo_ph[-1] % 1.0)
        pos = v["s2.pos"] + v["s2.posenv"] * fe + v["s2.lfoamt"] * 0.5 * np.sin(TWO_PI * lfo_ph)
        np.clip(pos, 0.0, 1.0, out=pos)
        tables = self.bank[int(v["s2.table"])]
        F = tables.shape[1]
        fpos = pos * (F - 1)
        fi = np.minimum(fpos.astype(np.int64), F - 2)
        ff = fpos - fi
        chans = []
        for idx, cents in enumerate((-det, det)):
            dt = f * 2.0 ** (cents / 1200.0) / self.sr
            ph = (self.ph[idx] + np.cumsum(dt)) % 1.0
            self.ph[idx] = ph[-1]
            hmax = 0.45 / max(float(dt.max()), 1e-9)
            li = next((i for i, h in enumerate(self.levels) if h <= hmax), len(self.levels) - 1)
            tb = tables[li]
            x = ph * self.N
            xi = x.astype(np.int64)
            xf = x - xi
            a = tb[fi, xi] * (1 - xf) + tb[fi, xi + 1] * xf
            b = tb[fi + 1, xi] * (1 - xf) + tb[fi + 1, xi + 1] * xf
            chans.append(a * (1 - ff) + b * ff)
        L = chans[0] * 0.75 + chans[1] * 0.25
        R = chans[0] * 0.25 + chans[1] * 0.75
        x = np.stack([L, R], axis=1)
        y = self.filt(x, fe)
        y = np.tanh(y * 1.2)
        return y * (ae * (self.vel * v["s2.vol"] * 0.6))[:, None]


# ----------------------------------------------------------------------------- drums
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
            out += a[:, None]
            send += a[:, None] * v["fx.s1"]
            rsend += a[:, None] * v["rv.s1"]
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
