"""Synthesized drum kits for PotentialBox (v2.1: rebuilt from the ground up).

Every kit uses the same pad layout so BeatStep Pro drum patterns carry over:
 1 Kick  2 Kick 2 / 808  3 Snare  4 Clap  5 Closed Hat  6 Open Hat  7-9 Toms (low/mid/high)
10 Rim  11 Cowbell  12 Clave  13 Shaker  14 Cymbal  15 FX  16 Conga
Pad 5 chokes pad 6 in every kit.

How the sounds are made (each the way the classic machines, or the real instrument, make it):
- Kicks: a sine with a two-stage pitch drop, a held-then-falling body, a beater click and soft saturation.
  808 = long and round, 909 = short drop with a hard click, acoustic = membrane modes with a felt beater.
- Snares: two tuned drum modes with a pitch kick, plus snare-wire noise shaped by its own envelope and filters,
  and (for real-sounding ones) a short room baked in.
- Claps: 3-5 jittered bursts of band-passed noise and a diffuse tail, like the 808's.
- Hats and cymbals: the 808's six square-wave oscillators, band-limited so they don't alias, through band-pass
  filters, mixed with noise. Rides and crashes add dozens of inharmonic partials that ring and fade at
  different rates.
- Toms, congas, bongos, log drums: modal (a few inharmonic partials with their own decays) with a stick or slap.
Each pad is levelled for its role (kicks loudest, hats and shakers well under), so a beat comes out balanced.
"""
import math

import numpy as np
from scipy.signal import lfilter, butter, sosfilt, fftconvolve

TWO_PI = 2.0 * math.pi
METAL = (205.3, 304.4, 369.6, 522.7, 540.0, 800.0)   # the 808's six hat/cymbal oscillators


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
        return sosfilt(butter(order, self._f(fc), "high", output="sos"), x)

    def lp(self, x, fc, order=2):
        return sosfilt(butter(order, self._f(fc), "low", output="sos"), x)

    def bp(self, x, lo, hi, order=2):
        lo, hi = self._f(lo), self._f(hi)
        if hi <= lo * 1.01:
            hi = min(0.99, lo * 1.05)
        return sosfilt(butter(order, [lo, hi], "band", output="sos"), x)

    def reso(self, x, f, q):
        """A resonant band-pass (a ringing filter): q ~ 2-40."""
        w = TWO_PI * min(f, self.sr * 0.45) / self.sr
        alpha = math.sin(w) / (2 * q)
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * math.cos(w), 1 - alpha]
        return lfilter(b, a, x)

    def sweep(self, t, f0, f1, tau, tau2=None, mid=None):
        """Sine whose pitch falls from f0 to f1 (time constant tau). With tau2/mid: a fast drop to `mid`, then a
        slower one to f1 (how a real kick or tom bends)."""
        if tau2 and mid:
            f = f1 + (mid - f1) * np.exp(-t / tau2) + (f0 - mid) * np.exp(-t / tau)
        else:
            f = f1 + (f0 - f1) * np.exp(-t / tau)
        return np.sin(TWO_PI * np.cumsum(f) / self.sr)

    def square_bl(self, f, t):
        """Band-limited square wave (odd harmonics up to Nyquist), so metallic sounds don't alias."""
        y = np.zeros(len(t))
        k = 1
        ph = self.rng.random() * TWO_PI
        while k * f < self.sr * 0.45:
            y += np.sin(TWO_PI * k * f * t + k * ph) / k
            k += 2
        return y * (4 / math.pi)

    def metal(self, t, scale=1.0):
        return sum(self.square_bl(f * scale, t) for f in METAL) / 6.0

    def partials(self, t, freqs, decays, amps=None):
        amps = amps if amps is not None else [1.0] * len(freqs)
        y = np.zeros(len(t))
        for f, d, a in zip(freqs, decays, amps):
            if f < self.sr * 0.45:
                y += a * np.sin(TWO_PI * f * t + self.rng.random() * TWO_PI) * np.exp(-t / d)
        return y

    def room(self, x, size=0.25, damp=6000, mix=0.2, pre=0.004):
        """A short, dense room baked into a sound: exponentially fading filtered noise as the impulse."""
        if mix <= 0:
            return x
        n = int((0.08 + size * 0.6) * self.sr)
        ti = np.arange(n) / self.sr
        ir = self.rng.standard_normal(n) * np.exp(-ti / (0.02 + size * 0.15))
        ir = self.lp(ir, damp)
        ir[: int(pre * self.sr)] = 0
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-12
        wet = fftconvolve(x, ir)[: len(x) + n]
        dry = np.concatenate([x, np.zeros(len(wet) - len(x))])
        return dry + mix * wet * (np.max(np.abs(x)) / (np.max(np.abs(wet)) + 1e-12)) * 0.7


def _sat(x, amt):
    """Soft saturation that keeps the level (amt 0-1)."""
    if amt <= 0:
        return x
    g = 1 + amt * 6
    return np.tanh(x * g) / math.tanh(g)


def _attack(t, ms):
    return np.clip(t / max(ms / 1000.0, 1e-5), 0, 1)


# ---------------------------------------------------------------- voices
def kick(g, f=50, top=3.2, drop=0.022, drop2=0.09, decay=0.32, hold=0.02, click=0.35, click_hz=4000, drive=0.15,
         sub=0.0, dur=0.9, room=0.0):
    """Electronic kick. top = how many times the base pitch it starts at; drop = how fast it falls; hold = how long
    the body stays full before it fades."""
    t = g.t(dur)
    mid = f * (1 + (top - 1) * 0.28)
    body = g.sweep(t, f * top, f, drop, drop2, mid)
    env = np.where(t < hold, 1.0, np.exp(-(t - hold) / decay)) * _attack(t, 0.4)
    y = body * env
    if sub:   # reinforce the low end with the body's own fundamental (no beating)
        y += sub * 2.0 * g.lp(y, f * 2.2, 2)
    if click:
        ck = g.bp(g.noise(len(t)), click_hz * 0.5, min(click_hz * 2.2, g.sr * 0.45)) * np.exp(-t / 0.0025)
        ck += 0.6 * np.sin(TWO_PI * click_hz * 0.35 * t) * np.exp(-t / 0.0015)
        y = y + click * ck
    y = _sat(y, drive)
    return g.room(y, 0.15, 3000, room) if room else y


