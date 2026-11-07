"""Genre beat generator and player.

Patterns are written per drum role as step strings and turned into hits with a bit of randomness, so
every NEW BEAT is a different take on the genre. The player runs on the audio thread: locked to the
BeatStep's clock while it plays, otherwise on its own tempo. It can also send the beat once over MIDI
to the BeatStep so its drum sequencer can record it.

Step characters: X accent, x hit, g ghost, ? hit half the time, ; ghost half the time,
r two quick hits (32nds), t three quick hits (triplet roll), . rest.
"""
import collections
import math

import numpy as np

# shared kit layout (0-based pads)
ROLE_PAD = {"K": 0, "B": 1, "S": 2, "C": 3, "H": 4, "O": 5, "L": 6, "M": 7, "T": 8, "R": 9,
            "W": 10, "V": 11, "Z": 12, "Y": 13, "F": 14, "G": 15}
ROLE_NAME = {"K": "Kick", "B": "808 / kick 2", "S": "Snare", "C": "Clap", "H": "Closed hat", "O": "Open hat",
             "L": "Low tom", "M": "Mid tom", "T": "High tom", "R": "Rim", "W": "Cowbell", "V": "Clave",
             "Z": "Shaker", "Y": "Cymbal", "F": "FX", "G": "Conga"}
GROUPS = {"Kick": (0, 1), "Snare": (2, 3, 9), "Hats": (4, 5, 13), "Perc": (6, 7, 8, 10, 11, 12, 14, 15)}
GROUP_NAMES = list(GROUPS)
KIT_NAMES = ["Potential", "808 Boom", "909 Punch", "606 Tight", "Trap 808", "SP Dust", "Electro 80s", "Minimal Tech",
             "Industrial"]

E = "................................"

