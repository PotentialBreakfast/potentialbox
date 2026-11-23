"""CAPTURE > STEMS (v2.0): bounce what's playing as bar-exact loops, the mix plus one WAV per part.

The engine records from the start of the next bar (when the BeatStep or PotentialBox's own clock is running) for
exactly the bars you picked, so every file is the same length and loops cleanly in the MPC or any DAW. Parts that
were silent are left out. Files go to Music > PotentialBox Loops > <name>, named with the tempo so the MPC (and
most DAWs) can read it.
"""
import os
import re
import time

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