def kick808(g, f=48, decay=0.55, top=2.0, drop=0.03, click=0.08, drive=0.1, dur=1.8):
    """The 808's bridged-T kick: a long round sine with a small pitch bend; turn up `drive` for a distorted 808."""
    t = g.t(dur)
    y = g.sweep(t, f * top, f, drop) * np.exp(-t / decay) * _attack(t, 0.6)
    y += click * g.hp(g.noise(len(t)), 2500) * np.exp(-t / 0.002)
    return _sat(y, drive)


def kick_acoustic(g, f=56, decay=0.28, beater=0.5, room=0.25, dur=0.8, damp=0.6):
    """A real bass drum: membrane modes, a felt beater, the shell's thud, a little room."""
    t = g.t(dur)
    modes = [f, f * 1.59, f * 2.14, f * 2.65, f * 3.16]
    dec = [decay, decay * 0.45 * (1.2 - damp), decay * 0.3 * (1.2 - damp), decay * 0.2, decay * 0.12]
    amp = [1.0, 0.45, 0.3, 0.18, 0.1]
    bend = 1 + 0.25 * np.exp(-t / 0.012)
    y = np.zeros(len(t))
    for fm, d, a in zip(modes, dec, amp):
        y += a * np.sin(TWO_PI * np.cumsum(fm * bend) / g.sr) * np.exp(-t / d)
    y *= _attack(t, 0.8)
    bt = g.bp(g.noise(len(t)), 1200, 5000) * np.exp(-t / 0.004)
    thud = g.lp(g.noise(len(t)), 300) * np.exp(-t / 0.03)
    y = y + beater * bt + 0.6 * thud
    y = _sat(y, 0.2)
    return g.room(y, 0.2, 4000, room)


def snare(g, f=185, f2=None, tone=0.55, tdecay=0.07, noise=0.8, ndecay=0.14, hp=1300, lpf=11000, snap=0.5,
          dur=0.45, gate=None, drive=0.0, room=0.0, roomsize=0.25, pitch=1.35):
    """Electronic snare (808/909 style): two tuned modes with a pitch kick + shaped snare noise."""
    t = g.t(dur)
    f2 = f2 or f * 1.62
    b1 = g.sweep(t, f * pitch, f, 0.012)
    b2 = np.sin(TWO_PI * f2 * t + 0.3)
    body = (b1 + 0.55 * b2 * np.exp(-t / (tdecay * 0.6))) * np.exp(-t / tdecay)
    nz = g.noise(len(t))
    wires = g.lp(g.hp(nz, hp), lpf) * np.exp(-t / ndecay)
    crack = g.bp(nz, 2500, 9000) * np.exp(-t / 0.006)
    y = tone * body + noise * wires + snap * crack
    y *= _attack(t, 0.3)
    if gate:
        y = y * np.clip((gate - t) / 0.008, 0, 1)
    y = _sat(y, drive)
    return g.room(y, roomsize, 7000, room) if room else y


def snare_acoustic(g, f=200, decay=0.12, wires=0.9, wdecay=0.18, stick=0.7, room=0.35, roomsize=0.35, bright=8000,
                   dur=0.6, rim=0.0):
    """A real snare: drum-head modes, a stick hit, rattling wires (noise that follows the head) and a room."""
    t = g.t(dur)
    modes = [f, f * 1.47, f * 1.73, f * 2.0, f * 2.3]
    y = g.partials(t, modes, [decay, decay * 0.7, decay * 0.55, decay * 0.4, decay * 0.3], [1, 0.6, 0.45, 0.3, 0.25])
    nz = g.noise(len(t))
    w = g.lp(g.hp(nz, 1800), bright) * (np.exp(-t / wdecay) * 0.85 + 0.15 * np.exp(-t / 0.02))
    w += 0.4 * g.bp(nz, 4000, 9000) * np.exp(-t / (wdecay * 0.5))
    st = g.bp(nz, 1500, 6000) * np.exp(-t / 0.003)
    y = y * _attack(t, 0.3) + wires * w + stick * st
    if rim:
        y += rim * g.reso(nz * np.exp(-t / 0.002), 1700, 25) * 3
    y = _sat(y, 0.25)
    return g.room(y, roomsize, 7500, room)


def clap(g, tail=0.16, lo=900, hi=2400, n=4, spacing=0.0105, dur=0.6, room=0.15, bright=0.3):
    """The 808 clap: a few jittered bursts of band-passed noise, then a diffuse tail."""
    t = g.t(dur)
    env = np.zeros(len(t))
    off = 0.0
    for i in range(n):
        env += (t >= off) * np.exp(-np.clip(t - off, 0, None) / 0.0032) * (0.8 + 0.2 * g.rng.random())
        off += spacing * (0.75 + 0.5 * g.rng.random())
    env += 0.85 * np.exp(-np.clip(t - off, 0, None) / tail) * (t >= off - 0.002)
    nz = g.noise(len(t))
    y = (g.bp(nz, lo, hi) + bright * g.bp(nz, hi, min(hi * 3.5, g.sr * 0.45))) * env
    y *= _attack(t, 0.2)
    return g.room(y, 0.3, 6000, room) if room else y


def hat(g, decay=0.045, metal=0.75, nz=0.35, hp=7000, bp=(6500, 11000), scale=1.0, dur=None, att=0.4, chick=0.0):
    """808/909 hat: the six metal oscillators (band-limited) and noise, through band-pass and high-pass."""
    t = g.t(dur or max(0.12, decay * 6))
    x = metal * g.metal(t, scale * 1.0) + nz * g.noise(len(t))
    x = g.bp(x, bp[0], bp[1]) + 0.35 * g.hp(x, max(hp, bp[1]))
    x = g.hp(x, hp)
    env = np.exp(-t / decay) * _attack(t, att)
    y = x * env
    if chick:   # a pedal hat's "chick"
        y += chick * g.bp(g.noise(len(t)), 800, 3000) * np.exp(-t / 0.006)
    return y


