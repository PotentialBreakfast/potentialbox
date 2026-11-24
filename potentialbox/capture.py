"""CAPTURE > STEMS (v2.0): bounce what's playing as bar-exact loops, the mix plus one WAV per part.

The engine records from the start of the next bar (when the BeatStep or PotentialBox's own clock is running) for
exactly the bars you picked, so every file is the same length and loops cleanly in the MPC or any DAW. Parts that
were silent are left out. Files go to Music > PotentialBox Loops > <name>, named with the tempo so the MPC (and
most DAWs) can read it.
"""
import os
import re
import time
import wave

import numpy as np

from potentialbox.recorder import write_wav

STEM_FILES = [("mix", "Mix"), ("dr", "Drums"), ("s1", "Synth 1"), ("s2", "Synth 2"), ("fx", "FX"), ("lp", "Looper")]
SILENT = 10 ** (-70 / 20)   # quieter than -70 dBFS all the way through = nothing there


def loops_dir():
    home = os.path.expanduser("~")
    music = os.path.join(home, "Music")
    return os.path.join(music if os.path.isdir(music) else home, "PotentialBox Loops")


def clean(s):
    s = re.sub(r'[\\/:*?"<>|]+', " ", str(s))
    return re.sub(r"\s+", " ", s).strip(" .") or "Loop"


def bounce_name(what, bpm, bars, when=None):
    """e.g. "Acid 126bpm 4bar 1830" (short enough for the MPC's screen, unique to the minute)."""
    t = time.localtime(when or time.time())
    return clean(f"{what} {int(round(bpm))}bpm {bars}bar {t.tm_hour:02d}{t.tm_min:02d}{t.tm_sec:02d}")


def save_bounce(parts, sr, name, root=None):
    """Write each part that isn't silent. Returns (folder, [file names]). The mix gets the same headroom as the
    parts (no normalising), so the parts still add up the way they sounded."""
    folder = os.path.join(root or loops_dir(), name)
    base, k = folder, 2
    while os.path.exists(folder):
        folder = f"{base} ({k})"
        k += 1
    os.makedirs(folder)
    files = []
    for key, label in STEM_FILES:
        x = parts.get(key)
        if x is None or not len(x):
            continue
        x = np.asarray(x, dtype=np.float64)
        if key != "mix" and float(np.max(np.abs(x))) < SILENT:
            continue
        x = np.clip(x, -1.0, 1.0)   # no fades: loops stay sample-exact, so they don't click when they repeat
        fn = f"{os.path.basename(folder)} - {label}.wav"
        write_wav(os.path.join(folder, fn), x, sr)
        files.append(fn)
    return folder, files


def mix_file(folder):
    """The bounce's mix WAV (or its first WAV if the mix is missing), or None."""
    try:
        wavs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".wav"))
    except OSError:
        return None
    mix = [f for f in wavs if f.lower().endswith(" - mix.wav")]
    pick = (mix or wavs or [None])[0]
    return os.path.join(folder, pick) if pick else None


def read_wav(path, sr):
    """v2.3: read a bounce WAV (16/24/32-bit PCM, mono or stereo) as float32 stereo at `sr`, for listening."""
    with wave.open(path, "rb") as w:
        ch, width, fs, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif width == 2:
        x = np.frombuffer(raw, "<i2") / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, "<i4") / float(1 << 31)
    else:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128.0
    x = x.reshape(-1, ch)
    x = np.repeat(x, 2, axis=1) if ch == 1 else x[:, :2]
    if fs != sr and len(x) > 1:
        m = int(round(len(x) * sr / fs))
        t = np.linspace(0, len(x) - 1, m)
        x = np.stack([np.interp(t, np.arange(len(x)), x[:, c]) for c in range(2)], axis=1)
    return np.ascontiguousarray(x, dtype=np.float32)
