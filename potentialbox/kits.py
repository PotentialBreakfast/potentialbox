"""Synthesized drum machine kits for PotentialBox.

Every kit uses the same pad layout so BeatStep Pro drum patterns carry over:
 1 Kick  2 Kick 2  3 Snare  4 Clap  5 Closed Hat  6 Open Hat  7-9 Toms (low/mid/high)
10 Rim  11-13 Percussion  14 Cymbal  15 FX  16 Perc
Pad 5 chokes pad 6 in every kit.
"""
import math

import numpy as np
from scipy.signal import lfilter, butter

TWO_PI = 2.0 * math.pi
METAL = (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)


class Gen:
    def __init__(self, sr, seed=3):
        self.sr = sr
        self.rng = np.random.default_rng(seed)

    def t(self, dur):
        return np.arange(max(1, int(dur * self.sr))) / self.sr

    def noise(self, n):
        return self.rng.uniform(-1, 1, n)

    def _f(self, fc):
        return min(max(fc / (self.sr / 2), 1e-4), 0.99)

    def hp(self, x, fc, order=2):
        return lfilter(*butter(order, self._f(fc), "high"), x)

    def lp(self, x, fc, order=2):
        return lfilter(*butter(order, self._f(fc), "low"), x)

    def bp(self, x, lo, hi):
        return lfilter(*butter(2, [self._f(lo), self._f(hi)], "band"), x)

    def sweep(self, t, f0, f1, tau):
        f = f1 + (f0 - f1) * np.exp(-t / tau)
        return np.sin(TWO_PI * np.cumsum(f) / self.sr)

    def metal(self, t, scale=1.0):
        return sum(np.sign(np.sin(TWO_PI * f * 2.2 * scale * t)) for f in METAL) / 6.0


def _drive(x, amt):
    if amt <= 0:
        return x
    g = 1 + amt * 6
    return np.tanh(x * g) / math.tanh(g)


# ---------------------------------------------------------------- voices
def kick(g, f0=160, f1=48, sweep=0.035, decay=0.18, click=0.3, drive=0.0, dur=0.6):
    t = g.t(dur)
    y = g.sweep(t, f0, f1, sweep) * np.exp(-t / decay)
    if click:
        y = y + click * g.hp(g.noise(len(t)), 1500) * np.exp(-t / 0.003)
    return _drive(y, drive)


def snare(g, f=185, f2=None, tone=0.6, tdecay=0.06, noise=0.7, ndecay=0.09, hp=1500, dur=0.35, gate=None, drive=0.0):
    t = g.t(dur)
    body = g.sweep(t, f * 1.3, f, 0.02)
    if f2:
        body = body + 0.6 * np.sin(TWO_PI * f2 * t)
    y = tone * body * np.exp(-t / tdecay) + noise * g.hp(g.noise(len(t)), hp) * np.exp(-t / ndecay)
    if gate:
        y = y * np.clip((gate - t) / 0.006, 0, 1)
    return _drive(y, drive)


def clap(g, tail=0.12, lo=800, hi=2200, n=3, spacing=0.011, dur=0.5):
    t = g.t(dur)
    burst = np.zeros(len(t))
    for i in range(n):
        off = i * spacing
        burst += (t >= off) * np.exp(-np.clip(t - off, 0, None) / 0.004)
    env = burst * 0.6 + np.exp(-t / tail) * (t > n * spacing)
    return g.bp(g.noise(len(t)), lo, hi) * env


def hat(g, decay=0.03, metal=0.6, nz=0.6, hp=7000, scale=1.0, dur=None):
    t = g.t(dur or max(0.12, decay * 5))
    x = metal * g.metal(t, scale) + nz * g.noise(len(t))
    return g.hp(x, hp) * np.exp(-t / decay)


