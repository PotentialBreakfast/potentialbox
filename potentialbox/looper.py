"""PotentialBox looper: 5 stereo tracks in the style of a BOSS RC-505.

Everything here runs on the audio thread. The GUI and MIDI threads only append commands to `cmds`.
Loop time `T` counts samples. While the BeatStep plays, record/play actions snap to its bars and a
gentle varispeed keeps the loops locked to its clock. When it's stopped, the first loop you record
sets the length that later loops snap to.
"""
import collections
import math

import numpy as np

TRACKS = 5
SOURCES = ["Input", "PotentialBox", "Both"]
FX_TYPES = ["Low-pass", "High-pass", "Lo-fi", "Echo", "Tremolo"]
SPEEDS = [("1/2", 0.5), ("1x", 1.0), ("2x", 2.0)]
LENGTHS = [("Free", 0), ("1 bar", 1), ("2 bars", 2), ("4 bars", 4), ("8 bars", 8)]
MAX_SECONDS = 300
STATE_TEXT = {"empty": "EMPTY", "armed": "WAITING", "rec": "REC", "ending": "FINISHING", "play": "PLAY",
              "dub": "OVERDUB", "stopped": "STOPPED", "cued": "WAITING", "paused": "PAUSED"}


class Track:
    def __init__(self, i, sr, mfx_cls, delay_cls):
        self.i = i
        self.state = "empty"
        self.buf = None
        self.L = 0
        self.start = 0.0
        self.chunks = []
        self.got = 0
        self.ev = None          # (time, action)
        self.undo = None
        self.redo = None
        self.src = 0
        self.fx = [0, 1, 3, 2, 4][i % 5]
        self.reverse = False
        self.speed = 1
        self.was_playing = False
        self.idx0 = 0           # which sample of the loop lines up with the grid's origin
        self.rec_O = None
        self.mfx = mfx_cls(sr)
        self.delay = delay_cls(sr)
        self.peak = 0.0

    def has_audio(self):
        return self.buf is not None and self.L > 0