def ride(g, decay=1.6, ping=0.6, bell=2400, wash=0.5, dur=3.0, hp=2500):
    """Ride: many inharmonic partials that fade at different rates, a stick ping and a noise wash."""
    t = g.t(dur)
    fr = np.exp(g.rng.uniform(np.log(380), np.log(9500), 36))
    y = g.partials(t, fr, decay * (0.25 + 0.75 * (400 / fr) ** 0.35), g.rng.uniform(0.3, 1.0, 36))
    y += ping * g.partials(t, [bell, bell * 1.51, bell * 2.08], [0.5, 0.35, 0.25], [1, 0.6, 0.4])
    y += wash * g.hp(g.noise(len(t)), 6000) * np.exp(-t / (decay * 0.4))
    y += 0.8 * g.hp(g.noise(len(t)), 3000) * np.exp(-t / 0.004)
    return g.hp(y, hp) * _attack(t, 0.5)


def crash(g, decay=1.4, dur=3.2, hp=1800, scale=1.0):
    """Crash: noise and a dense cloud of partials with a short bloom."""
    t = g.t(dur)
    fr = np.exp(g.rng.uniform(np.log(300 * scale), np.log(12000), 60))
    y = 0.5 * g.partials(t, fr, decay * (0.3 + 0.7 * (300 / fr) ** 0.25), g.rng.uniform(0.2, 1.0, 60))
    y += 0.9 * g.lp(g.hp(g.noise(len(t)), 3000), 14000) * np.exp(-t / (decay * 0.7))
    y += 0.4 * g.metal(t, 1.3) * np.exp(-t / (decay * 0.5))
    env = _attack(t, 3) * (0.7 + 0.3 * np.exp(-t / 0.08))
    return g.hp(y * env, hp)


def cymbal(g, decay=0.8, scale=1.3, hp=4000, dur=2.2):
    """808 cymbal: the metal oscillators, long."""
    t = g.t(dur)
    x = 0.8 * g.metal(t, scale) + 0.5 * g.noise(len(t))
    x = g.bp(x, 3500, 12000) + 0.3 * g.hp(x, 8000)
    return g.hp(x, hp) * np.exp(-t / decay) * _attack(t, 1)


def tom(g, f=130, decay=0.3, bend=1.35, noise=0.25, dur=0.9, modes=True, room=0.0):
    """Tom: a bending fundamental with two overtone modes and a stick."""
    t = g.t(dur)
    y = g.sweep(t, f * bend, f, 0.05) * np.exp(-t / decay)
    if modes:
        y += 0.35 * g.sweep(t, f * 1.5 * bend, f * 1.5, 0.05) * np.exp(-t / (decay * 0.5))
        y += 0.18 * np.sin(TWO_PI * f * 2.44 * t) * np.exp(-t / (decay * 0.3))
    if noise:
        y += noise * g.bp(g.noise(len(t)), 800, 5000) * np.exp(-t / 0.006)
    y = _sat(y * _attack(t, 0.5), 0.15)
    return g.room(y, 0.3, 6000, room) if room else y


def rim(g, f1=1700, f2=480, decay=0.009, click=0.5, room=0.0):
    t = g.t(0.12)
    y = (np.sin(TWO_PI * f1 * t) + 0.6 * np.sin(TWO_PI * f2 * t)) * np.exp(-t / decay)
    y += click * g.bp(g.noise(len(t)), 2500, 9000) * np.exp(-t / 0.002)
    y += 0.4 * g.reso(g.noise(len(t)) * np.exp(-t / 0.001), f1 * 0.9, 18)
    return g.room(y, 0.2, 7000, room) if room else y


def cowbell(g, f1=540, f2=800, decay=0.12, dur=None):
    """808 cowbell: two band-limited squares, band-passed, with a fast-then-slow fade."""
    t = g.t(dur or max(0.4, decay * 5))
    x = g.square_bl(f1, t) + g.square_bl(f2, t)
    x = g.bp(x, f1 * 0.9, f2 * 4.0)
    env = 0.55 * np.exp(-t / 0.012) + 0.45 * np.exp(-t / decay)
    return x * env * _attack(t, 0.3)


def clave(g, f=2500, decay=0.022):
    t = g.t(0.15)
    exc = g.noise(len(t)) * np.exp(-t / 0.0008)
    return g.reso(exc, f, 40) * 6 + np.sin(TWO_PI * f * t) * np.exp(-t / decay)


def woodblock(g, f=900, decay=0.04):
    t = g.t(0.2)
    return g.partials(t, [f, f * 2.76, f * 5.4], [decay, decay * 0.5, decay * 0.25], [1, 0.5, 0.2]) \
        + 0.3 * g.bp(g.noise(len(t)), 2000, 6000) * np.exp(-t / 0.002)


def shaker(g, decay=0.05, att=0.012, lo=4500, hi=11000, grains=2):
    """Shaker: noise in a few grains with a soft attack."""
    t = g.t(max(0.18, decay * 5))
    env = np.zeros(len(t))
    for i in range(grains):
        o = i * 0.006 * (1 + g.rng.random())
        tt = np.clip(t - o, 0, None)
        env += (t >= o) * (1 - np.exp(-tt / att)) * np.exp(-tt / decay) * (1.0 if i == 0 else 0.5)
    return g.bp(g.noise(len(t)), lo, hi) * env


def tambourine(g, decay=0.12):
    t = g.t(0.5)
    jingle = g.partials(t, [5200, 6900, 8100, 9800, 11800], [decay] * 5, [1, 0.8, 0.7, 0.5, 0.4])
    return g.hp(jingle + 0.8 * g.noise(len(t)) * np.exp(-t / (decay * 0.6)), 4500) * _attack(t, 2)


def conga(g, f=330, decay=0.16, slap=0.35, bend=1.12, dur=0.6):
    """Conga / bongo: membrane modes with a little bend and a slap."""
    t = g.t(dur)
    b = 1 + (bend - 1) * np.exp(-t / 0.01)
    y = np.sin(TWO_PI * np.cumsum(f * b) / g.sr) * np.exp(-t / decay)
    y += 0.3 * np.sin(TWO_PI * np.cumsum(f * 1.59 * b) / g.sr) * np.exp(-t / (decay * 0.4))
    y += slap * g.bp(g.noise(len(t)), 1200, 6000) * np.exp(-t / 0.004)
    return y * _attack(t, 0.4)