def tom(g, f=130, decay=0.18, bend=1.4, noise=0.0, dur=0.6):
    t = g.t(dur)
    y = g.sweep(t, f * bend, f, 0.04) * np.exp(-t / decay)
    if noise:
        y = y + noise * g.lp(g.noise(len(t)), 3000) * np.exp(-t / (decay * 0.4))
    return y


def rim(g, f1=1700, f2=480, decay=0.008):
    t = g.t(0.06)
    return (np.sin(TWO_PI * f1 * t) + 0.5 * np.sin(TWO_PI * f2 * t)) * np.exp(-t / decay) \
        + 0.3 * g.hp(g.noise(len(t)), 3000) * np.exp(-t / 0.003)


def cowbell(g, f1=540, f2=800, decay=0.08):
    t = g.t(max(0.3, decay * 5))
    x = np.sign(np.sin(TWO_PI * f1 * t)) + np.sign(np.sin(TWO_PI * f2 * t))
    return g.bp(x, 400, 3000) * np.exp(-t / decay)


def clave(g, f=2500, decay=0.015):
    t = g.t(0.1)
    return np.sin(TWO_PI * f * t) * np.exp(-t / decay)


def shaker(g, decay=0.04, att=0.015):
    t = g.t(max(0.15, decay * 5))
    return g.hp(g.noise(len(t)), 5000) * (1 - np.exp(-t / att)) * np.exp(-t / decay)


def cymbal(g, decay=0.55, scale=1.3, hp=4000, dur=2.0):
    t = g.t(dur)
    return g.hp(0.5 * g.metal(t, scale) + 0.8 * g.noise(len(t)), hp) * np.exp(-t / decay)


def zap(g, f0=2500, f1=90, tau=0.025, decay=0.06):
    t = g.t(max(0.15, decay * 4))
    return g.sweep(t, f0, f1, tau) * np.exp(-t / decay)


def conga(g, f0=330, f1=210, decay=0.09):
    t = g.t(max(0.25, decay * 4))
    return g.sweep(t, f0, f1, 0.008) * np.exp(-t / decay)


def blip(g, f=1200, decay=0.03):
    t = g.t(max(0.06, decay * 5))
    return np.sin(TWO_PI * f * t) * np.exp(-t / decay)


# ---------------------------------------------------------------- kits
K = lambda name, fn, **kw: (name, fn, kw)  # noqa: E731

