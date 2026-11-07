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


# ways to end the loop that lead back to the start, by the genre's fill style
TURNS = {"roll": ["roll", "pickup", "openhat", "dropout", "kickrun"],
         "toms": ["toms", "pickup", "openhat", "dropout"],
         "break": ["pickup", "kickskip", "openhat", "dropout", "roll"]}
TURN_NAMES = {"roll": "snare roll", "pickup": "snare pickup", "openhat": "open hat", "dropout": "drop-out",
              "kickrun": "kick run", "toms": "tom run", "kickskip": "kick skip"}
BAR_CHOICES = [1, 2, 4]


class Beat:
    """A generated pattern of 1, 2 or 4 bars. The last bar ends with a change (a turnaround)
    that leads back to the start."""

    def __init__(self, genre=0, seed=None, bars=2):
        self.genre = genre % len(GENRES)
        self.rng = np.random.default_rng(seed)
        name, bpm, swing, native, kit, fill, parts = GENRES[self.genre]
        self.native = native
        self.bars = bars if bars in BAR_CHOICES else 2
        self.steps = max(16 * self.bars, 16) if not (native == 32 and self.bars == 1) else 16
        self.choice = {}
        self.base = {}
        self.grid = {}
        self.fill = fill_pattern(fill, native, self.rng)
        self.make_turn()
        for role in parts:
            self.pick(role)
        self.ensure_roles()

    def make_turn(self):
        """Choose the turnaround (one or two ideas) and the steps it changes: {role: {step: char}}"""
        fill = GENRES[self.genre][5]
        roles = GENRES[self.genre][6]
        L = self.steps
        kinds = list(TURNS[fill])
        first = kinds[int(self.rng.integers(len(kinds)))]
        chosen = [first]
        if self.rng.random() < 0.45:
            rest = [k for k in kinds if k != first and {k, first} != {"dropout", "kickrun"}]
            chosen.append(rest[int(self.rng.integers(len(rest)))])
        snare = "S" if "S" in roles else ("C" if "C" in roles else "R")
        kick = "K" if "K" in roles else "B"
        m = collections.defaultdict(dict)
        for k in chosen:
            if k == "roll":
                for i, ch in zip(range(L - 4, L), ["x", "x", "r", "t"]):
                    m[snare][i] = ch
            elif k == "pickup":
                pat = [["g", "x", "X"], [".", "x", "x"], ["x", ".", "X"], ["g", "g", "x"]][int(self.rng.integers(4))]
                for i, ch in zip(range(L - 3, L), pat):
                    m[snare][i] = ch
                m[kick][L - 1] = "."
            elif k == "openhat":
                at = L - 1 if self.rng.random() < 0.5 else L - 2
                m["O"][at] = "x"
                m["H"][at] = "."
            elif k == "dropout":
                for i in range(L - 4, L):  # kick and snare out for the last beat, hats carry on
                    m[kick][i] = "."
                    m[snare][i] = "."
                    if "C" in roles and snare != "C":
                        m["C"][i] = "."
                if self.rng.random() < 0.6:
                    m["Y"][0] = "x"  # crash back in on the one
            elif k == "kickrun":
                for i in range(L - 4, L):
                    m[kick][i] = "x" if i % 2 == 0 or self.rng.random() < 0.5 else "g"
            elif k == "kickskip":
                for i in range(L - 8, L):
                    m[kick][i] = "."
                for i in (L - 6, L - 3):
                    m[kick][i] = "x"
            elif k == "toms":
                run = [("T", "x"), ("T", "x"), ("M", "x"), ("L", "X")] if self.rng.random() < 0.6 else \
                      [("M", "g"), ("T", "x"), ("M", "x"), ("L", "x")]
                for i, (r, ch) in zip(range(L - 4, L), run):
                    m[r][i] = ch
                for i in range(L - 4, L):
                    m[snare].setdefault(i, ".")
        self.turn = dict(m)
        self.turn_kinds = chosen

    def pick(self, role, mutate=False):
        parts = GENRES[self.genre][6]
        vs = parts.get(role)
        if vs is None:
            self.base[role] = E[:self.native]
            self.expand(role)
            return
        cur = self.choice.get(role)
        if mutate and len(vs) > 1:
            k = int(self.rng.choice([i for i in range(len(vs)) if i != cur]))
        else:
            k = 0 if (len(vs) == 1 or self.rng.random() < 0.55) else int(self.rng.integers(1, len(vs)))
        self.choice[role] = k
        self.base[role] = _fit(vs[k], self.native)
        self.expand(role)

    def expand(self, role):
        """Repeat the genre pattern over the loop, vary the hats a little in later bars, then the turnaround."""
        b = self.base[role]
        L = self.steps
        s = list((b * (L // len(b) + 1))[:L])
        if role in "HZRGVW":
            for bar_start in range(0, L, 16):
                if self.rng.random() < (0.35 if bar_start else 0.5):
                    for _ in range(int(self.rng.integers(1, 3))):
                        i = bar_start + int(self.rng.integers(16))
                        if i < L:
                            s[i] = ";" if s[i] == "." else ("." if s[i] in "g;" else s[i])
        for i, ch in self.turn.get(role, {}).items():
            if 0 <= i < L:
                s[i] = ch
        if any(c != "." for c in s) or role in self.grid:
            self.grid[role] = "".join(s)
        else:
            self.grid.pop(role, None)

    def ensure_roles(self):
        for role in self.turn:
            if role not in self.base:
                self.base[role] = E[:self.native]
                self.expand(role)

    def mutate(self):
        roles = [r for r in self.base if r in GENRES[self.genre][6]]
        self.pick(roles[int(self.rng.integers(len(roles)))], mutate=True)

    def new_ending(self):
        self.make_turn()
        for role in list(self.base):
            self.expand(role)
        self.ensure_roles()

    # ---- SIMPLER / BUSIER: change the beat itself, one layer at a time
    def _row(self, role):
        return list(self.grid.get(role, E[:self.steps] * (self.steps // 32 + 1))[:self.steps])

    def _set(self, role, row):
        r = "".join(row)
        if any(c != "." for c in r):
            self.grid[role] = r
        else:
            self.grid.pop(role, None)

    def _turn_steps(self):
        return {i for d in getattr(self, "turn", {}).values() for i in d}

    def busier(self):
        """Add a layer. Returns a short description of what changed (or '')."""
        rng = self.rng
        L = self.steps
        keep = self._turn_steps()
        snare = "S" if "S" in self.grid else ("C" if "C" in self.grid else "S")
        kick = "K" if "K" in self.grid else ("B" if "B" in self.grid else "K")
        ideas = []
        h = self._row("H")
        if "H" not in self.grid:
            ideas.append("hats")
        elif sum(c != "." for c in h) < L * 0.75:
            ideas.append("hat16")
        if "?" in "".join(self.grid.values()):
            ideas.append("maybes")
        ideas += ["ghosts", "kick"]
        if "Z" not in self.grid:
            ideas.append("shaker")
        elif "G" not in self.grid:
            ideas.append("conga")
        rng.shuffle(ideas)
        done = []
        for idea in ideas:
            if len(done) >= 2:
                break
            if idea == "hats":
                self._set("H", [("x" if i % 4 == 2 else ".") for i in range(L)])
                done.append("offbeat hats")
            elif idea == "hat16":
                row = self._row("H")
                for i in range(L):
                    if row[i] == "." and i not in keep:
                        row[i] = "g" if i % 2 else "x"
                self._set("H", row)
                done.append("16th hats")
            elif idea == "maybes":
                for r, s2 in list(self.grid.items()):
                    self.grid[r] = s2.replace("?", "x").replace(";", "g")
                done.append("all maybe-hits play")
            elif idea == "ghosts":
                row = self._row(snare)
                free = [i for i in range(L) if row[i] == "." and i not in keep and i % 4 in (1, 3)]
                if not free:
                    continue
                for i in rng.choice(free, size=min(len(free), max(1, L // 12)), replace=False):
                    row[int(i)] = "g"
                self._set(snare, row)
                done.append("ghost snares")
            elif idea == "kick":
                row = self._row(kick)
                sn = self._row(snare)
                free = [i for i in range(L) if row[i] == "." and sn[i] == "." and i not in keep and i % 2 == 0
                        and i % 8 != 4]
                if not free:
                    continue
                row[int(rng.choice(free))] = "x"
                self._set(kick, row)
                done.append("extra kick")
            elif idea == "shaker":
                self._set("Z", [("g" if i % 2 else ";") for i in range(L)])
                done.append("shaker")
            elif idea == "conga":
                self._set("G", [("x" if (i % 16) in (3, 6, 11, 14) else ".") for i in range(L)])
                done.append("congas")
        return " + ".join(done)

    def simpler(self):
        """Take a layer away. Returns a short description of what changed (or '')."""
        L = self.steps
        keep = self._turn_steps()
        for r in ("Z", "G", "V", "W", "F"):
            if r in self.grid:
                self.grid.pop(r)
                return f"no {ROLE_NAME[r].lower()}"
        all_s = "".join(self.grid.values())
        if "?" in all_s or ";" in all_s:
            for r, s2 in list(self.grid.items()):
                self._set(r, list(s2.replace("?", ".").replace(";", ".")))
            return "no maybe-hits"
        if "g" in all_s:
            for r, s2 in list(self.grid.items()):
                self._set(r, list(s2.replace("g", ".")))
            return "no ghost notes"
        h = self._row("H")
        if sum(1 for i in range(1, L, 2) if h[i] != ".") > 0:
            for i in range(1, L, 2):
                if i not in keep:
                    h[i] = "."
            self._set("H", h)
            return "8th hats"
        if "R" in self.grid:
            self.grid.pop("R")
            return "no rim"
        if "O" in self.grid:
            self.grid.pop("O")
            return "no open hat"
        h = self._row("H")
        if sum(1 for i in range(L) if h[i] != "." and i % 4 != 2 and i % 4 != 0) == 0 and \
                sum(1 for i in range(0, L, 4) if h[i] != ".") > 0 and sum(1 for i in range(2, L, 4) if h[i] != ".") > 0:
            for i in range(0, L, 4):
                h[i] = "."
            self._set("H", h)
            return "offbeat hats only"
        return ""

    def turn_text(self):
        return " + ".join(TURN_NAMES[k] for k in getattr(self, "turn_kinds", []))

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
        return dict(genre=self.genre, steps=self.steps, bars=self.bars, grid=self.grid,
                    turn=getattr(self, "turn_kinds", []))

    @classmethod
    def from_json(cls, d):
        b = cls(int(d.get("genre", 0)), bars=int(d.get("bars", 2)))
        g = d.get("grid")
        if isinstance(g, dict):
            b.steps = int(d.get("steps", b.steps))
            b.grid = {r: _fit(s, b.steps) for r, s in g.items() if r in ROLE_PAD}
            b.turn_kinds = [k for k in d.get("turn", []) if k in TURN_NAMES]
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

    def on_tick(self, t, offset=0):
        """Clock tick while the transport plays; step k starts at tick 6k."""
        if t % 6:
            return
        k = t // 6
        if self.send == "armed" and k % self.beat.steps == 0:
            self.send = "sending"
            self.sent = 0
        if self.on or self.send == "sending":
            self._step(k, offset)

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