def logdrum(g, f=82, decay=0.35, bend=1.5, dur=0.9):
    """Amapiano / afro log drum: a woody, bending bass hit."""
    t = g.t(dur)
    b = 1 + (bend - 1) * np.exp(-t / 0.03)
    y = np.sin(TWO_PI * np.cumsum(f * b) / g.sr) * np.exp(-t / decay)
    y += 0.35 * np.sin(TWO_PI * np.cumsum(f * 2.76 * b) / g.sr) * np.exp(-t / (decay * 0.3))
    y += 0.2 * np.sin(TWO_PI * np.cumsum(f * 5.4 * b) / g.sr) * np.exp(-t / (decay * 0.12))
    return _sat(y * _attack(t, 1), 0.3)


def zap(g, f0=2600, f1=90, tau=0.03, decay=0.08):
    t = g.t(max(0.2, decay * 4))
    return g.sweep(t, f0, f1, tau) * np.exp(-t / decay)


def riser(g, dur=1.2, f0=300, f1=7000):
    """White noise sweeping up through a band-pass, swelling in."""
    t = g.t(dur)
    nz = g.noise(len(t))
    out = np.zeros(len(t))
    seg = int(0.02 * g.sr)
    for s in range(0, len(t), seg):
        fc = f0 * (f1 / f0) ** (s / len(t))
        out[s:s + seg] = g.bp(nz[max(0, s - 512):s + seg], fc * 0.8, fc * 1.25)[-len(out[s:s + seg]):]
    return out * (t / dur) ** 2


def vinyl(g, dur=1.0):
    """Vinyl crackle and hiss for the FX pad of dusty kits."""
    t = g.t(dur)
    y = 0.08 * g.lp(g.noise(len(t)), 5000)
    pops = g.rng.random(len(t)) < 30 / g.sr
    y += g.hp(pops * g.rng.uniform(-1, 1, len(t)) * 3, 1500)
    return y * np.minimum(1, (dur - t) / 0.1)


def blip(g, f=1200, decay=0.035):
    t = g.t(max(0.08, decay * 5))
    return np.sin(TWO_PI * f * t) * np.exp(-t / decay) * _attack(t, 0.3)


def reverse_cym(g, dur=1.0):
    y = crash(g, decay=0.9, dur=dur)
    return y[::-1] * np.linspace(0, 1, len(y)) ** 0.5


# ---------------------------------------------------------------- levels and stereo per pad role
# Peak level each pad is made to, so a beat comes out balanced (kicks loudest, hats and shakers well under).
ROLE_LEVEL = [0.95, 0.93, 0.8, 0.72, 0.52, 0.47, 0.66, 0.64, 0.62, 0.55, 0.46, 0.46, 0.44, 0.42, 0.45, 0.56]
# Where each pad sits in the stereo field (scaled by the Drums BUS > Width knob), like a real kit from the
# audience: hats right, toms spread, percussion either side, kicks and snares in the middle.
ROLE_PAN = [0.0, 0.0, 0.0, 0.0, 0.28, 0.32, -0.38, -0.05, 0.3, -0.12, 0.4, -0.42, 0.45, -0.3, 0.0, -0.35]

K = lambda name, fn, **kw: (name, fn, kw)  # noqa: E731
# a pad's own level (x its role level): lv=1.1


def _std_toms(f=95, decay=0.32, bend=1.35, noise=0.25, **kw):
    return [K("Low Tom", tom, f=f, decay=decay, bend=bend, noise=noise, **kw),
            K("Mid Tom", tom, f=f * 1.35, decay=decay * 0.9, bend=bend, noise=noise, **kw),
            K("High Tom", tom, f=f * 1.8, decay=decay * 0.8, bend=bend, noise=noise, **kw)]