KITS = [
    dict(name="Potential", desc="The original all-rounder", pads=[
        K("Kick", kick), K("808", kick, f0=70, f1=43, sweep=0.06, decay=0.5, click=0, drive=0.25, dur=1.6),
        K("Snare", snare), K("Clap", clap), K("Closed Hat", hat), K("Open Hat", hat, decay=0.2, dur=0.8),
        K("Low Tom", tom, f=95), K("Mid Tom", tom, f=135), K("High Tom", tom, f=185), K("Rim", rim),
        K("Cowbell", cowbell), K("Clave", clave), K("Shaker", shaker), K("Crash", cymbal), K("Zap", zap),
        K("Conga", conga)]),
    dict(name="808 Boom", desc="Round booming kick, classic metal hats", pads=[
        K("Kick", kick, f0=110, f1=50, sweep=0.02, decay=0.35, click=0.05, dur=1.2),
        K("Sub Kick", kick, f0=60, f1=45, sweep=0.03, decay=0.8, click=0, dur=2.0),
        K("Snare", snare, f=238, f2=476, tone=0.7, tdecay=0.08, noise=0.5, ndecay=0.12, hp=2000),
        K("Clap", clap, tail=0.15, lo=900, hi=1800, n=4, spacing=0.01),
        K("Closed Hat", hat, decay=0.025, metal=1.0, nz=0.1), K("Open Hat", hat, decay=0.25, metal=1.0, nz=0.1, dur=1.0),
        K("Low Tom", tom, f=80, decay=0.3, bend=1.15), K("Mid Tom", tom, f=120, decay=0.28, bend=1.15),
        K("High Tom", tom, f=165, decay=0.25, bend=1.15), K("Rim", rim, f1=1667, f2=455, decay=0.006),
        K("Cowbell", cowbell, decay=0.1), K("Clave", clave, decay=0.02), K("Maracas", shaker, decay=0.025, att=0.003),
        K("Cymbal", cymbal, decay=1.0, scale=1.0), K("Lo Conga", conga, f0=250, f1=220, decay=0.13),
        K("Hi Conga", conga, f0=370, f1=330, decay=0.1)]),
    dict(name="909 Punch", desc="Clicky driven kick, noisy snare, rides", pads=[
        K("Kick", kick, f0=230, f1=52, sweep=0.018, decay=0.22, click=0.6, drive=0.35, dur=0.7),
        K("Long Kick", kick, f0=200, f1=48, sweep=0.02, decay=0.4, click=0.4, drive=0.5, dur=1.0),
        K("Snare", snare, f=200, tone=0.45, tdecay=0.04, noise=1.0, ndecay=0.15, hp=1200),
        K("Clap", clap, tail=0.18, lo=700, hi=2500, spacing=0.012),
        K("Closed Hat", hat, decay=0.04, metal=0.3, nz=1.0, hp=8000),
        K("Open Hat", hat, decay=0.3, metal=0.3, nz=1.0, hp=8000, dur=1.0),
        K("Low Tom", tom, f=100, decay=0.25, bend=1.6, noise=0.15), K("Mid Tom", tom, f=140, decay=0.22, bend=1.6, noise=0.15),
        K("High Tom", tom, f=190, decay=0.2, bend=1.6, noise=0.15), K("Rim", rim, f1=1900, f2=600, decay=0.01),
        K("Ride", cymbal, decay=1.2, scale=1.7, hp=5000, dur=2.5), K("Clave", clave), K("Shaker", shaker),
        K("Crash", cymbal, decay=1.5, scale=1.2, hp=3500, dur=2.5), K("Zap", zap), K("Conga", conga)]),
    dict(name="606 Tight", desc="Small, snappy and crisp", pads=[
        K("Kick", kick, f0=140, f1=60, sweep=0.015, decay=0.12, click=0.2, dur=0.4),
        K("Kick 2", kick, f0=120, f1=55, sweep=0.02, decay=0.2, click=0.1, dur=0.6),
        K("Snare", snare, f=260, tone=0.4, tdecay=0.03, noise=0.9, ndecay=0.07, hp=2500),
        K("Clap", clap, tail=0.08, lo=1000, hi=3000),
        K("Closed Hat", hat, decay=0.018, metal=0.8, nz=0.4, hp=9000),
        K("Open Hat", hat, decay=0.12, metal=0.8, nz=0.4, hp=9000, dur=0.5),
        K("Low Tom", tom, f=130, decay=0.12, bend=1.3), K("Mid Tom", tom, f=180, decay=0.11, bend=1.3),
        K("High Tom", tom, f=240, decay=0.1, bend=1.3), K("Rim", rim), K("Cowbell", cowbell, f1=600, f2=900, decay=0.05),
        K("Clave", clave), K("Shaker", shaker, decay=0.03), K("Cymbal", cymbal, decay=0.4, scale=1.5, hp=6000, dur=1.2),
        K("Blip", blip), K("Conga", conga, decay=0.07)]),
    dict(name="Trap 808", desc="Punch kick, long distorted 808 to tune", pads=[
        K("Punch Kick", kick, f0=180, f1=55, sweep=0.015, decay=0.15, click=0.5, drive=0.4, dur=0.5),
        K("808 Long", kick, f0=90, f1=41, sweep=0.05, decay=1.2, click=0.05, drive=0.6, dur=3.0),
        K("Snare", snare, f=210, tone=0.5, tdecay=0.05, noise=0.9, ndecay=0.12, hp=1800, drive=0.3),
        K("Clap", clap, tail=0.2, lo=900, hi=3000, n=4, spacing=0.008),
        K("Closed Hat", hat, decay=0.02, metal=0.4, nz=1.0, hp=9500),
        K("Open Hat", hat, decay=0.18, metal=0.4, nz=1.0, hp=9500, dur=0.8),
        K("808 Tom Lo", tom, f=70, decay=0.5, bend=1.2), K("808 Tom Mid", tom, f=98, decay=0.45, bend=1.2),
        K("808 Tom Hi", tom, f=131, decay=0.4, bend=1.2), K("Rim", rim), K("Perc", blip, f=800, decay=0.05),
        K("Clave", clave), K("Shaker", shaker), K("Crash", cymbal), K("Laser", zap, f0=4000, f1=200, tau=0.05, decay=0.12),
        K("Conga", conga)]),
    dict(name="SP Dust", desc="12-bit boom bap, crunchy and warm", crush=(12, 26040), drive=0.35, lp=11000, pads=[
        K("Kick", kick, f0=130, f1=50, sweep=0.03, decay=0.22, click=0.4, drive=0.5),
        K("Kick 2", kick, f0=100, f1=45, sweep=0.03, decay=0.35, click=0.2, drive=0.6, dur=0.8),
        K("Snare", snare, f=190, tone=0.6, tdecay=0.07, noise=0.8, ndecay=0.14, hp=1000),
        K("Clap", clap, tail=0.14), K("Closed Hat", hat, decay=0.035, metal=0.4, nz=0.8, hp=5000),
        K("Open Hat", hat, decay=0.25, metal=0.4, nz=0.8, hp=5000, dur=0.9),
        K("Low Tom", tom, f=90), K("Mid Tom", tom, f=125), K("High Tom", tom, f=170), K("Rim", rim),
        K("Cowbell", cowbell), K("Clave", clave), K("Shaker", shaker, decay=0.05), K("Crash", cymbal, decay=0.7),
        K("Zap", zap), K("Conga", conga)]),
    dict(name="Electro 80s", desc="Gated snare, big pitch-drop toms", pads=[
        K("Kick", kick, f0=150, f1=45, sweep=0.04, decay=0.3, click=0.15, dur=0.8),
        K("Boom", kick, f0=90, f1=40, sweep=0.05, decay=0.7, click=0, dur=1.6),
        K("Gated Snare", snare, f=180, tone=0.5, tdecay=0.06, noise=1.0, ndecay=0.3, hp=900, dur=0.35, gate=0.25),
        K("Clap", clap, tail=0.25, n=4, spacing=0.015), K("Closed Hat", hat, decay=0.03, metal=0.5, nz=0.8),
        K("Open Hat", hat, decay=0.22, metal=0.5, nz=0.8, dur=0.9),
        K("Syn Tom Lo", tom, f=90, decay=0.4, bend=2.0, noise=0.2, dur=0.9),
        K("Syn Tom Mid", tom, f=130, decay=0.35, bend=2.0, noise=0.2, dur=0.8),
        K("Syn Tom Hi", tom, f=180, decay=0.3, bend=2.0, noise=0.2, dur=0.7), K("Rim", rim),
        K("Cowbell", cowbell), K("Clave", clave), K("Shaker", shaker), K("Crash", cymbal, decay=0.9),
        K("Zap", zap, f0=3000, f1=60, tau=0.05, decay=0.15), K("Conga", conga)]),
    dict(name="Minimal Tech", desc="Clicks, blips and tight kicks", pads=[
        K("Kick", kick, f0=200, f1=50, sweep=0.012, decay=0.16, click=0.25, drive=0.2, dur=0.45),
        K("Sub Thud", kick, f0=70, f1=50, sweep=0.02, decay=0.25, click=0, dur=0.6),
        K("Snap", snare, f=300, tone=0.3, tdecay=0.02, noise=0.8, ndecay=0.05, hp=3000),
        K("Clap", clap, tail=0.06, n=2), K("Closed Hat", hat, decay=0.012, metal=0.2, nz=1.0, hp=10000),
        K("Open Hat", hat, decay=0.1, metal=0.2, nz=1.0, hp=10000, dur=0.5),
        K("Blip Lo", tom, f=200, decay=0.06, bend=1.1), K("Blip Mid", tom, f=300, decay=0.06, bend=1.1),
        K("Blip Hi", tom, f=450, decay=0.06, bend=1.1), K("Rim", rim, f1=2200, f2=700, decay=0.005),
        K("Click", blip, f=3000, decay=0.004), K("Clave", clave), K("Shaker", shaker, decay=0.03),
        K("Ride", cymbal, decay=0.8, scale=1.8, hp=7000, dur=1.5), K("Zap", zap), K("Bongo", conga, f0=450, f1=400, decay=0.05)]),
    dict(name="Industrial", desc="Distorted, metallic and heavy", drive=0.6, crush=(10, 48000), pads=[
        K("Kick", kick, f0=160, f1=40, sweep=0.03, decay=0.3, click=0.8, drive=1.0, dur=0.8),
        K("Kick 2", kick, f0=90, f1=35, sweep=0.04, decay=0.6, click=0.3, drive=1.0, dur=1.2),
        K("Snare", snare, f=160, tone=0.6, tdecay=0.1, noise=1.0, ndecay=0.2, hp=600, drive=0.8),
        K("Metal Clap", clap, tail=0.2, lo=1500, hi=5000, n=4), K("Closed Hat", hat, decay=0.03, metal=1.0, nz=0.6, hp=4000, scale=0.7),
        K("Open Hat", hat, decay=0.3, metal=1.0, nz=0.6, hp=4000, scale=0.7, dur=1.0),
        K("Low Tom", tom, f=70, decay=0.3, bend=1.8, noise=0.5), K("Mid Tom", tom, f=100, decay=0.28, bend=1.8, noise=0.5),
        K("High Tom", tom, f=140, decay=0.25, bend=1.8, noise=0.5), K("Anvil", cowbell, f1=900, f2=1400, decay=0.12),
        K("Clank", cowbell, f1=320, f2=470, decay=0.2), K("Clave", clave, f=1800), K("Grit", shaker, decay=0.08),
        K("Crash", cymbal, decay=1.2, scale=0.8, hp=2500), K("Zap", zap, f0=1500, f1=40, decay=0.12),
        K("Hit", conga, f0=200, f1=120, decay=0.12)]),
]

