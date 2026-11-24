"""v2.4 SONG START: a bass line (Synth 1) and chords (Synth 2) in one key, in the style of a beat genre.

A Song is 4 bars (64 steps of a 16th) with a chord per bar. The beat generator plays it in time with the drums
(beats.BeatPlayer), so one tap gives you drums, bass and chords that fit together."""
import random

from potentialbox.keys import NAMES

MINOR = (0, 2, 3, 5, 7, 8, 10)
MAJOR = (0, 2, 4, 5, 7, 9, 11)
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]

# chord progressions as scale degrees (0 = the key's own chord), one chord per bar
PROG_MINOR = [(0, 5, 2, 6), (0, 3, 4, 0), (0, 6, 5, 6), (0, 0, 3, 3), (0, 5, 3, 4), (0, 3, 6, 2), (0, 2, 5, 4),
              (0, 3, 0, 4), (0, 6, 3, 4), (0, 0, 5, 6)]
PROG_MAJOR = [(0, 4, 5, 3), (0, 5, 3, 4), (1, 4, 0, 0), (0, 3, 0, 4), (5, 3, 0, 4), (0, 3, 4, 3), (0, 2, 3, 4)]

# bass rhythms, one bar of 16ths: R root, O root an octave up, 5 fifth, 3 the chord's third, b a step into the
# next chord, - hold the last note, . silence
BASS = {
    "four":   ["..R-..R-..R-..R-", "R-.RR-.RR-.RR-.R", "..R...O...R...O.", "R--.R5..R--.O-5.", "..R..R.R..R..R.R"],
    "techno": ["..R...R...R...R.", ".RR..RR..RR..RR.", "R.RR.RR.R.RR.RR."],
    "garage": ["R--..R.-..R--.5.", "R-..R..5-.R-.O..", "R--.R--..5-.R-.b"],
    "dnb":    ["R-------.....5--", "R-----------b---", "R--------..R-5--"],
    "half":   ["R-----..........", "R--.....R-..5-..", "R-------....O---", "R--..R--........"],
    "hiphop": ["R--..R-...R-.5..", "R-.R....R--..b..", "R---..R-..5---.."],
    "lofi":   ["R---..5-R---..b-", "R--..O..R--.5...", "R-----..5---3---"],
    "reggae": ["R-.R..5.R-..O.5.", "..R-5.R...R-5.R.", "R--.R..5R--.3..b"],
    "latin":  ["R..R..R.R..R..R.", "R-.R..5.R-.R..O.", "R..5..R.R..5..O."],
    "funk":   ["R.ORR.5.R.ORb.5.", "R..R.5..R.R..b..", "R.R.O.R.5.R.O.Rb"],
    "disco":  ["R.O.R.O.R.O.R.O.", "RO.ORO.ORO.ORO.O"],
    "electro": ["R.R..R.RR.R..5.R", "R-.R.-R.R-.R.O.R", "RR.R..R.RR.R..5."],
}
# chord rhythms: X a chord, - hold it, . silence
CHORDS = {
    "hold":   ["X---------------"],
    "half":   ["X-------X-------", "X-----------X---"],
    "stab":   ["..X...X...X...X.", "X..X..X...X..X..", "X.....X..X......", "..X-..X-..X-..X-"],
    "skank":  ["....X.......X...", "....X-......X-..", "..X...X...X...X."],
    "latin":  ["X..X..X.X..X..X.", "..X..X....X..X..", "X..X..X...X.X..."],
    "funk":   ["X.X..X.X..X.X...", ".X..X.X..X..X.X.", "X..X..X.X..X...."],
    "pulse":  ["X.X.X.X.X.X.X.X.", "XX.XX.XX.XX.XX.X"],
}