KITS = [
    # ------------------------------------------------------------------ 0-8: the 1.x kits, rebuilt
    dict(name="Potential", desc="Punchy all-rounder, snare with room", pads=[
        K("Kick", kick, f=52, top=3.4, decay=0.3, click=0.35, drive=0.2),
        K("808", kick808, f=45, decay=0.7, drive=0.25),
        K("Snare", snare, f=190, room=0.2), K("Clap", clap),
        K("Closed Hat", hat), K("Open Hat", hat, decay=0.28, dur=1.1),
        *_std_toms(), K("Rim", rim), K("Cowbell", cowbell), K("Clave", clave), K("Shaker", shaker),
        K("Crash", crash), K("Zap", zap), K("Conga", conga)]),
    dict(name="808 Boom", desc="Round boom kick, metal hats, cowbell", pads=[
        K("Kick", kick808, f=52, decay=0.42, top=2.2, click=0.12, drive=0.05, dur=1.4),
        K("Sub Kick", kick808, f=44, decay=0.9, top=1.8, click=0.04, drive=0.1, dur=2.4),
        K("Snare", snare, f=238, f2=476, tone=0.75, tdecay=0.07, noise=0.55, ndecay=0.11, hp=1800, snap=0.25,
          pitch=1.15),
        K("Clap", clap, tail=0.17, lo=900, hi=1900, n=4, spacing=0.01, room=0.1),
        K("Closed Hat", hat, decay=0.035, metal=1.0, nz=0.1), K("Open Hat", hat, decay=0.32, metal=1.0, nz=0.1, dur=1.2),
        K("Low Tom", tom, f=82, decay=0.38, bend=1.15, noise=0.05, modes=False),
        K("Mid Tom", tom, f=118, decay=0.34, bend=1.15, noise=0.05, modes=False),
        K("High Tom", tom, f=164, decay=0.3, bend=1.15, noise=0.05, modes=False),
        K("Rim", rim, f1=1667, f2=455, decay=0.007), K("Cowbell", cowbell, decay=0.14), K("Clave", clave, decay=0.025),
        K("Maracas", shaker, decay=0.03, att=0.004, grains=1), K("Cymbal", cymbal, decay=1.0, scale=1.0),
        K("Lo Conga", conga, f=220, decay=0.18, slap=0.1, bend=1.05), K("Hi Conga", conga, f=330, decay=0.14,
                                                                          slap=0.1, bend=1.05)]),
    dict(name="909 Punch", desc="Driven clicky kick, noisy snare, ride", pads=[
        K("Kick", kick, f=50, top=4.5, drop=0.012, drop2=0.06, decay=0.26, hold=0.03, click=0.6, click_hz=5000,
          drive=0.45, dur=0.8),
        K("Long Kick", kick, f=46, top=4.0, drop=0.014, decay=0.5, hold=0.04, click=0.45, drive=0.55, dur=1.2),
        K("Snare", snare, f=200, tone=0.5, tdecay=0.05, noise=1.0, ndecay=0.17, hp=900, lpf=12000, snap=0.6,
          room=0.12),
        K("Clap", clap, tail=0.2, lo=800, hi=2600, spacing=0.012, room=0.15),
        K("Closed Hat", hat, decay=0.05, metal=0.35, nz=0.9, bp=(8000, 14000), hp=8000),
        K("Open Hat", hat, decay=0.34, metal=0.35, nz=0.9, bp=(8000, 14000), hp=8000, dur=1.3),
        *_std_toms(f=100, decay=0.28, bend=1.6, noise=0.3), K("Rim", rim, f1=1900, f2=600, decay=0.01),
        K("Ride", ride, decay=1.6), K("Clave", clave), K("Shaker", shaker),
        K("Crash", crash, decay=1.6), K("Zap", zap), K("Conga", conga)]),
    dict(name="606 Tight", desc="Small, snappy and crisp", pads=[
        K("Kick", kick, f=60, top=2.6, drop=0.012, decay=0.14, hold=0.01, click=0.25, dur=0.5),
        K("Kick 2", kick, f=55, top=2.4, decay=0.22, click=0.15, dur=0.7),
        K("Snare", snare, f=260, tone=0.4, tdecay=0.035, noise=0.9, ndecay=0.08, hp=2500, snap=0.4),
        K("Clap", clap, tail=0.09, lo=1000, hi=3000),
        K("Closed Hat", hat, decay=0.022, metal=0.9, nz=0.3, bp=(7500, 12000), hp=9000),
        K("Open Hat", hat, decay=0.15, metal=0.9, nz=0.3, bp=(7500, 12000), hp=9000, dur=0.6),
        *_std_toms(f=130, decay=0.14, bend=1.3, noise=0.1), K("Rim", rim),
        K("Cowbell", cowbell, f1=600, f2=900, decay=0.07), K("Clave", clave), K("Shaker", shaker, decay=0.03),
        K("Cymbal", cymbal, decay=0.45, scale=1.5, hp=6000, dur=1.4), K("Blip", blip), K("Conga", conga, decay=0.09)]),
    dict(name="Trap 808", desc="Punch kick, long distorted 808", pads=[
        K("Punch Kick", kick, f=55, top=3.6, drop=0.01, decay=0.16, hold=0.02, click=0.55, drive=0.5, sub=0.3, dur=0.6),
        K("808 Long", kick808, f=43, decay=1.3, top=2.4, drop=0.04, click=0.06, drive=0.55, dur=3.2),
        K("Snare", snare, f=215, tone=0.5, tdecay=0.05, noise=0.9, ndecay=0.13, hp=1700, snap=0.6, drive=0.25,
          room=0.15),
        K("Clap", clap, tail=0.22, lo=950, hi=3200, n=5, spacing=0.0085, room=0.25, bright=0.5),
        K("Closed Hat", hat, decay=0.028, metal=0.45, nz=0.9, bp=(8500, 15000), hp=9500),
        K("Open Hat", hat, decay=0.2, metal=0.45, nz=0.9, bp=(8500, 15000), hp=9500, dur=0.9),
        K("808 Tom Lo", kick808, f=73, decay=0.45, top=1.4, click=0.05, drive=0.2, dur=1.4),
        K("808 Tom Mid", kick808, f=98, decay=0.4, top=1.4, click=0.05, drive=0.2, dur=1.2),
        K("808 Tom Hi", kick808, f=131, decay=0.35, top=1.4, click=0.05, drive=0.2, dur=1.0),
        K("Rim", rim, room=0.15), K("Perc", blip, f=820, decay=0.06), K("Clave", clave),
        K("Shaker", shaker, decay=0.04), K("Crash", crash), K("Laser", zap, f0=4000, f1=200, tau=0.05, decay=0.12),
        K("Conga", conga)]),
    dict(name="SP Dust", desc="12-bit boom bap, snare in a room", crush=(12, 26040),
         drive=0.3, lp=12000, pads=[
        K("Kick", kick_acoustic, f=58, decay=0.26, beater=0.6, room=0.2),
        K("Kick 2", kick, f=50, top=2.8, decay=0.34, click=0.3, drive=0.5, dur=0.9),
        K("Snare", snare_acoustic, f=210, decay=0.11, wires=1.0, wdecay=0.2, room=0.45, roomsize=0.3),
        K("Clap", clap, tail=0.15, room=0.3),
        K("Closed Hat", hat, decay=0.04, metal=0.3, nz=0.9, bp=(6000, 10000), hp=5500, chick=0.2),
        K("Open Hat", hat, decay=0.3, metal=0.3, nz=0.9, bp=(6000, 10000), hp=5500, dur=1.1),
        *_std_toms(f=92, decay=0.3, room=0.25), K("Rim", rim, f1=1500, f2=420, room=0.3),
        K("Cowbell", cowbell, decay=0.1), K("Clave", woodblock), K("Shaker", tambourine),
        K("Ride", ride, decay=1.4, hp=2000), K("Vinyl", vinyl), K("Conga", conga, f=300)]),
    dict(name="Electro 80s", desc="Gated snare, big syn toms", pads=[
        K("Kick", kick, f=48, top=3.2, drop=0.03, decay=0.32, click=0.2, drive=0.2, dur=0.9),
        K("Boom", kick808, f=42, decay=0.8, top=2.4, drop=0.05, click=0.02, dur=1.8),
        K("Gated Snare", snare, f=180, tone=0.5, tdecay=0.07, noise=1.0, ndecay=0.4, hp=800, dur=0.45, gate=0.26,
          room=0.45, roomsize=0.5),
        K("Clap", clap, tail=0.28, n=4, spacing=0.015, room=0.4),
        K("Closed Hat", hat, decay=0.035, metal=0.6, nz=0.6),
        K("Open Hat", hat, decay=0.25, metal=0.6, nz=0.6, dur=1.0),
        K("Syn Tom Lo", tom, f=90, decay=0.42, bend=2.0, noise=0.3, dur=1.0, modes=False),
        K("Syn Tom Mid", tom, f=130, decay=0.36, bend=2.0, noise=0.3, dur=0.9, modes=False),
        K("Syn Tom Hi", tom, f=180, decay=0.32, bend=2.0, noise=0.3, dur=0.8, modes=False),
        K("Rim", rim), K("Cowbell", cowbell), K("Clave", clave), K("Shaker", shaker), K("Crash", crash, decay=1.1),
        K("Zap", zap, f0=3200, f1=60, tau=0.05, decay=0.16), K("Conga", conga)]),
    dict(name="Minimal Tech", desc="Clicks, blips, tight kick, dry ride", pads=[
        K("Kick", kick, f=52, top=4.0, drop=0.01, decay=0.18, hold=0.015, click=0.3, drive=0.25, dur=0.55),
        K("Sub Thud", kick, f=48, top=1.6, decay=0.28, click=0.0, dur=0.7),
        K("Snap", snare, f=300, tone=0.3, tdecay=0.02, noise=0.8, ndecay=0.05, hp=3000, snap=0.7),
        K("Clap", clap, tail=0.07, n=3, room=0.2),
        K("Closed Hat", hat, decay=0.016, metal=0.25, nz=1.0, bp=(9000, 15000), hp=10000),
        K("Open Hat", hat, decay=0.11, metal=0.25, nz=1.0, bp=(9000, 15000), hp=10000, dur=0.5),
        K("Blip Lo", conga, f=200, decay=0.07, slap=0.05), K("Blip Mid", conga, f=300, decay=0.07, slap=0.05),
        K("Blip Hi", conga, f=450, decay=0.06, slap=0.05), K("Rim", rim, f1=2200, f2=700, decay=0.005),
        K("Click", blip, f=3000, decay=0.004), K("Clave", clave), K("Shaker", shaker, decay=0.03),
        K("Ride", ride, decay=1.0, ping=0.8, wash=0.2), K("Zap", zap), K("Bongo", conga, f=440, decay=0.06)]),
    dict(name="Industrial", desc="Distorted, metallic and heavy", drive=0.55, crush=(10, 48000), pads=[
        K("Kick", kick, f=46, top=4.0, decay=0.32, click=0.8, drive=0.9, dur=0.9),
        K("Kick 2", kick808, f=40, decay=0.7, top=2.5, click=0.3, drive=0.9, dur=1.4),
        K("Snare", snare, f=160, tone=0.6, tdecay=0.1, noise=1.0, ndecay=0.22, hp=600, drive=0.7, room=0.35,
          roomsize=0.5),
        K("Metal Clap", clap, tail=0.22, lo=1500, hi=5000, n=4, room=0.3),
        K("Closed Hat", hat, decay=0.035, metal=1.0, nz=0.5, hp=4000, bp=(4000, 9000), scale=0.7),
        K("Open Hat", hat, decay=0.32, metal=1.0, nz=0.5, hp=4000, bp=(4000, 9000), scale=0.7, dur=1.2),
        *_std_toms(f=70, decay=0.3, bend=1.8, noise=0.5),
        K("Anvil", cowbell, f1=900, f2=1400, decay=0.14), K("Clank", cowbell, f1=320, f2=470, decay=0.22),
        K("Clave", clave, f=1800), K("Grit", shaker, decay=0.08, lo=2000, hi=8000),
        K("Crash", crash, decay=1.3, scale=0.8), K("Zap", zap, f0=1500, f1=40, decay=0.14),
        K("Hit", conga, f=150, decay=0.14, bend=1.6, slap=0.6)]),
    # ------------------------------------------------------------------ 9+: v2.1 genre kits
    dict(name="House Deep", desc="Warm kick, soft clap, airy hats", pads=[
        K("Kick", kick, f=48, top=3.0, drop=0.02, decay=0.36, hold=0.03, click=0.22, click_hz=3000, drive=0.2,
          sub=0.25, dur=1.0),
        K("Sub Kick", kick808, f=44, decay=0.6, top=1.7, click=0.05, dur=1.6),
        K("Snare", snare, f=200, tone=0.4, tdecay=0.05, noise=0.8, ndecay=0.16, hp=1200, snap=0.3, room=0.35,
          roomsize=0.4),
        K("Clap", clap, tail=0.22, lo=800, hi=2200, n=4, spacing=0.012, room=0.4, bright=0.2),
        K("Closed Hat", hat, decay=0.06, metal=0.3, nz=0.8, bp=(7000, 13000), hp=7000, att=1.0, lv=1.2),
        K("Open Hat", hat, decay=0.38, metal=0.3, nz=0.8, bp=(7000, 13000), hp=7000, dur=1.4, att=2.0),
        *_std_toms(f=105, decay=0.3), K("Rim", rim, f1=1600, f2=500, room=0.25),
        K("Cowbell", cowbell, decay=0.08), K("Clave", clave), K("Shaker", shaker, decay=0.06, att=0.02, grains=3),
        K("Ride", ride, decay=1.8, ping=0.5), K("Riser", riser), K("Conga", conga, f=290, decay=0.18)]),
    dict(name="Garage Shuffle", desc="Short thump kick, crisp snare and rim", pads=[
        K("Kick", kick, f=54, top=3.8, drop=0.012, decay=0.2, hold=0.02, click=0.4, drive=0.35, sub=0.2, dur=0.7),
        K("Kick 2", kick808, f=48, decay=0.45, top=2.0, click=0.1, drive=0.2, dur=1.2),
        K("Snare", snare, f=230, tone=0.45, tdecay=0.04, noise=0.95, ndecay=0.12, hp=1800, snap=0.7, room=0.25,
          roomsize=0.25),
        K("Clap", clap, tail=0.14, lo=1100, hi=3000, n=3, room=0.25, bright=0.4),
        K("Closed Hat", hat, decay=0.03, metal=0.3, nz=1.0, bp=(8500, 15000), hp=9000),
        K("Open Hat", hat, decay=0.16, metal=0.3, nz=1.0, bp=(8500, 15000), hp=9000, dur=0.8),
        *_std_toms(f=115, decay=0.22), K("Rim", rim, f1=1850, f2=520, room=0.2),
        K("Cowbell", cowbell, decay=0.07), K("Clave", clave), K("Shaker", shaker, decay=0.035, att=0.006),
        K("Ride", ride, decay=1.3), K("Vox Blip", blip, f=1500, decay=0.05), K("Conga", conga, f=340)]),
    dict(name="DnB Break", desc="Tight kick, cracking snare, ride",
         pads=[
        K("Kick", kick_acoustic, f=60, decay=0.18, beater=0.8, room=0.12, damp=0.8, dur=0.6),
        K("Kick 2", kick, f=52, top=3.8, drop=0.01, decay=0.2, click=0.5, drive=0.4, dur=0.7),
        K("Snare", snare_acoustic, f=230, decay=0.09, wires=1.1, wdecay=0.15, stick=1.0, room=0.35, roomsize=0.3,
          bright=10000, rim=0.3),
        K("Clap", clap, tail=0.16, room=0.3),
        K("Closed Hat", hat, decay=0.035, metal=0.3, nz=1.0, bp=(7000, 14000), hp=7500, chick=0.15),
        K("Open Hat", hat, decay=0.24, metal=0.3, nz=1.0, bp=(7000, 14000), hp=7500, dur=1.0),
        *_std_toms(f=110, decay=0.24, room=0.2), K("Rim", rim, room=0.2), K("Ride", ride, decay=1.4, ping=0.8),
        K("Clave", woodblock), K("Shaker", shaker, decay=0.035), K("Crash", crash), K("Reese Hit", zap, f0=800,
                                                                                         f1=60, decay=0.2),
        K("Conga", conga)]),
    dict(name="Jungle Crunch", desc="Chopped-break sounds, 12-bit crunch", crush=(12, 30000),
         drive=0.35, lp=13000, pads=[
        K("Kick", kick_acoustic, f=62, decay=0.22, beater=0.7, room=0.25, damp=0.5),
        K("Kick 2", kick808, f=44, decay=0.9, top=2.0, click=0.05, drive=0.3, dur=2.0),
        K("Snare", snare_acoustic, f=215, decay=0.14, wires=1.0, wdecay=0.22, stick=0.8, room=0.5, roomsize=0.4,
          rim=0.2),
        K("Ghost Snare", snare_acoustic, f=240, decay=0.06, wires=0.8, wdecay=0.08, stick=0.3, room=0.3, lv=0.75),
        K("Closed Hat", hat, decay=0.04, metal=0.25, nz=1.0, bp=(6000, 12000), hp=6000, chick=0.2),
        K("Open Hat", hat, decay=0.28, metal=0.25, nz=1.0, bp=(6000, 12000), hp=6000, dur=1.1),
        *_std_toms(f=100, decay=0.3, room=0.3), K("Rim", rim, room=0.3), K("Cowbell", cowbell),
        K("Clave", woodblock), K("Tambourine", tambourine), K("Ride", ride, decay=1.6), K("Vinyl", vinyl),
        K("Conga", conga)]),
    dict(name="Dub Steppa", desc="Deep kick, huge snare in a hall",
         pads=[
        K("Kick", kick, f=46, top=2.8, drop=0.025, decay=0.42, hold=0.03, click=0.2, click_hz=2500, drive=0.25,
          sub=0.35, dur=1.2),
        K("Sub", kick808, f=41, decay=1.0, top=1.6, click=0.02, dur=2.4),
        K("Snare", snare, f=180, tone=0.6, tdecay=0.09, noise=0.95, ndecay=0.22, hp=800, snap=0.6, room=0.65,
          roomsize=0.8, dur=0.8),
        K("Clap", clap, tail=0.3, room=0.55, n=5),
        K("Closed Hat", hat, decay=0.045, metal=0.4, nz=0.8, lv=1.25),
        K("Open Hat", hat, decay=0.3, metal=0.4, nz=0.8, dur=1.2, lv=1.15),
        *_std_toms(f=85, decay=0.4, room=0.4), K("Rimshot", rim, f1=1500, f2=460, room=0.5),
        K("Cowbell", cowbell), K("Clave", clave), K("Shaker", shaker, decay=0.05, grains=3),
        K("Crash", crash, decay=1.8), K("Siren", zap, f0=1800, f1=400, tau=0.3, decay=0.5), K("Conga", conga)]),
    dict(name="Drill Slide", desc="Punch kick, gliding 808, tight snare",
         pads=[
        K("Kick", kick, f=56, top=3.4, drop=0.01, decay=0.15, click=0.5, drive=0.45, dur=0.55),
        K("808 Slide", kick808, f=41, decay=1.4, top=3.0, drop=0.09, click=0.04, drive=0.6, dur=3.2),
        K("Snare", snare, f=240, tone=0.4, tdecay=0.035, noise=0.95, ndecay=0.1, hp=2200, snap=0.8, room=0.2),
        K("Clap", clap, tail=0.15, lo=1200, hi=3500, n=3, room=0.2, bright=0.5),
        K("Closed Hat", hat, decay=0.025, metal=0.7, nz=0.6, bp=(8000, 14000), hp=9000),
        K("Open Hat", hat, decay=0.18, metal=0.7, nz=0.6, bp=(8000, 14000), hp=9000, dur=0.8),
        K("808 Tom Lo", kick808, f=65, decay=0.4, top=1.3, drive=0.3, dur=1.2),
        K("808 Tom Mid", kick808, f=87, decay=0.35, top=1.3, drive=0.3, dur=1.0),
        K("808 Tom Hi", kick808, f=116, decay=0.3, top=1.3, drive=0.3, dur=0.9),
        K("Rim", rim, f1=2000, f2=560), K("Perc", blip, f=1000, decay=0.05), K("Clave", clave),
        K("Shaker", shaker, decay=0.03), K("Crash", crash), K("Riser", riser), K("Conga", conga, f=380)]),
    dict(name="Afro Perc", desc="Log drum, shakers, congas, agogo",
         pads=[
        K("Kick", kick, f=52, top=2.6, drop=0.02, decay=0.28, click=0.2, click_hz=2500, drive=0.15, sub=0.2),
        K("Log Drum", logdrum, f=80, decay=0.4),
        K("Snare", snare, f=230, tone=0.55, tdecay=0.05, noise=0.7, ndecay=0.1, hp=1800, snap=0.5, room=0.25),
        K("Clap", clap, tail=0.14, n=3, room=0.3),
        K("Closed Hat", hat, decay=0.035, metal=0.4, nz=0.8),
        K("Open Hat", hat, decay=0.2, metal=0.4, nz=0.8, dur=0.9),
        K("Low Tom", conga, f=160, decay=0.25, slap=0.2), K("Mid Tom", conga, f=220, decay=0.22, slap=0.25),
        K("High Tom", conga, f=300, decay=0.18, slap=0.3), K("Rim", rim, f1=1700, f2=500, room=0.15),
        K("Agogo", cowbell, f1=880, f2=1320, decay=0.15), K("Woodblock", woodblock, f=1100),
        K("Shaker", shaker, decay=0.06, att=0.02, grains=3), K("Tambourine", tambourine),
        K("Talking Drum", conga, f=180, decay=0.3, bend=1.8, slap=0.15), K("Conga", conga, f=340, decay=0.15)]),
    dict(name="Funk Room", desc="A real-sounding kit in a room", pads=[
        K("Kick", kick_acoustic, f=55, decay=0.3, beater=0.55, room=0.3),
        K("Kick 2", kick_acoustic, f=50, decay=0.4, beater=0.3, room=0.3, damp=0.3),
        K("Snare", snare_acoustic, f=195, decay=0.13, wires=0.95, wdecay=0.2, room=0.45, roomsize=0.4),
        K("Clap", clap, tail=0.18, room=0.35),
        K("Closed Hat", hat, decay=0.045, metal=0.35, nz=0.8, bp=(6500, 12000), hp=6000, chick=0.3),
        K("Open Hat", hat, decay=0.32, metal=0.35, nz=0.8, bp=(6500, 12000), hp=6000, dur=1.2),
        *_std_toms(f=90, decay=0.36, room=0.35), K("Rim", rim, f1=1500, f2=420, room=0.35),
        K("Cowbell", cowbell, f1=560, f2=845, decay=0.12), K("Clave", woodblock), K("Tambourine", tambourine),
        K("Ride", ride, decay=1.7), K("Crash", crash), K("Conga", conga, f=310)]),
    dict(name="Lo-fi Tape", desc="Soft muffled kit, vinyl crackle", crush=(12, 22050), drive=0.25,
         lp=7500, pads=[
        K("Kick", kick_acoustic, f=55, decay=0.3, beater=0.3, room=0.3, damp=0.4),
        K("Kick 2", kick808, f=48, decay=0.5, top=1.6, click=0.02, dur=1.2),
        K("Snare", snare_acoustic, f=205, decay=0.12, wires=0.8, wdecay=0.18, stick=0.35, room=0.5, roomsize=0.35,
          bright=6000),
        K("Clap", clap, tail=0.16, lo=700, hi=1900, room=0.4, bright=0.1),
        K("Closed Hat", hat, decay=0.05, metal=0.2, nz=0.9, bp=(5000, 9000), hp=4500, att=1.5),
        K("Open Hat", hat, decay=0.3, metal=0.2, nz=0.9, bp=(5000, 9000), hp=4500, dur=1.1, att=2.0),
        *_std_toms(f=88, decay=0.32, room=0.35), K("Rim", rim, f1=1400, f2=420, room=0.4),
        K("Cowbell", cowbell, decay=0.09), K("Clave", woodblock, f=800), K("Shaker", shaker, decay=0.07, att=0.025),
        K("Ride", ride, decay=1.3, hp=1800), K("Vinyl", vinyl, dur=2.0), K("Conga", conga, f=280)]),
]