NAMES = [k["name"] for k in KITS]
_CACHE = {}


def _crush(x, bits, rate, sr):
    hold = max(1, int(round(sr / rate)))
    if hold > 1:
        x = np.repeat(x[::hold], hold)[: len(x)]
    q = 2 ** (bits - 1)
    return np.round(x * q) / q


def build(index, sr):
    """Return (pad names, list of 16 float32 sample arrays) for factory kit `index`."""
    index = int(index) % len(KITS)
    key = (index, int(sr))
    if key in _CACHE:
        return _CACHE[key]
    kit = KITS[index]
    g = Gen(sr, seed=3 + index)
    names, samples = [], []
    for name, fn, kw in kit["pads"]:
        x = np.asarray(fn(g, **kw), dtype=np.float64)
        x = x / max(np.max(np.abs(x)), 1e-9) * 0.9
        if kit.get("drive"):
            x = _drive(x, kit["drive"])
        if kit.get("lp"):
            x = g.lp(x, kit["lp"])
        if kit.get("crush"):
            x = _crush(x, kit["crush"][0], kit["crush"][1], sr)
        x = x / max(np.max(np.abs(x)), 1e-9) * 0.9
        fade = min(len(x), int(0.003 * sr))
        x[-fade:] *= np.linspace(1, 0, fade)
        names.append(name)
        samples.append(np.append(x, 0.0).astype(np.float32))
    _CACHE[key] = (names, samples)
    return names, samples
