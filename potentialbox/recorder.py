"""Recording to WAV files on a background thread (the audio thread only hands over copies)."""
import os
import queue
import threading
import time
import wave

import numpy as np

STEM_NAMES = {"dr": "Drums", "s1": "Synth 1", "s2": "Synth 2", "fx": "FX returns", "lp": "Looper"}


def to_pcm24(x):
    x = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    i = np.round(x * 8388607.0).astype("<i4").reshape(-1)
    return i.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()


def write_wav(path, x, sr):
    """Write a whole array (mono or stereo float) as 24-bit WAV."""
    x = np.asarray(x)
    ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(3)
        w.setframerate(int(sr))
        w.writeframes(to_pcm24(x))


def recordings_dir():
    home = os.path.expanduser("~")
    music = os.path.join(home, "Music")
    return os.path.join(music if os.path.isdir(music) else home, "PotentialBox Recordings")


class Recorder:
    def __init__(self, sr, stems=True, root=None):
        self.sr = int(sr)
        self.folder = os.path.join(root or recordings_dir(), time.strftime("%Y-%m-%d %H-%M-%S"))
        os.makedirs(self.folder, exist_ok=True)
        self.stems = stems
        self.files = {}
        self.q = queue.Queue(maxsize=2000)
        self.frames = 0
        self.dropped = 0
        self.started = time.time()
        self._open("master", "Master")
        if stems:
            for k, name in STEM_NAMES.items():
                self._open(k, name)
        self.th = threading.Thread(target=self._run, daemon=True)
        self.th.start()

    def _open(self, key, name):
        w = wave.open(os.path.join(self.folder, f"{name}.wav"), "wb")
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(self.sr)
        self.files[key] = w

    def push(self, master, stems):  # audio thread: copy and go
        n = len(master)
        item = (master.copy(), {k: v.copy() for k, v in (stems or {}).items()} if self.stems else None, n)
        try:
            self.q.put_nowait(item)
        except queue.Full:
            self.dropped += 1

    def seconds(self):
        return self.frames / float(self.sr)

    def _run(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            master, stems, n = item
            try:
                self.files["master"].writeframes(to_pcm24(master))
                if stems is not None:
                    z = None
                    for k in STEM_NAMES:
                        x = stems.get(k)
                        if x is None:
                            if z is None:
                                z = np.zeros((n, 2))
                            x = z
                        self.files[k].writeframes(to_pcm24(x))
                self.frames += n
            except Exception:
                pass
        for w in self.files.values():
            try:
                w.close()
            except Exception:
                pass

    def close(self):
        self.q.put(None)
        self.th.join(timeout=10)
        return self.folder