NAMES = [k["name"] for k in KITS]
_CACHE = {}
CACHE_DIR = None        # set by the app: built kits are kept on disk, so each is only ever made once
CACHE_VERSION = "v21b"  # change when any sound above changes


def _crush(x, bits, rate, sr):
    hold = max(1, int(round(sr / rate)))
    if hold > 1:
        x = np.repeat(x[::hold], hold)[: len(x)]
    q = 2 ** (bits - 1)
    return np.round(x * q) / q


def pan_of(index, pad):
    """Stereo position (-1..1) for factory kit `index`'s pad `pad`, before the Width knob."""
    return ROLE_PAN[int(pad) % 16]


def build(index, sr):
    """Return (pad names, list of 16 float32 sample arrays) for factory kit `index`."""
    index = int(index) % len(KITS)
    key = (index, int(sr))
    if key in _CACHE:
        return _CACHE[key]
    disk = None
    if CACHE_DIR:
        import os
        disk = os.path.join(CACHE_DIR, f"kit-{CACHE_VERSION}-{index}-{int(sr)}.npz")
        try:
            d = np.load(disk, allow_pickle=False)
            names = [str(n) for n in d["names"]]
            samples = [d[f"p{i}"].astype(np.float32) for i in range(16)]
            if len(names) == 16:
                _CACHE[key] = (names, samples)
                return names, samples
        except Exception:
            pass
    kit = KITS[index]
    g = Gen(sr, seed=3 + index)
    names, samples = [], []
    for i, (name, fn, kw) in enumerate(kit["pads"]):
        kw = dict(kw)
        lv = kw.pop("lv", 1.0)
        x = np.asarray(fn(g, **kw), dtype=np.float64)
        x = x / max(np.max(np.abs(x)), 1e-9)
        if kit.get("drive"):
            x = _sat(x, kit["drive"])
        if kit.get("lp"):
            x = g.lp(x, kit["lp"])
        if kit.get("crush"):
            x = _crush(x, kit["crush"][0], kit["crush"][1], sr)
        # trim the silent tail, fade the last few ms
        thr = 10 ** (-70 / 20) * np.max(np.abs(x))
        nz = np.nonzero(np.abs(x) > thr)[0]
        if len(nz):
            x = x[: min(len(x), nz[-1] + int(0.01 * sr))]
        x = x / max(np.max(np.abs(x)), 1e-9) * ROLE_LEVEL[i] * lv
        fade = min(len(x), int(0.004 * sr))
        x[-fade:] *= np.linspace(1, 0, fade)
        names.append(name)
        samples.append(np.append(x, 0.0).astype(np.float32))
    _CACHE[key] = (names, samples)
    if disk:
        try:
            import os
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = disk + ".tmp.npz"
            np.savez(tmp, names=np.array(names), **{f"p{i}": x for i, x in enumerate(samples)})
            os.replace(tmp, disk)
        except Exception:
            pass
    return names, samples