# name, bpm, swing %, steps, factory kit, fill style, parts {role: [variants, first = the classic]}
GENRES = [
    ("Techno", 130, 50, 16, 2, "roll", {
        "K": ["X...X...X...X...", "X...X...X...X..x", "X...X...X..xX..."],
        "C": ["....x.......x...", "", "....x.......x..;"],
        "H": ["..x...x...x...x.", "x.x.x.x.x.x.x.x.", "gxgxgxgxgxgxgxgx"],
        "O": ["..x...x...x...x.", "", "......x.......x."],
        "R": ["...?..?....?..?.", "", "..;...;...;...;."],
        "Y": ["", "x.x.x.x.x.x.x.x.", ""],
        "W": ["", "...?.......?...."]}),
    ("House", 124, 54, 16, 2, "roll", {
        "K": ["X...X...X...X...", "X...X...X...X..?"],
        "C": ["....x.......x...", "....x.......x..g"],
        "H": ["x.x.x.x.x.x.x.x.", "gxgxgxgxgxgxgxgx", ""],
        "O": ["..x...x...x...x."],
        "Z": ["xgxgxgxgxgxgxgxg", ""],
        "V": ["...?..?....?...?", ""],
        "G": ["......?.......?.", ""]}),
    ("Deep House", 120, 58, 16, 5, "roll", {
        "K": ["X...X...X...X..."],
        "R": ["....x.......x...", "...;x..;....x..;"],
        "C": ["", "............x..."],
        "H": ["..x...x...x...x.", "x;x;x;x;x;x;x;x;"],
        "Z": ["gggggggggggggggg", ""],
        "G": ["...x..?....x..?.", "......x.......x."]}),
    ("Minimal", 126, 55, 16, 7, "break", {
        "K": ["X...X...X...X...", "X...X..?X...X..."],
        "R": ["...x.....x....x.", "..x...x.?..x...."],
        "C": ["....x.......x...", "............x..."],
        "H": ["..x...x...x...x.", "..x..;x...x..;x."],
        "W": ["?..?...?..?....?", ""],
        "V": ["", ".?....?....?...."]}),
    ("UK Garage", 132, 64, 16, 2, "roll", {
        "K": ["X.........X.....", "X......x..X.....", "X.....x...X....."],
        "S": ["....X.......X...", "....X.......X..g"],
        "C": ["....x.......x...", ""],
        "H": ["..x...x...x...x.", "..xx..x...xx..x."],
        "O": ["......x.......?.", ""],
        "R": ["...;...;...;..;.", "......;.....;..."]}),
    ("Drum & Bass", 174, 50, 32, 0, "roll", {
        "K": ["X.........X.....X.........?.....", "X.........X.x...X.........X.....", "X.......X.X.....X.........X..x.."],
        "S": ["....X.......X.......X.......X...", "....X..g....X..g....X..g....X..g"],
        "H": ["x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.", "x.xxx.xxx.xxx.xxx.xxx.xxx.xxx.xx"],
        "O": ["..............x...............?.", ""],
        "Y": ["", "x.......x.......x.......x......."],
        "Z": ["", "gggggggggggggggggggggggggggggggg"]}),
    ("Jungle", 168, 52, 32, 5, "break", {
        "K": ["X.........X.....X.x.......X.....", "X.X.......X.....X.........X.x..."],
        "S": ["....X..g.g.X..g.....X..g.g.X..g.", "....X.......X..g.g..X.......X.gg"],
        "H": ["x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.", "x;x;x;x;x;x;x;x;x;x;x;x;x;x;x;x;"],
        "Y": ["x...............x...............", ""],
        "R": ["", "...;.......;...;...;.......;...;"]}),
    ("Dubstep", 140, 50, 32, 1, "toms", {
        "K": ["X.........x.....X.........?.....", "X.....x.........X.....x...x....."],
        "S": ["........X...............X.......", "........X...............X.....g."],
        "C": ["........x...............x.......", ""],
        "H": ["x...x...x...x...x...x...x...x...", "x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.", "..x...x...x...x...x...x...x...x."],
        "O": ["......x...............x.........", ""]}),
    ("Grime", 140, 50, 16, 6, "break", {
        "K": ["X.....x...X.x...", "X..x......X.....", "X.....X.....x..."],
        "S": ["....X.......X...", "........X......."],
        "C": ["....x.......x...", ""],
        "H": ["x.x.x.x.x.x.x.x.", "x...x...x...x...", "..x...x...x...x."],
        "V": ["...?......?....?", ""]}),
    ("UK Drill", 142, 50, 32, 4, "toms", {
        "K": ["X.........................x.....", ""],
        "B": ["X.....x...x.....X......x..x.....", "X........x..X...X.....x.....x..."],
        "S": ["........X...............X.....x.", "........X.........;.....X......."],
        "H": ["x..x..x.x..x..x.x..x..x.x..x.tx.", "x..x..x...x..x..x..x..x...x.t..x"],
        "R": ["", "......;...............;........."]}),
    ("Trap", 140, 50, 32, 4, "roll", {
        "B": ["X.........X.....X.....x...x.....", "X......x..X.......x..X.....x....", "X.....X.....x...X.......x.x....."],
        "C": ["........X...............X.......", "........X...............X.....g."],
        "S": ["", "........x...............x......."],
        "H": ["x.x.x.x.x.x.x.xrx.x.x.x.x.r.x.x.", "xxxxxxxxxxxxtxxxxxxxxxxxxxxrxrxr", "x.x.x.x.x.x.x.x.x.x.x.x.t...x.x."],
        "O": ["..............x...............?.", ""]}),
    ("Hip Hop", 92, 58, 16, 1, "break", {
        "K": ["X......x..X.....", "X.....x...X..x..", "X..x......X....."],
        "S": ["....X.......X...", "....X.......X..g"],
        "H": ["x.x.x.x.x.x.x.x.", "x.x.x.x.x.x.x.xx", "xgxgxgxgxgxgxgxg"],
        "O": ["..............x.", ""]}),
    ("Boom Bap", 88, 63, 16, 5, "break", {
        "K": ["X.....x...X.x...", "X..x......X.....", "X......x.xX....."],
        "S": ["....X.......X...", "....X..g....X..g"],
        "H": ["x.x.x.x.x.x.x.x.", "x.X.x.X.x.X.x.X."],
        "O": ["..............?.", ""],
        "R": ["...;......;....;", ""]}),
    ("Lo-fi", 78, 66, 16, 5, "break", {
        "K": ["X......x..X.....", "X.....x...x..x.."],
        "S": ["....x.......x...", "....x..;....x..;"],
        "H": ["x;x;x;x;x;x;x;x;", "x.x.x.x.x.x.x.x."],
        "Z": ["g.g.g.g.g.g.g.g.", ""],
        "R": ["", "..;.......;....."]}),
    ("Reggae One Drop", 76, 60, 16, 0, "toms", {
        "K": ["........X......."],
        "R": ["........X.......", "....;...X.......", "........X.....;."],
        "H": ["x.x.x.x.x.x.x.x.", "..x...x...x...x.", "x.xxx.xxx.xxx.xx"],
        "O": ["..............?.", ""],
        "G": ["", "......?.......?."]}),
    ("Steppers", 76, 58, 16, 0, "toms", {
        "K": ["X...X...X...X..."],
        "R": ["........X.......", "....X.......X..."],
        "H": ["x.x.x.x.x.x.x.x.", "..x...x...x...x."],
        "O": ["", "..............x."],
        "W": ["", "x.......x......."]}),
    ("Dancehall", 100, 52, 16, 1, "break", {
        "K": ["X..x..x.X..x..x.", "X.......X.......", "X..x....X..x...."],
        "S": ["...x..x....x..x.", "...X..x.....x..."],
        "H": ["x.x.x.x.x.x.x.x.", ""],
        "V": ["x..x..x...x.x...", ""],
        "G": ["", "..?...x...?...x."]}),
    ("Reggaeton", 95, 50, 16, 4, "break", {
        "K": ["X...X...X...X..."],
        "S": ["...x..x....x..x.", "...x..x....x.xx."],
        "H": ["x.x.x.x.x.x.x.x.", "................"],
        "V": ["", "x..x..x...x.x..."],
        "O": ["", "..............x."]}),
    ("Afrobeats", 108, 56, 16, 0, "toms", {
        "K": ["X......x..X.....", "X.....x...X..x.."],
        "R": ["...x..x....x..x.", "...x..x.x..x..x."],
        "Z": ["x.xxx.xxx.xxx.xx", "xgxgxgxgxgxgxgxg"],
        "G": ["......x.?.....x.", "..x...x...x.x..."],
        "C": ["", "....x.......x..."],
        "W": ["", "x.x.xx.x.x.x.xx."]}),
    ("Breakbeat", 130, 52, 16, 6, "break", {
        "K": ["X.........X.x...", "X.X.......x....."],
        "S": ["....X..g.g..X..g", "....X.......X..."],
        "H": ["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx"],
        "O": ["..............x.", ""]}),
    ("Electro", 125, 50, 16, 6, "roll", {
        "K": ["X.....X...X.....", "X.....X...X..X.."],
        "S": ["....X.......X..."],
        "C": ["....x.......x...", ""],
        "H": ["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx"],
        "W": ["..x.....x.x.....", ""]}),
    ("Disco", 118, 52, 16, 2, "roll", {
        "K": ["X...X...X...X..."],
        "S": ["....X.......X..."],
        "C": ["", "....x.......x..."],
        "O": ["..x...x...x...x."],
        "H": ["xgxgxgxgxgxgxgxg", "x.x.x.x.x.x.x.x."],
        "G": ["", "...x..x....x..x."]}),
    ("Funk", 100, 56, 16, 5, "break", {
        "K": ["X.x....x..X.....", "X..x...x.xX....."],
        "S": ["....X..g.g..X..g", "....X.g..g..X..."],
        "H": ["xgxgxgxgxgxgxgxg", "xxxxxxxxxxxxxxxx"],
        "O": ["", "......x.......x."]}),
    ("Footwork", 160, 50, 32, 1, "roll", {
        "K": ["X..X..X...X..X..X..X..X...X..X..", "X..X......X..X..X..X......X..X.."],
        "C": ["........x...............x.......", "....x.......x.......x.......x..."],
        "H": ["..x...x...x...x...x...x...x...x."],
        "R": ["", "...;...;...;...;...;...;...;...;"]}),
]
GENRE_NAMES = [g[0] for g in GENRES]