class Looper:
    def __init__(self, eng):
        from potentialbox.engine import MasterFX, Delay  # local import: engine imports this module
        self.eng = eng
        self.sr = eng.sr
        self.tracks = [Track(i, self.sr, MasterFX, Delay) for i in range(TRACKS)]
        self.T = 0.0
        self.rate = 1.0
        self.cmds = collections.deque()
        self.sync = True          # snap to the BeatStep's bars and follow its Start / Stop
        self.length = 0           # index into LENGTHS
        self.on_bar_start = False  # False: recording starts the moment you tap (its length still snaps)
        self.master = None
        self.last = 0             # last track touched (for undo, reverse, speed)
        self.bsp_origin = None
        self.bsp_unit = None
        self.bsp_bars = 0
        self.rt = 0               # round-trip latency (samples) to line up recorded input
        H = int(self.sr * 4)
        self.H = H
        self.hist_in = np.zeros((H, 2), dtype=np.float32)
        self.hist_box = np.zeros((H, 2), dtype=np.float32)
        self.hw = 0
        self.in_peak = 0.0
        self.has_input = False
        self.toast = None
        self.bus = None

    # ------------------------------------------------------------------ commands (any thread)
    def cmd(self, *a):
        self.cmds.append(a)

    # ------------------------------------------------------------------ grid
    def bar_len(self):
        return 4 * 60.0 / max(self.eng.bpm, 30.0) * self.sr

    def grid(self):
        if self.sync and self.eng.playing and self.bsp_origin is not None:
            return self.bsp_origin, self.bsp_unit or self.bar_len()
        m = self.tracks[self.master] if self.master is not None else None
        if m is not None and m.has_audio():
            return m.start, float(m.L)
        return None

    def tol(self, U):
        return min(0.125 * U, 0.3 * self.sr)

    def boundary(self, now, late_ok=True):
        g = self.grid()
        if g is None:
            return now
        O, U = g
        k = (now - O) / U
        f = (k - math.floor(k)) * U
        if late_ok and f < self.tol(U):
            return O + math.floor(k) * U
        return O + math.ceil(k) * U

    # ------------------------------------------------------------------ transport (audio thread, from Engine)
    def on_start(self):
        self.bsp_origin = self.T
        self.bsp_unit = self.bar_len()
        self.bsp_bars = 0
        self.rate = 1.0
        if not self.sync:
            return
        for tr in self.tracks:
            if tr.has_audio():
                tr.start = self.T - tr.idx0  # bar 1 of the BeatStep = the same place in every loop
                if tr.state in ("play", "dub") or tr.was_playing:
                    tr.state = "play"
                tr.was_playing = False

    def on_stop(self):
        self.rate = 1.0
        if not self.sync:
            return
        for tr in self.tracks:
            if tr.state in ("rec", "ending"):
                self._finish_rec(tr, self.T)
            if tr.state in ("play", "dub"):
                tr.was_playing = True
                tr.state = "paused"
            elif tr.state in ("armed", "cued"):
                tr.ev = None
                tr.state = "empty" if not tr.has_audio() else "stopped"

    def on_bar(self):
        """Every BeatStep bar: re-anchor the grid, or nudge the loop speed to stay locked."""
        if self.bsp_origin is None:
            return
        self.bsp_bars += 1
        U = self.bsp_unit
        busy = any(t.has_audio() or t.state in ("rec", "ending") for t in self.tracks)
        if not busy:
            # nothing recorded yet: follow the BeatStep's actual bars exactly
            self.bsp_unit = U = self.bar_len()
            self.bsp_origin = self.T - self.bsp_bars * U
            self.rate = 1.0
            return
        err = self.T - (self.bsp_origin + self.bsp_bars * U)
        self.rate = 1.0 - max(min(err / U * 0.5, 0.003), -0.003)

    # ------------------------------------------------------------------ actions
    def _apply(self, c):
        kind = c[0]
        now = self.T
        if kind == "main":
            self._main(self.tracks[c[1]], now)
        elif kind == "stop":
            self._stop(self.tracks[c[1]], now)
        elif kind == "clear":
            self._clear(self.tracks[c[1]], keep_redo=False)
        elif kind == "undo":
            self._undo(self.tracks[c[1] if len(c) > 1 else self.last])
        elif kind == "allstop":
            playing = [t for t in self.tracks if t.state in ("play", "dub", "rec", "ending", "cued", "armed")]
            if playing:
                for t in self.tracks:
                    self._stop(t, now)
            else:
                for t in self.tracks:
                    if t.has_audio() and t.state in ("stopped", "paused"):
                        self._cue_play(t, now)
        elif kind == "clearall":
            for t in self.tracks:
                self._clear(t, keep_redo=False)
            self.master = None
        elif kind == "reverse":
            t = self.tracks[c[1]]
            t.reverse = not t.reverse
        elif kind == "speed":
            t = self.tracks[c[1]]
            t.speed = c[2] if len(c) > 2 else (t.speed + 1) % len(SPEEDS)
            if t.state == "dub" and SPEEDS[t.speed][1] != 1.0:
                t.state = "play"
        elif kind == "src":
            self.tracks[c[1]].src = c[2]
        elif kind == "fx":
            self.tracks[c[1]].fx = c[2]
        elif kind == "recnext":
            for t in self.tracks:
                if t.state == "empty":
                    self._main(t, now)
                    break
        elif kind == "load":
            self._load(c[1])
        if kind in ("main", "stop", "clear", "undo", "reverse", "speed", "src", "fx"):
            self.last = c[1] if len(c) > 1 else self.last

    def _main(self, tr, now):
        st = tr.state
        if st == "empty":
            B = self.boundary(now) if self.on_bar_start else now
            self._clear(tr, keep_redo=False)
            if B <= now + 0.5:
                self._rec_start(tr, B, now)
            else:
                tr.ev = (B, "rec_start")
                tr.state = "armed"
        elif st == "armed":
            tr.ev = None
            tr.state = "empty"
        elif st == "rec":
            self._end_rec(tr, now, then="play")
        elif st == "ending":
            pass
        elif st == "play":
            if SPEEDS[tr.speed][1] != 1.0:
                self.toast = "OVERDUB NEEDS 1X SPEED"
                return
            tr.undo = tr.buf.copy()
            tr.redo = None
            tr.state = "dub"
        elif st == "dub":
            tr.state = "play"
        elif st in ("stopped", "paused"):
            self._cue_play(tr, now)
        elif st == "cued":
            tr.ev = None
            tr.state = "stopped"

    def _stop(self, tr, now):
        if tr.state == "rec":
            self._end_rec(tr, now, then="stopped")
        elif tr.state == "ending":
            tr.ev = (tr.ev[0], "rec_end_stop") if tr.ev else None
        elif tr.state in ("play", "dub", "paused"):
            tr.state = "stopped"
            tr.was_playing = False
        elif tr.state == "armed":
            tr.ev = None
            tr.state = "empty"
        elif tr.state == "cued":
            tr.ev = None
            tr.state = "stopped"

    def _cue_play(self, tr, now):
        g = self.grid()
        bsp = self.sync and self.eng.playing
        others = any(t.state in ("play", "dub") and t is not tr for t in self.tracks)
        if g is None or (not bsp and not others):
            # nothing to stay in time with: play from the top straight away
            tr.start = now
            if self.master is not None and self.master != tr.i and not bsp:
                m = self.tracks[self.master]
                if m.has_audio():  # keep the stopped master's grid lined up with this track
                    m.start = now + tr.idx0 - m.idx0
            tr.state = "play"
            return
        O, U = g
        tr.start = O - tr.idx0
        B = self.boundary(now)
        if B <= now + 0.5:
            tr.state = "play"
        else:
            tr.ev = (B, "play_start")
            tr.state = "cued"

    def _rec_start(self, tr, B, now):
        tr.state = "rec"
        tr.start = B
        g = self.grid()
        tr.rec_O = g[0] if g is not None else B
        tr.chunks = []
        tr.got = 0
        tr.ev = None
        back = int(round(now - B))
        if back > 0:  # pressed a little late: take the start from the last moments of sound
            tr.chunks.append(self._history(tr, back))
            tr.got = back
        n_units = LENGTHS[self.length][1]
        g = self.grid()
        if n_units and g is not None:
            tr.ev = (B + n_units * g[1], "rec_end")

    def _end_rec(self, tr, now, then):
        g = self.grid()
        if g is None:  # free: the loop ends right here and sets the length for the others
            self._finish_rec(tr, now)
            if then == "stopped":
                tr.state = "stopped"
            return
        U = g[1]
        k = (now - tr.start) / U
        f = (k - math.floor(k)) * U
        units = math.floor(k) if (f < self.tol(U) and k >= 1) else math.ceil(k)
        end = tr.start + max(units, 1) * U
        if end <= now + 0.5:
            self._finish_rec(tr, end)
            if then == "stopped":
                tr.state = "stopped"
        else:
            tr.ev = (end, "rec_end" if then == "play" else "rec_end_stop")
            tr.state = "ending"

    def _finish_rec(self, tr, end):
        L = int(round(end - tr.start))
        x = np.concatenate(tr.chunks) if tr.chunks else np.zeros((0, 2), dtype=np.float32)
        tr.chunks = []
        if L <= 64 or len(x) < 64:
            tr.state = "empty"
            tr.buf = None
            tr.L = 0
            tr.ev = None
            return
        if len(x) < L:
            x = np.concatenate([x, np.zeros((L - len(x), 2), dtype=np.float32)])
        x = x[:L].astype(np.float32)
        f = min(64, L // 4)  # tiny crossfade at the loop point
        x[:f] *= np.linspace(0, 1, f, dtype=np.float32)[:, None]
        x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
        tr.buf = x
        tr.L = L
        tr.ev = None
        tr.undo = None
        tr.state = "play"
        tr.idx0 = int(round((tr.rec_O if tr.rec_O is not None else tr.start) - tr.start)) % L
        if self.master is None or not self.tracks[self.master].has_audio():
            self.master = tr.i

    def _clear(self, tr, keep_redo=True):
        if keep_redo and tr.has_audio():
            tr.redo = ("full", tr.buf, tr.L, tr.start)
        else:
            tr.redo = None
        tr.state = "empty"
        tr.buf = None
        tr.L = 0
        tr.chunks = []
        tr.ev = None
        tr.undo = None
        tr.was_playing = False
        if self.master == tr.i:
            self.master = next((t.i for t in self.tracks if t.has_audio()), None)

    def _undo(self, tr):
        if tr.state in ("rec", "ending", "armed"):
            self._clear(tr, keep_redo=False)
            self.toast = f"TRACK {tr.i + 1} RECORDING CANCELLED"
            return
        if tr.undo is not None:
            tr.redo = ("dub", tr.buf)
            tr.buf = tr.undo
            tr.undo = None
            if tr.state == "dub":
                tr.state = "play"
            self.toast = f"UNDO · TRACK {tr.i + 1}"
        elif tr.redo is not None:
            if tr.redo[0] == "dub":
                tr.undo = tr.buf
                tr.buf = tr.redo[1]
            else:
                _, tr.buf, tr.L, tr.start = tr.redo
                tr.state = "play"
                if self.master is None:
                    self.master = tr.i
            tr.redo = None
            self.toast = f"REDO · TRACK {tr.i + 1}"
        elif tr.has_audio():
            self._clear(tr, keep_redo=True)
            self.toast = f"UNDO · TRACK {tr.i + 1} EMPTY (TAP AGAIN TO REDO)"

    def _load(self, data):
        for i, td in enumerate(data[:TRACKS]):
            tr = self.tracks[i]
            self._clear(tr, keep_redo=False)
            if td.get("buf") is not None and len(td["buf"]) > 64:
                tr.buf = td["buf"].astype(np.float32)
                tr.L = len(tr.buf)
                tr.idx0 = int(td.get("idx0", 0)) % tr.L
                tr.start = self.T - tr.idx0
                tr.state = "stopped"
            for k in ("src", "fx", "reverse", "speed"):
                if k in td:
                    setattr(tr, k, td[k])
        self.master = next((t.i for t in self.tracks if t.has_audio()), None)

    def _fire(self, tr):
        when, act = tr.ev
        tr.ev = None
        if act == "rec_start":
            self._rec_start(tr, when, when)
        elif act in ("rec_end", "rec_end_stop"):
            if tr.state in ("rec", "ending"):
                self._finish_rec(tr, when)
                if act == "rec_end_stop" and tr.state == "play":
                    tr.state = "stopped"
        elif act == "play_start":
            tr.state = "play"

    # ------------------------------------------------------------------ audio
    def _history(self, tr, back):
        back = min(back, self.H - 1)
        idx = (self.hw - back + np.arange(back)) % self.H
        return self._src_mix(tr, self.hist_in[idx], self.hist_box[idx])

    def _src_mix(self, tr, a_in, a_box):
        s = tr.src if self.has_input else 1
        if s == 0:
            return a_in.copy()
        if s == 1:
            return a_box.copy()
        return a_in + a_box

    def busy(self):
        return bool(self.cmds) or any(t.state != "empty" for t in self.tracks)

    def process(self, n, inp, box, duck=None):
        """inp: interface input (n, 2) or None. box: PotentialBox's own mix (n, 2). Returns the loops or None."""
        v = self.eng.p.val
        while self.cmds:
            try:
                self._apply(self.cmds.popleft())
            except Exception:
                pass
        self.has_input = inp is not None
        if inp is None:
            inp = np.zeros((n, 2), dtype=np.float32)
        else:
            inp = inp * v["lp.in"]
            self.in_peak = max(float(np.abs(inp).max()) if n else 0.0, self.in_peak * 0.85)
        # history (also gives the input delayed by the round-trip latency, so it lines up with the loops)
        idx = (self.hw + np.arange(n)) % self.H
        self.hist_box[idx] = box
        self.hist_in[idx] = inp
        d = min(max(int(self.rt), 0), self.H - n - 1)
        if d:
            inp = self.hist_in[(self.hw - d + np.arange(n)) % self.H]
        self.hw = (self.hw + n) % self.H
        if not any(t.state != "empty" for t in self.tracks):
            self.T += n * self.rate
            return None
        out = np.zeros((n, 2))
        pos = 0
        while pos < n:
            now = self.T
            for tr in self.tracks:
                if tr.ev is not None and tr.ev[0] <= now + 0.5:
                    self._fire(tr)
            due = [tr.ev[0] for tr in self.tracks if tr.ev is not None]
            m = n - pos
            if due:
                m = int(min(m, max(1, math.ceil((min(due) - now) / self.rate))))
            seg_in = inp[pos:pos + m]
            seg_box = box[pos:pos + m]
            for tr in self.tracks:
                self._render_track(tr, now, m, seg_in, seg_box, out[pos:pos + m], v)
            self.T += m * self.rate
            pos += m
        # loop bus: filter and duck
        out = self.bus_fx(out, v)
        if duck is not None and v["lp.duck"] > 0.005:
            out = out * (1.0 - v["lp.duck"] * duck)[:, None]
        return out * v["lp.vol"]

    def bus_fx(self, out, v):
        if self.bus is None:
            from potentialbox.engine import MasterFX
            self.bus = MasterFX(self.sr)
        return self.bus.process(out, v["lp.filter"], 0.0)

    def _render_track(self, tr, now, m, seg_in, seg_box, out, v):
        st = tr.state
        if st == "rec" or st == "ending":
            if tr.got + m <= MAX_SECONDS * self.sr:
                tr.chunks.append(self._src_mix(tr, seg_in, seg_box))
                tr.got += m
            elif st == "rec":
                self._end_rec(tr, now, then="play")
            return
        if st not in ("play", "dub") or not tr.has_audio():
            tr.peak *= 0.9
            return
        L = tr.L
        sp = SPEEDS[tr.speed][1]
        p = (now - tr.start) + np.arange(m) * self.rate
        if sp == 1.0 and abs(self.rate - 1.0) < 1e-9:
            ii = (np.floor(p).astype(np.int64)) % L
            if tr.reverse:
                ii = L - 1 - ii
            y = tr.buf[ii]
        else:
            q = (p * sp) % L
            if tr.reverse:
                q = (L - 1) - q
            i0 = np.floor(q).astype(np.int64) % L
            fr = (q - np.floor(q))[:, None].astype(np.float32)
            y = tr.buf[i0] * (1 - fr) + tr.buf[(i0 + 1) % L] * fr
            ii = i0
        if st == "dub":
            fb = v["lp.fb"]
            tr.buf[ii] = tr.buf[ii] * fb + self._src_mix(tr, seg_in, seg_box)
        y = self._track_fx(tr, y.astype(np.float64), now, v)
        g = v[f"lp.t{tr.i + 1}.vol"]
        tr.peak = max(float(np.abs(y).max()) * g, tr.peak * 0.9)
        out += y * g

    def _track_fx(self, tr, y, now, v):
        amt = v[f"lp.t{tr.i + 1}.fx"]
        if amt < 0.01:
            return y
        kind = FX_TYPES[tr.fx]
        if kind == "Low-pass":
            return tr.mfx.process(y, -amt, 0.0)
        if kind == "High-pass":
            return tr.mfx.process(y, amt * 0.9, 0.0)
        if kind == "Lo-fi":
            return tr.mfx.process(y, 0.0, amt)
        beat = 60.0 / max(self.eng.bpm, 30.0)
        if kind == "Echo":
            return y + tr.delay.process(y * amt, beat * 0.75, 0.25 + 0.45 * amt, 5000.0)
        # Tremolo in eighths
        ph = (now + np.arange(len(y))) / (beat * 0.5 * self.sr)
        g = 1.0 - amt * (0.5 + 0.5 * np.cos(2 * np.pi * ph))
        return y * g[:, None]

    # ------------------------------------------------------------------ for the screen
    def progress(self, tr):
        if tr.state in ("rec", "ending"):
            g = self.grid()
            return None if g is None else ((self.T - tr.start) % g[1]) / g[1]
        if tr.has_audio() and tr.state in ("play", "dub"):
            return ((self.T - tr.start) * SPEEDS[tr.speed][1] % tr.L) / tr.L
        return None

    def length_text(self, tr):
        if not tr.has_audio():
            if tr.state in ("rec", "ending"):
                return f"{(self.T - tr.start) / self.sr:.1f} s"
            return ""
        sec = tr.L / self.sr
        bars = tr.L / self.bar_len()
        if abs(bars - round(bars)) < 0.02 and round(bars) >= 1:
            b = int(round(bars))
            return f"{b} BAR{'S' if b > 1 else ''} · {sec:.1f} s"
        return f"{sec:.1f} s"