# per genre: bass style, chord style(s), chance of a major key, 7th chords, Synth 1 sounds, Synth 2 sounds
STYLE = {
    "Techno":         ("techno", ("hold", "pulse"), 0.0, False, ["Techno Rumble", "Acid 303", "Sub Foundation"],
                       ["Evolving Texture", "Deep Drone", "Glass Pad"]),
    "House":          ("four", ("stab",), 0.35, True, ["Deep House", "Moog Punch", "Sub Foundation"],
                       ["Garage Organ Stab", "Tremolo E-Piano", "Glass Keys", "Lush Pad"]),
    "Deep House":     ("four", ("stab", "hold"), 0.2, True, ["Deep House", "Sub Foundation"],
                       ["Tremolo E-Piano", "Lush Pad", "Glass Keys", "Garage Organ Stab"]),
    "Minimal":        ("techno", ("stab", "hold"), 0.0, False, ["Techno Rumble", "Sub Foundation", "Acid 303"],
                       ["Glass Keys", "Digital Stab", "Glass Pad"]),
    "UK Garage":      ("garage", ("stab", "half"), 0.2, True, ["Garage Organ Bass", "Sub Foundation", "Moog Punch"],
                       ["Garage Organ Stab", "Tremolo E-Piano", "Glass Keys"]),
    "Drum & Bass":    ("dnb", ("hold", "half"), 0.15, True, ["Reese Rumble", "Neuro Hornet", "Sub Foundation"],
                       ["Lush Pad", "Choir Air", "String Machine", "Glass Pad"]),
    "Jungle":         ("dnb", ("hold", "skank"), 0.1, False, ["Sub Foundation", "Reese Rumble", "Dub Sub"],
                       ["String Machine", "Choir Air", "Lush Pad"]),
    "Dubstep":        ("half", ("hold",), 0.0, False, ["Wobble 1/8", "FM Growl", "Sub Foundation"],
                       ["Deep Drone", "Choir Air", "Evolving Texture"]),
    "Grime":          ("half", ("stab", "hold"), 0.0, False, ["Sub Foundation", "FM Growl", "808 Glide"],
                       ["Digital Stab", "String Machine", "Glass Keys"]),
    "UK Drill":       ("half", ("hold", "half"), 0.0, False, ["808 Glide", "Sub Foundation"],
                       ["String Machine", "Choir Air", "Glass Pad"]),
    "Trap":           ("half", ("hold", "half"), 0.0, False, ["808 Glide", "Sub Foundation"],
                       ["Choir Air", "Glass Pad", "Lush Pad", "Glass Keys"]),
    "Hip Hop":        ("hiphop", ("hold", "half"), 0.2, True, ["Moog Punch", "808 Glide", "Sub Foundation"],
                       ["Tremolo E-Piano", "Lo-fi Keys", "String Machine"]),
    "Boom Bap":       ("hiphop", ("half", "hold"), 0.15, True, ["Moog Punch", "Sub Foundation"],
                       ["Tremolo E-Piano", "Lo-fi Keys", "String Machine", "Leslie Organ"]),
    "Lo-fi":          ("lofi", ("hold", "half"), 0.3, True, ["Sub Foundation", "Moog Punch"],
                       ["Lo-fi Keys", "Tremolo E-Piano", "Glass Keys"]),
    "Reggae One Drop": ("reggae", ("skank",), 0.4, False, ["Dub Sub", "Sub Foundation", "Moog Punch"],
                        ["Leslie Organ", "Clavinet", "Tremolo E-Piano"]),
    "Steppers":       ("reggae", ("skank",), 0.3, False, ["Dub Sub", "Sub Foundation"],
                       ["Leslie Organ", "Clavinet", "Glass Keys"]),
    "Dancehall":      ("latin", ("latin", "skank"), 0.3, False, ["808 Glide", "Sub Foundation", "Dub Sub"],
                       ["Digital Stab", "Glass Keys", "Marimba"]),
    "Reggaeton":      ("latin", ("latin",), 0.3, False, ["808 Glide", "Sub Foundation"],
                       ["Glass Keys", "Marimba", "Super Pluck", "Tremolo E-Piano"]),
    "Afrobeats":      ("latin", ("latin", "funk"), 0.55, True, ["Sub Foundation", "Moog Punch", "808 Glide"],
                       ["Marimba", "Kalimba", "Glass Keys", "Tremolo E-Piano"]),
    "Breakbeat":      ("funk", ("stab", "hold"), 0.2, False, ["Moog Punch", "Acid 303", "Reese Rumble"],
                       ["Digital Stab", "Lush Pad", "Glass Keys"]),
    "Electro":        ("electro", ("stab", "pulse"), 0.1, False, ["Electro Square", "Acid 303", "FM Growl"],
                       ["Digital Stab", "Glass Pad", "Super Pluck"]),
    "Disco":          ("disco", ("funk", "stab"), 0.6, True, ["Moog Punch", "Electro Square"],
                       ["String Machine", "Clavinet", "Tremolo E-Piano"]),
    "Funk":           ("funk", ("funk",), 0.5, True, ["Moog Punch", "Electro Square"],
                       ["Clavinet", "Leslie Organ", "Tremolo E-Piano"]),
    "Footwork":       ("half", ("half", "stab"), 0.1, True, ["808 Glide", "Sub Foundation"],
                       ["Choir Air", "Glass Keys", "Vocal Chop"]),
}
DEFAULT = ("four", ("hold",), 0.2, False, ["Sub Foundation"], ["Lush Pad"])


SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def flat_key(root, minor):
    """Keys written with flats (F, Bb, Eb ... major; D, G, C ... minor)."""
    return (root % 12) in ((2, 7, 0, 5, 10, 3, 8) if minor else (5, 10, 3, 8, 1))


def spell(pc, root, minor):
    pc %= 12
    if pc in (0, 2, 4, 5, 7, 9, 11):
        return SHARPS[pc]
    return (FLATS if flat_key(root, minor) else SHARPS)[pc]


def short_key(root, minor):
    return spell(root, root, minor) + ("m" if minor else "")


def key_name(root, minor):
    return spell(root, root, minor) + (" MINOR" if minor else " MAJOR")


class Song:
    """A generated bass line + chords. events: step -> [(part, (notes...), vel, length in steps)]."""
    STEPS = 64

    def __init__(self, genre_name, root=None, minor=None, seed=None, prog=None, bass_pat=None, chord_pat=None):
        self.seed = random.randrange(1 << 30) if seed is None else int(seed)
        rng = random.Random(self.seed)
        st = STYLE.get(genre_name, DEFAULT)
        self.genre = genre_name
        self.bass_style, chord_styles, p_major, self.sevenths, self.bass_sounds, self.pad_sounds = st
        self.minor = (rng.random() >= p_major) if minor is None else bool(minor)
        self.root = rng.choice([9, 2, 4, 7, 0, 5, 11, 1, 3, 6, 8, 10][:8 if rng.random() < 0.8 else 12]) if root is None else int(root) % 12
        progs = PROG_MINOR if self.minor else PROG_MAJOR
        self.prog = tuple(prog) if prog is not None else rng.choice(progs)
        self.bass_pat = bass_pat or [rng.choice(BASS[self.bass_style]) for _ in range(2)]
        self.chord_style = rng.choice(chord_styles)
        self.chord_pat = chord_pat or rng.choice(CHORDS[self.chord_style])
        self.build()

    # ---- music
    @property
    def scale(self):
        return MINOR if self.minor else MAJOR

    def chord_root_pc(self, deg):
        return (self.root + self.scale[deg % 7]) % 12

    def chord_pcs(self, deg):
        sc = self.scale
        n = 4 if self.sevenths else 3
        return [(self.root + sc[(deg + 2 * i) % 7] + 12 * ((deg + 2 * i) // 7)) for i in range(n)]

    def chord_name(self, deg):
        pcs = self.chord_pcs(deg)
        third = (pcs[1] - pcs[0]) % 12
        fifth = (pcs[2] - pcs[0]) % 12
        nm = spell(pcs[0], self.root, self.minor)
        if fifth == 6:
            return nm + "dim"
        nm += "m" if third == 3 else ""
        if self.sevenths:
            sev = (pcs[3] - pcs[0]) % 12
            nm += "maj7" if sev == 11 and third == 4 else "7"
        return nm

    def chords_text(self):
        return "  ".join(self.chord_name(d) for d in self.prog)

    def bass_base(self, pc):
        return 33 + ((pc - 9) % 12)   # A1 .. G#2

    def build(self):
        ev = {}
        prev = None
        for bar, deg in enumerate(self.prog):
            # ---- chords: voiced near middle C, moving as little as possible from the last chord
            pcs = [p % 12 for p in self.chord_pcs(deg)]
            best = None
            for inv in range(len(pcs)):
                order = pcs[inv:] + pcs[:inv]
                notes = [52 + (order[0] - 52) % 12]
                for pc in order[1:]:
                    notes.append(notes[-1] + 1 + (pc - notes[-1] - 1) % 12)
                cost = 0 if prev is None else sum(min(abs(a - b) for b in prev) for a in notes)
                cost += abs(sum(notes) / len(notes) - 64) * 0.5
                if best is None or cost < best[0]:
                    best = (cost, notes)
            notes = tuple(best[1])
            prev = notes
            pat = self.chord_pat
            for s, ch in enumerate(pat):
                if ch != "X":
                    continue
                ln = 1
                while s + ln < 16 and pat[s + ln] == "-":
                    ln += 1
                ev.setdefault(bar * 16 + s, []).append(("s2", notes, 84 if ln > 2 else 96, ln))
            # ---- bass
            bpat = self.bass_pat[bar % 2]
            root = self.bass_base(self.chord_root_pc(deg))
            nxt = self.prog[(bar + 1) % len(self.prog)]
            nroot = self.bass_base(self.chord_root_pc(nxt))
            third = root + (self.chord_pcs(deg)[1] - self.chord_pcs(deg)[0])
            for s, ch in enumerate(bpat):
                if ch in ".-":
                    continue
                ln = 1
                while s + ln < 16 and bpat[s + ln] == "-":
                    ln += 1
                if ch == "b":   # a scale step into the next chord's root
                    below = [nroot - k for k in (1, 2) if (nroot - k - self.root) % 12 in self.scale]
                    note = below[0] if below else nroot - 1
                else:
                    note = {"R": root, "O": root + 12, "5": root + 7, "3": third}.get(ch, root)
                acc = 112 if s % 4 == 0 else 96
                ev.setdefault(bar * 16 + s, []).append(("s1", (note,), acc, ln))
        self.events = ev

    # ---- edits (same key)
    def new_bass(self):
        rng = random.Random()
        self.bass_pat = [rng.choice(BASS[self.bass_style]) for _ in range(2)]
        self.build()

    def new_chords(self):
        rng = random.Random()
        progs = PROG_MINOR if self.minor else PROG_MAJOR
        self.prog = rng.choice([p for p in progs if p != self.prog] or progs)
        st = STYLE.get(self.genre, DEFAULT)
        self.chord_style = rng.choice(st[1])
        self.chord_pat = rng.choice(CHORDS[self.chord_style])
        self.build()

    def transpose(self, d):
        self.root = (self.root + d) % 12
        self.build()

    # ---- saving
    def to_json(self):
        return {"genre": self.genre, "root": self.root, "minor": self.minor, "seed": self.seed, "prog": list(self.prog),
                "bass_pat": list(self.bass_pat), "chord_pat": self.chord_pat, "chord_style": self.chord_style}

    @classmethod
    def from_json(cls, d):
        s = cls(d["genre"], d["root"], d["minor"], d.get("seed"), d.get("prog"), d.get("bass_pat"), d.get("chord_pat"))
        if d.get("chord_style") in CHORDS:
            s.chord_style = d["chord_style"]
        return s

    def notes(self):
        """For a MIDI file: [(step, part, note, vel, length)]."""
        out = []
        for st, lst in sorted(self.events.items()):
            for part, notes, vel, ln in lst:
                for nt in notes:
                    out.append((st, part, nt, vel, ln))
        return out