def _fit(s, steps):
    if not s:
        return E[:steps]
    return (s * (steps // len(s) + 1))[:steps]


def cell(ch, rng, human):
    """step character -> (probability, velocity, ratchet) or None"""
    base = {"X": (1.0, 118, 1), "x": (1.0, 96, 1), "g": (1.0, 44, 1), "?": (0.5, 90, 1), ";": (0.5, 42, 1),
            "r": (1.0, 84, 2), "t": (1.0, 78, 3)}.get(ch)
    if base is None:
        return None
    p, v, r = base
    v = int(min(127, max(1, v + rng.normal(0, 4 + 10 * human))))
    return p, v, r, ch == "X"


def fill_pattern(style, steps, rng):
    """One bar (16 steps) to play while FILL is held: {pad: [(step, vel, ratchet)]}"""
    out = collections.defaultdict(list)
    if style == "toms":
        seq = [(8, 9), (8, 10), (7, 11), (7, 12), (7, 13), (6, 14), (6, 15)]
        out[2] += [(4, 96, 1), (12, 100, 1)]
        for pad, st in seq:
            out[pad].append((st, 90 + st, 1))
        out[0] += [(0, 118, 1), (8, 100, 1)]
    elif style == "break":
        for st in (0, 3, 6, 10, 11):
            out[0].append((st, 112, 1))
        for st in (4, 7, 9, 12, 13, 14, 15):
            out[2].append((st, 80 + st * 2, 1 if st < 14 else 2))
    else:  # roll: snare 16ths getting louder, faster at the end
        for st in range(16):
            out[2].append((st, 50 + st * 4, 1 if st < 12 else 2))
        out[0] += [(0, 118, 1), (4, 110, 1), (8, 110, 1), (12, 110, 1)]
    return out


class Beat:
    """A generated pattern: hits[step] = [(pad, prob, vel, ratchet, core)]"""

    def __init__(self, genre=0, seed=None, busy=0.0):
        self.genre = genre % len(GENRES)
        self.rng = np.random.default_rng(seed)
        name, bpm, swing, steps, kit, fill, parts = GENRES[self.genre]
        self.steps = steps
        self.choice = {}
        self.grid = {}
        for role in parts:
            self.pick(role)
        self.fill = fill_pattern(fill, steps, self.rng)

    def pick(self, role, mutate=False):
        parts = GENRES[self.genre][6]
        vs = parts[role]
        cur = self.choice.get(role)
        if mutate and len(vs) > 1:
            k = int(self.rng.choice([i for i in range(len(vs)) if i != cur]))
        else:
            k = 0 if (len(vs) == 1 or self.rng.random() < 0.55) else int(self.rng.integers(1, len(vs)))
        self.choice[role] = k
        s = _fit(vs[k], self.steps)
        # small surprise: sometimes swap a rest for a ghost or a ghost for a rest on hats/perc
        if role in "HZRGVW" and self.rng.random() < 0.5:
            s = list(s)
            for _ in range(int(self.rng.integers(1, 3))):
                i = int(self.rng.integers(self.steps))
                s[i] = ";" if s[i] == "." else ("." if s[i] in "g;" else s[i])
            s = "".join(s)
        self.grid[role] = s

    def mutate(self):
        roles = list(self.grid)
        self.pick(roles[int(self.rng.integers(len(roles)))], mutate=True)

    def hits_at(self, step, human):
        out = []
        for role, s in self.grid.items():
            c = cell(s[step % self.steps], self.rng, human)
            if c:
                out.append((ROLE_PAD[role], *c))
        return out

    def toggle(self, role, step):
        s = list(self.grid.get(role, E[:self.steps]))
        s[step] = "." if s[step] != "." else "x"
        self.grid[role] = "".join(s)

    def to_json(self):
        return dict(genre=self.genre, steps=self.steps, grid=self.grid)

    @classmethod
    def from_json(cls, d):
        b = cls(int(d.get("genre", 0)))
        g = d.get("grid")
        if isinstance(g, dict):
            b.steps = int(d.get("steps", b.steps))
            b.grid = {r: _fit(s, b.steps) for r, s in g.items() if r in ROLE_PAD}
        return b


class BeatPlayer:
    """Audio-thread player. The GUI changes `beat`, `on`, `mutes`, `send` (atomic attribute sets)."""

    def __init__(self, eng):
        self.eng = eng
        self.sr = eng.sr
        self.beat = Beat(0)
        self.on = False
        self.auto = False          # was on when the BeatStep stopped: comes back with its next Start
        self.mutes = set()
        self.pos = 0.0             # own clock (samples since start) when the BeatStep isn't playing
        self.step = None
        self.pending = []          # (abs sample, pad, vel)
        self.midi_out = None       # callable(pad, vel) for SEND TO BEATSTEP
        self.send = None           # None | "armed" | "sending"
        self.sent = 0
        self.send_done = False
        self.var_rng = np.random.default_rng(7)

    # transport hooks (audio thread)
    def on_start(self):
        if self.auto:
            self.on = True
            self.auto = False

    def on_stop(self):
        if self.on:
            self.auto = True
            self.on = False
        if self.send == "sending":
            self.send = None
        self.pending = []

    def on_tick(self, t):
        """BeatStep clock tick while it plays; step k starts at tick 6k."""
        if t % 6:
            return
        k = t // 6
        if self.send == "armed" and k % self.beat.steps == 0:
            self.send = "sending"
            self.sent = 0
        if self.on or self.send == "sending":
            self._step(k, 0)

    def step_len(self):
        return 60.0 / max(self.eng.bpm, 30.0) / 4.0 * self.sr

    def _step(self, k, offset):
        v = self.eng.p.val
        b = self.beat
        st = k % b.steps
        self.step = st
        L = self.step_len()
        swing = v["bt.swing"] if v["bt.swing"] > 50.5 else GENRES[b.genre][2]
        delay = ((swing - 50.0) / 50.0) * L if st % 2 else 0.0
        human = v["bt.human"]
        busy = v["bt.busy"]
        fill = self.eng.fill and self.send != "sending"
        hits = b.hits_at(st, human)
        if fill:
            fp = b.fill
            hits = [h for h in hits if h[0] in (4, 5, 12, 13)]
            for pad, lst in fp.items():
                for s2, vel, rat in lst:
                    if s2 == st % 16:
                        hits.append((pad, 1.0, vel, rat, True))
        # variation: a little something extra now and then
        if v["bt.var"] > 0.01 and self.var_rng.random() < v["bt.var"] * 0.25 and not fill:
            pad = [4, 2, 0, 12][int(self.var_rng.integers(4))]
            hits.append((pad, 1.0, 40 if pad == 2 else 70, 2 if pad == 4 else 1, False))
        now = self.eng.samples + offset
        sending = self.send == "sending"
        for pad, p, vel, rat, core in hits:
            if any(pad in GROUPS[g] for g in self.mutes) and not sending:
                continue
            if p < 1.0:
                p = min(max(p + 0.4 * busy, 0.0), 1.0)
            elif not core and busy < 0:
                p = 1.0 + busy * 0.7
            if p < 1.0 and self.var_rng.random() > p:
                continue
            jit = self.var_rng.normal(0, 0.004 * self.sr * human) if human > 0.01 else 0.0
            for j in range(rat):
                at = now + delay + jit + j * (L / rat)
                self.pending.append((max(at, self.eng.samples), pad, max(1, int(vel * (0.85 if j else 1.0)))))
                if sending and j == 0 and self.midi_out:
                    try:
                        self.midi_out(pad, vel)
                    except Exception:
                        pass
        if sending:
            self.sent += 1
            if self.sent >= b.steps:
                self.send = None
                self.send_done = True

    def render_hits(self, n):
        """Called before the drums render: start the hits that fall in this block."""
        eng = self.eng
        if self.on and not eng.playing:
            L = self.step_len()
            k0 = int(math.ceil(self.pos / L - 1e-9))
            t = k0 * L
            while t < self.pos + n:
                self._step(k0, int(t - self.pos))
                k0 += 1
                t = k0 * L
            self.pos += n
        elif not self.on:
            self.pos = 0.0
        if not self.pending:
            return
        end = eng.samples + n
        keep = []
        for at, pad, vel in self.pending:
            if at < end:
                off = int(at - eng.samples)
                if eng.cond_ok(pad):
                    eng.drums.trigger(pad, vel, off)
                    if pad == int(eng.p.val["dk.src"]):
                        eng.duck_hit = off
            else:
                keep.append((at, pad, vel))
        self.pending = keep
