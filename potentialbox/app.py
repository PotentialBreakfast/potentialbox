"""PotentialBox - drum sampler + 2 synths, pre-wired to the Arturia BeatStep Pro.

Seq 1 (MIDI ch 1)  -> Synth 1 (analog-style)
Seq 2 (MIDI ch 2)  -> Synth 2 (wavetable)
Drum  (MIDI ch 10) -> Drums  (16 pads, notes 36-51)
16 knobs (CNTRL mode) -> the 16 knobs on the current page

Look: the PotentialSuite looks (Print Plate, Night Rack, Colour Block, Vintage), picked on the Setup tab.
"""
import os
import sys
import json
import copy
import math
import time
import traceback
import threading
import collections
import random

os.environ.setdefault("SD_ENABLE_ASIO", "1")  # load the ASIO-enabled PortAudio on Windows

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

try:
    import sounddevice as sd
except Exception:  # ASIO build failed to load: fall back to the plain one
    for m in ("sounddevice", "_sounddevice"):
        sys.modules.pop(m, None)
    os.environ.pop("SD_ENABLE_ASIO", None)
    try:
        import sounddevice as sd
    except Exception:
        sd = None

try:
    import mido
    mido.set_backend("mido.backends.rtmidi")
except Exception:
    mido = None

import tkinter as tk  # noqa: E402
from tkinter import font as tkfont, filedialog  # noqa: E402

from potentialbox.engine import (Engine, ParamStore, SPECS, PAGES, PRESETS, MACROS, SUBPAGES,  # noqa: E402
                                 MOD_SOURCES, MOD_DESTS, PUNCH_FX, PRESET_CAT, PRESET_CATS, bounce_stems)
from potentialbox import capture  # noqa: E402
from potentialbox import kits as _kits  # noqa: E402
from potentialbox.recorder import Recorder, write_wav, recordings_dir  # noqa: E402
from potentialbox.looper import TRACKS, SOURCES, FX_TYPES, SPEEDS, LENGTHS, STATE_TEXT  # noqa: E402
from potentialbox import parts as partsmod
from potentialbox import beats as beatsmod  # noqa: E402
from potentialbox.beats import (Beat, GENRES, GENRE_NAMES, ROLE_PAD, ROLE_NAME, GROUP_NAMES,  # noqa: E402
                               GROUPS as BEAT_GROUPS, BAR_CHOICES)
from potentialbox import kits  # noqa: E402
from potentialbox.library import Library, map_kit, brand_of  # noqa: E402
from potentialbox.samples import (SampleIndex, default_roots, GROUPS, TYPES,  # noqa: E402
                                  SHORT as SHORT_TYPE, group_of_type)
from potentialbox import kitmaker  # noqa: E402
from potentialbox.mpcsync import MpcSync, MpcSend  # noqa: E402
from potentialbox import projects as projmod  # noqa: E402
from potentialbox.voice import Voice, friendly_error, MIN_CONFIDENCE  # noqa: E402
try:                                      # hi-fi sprites are optional; the app falls back to flat drawing
    from potentialbox import skins
except Exception:                         # pragma: no cover
    skins = None

APP = "PotentialBox"
VERSION = "2.4.0"
W, H = 1280, 800
FACTORY_CCS = [10, 74, 71, 76, 77, 93, 73, 75, 114, 18, 19, 16, 17, 91, 79, 72]
# v2.0: five big sections along the bottom; each has a few sub-tabs (shown in the header). A sub-tab is one of the
# pages below, so BeatStep knobs, step locks and pad actions still work page by page.
SECTIONS = [
    ("JAM", [("PROJECTS", "Projects"), ("LIVE FX", "Live"), ("KNOBS", "Perform"), ("MACROS", "Macros")]),
    ("SOUNDS", [("SYNTH 1", "Synth 1"), ("SYNTH 2", "Synth 2"), ("DRUMS", "Drums"), ("MIX", "Mix"), ("FX", "FX")]),
    ("BEATS", [("BEATS", "Beats"), ("SONG START", "Song"), ("ARRANGE", "Arrangement")]),
    ("CAPTURE", [("STEMS", "Capture"), ("LOOPER", "Loop")]),
    ("SETUP", [("SETUP", "Setup")]),
]
SECTION_OF = {pg: sec for sec, subs in SECTIONS for _, pg in subs}
TABS = [pg for _, subs in SECTIONS for _, pg in subs]   # every page you can be on, in order (NEXT / PREVIOUS TAB)
# pages from 1.x that are now part of another tab: old page -> (new page, its sub-page)
OLD_PAGES = {"Drums 1-8": ("Drums", 1), "Drums 9-16": ("Drums", 2), "Mix & FX": ("Mix", 0)}
TAB_LABEL = {"Arrangement": "Arrange"}
SHORT_DEST = {"Wave position": "Wave pos", "Saw > Square": "Wave", "Pulse width": "Pulse w.", "Osc 2 pitch": "Osc 2",
              "Resonance": "Reso", "Velocity": "Vel", "Smooth random": "Smooth"}
CFG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), APP)
_kits.CACHE_DIR = os.path.join(CFG_DIR, "kit-cache")   # v2.1: built drum kits, made once
CFG_FILE = os.path.join(CFG_DIR, "state.json")
LOG_FILE = os.path.join(CFG_DIR, "log.txt")
SOUNDS_FILE = os.path.join(CFG_DIR, "my-sounds.json")
SLOTS = 8
KITS_FILE = os.path.join(CFG_DIR, "my-kits.json")
SETUPS_FILE = os.path.join(CFG_DIR, "my-setups.json")
SAMPLE_INDEX_FILE = os.path.join(CFG_DIR, "sample-index.json")
MPC_ONESHOTS_DIR = os.path.join(os.path.expanduser("~"), "Music", "MPC Drum One Shots")
RESAMPLE_DIR = os.path.join(CFG_DIR, "Resampled")
NO_LOCK_PAGES = ("Macros", "Projects", "Beats", "Live", "Loop", "Setup", "Capture")
OWN_SCREEN_PAGES = ("Projects", "Beats", "Live", "Loop", "Capture")  # tabs that draw their own screen and turn the pads into their own pads
LOOP_PADS = [f"Track {t} rec / play / dub" for t in range(1, 6)] + ["Undo / redo", "All stop / play",
             "Record next empty track"] + [f"Track {t} stop (hold: clear)" for t in range(1, 6)] + [
             "Reverse last track", "Speed last track", "Back to last tab"]
BEAT_PADS = ["Play / stop", "New beat", "Back (previous beat)", "Next genre", "Hold: Fill", "Mutate", "Simpler", "Busier",
             "Mute kick", "Mute snare", "Mute hats", "Mute perc", "Tempo down", "Tempo up", "Send to BeatStep",
             "Back to last tab"]
ACTIONS = [("rand_s1", "Random Synth 1"), ("rand_s2", "Random Synth 2"), ("rand_kit", "Random Drum Kit"),
           ("next_kit", "Next Kit"), ("prev_tab", "Previous Tab"), ("next_tab", "Next Tab"),
           ("tab:Perform", "Perform Tab"), ("tab:Synth 1", "Synth 1 Tab"), ("tab:Synth 2", "Synth 2 Tab"),
           ("tab:Drums 1-8", "Drums Tab"), ("tab:Drums 9-16", "Drums 9-16 Tab"), ("tab:Mix", "Mix Tab"),
           ("next_s1", "Synth 1 Next Sound"), ("next_s2", "Synth 2 Next Sound"), ("tab:Macros", "Macros Tab"),
           ("panic", "All Notes Off"),
           # v1.6: no default pad, tap the card and press a pad or step to use them
           ("tab:Live", "Live Tab"), ("tab:FX", "FX Tab"), ("rec", "Record On/Off"), ("fill", "Fill (hold)"),
           ("tab:Loop", "Loop Tab"), ("tab:Beats", "Beats Tab"), ("tab:Projects", "Projects Tab"),
           ("proj_mutate", "Mutate Project Sounds"), ("proj_back", "Project Sounds Back"),
           # v2.0
           ("tab:Capture", "Capture Tab"), ("bounce", "Bounce Stems"), ("send_mpc", "Send Last Bounce to MPC"),
           ("sec:JAM", "Jam Section"), ("sec:SOUNDS", "Sounds Section"),
           # v2.2
           ("grab", "Grab Last Bars"), ("beat_back", "Previous Beat (Back)"),
           # v2.3
           ("bounce_send", "Bounce + Send to MPC"), ("listen_last", "Listen to Last Bounce"),
           # v2.4
           ("song_start", "Song Start (same genre)"), ("song_surprise", "Song Start (surprise me)")]
ACTION_NAMES = dict(ACTIONS)
CAPTURE_PADS = ["Bounce 1 bar", "Bounce 2 bars", "Bounce 4 bars", "Bounce 8 bars", "Send last bounce to MPC",
                "Record on/off", "Cancel bounce", "Grab last bars", "Listen to last bounce",
                "Bounce + send to MPC"] + [""] * 5 + ["Back to last tab"]
PROJECT_PADS = [f"Load project {i} ({n})" for i, n in enumerate(projmod.NAMES, 1)]  # Projects tab pads
PAD_ACTIONS = [aid for aid, _ in ACTIONS[:16]]
HOLD_ACTIONS = {"fill"}
# On the Live tab the 16 BeatStep pads (the ones set to pad actions 1-16) play these instead
LIVE_PADS = [f"Hold: {n}" for n in PUNCH_FX] + ["Hold: Fill", "Hold: Scene morph", "Record on/off", "Random Synth 1",
                                                 "Random Synth 2", "Random Drum Kit", "Grab last bars", "Back to last tab"]


def default_actions():
    """BeatStep Pro pads in CNTRL mode, MIDI channel 16, notes 36-51 -> the first 16 actions in order."""
    d = {aid: {"t": "note", "ch": 16, "n": 36 + i} for i, aid in enumerate(PAD_ACTIONS)}
    d.update({aid: None for aid, _ in ACTIONS[16:]})
    return d


KNOB_GROUPS = {
    "Perform": [(0, 4, "Synth 1 (bass)"), (4, 8, "Synth 2 (lead)"), (8, 12, "Drums"), (12, 16, "Effects & level")],
    "Drums Bus": [(0, 4, "Punch, room & width"), (4, 8, "Tone, drive, crush & filter"), (8, 13, "Kit tune & levels"),
                  (13, 16, "Sends & volume")],
    "Synth 1 Quick": [(0, 4, "Filter"), (4, 8, "Envelope"), (8, 12, "Character"), (12, 16, "Glide, space & level")],
    "Synth 2 Quick": [(0, 5, "Wave & filter"), (5, 8, "Envelope"), (8, 12, "Character"), (12, 16, "Movement, space & level")],
    "Synth 1": [(0, 4, "Filter"), (4, 8, "Oscillators"), (8, 12, "Amp envelope"), (12, 16, "Play & output")],
    "Synth 2": [(0, 4, "Wavetable"), (4, 8, "Filter & table"), (8, 12, "Amp envelope"), (12, 16, "Play & output")],
    "Drums 1-8": [(0, 8, "Tune · pads 1-8"), (8, 16, "Length · pads 1-8")],
    "Drums 9-16": [(0, 8, "Tune · pads 9-16"), (8, 16, "Length · pads 9-16")],
    "Macros": [(0, 8, "Synth moves"), (8, 16, "Space & performance")],
    "Synth 1 Osc+": [(0, 4, "Oscillator 2"), (4, 5, "Noise"), (5, 7, "Filter"), (7, 8, "Feel"),
                     (8, 13, "Chord · key · scale · lane"), (13, 15, "Pitch env"), (15, 16, "Glide")],
    "Synth 1 Uni+FX": [(0, 4, "Unison & supersaw"), (4, 6, "Drive"), (6, 8, "Distortion"), (8, 10, "Synth FX"),
                       (10, 13, "Filter"), (13, 16, "Sub & level")],
    "Synth 2 Uni+FX": [(0, 4, "Unison & sub"), (4, 8, "Warp & wavetable"), (8, 11, "Drive & distortion"),
                       (11, 13, "Synth FX"), (13, 16, "Filter & level")],
    "Synth 1 Mod": [(0, 3, "LFO 1"), (3, 6, "LFO 2"), (6, 8, "Mod env"), (8, 16, "Mod slots · tap a name to change it")],
    "Synth 2 Osc+": [(0, 2, "Chord"), (2, 4, "Sub & noise"), (4, 6, "Pan & drift"), (6, 8, "Pitch env"),
                     (8, 10, "Filter"), (10, 12, "Feel"), (12, 15, "Chord key · scale · lane"), (15, 16, "Level")],
    "Synth 2 Mod": [(0, 3, "LFO 1"), (3, 6, "LFO 2"), (6, 8, "Mod env"), (8, 16, "Mod slots · tap a name to change it")],
    "Mix": [(0, 4, "Levels"), (4, 8, "Bus & DJ filter"), (8, 13, "Side-chain duck"), (13, 16, "Glue & width")],
    "Projects": [(0, 4, "Synth 1 (bass)"), (4, 8, "Synth 2 (lead)"), (8, 12, "Drums"), (12, 16, "Effects & level")],
    "Beats": [(0, 4, "Beat feel"), (4, 8, "Drum bus"), (8, 15, "Pad levels"), (15, 16, "Kick")],
    "Live": [(0, 1, "Scenes"), (1, 8, "Mix and macros"), (8, 12, "Synths"), (12, 14, "Duck"), (14, 16, "Effects")],
    "Mix EQ": [(0, 3, "Synth 1 EQ"), (3, 6, "Synth 2 EQ"), (6, 8, "EQ frequencies"), (8, 11, "Drums EQ"),
               (11, 14, "Master EQ"), (14, 16, "Synth pan")],
    "Synth 1 Arp": [(0, 4, "Arpeggiator"), (4, 8, "Feel"), (8, 9, "Duck"), (9, 12, "EQ"), (12, 16, "Pan, sends & level")],
    "Synth 2 Arp": [(0, 4, "Arpeggiator"), (4, 8, "Feel"), (8, 9, "Duck"), (9, 12, "EQ"), (12, 16, "Pan, sends & level")],
    "Drums 1-8 Mix": [(0, 8, "Level · pads 1-8"), (8, 16, "Pan · pads 1-8")],
    "Drums 9-16 Mix": [(0, 8, "Level · pads 9-16"), (8, 16, "Pan · pads 9-16")],
    "Drums 1-8 Groove": [(0, 8, "Chance · pads 1-8"), (8, 16, "Plays when · pads 1-8")],
    "Drums 9-16 Groove": [(0, 8, "Chance · pads 9-16"), (8, 16, "Plays when · pads 9-16")],
    "FX": [(0, 3, "Delay sends"), (3, 6, "Delay"), (6, 8, "DJ filter & lo-fi"), (8, 11, "Reverb sends"),
           (11, 14, "Reverb"), (14, 15, "Bus"), (15, 16, "Limiter")],
    "Master FX": [(0, 3, "Modulation"), (3, 4, "Drive"), (4, 6, "Dynamics"), (6, 8, "Drive & DJ filter"),
                  (8, 9, "Lo-fi"), (9, 11, "Glue"), (11, 13, "Width & level"), (13, 16, "Reverb")],
    "Synth 1 Mod 2": [(0, 4, "Mod slots 9-12 · tap a name to change it"), (4, 8, "LFO 1 & mod env attack"),
                      (8, 12, "LFO 2 & mod env decay"), (12, 16, "Feel & pan")],
    "Synth 2 Mod 2": [(0, 4, "Mod slots 9-12 · tap a name to change it"), (4, 8, "LFO 1 & mod env attack"),
                      (8, 12, "LFO 2 & mod env decay"), (12, 16, "Feel & pan")],
    "Synth 1 Env": [(0, 4, "Amp envelope"), (4, 6, "Decay 2 (0 = off)"), (6, 8, "Filter envelope"), (8, 10, "Mod env"),
                    (10, 12, "Pitch env"), (12, 16, "Glide, velocity & level")],
    "Synth 2 Env": [(0, 4, "Amp envelope"), (4, 6, "Decay 2 (0 = off)"), (6, 8, "Envelope amounts"), (8, 10, "Mod env"),
                    (10, 12, "Pitch env"), (12, 16, "Glide, velocity & level")],
    "Synth 1 LFO1 Steps": [(0, 8, "LFO 1 steps 1-8 · set LFO 1 shape to Step"), (8, 16, "Steps 9-16")],
    "Synth 1 LFO2 Steps": [(0, 8, "LFO 2 steps 1-8 · set LFO 2 shape to Step"), (8, 16, "Steps 9-16")],
    "Synth 2 LFO1 Steps": [(0, 8, "LFO 1 steps 1-8 · set LFO 1 shape to Step"), (8, 16, "Steps 9-16")],
    "Synth 2 LFO2 Steps": [(0, 8, "LFO 2 steps 1-8 · set LFO 2 shape to Step"), (8, 16, "Steps 9-16")],
    "Drums Choke": [(0, 8, "Choke group · pads 1-8 (a pad cuts off the others in its group)"), (8, 16, "Pads 9-16")],
    "Track Mute/Solo": [(0, 3, "Mute"), (3, 6, "Solo"), (6, 8, "Looper & master"), (8, 11, "Levels"),
                        (11, 13, "Pan"), (13, 16, "Master bus")],
}
LIBRARY_GUESSES = [os.path.join(os.path.expanduser("~"), sub, "Drum Machine Collection")
                   for sub in ("Downloads", "Documents", "Music", "Desktop")]


def mpc_host_guess():
    try:
        from potentialbox.mpcsync import mpc_tools_settings
        return mpc_tools_settings().get("host", "")
    except Exception:
        return ""


def log(*a):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------- looks
# v2.0 has one look, Hi-Fi: a BeatStep-coloured hi-fi deck (charcoal plate, walnut cabinet, cream keys, amber LEDs,
# green display). It's kept as a palette (the same colour roles every drawing call reads from T) plus shape numbers:
# round = how round the keys are, edge = an outline on every key, frame = how heavy panel outlines are.
LOOKS = {
    "hifi": dict(  # a hi-fi deck in BeatStep colours: dark panel, walnut cabinet, cream keys, amber LEDs, green display.
        # Optional keys read with T.get() so a look only needs them if it wants them:
        #   wood     - width of the walnut cabinet border drawn round the window (0 = none)
        #   screen   - display glass behind readouts (falls back to well)
        #   lcd_ink  - text on the display glass (falls back to accent)
        #   logo     - the app name in the header (falls back to accent)
        #   title    - frame headings (falls back to accent)
        name="Hi-Fi", round=0.42, edge=1.0, frame=1.0, narrow=False, wood=15, plate=True, pointer=True, dome=True,
        bevel=True, glass=True, serif=True, screw=True,
        bg="17181b", panel="202127", line="5d5a50", ink="ece6d6", ink_dim="8f8a7d", ink_faint="746f63",
        accent="e0803c", accent_hi="ffab63", knob_face="24252a", knob_ring="4b4942", knob_dot="f4efe0",
        knob_pointer="f2ecdc", knob_hub="efe8d6", knob_hi="6a6b75", knob_shadow="0f1013",
        seg_active="f2c879", seg_inactive="2a2b2f", seg_active_tx="241d12", btn_text="241d12", btn_bg="d8d2c2",
        btn_on="f2c879", tab_on="f2c879", tab_on_tx="1a1610", lcd="0b140e", well="24252a", chrome_ink="ece6d6",
        screen="0b140e", lcd_ink="8cffb0", logo="f4efe0", title="f4efe0", key_dim="8b8272"),
}
LOOK_ORDER = ["hifi"]
T = {}        # the current look's colours, "#rrggbb"
STYLE = {}    # the current look's name and shape numbers


def shade(c, k):
    """Lighten (k > 1) or darken (k < 1) a #rrggbb colour, clamped."""
    c = c.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (min(255, int(r * k)), min(255, int(g * k)), min(255, int(b * k)))


def mix2(a, b, t):
    """Blend two #rrggbb colours, 0 = a, 1 = b."""
    a, b = a.lstrip("#"), b.lstrip("#")
    ra, ga, ba = (int(a[i:i + 2], 16) for i in (0, 2, 4))
    rb, gb, bb = (int(b[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


def apply_look(look):
    """Make `look` the current one (in place: every drawing call reads T and STYLE)."""
    d = LOOKS[look if look in LOOKS else "hifi"]
    T.clear()
    STYLE.clear()
    for k, v in d.items():
        if isinstance(v, str) and k != "name":
            T[k] = "#" + v
        else:
            STYLE[k] = v
    T.setdefault("key_dim", T["ink_dim"])     # muted print on a key (dark looks use ink_dim for that too)
    T.setdefault("key_text", T["btn_text"])


apply_look("hifi")


# ----------------------------------------------------------------------------- state
class State:
    def __init__(self):
        self.params = ParamStore()
        self.cc_map = list(FACTORY_CCS)
        self.knob_mode = "absolute"
        self.ch = {"s1": 1, "s2": 2, "dr": 10}
        self.device = None  # {"label":..., "hostapi":..., "name":..., "exclusive":bool}
        self.blocksize = 256
        self.kit = {"factory": 0}  # or {"folder": path}
        self.recent = []  # recent kits: {"folder": path} or {"library": [machine, kit]}
        self.library_root = next((p for p in LIBRARY_GUESSES if os.path.isdir(p)), None)
        self.sounds = {"s1": [None] * SLOTS, "s2": [None] * SLOTS}
        self.mykits = [None] * SLOTS
        self.actions = default_actions()
        self.preset = {"s1": 0, "s2": 0}
        self.preset_name = {"s1": PRESETS["s1"][0][0], "s2": PRESETS["s2"][0][0]}
        self.page = "Projects"
        self.subpage = {t: 0 for t in SUBPAGES}
        self.last_tab = "Projects"
        self.sec_page = {}            # v2.0: each section's last sub-tab, so going back lands where you were
        self.synth_edit = {"s1": False, "s2": False}   # v2.0: synth tab shows the sound browser (False) or EDIT
        self.bounce_bars = 4          # v2.0 CAPTURE > STEMS
        self.bounce_mpc = False       # send every bounce to the MPC as soon as it's saved
        self.bounces = []             # recent bounce folders, newest first
        self.keep = {"dr": False, "s1": False, "s2": False}   # v2.4 KEEP: projects / mutate / random / song start leave it
        self.song = None              # v2.4 SONG START: parts.Song.to_json()
        self.song_mute = []           # "s1" / "s2" switched off in the song
        self.setups = [None] * SLOTS
        self.rec_stems = True
        self.loop_input = None    # list of interface input channels (0-based) or None
        self.loop_cfg = {}
        self.beat = None          # Beat.to_json()
        self.beat_kit = True      # picking a genre also loads its kit: True (built-in), "samples" (Kit Maker) or False
        self.project = None       # Projects tab: which BeatStep genre set (0-15) is loaded
        self.project_take = 0     # which of its sound choices (NEW SOUNDS steps through them)
        self.project_kit = True   # True: built-in genre kit, "samples": Kit Maker kit from your one-shots
        self.project_fx = True    # a project also sets the effects, ducking and tempo
        self.mut_amount = "MEDIUM"  # Projects tab MUTATE: MILD / MEDIUM / WILD
        self.mut_auto = 0         # auto mutate every 0 (off) / 8 / 16 bars while the BeatStep plays
        self.sample_folders = []  # Kit Maker / pad editor: folders of one-shots besides the Drum Machine Collection
        self.km = {"style": "CLASSIC", "scope": "all", "one": False}
        self.mpc_host = ""        # only if MPC TOOLS' settings don't say
        self.mpc_dest = MPC_ONESHOTS_DIR
        self.arrangement = []      # list of beat dicts (pattern chain)
        self.locked_pads = set()  # pads kept when randomising a kit
        self.beat_mutes = []
        self.beat_bars = 2
        self.clock_master = False   # PotentialBox sends clock + Start/Stop to the BeatStep
        self.look = "hifi"          # v2.0: the Hi-Fi look is the only look
        self.midi_off = []  # port names the user switched off
        self.bad_audio = []  # labels of outputs that froze or crashed on open
        self.audio_pending = None  # label being opened right now (set before open, cleared after)
        self.dirty = False

    def load_sounds(self):
        try:
            with open(SOUNDS_FILE, encoding="utf-8") as f:
                d = json.load(f)
            for pre in ("s1", "s2"):
                lst = list(d.get(pre, []))[:SLOTS]
                self.sounds[pre] = lst + [None] * (SLOTS - len(lst))
        except Exception:
            pass

    def load_setups(self):
        try:
            with open(SETUPS_FILE, encoding="utf-8") as f:
                lst = list(json.load(f))[:SLOTS]
            self.setups = lst + [None] * (SLOTS - len(lst))
        except Exception:
            pass

    def save_setups(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            tmp = SETUPS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.setups, f, indent=1)
            os.replace(tmp, SETUPS_FILE)
            return True
        except Exception as e:
            log("setups save failed", e)
            return False

    def locks_json(self):
        return {k: {str(st): n for st, n in d.items()} for k, d in self.params.locks.items()}

    def load_locks(self, d):
        p = self.params
        p.locks = {}
        for k, steps in (d or {}).items():
            if k in SPECS and isinstance(steps, dict):
                p.locks[k] = {int(st) % 16: float(n) for st, n in steps.items()}

    def load_scenes(self, d):
        p = self.params
        p.scenes = {str(i): None for i in range(1, 9)}
        d = dict(d or {})
        for old, slot in (("A", "1"), ("B", "2")):  # scenes saved by 1.9.0 and earlier
            if isinstance(d.get(old), dict) and not isinstance(d.get(slot), dict):
                d[slot] = d[old]
        for w in (str(i) for i in range(1, 9)):
            sc = d.get(w)
            if isinstance(sc, dict):
                p.scenes[w] = {k: float(n) for k, n in sc.items() if k in SPECS and not k.startswith("sc.")}
        p._scene_keys()

    def load_kits(self):
        try:
            with open(KITS_FILE, encoding="utf-8") as f:
                lst = list(json.load(f))[:SLOTS]
            self.mykits = lst + [None] * (SLOTS - len(lst))
        except Exception:
            pass

    def save_kits(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            tmp = KITS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.mykits, f, indent=1)
            os.replace(tmp, KITS_FILE)
            return True
        except Exception as e:
            log("kits save failed", e)
            return False

    def save_sounds(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            tmp = SOUNDS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.sounds, f, indent=1)
            os.replace(tmp, SOUNDS_FILE)
            return True
        except Exception as e:
            log("sounds save failed", e)
            return False

    def load(self):
        self.load_sounds()
        self.load_kits()
        self.load_setups()
        try:
            with open(CFG_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            self.params.apply_preset("s1", PRESETS["s1"][0][1])
            self.params.apply_preset("s2", PRESETS["s2"][0][1])
            return
        for k, n in d.get("params", {}).items():
            if k in SPECS:
                self.params.set_norm(k, n)
        cc = d.get("cc_map")
        if isinstance(cc, list) and len(cc) == 16:
            self.cc_map = [int(x) for x in cc]
        self.knob_mode = d.get("knob_mode", self.knob_mode)
        self.ch.update({k: int(v) for k, v in d.get("ch", {}).items() if k in self.ch})
        self.device = d.get("device")
        self.blocksize = int(d.get("blocksize", self.blocksize))
        kit = d.get("kit")
        acts = d.get("actions")
        if isinstance(acts, dict):
            if "tab:Mix & FX" in acts:
                acts["tab:Mix"] = acts.pop("tab:Mix & FX")
            for aid, trig in acts.items():
                if aid in ACTION_NAMES and (trig is None or isinstance(trig, dict)):
                    self.actions[aid] = trig
        if isinstance(kit, dict) and ("factory" in kit or "folder" in kit or "library" in kit or "pads" in kit):
            self.kit = kit
        elif d.get("kit_folder"):  # v1.0 settings
            self.kit = {"folder": d["kit_folder"]}
        self.recent = [k for k in d.get("recent", []) if isinstance(k, dict) and ("folder" in k or "library" in k)][:8]
        for p in d.get("recent_folders", []):  # v1.1 settings
            if isinstance(p, str) and {"folder": p} not in self.recent:
                self.recent.append({"folder": p})
        if ("folder" in self.kit or "library" in self.kit) and self.kit not in self.recent:
            self.recent.insert(0, self.kit)
        if d.get("library_root") and os.path.isdir(d["library_root"]):
            self.library_root = d["library_root"]
        self.preset.update(d.get("preset", {}))
        self.preset_name.update(d.get("preset_name", {}))
        sp = d.get("subpage", {})
        if isinstance(sp, dict):
            for t in self.subpage:
                try:
                    self.subpage[t] = int(sp.get(t, 0)) % len(SUBPAGES[t])
                except (TypeError, ValueError):
                    pass
        page = d.get("page")
        if page in OLD_PAGES:  # 1.x pages that are now sub-pages of a v2.0 tab
            page, sub = OLD_PAGES[page]
            if page in SUBPAGES:
                self.subpage[page] = sub
        self.page = page if page in TABS else "Projects"
        sec = d.get("sec_page")
        if isinstance(sec, dict):
            self.sec_page = {k: v for k, v in sec.items() if k in dict(SECTIONS) and v in TABS and SECTION_OF[v] == k}
        se = d.get("synth_edit")
        if isinstance(se, dict):
            self.synth_edit.update({k: bool(v) for k, v in se.items() if k in self.synth_edit})
        self.bounce_bars = d.get("bounce_bars") if d.get("bounce_bars") in (1, 2, 4, 8) else 4
        self.bounce_mpc = bool(d.get("bounce_mpc", False))
        self.bounces = [b for b in d.get("bounces", []) if isinstance(b, str)][:12]
        kp = d.get("keep")
        if isinstance(kp, dict):
            self.keep.update({k: bool(v) for k, v in kp.items() if k in self.keep})
        self.song = d.get("song") if isinstance(d.get("song"), dict) else None
        self.song_mute = [m for m in d.get("song_mute", []) if m in ("s1", "s2")]
        self.load_locks(d.get("locks"))
        self.load_scenes(d.get("scenes"))
        self.rec_stems = bool(d.get("rec_stems", True))
        li = d.get("loop_input")
        self.loop_input = [int(c) for c in li][:2] if isinstance(li, list) and li else None
        self.loop_cfg = d.get("loop_cfg", {}) if isinstance(d.get("loop_cfg"), dict) else {}
        self.beat = d.get("beat") if isinstance(d.get("beat"), dict) else None
        self.arrangement = [x for x in d.get("arrangement", []) if isinstance(x, dict)] if isinstance(d.get("arrangement"), list) else []
        self.locked_pads = set(x for x in d.get("locked_pads", []) if isinstance(x, int) and 0 <= x < 16)
        bk = d.get("beat_kit", True)
        self.beat_kit = "samples" if bk == "samples" else bool(bk)
        self.sample_folders = [f for f in d.get("sample_folders", []) if isinstance(f, str)][:12]
        km = d.get("km") if isinstance(d.get("km"), dict) else {}
        if km.get("style") in kitmaker.STYLE_NAMES:
            self.km["style"] = km["style"]
        if km.get("scope") in kitmaker.SCOPES:
            self.km["scope"] = km["scope"]
        self.km["one"] = bool(km.get("one", False))
        self.mpc_host = d.get("mpc_host", "") if isinstance(d.get("mpc_host"), str) else ""
        if isinstance(d.get("mpc_dest"), str) and d["mpc_dest"]:
            self.mpc_dest = d["mpc_dest"]
        self.beat_mutes = [g for g in d.get("beat_mutes", []) if g in GROUP_NAMES]
        self.beat_bars = int(d.get("beat_bars", 2)) if int(d.get("beat_bars", 2)) in BAR_CHOICES else 2
        self.clock_master = bool(d.get("clock_master", False))
        pr = d.get("project")
        self.project = pr if isinstance(pr, int) and 0 <= pr < len(projmod.PROJECTS) else None
        self.project_take = int(d.get("project_take", 0)) if isinstance(d.get("project_take", 0), int) else 0
        pk = d.get("project_kit", True)
        self.project_kit = "samples" if pk == "samples" else True
        self.project_fx = bool(d.get("project_fx", True))
        self.mut_amount = d.get("mut_amount") if d.get("mut_amount") in projmod.AMOUNTS else "MEDIUM"
        self.mut_auto = d.get("mut_auto") if d.get("mut_auto") in (0, 8, 16) else 0
        self.look = "hifi"   # v2.0: one look
        self.last_tab = d.get("last_tab") if d.get("last_tab") in TABS else "Projects"
        self.midi_off = d.get("midi_off", [])
        self.bad_audio = [x for x in d.get("bad_audio", []) if isinstance(x, str)]
        self.audio_pending = d.get("audio_pending")

    def save(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            d = dict(params=self.params.norm, cc_map=self.cc_map, knob_mode=self.knob_mode, ch=self.ch,
                     device=self.device, blocksize=self.blocksize, kit=self.kit, recent=self.recent, library_root=self.library_root,
                     preset=self.preset, preset_name=self.preset_name, page=self.page, subpage=self.subpage, midi_off=self.midi_off,
                     bad_audio=self.bad_audio, audio_pending=self.audio_pending, actions=self.actions,
                     locks=self.locks_json(), scenes=self.params.scenes, rec_stems=self.rec_stems, last_tab=self.last_tab,
                     loop_input=self.loop_input, loop_cfg=self.loop_cfg, beat=self.beat, beat_kit=self.beat_kit,
                     beat_mutes=self.beat_mutes, beat_bars=self.beat_bars,
                     arrangement=self.arrangement, locked_pads=sorted(self.locked_pads),
                     clock_master=self.clock_master, look=self.look, sample_folders=self.sample_folders,
                     km=self.km, mpc_host=self.mpc_host, mpc_dest=self.mpc_dest, project=self.project,
                     project_take=self.project_take, project_kit=self.project_kit, project_fx=self.project_fx,
                     mut_amount=self.mut_amount, mut_auto=self.mut_auto, sec_page=self.sec_page,
                     synth_edit=self.synth_edit, bounce_bars=self.bounce_bars, bounce_mpc=self.bounce_mpc,
                     bounces=self.bounces, keep=self.keep, song=self.song, song_mute=self.song_mute)
            tmp = CFG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=1)
            os.replace(tmp, CFG_FILE)
            self.dirty = False
        except Exception as e:
            log("save failed", e)


# ----------------------------------------------------------------------------- audio
class Audio:
    ORDER = {"ASIO": 0, "Windows WASAPI": 1, "Windows WDM-KS": 3, "Windows DirectSound": 4, "MME": 5}

    def __init__(self, state):
        self.state = state
        self.stream = None
        self.engine = Engine(48000, state.params)
        self.error = ""
        self.label = "No audio"
        self.latency_ms = 0.0
        self.in_chans = None
        self.in_error = ""
        self.max_in = 0
        self.underruns = 0   # buffers the sound card had to play without fresh audio (= a crackle)

    def devices(self):
        out = []
        if sd is None:
            return out
        try:
            apis = sd.query_hostapis()
            for i, d in enumerate(sd.query_devices()):
                if d["max_output_channels"] < 2:
                    continue
                api = apis[d["hostapi"]]["name"]
                short = {"Windows WASAPI": "WASAPI", "Windows DirectSound": "DirectSound",
                         "Windows WDM-KS": "WDM-KS"}.get(api, api)
                out.append(dict(index=i, name=d["name"], hostapi=api, exclusive=False,
                                label=f"{short}  ·  {d['name']}"))
                if api == "Windows WASAPI":
                    out.append(dict(index=i, name=d["name"], hostapi=api, exclusive=True,
                                    label=f"WASAPI EXCLUSIVE (low lag)  ·  {d['name']}"))
        except Exception as e:
            log("query devices", e)
        out.sort(key=lambda x: (self.ORDER.get(x["hostapi"], 2) if not x["exclusive"] else 0.5))
        return out

    def find(self, want):
        devs = self.devices()
        if want:
            for d in devs:
                if d["name"] == want.get("name") and d["hostapi"] == want.get("hostapi") \
                        and d["exclusive"] == want.get("exclusive", False):
                    return d
        bad = set(self.state.bad_audio)
        asio = [d for d in devs if d["hostapi"] == "ASIO" and d["label"] not in bad]
        if asio:  # first run: prefer a real interface's ASIO driver over generic / virtual ones
            return sorted(asio, key=lambda d: asio_rank(d["name"]))[0]
        try:
            default_out = sd.default.device[1]
            for d in devs:
                if d["index"] == default_out:
                    return d
        except Exception:
            pass
        return devs[0] if devs else None

    def busy(self):
        return getattr(self, "_worker", None) is not None and self._worker.is_alive()

    def render_failed(self, outdata):
        """A render error must never stall the audio thread: silence this block, log at most every 5 s."""
        outdata.fill(0)
        now = time.monotonic()
        if now - getattr(self, "_err_t", 0.0) > 5.0:
            self._err_t = now
            log("render error", traceback.format_exc())

    def callback(self, outdata, frames, t, status):
        if status.output_underflow:
            self.underruns += 1
        try:
            outdata[:] = self.engine.render(frames)
        except Exception:
            self.render_failed(outdata)

    def duplex_callback(self, indata, outdata, frames, t, status):
        if status.output_underflow or status.input_overflow:
            self.underruns += 1
        try:
            ch = self.in_chans
            x = indata[:, ch]
            if x.shape[1] == 1:
                x = np.repeat(x, 2, axis=1)
            outdata[:] = self.engine.render(frames, x)
        except Exception:
            self.render_failed(outdata)

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def start(self, dev=None):
        self.stop()
        self.error = ""
        self.underruns = 0
        if sd is None:
            self.error = "Audio library missing - run the installer again"
            self.label = "NO AUDIO"
            return False
        dev = dev or self.find(self.state.device)
        if dev is None:
            self.error = "No audio outputs found"
            self.label = "NO AUDIO"
            return False
        info = sd.query_devices(dev["index"])
        rates = []
        for r in (info["default_samplerate"], 48000, 44100):
            if r and int(r) not in rates:
                rates.append(int(r))
        extra = None
        if dev["exclusive"]:
            try:
                extra = sd.WasapiSettings(exclusive=True)
            except Exception:
                extra = None
        last = None
        self.state.audio_pending = dev["label"]
        self.state.save()
        self.max_in = int(info.get("max_input_channels", 0) or 0)
        want = self.state.loop_input
        self.in_error = ""
        if want and max(want) >= self.max_in:
            self.in_error = "This output has no inputs. Use your interface's ASIO driver to loop mics and instruments."
            want = None
        for sr in rates:
            try:
                if sr != self.engine.sr:
                    self.rebuild_engine(sr)
                self.stream = None
                if want:
                    try:
                        self.stream = sd.Stream(device=(dev["index"], dev["index"]), samplerate=sr,
                                                channels=(max(want) + 1, 2), dtype="float32",
                                                blocksize=self.state.blocksize, latency="low",
                                                extra_settings=(extra, extra) if extra else None,
                                                callback=self.duplex_callback)
                        self.in_chans = list(want)
                        self.stream.start()
                    except Exception as e:
                        log("input open failed", e)
                        self.in_error = f"Couldn't open the input: {e}"[:110]
                        self.stream = None
                if self.stream is None:
                    self.in_chans = None
                    self.stream = sd.OutputStream(device=dev["index"], samplerate=sr, channels=2, dtype="float32",
                                                  blocksize=self.state.blocksize, latency="low",
                                                  extra_settings=extra, callback=self.callback)
                    self.stream.start()
                lat = self.stream.latency
                if isinstance(lat, (tuple, list)):
                    self.engine.looper.rt = (float(lat[0]) + float(lat[1])) * sr
                    lat = lat[1]
                self.latency_ms = float(lat) * 1000.0
                self.state.device = {k: dev[k] for k in ("name", "hostapi", "exclusive", "label")}
                api = "ASIO" if dev["hostapi"] == "ASIO" else ("WASAPI EXCL" if dev["exclusive"] else
                                                               dev["hostapi"].replace("Windows ", ""))
                self.label = f"{api} · {dev['name'][:26]}"
                log("audio started", dev["label"], sr, self.state.blocksize, f"{self.latency_ms:.1f}ms")
                self.state.audio_pending = None
                self.state.save()
                return True
            except Exception as e:
                last = e
                self.stream = None
        self.state.audio_pending = None
        self.state.save()
        self.error = f"Could not open {dev['label'][:40]}: {last}"[:120]
        self.label = "AUDIO ERROR"
        log(self.error)
        return False

    def rebuild_engine(self, sr):
        old = self.engine
        eng = Engine(sr, self.state.params)
        eng.bpm = old.bpm
        self.apply_kit(eng)
        self.engine = eng
        if hasattr(self, "on_engine"):
            self.on_engine(eng)

    def apply_kit(self, eng=None):
        """Load the kit named in state into the engine. Returns number of pads loaded (16 for factory)."""
        eng = eng or self.engine
        kit = self.state.kit
        if "pads" in kit:
            eng.drums.load_sources(kit["pads"], kit.get("name", "Custom kit"))
            return 16
        if "library" in kit:
            n = self.load_library_kit(eng, *kit["library"])
            if n:
                return n
            self.state.kit = {"factory": 0}
            kit = self.state.kit
        if "folder" in kit:
            n = eng.drums.load_folder(kit["folder"]) if os.path.isdir(kit["folder"]) else 0
            if n:
                return n
            self.state.kit = {"factory": 0}
            kit = self.state.kit
        eng.drums.load_factory(int(kit.get("factory", 0)))
        return 16

    def library(self):
        root = self.state.library_root
        if getattr(self, "_lib", None) is None or self._lib.root != root:
            self._lib = Library(root)
        return self._lib

    def load_library_kit(self, eng, machine, kit_name):
        lib = self.library()
        if not lib.ok():
            return 0
        kit = next((k for k in lib.kits(machine) if k["name"] == kit_name), None) if machine in lib.machines else None
        if not kit:
            return 0
        return eng.drums.load_mapped(map_kit(kit["files"], machine), library_kit_label(machine, kit_name))


GENERIC_ASIO = ("asio4all", "voicemeeter", "fl studio", "flexasio", "steinberg built-in", "generic", "virtual",
                "realtek", "asio2wasapi", "reaper")


def asio_rank(name):
    n = name.lower()
    return 1 if any(g in n for g in GENERIC_ASIO) else 0


def library_kit_label(machine, kit_name):
    model = machine[len(brand_of(machine)):].strip() or machine
    if kit_name == "Main kit":
        return machine
    if model.lower().split()[0] in kit_name.lower():
        return kit_name
    return f"{model} · {kit_name}"


# ----------------------------------------------------------------------------- MIDI
class ClockOut:
    """PotentialBox as the master clock: sends MIDI clock (24 per beat), Start and Stop to the BeatStep and
    drives PotentialBox's own transport with the same ticks. The BeatStep's Sync must be set to USB."""

    def __init__(self, app):
        self.app = app
        self.run = False
        self.th = None
        self.playing = False
        self.reset = False

    def eng(self):
        return self.app.audio.engine

    def _send(self, kind):
        out = self.app.midi.out
        if out is not None:
            try:
                out.send(mido.Message(kind))
            except Exception as e:
                log("clock out", e)

    def enable(self):
        if not self.app.midi.open_out():
            return False
        if self.th is None or not self.th.is_alive():
            self.run = True
            self.th = threading.Thread(target=self._loop, daemon=True, name="clock-out")
            self.th.start()
        return True

    def disable(self):
        if self.playing:
            self.stop_transport()
        self.run = False

    def start_transport(self):
        if not self.run and not self.enable():
            return False
        self._send("stop")
        self.reset = True
        self.eng().clock("start", time.perf_counter())
        self._send("start")
        self.playing = True
        return True

    def stop_transport(self):
        self._send("stop")
        eng = self.eng()
        eng.clock("stop")
        eng.panic()
        self.playing = False

    def _loop(self):
        nxt = time.perf_counter()
        while self.run:
            dt = 60.0 / max(self.eng().bpm, 30.0) / 24.0
            now = time.perf_counter()
            if self.reset:
                self.reset = False
                nxt = now
            wait = nxt - now
            if wait > 0.002:
                time.sleep(wait - 0.0015)
                continue
            while time.perf_counter() < nxt:
                pass
            self._send("clock")
            self.eng().clock("tick", time.perf_counter())
            nxt += dt
            if time.perf_counter() - nxt > 0.1:  # we were held up: don't rush to catch up
                nxt = time.perf_counter()
        self.playing = False


class Midi:
    def __init__(self, app):
        self.app = app
        self.ports = {}
        self.clock_times = collections.deque(maxlen=48)
        self.last_clock = 0.0
        self.learn = None  # index of knob being learned, or None
        self.action_learn = None  # action id waiting for a pad/step press
        self.learn_last_cc = None
        self.flash = [0.0] * 16
        self.activity = 0.0
        self.error = ""
        self.clock_port = None
        self.clock_seen = 0.0
        self.scene_hold = None
        self.out = None
        self.out_name = None
        self.offs = collections.deque()

    def open_out(self):
        """MIDI out to the BeatStep (for SEND TO BEATSTEP)."""
        if self.out is not None:
            return True
        if mido is None:
            return False
        try:
            names = mido.get_output_names()
        except Exception as e:
            log("midi out names", e)
            return False
        cand = [n for n in names if "beatstep" in n.lower()]
        cand.sort(key=lambda n: ("midiout2" in n.lower() or "2 (" in n.lower(), n))
        for n in cand:
            try:
                self.out = mido.open_output(n)
                self.out_name = n
                log("midi out", n)
                return True
            except Exception as e:
                log("midi out failed", n, e)
        return False

    def send_drum(self, pad, vel):  # audio thread
        if self.out is None:
            return
        ch = self.app.state.ch["dr"] - 1
        self.out.send(mido.Message("note_on", channel=ch, note=36 + pad, velocity=int(vel)))
        self.offs.append((time.time() + 0.06, mido.Message("note_off", channel=ch, note=36 + pad, velocity=0)))

    def flush_offs(self):
        now = time.time()
        while self.offs and self.offs[0][0] <= now:
            _, m = self.offs.popleft()
            try:
                self.out.send(m)
            except Exception:
                pass

    def names(self):
        if mido is None:
            return []
        try:
            return sorted(set(mido.get_input_names()))
        except Exception as e:
            self.error = str(e)
            return []

    def open_all(self):
        self.close_all()
        if mido is None:
            self.error = "MIDI library missing"
            return
        names = self.names()
        off = set(self.app.state.midi_off)
        bsp = [n for n in names if "beatstep" in n.lower()]
        targets = [n for n in (bsp or names) if n not in off]
        for n in targets:
            self.open(n)

    def open(self, name):
        try:
            self.ports[name] = mido.open_input(name, callback=lambda m, n=name: self.on_msg(m, n))
            log("midi open", name)
        except Exception as e:
            self.error = f"{name}: {e}"
            log("midi open failed", name, e)

    def close(self, name):
        p = self.ports.pop(name, None)
        if p:
            try:
                p.close()
            except Exception:
                pass

    def close_all(self):
        for n in list(self.ports):
            self.close(n)

    def status(self):
        if mido is None:
            return "NO MIDI LIBRARY"
        if not self.ports:
            return "NO BEATSTEP FOUND"
        n = next(iter(self.ports))
        label = "BEATSTEP PRO" if "beatstep" in n.lower() else n[:20].upper()
        return label + (f" +{len(self.ports)-1}" if len(self.ports) > 1 else "")

    def on_msg(self, msg, port=None):
        try:
            self._handle(msg, port)
        except Exception:
            log("midi error", traceback.format_exc())

    def _handle(self, msg, port=None):
        app = self.app
        eng = app.audio.engine
        t = msg.type
        if t in ("clock", "start", "stop", "continue"):
            if app.state.clock_master:
                return  # PotentialBox is the clock: ignore any clock coming back
            # the BeatStep shows up as two ports: only follow the clock from one of them
            now = time.time()
            if self.clock_port is None or now - self.clock_seen > 2.0:
                self.clock_port = port
            if port != self.clock_port:
                return
            self.clock_seen = now
            if t != "clock":
                eng.clock({"start": "start", "stop": "stop", "continue": "cont"}[t])
                if t == "stop":
                    eng.panic()
                return
            eng.clock("tick", time.perf_counter())
        if t == "clock":
            now = time.perf_counter()
            if self.last_clock and now - self.last_clock < 0.25:
                self.clock_times.append(now - self.last_clock)
                if len(self.clock_times) >= 24:
                    avg = sum(self.clock_times) / len(self.clock_times)
                    bpm = 60.0 / (avg * 24.0)
                    if 30 < bpm < 300:
                        eng.bpm = round(bpm * 10) / 10
            self.last_clock = now
            return
        self.activity = time.time()
        ch = getattr(msg, "channel", -1) + 1
        if t in ("note_on", "note_off", "control_change"):
            kind = "cc" if t == "control_change" else "note"
            num = msg.control if kind == "cc" else msg.note
            val = msg.value if kind == "cc" else (msg.velocity if t == "note_on" else 0)
            if self.action_learn is not None and val > 0 and self.learn is None:
                aid = self.action_learn
                for other, trig in app.state.actions.items():  # one trigger per action
                    if trig and other != aid and (trig["t"], trig["ch"], trig["n"]) == (kind, ch, num):
                        app.state.actions[other] = None
                app.state.actions[aid] = {"t": kind, "ch": ch, "n": num}
                self.action_learn = None
                app.rebuild_actions()
                app.state.dirty = True
                app.request_redraw()
                return
            aid = app.action_lookup.get((kind, ch, num))
            if aid:
                if app.state.page == "Live" and aid in PAD_ACTIONS and app.overlay is None:
                    app.live_pad(PAD_ACTIONS.index(aid), val > 0)  # straight from this thread: no GUI delay
                elif app.state.page == "Loop" and aid in PAD_ACTIONS and app.overlay is None:
                    app.loop_pad(PAD_ACTIONS.index(aid), val > 0)
                elif app.state.page == "Beats" and aid in PAD_ACTIONS and app.overlay is None:
                    app.beat_pad(PAD_ACTIONS.index(aid), val > 0)
                elif app.state.page == "Capture" and aid in PAD_ACTIONS and app.overlay is None:
                    if val > 0:
                        app.action_q.append(("capture", PAD_ACTIONS.index(aid)))
                elif app.state.page == "Projects" and aid in PAD_ACTIONS and app.overlay is None:
                    if val > 0:
                        app.action_q.append(("project", PAD_ACTIONS.index(aid)))
                elif aid in HOLD_ACTIONS:
                    eng.set_fill(val > 0)
                    app.action_flash[aid] = time.time()
                elif val > 0:
                    app.action_q.append(aid)
                return  # pad/step releases for actions are swallowed too
        if t in ("note_on", "note_off"):
            vel = msg.velocity if t == "note_on" else 0
            target = None
            if ch == app.state.ch["dr"]:
                target = "dr"
            elif ch == app.state.ch["s1"]:
                target = "s1"
            elif ch == app.state.ch["s2"]:
                target = "s2"
            if target == "dr":
                if eng.beats.send == "sending":
                    return  # the BeatStep echoing the beat we're sending it: don't play it twice
                pad = (msg.note - 36) % 16
                if 8 <= pad <= 14 and (app.state.params.val["s2.lane"] >= 0.5 or app.state.params.val["s1.lane"] >= 0.5):
                    if vel > 0:  # chord lane: drum tracks 9-15 say which chord (scale degree 1-7) the bar is on
                        eng.s1.lane_deg = eng.s2.lane_deg = pad - 7
                    return
                if vel > 0:
                    eng.note_on("dr", (msg.note - 36) % 16, vel)
            elif target:
                if vel > 0:
                    eng.note_on(target, msg.note, vel)
                else:
                    eng.note_off(target, msg.note)
            return
        if t == "control_change":
            cc, val = msg.control, msg.value
            if cc in (120, 123):
                eng.panic()
                return
            if self.learn is not None:
                if cc != self.learn_last_cc and cc not in self.app.state.cc_map[: self.learn]:
                    st = self.app.state
                    st.cc_map[self.learn] = cc
                    self.flash[self.learn] = time.time()
                    self.learn_last_cc = cc
                    self.learn += 1
                    st.dirty = True
                    if self.learn >= 16:
                        self.learn = None
                    app.request_redraw()
                return
            if cc not in app.state.cc_map:
                return
            idx = app.state.cc_map.index(cc)
            key = app.page_keys()[idx]
            p = app.state.params
            if app.state.knob_mode == "relative":
                d = val - 64
                if d:
                    if SPECS[key].step:
                        p.nudge(key, 1 if d > 0 else -1)
                    else:
                        p.set_norm(key, p.norm[key] + d / 100.0)
            else:
                p.set_norm(key, val / 127.0)
            self.flash[idx] = time.time()
            if key.startswith("mc."):
                app.last_macro = int(key[3:]) - 1
            app.state.dirty = True
            app.request_redraw()


# ----------------------------------------------------------------------------- GUI
class App:
    def __init__(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
                ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x80)
            except Exception:
                pass
        self.state = State()
        self.state.load()
        apply_look(self.state.look)
        self.audio = Audio(self.state)
        self.audio.apply_kit()
        self.midi = Midi(self)

        if sys.platform == "win32":  # its own taskbar button and icon, not Python's
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PotentialBreaks.PotentialBox")
            except Exception:
                pass
        self.root = tk.Tk()
        self.root.title(f"{APP} {VERSION}")
        here = os.path.dirname(os.path.abspath(__file__))
        try:  # the PotentialBox icon instead of Tk's feather (title bar, taskbar, dialogs)
            if sys.platform == "win32":
                # a small plain-bitmap .ico (16-64 px): Windows' title bar and taskbar take it as it is
                self.root.iconbitmap(default=os.path.join(here, "window.ico"))
            else:
                self._icon = tk.PhotoImage(file=os.path.join(here, "potentialbox.png"))
                self.root.iconphoto(True, self._icon)
        except Exception:
            log("icon", traceback.format_exc())
        self.root.configure(bg=T["bg"])
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        s = min(1.0, sw * 0.92 / W, sh * 0.86 / H)
        self.root.geometry(f"{int(W*s)}x{int(H*s)}")
        self.root.minsize(640, 400)  # everything scales; a big minimum pushed the tabs off small screens
        self.cv = tk.Canvas(self.root, bg=T["bg"], highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.scale, self.ox, self.oy = s, 0, 0
        self.fonts = {}
        self.pick_fonts()
        self._sprites = {}      # PhotoImages by key (hi-fi knobs, cabinet); kept alive here
        self.hits = []
        self.redraw_wanted = True
        self.drag = None
        self.dev_scroll = 0
        self.toast = ("", 0.0)
        self.cv.bind("<Configure>", self.on_resize)
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<MouseWheel>", self.on_wheel)
        self.root.bind("<Control-z>", lambda e: self.do_undo())
        self.root.bind("<Control-y>", lambda e: self.do_redo())
        for i, (sec, _) in enumerate(SECTIONS):  # Ctrl+1-5: the five sections
            self.root.bind(f"<Control-Key-{i+1}>", lambda e, sc=sec: self.set_section(sc))
        self.cv.bind("<Button-4>", lambda e: self.on_wheel(e, 120))
        self.cv.bind("<Button-5>", lambda e: self.on_wheel(e, -120))
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.bind("<Escape>", lambda e: self.close_overlay())
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.overlay = None  # None, ("sounds", "s1"/"s2") or ("kits",)
        self.armed = None  # (pre, slot, time) for "tap again to replace"
        self.lib_brand = None
        self.lib_machine = None
        self.lib_scroll = {"brands": 0, "machines": 0, "kits": 0}
        self.sel_pad = 0
        self.pe = {"group": None, "scope": "all", "scroll": 0}
        self.samples = SampleIndex(SAMPLE_INDEX_FILE)  # every one-shot: Drum Machine Collection + sample folders
        self.samples_again = False
        self.km_hist = collections.deque()
        self.km_rng = random.Random()
        self.sync = None
        self.sync_thread = None
        self.action_q = collections.deque()
        self.action_flash = {}
        self.rebuild_actions()
        self.test_notes = {}
        self.lock_mode = False
        self.lock_sel = None
        self.rs = {"src": "Synth 1", "len": "1 bar"}
        self.last_rec_folder = None
        self.live_held = set()
        self.loop_held = {}
        self.audio.on_engine = self.apply_engine_state
        self.apply_engine_state(self.audio.engine)
        self.clockout = ClockOut(self)
        self.voice = Voice(projmod.PHRASES)
        self.voice_heard = ("", 0.0)
        self.mut_pending = None   # a mutation waiting for the next bar
        self.mut_hist = collections.deque()
        self.mut_count = {"bass": 0, "lead": 0, "drums": 0}
        self.morph = None         # synth settings gliding to a mutation
        self.auto_block = None
        self.send_countdown = None
        self.bounce_job = None     # v2.0: the last stem bounce being saved
        self.bounce_jobs = []      # v2.2: every bounce / grab still saving
        self.grab_wait = None      # v2.2: GRAB waiting for the bar to finish
        self.taps = []             # v2.4: TAP TEMPO times
        self.tap_flash = 0.0
        self.tap_bpm = None
        self.beat_hist = []        # v2.2: beats before NEW BEAT / MUTATE / ..., for ◀ BACK
        self.send_queue = []       # v2.3: bounces waiting to go to the MPC
        self.song_hist = []        # v2.4: songs before SONG START / NEW BASS LINE / ..., for ◀ BACK
        self.sent_folders = set()  # v2.3: bounces that made it to the MPC this session (SEND shows ✓)
        self._listen_draw = 0.0
        self.mpc_sender = None     # v2.0: MpcSend while sending loops to the MPC
        if self.state.clock_master:
            self.root.after(1500, lambda: self.clockout.enable() or self.show_toast("CLOCK OUT: BEATSTEP NOT FOUND"))

        if self.state.audio_pending:  # last launch froze or crashed while opening this output
            bad = self.state.audio_pending
            if bad not in self.state.bad_audio:
                self.state.bad_audio.append(bad)
            if (self.state.device or {}).get("label") == bad:
                self.state.device = None
            self.state.audio_pending = None
            self.state.save()
            self.state.page = "Setup"
            self.audio.error = f"{bad[:50]} froze last time - pick an output below"
            log("skipping output that froze last launch:", bad)
        else:
            self.root.after(300, lambda: self.start_audio(fallback=True))
        self.midi.open_all()
        self.root.after(1200, self.rescan_samples)
        self.last_save = time.time()
        self.last_draw = 0.0
        self.root.after(40, self.tick)
        self.root.after(6000, self.warm_kits)

    def warm_kits(self):
        """v2.1: build the drum kits that aren't on disk yet, one at a time in the background, so picking any kit
        is instant (a built kit is kept in the kit-cache folder)."""
        sr = self.audio.engine.sr

        def work():
            for i in range(len(_kits.KITS)):
                if (i, int(sr)) not in _kits._CACHE:
                    try:
                        _kits.build(i, sr)
                    except Exception as e:  # noqa: BLE001
                        log("kit warm-up", i, e)
                    time.sleep(0.3)
        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- helpers
    def request_redraw(self):
        self.redraw_wanted = True

    def page_name(self):
        """The knob page shown: a tab, or the selected sub-page of a synth tab."""
        page = self.state.page if self.state.page in PAGES else "Perform"
        if page in ("Synth 1", "Synth 2") and not self.state.synth_edit["s" + page[-1]]:
            return page + " Quick"      # the sound browser's knobs
        if page in SUBPAGES:
            subs = SUBPAGES[page]
            return subs[self.state.subpage.get(page, 0) % len(subs)][1]
        return page

    def page_keys(self):
        return PAGES[self.page_name()]

    def X(self, x):
        return self.ox + x * self.scale

    def Y(self, y):
        return self.oy + y * self.scale

    def pick_fonts(self):
        """The look's typefaces, from what Windows has. Every look stays on Bahnschrift, which the pages are laid out
        for; Night Rack takes its narrower cut (a narrower face always fits)."""
        fams = set(tkfont.families(self.root))
        base = ("Bahnschrift", "Segoe UI", "DejaVu Sans", "Helvetica")
        bold = ("Bahnschrift SemiBold", "Segoe UI Semibold")
        if STYLE.get("narrow"):
            base = ("Bahnschrift SemiCondensed",) + base
            bold = ("Bahnschrift SemiBold SemiCondensed", "Bahnschrift SemiBold SemiConden") + bold
        self.fam = next((f for f in base if f in fams), "TkDefaultFont")
        self.fam_b = next((f for f in bold if f in fams), self.fam)
        self.fam_serif = next((f for f in ("Georgia", "Constantia", "Cambria", "Times New Roman", "DejaVu Serif")
                               if f in fams), None)
        self.fonts = {}
        self._fit = {}

    def font(self, px, bold=False):
        key = (int(px * self.scale * 10), bold)
        f = self.fonts.get(key)
        if f is None:
            f = tkfont.Font(family=self.fam_b if bold else self.fam, size=-max(6, int(px * self.scale)),
                            weight="bold" if bold and self.fam_b == self.fam else "normal")
            self.fonts[key] = f
        return f

    def rrect(self, x, y, w, h, r, fill, outline=""):
        X, Y, s = self.X, self.Y, self.scale
        if STYLE.get("bevel") and skins is not None and getattr(skins, "HAVE", False) and w > 3 and h > 3:
            rr = min(r * STYLE["round"], w / 2, h / 2)
            ol = outline or (T["line"] if STYLE["edge"] else None)
            pw, ph = max(4, int(round(w * s))), max(4, int(round(h * s)))
            img = self.photo(("key", pw, ph, round(rr * s, 1), fill, ol),
                             lambda: skins.key(pw, ph, rr * s, fill, ol))
            if img is not None:
                m = skins.KEY_MARGIN
                self.cv.create_image(X(x) - m, Y(y) - m, image=img, anchor="nw")
                return
        x0, y0, x1, y1 = X(x), Y(y), X(x + w), Y(y + h)
        r = min(r * s, (x1 - x0) / 2, (y1 - y0) / 2)
        r *= STYLE["round"]                      # the look: rounder or squarer keys
        edge = max(1, round(STYLE["edge"] * s)) if STYLE["edge"] else 1
        if not outline and STYLE["edge"]:        # the look: every key gets an outline
            outline = T["line"]
        if r < 0.5:
            self.cv.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=edge if outline else 0)
            return
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        self.cv.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=edge if outline else 1)

    def rect(self, x, y, w, h, fill="", outline=""):
        width = max(1, round(STYLE["frame"] * self.scale)) if outline else 1
        self.cv.create_rectangle(self.X(x), self.Y(y), self.X(x + w), self.Y(y + h), fill=fill, outline=outline, width=width)

    def text(self, x, y, s, px, color, bold=False, anchor="center"):
        self.cv.create_text(self.X(x), self.Y(y), text=s, font=self.font(px, bold), fill=color, anchor=anchor)

    def logo(self, x, y, s, px, color):
        """The app name: the look's serif face when it has one (Vintage), otherwise the normal bold face."""
        fam = getattr(self, "fam_serif", None) if STYLE.get("serif") else None
        if not fam:
            self.text(x, y, s, px, color, True, "w")
            return
        key = ("logo", s, px, round(self.scale, 3))
        f = self.fonts.get(key)
        if f is None:
            f = tkfont.Font(family=fam, size=-max(6, int(px * self.scale)), weight="bold")
            self.fonts[key] = f
        self.cv.create_text(self.X(x), self.Y(y), text=s, font=f, fill=color, anchor="w")

    def screw(self, cx, cy):
        """The little cross-head screw that holds the key plates down."""
        r = 2.6
        self.cv.create_oval(self.X(cx - r), self.Y(cy - r), self.X(cx + r), self.Y(cy + r),
                            fill="#6f695d", outline="#2e2b26", width=max(1, round(self.scale)))
        self.cv.create_line(self.X(cx - r * 0.55), self.Y(cy - r * 0.55), self.X(cx + r * 0.55), self.Y(cy + r * 0.55),
                            fill="#2e2b26", width=max(1, round(self.scale)))

    def text_fit(self, x, y, s, px, maxw, color, bold=False, anchor="center", minpx=8):
        """Text that shrinks (down to `minpx`) to fit `maxw` design pixels instead of running into its neighbours."""
        key = (s, px, maxw, bold, round(self.scale, 3), self.fam)
        fit = self._fit.get(key)
        if fit is None:
            fit = px
            while fit > minpx and self.font(fit, bold).measure(s) / self.scale > maxw:
                fit -= 1
            if len(self._fit) > 4000:
                self._fit.clear()
            self._fit[key] = fit
        self.text(x, y, s, fit, color, bold, anchor)

    def hit(self, x, y, w, h, fn, kind="tap"):
        self.hits.append((x, y, x + w, y + h, fn, kind))

    # ---------------------------------------------------------------- widgets (theme)
    def frame(self, x, y, w, h, title, sub="", led=None):
        if STYLE.get("plate"):                       # looks with raised panel plates (Vintage)
            n = 22
            top, bot = shade(T["panel"], 1.12), shade(T["panel"], 0.88)
            for i in range(n):
                self.rect(x + 1, y + 1 + (h - 2) * i / n, w - 2, (h - 2) / n + 1,
                          fill=mix2(top, bot, i / (n - 1)))
            self.rect(x, y, w, h, outline=T["line"])
        else:
            self.rect(x, y, w, h, outline=T["line"])
        self.text(x + 18, y + 30, title.upper(), 22, T.get("title", T["accent"]), True, "w")
        tw = self.font(22, True).measure(title.upper()) / self.scale
        if led is not None:
            self.led(x + 18 + tw + 16, y + 30, led)
            tw += 26
        self.cv.create_line(self.X(x + 18 + tw + 4), self.Y(y + 36), self.X(x + w - 18), self.Y(y + 36), fill=T["line"])
        if sub:
            self.text(x + w - 18, y + 22, sub, 12, T["ink_dim"], False, "e")

    def readout(self, cx, cy, w, h, s, label="", above=False):
        x0, y0 = cx - w / 2, cy - h / 2
        glass = T.get("screen", T["well"])
        img = None
        if STYLE.get("glass") and skins is not None and getattr(skins, "HAVE", False):
            pw, ph = max(8, int(round(w * self.scale))), max(8, int(round(h * self.scale)))
            img = self.photo(("scr", pw, ph, glass), lambda: skins.screen(pw, ph, glass))
        if img is not None:
            self.cv.create_image(self.X(x0), self.Y(y0), image=img, anchor="nw")
            self.rect(x0, y0, w, h, outline=T["line"])
        else:
            self.rect(x0, y0, w, h, fill=glass, outline=T["line"])
        self.text(cx, cy, s.upper(), 16, T.get("lcd_ink", T["accent"]), True)
        if label and above:
            self.text(cx - w / 2, cy - h / 2 - 10, label.upper(), 11, T["ink_dim"], True, "w")
        elif label:
            self.text(cx - w / 2 - 8, cy, " ".join(label.upper()), 8, T["ink_dim"], False, "e")

    def button(self, cx, cy, w, h, label, fn, accent=False, on=False, px=None):
        fill = T["btn_on"] if (accent or on) else T["btn_bg"]
        self.rrect(cx - w / 2, cy - h / 2, w, h, 12, fill)
        px = px or min(30, max(14, h * 0.36))
        self.text(cx, cy, label, px, T["btn_text"], True)
        self.hit(cx - w / 2, cy - h / 2, w, h, fn)

    def seg(self, x, y, w, h, options, current, fn, vertical=True):
        n = len(options)
        for i, opt in enumerate(options):
            if vertical:
                bx, by, bw, bh = x, y + i * h, w, h
            else:
                bx, by, bw, bh = x + i * w, y, w, h
            on = opt == current
            self.rect(bx + 1, by + 1, bw - 2, bh - 2, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text_fit(bx + bw / 2, by + bh / 2, str(opt).upper(), 13, bw - 8, T["seg_active_tx"] if on else T["ink_dim"], on)
            self.hit(bx, by, bw, bh, lambda o=opt: fn(o))

    def led(self, cx, cy, lit):
        r = 6
        self.cv.create_oval(self.X(cx - r), self.Y(cy - r), self.X(cx + r), self.Y(cy + r),
                            fill=T["accent"] if lit else T["well"], outline=T["line"])

    @staticmethod
    def is_toggle(key):
        sp = SPECS[key]
        return bool(sp.choices) and len(sp.choices) == 2 and sp.step == 1

    def toggle_param(self, key):
        p = self.state.params
        sp = SPECS[key]
        cur = int(round(sp.to_val(p.cur_norm(key))))
        p.set_val(key, 1 - cur) if p.lock_step is None else p.set_norm(key, sp.to_norm(1 - cur))
        self.state.dirty = True

    def arc(self, cx, cy, r, start, extent, color, width):
        if abs(extent) < 0.5:
            return
        X, Y = self.X, self.Y
        self.cv.create_arc(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r), start=start, extent=extent, style="arc",
                           outline=color, width=max(1, round(width * self.scale)))

    def knob(self, idx, cx, cy, r, key):
        spec = SPECS[key]
        p = self.state.params
        locked_here = p.lock_step is not None and p.lock_step in p.locks.get(key, {})
        n = p.cur_norm(key) if p.lock_step is not None else p.shown(key)
        moved = p.lock_step is None and abs(n - p.norm[key]) > 0.004
        hot = time.time() - self.midi.flash[idx] < 0.35
        X, Y, s = self.X, self.Y, self.scale
        if self.is_toggle(key):  # on/off settings are one-tap keys, not knobs (the BeatStep knob still works)
            on = int(round(spec.to_val(n))) == 1
            self.rrect(cx - 62, cy - 30, 124, 60, 12, T["btn_on"] if on else T["btn_bg"],
                       outline=T["accent"] if hot else "")
            self.text(cx, cy, spec.choices[1 if on else 0].upper(), 18 if len(spec.choices[1]) < 6 else 13,
                      T["btn_text"], True)
            self.text_fit(cx, cy + r + 24, self.knob_label(key), 13, 150, T["ink"], True)
            self.text(cx, cy + r + 46, "TAP TO SWITCH", 11, T["ink_faint"])
            self.text(cx - r - 30, cy - r - 2, str(idx + 1), 10, T["ink_faint"], False, "e")
            self.hit(cx - 62, cy - 30, 124, 60, lambda k=key: self.toggle_param(k))
            return
        # value ring: a track arc and the value arc (bipolar settings fill from the top)
        rr = r + 10
        self.arc(cx, cy, rr, 225, -270, T["ink_faint"], 3)
        bip = spec.lo < 0 < spec.hi or spec.unit in ("djm", "sw")
        core = T.get("accent_hi", T["accent"])
        if bip:
            zero = spec.to_norm(0.0) if spec.lo < 0 < spec.hi else 0.5
            a0, a1 = 225 - 270 * zero, 225 - 270 * n
            self.arc(cx, cy, rr, a0, a1 - a0, T["accent"], 5)
            self.arc(cx, cy, rr, a0, a1 - a0, core, 2)
        else:
            self.arc(cx, cy, rr, 225, -270 * n, T["accent"], 5)
            self.arc(cx, cy, rr, 225, -270 * n, core, 2)
        dome = T.get("knob_hi")
        hot_ring = T["accent"] if hot else T["knob_ring"]
        sprite = None
        if dome and STYLE.get("dome") and skins is not None and getattr(skins, "HAVE", False):
            px = max(8, int(round(2 * r * s)))
            sprite = self.photo(("knob", px, T["knob_face"], dome, T["knob_ring"], bool(hot)),
                                lambda: skins.knob(px, T["knob_face"], dome, hot_ring))
        if sprite is not None:   # hi-fi: a rendered dome with its own shadow and highlight
            self.cv.create_image(X(cx), Y(cy), image=sprite, anchor="center")
        elif dome:               # fallback: nested circles shifted to the light, on a soft cast shadow
            self.cv.create_oval(X(cx - r * 1.03), Y(cy - r * 0.97 + 4), X(cx + r * 1.03), Y(cy + r * 1.05 + 4),
                                fill=T.get("knob_shadow", "#101114"), outline="")
            for i in range(18):
                t = i / 17.0
                rr = r * (1.0 - 0.64 * t)
                off = -r * 0.12 * t
                self.cv.create_oval(X(cx - rr + off), Y(cy - rr + off), X(cx + rr + off), Y(cy + rr + off),
                                    fill=mix2(T["knob_face"], dome, t), outline="")
            self.cv.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r),
                                outline=hot_ring, width=max(1, int(2 * s)))
        else:
            self.cv.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r), fill=T["knob_face"],
                                outline=hot_ring, width=max(1, int(2 * s)))
        if moved:  # where your own setting is, while a macro pushes the knob
            ab = math.radians(225 - 270 * p.norm[key])
            bx, by = cx + (r - 12) * math.cos(ab), cy - (r - 12) * math.sin(ab)
            self.cv.create_oval(X(bx - 4), Y(by - 4), X(bx + 4), Y(by + 4), fill="", outline=T["ink_faint"], width=max(1, int(2 * s)))
        a = math.radians(225 - 270 * n)
        if STYLE.get("pointer"):   # domed encoder: cream pointer from a cream hub (Vintage / BeatStep)
            pc = T.get("knob_pointer", T["knob_dot"])
            pimg = None
            if sprite is not None and skins is not None:
                angle = round((-135 + 270 * n) / 2.5) * 2.5
                px2 = max(8, int(round(2 * r * s)))
                pimg = self.photo(("ptr", px2, angle, pc), lambda: skins.pointer(px2, pc, angle))
            if pimg is not None:
                self.cv.create_image(X(cx), Y(cy), image=pimg, anchor="center")
            else:
                ca, sa = math.cos(a), math.sin(a)
                self.cv.create_line(X(cx + r * 0.30 * ca), Y(cy - r * 0.30 * sa),
                                    X(cx + r * 0.84 * ca), Y(cy - r * 0.84 * sa),
                                    fill=pc, width=max(2, round(r * 0.17 * s)), capstyle="round")
                hr = r * 0.18
                self.cv.create_oval(X(cx - hr), Y(cy - hr), X(cx + hr), Y(cy + hr), fill=pc, outline="")
        else:
            dx, dy = cx + (r - 12) * math.cos(a), cy - (r - 12) * math.sin(a)
            self.cv.create_oval(X(dx - 7), Y(dy - 7), X(dx + 7), Y(dy + 7), fill=T["knob_dot"], outline="")
        self.text_fit(cx, cy + r + 24, self.knob_label(key), 13, 150, T["ink"], True)
        shown = spec.fmt(spec.to_val(n) if p.lock_step is not None else p.val[key])
        if key[2:5] in (".l1", ".l2") and key.endswith("rate") and p.val[key[:5] + "sync"] >= 0.5:
            shown = "Synced"
        if p.lock_step is not None:
            shown = ("LOCK " if locked_here else "") + shown
        self.text(cx, cy + r + 46, shown, 15, T["accent"] if (hot or moved or locked_here) else T["ink_dim"])
        self.text(cx - r - 4, cy - r - 2, str(idx + 1), 10, T["ink_faint"], False, "e")
        if key in p.locks:
            self.rrect(cx + r - 6, cy - r - 12, 18, 16, 4, T["btn_on"])
            self.text(cx + r + 3, cy - r - 4, "L", 10, T["btn_text"], True)
        self.hit(cx - 70, cy - r - 16, 140, 2 * r + 70, lambda k=key: k, "knob")
        slot = self.mod_slot(key)
        if slot:
            self.hit(cx - 74, cy + r + 10, 148, 26, lambda sl=slot: self.open_overlay(("route",) + sl))

    @staticmethod
    def mod_slot(key):
        if key[:2] in ("s1", "s2") and key[2:4] == ".m" and key.endswith("amt"):
            try:
                return key[:2], int(key[4:-3])
            except ValueError:
                return None
        return None

    def route_text(self, pre, j):
        v = self.state.params.val
        src = MOD_SOURCES[int(v[f"{pre}.m{j}src"])]
        if src == "Off":
            return f"Slot {j}: off"
        dst = MOD_DESTS[pre][int(v[f"{pre}.m{j}dst"])]
        return f"{SHORT_DEST.get(src, src)} > {SHORT_DEST.get(dst, dst)}"

    def knob_label(self, key):
        slot = self.mod_slot(key)
        if slot:
            return self.route_text(*slot)[:20]
        if key.startswith("dr.p"):
            pad = int(key.split(".")[1][1:]) - 1
            name = self.audio.engine.drums.names[pad]
            return f"{name} {SPECS[key].label}"[:18]
        lab = SPECS[key].label
        if self.page_name() in ("Perform", "Mix", "Mix EQ", "FX", "Track Mute/Solo", "Master FX") and key[:2] in ("s1", "s2") and "Synth" not in lab:
            lab = key[:2].upper() + " " + lab
        return lab

    # ---------------------------------------------------------------- drawing
    def draw(self):
        cv = self.cv
        cv.delete("all")
        self.hits = []
        cw, ch = cv.winfo_width(), cv.winfo_height()
        self.scale = min(cw / W, ch / H)
        self.ox, self.oy = (cw - W * self.scale) / 2, (ch - H * self.scale) / 2
        if not self.draw_cabinet_image():
            self.rect(0, 0, W, H, fill=T["bg"])
            self.draw_cabinet()
        self.draw_header()
        if self.state.page == "Setup":
            self.draw_setup()
        elif self.state.page == "Live":
            self.draw_live()
        elif self.state.page == "Loop":
            self.draw_loop()
        elif self.state.page == "Beats":
            self.draw_beats()
        elif self.state.page == "Projects":
            self.draw_projects()
        elif self.state.page == "Arrangement":
            self.draw_arrangement()
        elif self.state.page == "Song":
            self.draw_song()
        elif self.state.page == "Capture":
            self.draw_capture()
        elif self.state.page in ("Synth 1", "Synth 2") and not self.state.synth_edit["s" + self.state.page[-1]]:
            self.draw_browser("s" + self.state.page[-1])
        else:
            self.draw_knobs()
            if self.lock_mode:
                self.draw_locks()
            else:
                self.draw_instruments()
        self.draw_tabs()
        ov = self.overlay[0] if self.overlay else None
        draw_ov = {
            "sounds": lambda: self.draw_sounds(self.overlay[1]),
            "kits": self.draw_kits,
            "machines": self.draw_machines,
            "pad": self.draw_pad_editor,
            "mykits": self.draw_mykits,
            "actions": self.draw_actions,
            "route": lambda: self.draw_route(self.overlay[1], self.overlay[2]),
            "resample": self.draw_resample,
            "tempo": self.draw_tempo,
            "setups": self.draw_setups,
            "loopinput": self.draw_loop_input,
            "myloops": self.draw_my_loops,
            "kitmaker": self.draw_kitmaker,
            "ksources": self.draw_ksources,
        }.get(ov)
        if draw_ov:
            draw_ov()
        msg, until = self.toast
        if msg and time.time() < until:
            self.rrect(236, 8, 712, 40, 8, T["btn_on"])
            self.text_fit(592, 28, msg[:70], 18, 690, T["btn_text"], True)

    # ---------------------------------------------------------------- arrangement (a chain of beats = a song)
    ARR_MAX = 16

    def arr_sync(self, bp=None):
        """Hand the chain to the beat player as Beat objects (it plays them in order, then round again)."""
        bp = bp or self.audio.engine.beats
        chain = []
        for d in self.state.arrangement[:self.ARR_MAX]:
            try:
                chain.append(Beat.from_json(d))
            except Exception:
                pass
        bp.chain = chain
        if not chain:
            bp.chain_on = False

    def draw_arrangement(self):
        eng = self.audio.engine
        bp = eng.beats
        arr = self.state.arrangement[:self.ARR_MAX]
        self.frame(14, 100, 1252, 632, "Arrangement", "BEATS PLAY IN THIS ORDER, EACH FOR ITS OWN LENGTH, THEN ROUND AGAIN")
        for i, key in enumerate(PAGES["Arrangement"]):
            self.mini_knob(i, 14 + 39 + i * 77.5, 172, key)
        playing = bp.chain_on and bool(bp.chain) and (bp.on or eng.playing)
        for i in range(self.ARR_MAX):
            r, c = divmod(i, 4)
            x0, y0 = 30 + c * 222, 262 + r * 96
            if i < len(arr):
                d = arr[i]
                g = int(d.get("genre", 0)) % len(GENRES)
                bars = max(1, int(d.get("steps", 16)) // 16)
                now = playing and i == bp.chain_i % max(len(bp.chain), 1)
                self.rrect(x0, y0, 212, 86, 12, T["btn_on"] if now else T["btn_bg"])
                self.text(x0 + 16, y0 + 22, str(i + 1), 13, T["accent"] if not now else T["btn_text"], True, "w")
                self.text(x0 + 106, y0 + 40, GENRE_NAMES[g].upper(), 17, T["btn_text"], True)
                self.text(x0 + 106, y0 + 64, f"{bars} BAR{'S' if bars > 1 else ''}" + ("  ·  PLAYING" if now else ""),
                          11, T["btn_text"] if now else T["key_dim"], now)
                self.hit(x0, y0, 212, 86, lambda j=i: self.arr_pick(j))
            else:
                self.rect(x0, y0, 212, 86, outline=T["ink_faint"])
                first = i == len(arr)
                self.text(x0 + 106, y0 + 43, "+ ADD THE BEAT" if first else "", 13, T["ink_dim"], True)
                if first:
                    self.hit(x0, y0, 212, 86, self.arr_add)
        rx = 1090
        self.button(rx, 300, 300, 72, "■ STOP SONG" if playing else "▶ PLAY SONG", self.arr_play,
                    accent=not playing, on=playing, px=20)
        self.button(rx, 386, 300, 60, "ADD CURRENT BEAT", self.arr_add, px=16)
        self.button(rx, 456, 300, 60, "REMOVE LAST", self.arr_remove_last, px=16)
        armed = time.time() - getattr(self, "arr_clear_armed", 0) < 3
        self.button(rx, 526, 300, 60, "TAP AGAIN TO CLEAR" if armed else "CLEAR SONG", self.arr_clear,
                    accent=armed, px=16)
        self.button(rx, 596, 300, 60, "SAVE SONG AS MIDI FILE", self.arr_export_midi, px=15)
        bars = sum(max(1, int(d.get("steps", 16)) // 16) for d in arr)
        secs = bars * 4 * 60.0 / max(eng.bpm, 30.0)
        info = (f"{len(arr)} BEAT{'S' if len(arr) != 1 else ''} · {bars} BARS · {int(secs // 60)}:{int(secs % 60):02d} AT {eng.bpm:.0f} BPM"
                if arr else "MAKE A BEAT ON THE BEATS TAB, THEN ADD IT HERE. TAP A BEAT TO JUMP TO IT OR HEAR IT.")
        self.text(30, 714, info, 12, T["ink_dim"], False, "w")

    def arr_add(self):
        arr = self.state.arrangement
        if len(arr) >= self.ARR_MAX:
            self.show_toast(f"THE SONG IS FULL ({self.ARR_MAX} BEATS)")
            return
        arr.append(self.audio.engine.beats.beat.to_json())
        self.state.dirty = True
        self.arr_sync()
        self.show_toast(f"ADDED AS BEAT {len(arr)}")

    def arr_remove_last(self):
        if self.state.arrangement:
            self.state.arrangement.pop()
            self.state.dirty = True
            self.arr_sync()
            self.show_toast("REMOVED THE LAST BEAT")

    def arr_clear(self):
        if time.time() - getattr(self, "arr_clear_armed", 0) >= 3:
            self.arr_clear_armed = time.time()
            return
        self.arr_clear_armed = 0
        self.state.arrangement = []
        self.state.dirty = True
        self.arr_sync()
        self.show_toast("SONG CLEARED")

    def arr_pick(self, i):
        """Tap a beat: while the song plays, jump to it; otherwise put it on the Beats tab to hear and edit."""
        bp = self.audio.engine.beats
        if bp.chain_on and bp.on:
            bp.chain_i, bp.chain_pos = i, 0
            return
        d = self.state.arrangement[i]
        bp.beat = Beat.from_json(d)
        self.beat_save()
        self.show_toast(f"BEAT {i + 1} IS ON THE BEATS TAB")

    def arr_play(self):
        eng = self.audio.engine
        bp = eng.beats
        if bp.chain_on and (bp.on or eng.playing):
            bp.chain_on = False
            if self.state.clock_master and self.clockout.playing:
                self.beat_transport()
            else:
                bp.on = False
            return
        self.arr_sync()
        if not bp.chain:
            self.show_toast("ADD A BEAT FIRST")
            return
        bp.chain_restart()
        bp.chain_on = True
        if self.state.clock_master:
            if not self.clockout.playing:
                self.beat_transport()
        else:
            bp.on = True
            bp.auto = False
            if not eng.playing:
                bp.pos = 0.0

    def arr_export_midi(self):
        if not self.state.arrangement:
            self.show_toast("THE SONG IS EMPTY")
            return
        self.save_midi(self.state.arrangement, "Song")

    def _beat_midi_track(self, beats, tempo=False):
        """Beats -> one MIDI track on the drum channel. Pad n plays note 36 + n, like the BeatStep."""
        vel = {"X": 120, "x": 96, "g": 48, "?": 90, ";": 48, "r": 96, "t": 96}
        hits = {"r": 2, "t": 3}
        q = 120  # ticks per 16th at 480 per beat
        events = []
        t0 = 0
        for d in beats:
            steps = int(d.get("steps", 16))
            for role, row in (d.get("grid") or {}).items():
                if role not in ROLE_PAD:
                    continue
                note = 36 + ROLE_PAD[role]
                for st, ch in enumerate(str(row)[:steps]):
                    if ch not in vel:
                        continue
                    k = hits.get(ch, 1)
                    for j in range(k):
                        at = t0 + st * q + j * q // k
                        events.append((at, 1, note, vel[ch] if j == 0 else int(vel[ch] * 0.85)))
                        events.append((at + max(20, q // k // 2), 0, note, 0))
            t0 += steps * q
        events.sort(key=lambda e: (e[0], e[1]))
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name="Drums", time=0))
        if tempo:
            tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(self.audio.engine.bpm), time=0))
        ch = max(0, min(15, self.state.ch["dr"] - 1))
        last = 0
        for at, kind, note, v in events:
            tr.append(mido.Message("note_on" if kind else "note_off", channel=ch, note=note, velocity=v, time=at - last))
            last = at
        return tr

    def save_midi(self, beats, what):
        """Beats -> a .mid file in Music > PotentialBox Recordings."""
        if mido is None:
            self.show_toast("MIDI FILES NEED MIDO - RUN THE INSTALLER AGAIN")
            return
        mid = mido.MidiFile(ticks_per_beat=480)
        mid.tracks.append(self._beat_midi_track(beats, tempo=True))
        try:
            folder = recordings_dir()
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"PotentialBox {what} {time.strftime('%Y-%m-%d %H%M%S')}.mid")
            mid.save(path)
        except Exception as e:
            log("midi save failed", e)
            self.show_toast("COULDN'T SAVE THE MIDI FILE")
            return
        self.show_toast("SAVED IN MUSIC > POTENTIALBOX RECORDINGS", 2.5)

    def photo(self, key, build):
        """A cached Tk image. `build` returns a PIL image (or None if Pillow isn't there)."""
        img = self._sprites.get(key)
        if img is not None:
            return img
        pil = build()
        if pil is None:
            return None
        try:
            from PIL import ImageTk
            img = ImageTk.PhotoImage(pil)
        except Exception:
            return None
        if len(self._sprites) > 800:
            self._sprites.clear()
        self._sprites[key] = img
        return img

    def draw_cabinet_image(self):
        """The hi-fi backdrop: walnut cabinet + brushed plate, rendered once per size and cached."""
        if skins is None or not getattr(skins, "HAVE", False) or not STYLE.get("wood"):
            return False
        s = self.scale
        w, h = max(4, int(round(W * s))), max(4, int(round(H * s)))
        band = max(2, int(round(STYLE["wood"] * s)))
        key = ("cab", w, h, band, T.get("panel", ""), T["accent"])
        img = self.photo(key, lambda: skins.cabinet(w, h, band, "#6d4527", "#3a2413",
                                                    shade(T["panel"], 0.90), shade(T["panel"], 1.08), T["accent"]))
        if img is None:
            return False
        self.cv.create_image(self.X(0), self.Y(0), image=img, anchor="nw")
        return True

    def draw_cabinet(self):
        """Vintage look: walnut cabinet round the window, brushed panel, orange pinstripe."""
        wood = STYLE.get("wood", 0) or 0
        if not wood:
            return
        cv, s = self.cv, self.scale
        import random as _r
        rnd = _r.Random(7)
        wood = min(wood, 40)
        for bx0, by0, bx1, by1 in ((0, 0, W, wood), (0, H - wood, W, H),
                                   (0, 0, wood, H), (W - wood, 0, W, H)):
            cv.create_rectangle(self.X(bx0), self.Y(by0), self.X(bx1), self.Y(by1), fill="#5a3820", outline="")
        tones = ("#472a16", "#6d4527", "#3c2413", "#7c5230")
        for _ in range(130):
            tone = tones[rnd.randrange(len(tones))]
            ph, amp = rnd.uniform(0, 6.28), rnd.uniform(0.4, 1.5)
            pts = []
            if rnd.random() < 0.5:          # grain across the top / bottom rails
                yy = rnd.uniform(0, wood) if rnd.random() < 0.5 else rnd.uniform(H - wood, H)
                for xx in range(0, W + 40, 40):
                    pts += [self.X(min(xx, W)), self.Y(yy + amp * math.sin(xx / 90.0 + ph))]
            else:                           # grain down the two cheeks
                xx = rnd.uniform(0, wood) if rnd.random() < 0.5 else rnd.uniform(W - wood, W)
                for yy in range(0, H + 40, 40):
                    pts += [self.X(xx + amp * math.sin(yy / 90.0 + ph)), self.Y(min(yy, H))]
            cv.create_line(*pts, fill=tone, width=1)
        # brushed panel inside the cabinet
        for yy in range(int(wood) + 2, int(H - wood) - 2, 3):
            cv.create_line(self.X(wood), self.Y(yy), self.X(W - wood), self.Y(yy),
                           fill="#1d1e22" if (yy // 3) % 2 else "#191a1e", width=1)
        # bevelled edge and the orange pinstripe along the bottom
        cv.create_rectangle(self.X(wood), self.Y(wood), self.X(W - wood), self.Y(H - wood),
                            outline="#20130a", width=max(1, round(2 * s)))
        cv.create_line(self.X(wood), self.Y(wood + 1), self.X(W - wood), self.Y(wood + 1),
                       fill="#8a5c34", width=1)
        cv.create_line(self.X(wood), self.Y(H - wood - 3), self.X(W - wood), self.Y(H - wood - 3),
                       fill="#c2591f", width=max(1, round(2 * s)))

    def draw_header(self):
        """Row 1: logo, the display (what's loaded / recording / bouncing), tempo and level.
        Row 2: this section's sub-tabs, and the audio + MIDI lights (tap them for Setup)."""
        eng = self.audio.engine
        self.rect(0, 0, W, 92, fill=T["bg"])
        self.logo(26, 28, APP, 27, T.get("logo", T["accent"]))
        # the display
        x0, y0, dw, dh = 236, 8, 712, 40
        glass = T.get("screen", T["well"])
        img = None
        if STYLE.get("glass") and skins is not None and getattr(skins, "HAVE", False):
            pw, ph = max(8, int(round(dw * self.scale))), max(8, int(round(dh * self.scale)))
            img = self.photo(("scr", pw, ph, glass), lambda: skins.screen(pw, ph, glass))
        if img is not None:
            self.cv.create_image(self.X(x0), self.Y(y0), image=img, anchor="nw")
        else:
            self.rect(x0, y0, dw, dh, fill=glass)
        self.rect(x0, y0, dw, dh, outline=T["line"])
        ink = T.get("lcd_ink", T["accent"])
        line, col = self.display_line(), ink
        if self.audio.error:
            line, col = "AUDIO PROBLEM - TAP AUDIO (RIGHT) TO PICK AN OUTPUT", "#ff8a6a"
        self.text_fit(x0 + 16, y0 + dh / 2, line, 17, dw - 32, col, True, "w", minpx=11)
        # tempo + level
        self.readout(1010, 28, 112, 40, f"{eng.bpm:.0f} BPM")
        self.hit(954, 8, 112, 40, self.toggle_tempo)   # v2.4: tap the tempo for TAP TEMPO and presets
        pk = min(eng.peak, 1.0)
        self.rect(1078, 8, 180, 40, fill=T["well"], outline=T["line"])
        for i in range(18):   # LED ladder
            lit = pk > (i + 0.5) / 18
            c = ("#e0483c" if i >= 16 else T["accent"] if i >= 12 else ink) if lit else shade(T["well"], 1.25)
            self.rect(1084 + i * 9.6, 16, 7, 24, fill=c)
        # row 2: sub-tabs
        sec = SECTION_OF.get(self.state.page, "JAM")
        subs = dict(SECTIONS)[sec]
        tx = 26
        for label, pg in subs:
            on = pg == self.state.page
            w = 156 if len(subs) > 1 else 200
            self.rrect(tx, 56, w, 30, 8, T["seg_active"] if on else T["seg_inactive"])
            self.text_fit(tx + w / 2, 71, label, 15, w - 12, T["seg_active_tx"] if on else T["ink"], True)
            self.hit(tx, 54, w, 34, lambda g=pg: self.set_page(g, tapped=True))
            tx += w + 8
        # audio + MIDI lights
        ok = bool(self.audio.stream) and not self.audio.error
        lat = f"{self.audio.latency_ms:.0f} MS" if ok else "OFF"
        self.status_light(1000, 71, "AUDIO " + lat, ok, False)
        self.status_light(1150, 71, "MIDI", bool(self.midi.ports), time.time() - self.midi.activity < 0.12)
        self.hit(990, 54, 270, 34, lambda: self.set_page("Setup"))
        self.cv.create_line(self.X(0), self.Y(92), self.X(W), self.Y(92), fill=T["line"])

    def status_light(self, x, cy, label, ok, flash):
        c = (T.get("lcd_ink", T["accent"]) if flash else "#3fbf6a") if ok else "#e0483c"
        self.cv.create_oval(self.X(x - 5), self.Y(cy - 5), self.X(x + 5), self.Y(cy + 5), fill=c, outline=T["line"])
        self.text(x + 12, cy, label, 13, T["ink_dim"], True, "w")

    def display_line(self):
        """What the display at the top says: recording / bouncing first, then what's loaded."""
        eng = self.audio.engine
        parts = []
        rec = eng.recorder
        if rec is not None:
            sec = int(rec.seconds())
            parts.append(f"● REC {sec // 60:02d}:{sec % 60:02d}")
        b = eng.bounce
        if b:
            parts.append(self.bounce_text(b))
        elif self.grab_wait:
            parts.append("GRAB: FINISHING THIS BAR...")
        elif any(j.get("state") == "saving" for j in self.bounce_jobs):
            parts.append("SAVING STEMS...")
        pr = self.state.project
        song = eng.beats.parts
        if song is not None:   # v2.4
            parts.append(f"SONG {song.genre.upper()} IN {partsmod.key_name(song.root, song.minor)}")
        elif pr is not None:
            parts.append(f"P{pr + 1:02d} {projmod.NAMES[pr].upper()}")
        parts.append("S1 " + self.state.preset_name["s1"].upper())
        parts.append("S2 " + self.state.preset_name["s2"].upper())
        kn = eng.drums.kit_name.upper()[:22]
        parts.append(kn if "KIT" in kn.split() else "KIT " + kn)   # "ACID SET KIT", not "KIT ACID SET KIT"
        return "  ·  ".join(parts)

    def draw_knobs(self):
        keys = self.page_keys()
        mix = self.state.page == "Mix"
        sub = "BEATSTEP PRO: PRESS CNTRL, THEN TURN KNOBS 1-16  ·  TAP LEFT / RIGHT OF A KNOB TO NUDGE"
        if mix:
            sub = "TAP LEFT / RIGHT OF A KNOB TO NUDGE"
        if self.state.page == "Macros":
            i = getattr(self, "last_macro", None)
            sub = (f"{i + 1} {MACROS[i][0].upper()}: {MACROS[i][1].upper()}" if i is not None
                   else "EACH KNOB MOVES SEVERAL SETTINGS  ·  BACK TO ZERO = BACK TO YOUR SOUND")[:96]
        tab = self.state.page
        if tab not in NO_LOCK_PAGES:
            sub = ""
        self.frame(14, 100, 1252, 372, {"Perform": "Knobs"}.get(tab, tab), sub)
        if tab == "Macros":
            self.button(560, 121, 220, 32, "ZERO ALL MACROS", self.zero_macros, px=13)
        synth = tab in ("Synth 1", "Synth 2")
        if tab in SUBPAGES:
            names = [lab for lab, _ in SUBPAGES[tab]]
            cur = names[self.state.subpage.get(tab, 0) % len(names)]
            x0 = 32 + self.font(22, True).measure(tab.upper()) / self.scale + 22
            x1 = 800 if synth else 950
            bw = min(110, (x1 - x0) / len(names))
            self.rect(x0 - 6, 103, bw * len(names) + 12, 36, fill=T["bg"])  # keeps the frame's rule out from behind
            self.seg(x0, 105, bw, 32, names, cur, self.pick_subpage, vertical=False)
            if self.midi.learn is None and synth:
                undo = getattr(self, "init_undo", None)
                if undo and undo[0] == self.page_name() and time.time() < undo[2]:
                    self.button(895, 121, 160, 32, "UNDO INIT", self.undo_init, px=13)
                else:
                    self.button(895, 121, 160, 32, self.init_label(), self.init_page, accent=True, px=12)
                pre = "s" + tab[-1]
                self.button(1195, 121, 130, 32, "◂ SOUNDS", lambda p=pre: self.synth_view(p, False), on=True, px=14)
        if tab not in NO_LOCK_PAGES and self.midi.learn is None:
            lx, lw = (1050, 130) if synth else (1160, 180)
            self.button(lx, 121, lw, 32, "LOCKS ON" if self.lock_mode else "STEP LOCKS", self.toggle_locks,
                        on=self.lock_mode, px=14)
        if mix and self.midi.learn is None and self.page_name() == "Mix":
            armed = time.time() - getattr(self, "reset_armed", 0) < 3
            self.button(800, 121, 300, 32, "TAP AGAIN TO RESET EVERYTHING" if armed else "RESET ALL TO INIT",
                        self.reset_all, accent=True, px=14)
        if self.midi.learn is not None:
            i = self.midi.learn
            self.rrect(40, 170, 1200, 220, 16, T["btn_on"])
            self.text(640, 235, f"TURN KNOB {i+1} ON THE BEATSTEP PRO", 40, T["btn_text"], True)
            self.text(640, 285, "Top row is 1-8, bottom row is 9-16. Press CNTRL first.", 18, T["btn_text"])
            self.button(520, 345, 220, 60, "SKIP KNOB", self.learn_skip)
            self.button(760, 345, 220, 60, "DONE", self.learn_stop)
            return
        for row in (0, 1):
            ly = 150 + row * 160
            for a, b, label in KNOB_GROUPS.get(self.page_name(), []):
                if a // 8 != row:
                    continue
                x0 = 14 + 10 + (a % 8) * 156.5
                x1 = 14 + ((b - 1) % 8 + 1) * 156.5 - 10
                self.text(x0, ly, label.upper(), 11, T["accent"], True, "w")
                tw = self.font(11, True).measure(label.upper()) / self.scale
                self.cv.create_line(self.X(x0 + tw + 8), self.Y(ly), self.X(x1), self.Y(ly), fill=T["line"])
        for i, key in enumerate(keys):
            row, col = divmod(i, 8)
            cx = 14 + 78 + col * 156.5
            cy = 205 + row * 160
            self.knob(i, cx, cy, 34, key)

    def draw_instruments(self):
        eng = self.audio.engine
        y = 482
        for x, pre, title, src in ((14, "s1", "Synth 1", "SEQ 1"), (434, "s2", "Synth 2", "SEQ 2")):
            syn = eng.s1 if pre == "s1" else eng.s2
            self.frame(x, y, 412, 250, title, f"PLAYED BY {src} · CH {self.state.ch[pre]}", led=syn.amp.stage != 0)
            cx = x + 206
            self.readout(cx + 20, y + 72, 330, 36, self.state.preset_name[pre], "sound")
            self.button(x + 72, y + 135, 120, 62, "< PREV", lambda p=pre: self.preset_step(p, -1))
            self.button(x + 206, y + 135, 120, 62, "NEXT >", lambda p=pre: self.preset_step(p, 1))
            self.button(x + 340, y + 135, 120, 62, "TEST", lambda p=pre: self.test_note(p))
            self.button(x + 108, y + 210, 188, 54, "RANDOM", lambda p=pre: self.random_sound(p), accent=True)
            self.button(x + 304, y + 210, 188, 54, "MY SOUNDS", lambda p=pre: self.open_overlay(("sounds", p)))
        x = 854
        self.frame(x, y, 412, 250, "Drums", f"PLAYED BY DRUM SEQ · CH {self.state.ch['dr']}")
        self.readout(x + 226, y + 72, 330, 36, eng.drums.kit_name[:30], "kit")
        now = time.time()
        for i in range(16):
            row, col = divmod(i, 8)
            bx, by = x + 16 + col * 48.5, y + 102 + row * 50
            act = eng.drums.active[i]
            on = act > 0.05
            self.rrect(bx, by, 44, 44, 8, T["btn_on"] if on else T["btn_bg"],
                       outline=T["accent"] if i == self.sel_pad else "")
            if STYLE.get("screw"):
                self.screw(bx + 35, by + 9)
            self.text(bx + 22, by + 15, str(i + 1), 11, T["btn_text"], True)
            self.text(bx + 22, by + 32, eng.drums.names[i][:5].upper(), 8, T["ink_faint"] if not on else T["btn_text"])
            self.hit(bx, by, 44, 44, lambda p=i: self.test_pad(p))
        self.button(x + 40, y + 222, 52, 42, "<", lambda: self.kit_step(-1), px=20)
        self.button(x + 114, y + 222, 88, 42, "KITS", lambda: self.open_overlay(("kits",)), px=15)
        self.button(x + 188, y + 222, 52, 42, ">", lambda: self.kit_step(1), px=20)
        self.button(x + 270, y + 222, 104, 42, "KIT MAKER", lambda: self.open_overlay(("kitmaker",)), accent=True, px=13)
        self.button(x + 361, y + 222, 70, 42, f"EDIT {self.sel_pad + 1}", self.open_pad_editor, px=13)

    # ---------------------------------------------------------------- overlays
    def overlay_base(self, title, sub):
        self.hit(0, 90, W, 652, lambda: None)  # block taps on the page underneath
        self.rect(4, 94, W - 8, 644, fill=T["bg"])
        self.frame(14, 100, 1252, 632, title, sub)

    def draw_sounds(self, pre):
        name = "Synth 1" if pre == "s1" else "Synth 2"
        self.overlay_base(f"My sounds · {name}", "SAVE HERE STORES THE SOUND YOU HEAR NOW  ·  LOAD PLAYS IT BACK")
        self.button(1176, 172, 150, 56, "CLOSE", self.close_overlay, px=18)
        slots = self.state.sounds[pre]
        cur = self.state.preset_name[pre]
        now = time.time()
        for i in range(SLOTS):
            r, c = divmod(i, 4)
            x0, y0 = 34 + c * 305, 215 + r * 260
            slot = slots[i]
            on = bool(slot) and slot.get("name") == cur
            self.rect(x0, y0, 290, 245, fill=T["seg_active"] if on else T["seg_inactive"], outline=T["line"])
            self.text(x0 + 16, y0 + 24, f"SLOT {i+1}", 13, T["accent"] if on else T["ink_dim"], True, "w")
            self.readout(x0 + 145, y0 + 66, 258, 40, slot["name"] if slot else "EMPTY")
            if slot and slot.get("from"):
                self.text(x0 + 145, y0 + 104, f"made from {slot['from']}"[:34], 12, T["ink_dim"])
            if slot:
                self.button(x0 + 145, y0 + 150, 258, 52, "LOAD", lambda p=pre, j=i: self.load_slot(p, j), px=18)
            else:
                self.rrect(x0 + 16, y0 + 124, 258, 52, 12, T["well"])
                self.text(x0 + 145, y0 + 150, "NOTHING SAVED YET", 13, T["ink_faint"], True)
            armed = self.armed and self.armed[:2] == (pre, i) and now - self.armed[2] < 3
            self.button(x0 + 145, y0 + 210, 258, 52, "TAP AGAIN TO REPLACE" if armed else "SAVE HERE",
                        lambda p=pre, j=i: self.save_slot(p, j), accent=True, px=15 if armed else 18)

    def kit_choices(self):
        ch = [("factory", i, n) for i, n in enumerate(kits.NAMES)]
        for k in self.state.recent:
            if "folder" in k:
                ch.append(("folder", k["folder"], os.path.basename(os.path.normpath(k["folder"]))))
        return ch

    def kit_is_current(self, kind, ref):
        k = self.state.kit
        if kind == "library":
            return list(k.get("library", [])) == list(ref)
        return (kind == "factory" and k.get("factory") == ref) or (kind == "folder" and k.get("folder") == ref)

    def recent_label(self, k):
        if "library" in k:
            return library_kit_label(*k["library"])
        return os.path.basename(os.path.normpath(k["folder"]))

    def draw_kits(self):
        self.overlay_base("Drum kits", "EVERY KIT USES THE SAME PAD LAYOUT, SO YOUR BEATSTEP PATTERNS CARRY OVER")
        cols = 3
        rows = -(-len(kits.KITS) // cols)
        kh = min(108, (410 - (rows - 1) * 7) / rows)   # v2.1: 18 kits fit in 6 rows
        for i, kit in enumerate(kits.KITS):
            r, c = divmod(i, cols)
            x0, y0 = 34 + c * 272, 152 + r * (kh + 7)
            on = self.kit_is_current("factory", i)
            self.rrect(x0, y0, 260, kh, 10, T["seg_active"] if on else T["btn_bg"])
            self.text_fit(x0 + 130, y0 + kh * 0.36, kit["name"].upper(), 18, 244,
                          T["accent"] if on else T["btn_text"], True)
            self.text_fit(x0 + 130, y0 + kh * 0.72, kit["desc"], 11, 244, T["ink_dim"] if on else T["key_dim"])
            self.hit(x0, y0, 260, kh, lambda j=i: self.select_kit("factory", j))
        self.text(34, 584, "TAP A KIT TO HEAR IT. IT STAYS LOADED WHEN YOU CLOSE THIS MENU.", 13, T["ink_dim"], False, "w")
        lib = self.audio.library()
        n = len(lib.machines) if lib.ok() else 0
        self.button(132, 646, 196, 70, f"DRUM MACHINES ({n})" if n else "DRUM MACHINES",
                    lambda: self.open_overlay(("machines",)), accent=True, px=15)
        self.button(336, 646, 196, 70, "KIT MAKER", lambda: self.open_overlay(("kitmaker",)), accent=True, px=18)
        self.button(540, 646, 196, 70, "PLAY DEMO BEAT", self.demo_beat, px=15)
        self.button(744, 646, 196, 70, "RESET PAD KNOBS", self.reset_pads, px=15)
        # recent library kits + folders
        self.text(866, 168, "RECENT KITS", 16, T["accent"], True, "w")
        recent = self.state.recent
        for j, k in enumerate(recent[:4]):
            y0 = 190 + j * 54
            kind = "library" if "library" in k else "folder"
            ref = k[kind]
            on = self.kit_is_current(kind, ref)
            self.rect(866, y0, 380, 48, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(882, y0 + 24, self.recent_label(k).upper()[:32], 14, T["accent"] if on else T["ink"], on, "w")
            self.hit(866, y0, 380, 48, lambda kk=kind, rr=ref: self.select_kit(kk, rr))
        if not recent:
            self.text(1056, 240, "Kits you pick from DRUM MACHINES", 14, T["ink_dim"])
            self.text(1056, 264, "or ADD FOLDER show up here", 14, T["ink_dim"])
        self.button(1056, 448, 380, 56, "MY KITS", lambda: self.open_overlay(("mykits",)), accent=True, px=18)
        self.button(1056, 518, 380, 56, "ADD FOLDER", self.load_kit, px=17)
        self.button(1056, 646, 380, 70, "CLOSE", self.close_overlay, px=20)

    def draw_machines(self):
        lib = self.audio.library()
        if not lib.ok():
            self.overlay_base("Drum machines", "")
            self.text(640, 300, "I can't find your Drum Machine Collection folder.", 22, T["ink"], True)
            self.text(640, 340, "Tap the button and pick the folder that holds the machine folders (Roland TR-808 ...).", 15, T["ink_dim"])
            self.button(640, 440, 420, 80, "PICK LIBRARY FOLDER", self.pick_library, accent=True, px=20)
            self.button(640, 560, 300, 64, "BACK", lambda: self.open_overlay(("kits",)), px=18)
            return
        self.overlay_base("Drum machines", f"{len(lib.machines)} MACHINES  ·  {lib.root[-60:].upper()}")
        self.button(930, 172, 260, 56, "RANDOM MACHINE", self.random_machine, accent=True, px=17)
        self.button(1150, 172, 160, 56, "BACK", lambda: self.open_overlay(("kits",)), px=17)
        brands = list(lib.brands)
        if self.lib_brand not in lib.brands:
            cur = self.state.kit.get("library")
            self.lib_brand = next((b for b in brands if cur and cur[0] in lib.brands[b]), brands[0])
        # brand column
        rows = 10
        bs = self.lib_scroll["brands"] = max(0, min(self.lib_scroll["brands"], max(0, len(brands) - rows)))
        for j, b in enumerate(brands[bs:bs + rows]):
            y0 = 210 + j * 46
            on = b == self.lib_brand
            self.rect(34, y0, 240, 42, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(48, y0 + 21, b.upper()[:16], 15, T["accent"] if on else T["ink"], on, "w")
            self.text(262, y0 + 21, str(len(lib.brands[b])), 12, T["ink_dim"], False, "e")
            self.hit(34, y0, 240, 42, lambda bb=b: self.pick_brand(bb))
        self.arrows(94, 214, 690, "brands", len(brands), rows)
        if self.lib_machine and self.lib_machine in lib.machines:
            self.draw_machine_kits(lib)
            return
        ms = lib.brands[self.lib_brand]
        per = 21
        sc = self.lib_scroll["machines"] = max(0, min(self.lib_scroll["machines"], max(0, (len(ms) - 1) // per * per)))
        cur = (self.state.kit.get("library") or [None])[0]
        for j, m in enumerate(ms[sc:sc + per]):
            r, c = divmod(j, 3)
            x0, y0 = 292 + c * 320, 210 + r * 64
            on = m == cur
            self.rrect(x0, y0, 308, 56, 10, T["seg_active"] if on else T["btn_bg"])
            label = m if self.lib_brand == "Other" else (m[len(brand_of(m)):].strip() or m)
            self.text(x0 + 154, y0 + 28, label.upper()[:30], 14, T["accent"] if on else T["btn_text"], True)
            self.hit(x0, y0, 308, 56, lambda mm=m: self.pick_machine(mm))
        if len(ms) > per:
            self.arrows(352, 432, 690, "machines", len(ms), per, page=per)
            self.text(470, 690, f"{sc // per + 1} / {(len(ms) - 1) // per + 1}", 13, T["ink_dim"], False, "w")
        self.button(1120, 690, 250, 48, "CHANGE FOLDER", self.pick_library, px=14)

    def arrows(self, x_up, x_down, cy, key, total, rows, page=3):
        for cx, d in ((x_up, -1), (x_down, 1)):
            self.button(cx, cy, 70, 48, "", lambda d=d: self.scroll(key, d * page, total, rows))
            pts = [(cx - 13, cy - 7 * d), (cx + 13, cy - 7 * d), (cx, cy + 9 * d)]
            self.cv.create_polygon([c for x, y in pts for c in (self.X(x), self.Y(y))], fill=T["ink"], outline="")

    def draw_machine_kits(self, lib):
        m = self.lib_machine
        ks = lib.kits(m)
        self.text(292, 222, m.upper(), 22, T["accent"], True, "w")
        self.text(292, 250, f"{len(ks)} KIT{'S' if len(ks) != 1 else ''}  ·  TAP ONE TO LOAD AND HEAR IT", 12, T["ink_dim"], False, "w")
        per = 12
        sc = self.lib_scroll["kits"] = max(0, min(self.lib_scroll["kits"], max(0, (len(ks) - 1) // per * per)))
        for j, k in enumerate(ks[sc:sc + per]):
            r, c = divmod(j, 3)
            x0, y0 = 292 + c * 320, 270 + r * 100
            on = self.kit_is_current("library", [m, k["name"]])
            self.rrect(x0, y0, 308, 90, 12, T["seg_active"] if on else T["btn_bg"])
            self.text(x0 + 154, y0 + 36, k["name"].upper()[:28], 16, T["accent"] if on else T["btn_text"], True)
            self.text(x0 + 154, y0 + 64, f"{len(k['files'])} sounds", 12, T["ink_dim"])
            self.hit(x0, y0, 308, 90, lambda kn=k["name"]: self.select_kit("library", [m, kn]))
        if not ks:
            self.text(760, 400, "No WAV files in this machine folder", 16, T["ink_dim"])
        self.button(392, 690, 200, 48, "< MACHINES", self.back_to_machines, px=15)
        if len(ks) > per:
            self.arrows(540, 620, 690, "kits", len(ks), per, page=per)

    # ---------------------------------------------------------------- pad editor (one-shots)
    def open_pad_editor(self, pad=None):
        if pad is not None:
            self.sel_pad = pad
        self.pe["group"] = group_of_type(self.pad_type(self.sel_pad))
        self.pe["scroll"] = 0
        self.open_overlay(("pad",))

    def pad_source(self, p=None):
        """The drum machine or pack the pad's sound comes from (for ONLY THIS SOURCE in the pad editor)."""
        c = self.km_cur()[self.sel_pad if p is None else p]
        return (c or {}).get("src") or (self.state.kit.get("library") or [None])[0]

    def pad_list(self):
        if not self.samples.entries:
            return []
        m = self.pe.get("source") if self.pe["scope"] == "machine" else None
        return self.samples.filter(self.pe["group"], m)

    def draw_pad_editor(self):
        eng = self.audio.engine
        p = self.sel_pad
        src = eng.drums.sources[p] if p < len(eng.drums.sources) else {}
        where = (self.pad_source(p) or os.path.basename(os.path.dirname(src["file"]))) if "file" in src else "built-in"
        self.overlay_base(f"Pad {p + 1} · {eng.drums.names[p]}", "TAP A SOUND TO PUT IT ON THIS PAD  ·  SILENCE AT THE START IS TRIMMED")
        # pad strip
        for i in range(16):
            bx = 34 + i * 76
            on = i == p
            self.rrect(bx, 150, 70, 46, 8, T["seg_active"] if on else T["btn_bg"])
            self.text(bx + 35, 164, str(i + 1), 12, T["accent"] if on else T["btn_text"], True)
            self.text(bx + 35, 184, eng.drums.names[i][:7].upper(), 8, T["key_dim"])
            self.hit(bx, 150, 70, 46, lambda j=i: self.pe_pick_pad(j))
        # categories
        for j, (g, _) in enumerate(GROUPS):
            y0 = 212 + j * 49
            on = g == self.pe["group"]
            self.rect(34, y0, 200, 44, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(50, y0 + 22, g.upper(), 15, T["accent"] if on else T["ink"], on, "w")
            self.hit(34, y0, 200, 44, lambda gg=g: self.pe_group(gg))
        # sound list
        x0, w = 250, 690
        if not self.samples.entries and not self.samples.busy:
            self.text(x0 + w / 2, 380, "No sample folders yet.", 16, T["ink_dim"])
            self.button(x0 + w / 2, 440, 340, 60, "SAMPLE FOLDERS", lambda: self.open_overlay(("ksources",)), px=16)
        elif not self.samples.entries:
            self.text(x0 + w / 2, 400, "Reading your samples...", 18, T["ink_dim"])
        else:
            lst = self.pad_list()
            rows = 10
            sc = self.pe["scroll"] = max(0, min(self.pe["scroll"], max(0, (len(lst) - 1) // rows * rows)))
            cur = src.get("file")
            for j, (m, path, cat, label) in enumerate(lst[sc:sc + rows]):
                y0 = 212 + j * 46
                on = path == cur
                self.rect(x0, y0, w, 42, fill=T["seg_active"] if on else T["seg_inactive"])
                self.text(x0 + 14, y0 + 21, label.upper(), 15, T["accent"] if on else T["ink"], on, "w")
                self.text(x0 + w - 14, y0 + 21, m[:34], 12, T["ink_dim"], False, "e")
                self.hit(x0, y0, w, 42, lambda pp=path, ll=label: self.pe_assign(pp, ll))
            if not lst:
                self.text(x0 + w / 2, 400, "No sounds of this type here", 16, T["ink_dim"])
            self.arrows(x0 + 40, x0 + 120, 700, "pe", len(lst), rows, page=rows)
            if lst:
                self.text(x0 + 170, 700, f"{sc + 1}-{min(sc + rows, len(lst))} OF {len(lst)}", 13, T["ink_dim"], False, "w")
        # actions (right column: 950-1250)
        rx, lx, rx2 = 1100, 1024, 1176
        self.button(rx, 236, 300, 52, f"RANDOM {self.pe['group'].upper()}", self.pe_random, accent=True, px=17)
        locked = p in self.state.locked_pads
        self.button(lx, 290, 148, 48, "PLAY PAD", lambda: self.test_pad(p), px=15)
        self.button(rx2, 290, 148, 48, "UNLOCK PAD" if locked else "LOCK PAD",
                    lambda pp=p: self.toggle_pad_lock(pp), on=locked, px=14)
        scope_m = self.pe.get("source") if self.pe["scope"] == "machine" else self.pad_source()
        self.seg(950, 320, 150, 40, ["all", "this source"], {"machine": "this source"}.get(self.pe["scope"], "all"),
                 lambda v: self.pe_scope("machine" if v == "this source" else "all"), vertical=False)
        self.text_fit(rx, 374, ("ONLY " + scope_m.upper()) if scope_m else "THIS PAD HAS A BUILT-IN SOUND",
                      10, 296, T["ink_dim"])
        self.button(lx, 410, 148, 48, "FROM FILE...", self.pe_from_file, px=14)
        self.button(rx2, 410, 148, 48, "SAVE MY KIT", lambda: self.open_overlay(("mykits",)), px=14)
        self.text(952, 452, "EDIT THIS PAD'S SOUND", 11, T["accent"], True, "w")
        for j, row in enumerate(((("TRIM", self.sample_trim), ("NORMALIZE", self.sample_normalize)),
                                 (("FADE IN", self.sample_fade_in), ("FADE OUT", self.sample_fade_out)),
                                 (("PITCH −1", lambda: self.sample_pitch(-1)), ("PITCH +1", lambda: self.sample_pitch(1))))):
            for k, (lab, fn) in enumerate(row):
                self.button(lx if k == 0 else rx2, 486 + j * 50, 148, 44, lab, fn, px=13)
        self.text_fit(rx, 628, f"NOW: {where.upper()}", 10, 296, T["ink_dim"])
        self.button(rx, 676, 300, 52, "DONE", self.close_overlay, px=18)

    def toggle_pad_lock(self, pad):
        if pad in self.state.locked_pads:
            self.state.locked_pads.discard(pad)
            self.show_toast(f"PAD {pad + 1} UNLOCKED")
        else:
            self.state.locked_pads.add(pad)
            self.show_toast(f"PAD {pad + 1} LOCKED")
        self.state.dirty = True

    def _edit_pad_sample(self, fn):
        eng = self.audio.engine
        p = self.sel_pad
        layers = eng.drums.samples[p]
        if not layers:
            self.show_toast("NO SAMPLE")
            return
        x = np.asarray(layers[0], dtype=np.float64).copy()
        x = fn(x, eng.sr)
        if x is None or len(x) < 2:
            self.show_toast("FAILED")
            return
        layers[0] = np.append(x, 0.0).astype(np.float32)
        self.state.dirty = True

    def sample_trim(self):
        def fn(x, sr):
            thr = max(1e-4, 0.01 * float(np.max(np.abs(x))))
            idx = np.where(np.abs(x) > thr)[0]
            if len(idx) == 0:
                return x
            start = max(0, int(idx[0]) - int(0.001 * sr))
            end = min(len(x), int(idx[-1]) + int(0.001 * sr))
            return x[start:end]
        self._edit_pad_sample(fn)
        self.show_toast(f"PAD {self.sel_pad + 1} TRIMMED")

    def sample_normalize(self):
        def fn(x, sr):
            peak = float(np.max(np.abs(x))) if x.size else 0.0
            if peak <= 1e-6:
                return x
            return x / peak * 0.99
        self._edit_pad_sample(fn)
        self.show_toast(f"PAD {self.sel_pad + 1} NORMALIZED")

    def sample_fade_in(self):
        def fn(x, sr):
            n = len(x)
            f = min(n, int(0.05 * sr))
            if f < 2:
                return x
            x = x.copy()
            x[:f] *= np.linspace(0.0, 1.0, f)
            return x
        self._edit_pad_sample(fn)
        self.show_toast(f"PAD {self.sel_pad + 1} FADE IN")

    def sample_fade_out(self):
        def fn(x, sr):
            n = len(x)
            f = min(n, int(0.05 * sr))
            if f < 2:
                return x
            x = x.copy()
            x[-f:] *= np.linspace(1.0, 0.0, f)
            return x
        self._edit_pad_sample(fn)
        self.show_toast(f"PAD {self.sel_pad + 1} FADE OUT")

    def sample_pitch(self, semis):
        def fn(x, sr):
            if len(x) < 2:
                return x
            factor = 2.0 ** (semis / 12.0)
            new_n = max(2, int(len(x) / factor))
            return np.interp(np.linspace(0, len(x) - 1, new_n), np.arange(len(x)), x)
        self._edit_pad_sample(fn)
        self.show_toast(f"PAD {self.sel_pad + 1} PITCH {semis:+d} ST")

    def pe_pick_pad(self, i):
        self.sel_pad = i
        self.pe["group"] = group_of_type(self.pad_type(i))
        if self.pe["scope"] == "machine" and self.pad_source(i):
            self.pe["source"] = self.pad_source(i)
        self.pe["scroll"] = 0
        self.test_pad(i)

    def pe_group(self, g):
        self.pe["group"] = g
        self.pe["scroll"] = 0

    def pe_scope(self, s):
        if s == "machine":
            src = self.pad_source()
            if not src:
                self.show_toast("THIS PAD HAS A BUILT-IN SOUND")
                return
            self.pe["source"] = src
        self.pe["scope"] = s
        self.pe["scroll"] = 0

    def scroll(self, key, d, total, rows):
        if key == "pe":
            self.pe["scroll"] = max(0, min(self.pe["scroll"] + d, max(0, total - 1)))
        else:
            self.lib_scroll[key] = max(0, min(self.lib_scroll[key] + d, max(0, total - 1)))
        self.request_redraw()

    def pe_assign(self, path, label):
        eng = self.audio.engine
        try:
            eng.drums.set_pad(self.sel_pad, path, label)
            e = self.samples.find(path)
            if e:
                eng.drums.sources[self.sel_pad].update(type=e.type, src=e.src)
        except Exception as e:
            log("pad load failed", path, e)
            self.show_toast("COULDN'T READ THAT FILE")
            return
        name = eng.drums.kit_name
        if not name.endswith(" *"):
            name = (name[:26] + " *")
        eng.drums.kit_name = name
        self.state.kit = {"pads": eng.drums.sources, "name": name}
        self.state.dirty = True
        self.audio.engine.note_on("dr", self.sel_pad, 110)

    def pe_random(self):
        lst = self.pad_list()
        if not lst:
            self.show_toast("NO SOUNDS TO PICK FROM")
            return
        import random as _r
        m, path, cat, label = _r.choice(lst)
        self.pe_assign(path, label)
        i = lst.index((m, path, cat, label))
        self.pe["scroll"] = i // 10 * 10

    def pe_from_file(self):
        path = filedialog.askopenfilename(title=f"Pick a WAV for pad {self.sel_pad + 1}",
                                          filetypes=[("WAV audio", "*.wav *.WAV")])
        if path:
            self.pe_assign(path, os.path.splitext(os.path.basename(path))[0][:24])

    # ---------------------------------------------------------------- samples + Kit Maker
    def sample_roots(self):
        return default_roots(self.state.library_root, self.state.sample_folders)

    def rescan_samples(self, quiet=True):
        """Read the sample folders again in the background (only new or changed files are opened)."""
        def done():
            self.request_redraw()
            if not quiet:
                self.toast = (f"{len(self.samples.entries)} SOUNDS READY", time.time() + 1.6)
        if not self.samples.scan_async(self.sample_roots(), done):
            self.samples_again = True

    def samples_tick(self):
        if getattr(self, "samples_again", False) and not self.samples.busy:
            self.samples_again = False
            self.rescan_samples()
        s = self.sync
        if s is not None and not s.busy and getattr(self, "sync_thread", None) is not None:
            self.sync_thread = None
            if s.copied and s.dest not in self.state.sample_folders:
                self.state.sample_folders.append(s.dest)
                self.state.dirty = True
            if s.copied or s.dest in self.state.sample_folders:
                self.rescan_samples(quiet=False)
            self.show_toast("MPC ONE-SHOTS: " + ("FAILED" if s.error else f"{s.copied} NEW"), 2.0)
            self.request_redraw()
        if (s is not None and s.busy) or self.samples.busy:
            self.request_redraw()

    def km_cur(self):
        """The kit as Kit Maker sees it: 16 dicts (file, label, type, src, tune, decay) or None for built-in pads."""
        d = self.audio.engine.drums
        val = self.state.params.val
        out = []
        for i, src in enumerate(d.sources):
            if "file" not in src:
                out.append(None)
                continue
            t, sname = src.get("type"), src.get("src")
            if not t or not sname:
                e = self.samples.find(src["file"]) if self.samples.ready else None
                t = t or (e.type if e else None)
                sname = sname or (e.src if e else "")
            out.append({"file": src["file"], "label": src.get("label", ""), "type": t, "src": sname or "",
                        "tune": int(val[f"dr.p{i+1}.tune"]), "decay": float(val[f"dr.p{i+1}.decay"])})
        return out

    def pad_type(self, i):
        c = self.km_cur()[i]
        return (c or {}).get("type") or kitmaker.PAD_ROLE[i].replace("Kick 2", "Kick").replace("Low Tom", "Tom") \
            .replace("Mid Tom", "Tom").replace("High Tom", "Tom")

    def km_snapshot(self):
        d = self.audio.engine.drums
        p = self.state.params
        keys = [f"dr.p{i}.{x}" for i in range(1, 17) for x in ("tune", "decay", "level")]
        return {"pads": [dict(s) for s in d.sources], "name": d.kit_name, "params": {k: p.val[k] for k in keys}}

    def km_restore(self, snap):
        d = self.audio.engine.drums
        d.load_sources(snap["pads"], snap["name"])
        for k, v in snap["params"].items():
            self.state.params.set_val(k, v)
        self.state.kit = {"pads": d.sources, "name": snap["name"]}
        self.state.dirty = True

    def km_apply(self, pads, name, match=True):
        """Put new pads on the kit (None = keep that pad), set their tune and length, even out their levels."""
        if not any(pads):
            self.show_toast("NO SOUNDS TO PICK FROM")
            return False
        self.km_hist.append(self.km_snapshot())
        while len(self.km_hist) > 12:
            self.km_hist.popleft()
        d = self.audio.engine.drums
        srcs = []
        for i in range(16):
            if pads[i]:
                pd = pads[i]
                srcs.append({"file": pd["file"], "label": pd["label"], "type": pd["type"], "src": pd["src"]})
            else:
                srcs.append(dict(d.sources[i]))
        loaded = d.load_sources(srcs, name)
        p = self.state.params
        for i, pd in enumerate(pads):
            if pd:
                p.set_val(f"dr.p{i+1}.tune", pd["tune"])
                p.set_val(f"dr.p{i+1}.decay", pd["decay"])
        if match:
            lv = kitmaker.match_levels([d.samples[i][0] if d.samples[i] else None for i in range(16)],
                                       [(d.sources[i].get("type") or "Other") for i in range(16)], d.sr)
            for i, pd in enumerate(pads):
                if pd and lv[i] is not None:
                    p.set_val(f"dr.p{i+1}.level", lv[i])
        self.state.kit = {"pads": d.sources, "name": name}
        self.state.dirty = True
        self.request_redraw()
        return loaded

    def km_ready(self):
        if self.samples.entries:
            return True
        if self.samples.busy:
            self.show_toast("STILL READING YOUR SAMPLES...")
        else:
            self.show_toast("NO SAMPLES YET - ADD A FOLDER")
            self.open_overlay(("ksources",))
        return False

    def km_name(self, style=None):
        return f"Kit Maker · {(style or self.state.km['style']).title()}"

    def km_new(self, style=None, preview=True, toast=True):
        if not self.km_ready():
            return
        km = self.state.km
        if style:
            km["style"] = style
        pads, src = kitmaker.make_kit(self.samples, km["style"], self.state.locked_pads, self.km_rng,
                                      km["scope"], km["one"])
        if self.km_apply(pads, self.km_name()):
            if preview:
                self.play_pattern([[0], [4], [2], [4]], 130)
            if toast:
                self.show_toast(f"NEW {km['style']} KIT" + (f" · {src.upper()[:20]}" if src else ""), 1.4)

    def km_roll(self, mode):
        if not self.km_ready():
            return
        km = self.state.km
        locked = self.state.locked_pads
        if mode == "MILD":
            pads = kitmaker.roll_mild(self.samples, self.km_cur(), locked, self.km_rng, km["scope"])
        elif mode == "MEDIUM":
            pads, _ = kitmaker.make_kit(self.samples, km["style"], locked, self.km_rng, km["scope"], km["one"],
                                        tune_jitter=2, decay_jitter=0.3)
        else:
            pads, _ = kitmaker.make_kit(self.samples, km["style"], locked, self.km_rng, km["scope"], False,
                                        wild=0.45, tune_jitter=5, decay_jitter=0.6)
        if self.km_apply(pads, self.km_name()):
            changed = [i for i, x in enumerate(pads) if x]
            if mode == "MILD":
                self.play_pattern([[i] for i in changed], 170)
            else:
                self.play_pattern([[0], [4], [2], [4]], 130)
            self.show_toast(f"ROLL {mode}: {len(changed)} PAD{'S' if len(changed) != 1 else ''}", 1.2)

    def km_type(self, t):
        if not self.km_ready():
            return
        i = self.sel_pad
        cur = self.km_cur()
        new = kitmaker.reroll_pad(self.samples, i, t, cur[i], self.km_rng, self.state.km["scope"], cur)
        if new is None:
            self.show_toast(f"NO {t.upper()} SOUNDS")
            return
        pads = [None] * 16
        pads[i] = new
        name = self.audio.engine.drums.kit_name
        if self.km_apply(pads, name if name.startswith("Kit Maker") else self.km_name()):
            self.audio.engine.note_on("dr", i, 110)

    def km_reroll(self):
        self.km_type(self.pad_type(self.sel_pad))

    def km_back(self):
        if not self.km_hist:
            self.show_toast("NO EARLIER KIT")
            return
        self.km_restore(self.km_hist.pop())
        self.play_pattern([[0], [4], [2], [4]], 130)
        self.show_toast("PREVIOUS KIT", 1.0)

    def km_select(self, i):
        self.sel_pad = i
        self.test_pad(i)

    def km_adjust(self, part, d):
        p = self.state.params
        k = f"dr.p{self.sel_pad + 1}.{part}"
        sp = SPECS[k]
        p.set_val(k, max(sp.lo, min(sp.hi, p.val[k] + d)))
        self.state.dirty = True
        self.audio.engine.note_on("dr", self.sel_pad, 110)

    def km_match(self):
        d = self.audio.engine.drums
        lv = kitmaker.match_levels([s[0] if s else None for s in d.samples],
                                   [(src.get("type") or self.pad_type(i)) for i, src in enumerate(d.sources)], d.sr)
        for i, v in enumerate(lv):
            if v is not None:
                self.state.params.set_val(f"dr.p{i+1}.level", v)
        self.state.dirty = True
        self.play_pattern([[0], [4], [2], [4], [0], [3], [5], [9]], 150)
        self.show_toast("LEVELS MATCHED", 1.2)

    def km_set(self, key, v):
        self.state.km[key] = v
        self.state.dirty = True

    def draw_kitmaker(self):
        eng = self.audio.engine
        ix = self.samples
        km = self.state.km
        nf = len([r for r in self.sample_roots() if r["path"] and os.path.isdir(r["path"])])
        sub = (f"{len(ix.entries)} SOUNDS IN {nf} FOLDER{'S' if nf != 1 else ''}  ·  LOCKED PADS STAY" if ix.entries else
               "READING YOUR SAMPLES..." if ix.busy else "ADD A SAMPLE FOLDER TO START")
        self.overlay_base("Kit Maker", sub)
        self.button(134, 172, 200, 64, "NEW KIT", lambda: self.km_new(), accent=True, px=22)
        for j, m in enumerate(("MILD", "MEDIUM", "WILD")):
            self.button(316 + j * 146, 172, 140, 64, f"ROLL {m}", lambda mm=m: self.km_roll(mm), px=15)
        self.button(784, 172, 140, 64, "PREVIOUS KIT", self.km_back, px=14)
        self.button(1000, 172, 236, 64, "SAMPLE FOLDERS", lambda: self.open_overlay(("ksources",)), px=16)
        self.button(1192, 172, 120, 64, "CLOSE", self.close_overlay, px=17)
        cur = self.km_cur()
        if not ix.entries:
            self.rect(34, 212, 820, 400, fill=T["well"])
            if ix.busy:
                self.text(444, 380, "Reading your samples...", 22, T["ink"], True)
                self.text(444, 416, (ix.progress or "")[:50], 14, T["ink_dim"])
            else:
                self.text(444, 330, "Kit Maker builds kits from your own one-shots.", 20, T["ink"], True)
                self.text(444, 366, "Tap SAMPLE FOLDERS to add a folder or copy your MPC's DRUM ONE SHOTS.", 14,
                          T["ink_dim"])
                self.button(444, 450, 360, 70, "SAMPLE FOLDERS", lambda: self.open_overlay(("ksources",)),
                            accent=True, px=20)
        else:
            for i in range(16):
                r, c = divmod(i, 8)
                x0, y0 = 34 + c * 103, 212 + r * 140
                self.km_tile(i, x0, y0, cur[i], eng)
        # styles
        self.text(34, 498, "STYLE  ·  TAP ONE FOR A NEW KIT IN THAT STYLE", 12, T["accent"], True, "w")
        for j, st in enumerate(kitmaker.STYLES):
            r, c = divmod(j, 6)
            x0, y0 = 34 + c * 137, 512 + r * 54
            on = st["name"] == km["style"]
            self.rrect(x0, y0, 132, 48, 10, T["btn_on"] if on else T["btn_bg"])
            self.text_fit(x0 + 66, y0 + 18, st["name"], 15, 124, T["btn_text"], True)
            self.text_fit(x0 + 66, y0 + 36, st["desc"], 11, 124, T["btn_text"] if on else T["ink_dim"])
            self.hit(x0, y0, 132, 48, lambda s=st["name"]: self.km_new(s))
        # where sounds come from
        self.text(34, 638, "DRAW FROM", 11, T["ink_dim"], True, "w")
        for j, sc in enumerate(kitmaker.SCOPES):
            on = sc == km["scope"]
            self.rect(36 + j * 150, 654, 146, 48, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text_fit(34 + j * 150 + 75, 678, kitmaker.SCOPE_LABEL[sc], 13, 140,
                          T["seg_active_tx"] if on else T["ink_dim"], on)
            self.hit(34 + j * 150, 652, 150, 52, lambda v=sc: self.km_set("scope", v))
        self.button(574, 678, 156, 52, "ONE SOURCE: ON" if km["one"] else "ONE SOURCE: OFF",
                    lambda: self.km_set("one", not km["one"]), on=km["one"], px=13)
        self.button(746, 678, 160, 52, "MATCH LEVELS", self.km_match, px=14)
        self.text(34, 720, "ONE SOURCE: the whole kit from one drum machine or pack where it can", 12, T["ink_dim"],
                  False, "w")
        self.km_panel(cur)

    def km_tile(self, i, x0, y0, c, eng):
        on = i == self.sel_pad
        locked = i in self.state.locked_pads
        hit_now = eng.drums.active[i] > 0.05
        fill = T["btn_on"] if hit_now else (T["seg_active"] if on else T["btn_bg"])
        self.rrect(x0, y0, 98, 132, 10, fill, outline=T["accent"] if on else "")
        tx = T["btn_text"] if hit_now else (T["seg_active_tx"] if on else T["btn_text"])
        t = (c or {}).get("type") or ("BUILT-IN" if c is None else "?")
        self.text(x0 + 10, y0 + 16, str(i + 1), 14, tx, True, "w")
        self.text_fit(x0 + 90, y0 + 16, SHORT_TYPE.get(t, t).upper(), 11, 56, tx if (hit_now or on) else T["ink_dim"],
                      True, "e")
        name = (c or {}).get("label") or eng.drums.names[i]
        a, b = self.split2(name.upper(), 11)
        self.text_fit(x0 + 49, y0 + 42, a, 12, 90, tx, True)
        if b:
            self.text_fit(x0 + 49, y0 + 58, b, 12, 90, tx, True)
        self.text_fit(x0 + 49, y0 + 80, ((c or {}).get("src") or "built-in")[:22], 11, 90, tx if on else T["ink_dim"])
        self.hit(x0, y0, 98, 96, lambda j=i: self.km_select(j))
        self.rrect(x0 + 6, y0 + 98, 86, 28, 8, T["btn_on"] if locked else T["well"])
        self.text(x0 + 49, y0 + 112, "LOCKED" if locked else "LOCK", 11, T["btn_text"] if locked else T["ink_dim"], True)
        self.hit(x0, y0 + 96, 98, 36, lambda j=i: self.toggle_pad_lock(j))

    @staticmethod
    def split2(s, n):
        if len(s) <= n:
            return s, ""
        cut = s.rfind(" ", 0, n + 1)
        if cut <= 0:
            cut = n
        return s[:cut].strip(), s[cut:].strip()

    def km_panel(self, cur):
        i = self.sel_pad
        c = cur[i] or {}
        p = self.state.params.val
        x0, w = 870, 380
        self.rect(x0, 212, w, 498, fill=T["well"], outline=T["line"])
        t = self.pad_type(i)
        self.text(x0 + 16, 234, f"PAD {i + 1}  ·  {t.upper()}", 17, T["accent"], True, "w")
        self.text_fit(x0 + 16, 260, (c.get("label") or self.audio.engine.drums.names[i]).upper(), 14, w - 32, T["ink"],
                      True, "w")
        self.text_fit(x0 + 16, 282, c.get("src") or "built-in sound", 11, w - 32, T["ink_dim"], False, "w")
        locked = i in self.state.locked_pads
        self.button(x0 + 66, 320, 116, 46, "PLAY", lambda: self.test_pad(i), px=15)
        self.button(x0 + 190, 320, 116, 46, "NEW " + SHORT_TYPE.get(t, t).upper()[:6], self.km_reroll, accent=True,
                    px=13)
        self.button(x0 + 314, 320, 116, 46, "UNLOCK" if locked else "LOCK", lambda: self.toggle_pad_lock(i),
                    on=locked, px=14)
        self.text(x0 + 16, 362, "TYPE  ·  TAP FOR A NEW SOUND OF THAT TYPE", 11, T["ink_dim"], True, "w")
        counts = self.samples.type_counts()
        for j, ty in enumerate(TYPES):
            r, col = divmod(j, 6)
            bx, by = x0 + 8 + col * 61, 374 + r * 44
            on = ty == t
            n = counts.get(ty, 0)
            self.rrect(bx, by, 57, 40, 8, T["btn_on"] if on else (T["btn_bg"] if n else T["seg_inactive"]))
            self.text_fit(bx + 28.5, by + 15, SHORT_TYPE.get(ty, ty).upper(), 11, 53,
                          T["btn_text"] if (on or n) else T["ink_faint"], True)
            self.text(bx + 28.5, by + 31, str(n), 10, T["btn_text"] if on else T["ink_dim"])
            self.hit(bx, by, 57, 40, lambda tt=ty: self.km_type(tt))
        rows = (("PITCH", "tune", 1, f"{int(p[f'dr.p{i+1}.tune']):+d} ST"),
                ("LENGTH", "decay", 0.1, f"{int(round(p[f'dr.p{i+1}.decay'] * 100))} %"),
                ("LEVEL", "level", 0.05, f"{int(round(p[f'dr.p{i+1}.level'] * 100))} %"))
        for j, (lab, part, step, txt) in enumerate(rows):
            y = 528 + j * 50
            self.text(x0 + 16, y, lab, 13, T["ink"], True, "w")
            self.button(x0 + 160, y, 70, 42, "−", lambda pp=part, s=step: self.km_adjust(pp, -s), px=22)
            self.text(x0 + 245, y, txt, 14, T["accent"], True)
            self.button(x0 + 330, y, 70, 42, "+", lambda pp=part, s=step: self.km_adjust(pp, s), px=22)
        self.button(x0 + 96, 678, 176, 50, "SAVE MY KIT", lambda: self.open_overlay(("mykits",)), px=15)
        self.button(x0 + 284, 678, 176, 50, "PICK FROM LIST", lambda: self.open_pad_editor(i), px=14)

    # ---------------------------------------------------------------- sample folders
    def draw_ksources(self):
        ix = self.samples
        self.overlay_base("Sample folders", "KIT MAKER AND THE PAD EDITOR USE EVERY ONE-SHOT IN THESE FOLDERS")
        self.button(1000, 172, 236, 64, "KIT MAKER", lambda: self.open_overlay(("kitmaker",)), accent=True, px=17)
        self.button(1192, 172, 120, 64, "CLOSE", self.close_overlay, px=17)
        rows = [("DRUM MACHINES", self.state.library_root, "machines")] + \
               [("FOLDER", f, "folder") for f in self.state.sample_folders]
        now = time.time()
        for j, (kind, path, k) in enumerate(rows[:7]):
            y0 = 152 + j * 64 + (40 if j else 0)
            if j == 1:
                self.text(34, 236, "YOUR SAMPLE FOLDERS", 12, T["accent"], True, "w")
            ok = bool(path) and os.path.isdir(path)
            self.rect(34, y0, 820, 58, fill=T["seg_inactive"], outline=T["line"])
            name = os.path.basename(os.path.normpath(path)) if path else "Drum Machine Collection (not found)"
            self.text_fit(50, y0 + 20, name.upper(), 16, 520, T["ink"] if ok else T["ink_faint"], True, "w")
            self.text_fit(50, y0 + 42, path or "Pick the folder that holds your machine folders", 10, 520, T["ink_dim"],
                          False, "w")
            n = ix.counts.get(path)
            self.text(620, y0 + 29, ("MISSING" if path and not ok else f"{n} SOUNDS" if n is not None else "..."),
                      13, T["accent"] if ok else T["ink_faint"], True, "e")
            if k == "machines":
                self.button(744, y0 + 29, 200, 44, "CHANGE", self.pick_library, px=14)
            else:
                armed = self.armed and self.armed[:2] == ("rmsrc", path) and now - self.armed[2] < 3
                self.button(744, y0 + 29, 200, 44, "TAP AGAIN TO REMOVE" if armed else "REMOVE",
                            lambda pp=path: self.remove_sample_folder(pp), px=12 if armed else 14)
        if len(rows) == 1:
            self.text(444, 300, "No folders yet. Add one, or copy your MPC's one-shots.", 15, T["ink_dim"])
        # right column: add / MPC / rescan
        x0 = 870
        self.rect(x0, 212, 380, 498, fill=T["well"], outline=T["line"])
        self.button(x0 + 190, 262, 340, 64, "ADD A FOLDER", self.add_sample_folder, px=18)
        s = self.sync
        busy = s is not None and s.busy
        self.button(x0 + 190, 350, 340, 72, "STOP COPYING" if busy else "GET MPC ONE-SHOTS",
                    self.stop_mpc_sync if busy else self.start_mpc_sync, accent=True, px=18)
        msg = s.status if s else "Copies the DRUM ONE SHOTS folder MPC TOOLS makes on your MPC's SD card, over SSH. " \
                                 "Tap again later to fetch only new sounds."
        for k, line in enumerate(self.wrap(msg, 46)[:4]):
            self.text(x0 + 20, 402 + k * 18, line, 11, T["ink"] if s else T["ink_dim"], False, "w")
        if busy and s.total:
            self.rect(x0 + 20, 478, 340, 10, fill=T["seg_inactive"])
            self.rect(x0 + 20, 478, 340 * s.done / max(1, s.total), 10, fill=T["accent"])
        self.button(x0 + 190, 530, 340, 56, "READING..." if ix.busy else "READ FOLDERS AGAIN",
                    lambda: self.rescan_samples(quiet=False), px=15)
        tc = ix.type_counts()
        parts = [f"{SHORT_TYPE.get(t, t).upper()} {n}" for t, n in tc.items() if n]
        for k, line in enumerate(self.wrap("  ·  ".join(parts) if parts else "No sounds yet", 48)[:5]):
            self.text(x0 + 20, 584 + k * 18, line, 11, T["ink_dim"], False, "w")
        if ix.skipped:
            self.text(x0 + 20, 690, f"{ix.skipped} loops or long files left out", 10, T["ink_faint"], False, "w")

    @staticmethod
    def wrap(s, n):
        out, line = [], ""
        for w in s.split(" "):
            if len(line) + len(w) + 1 > n and line:
                out.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            out.append(line)
        return out

    def add_sample_folder(self):
        folder = filedialog.askdirectory(title="Pick a folder of one-shot samples (subfolders are read too)")
        if not folder:
            return
        folder = os.path.normpath(folder)
        if folder in self.state.sample_folders or folder == self.state.library_root:
            self.show_toast("ALREADY ADDED")
            return
        self.state.sample_folders.append(folder)
        self.state.dirty = True
        self.rescan_samples(quiet=False)

    def remove_sample_folder(self, path):
        now = time.time()
        if not (self.armed and self.armed[:2] == ("rmsrc", path) and now - self.armed[2] < 3):
            self.armed = ("rmsrc", path, now)
            self.root.after(3100, self.request_redraw)
            return
        self.armed = None
        if path in self.state.sample_folders:
            self.state.sample_folders.remove(path)
            self.state.dirty = True
            self.rescan_samples()

    def start_mpc_sync(self):
        if self.sync is not None and self.sync.busy:
            return
        s = MpcSync(self.state.mpc_dest, host=self.state.mpc_host or None)
        if not s.host:
            from tkinter import simpledialog
            h = simpledialog.askstring("Your MPC", "Your MPC's network address (it's on MPC TOOLS' first screen):",
                                       parent=self.root)
            if not h or not h.strip():
                return
            s.host = self.state.mpc_host = h.strip()
            self.state.dirty = True
        self.sync = s
        self.sync_thread = threading.Thread(target=s.run, daemon=True)
        self.sync_thread.start()
        self.request_redraw()

    def stop_mpc_sync(self):
        if self.sync is not None:
            self.sync.cancel = True

    # ---------------------------------------------------------------- my kits
    def draw_mykits(self):
        self.overlay_base("My kits", "SAVE HERE STORES THE KIT YOU HAVE NOW (EVERY PAD)  ·  LOAD BRINGS IT BACK")
        self.button(1150, 172, 160, 56, "BACK", lambda: self.open_overlay(("kits",)), px=17)
        now = time.time()
        cur = self.state.kit.get("name")
        for i in range(SLOTS):
            r, c = divmod(i, 4)
            x0, y0 = 34 + c * 305, 215 + r * 260
            slot = self.state.mykits[i]
            on = bool(slot) and slot.get("name") == cur
            self.rect(x0, y0, 290, 245, fill=T["seg_active"] if on else T["seg_inactive"], outline=T["line"])
            self.text(x0 + 16, y0 + 24, f"SLOT {i+1}", 13, T["accent"] if on else T["ink_dim"], True, "w")
            self.readout(x0 + 145, y0 + 66, 258, 40, slot["name"] if slot else "EMPTY")
            if slot and slot.get("from"):
                self.text(x0 + 145, y0 + 104, f"made from {slot['from']}"[:34], 12, T["ink_dim"])
            if slot:
                self.button(x0 + 145, y0 + 150, 258, 52, "LOAD", lambda j=i: self.load_mykit(j), px=18)
            else:
                self.rrect(x0 + 16, y0 + 124, 258, 52, 12, T["well"])
                self.text(x0 + 145, y0 + 150, "NOTHING SAVED YET", 13, T["ink_faint"], True)
            armed = self.armed and self.armed[:2] == ("kit", i) and now - self.armed[2] < 3
            self.button(x0 + 145, y0 + 210, 258, 52, "TAP AGAIN TO REPLACE" if armed else "SAVE HERE",
                        lambda j=i: self.save_mykit(j), accent=True, px=15 if armed else 18)

    def save_mykit(self, i):
        now = time.time()
        slot = self.state.mykits[i]
        if slot and not (self.armed and self.armed[:2] == ("kit", i) and now - self.armed[2] < 3):
            self.armed = ("kit", i, now)
            self.root.after(3100, self.request_redraw)
            return
        self.armed = None
        d = self.audio.engine.drums
        name = f"My Kit {i + 1}"
        src = d.kit_name.rstrip(" *")
        if slot and src == slot.get("name"):
            src = slot.get("from", "")
        pv = self.state.params.val
        knobs = {f"dr.p{j}.{x}": pv[f"dr.p{j}.{x}"] for j in range(1, 17) for x in ("tune", "decay", "level", "pan", "choke")}
        self.state.mykits[i] = {"name": name, "from": src, "pads": [dict(x) for x in d.sources], "knobs": knobs,
                                "saved": time.strftime("%Y-%m-%d %H:%M")}
        d.kit_name = name
        self.state.kit = {"pads": d.sources, "name": name}
        self.state.dirty = True
        self.show_toast(f"KIT SAVED TO SLOT {i + 1}" if self.state.save_kits() else "COULD NOT SAVE - SEE LOG")

    def load_mykit(self, i):
        slot = self.state.mykits[i]
        if not slot:
            return
        d = self.audio.engine.drums
        d.load_sources(slot["pads"], slot["name"])
        for k, v in (slot.get("knobs") or {}).items():  # saved by 1.10 and later: pitch, length, level, pan, choke
            if k in SPECS:
                self.state.params.set_val(k, v)
        self.state.kit = {"pads": d.sources, "name": slot["name"]}
        self.state.dirty = True
        self.play_pattern([[0], [4], [2], [4]], 130)

    # ---------------------------------------------------------------- pad actions (channel 16)
    def rebuild_actions(self):
        self.action_lookup = {(t["t"], t["ch"], t["n"]): aid for aid, t in self.state.actions.items() if t}

    def trig_text(self, trig):
        if not trig:
            return "NOT SET"
        return f"CH {trig['ch']} · {'NOTE' if trig['t'] == 'note' else 'CC'} {trig['n']}"

    def draw_actions(self):
        self.overlay_base("Pad actions", "TAP A CARD, THEN PRESS A PAD OR STEP BUTTON ON THE BEATSTEP PRO TO ASSIGN IT")
        self.button(1150, 172, 160, 56, "CLOSE", self.close_overlay, px=17)
        self.text(34, 172, "Set the BeatStep Pro pads (CNTRL mode) to channel 16. Out of the box: pads 1-16 = notes 36-51.",
                  13, T["ink_dim"], False, "w")
        now = time.time()
        for i, (aid, name) in enumerate(ACTIONS):
            r, c = divmod(i, 5)
            x0, y0 = 34 + c * 244, 205 + r * 98
            learning = self.midi.action_learn == aid
            hot = now - self.action_flash.get(aid, 0) < 0.4
            fill = T["btn_on"] if learning else (T["seg_active"] if hot else T["btn_bg"])
            self.rrect(x0, y0, 232, 88, 12, fill)
            self.text(x0 + 14, y0 + 18, str(i + 1), 12, T["ink_dim"], True, "w")
            self.text(x0 + 116, y0 + 38, name.upper(), 15, T["accent"] if hot else T["btn_text"], True)
            sub = "PRESS A PAD OR STEP NOW" if learning else self.trig_text(self.state.actions.get(aid))
            self.text(x0 + 116, y0 + 66, sub, 12, T["btn_text"] if learning else T["ink_dim"])
            self.hit(x0, y0, 232, 88, lambda a=aid: self.learn_action(a))
        self.text(560, 714, "On the LIVE and LOOP tabs, pads 1-16 play that tab's own pads instead.",
                  12, T["ink_dim"], False, "w")
        self.button(250, 714, 420, 38, "RESET TO CHANNEL 16 DEFAULTS", self.reset_actions, px=14)

    def learn_action(self, aid):
        self.midi.action_learn = None if self.midi.action_learn == aid else aid

    def reset_actions(self):
        self.state.actions = default_actions()
        self.rebuild_actions()
        self.state.dirty = True
        self.show_toast("PAD ACTIONS RESET")

    def run_action(self, aid):
        self.action_flash[aid] = time.time()
        tabs = [t for t in TABS if t != "Setup"]
        if aid in ("rand_s1", "rand_s2", "rand_kit", "next_kit", "prev_kit") and self.kept_block(
                "dr" if "kit" in aid else aid[-2:]):
            pass
        elif aid in ("rand_s1", "rand_s2"):
            pre = aid[-2:]
            self.random_sound(pre)
            self.show_toast(f"SYNTH {pre[1]}: {self.state.preset_name[pre].upper()}", 1.2)
        elif aid in ("next_s1", "next_s2"):
            pre = aid[-2:]
            self.preset_step(pre, 1)
            self.show_toast(f"SYNTH {pre[1]}: {self.state.preset_name[pre].upper()}", 1.2)
        elif aid == "rand_kit" and self.samples.entries:  # Kit Maker: a new kit in the current style
            self.km_new(preview=False)
        elif aid == "rand_kit":
            locked = self._locked_pad_data()
            if self.audio.library().ok():
                self.random_machine()
            else:
                import random as _r
                self.select_kit("factory", _r.randrange(len(kits.KITS)))
                self.show_toast(self.audio.engine.drums.kit_name.upper(), 1.2)
            self._restore_locked_pads(locked)
            if locked:
                self.show_toast("RANDOM KIT (LOCKED PADS KEPT)", 1.2)
        elif aid in ("next_kit", "prev_kit"):
            self.kit_step(1 if aid == "next_kit" else -1)
            self.show_toast(self.audio.engine.drums.kit_name.upper()[:34], 1.2)
        elif aid in ("next_tab", "prev_tab"):
            cur = tabs.index(self.state.page) if self.state.page in tabs else 0
            self.set_page(tabs[(cur + (1 if aid == "next_tab" else -1)) % len(tabs)])
        elif aid.startswith("tab:"):
            self.set_page(aid[4:])
        elif aid.startswith("sec:"):
            self.set_section(aid[4:])
        elif aid == "bounce":
            self.bounce_start()
        elif aid == "grab":
            self.grab_start()
        elif aid == "bounce_send":
            self.bounce_send()
        elif aid == "listen_last":
            self.listen_last()
        elif aid == "beat_back":
            self.beat_back()
        elif aid == "song_start":
            self.song_start()
        elif aid == "song_surprise":
            self.song_start("surprise")
        elif aid == "send_mpc":
            self.send_last_bounce()
        elif aid == "panic":
            self.panic()
        elif aid == "rec":
            self.toggle_rec()
        elif aid == "proj_mutate":
            self.project_mutate("all")
        elif aid == "proj_back":
            self.project_back()
        self.request_redraw()

    # ---------------------------------------------------------------- live tab
    def live_pad(self, i, on):
        """A BeatStep pad on the Live tab (MIDI thread or screen). Holds act at once, taps go to the GUI."""
        eng = self.audio.engine
        (self.live_held.add if on else self.live_held.discard)(i)
        if i < 8:
            eng.punch_fx(i, on)
        elif i == 8:
            eng.set_fill(on)
        elif i == 9:
            self.scene_hold(on)
        elif on:
            self.action_q.append({10: "rec", 11: "rand_s1", 12: "rand_s2", 13: "rand_kit", 14: "grab",
                                  15: "tab:" + self.state.last_tab}[i])
        self.request_redraw()

    def scene_hold(self, on):
        p = self.state.params
        if on:
            src, dst = p.scene_pair()
            if not (p.scenes.get(src) and p.scenes.get(dst)):
                self.show_toast(f"SAVE SCENES {src} AND {dst} FIRST")
                return
            if self.midi.scene_hold is None:
                self.midi.scene_hold = p.norm["sc.morph"]
            p.set_norm("sc.morph", 1.0)
        elif self.midi.scene_hold is not None:
            p.set_norm("sc.morph", self.midi.scene_hold)
            self.midi.scene_hold = None
        self.state.dirty = True

    def save_scene(self, slot):
        p = self.state.params
        p.save_scene(slot)
        self.state.dirty = True
        src, dst = p.scene_pair()
        both = p.scenes.get(src) and p.scenes.get(dst)
        self.show_toast(f"SCENE {slot} SAVED" + (f" · {len(p.scene_keys)} DIFFER" if both else ""))

    def do_undo(self):
        if self.state.params.undo():
            self.state.dirty = True
            self.show_toast("UNDO", 0.8)
        self.request_redraw()

    def do_redo(self):
        if self.state.params.redo():
            self.state.dirty = True
            self.show_toast("REDO", 0.8)
        self.request_redraw()

    def toggle_fullscreen(self):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def load_scene(self, slot):
        sc = self.state.params.scenes.get(str(slot))
        if not isinstance(sc, dict):
            self.show_toast(f"SCENE {slot} EMPTY")
            return
        for k, n in sc.items():
            if k in SPECS:
                self.state.params.set_norm(k, n)
        self.state.dirty = True
        self.show_toast(f"LOADED SCENE {slot}")

    def cycle_scene(self, key):
        """FROM / TO keys: step the scene slot 1 > 2 > ... > 8 > 1."""
        p = self.state.params
        cur = int(round(p.val[key]))
        p.set_val(key, cur % 8 + 1)
        self.state.dirty = True
        src, dst = p.scene_pair()
        self.show_toast(f"MORPH: SCENE {src} > SCENE {dst}", 1.2)

    def set_morph(self, x):
        self.state.params.set_norm("sc.morph", x)
        self.state.dirty = True

    def mini_knob(self, idx, cx, cy, key, r=19, labw=74, prefix=True):
        p = self.state.params
        n = p.shown(key)
        hot = time.time() - self.midi.flash[idx] < 0.35
        X, Y = self.X, self.Y
        self.arc(cx, cy, r + 5, 225, -270, T["ink_faint"], 2)
        self.arc(cx, cy, r + 5, 225, -270 * n, T["accent"], 3)
        self.arc(cx, cy, r + 5, 225, -270 * n, T.get("accent_hi", T["accent"]), 1)
        dome = T.get("knob_hi")
        hot_ring = T["accent"] if hot else T["knob_ring"]
        sprite = None
        if dome and STYLE.get("dome") and skins is not None and getattr(skins, "HAVE", False):
            px = max(8, int(round(2 * r * self.scale)))
            sprite = self.photo(("knob", px, T["knob_face"], dome, T["knob_ring"], bool(hot)),
                                lambda: skins.knob(px, T["knob_face"], dome, hot_ring))
        if sprite is not None:
            self.cv.create_image(X(cx), Y(cy), image=sprite, anchor="center")
        elif dome:
            self.cv.create_oval(X(cx - r * 1.03), Y(cy - r * 0.97 + 3), X(cx + r * 1.03), Y(cy + r * 1.05 + 3),
                                fill=T.get("knob_shadow", "#101114"), outline="")
            for i in range(10):
                t = i / 9.0
                rr = r * (1.0 - 0.58 * t)
                off = -r * 0.09 * t
                self.cv.create_oval(X(cx - rr + off), Y(cy - rr + off), X(cx + rr + off), Y(cy + rr + off),
                                    fill=mix2(T["knob_face"], dome, t), outline="")
            self.cv.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r),
                                outline=hot_ring, width=max(1, int(2 * self.scale)))
        else:
            self.cv.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r), fill=T["knob_face"],
                                outline=hot_ring, width=max(1, int(2 * self.scale)))
        a = math.radians(225 - 270 * n)
        if STYLE.get("pointer"):
            pc = T.get("knob_pointer", T["knob_dot"])
            pimg = None
            if sprite is not None and skins is not None:
                angle = round((-135 + 270 * n) / 3.0) * 3.0
                px2 = max(8, int(round(2 * r * self.scale)))
                pimg = self.photo(("ptr", px2, angle, pc), lambda: skins.pointer(px2, pc, angle))
            if pimg is not None:
                self.cv.create_image(X(cx), Y(cy), image=pimg, anchor="center")
            else:
                ca, sa = math.cos(a), math.sin(a)
                self.cv.create_line(X(cx + r * 0.30 * ca), Y(cy - r * 0.30 * sa),
                                    X(cx + r * 0.82 * ca), Y(cy - r * 0.82 * sa),
                                    fill=pc, width=max(2, round(r * 0.17 * self.scale)), capstyle="round")
                hr = r * 0.17
                self.cv.create_oval(X(cx - hr), Y(cy - hr), X(cx + hr), Y(cy + hr), fill=pc, outline="")
        else:
            dx, dy = cx + (r - 7) * math.cos(a), cy - (r - 7) * math.sin(a)
            self.cv.create_oval(X(dx - 4), Y(dy - 4), X(dx + 4), Y(dy + 4), fill=T["knob_dot"], outline="")
        lab = SPECS[key].label
        lab = {"Build-Up": "Build-up", "Dub Throw": "Dub throw"}.get(lab, lab)
        if key.startswith("lp.t"):
            lab = lab.replace("Track ", "T")
        if key.startswith("dr.p"):
            pn = int(key.split(".")[1][1:]) - 1
            lab = f"{self.audio.engine.drums.names[pn][:7]} {lab.lower()}"
        if prefix and key[:2] in ("s1", "s2") and "Synth" not in lab:
            lab = key[:2].upper() + " " + lab
        big = r > 19
        self.text_fit(cx, cy + r + (17 if big else 15), lab, 13 if big else 11, labw, T["ink"], True)
        self.text_fit(cx, cy + r + (35 if big else 31), SPECS[key].fmt(p.val[key]), 13 if big else 12, labw,
                      T["accent"] if hot else T["ink_dim"])
        self.text(cx - r - 2, cy - r, str(idx + 1), 9, T["ink_faint"], False, "e")
        hw = max(38, labw / 2)
        self.hit(cx - hw, cy - r - 8, 2 * hw, 2 * r + 46, lambda k=key: k, "knob")

    def draw_live(self):
        eng = self.audio.engine
        p = self.state.params
        self.frame(14, 100, 1252, 372, "Live",
                   "BEATSTEP PADS HERE: 1-8 EFFECTS · 9 FILL · 10 HOLD SCENE · 11 REC · 12-14 RANDOM · 15 GRAB · 16 BACK")
        for i, key in enumerate(PAGES["Live"]):
            self.mini_knob(i, 14 + 39 + i * 77.5, 172, key)
        self.text(34, 262, "PUNCH-IN EFFECTS · HOLD", 11, T["accent"], True, "w")
        held = eng.punch.held
        for i, name in enumerate(PUNCH_FX):
            x0 = 30 + i * 153
            on = name in held or i in self.live_held
            self.rrect(x0, 276, 143, 180, 14, T["btn_on"] if on else T["btn_bg"])
            self.text(x0 + 72, 330, name.split(" ")[0].upper(), 22, T["btn_text"], True)
            rest = " ".join(name.split(" ")[1:])
            if rest:
                self.text(x0 + 72, 362, rest.upper(), 18, T["btn_text"], True)
            self.text(x0 + 72, 430, f"PAD {i + 1}", 11, T["btn_text"] if on else T["key_dim"], True)
            self.hit(x0, 276, 143, 180, lambda on, j=i: self.live_pad(j, on), "hold")
        # scenes: 8 snapshots, morph between any two
        y = 482
        self.frame(14, y, 626, 250, "Scenes", "SAVE · CHANGE THINGS · SAVE ANOTHER · MORPH")
        src, dst = p.scene_pair()
        self.button(78, y + 72, 100, 40, f"FROM {src}", lambda: self.cycle_scene("sc.src"), px=14)
        self.button(576, y + 72, 100, 40, f"TO {dst}", lambda: self.cycle_scene("sc.dst"), px=14)
        x0, x1 = 146, 508
        m = p.norm["sc.morph"]
        self.rect(x0, y + 64, x1 - x0, 16, fill=T["well"], outline=T["line"])
        self.rect(x0, y + 64, (x1 - x0) * m, 16, fill=T["accent"])
        hx = x0 + (x1 - x0) * m
        self.rrect(hx - 8, y + 54, 16, 36, 5, T["knob_dot"], outline=T["line"])
        both = p.scenes.get(src) and p.scenes.get(dst)
        info = (f"MORPH {m * 100:.0f}% · {len(p.scene_keys)} SETTINGS MOVE · BEATSTEP KNOB 1" if both
                else f"SAVE SCENES {src} AND {dst} TO MORPH")
        self.text_fit((x0 + x1) / 2, y + 104, info, 11, x1 - x0 + 40, T["ink_dim"], True)
        self.hit(x0 - 10, y + 50, x1 - x0 + 20, 44, self.set_morph, "slider")
        for i in range(1, 9):
            xx = 54 + (i - 1) * 72
            has = p.scenes.get(str(i)) is not None
            self.button(xx, y + 136, 66, 36, f"SAVE {i}", lambda sl=i: self.save_scene(sl), px=11)
            self.button(xx, y + 176, 66, 36, f"LOAD {i}" if has else "EMPTY", lambda sl=i: self.load_scene(sl),
                        on=has, px=11)
        on = self.midi.scene_hold is not None
        self.rrect(40, y + 202, 560, 38, 10, T["btn_on"] if on else T["btn_bg"])
        self.text(320, y + 221, f"HOLD FOR SCENE {dst}  ·  PAD 10", 14, T["btn_text"], True)
        self.hit(40, y + 202, 560, 38, self.scene_hold, "hold")
        # record
        # v2.2: GRAB saves the bars you just played (always listening), RECORD runs until you stop it
        rec = eng.recorder
        self.frame(650, y, 300, 250, "Capture", "")
        gb = self.state.bounce_bars
        waiting = bool(self.grab_wait)
        self.rrect(670, y + 42, 260, 64, 12, T["btn_on"])
        self.text(800, y + 66, "GRABBING..." if waiting else f"GRAB LAST {gb} BAR{'S' if gb > 1 else ''}", 20,
                  T["btn_text"], True)
        self.text(800, y + 91, "WHAT YOU JUST PLAYED · PAD 15", 11, T["btn_text"], True)
        self.hit(670, y + 42, 260, 64, self.grab_start)
        opts = [f"{n} BAR" + ("S" if n > 1 else "") for n in self.BOUNCE_BARS]
        self.seg(670, y + 112, 65, 28, opts, f"{gb} BAR" + ("S" if gb > 1 else ""), self.set_grab_bars, vertical=False)
        # v2.3: bounce the next bars and send them to the MPC, without leaving JAM
        b = eng.bounce
        snd = self.mpc_sender
        saving = any(j.get("send") and j["state"] == "saving" for j in self.bounce_jobs)
        if b:
            bl, busy = self.bounce_short(b), True
        elif saving:
            bl, busy = "SAVING...", True
        elif snd is not None and snd.busy:
            bl, busy = "SENDING TO THE MPC...", True
        else:
            bl, busy = f"● BOUNCE NEXT {gb} BAR{'S' if gb > 1 else ''} + SEND", False
        self.button(800, y + 170, 260, 48, bl, self.bounce_send, on=busy, px=15 if gb > 1 else 16)
        if b and b["state"] == "rec" and b.get("bar_at") is not None:
            frac = min(1.0, max(0, b["got"] - b["bar_at"]) / max(b["need"], 1))
            self.rect(680, y + 186, 240 * frac, 4, fill=T["accent_hi"])
        if rec:
            sec = int(rec.seconds())
            self.button(800, y + 222, 260, 44, f"■ STOP  {sec // 60:02d}:{sec % 60:02d}", self.toggle_rec, on=True, px=16)
        else:
            self.button(734, y + 222, 126, 44, "● RECORD", self.toggle_rec, px=15)
            self.button(866, y + 222, 126, 44, "STEMS: ON" if self.state.rec_stems else "STEMS: OFF",
                        lambda: self.pick_stems("MIX ONLY" if self.state.rec_stems else "MIX + STEMS"), px=13)
        # more
        self.frame(960, y, 306, 250, "More", "")
        on = eng.fill or 8 in self.live_held
        self.rrect(976, y + 50, 274, 70, 12, T["btn_on"] if on else T["btn_bg"])
        self.text(1113, y + 85, "HOLD FOR FILL  ·  PAD 9", 16, T["btn_text"], True)
        self.hit(976, y + 50, 274, 70, lambda on: self.live_pad(8, on), "hold")
        self.button(1113, y + 158, 274, 54, "RESAMPLE TO A PAD", lambda: self.open_overlay(("resample",)), px=15)
        self.button(1113, y + 218, 274, 44, "MY SETUPS", lambda: self.open_overlay(("setups",)), accent=True, px=15)

    def pick_stems(self, label):
        self.state.rec_stems = label == "MIX + STEMS"
        self.state.dirty = True

    def toggle_rec(self):
        eng = self.audio.engine
        if eng.recorder is not None:
            r, eng.recorder = eng.recorder, None
            self.last_rec_folder = r.close()
            self.show_toast("SAVED IN MUSIC > POTENTIALBOX RECORDINGS", 2.5)
            return
        try:
            eng.recorder = Recorder(eng.sr, self.state.rec_stems)
            self.show_toast("RECORDING" + (" MIX + STEMS" if self.state.rec_stems else ""), 1.2)
        except Exception as e:
            log("record failed", e)
            self.show_toast("COULDN'T START RECORDING")

    def open_recordings(self):
        path = self.last_rec_folder or recordings_dir()
        try:
            os.makedirs(path, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(path)
            else:
                self.show_toast(path[-38:])
        except Exception as e:
            log("open folder failed", e)

    # ---------------------------------------------------------------- beats tab
    def apply_engine_state(self, eng):
        self.apply_loop_cfg(eng)
        bp = eng.beats
        if self.state.beat:
            try:
                bp.beat = Beat.from_json(self.state.beat)
            except Exception:
                pass
        bp.mutes = set(self.state.beat_mutes)
        self.arr_sync(bp)
        if self.state.song:
            try:
                bp.parts = partsmod.Song.from_json(self.state.song)
            except Exception as e:  # noqa: BLE001
                log("song restore failed", e)
        bp.parts_mute = set(self.state.song_mute)

    def clock_live(self):
        """True when the tempo comes from the BeatStep (it's sending clock and we're not the master)."""
        return not self.state.clock_master and time.perf_counter() - self.midi.last_clock < 1.0

    def beat_save(self):
        bp = self.audio.engine.beats
        self.state.beat = bp.beat.to_json()
        self.state.beat_mutes = sorted(bp.mutes)
        self.state.dirty = True

    def beat_genre(self, g):
        eng = self.audio.engine
        self.beat_push()
        name, bpm, swing, steps, kit, fill, parts = GENRES[g % len(GENRES)]
        eng.beats.beat = Beat(g, bars=self.state.beat_bars)
        if self.state.beat_kit == "samples" and self.samples.entries:
            self.km_new(kitmaker.GENRE_STYLE.get(name, "CLASSIC"), preview=False, toast=False)
        elif self.state.beat_kit:
            self.select_kit("factory", kit, preview=False)
        if self.state.beat_kit:
            beatsmod.drum_bus(self.state.params, name)   # v2.1: the genre's punch, room, width, tone, drive
        if not self.clock_live():
            eng.bpm = float(bpm)  # with CLOCK OUT on, the BeatStep follows this tempo
        self.beat_save()
        self.show_toast(f"{name.upper()} · {bpm} BPM" + (" · TAP PLAY" if not eng.beats.on and not eng.playing else ""), 1.6)

    def beat_pad(self, i, on):
        eng = self.audio.engine
        bp = eng.beats
        if i == 4:
            eng.set_fill(on)
            (self.live_held.add if on else self.live_held.discard)(("fill",))
            self.request_redraw()
            return
        if not on:
            return
        g = bp.beat.genre
        if i == 0:
            if self.state.clock_master:
                self.action_q.append(("transport",))
                return
            bp.on = not bp.on
            bp.auto = False
            if bp.on and not eng.playing:
                bp.pos = 0.0
        elif i == 1:
            self.beat_push()
            bp.beat = Beat(g, bars=self.state.beat_bars)
            self.beat_save()
        elif i == 2:
            self.action_q.append("beat_back")   # v2.2: was "previous genre" (the genre buttons are on screen)
        elif i == 3:
            self.action_q.append(("genre", (g + 1) % len(GENRES)))
        elif i == 5:
            self.beat_push()
            bp.beat.mutate()
            self.beat_save()
        elif i in (6, 7):
            self.beat_push()
            what = bp.beat.busier() if i == 7 else bp.beat.simpler()
            self.beat_save()
            self.action_q.append(("toast", ("BUSIER: " if i == 7 else "SIMPLER: ") + what.upper() if what else
                                  ("AS BUSY AS IT GETS" if i == 7 else "AS SIMPLE AS IT GETS")))
        elif 8 <= i <= 11:
            grp = GROUP_NAMES[i - 8]
            (bp.mutes.discard if grp in bp.mutes else bp.mutes.add)(grp)
            self.beat_save()
        elif i in (12, 13):
            self.action_q.append(("tempo", 2 if i == 13 else -2))
        elif i == 14:
            self.action_q.append(("send",))
        elif i == 15:
            self.action_q.append("tab:" + self.state.last_tab)
        self.request_redraw()

    # ---------------------------------------------------------------- v2.4: tempo panel (tap + presets)
    TEMPO_PRESETS = (70, 80, 90, 100, 110, 120, 128, 140, 174)

    def toggle_tempo(self):
        if self.overlay and self.overlay[0] == "tempo":
            self.close_overlay()
        else:
            self.taps = []
            self.tap_bpm = None
            self.open_overlay(("tempo",))
        self.request_redraw()

    def set_bpm(self, bpm):
        eng = self.audio.engine
        if self.clock_live():
            self.show_toast("TEMPO COMES FROM THE BEATSTEP · TURN ON CLOCK OUT TO SET IT HERE", 2.5)
            return False
        eng.bpm = float(min(max(round(bpm), 40), 220))
        self.state.dirty = True
        return True

    def tap_tempo(self):
        """Tap in time: the tempo follows from the second tap, using the middle of the last 8 gaps (so one
        late tap doesn't throw it). A pause of 2 seconds starts again."""
        now = time.perf_counter()
        t = self.taps
        if t and now - t[-1] > 2.0:
            t.clear()
        t.append(now)
        del t[:-9]
        self.tap_flash = time.time()
        self.root.after(140, self.request_redraw)
        if len(t) < 2:
            return
        gap = float(np.median(np.diff(t)))
        bpm = 60.0 / max(gap, 1e-3)
        while bpm > 220:
            bpm /= 2
        while bpm < 40:
            bpm *= 2
        self.tap_bpm = int(round(bpm))
        if not self.clock_live():
            self.audio.engine.bpm = float(self.tap_bpm)
            self.state.dirty = True

    def draw_tempo(self):
        eng = self.audio.engine
        live = self.clock_live()
        self.overlay_base("Tempo", "TAP THE BIG KEY IN TIME · OR PICK ONE")
        self.button(1150, 172, 160, 56, "CLOSE", self.close_overlay, px=17)
        # what it is now
        self.rrect(40, 210, 580, 120, 14, T.get("screen", T["well"]))
        self.text(330, 262, f"{eng.bpm:.0f}", 64, T.get("lcd_ink", T["accent"]), True)
        self.text(330, 310, "BPM" + ("  ·  FROM THE BEATSTEP" if live else ""), 15, T.get("lcd_ink", T["accent"]), True)
        # the tap key (fires on press, so the timing is yours)
        lit = time.time() - self.tap_flash < 0.12
        self.rrect(40, 352, 580, 300, 18, T["btn_on"] if lit else T["btn_bg"])
        self.text(330, 470, "TAP", 64, T["btn_text"], True)
        n = len(self.taps)
        if self.tap_bpm and n >= 2:
            sub = f"YOU TAPPED {self.tap_bpm} BPM" + (" · SET IT ON THE BEATSTEP" if live else "") + " · KEEP GOING TO FINE-TUNE"
        else:
            sub = "TAP 4 TIMES, ON THE BEAT"
        self.text(330, 560, sub, 14, T["btn_text"], True)
        self.hit(40, 352, 580, 300, self.tap_tempo)
        # presets and nudges
        self.text(680, 222, "PICK ONE", 12, T["accent"], True, "w")
        for i, b in enumerate(self.TEMPO_PRESETS):
            r, c = divmod(i, 3)
            on = abs(eng.bpm - b) < 0.5
            self.button(772 + c * 186, 278 + r * 84, 174, 72, str(b), lambda v=b: self.set_bpm(v), on=on, px=26)
        self.text(680, 538, "NUDGE", 12, T["accent"], True, "w")
        for i, (lab, fn) in enumerate((("−5", lambda: self.set_bpm(eng.bpm - 5)), ("−1", lambda: self.set_bpm(eng.bpm - 1)),
                                       ("+1", lambda: self.set_bpm(eng.bpm + 1)), ("+5", lambda: self.set_bpm(eng.bpm + 5)))):
            self.button(749 + i * 140, 590, 128, 64, lab, fn, px=24)
        self.button(819, 670, 268, 52, "HALF TIME  ½", lambda: self.set_bpm(eng.bpm / 2), px=16)
        self.button(1099, 670, 268, 52, "DOUBLE  ×2", lambda: self.set_bpm(eng.bpm * 2), px=16)
        if live:
            self.text(330, 690, "The BeatStep sets the tempo now. Turn CLOCK OUT on (BEATS) to set it here.",
                      13, T["ink_dim"], True)

    def beat_tempo(self, d):
        eng = self.audio.engine
        if self.clock_live():
            self.show_toast("TEMPO COMES FROM THE BEATSTEP · TURN ON CLOCK OUT TO SET IT HERE", 2.5)
            return
        eng.bpm = float(min(max(round(eng.bpm) + d, 40), 220))

    def beat_transport(self):
        """PLAY / STOP with CLOCK OUT on: starts and stops the BeatStep and the beat together."""
        eng = self.audio.engine
        bp = eng.beats
        if self.clockout.playing:
            bp.on = False
            bp.auto = False
            self.clockout.stop_transport()
        else:
            bp.on = True
            bp.auto = False
            if not self.clockout.start_transport():
                bp.on = False
                self.show_toast("NO MIDI OUT TO THE BEATSTEP FOUND - IS IT PLUGGED IN?", 2.5)

    def toggle_clock_master(self):
        st = self.state
        if st.clock_master:
            self.clockout.disable()
            st.clock_master = False
            self.show_toast("CLOCK OUT OFF · SET THE BEATSTEP'S SYNC BACK TO INT", 2.5)
        else:
            if not self.clockout.enable():
                self.show_toast("NO MIDI OUT TO THE BEATSTEP FOUND - IS IT PLUGGED IN?", 2.5)
                return
            st.clock_master = True
            self.audio.engine.beats.on = False
            self.show_toast("CLOCK OUT ON · SET THE BEATSTEP'S SYNC TO USB (SYNC BUTTON)", 3.0)
        st.dirty = True

    def beat_send(self):
        bp = self.audio.engine.beats
        if bp.send or self.send_countdown:
            bp.send = None
            self.send_countdown = None
            self.show_toast("SEND CANCELLED")
            return
        if not self.midi.open_out():
            self.show_toast("NO MIDI OUT TO THE BEATSTEP FOUND - IS IT PLUGGED IN?", 2.5)
            return
        bp.midi_out = self.midi.send_drum
        bp.send_done = False
        bp.send = "armed"
        if self.state.clock_master and not self.clockout.playing:
            # we start the BeatStep ourselves: give a few seconds to press REC on it
            self.send_countdown = time.time() + 4.0
            self.show_toast("PRESS REC ON THE BEATSTEP NOW · STARTING IN 4 SECONDS", 3.5)
        elif self.state.clock_master:
            self.show_toast("PRESS REC ON THE BEATSTEP · THE BEAT GOES IN FROM THE NEXT STEP 1", 3.5)
        else:
            self.show_toast("READY: CLEAR THE BEATSTEP'S DRUM PATTERN, THEN PRESS REC + PLAY ON IT", 3.5)

    def beat_tick(self):
        bp = self.audio.engine.beats
        if self.midi.offs:
            self.midi.flush_offs()
        if self.send_countdown and time.time() >= self.send_countdown:
            self.send_countdown = None
            if bp.send == "armed" and not self.clockout.playing:
                bp.on = True
                self.clockout.start_transport()
        if bp.send_done:
            bp.send_done = False
            bp.on = False
            bp.auto = False
            self.show_toast("SENT! THE BEATSTEP HAS THE BEAT - PRESS REC TO STOP RECORDING", 3.5)
        if self.state.page == "Beats" and (bp.on or bp.send or self.audio.engine.playing or self.send_countdown):
            self.request_redraw()

    def run_beat_q(self, item):
        if item[0] == "toast":
            self.show_toast(item[1], 1.8)
        elif item[0] == "transport":
            self.beat_transport()
        elif item[0] == "genre":
            self.beat_genre(item[1])
        elif item[0] == "tempo":
            self.beat_tempo(item[1])
        elif item[0] == "send":
            self.beat_send()
        elif item[0] == "project":
            self.load_project(item[1])
        elif item[0] == "capture":
            self.capture_pad(item[1])

    def beat_cell(self, role, step):
        bp = self.audio.engine.beats
        self.beat_push()
        bp.beat.toggle(role, step)
        self.beat_save()

    # ---------------------------------------------------------------- v2.2: ◀ BACK to the beat before
    BEAT_HIST_MAX = 40

    def beat_push(self):
        """Remember the beat (and the genre's kit, drum bus and tempo) before it changes, for ◀ BACK.
        Safe from the MIDI thread: it only reads and appends."""
        eng = self.audio.engine
        bp = eng.beats
        p = self.state.params
        try:
            snap = {"beat": bp.beat.to_json(), "mutes": sorted(bp.mutes), "bars": self.state.beat_bars,
                    "bpm": eng.bpm, "kit": copy.deepcopy(self.state.kit),
                    "bus": {k: p.norm[k] for k in beatsmod.DRUM_BUS_KEYS if k in p.norm}}
        except Exception as e:  # noqa: BLE001
            log("beat history failed", e)
            return
        self.beat_hist.append(snap)
        del self.beat_hist[:-self.BEAT_HIST_MAX]

    def beat_back(self):
        """Step back to the beat before the last NEW BEAT / MUTATE / SIMPLER / BUSIER / genre / tap.
        If the genre changed, its kit, drum bus and tempo come back too."""
        eng = self.audio.engine
        bp = eng.beats
        if not self.beat_hist:
            self.show_toast("NOTHING TO GO BACK TO")
            return
        snap = self.beat_hist.pop()
        old_genre = bp.beat.genre
        try:
            b = Beat.from_json(snap["beat"])
        except Exception as e:  # noqa: BLE001
            log("beat back failed", e)
            self.show_toast("COULDN'T GO BACK")
            return
        bp.beat = b
        bp.mutes = set(snap.get("mutes", []))
        if snap.get("bars") in BAR_CHOICES:
            self.state.beat_bars = snap["bars"]
        if b.genre != old_genre:
            if snap.get("kit") and snap["kit"] != self.state.kit:
                self.state.kit = snap["kit"]
                try:
                    self.audio.apply_kit(eng)
                except Exception as e:  # noqa: BLE001
                    log("kit back failed", e)
            p = self.state.params
            for k, n in snap.get("bus", {}).items():
                if k in SPECS:
                    p.set_norm(k, n)
            if not self.clock_live() and snap.get("bpm"):
                eng.bpm = float(snap["bpm"])
        self.beat_save()
        left = len(self.beat_hist)
        self.show_toast(f"BACK: {GENRES[b.genre][0].upper()}" + (f" · {left} MORE" if left else ""), 1.2)
        self.request_redraw()

    def draw_beats(self):
        eng = self.audio.engine
        bp = eng.beats
        b = bp.beat
        gname, gbpm, gswing, steps, gkit, _, _ = GENRES[b.genre]
        self.frame(14, 100, 1252, 632, "Beats",
                   "PADS HERE: 1 PLAY · 2 NEW BEAT · 3 ◀ BACK · 4 NEXT GENRE · 5 FILL · 6 MUTATE · 7/8 SIMPLER/BUSIER · 9-12 MUTES · 15 SEND · 16 TAB BACK")
        for i, key in enumerate(PAGES["Beats"]):
            self.mini_knob(i, 14 + 39 + i * 77.5, 172, key)
        # genres
        for g, name in enumerate(GENRE_NAMES):
            r, c = divmod(g, 12)
            x0, y0 = 30 + c * 102, 240 + r * 54
            on = g == b.genre
            self.rrect(x0, y0, 96, 48, 9, T["btn_on"] if on else T["btn_bg"])
            words = name.upper().split(" ")
            if len(words) > 1 and len(name) > 9:
                self.text(x0 + 48, y0 + 16, " ".join(words[:-1]), 11, T["btn_text"], True)
                self.text(x0 + 48, y0 + 32, words[-1], 11, T["btn_text"], True)
            else:
                self.text(x0 + 48, y0 + 24, name.upper(), 12, T["btn_text"], True)
            self.hit(x0, y0, 96, 48, lambda gg=g: self.beat_genre(gg))
        # pattern grid
        roles = sorted(b.grid, key=lambda r: ROLE_PAD[r])
        y0 = 352
        rh = min(34, int(200 / max(len(roles), 1)))
        gx0, gx1 = 140, 1250
        cw = (gx1 - gx0) / b.steps
        cur = bp.step if (bp.on or bp.send or eng.playing) else None
        for j in range(b.steps):
            if j % 4 == 0:
                self.rect(gx0 + j * cw, y0 - 4, cw * 4 - 2, rh * len(roles) + 6, fill=T["well"])
        tsteps = sorted({i for d in getattr(b, "turn", {}).values() for i in d if i >= b.steps - 8})
        if tsteps and b.steps >= 16:
            t0 = min(tsteps)
            self.rect(gx0 + t0 * cw, y0 - 4, (b.steps - t0) * cw - 2, rh * len(roles) + 6, fill=T["seg_inactive"])
        for bar in range(16, b.steps, 16):
            self.rect(gx0 + bar * cw - 2, y0 - 8, 2, rh * len(roles) + 14, fill=T["accent"])
        if cur is not None:
            self.rect(gx0 + cur * cw, y0 - 4, cw - 1, rh * len(roles) + 6, fill=T["seg_active"])
        for i, role in enumerate(roles):
            y = y0 + i * rh
            pad = ROLE_PAD[role]
            muted = any(pad in BEAT_GROUPS[m] for m in bp.mutes)
            self.text(30, y + rh / 2, ROLE_NAME[role][:13], 12, T["ink_faint"] if muted else T["ink"], True, "w")
            s = b.grid[role]
            for j, ch in enumerate(s):
                cx = gx0 + j * cw + cw / 2
                if ch != ".":
                    big = ch in "Xxrt"
                    rad = min(cw, rh) * (0.38 if big else 0.24)
                    col = T["ink_faint"] if muted else (T["accent"] if ch in "Xrt" else (T["ink"] if ch == "x" else T["ink_dim"]))
                    self.cv.create_oval(self.X(cx - rad), self.Y(y + rh / 2 - rad), self.X(cx + rad), self.Y(y + rh / 2 + rad),
                                        fill=col, outline="")
                    if ch in "?;":
                        self.text(cx, y + rh / 2, "?", 9, T["well"], True)
                self.hit(gx0 + j * cw, y, cw, rh, lambda rr=role, jj=j: self.beat_cell(rr, jj))
        # controls
        cy = 594
        running = self.clockout.playing if self.state.clock_master else bp.on
        self.button(95, cy, 130, 60, "STOP" if running else "▶ PLAY", lambda: self.beat_pad(0, True), accent=not running, px=20)
        self.button(250, cy, 160, 60, "NEW BEAT", lambda: self.beat_pad(1, True), accent=True, px=19)
        nb = len(self.beat_hist)
        self.rrect(340, cy - 30, 104, 60, 12, T["btn_bg"])
        self.text(392, cy - (7 if nb else 0), "◀ BACK", 17, T["btn_text"] if nb else T["key_dim"], True)
        if nb:
            self.text(392, cy + 15, f"{nb} STEP{'S' if nb > 1 else ''}", 10, T["key_dim"], True)
        self.hit(340, cy - 30, 104, 60, self.beat_back)
        self.button(518, cy, 128, 60, "NEW ENDING", self.beat_new_ending, px=14)
        self.button(646, cy, 108, 60, "MUTATE", lambda: self.beat_pad(5, True), px=14)
        self.button(760, cy, 100, 60, "SIMPLER", lambda: self.beat_pad(6, True), px=13)
        self.button(866, cy, 92, 60, "BUSIER", lambda: self.beat_pad(7, True), px=13)
        fon = eng.fill or ("fill",) in self.live_held
        self.rrect(922, cy - 30, 118, 60, 12, T["btn_on"] if fon else T["btn_bg"])
        self.text(981, cy - 6, "HOLD FOR", 11, T["btn_text"], True)
        self.text(981, cy + 12, "FILL", 18, T["btn_text"], True)
        self.hit(922, cy - 30, 118, 60, lambda on: self.beat_pad(4, on), "hold")
        if self.send_countdown:
            sl = f"PRESS REC · STARTS IN {max(0, int(self.send_countdown - time.time()) + 1)}"
        else:
            sl = {"armed": "WAITING FOR STEP 1" if self.state.clock_master else "WAITING FOR REC + PLAY",
                  "sending": f"SENDING {bp.sent}/{b.steps}"}.get(bp.send, "SEND TO BEATSTEP")
        self.button(1157, cy, 195, 60, sl, lambda: self.beat_pad(14, True), accent=not bp.send, on=bool(bp.send), px=14)
        cy2 = 664
        for k, grp in enumerate(GROUP_NAMES):
            self.button(76 + k * 96, cy2, 90, 44, ("MUTED " if grp in bp.mutes else "") + grp.upper(),
                        lambda kk=k: self.beat_pad(8 + kk, True), on=grp in bp.mutes, px=11 if grp in bp.mutes else 12)
        live = self.clock_live()
        self.button(456, cy2, 44, 44, "−", lambda: self.beat_tempo(-1), px=20)
        self.readout(534, cy2, 104, 44, f"{eng.bpm:.0f} BPM")
        self.hit(482, cy2 - 22, 104, 44, self.toggle_tempo)
        self.button(612, cy2, 44, 44, "+", lambda: self.beat_tempo(1), px=20)
        self.button(732, cy2, 176, 44, f"LENGTH: {b.steps // 16} BAR{'S' if b.steps > 16 else ''}", self.beat_bars_step,
                    on=b.steps > 16, px=13)
        bk = self.state.beat_kit
        self.button(916, cy2, 176, 44, "GENRE KIT: " + ("SAMPLES" if bk == "samples" else "BUILT-IN" if bk else "OFF"),
                    self.toggle_beat_kit, on=bool(bk), px=12)
        self.button(1086, cy2, 152, 44, "CLOCK OUT: ON" if self.state.clock_master else "CLOCK OUT: OFF",
                    self.toggle_clock_master, on=self.state.clock_master, px=13)
        self.button(1210, cy2, 88, 44, "MIDI FILE", self.export_beat_midi, px=12)
        if bp.send:
            if self.state.clock_master:
                msg = ("PRESS REC ON THE BEATSTEP (EMPTY DRUM PATTERN). POTENTIALBOX STARTS IT AND SENDS THE BEAT ONCE, FROM STEP 1."
                       if bp.send == "armed" else "RECORDING INTO THE BEATSTEP...")
            else:
                msg = ("CLEAR THE BEATSTEP'S DRUM PATTERN, THEN PRESS REC AND PLAY ON IT. THE BEAT IS SENT ONCE, FROM STEP 1."
                       if bp.send == "armed" else "RECORDING INTO THE BEATSTEP... KEEP IT PLAYING")
        else:
            msg = f"{gname.upper()} {gbpm} BPM" + (f" · SWING {gswing}%" if gswing > 50 else "")
            if b.turn_text():
                msg += " · ENDS: " + b.turn_text().upper()
            if b.steps != 16:
                msg += f"  ·  SET THE BEATSTEP'S DRUM LENGTH TO {b.steps} BEFORE SENDING"
            if self.state.clock_master:
                msg += "  ·  CLOCK OUT: BEATSTEP SYNC MUST BE ON USB"
            else:
                msg += "  ·  " + ("TEMPO FROM THE BEATSTEP" if live else "OWN TEMPO")
        self.text(30, 714, msg[:150], 11, T["accent"] if bp.send else T["ink_dim"], bool(bp.send), "w")

    # ---------------------------------------------------------------- projects tab: sounds for the BeatStep genre sets
    def load_project(self, i, take=None, toast=True):
        """Load BeatStep project i's sounds: Synth 1 bass, Synth 2 lead, the genre kit in the sets' drum order,
        and (PROJECT FX on) its effects and tempo. take picks one of its sound choices (NEW SOUNDS)."""
        i %= len(projmod.PROJECTS)
        pr = projmod.PROJECTS[i]
        st = self.state
        bp = self.audio.engine.beats
        if bp.parts is not None and hasattr(self, "song_hist"):   # v2.4: the BeatStep plays the project's parts now (◀ BACK on SONG START undoes)
            self.song_hist.append(self.song_snapshot())
            del self.song_hist[:-20]
            bp.parts = None
            bp.part_release = True
            st.song = None
        if take is None:
            take = st.project_take if st.project == i else 0
        st.project, st.project_take = i, take
        self.mut_pending, self.morph = None, None
        self.mut_count = {"bass": 0, "lead": 0, "drums": 0}
        (bname, bass), (lname, lead), kit = projmod.take(pr, take)
        p = st.params
        keep = st.keep
        if not keep["s1"]:
            p.apply_preset("s1", bass)
            st.preset_name["s1"] = f"{pr['name']} · {bname}"
        if not keep["s2"]:
            p.apply_preset("s2", lead)
            st.preset_name["s2"] = f"{pr['name']} · {lname}"
        if not keep["dr"]:
            self.project_drums(pr, kit)
        if st.project_fx:
            bus = {k: p.norm[k] for k in beatsmod.DRUM_BUS_KEYS if k in p.norm}
            for k in projmod.FX_KEYS:
                p.set_val(k, SPECS[k].default)
            beatsmod.drum_bus(p, pr.get("drums", ""))     # v2.1: the genre's drum bus, then the project's own fx
            for k, v in pr["fx"].items():
                p.set_val(k, v)
            if keep["dr"]:                                # v2.4 KEEP DRUMS: their bus stays as it was
                for k, n in bus.items():
                    p.set_norm(k, n)
            if not self.clock_live():
                self.audio.engine.bpm = float(pr["bpm"])  # with CLOCK OUT on, the BeatStep follows this tempo
        st.dirty = True
        if toast:
            kept = self.kept_text()
            self.show_toast(f"PROJECT {i + 1}: {pr['name'].upper()} · {pr['bpm']} BPM" + (f" · KEPT {kept}" if kept else ""), 1.8)
        self.request_redraw()

    def project_drums(self, pr, kit):
        """The genre kit with its pads moved into the order the genre sets play: 1 kick, 2 clap, 3 snare,
        4 percussion, 5 hat, 6 open hat, 7 rim, 8 shaker."""
        perc = pr["perc"]
        if perc == projmod.COWBELL and self.state.project_kit != "samples":
            pad11 = kits.KITS[int(kit) % len(kits.KITS)]["pads"][projmod.COWBELL][0]
            if not any(w in pad11 for w in ("Cowbell", "Perc", "Clank", "Click", "Agogo", "Anvil")):
                perc = projmod.CLAVE  # this kit keeps a ride on that pad
        order = projmod.set_order(perc)
        d = self.audio.engine.drums
        p = self.state.params
        name = f"{pr['name']} set kit"
        made = False
        if self.state.project_kit == "samples" and self.samples.entries:
            km = self.state.km
            km["style"] = pr["style"]
            pads, _src = kitmaker.make_kit(self.samples, pr["style"], (), self.km_rng, km["scope"], km["one"])
            if self.km_apply(pads, name):
                srcs = [dict(s) for s in d.sources]
                vals = {part: [p.val[f"dr.p{j + 1}.{part}"] for j in range(16)] for part in ("tune", "decay", "level")}
                d.load_sources([srcs[order[t]] for t in range(16)], name)
                for t in range(16):
                    for part in ("tune", "decay", "level"):
                        p.set_val(f"dr.p{t + 1}.{part}", vals[part][order[t]])
                made = True
        if not made:
            d.load_sources([{"factory": int(kit), "pad": order[t]} for t in range(16)], name)
            for t in range(16):
                for part in ("tune", "decay", "level"):
                    k = f"dr.p{t + 1}.{part}"
                    p.set_val(k, SPECS[k].default)
        for t in range(16):
            for part in ("pan", "chance", "cond", "choke"):
                k = f"dr.p{t + 1}.{part}"
                p.set_val(k, SPECS[k].default)
        self.state.kit = {"pads": d.sources, "name": name}
        self.state.dirty = True

    def project_new_sounds(self):
        st = self.state
        if st.project is None:
            self.show_toast("PICK A PROJECT FIRST")
            return
        self.load_project(st.project, (st.project_take + 1) % len(projmod.TAKES), toast=False)
        (bname, _), (lname, _), _ = projmod.take(projmod.PROJECTS[st.project], st.project_take)
        self.show_toast(f"{bname.upper()} + {lname.upper()}"[:44], 1.6)

    def project_step(self, d):
        cur = self.state.project
        self.load_project(0 if cur is None else (cur + d) % len(projmod.PROJECTS))

    def toggle_project_kit(self):
        st = self.state
        if st.project_kit == "samples":
            st.project_kit = True
        elif self.samples.entries:
            st.project_kit = "samples"
        else:
            self.show_toast("NO SAMPLES YET: ADD FOLDERS IN THE KIT MAKER")
            return
        st.dirty = True
        if st.project is not None:
            pr = projmod.PROJECTS[st.project]
            self.project_drums(pr, projmod.take(pr, st.project_take)[2])
            self.play_pattern([[0], [4], [2], [4]], 130)

    def toggle_project_fx(self):
        self.state.project_fx = not self.state.project_fx
        self.state.dirty = True

    # voice: say "project seven", a genre name, "next project", "new sounds"
    def toggle_voice(self):
        v = self.voice
        if v.state in ("starting", "listening"):
            v.stop()
            self.show_toast("MIC OFF")
        else:
            v.start()
            if v.state == "error":
                self.show_toast(friendly_error(v.error), 4.0)
        self.request_redraw()

    def voice_tick(self):
        for ev in self.voice.poll():
            if ev[0] == "ready":
                self.show_toast("LISTENING: SAY \"PROJECT SEVEN\"", 2.0)
            elif ev[0] == "error":
                self.show_toast(friendly_error(ev[1]), 4.0)
            elif ev[0] == "ended" and self.voice.state == "error":
                self.show_toast(friendly_error(self.voice.error), 4.0)
            elif ev[0] == "heard":
                text, conf = ev[1], ev[2]
                self.voice_heard = (text, time.time())
                cmd = projmod.command(text)
                if conf < MIN_CONFIDENCE or not cmd:
                    continue
                kind, arg = cmd
                if kind == "project":
                    self.load_project(arg)
                elif kind == "step":
                    self.project_step(arg)
                elif kind == "take":
                    self.project_new_sounds()
                elif kind == "mic_off":
                    self.voice.stop()
                    self.show_toast("MIC OFF")
                elif kind == "mutate":
                    self.project_mutate(arg)
                elif kind == "back":
                    self.project_back()
                elif kind == "amount":
                    self.set_mut_amount(arg)
                elif kind == "auto":
                    self.state.mut_auto = 8 if arg else 0
                    self.state.dirty = True
                    self.show_toast("AUTO MUTATE EVERY 8 BARS" if arg else "AUTO MUTATE OFF")
            self.request_redraw()

    # mutate: new sounds inside the project's curated ones, landing on the next bar so the track keeps flowing
    def set_mut_amount(self, a):
        self.state.mut_amount = a
        self.state.dirty = True
        self.show_toast(f"MUTATE: {a}", 1.0)

    def cycle_mut_auto(self):
        st = self.state
        st.mut_auto = {0: 8, 8: 16, 16: 0}[st.mut_auto]
        st.dirty = True

    def project_mutate(self, part="all", amount=None, toast=True):
        st = self.state
        if st.project is None:
            self.show_toast("PICK A PROJECT FIRST")
            return
        kp = {"bass": "s1", "lead": "s2", "drums": "dr"}
        if all(st.keep[kp[pt]] for pt in (kp if part == "all" else [part])):
            self.show_toast(("THAT PART IS" if part != "all" else "EVERYTHING IS") + " KEPT · TAP KEEP TO LET IT CHANGE", 2.0)
            return
        eng = self.audio.engine
        self.mut_pending = {"kind": "mutate", "part": part, "amount": amount or st.mut_amount, "bar": eng.bar(),
                            "t": time.time()}
        if not eng.playing:
            self.mutate_tick()
        elif toast:
            self.show_toast(f"MUTATE {'' if part == 'all' else part.upper() + ' '}AT THE NEXT BAR", 1.2)
        self.request_redraw()

    def project_back(self):
        if not self.mut_hist:
            self.show_toast("NOTHING TO GO BACK TO")
            return
        self.mut_pending = {"kind": "back", "bar": self.audio.engine.bar(), "t": time.time()}
        if not self.audio.engine.playing:
            self.mutate_tick()
        else:
            self.show_toast("BACK AT THE NEXT BAR", 1.2)

    def mutate_tick(self):
        eng = self.audio.engine
        st = self.state
        pend = self.mut_pending
        # land on the bar: in the last 16th of the bar (so new drums hit on the one), or once the bar has turned
        if pend and (not eng.playing or eng.bar() != pend["bar"] or eng.tick % 96 >= 90 or time.time() - pend["t"] > 8):
            self.mut_pending = None
            p = st.params
            ls, p.lock_step = p.lock_step, None  # mutations never write step locks
            try:
                if pend["kind"] == "back":
                    self.mut_restore(self.mut_hist.pop())
                else:
                    self.run_mutation(pend["part"], pend["amount"])
            finally:
                p.lock_step = ls
            self.request_redraw()
        m = self.morph
        if m:
            k = min(1.0, (time.time() - m["t0"]) / m["dur"])
            e = k * k * (3 - 2 * k)
            p = st.params
            ls, p.lock_step = p.lock_step, None
            try:
                for key, (a, b) in m["keys"].items():
                    p.set_norm(key, a + (b - a) * e)
            finally:
                p.lock_step = ls
            if k >= 1:
                self.morph = None
            st.dirty = True
        # auto mutate: a MILD change to one part at the start of every 8 or 16 bars
        n = st.mut_auto
        if n and st.project is not None and eng.playing and not self.mut_pending:
            b = eng.bar()
            if b % n == n - 1 and self.auto_block != b // n:
                self.auto_block = b // n
                free = [pt for pt, k in (("bass", "s1"), ("lead", "s2"), ("drums", "dr")) if not st.keep[k]]
                if free:
                    self.project_mutate(random.choice(free), "MILD", toast=False)

    def mut_snapshot(self):
        p = self.state.params
        return {"norm": {k: p.norm[k] for k in SPECS if k.startswith(("s1.", "s2.")) and not k.endswith((".vol", ".mute", ".solo"))},
                "drums": self.km_snapshot(), "count": dict(self.mut_count)}

    def mut_restore(self, snap):
        self.start_morph(snap["norm"])
        self.km_restore(snap["drums"])
        self.mut_count = dict(snap["count"])
        self.show_toast("BACK TO THE LAST SOUNDS", 1.2)

    def start_morph(self, targets):
        """Step settings switch now; everything else glides there over a bar (a moment when stopped)."""
        p = self.state.params
        eng = self.audio.engine
        glide = {}
        for k, n in targets.items():
            sp = SPECS[k]
            if sp.choices or sp.step:
                p.set_norm(k, n)
            elif abs(p.norm[k] - n) > 1e-4:
                glide[k] = (p.norm[k], n)
        dur = min(max(240.0 / max(eng.bpm, 40.0), 0.4), 4.0) if eng.playing else 0.25
        self.morph = {"keys": glide, "t0": time.time(), "dur": dur} if glide else None

    def run_mutation(self, part, amount):
        st = self.state
        pr = projmod.PROJECTS[st.project]
        p = st.params
        rng = self.km_rng
        self.mut_hist.append(self.mut_snapshot())
        while len(self.mut_hist) > 16:
            self.mut_hist.popleft()
        parts = ["bass", "lead", "drums"] if part == "all" else [part]
        kp = {"bass": "s1", "lead": "s2", "drums": "dr"}
        parts = [pt for pt in parts if not st.keep[kp[pt]]]   # v2.4 KEEP
        targets = {}
        for pt in parts:
            if pt in projmod.PART_PRE:
                targets.update(projmod.mutate_synth(SPECS, pr, pt, p.norm, amount, rng))
                self.mut_count[pt] += 1
        if targets:
            self.start_morph(targets)
        if "drums" in parts:
            self.mutate_drums(pr, amount, rng)
            self.mut_count["drums"] += 1
        st.dirty = True
        what = "EVERYTHING" if part == "all" else part.upper()
        self.show_toast(f"{amount} MUTATE: {what}", 1.2)

    def mutate_drums(self, pr, amount, rng):
        d = self.audio.engine.drums
        p = self.state.params
        swap, tweak = projmod.mutate_drums_plan(amount, rng)
        srcs = [dict(s) for s in d.sources]
        tuned = {}
        if swap:
            if self.state.project_kit == "samples" and self.samples.entries:
                order = projmod.set_order(pr["perc"])
                keep = set(range(16)) - {order[t] for t in swap}
                km = self.state.km
                pads, _src = kitmaker.make_kit(self.samples, pr["style"], keep, rng, km["scope"], km["one"])
                for t in swap:
                    pd = pads[order[t]]
                    if pd:
                        srcs[t] = {"file": pd["file"], "label": pd["label"], "type": pd["type"], "src": pd["src"]}
                        tuned[t] = (pd["tune"], pd["decay"])
            else:
                pool = sorted({k for q in projmod.PROJECTS for k in q["kits"]
                               if q is pr or (amount == "WILD" and q["style"] == pr["style"])})
                for t in swap:
                    cur = srcs[t].get("factory")
                    opts = [k for k in pool if k != cur] or pool
                    srcs[t] = {"factory": rng.choice(opts), "pad": srcs[t].get("pad", t)}
                    tuned[t] = projmod.drum_tweak(amount, t, rng)
            d.load_sources(srcs, d.kit_name)
        for t in tweak:
            tuned[t] = projmod.drum_tweak(amount, t, rng)
        for t, (tune, dec) in tuned.items():
            p.set_val(f"dr.p{t + 1}.tune", tune)
            p.set_val(f"dr.p{t + 1}.decay", dec)
        self.state.kit = {"pads": d.sources, "name": d.kit_name}

    def draw_projects(self):
        """JAM > PROJECTS: the jam home. Projects 1-16 laid out like the BeatStep's pads, what's loaded, MUTATE,
        and the tempo / clock / mic / kit switches along the bottom."""
        st = self.state
        eng = self.audio.engine
        # ---- the 16 projects
        self.frame(14, 100, 1252, 232, "Projects", "")
        self.button(1088, 121, 120, 32, "◂ PREVIOUS", lambda: self.project_step(-1), px=13)
        self.button(1198, 121, 92, 32, "NEXT ▸", lambda: self.project_step(1), px=13)
        self.text(1010, 121, "BEATSTEP PADS 1-16 LOAD THEM", 11, T["ink_dim"], False, "e")
        for i, pr in enumerate(projmod.PROJECTS):
            r, c = divmod(i, 8)
            x0, y0 = 30 + c * 153, 146 + r * 90
            on = i == st.project
            self.rrect(x0, y0, 143, 82, 12, T["btn_on"] if on else T["btn_bg"])
            self.text(x0 + 12, y0 + 18, str(i + 1), 18, T["btn_text"], True, "w")
            self.text(x0 + 131, y0 + 18, f"{pr['bpm']} BPM", 11, T["btn_text"] if on else T["key_dim"], True, "e")
            self.text_fit(x0 + 71, y0 + 54, pr["name"].upper(), 18, 128, T["btn_text"], True)
            self.hit(x0, y0, 143, 82, lambda ii=i: self.load_project(ii))
        # ---- what's loaded
        self.frame(14, 342, 760, 226, "Now playing", "")
        self.button(680, 363, 160, 32, "NEW SOUNDS", self.project_new_sounds, px=14)
        if st.project is None:
            self.text(394, 440, "TAP A PROJECT OR PRESS A BEATSTEP PAD", 19, T["ink"], True)
            self.text(394, 474, 'OR TAP TALK AND SAY "PROJECT SEVEN"', 15, T["ink_dim"], True)
            self.text(394, 520, "Synth 1 = bass on Seq 1 · Synth 2 = lead on Seq 2 · drums on the drum sequencer",
                      13, T["ink_faint"])
        else:
            pr = projmod.PROJECTS[st.project]
            (bname, _), (lname, _), kit = projmod.take(pr, st.project_take)
            self.text(34, 406, f"{st.project + 1} · {pr['name'].upper()}", 26, T["ink"], True, "w")
            pend = self.mut_pending
            sub = (f"{pr['bpm']} BPM · {pr['key'].upper()} · SET THE BEATSTEP TO PROJECT {st.project + 1}"
                   if not pend else ("GOING BACK" if pend["kind"] == "back" else f"{pend['amount']} MUTATE")
                   + " AT THE NEXT BAR...")
            self.text(36, 434, sub, 12, T["accent"] if pend else T["ink_dim"], True, "w")
            kname = eng.drums.kit_name if st.project_kit == "samples" else f"{kits.NAMES[int(kit)]} (set order)"
            kp = st.keep   # v2.4: a KEPT part shows what's really playing
            rows = [("SYNTH 1 · BASS", st.preset_name["s1"] if kp["s1"] else bname, "bass", "s1"),
                    ("SYNTH 2 · LEAD", st.preset_name["s2"] if kp["s2"] else lname, "lead", "s2"),
                    ("DRUMS", eng.drums.kit_name if kp["dr"] else kname, "drums", "dr")]
            for j, (lab, val, part, kk) in enumerate(rows):
                y = 452 + j * 38
                self.rrect(30, y, 508, 34, 7, T["seg_inactive"])
                n = self.mut_count.get(part, 0)
                self.text(44, y + 17, lab, 12, T.get("title", T["accent"]), True, "w")
                self.text_fit(190, y + 17, val.upper() + (f"   · MUTATED ×{n}" if n else ""), 15, 340,
                              T["ink"], True, "w")
                self.keep_button(590, y + 17, 96, 34, kk, px=12)
                self.button(698, y + 17, 112, 34, "MUTATE", lambda pt=part: self.project_mutate(pt), px=13)
        # ---- mutate
        self.frame(784, 342, 482, 226, "Mutate", "NEW SOUNDS ON THE NEXT BAR")
        self.button(1025, 418, 450, 66, "MUTATE ALL", lambda: self.project_mutate("all"), accent=True, px=24)
        self.seg(800, 460, 150, 42, projmod.AMOUNTS, st.mut_amount, self.set_mut_amount, vertical=False)
        self.button(905, 536, 210, 42, "◂ BACK", self.project_back, px=15)
        auto = {0: "AUTO: OFF", 8: "AUTO: EVERY 8 BARS", 16: "AUTO: EVERY 16 BARS"}[st.mut_auto]
        self.button(1141, 536, 222, 42, auto, self.cycle_mut_auto, on=bool(st.mut_auto), px=14)
        # ---- play: tempo, clock, mic, kit, fx
        self.frame(14, 578, 1252, 154, "Play", "")
        cy = 650
        self.button(52, cy, 52, 52, "−", lambda: self.beat_tempo(-1), px=22)
        self.readout(140, cy, 112, 52, f"{eng.bpm:.0f} BPM")
        self.hit(84, cy - 26, 112, 52, self.toggle_tempo)
        self.button(228, cy, 52, 52, "+", lambda: self.beat_tempo(1), px=22)
        self.button(390, cy, 210, 52, "CLOCK OUT: ON" if st.clock_master else "CLOCK OUT: OFF",
                    self.toggle_clock_master, on=st.clock_master, px=15)
        listening = self.voice.state in ("starting", "listening")
        mic = {"starting": "MIC STARTING...", "listening": "● LISTENING"}.get(self.voice.state, "🎤 TALK")
        mic = mic if not mic.startswith("🎤") else "TALK (MIC)"
        self.button(620, cy, 230, 52, mic, self.toggle_voice, on=listening, px=16)
        bk = st.project_kit
        self.button(862, cy, 236, 52, "KIT: MY SAMPLES" if bk == "samples" else "KIT: BUILT-IN",
                    self.toggle_project_kit, on=bk == "samples", px=15)
        self.button(1121, cy, 262, 52, "PROJECT FX + TEMPO: " + ("ON" if st.project_fx else "OFF"),
                    self.toggle_project_fx, on=st.project_fx, px=14)
        heard, when = self.voice_heard
        if self.voice.state == "error":
            msg, hot = friendly_error(self.voice.error), True
        elif listening:
            msg, hot = 'SAY "PROJECT SEVEN", A GENRE, "MUTATE", "MUTATE DRUMS", "GO BACK", "NEXT PROJECT", "NEW SOUNDS"', True
            if heard and time.time() - when < 6:
                msg = f'HEARD "{heard.upper()}"  ·  ' + msg
        elif st.clock_master:
            msg, hot = "CLOCK OUT IS ON: THE BEATSTEP FOLLOWS THIS TEMPO (SET ITS SYNC TO USB)", False
        elif self.clock_live():
            msg, hot = "TEMPO COMES FROM THE BEATSTEP. TURN CLOCK OUT ON TO SET IT FROM HERE", False
        else:
            msg, hot = "TURN CLOCK OUT ON AND THE BEATSTEP PLAYS AT EACH PROJECT'S TEMPO", False
        self.text_fit(640, 702, msg, 12, 1200, T["accent"] if hot else T["ink_dim"], True)

    def beat_bars_step(self):
        bp = self.audio.engine.beats
        self.beat_push()
        i = BAR_CHOICES.index(self.state.beat_bars) if self.state.beat_bars in BAR_CHOICES else 1
        self.state.beat_bars = BAR_CHOICES[(i + 1) % len(BAR_CHOICES)]
        bp.beat = Beat(bp.beat.genre, bars=self.state.beat_bars)
        self.beat_save()
        n = self.state.beat_bars
        self.show_toast(f"{n} BAR{'S' if n > 1 else ''} · {bp.beat.steps} STEPS")

    def beat_new_ending(self):
        bp = self.audio.engine.beats
        self.beat_push()
        bp.beat.new_ending()
        self.beat_save()
        self.show_toast("NEW ENDING: " + bp.beat.turn_text().upper())

    # ---------------------------------------------------------------- v2.4: KEEP and SONG START
    KEEP_NAMES = {"dr": "DRUMS", "s1": "SYNTH 1", "s2": "SYNTH 2"}

    def toggle_keep(self, part):
        k = self.state.keep
        k[part] = not k[part]
        self.state.dirty = True
        self.show_toast(f"KEEP {self.KEEP_NAMES[part]}: " + ("ON · NOTHING CHANGES IT FOR YOU" if k[part] else "OFF"), 1.6)
        self.request_redraw()

    def kept_text(self):
        return " + ".join(self.KEEP_NAMES[p] for p in ("dr", "s1", "s2") if self.state.keep[p])

    def kept_block(self, part):
        """True (with a message) when KEEP stops something from changing this part."""
        if self.state.keep.get(part):
            self.show_toast(f"{self.KEEP_NAMES[part]} IS KEPT · TAP KEEP TO LET IT CHANGE", 1.8)
            return True
        return False

    def keep_button(self, cx, cy, w, h, part, px=13):
        on = self.state.keep[part]
        self.button(cx, cy, w, h, ("✓ KEPT" if on else "KEEP"), lambda: self.toggle_keep(part), on=on, px=px)

    def song_snapshot(self):
        eng = self.audio.engine
        bp = eng.beats
        p = self.state.params
        return {"song": bp.parts.to_json() if bp.parts else None, "mute": sorted(bp.parts_mute),
                "beat": bp.beat.to_json(), "bars": self.state.beat_bars, "bpm": eng.bpm,
                "kit": copy.deepcopy(self.state.kit),
                "bus": {k: p.norm[k] for k in beatsmod.DRUM_BUS_KEYS if k in p.norm},
                "synth": {k: p.norm[k] for k in SPECS if k.startswith(("s1.", "s2.")) and not k.endswith((".vol", ".mute", ".solo"))},
                "names": dict(self.state.preset_name)}

    def song_back(self):
        if not self.song_hist:
            self.show_toast("NOTHING TO GO BACK TO")
            return
        snap = self.song_hist.pop()
        eng = self.audio.engine
        bp = eng.beats
        st = self.state
        p = st.params
        bp.parts = partsmod.Song.from_json(snap["song"]) if snap["song"] else None
        bp.parts_mute = set(snap["mute"])
        bp.part_release = True
        st.song, st.song_mute = snap["song"], list(snap["mute"])
        bp.beat = Beat.from_json(snap["beat"])
        st.beat_bars = snap["bars"]
        if snap["kit"] != st.kit:
            st.kit = snap["kit"]
            try:
                self.audio.apply_kit(eng)
            except Exception as e:  # noqa: BLE001
                log("song back kit failed", e)
        for k, n in snap["bus"].items():
            p.set_norm(k, n)
        for k, n in snap["synth"].items():
            p.set_norm(k, n)
        st.preset_name.update(snap["names"])
        if not self.clock_live():
            eng.bpm = float(snap["bpm"])
        self.beat_save()
        self.show_toast("BACK TO THE LAST SONG" + (f" · {len(self.song_hist)} MORE" if self.song_hist else ""), 1.4)
        self.request_redraw()

    def song_sound(self, pre, names):
        """Put one of these presets on a synth (the parts play their own chords, so no chord / arp modes)."""
        lst = PRESETS[pre]
        pick = [(n, v) for n, v in lst if n in names] or [lst[0]]
        name, vals = random.choice(pick)
        p = self.state.params
        p.apply_preset(pre, vals)
        for k, v in (("chord", 0), ("arp", 0), ("glmode", 0)):
            if f"{pre}.{k}" in SPECS and (k != "glmode" or pre == "s2"):
                p.set_val(f"{pre}.{k}", v)
        self.state.preset_name[pre] = name

    def song_start(self, g=None):
        """One tap: a new beat in the genre, a bass line on Synth 1 and chords on Synth 2, all in one key, at the
        genre's tempo, playing. KEEP leaves a part as it is."""
        eng = self.audio.engine
        bp = eng.beats
        st = self.state
        if g is None:
            g = bp.beat.genre
        elif g == "surprise":
            g = random.choice([i for i in range(len(GENRES)) if i != bp.beat.genre])
        g %= len(GENRES)
        gname = GENRES[g][0]
        self.song_hist.append(self.song_snapshot())
        del self.song_hist[:-20]
        st.project = None   # the synths now play the song, not a BeatStep project
        self.mut_pending = None
        if not st.keep["dr"]:
            self.beat_genre(g)
        song = partsmod.Song(gname)
        bp.parts = song
        st.song = song.to_json()
        if not st.keep["s1"]:
            self.song_sound("s1", song.bass_sounds)
        if not st.keep["s2"]:
            self.song_sound("s2", song.pad_sounds)
        st.dirty = True
        running = self.clockout.playing if st.clock_master else bp.on
        if not running:
            if st.clock_master:
                self.beat_transport()
            else:
                bp.on = True
                bp.auto = False
                if not eng.playing:
                    bp.pos = 0.0
        self.show_toast(f"{gname.upper()} · {partsmod.key_name(song.root, song.minor)} · {song.chords_text()}", 2.5)
        self.request_redraw()

    def song_edit(self, what):
        bp = self.audio.engine.beats
        if bp.parts is None:
            self.song_start()
            return
        self.song_hist.append(self.song_snapshot())
        del self.song_hist[:-20]
        s = partsmod.Song.from_json(bp.parts.to_json())   # a copy: the audio thread keeps reading the old one
        if what == "bass":
            if self.kept_block("s1"):
                self.song_hist.pop()
                return
            s.new_bass()
            msg = "NEW BASS LINE"
        elif what == "chords":
            if self.kept_block("s2"):
                self.song_hist.pop()
                return
            s.new_chords()
            msg = "NEW CHORDS: " + s.chords_text()
        else:
            s.transpose(what)
            msg = "KEY: " + partsmod.key_name(s.root, s.minor)
        bp.parts = s
        self.state.song = s.to_json()
        self.state.dirty = True
        self.show_toast(msg, 1.6)
        self.request_redraw()

    def song_mute_toggle(self, part):
        bp = self.audio.engine.beats
        m = set(bp.parts_mute)
        m ^= {part}
        bp.parts_mute = m
        if part in m:
            bp.part_release = True
        self.state.song_mute = sorted(m)
        self.state.dirty = True

    def song_key(self):
        """The key of the song that's playing (for bounce names, e.g. "Am"), or ""."""
        bp = self.audio.engine.beats
        s = bp.parts
        if s is None or not bp.on or len(bp.parts_mute) == 2:
            return ""
        return partsmod.short_key(s.root, s.minor)

    def export_song_midi(self):
        """The song as a .mid file: bass, chords and drums on their own tracks (4 bars), for the MPC or a DAW."""
        if mido is None:
            self.show_toast("MIDI FILES NEED MIDO - RUN THE INSTALLER AGAIN")
            return
        bp = self.audio.engine.beats
        s = bp.parts
        if s is None:
            self.show_toast("TAP SONG START FIRST")
            return
        q = 120
        mid = mido.MidiFile(ticks_per_beat=480)
        names = {"s1": "Bass", "s2": "Chords"}
        for part in ("s1", "s2"):
            tr = mido.MidiTrack()
            mid.tracks.append(tr)
            tr.append(mido.MetaMessage("track_name", name=names[part], time=0))
            if part == "s1":
                tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(self.audio.engine.bpm), time=0))
            ch = max(0, min(15, self.state.ch[part] - 1))
            ev = []
            for st_, pt, nt, vel, ln in s.notes():
                if pt == part:
                    ev.append((st_ * q, 1, nt, vel))
                    ev.append((st_ * q + int(ln * q * 0.88), 0, nt, 0))
            ev.sort(key=lambda e: (e[0], e[1]))
            last = 0
            for at, kind, nt, vel in ev:
                tr.append(mido.Message("note_on" if kind else "note_off", channel=ch, note=nt, velocity=vel, time=at - last))
                last = at
        reps = max(1, s.STEPS // max(bp.beat.steps, 1))
        dmid = self._beat_midi_track([bp.beat.to_json()] * reps)
        if dmid is not None:
            mid.tracks.append(dmid)
        try:
            folder = recordings_dir()
            os.makedirs(folder, exist_ok=True)
            key = partsmod.key_name(s.root, s.minor).replace(" MINOR", "m").replace(" MAJOR", "")
            path = os.path.join(folder, f"PotentialBox Song {s.genre} {self.audio.engine.bpm:.0f}bpm {key} "
                                        f"{time.strftime('%Y-%m-%d %H%M%S')}.mid")
            mid.save(path)
            self.show_toast("SONG MIDI SAVED IN POTENTIALBOX RECORDINGS (BASS, CHORDS, DRUMS)", 2.5)
        except Exception as e:  # noqa: BLE001
            log("song midi failed", e)
            self.show_toast("COULDN'T SAVE THE MIDI FILE")

    def draw_song(self):
        eng = self.audio.engine
        bp = eng.beats
        st = self.state
        s = bp.parts
        self.frame(14, 100, 1252, 632, "Song start", "ONE TAP: A BEAT, A BASS LINE AND CHORDS IN ONE KEY")
        cur = s.genre if s else None
        self.text(30, 150, "TAP A GENRE TO START A SONG IN IT", 12, T["accent"], True, "w")
        for i, gdef in enumerate(GENRES):
            r, c = divmod(i, 12)
            nm = {"Reggae One Drop": "ONE DROP"}.get(gdef[0], gdef[0].upper())
            self.button(81 + c * 102, 186 + r * 52, 96, 46, nm, lambda gi=i: self.song_start(gi), on=gdef[0] == cur,
                        px=11 if len(nm) > 10 else 12)
        cy = 302
        running = self.clockout.playing if st.clock_master else bp.on
        gnow = GENRES[bp.beat.genre][0].upper()
        self.button(250, cy, 440, 64, f"SONG START · {cur.upper() if cur else gnow}", lambda: self.song_start(
            GENRES.index(next(gd for gd in GENRES if gd[0] == cur)) if cur else None), accent=True, px=20)
        self.button(600, cy, 240, 64, "SURPRISE ME", lambda: self.song_start("surprise"), accent=True, px=18)
        self.button(810, cy, 160, 64, "◀ BACK", self.song_back, px=17)
        self.button(1000, cy, 200, 64, "STOP" if running else "▶ PLAY", lambda: self.beat_pad(0, True),
                    accent=not running, px=20)
        self.button(1180, cy, 140, 64, "MIDI FILE", self.export_song_midi, px=14)
        # ---- what's playing
        self.frame(14, 344, 1252, 388, "Now", "KEEP: PROJECTS, MUTATE, RANDOM AND SONG START LEAVE THAT PART ALONE")
        if s is None:
            self.text(30, 430, "No song yet. Tap a genre, or SONG START.", 18, T["ink_dim"], False, "w")
        else:
            self.text(30, 404, partsmod.key_name(s.root, s.minor), 26, T["ink"], True, "w")
            self.button(300, 404, 60, 40, "−", lambda: self.song_edit(-1), px=20)
            self.text(355, 404, "KEY", 12, T["ink_dim"], True)
            self.button(410, 404, 60, 40, "+", lambda: self.song_edit(1), px=20)
            pos = (bp.part_step // 16) % 4 if (running and bp.part_step is not None) else None
            for b_, deg in enumerate(s.prog):
                x0 = 470 + b_ * 196
                on = pos == b_
                self.rrect(x0, 382, 186, 44, 8, T["btn_on"] if on else T["seg_inactive"])
                self.text(x0 + 93, 404, s.chord_name(deg), 18, T["btn_text"] if on else T["ink"], True)
        rows = (("s1", "BASS · SYNTH 1", st.preset_name.get("s1", ""), "NEW BASS LINE", lambda: self.song_edit("bass")),
                ("s2", "CHORDS · SYNTH 2", st.preset_name.get("s2", ""), "NEW CHORDS", lambda: self.song_edit("chords")),
                ("dr", "DRUMS", f"{GENRES[bp.beat.genre][0]} · {eng.drums.kit_name}", "NEW BEAT", lambda: self.beat_pad(1, True)))
        for k, (part, label, what, newl, fn) in enumerate(rows):
            y = 452 + k * 64
            self.rrect(30, y, 640, 54, 8, T["seg_inactive"])
            self.text(46, y + 27, label, 13, T["ink_dim"], True, "w")
            self.text_fit(232, y + 27, what.upper(), 16, 430, T["ink"], True, "w")
            self.button(770, y + 27, 180, 52, newl, fn, px=14)
            if part != "dr":
                muted = part in bp.parts_mute
                self.button(960, y + 27, 160, 52, ("BASS" if part == "s1" else "CHORDS") + (": OFF" if muted else ": ON"),
                            lambda pp=part: self.song_mute_toggle(pp), on=not muted and s is not None, px=14)
            self.keep_button(1150, y + 27, 180, 52, part, px=15)
        self.text(30, 712, "The bass and chords play from here with the beat. If the BeatStep also plays Synth 1 or 2, "
                  "turn BASS or CHORDS off.", 12, T["ink_dim"], False, "w")

    def export_beat_midi(self):
        self.save_midi([self.audio.engine.beats.beat.to_json()], "Beat")

    def toggle_beat_kit(self):
        bk = self.state.beat_kit
        self.state.beat_kit = "samples" if bk is True else False if bk == "samples" else True
        self.show_toast({"samples": "GENRE KITS FROM YOUR SAMPLES", True: "BUILT-IN GENRE KITS",
                         False: "GENRE KIT OFF"}[self.state.beat_kit], 1.4)
        self.state.dirty = True

    # ---------------------------------------------------------------- loop tab
    LOOP_COL = {"rec": "#d9534f", "ending": "#d9534f", "armed": "#d9534f", "play": "#4cae4c", "cued": "#4cae4c",
                "dub": "#e8b73a"}

    def apply_loop_cfg(self, eng):
        lp = eng.looper
        c = self.state.loop_cfg or {}
        lp.sync = bool(c.get("sync", True))
        lp.length = int(c.get("length", 0)) % len(LENGTHS)
        lp.on_bar_start = bool(c.get("on_bar", False))
        for tr, tc in zip(lp.tracks, c.get("tracks", [])):
            tr.src = int(tc.get("src", tr.src)) % len(SOURCES)
            tr.fx = int(tc.get("fx", tr.fx)) % len(FX_TYPES)
            tr.reverse = bool(tc.get("reverse", False))
            tr.speed = int(tc.get("speed", 1)) % len(SPEEDS)

    def save_loop_cfg(self):
        lp = self.audio.engine.looper
        tracks = [dict(src=t.src, fx=t.fx, reverse=t.reverse, speed=t.speed) for t in lp.tracks]
        self.state.loop_cfg = dict(sync=lp.sync, length=lp.length, on_bar=lp.on_bar_start, tracks=tracks)
        self.state.dirty = True

    def loop_pad(self, i, on):
        """A BeatStep pad on the Loop tab (MIDI thread or screen)."""
        lp = self.audio.engine.looper
        if 8 <= i <= 12:
            t = i - 8
            if on:
                lp.cmd("stop", t)
                self.loop_held[t] = time.time()
            else:
                self.loop_held.pop(t, None)
        elif on:
            if i < 5:
                lp.cmd("main", i)
            elif i == 5:
                lp.cmd("undo", lp.last)
            elif i == 6:
                lp.cmd("allstop")
            elif i == 7:
                lp.cmd("recnext")
            elif i == 13:
                self.loop_set("rev", lp.last)
            elif i == 14:
                self.loop_set("speed", lp.last)
            elif i == 15:
                self.action_q.append("tab:" + self.state.last_tab)
        self.request_redraw()

    def loop_tick(self):
        lp = self.audio.engine.looper
        now = time.time()
        for t, t0 in list(self.loop_held.items()):
            if now - t0 > 0.9:
                self.loop_held.pop(t, None)
                lp.cmd("clear", t)
                self.show_toast(f"TRACK {t + 1} CLEARED")
        if lp.toast:
            self.show_toast(lp.toast)
            lp.toast = None
        if self.state.page == "Loop" and any(t.state != "empty" for t in lp.tracks):
            self.request_redraw()

    def loop_set(self, what, i=None):
        lp = self.audio.engine.looper
        tr = lp.tracks[i] if i is not None else None
        # simple per-track settings are plain attributes: set them here so quick taps never get lost
        if what == "src":
            tr.src = (tr.src + 1) % len(SOURCES)
        elif what == "fx":
            tr.fx = (tr.fx + 1) % len(FX_TYPES)
        elif what == "rev":
            tr.reverse = not tr.reverse
        elif what == "speed":
            tr.speed = (tr.speed + 1) % len(SPEEDS)
            lp.cmd("speed", i, tr.speed)  # also drops out of overdub if needed
        if tr is not None:
            lp.last = i
            self.save_loop_cfg()
        elif what == "sync":
            lp.sync = not lp.sync
            self.save_loop_cfg()
        elif what == "length":
            lp.length = (lp.length + 1) % len(LENGTHS)
            self.save_loop_cfg()
        elif what == "onbar":
            lp.on_bar_start = not lp.on_bar_start
            self.save_loop_cfg()
        elif what == "clearall":
            now = time.time()
            if self.armed and self.armed[:1] == ("clearall",) and now - self.armed[1] < 3:
                self.armed = None
                lp.cmd("clearall")
                self.show_toast("ALL TRACKS CLEARED")
            else:
                self.armed = ("clearall", now)
                self.root.after(3100, self.request_redraw)
        self.request_redraw()

    def input_label(self):
        ch = self.audio.in_chans
        if not ch:
            return "INPUT OFF"
        return "IN " + "+".join(str(c + 1) for c in ch)

    def draw_loop(self):
        eng = self.audio.engine
        lp = eng.looper
        now = time.time()
        self.frame(14, 100, 1252, 632, "Loop",
                   "PADS HERE: 1-5 REC / PLAY / DUB · 9-13 STOP (HOLD = CLEAR) · 6 UNDO · 7 ALL STOP · 8 REC NEXT · 16 BACK")
        for i, key in enumerate(PAGES["Loop"]):
            self.mini_knob(i, 14 + 39 + i * 77.5, 172, key)
        for i, tr in enumerate(lp.tracks):
            x0, y0 = 30 + i * 202, 252
            st = tr.state
            col = self.LOOP_COL.get(st)
            self.rrect(x0, y0, 192, 470, 12, T["panel"] if hasattr(T, "get") and "panel" in T else T["well"])
            self.text(x0 + 14, y0 + 22, f"TRACK {i + 1}", 15, T["accent"] if lp.last == i else T["ink"], True, "w")
            blink = st in ("armed", "cued", "ending") and int(now * 3) % 2
            self.text(x0 + 178, y0 + 22, STATE_TEXT.get(st, st.upper()), 13,
                      (col if not blink else T["ink_faint"]) if col else T["ink_dim"], True, "e")
            # loop position
            self.rect(x0 + 14, y0 + 44, 164, 12, fill=T["well"], outline=T["line"])
            pr = lp.progress(tr)
            if pr is not None:
                self.rect(x0 + 14, y0 + 44, 164 * pr, 12, fill=col or T["accent"])
            self.text(x0 + 96, y0 + 74, lp.length_text(tr) or "—", 12, T["ink_dim"])
            # level
            self.rect(x0 + 14, y0 + 90, 164, 5, fill=T["well"])
            self.rect(x0 + 14, y0 + 90, 164 * min(tr.peak, 1.0), 5, fill=T["accent"])
            # main button: shows what a tap does
            nxt = {"empty": "REC", "armed": "CANCEL", "rec": "PLAY", "ending": "...", "play": "DUB", "dub": "PLAY",
                   "stopped": "PLAY", "paused": "PLAY", "cued": "CANCEL"}.get(st, "REC")
            self.rrect(x0 + 14, y0 + 106, 164, 120, 14, col or T["btn_bg"])
            self.text(x0 + 96, y0 + 126, "TAP TO", 10, "#111111" if col else T["key_dim"], True)
            self.text(x0 + 96, y0 + 160, nxt, 30, "#111111" if col else T["btn_text"], True)
            self.text(x0 + 96, y0 + 200, f"PAD {i + 1}", 11, "#111111" if col else T["key_dim"], True)
            self.hit(x0 + 14, y0 + 106, 164, 120, lambda j=i: self.loop_pad(j, True))
            held = i in self.loop_held
            self.rrect(x0 + 14, y0 + 236, 164, 62, 12, T["btn_on"] if held else T["btn_bg"])
            self.text(x0 + 96, y0 + 258, "STOP", 18, T["btn_text"], True)
            self.text(x0 + 96, y0 + 282, f"HOLD = CLEAR · PAD {9 + i}", 10, T["btn_text"] if held else T["key_dim"], True)
            self.hit(x0 + 14, y0 + 236, 164, 62, lambda on, j=i: self.loop_pad(8 + j, on), "hold")
            src = SOURCES[tr.src] if self.audio.in_chans or tr.src == 1 else "PotentialBox"
            self.button(x0 + 96, y0 + 330, 164, 40, ("FROM: " + src).upper()[:22], lambda j=i: self.loop_set("src", j), px=12)
            self.button(x0 + 96, y0 + 376, 164, 40, ("FX: " + FX_TYPES[tr.fx]).upper(), lambda j=i: self.loop_set("fx", j), px=12)
            self.button(x0 + 55, y0 + 422, 82, 40, "REVERSE", lambda j=i: self.loop_set("rev", j), on=tr.reverse, px=11)
            self.button(x0 + 137, y0 + 422, 82, 40, SPEEDS[tr.speed][0].upper() + " SPEED", lambda j=i: self.loop_set("speed", j),
                        on=tr.speed != 1, px=11)
        # right column
        x = 1046
        cx = x + 103
        self.button(cx, 278, 206, 46, self.input_label(), lambda: self.open_overlay(("loopinput",)), accent=not self.audio.in_chans, px=15)
        self.rect(x, 306, 206, 6, fill=T["well"])
        self.rect(x, 306, 206 * min(lp.in_peak, 1.0), 6, fill="#d9534f" if lp.in_peak > 0.98 else T["accent"])
        self.button(cx, 340, 206, 44, "SYNC TO BEATSTEP" if lp.sync else "SYNC OFF", lambda: self.loop_set("sync"), on=lp.sync, px=13)
        self.button(cx, 392, 206, 44, "START: ON THE BAR" if lp.on_bar_start else "START: WHEN I TAP",
                    lambda: self.loop_set("onbar"), px=13)
        self.button(cx, 444, 206, 44, "LENGTH: " + LENGTHS[lp.length][0].upper(), lambda: self.loop_set("length"),
                    on=lp.length > 0, px=13)
        self.button(cx, 504, 206, 50, f"UNDO / REDO · T{lp.last + 1}", lambda: self.loop_pad(5, True), px=14)
        playing = any(t.state in ("play", "dub", "rec", "ending", "cued", "armed") for t in lp.tracks)
        self.button(cx, 560, 206, 50, "ALL STOP" if playing else "ALL PLAY", lambda: self.loop_pad(6, True), px=15)
        armed = self.armed and self.armed[:1] == ("clearall",) and now - self.armed[1] < 3
        self.button(cx, 616, 206, 50, "TAP AGAIN TO CLEAR" if armed else "CLEAR ALL", lambda: self.loop_set("clearall"),
                    accent=armed, px=14)
        self.button(cx, 676, 206, 56, "MY LOOPS", lambda: self.open_overlay(("myloops",)), accent=True, px=16)

    def draw_loop_input(self):
        self.overlay_base("Looper input", "WHICH INPUT ON YOUR AUDIO INTERFACE TO RECORD (MIC, GUITAR, KEYS...)")
        self.button(1150, 172, 160, 56, "CLOSE", self.close_overlay, px=17)
        mx = min(self.audio.max_in, 8)
        opts = [("INPUT OFF", None)]
        opts += [(f"IN {c + 1}", [c]) for c in range(mx)]
        opts += [(f"IN {c + 1}+{c + 2} STEREO", [c, c + 1]) for c in range(0, mx - 1, 2)]
        cur = self.state.loop_input
        for j, (lab, ch) in enumerate(opts):
            r, c = divmod(j, 4)
            x0, y0 = 34 + c * 305, 220 + r * 76
            on = ch == cur
            self.rect(x0, y0, 290, 64, fill=T["seg_active"] if on else T["seg_inactive"], outline=T["line"])
            self.text(x0 + 145, y0 + 32, lab, 17, T["accent"] if on else T["ink"], on)
            self.hit(x0, y0, 290, 64, lambda cc=ch: self.pick_loop_input(cc))
        y = 220 + ((len(opts) + 3) // 4) * 76 + 20
        if mx == 0:
            self.text(40, y, "This audio output has no inputs. In SETUP, pick your interface's ASIO driver, then come back here.",
                      14, T["accent"], True, "w")
            y += 30
        if self.audio.in_error:
            self.text(40, y, self.audio.in_error[:120], 13, "#d9534f", False, "w")
            y += 28
        for line in ("Mono inputs (a mic, a guitar) are heard in both speakers. HEAR INPUT (knob 7) sets how loud you hear it live.",
                     "With a mic, use headphones so the speakers don't feed back. The delay of your interface is made up for, "
                     "so what you record lands in time."):
            self.text(40, y, line, 13, T["ink_dim"], False, "w")
            y += 26

    def pick_loop_input(self, ch):
        self.state.loop_input = ch
        self.state.dirty = True
        self.state.save()
        self.close_overlay()
        self.start_audio()

    # ---------------------------------------------------------------- my loops (folders of WAVs)
    def loops_root(self):
        home = os.path.expanduser("~")
        music = os.path.join(home, "Music")
        return os.path.join(music if os.path.isdir(music) else home, "PotentialBox Loops")

    def loop_slot_dir(self, i):
        return os.path.join(self.loops_root(), f"Loop set {i + 1}")

    def loop_slot_info(self, i):
        try:
            with open(os.path.join(self.loop_slot_dir(i), "loopset.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def draw_my_loops(self):
        self.overlay_base("My loops", "SAVES ALL 5 TRACKS AS WAV FILES IN MUSIC > POTENTIALBOX LOOPS")
        self.button(1150, 172, 160, 56, "CLOSE", self.close_overlay, px=17)
        now = time.time()
        for i in range(SLOTS):
            r, c = divmod(i, 4)
            x0, y0 = 34 + c * 305, 215 + r * 260
            info = self.loop_slot_info(i)
            self.rect(x0, y0, 290, 245, fill=T["seg_inactive"], outline=T["line"])
            self.text(x0 + 16, y0 + 24, f"LOOP SET {i + 1}", 13, T["ink_dim"], True, "w")
            if info:
                n = sum(1 for t in info.get("tracks", []) if t.get("file"))
                self.readout(x0 + 145, y0 + 66, 258, 40, f"{n} TRACK{'S' if n != 1 else ''} · {info.get('bpm', 0):.0f} BPM")
                self.text(x0 + 145, y0 + 104, f"saved {info.get('saved', '')}"[:34], 12, T["ink_dim"])
                self.button(x0 + 145, y0 + 150, 258, 52, "LOAD", lambda j=i: self.load_loops(j), px=18)
            else:
                self.readout(x0 + 145, y0 + 66, 258, 40, "EMPTY")
                self.rrect(x0 + 16, y0 + 124, 258, 52, 12, T["well"])
                self.text(x0 + 145, y0 + 150, "NOTHING SAVED YET", 13, T["ink_faint"], True)
            armed = self.armed and self.armed[:2] == ("loops", i) and now - self.armed[2] < 3
            self.button(x0 + 145, y0 + 210, 258, 52, "TAP AGAIN TO REPLACE" if armed else "SAVE HERE",
                        lambda j=i: self.save_loops(j), accent=True, px=15 if armed else 18)

    def save_loops(self, i):
        lp = self.audio.engine.looper
        if not any(t.has_audio() for t in lp.tracks):
            self.show_toast("NOTHING TO SAVE YET")
            return
        now = time.time()
        if self.loop_slot_info(i) and not (self.armed and self.armed[:2] == ("loops", i) and now - self.armed[2] < 3):
            self.armed = ("loops", i, now)
            self.root.after(3100, self.request_redraw)
            return
        self.armed = None
        d = self.loop_slot_dir(i)
        try:
            os.makedirs(d, exist_ok=True)
            for f in os.listdir(d):
                if f.lower().endswith(".wav") or f == "loopset.json":
                    os.remove(os.path.join(d, f))
            tracks = []
            for t in lp.tracks:
                td = dict(src=t.src, fx=t.fx, reverse=t.reverse, speed=t.speed, vol=self.state.params.norm[f"lp.t{t.i + 1}.vol"])
                if t.has_audio():
                    name = f"Track {t.i + 1}.wav"
                    write_wav(os.path.join(d, name), np.clip(t.buf.copy(), -1, 1), lp.sr)
                    td.update(file=name, idx0=t.idx0)
                tracks.append(td)
            with open(os.path.join(d, "loopset.json"), "w", encoding="utf-8") as f:
                json.dump(dict(saved=time.strftime("%Y-%m-%d %H:%M"), bpm=self.audio.engine.bpm, sr=lp.sr,
                               tracks=tracks), f, indent=1)
            self.show_toast(f"SAVED LOOP SET {i + 1}")
        except Exception as e:
            log("save loops failed", e)
            self.show_toast("COULDN'T SAVE THE LOOPS")

    def load_loops(self, i):
        info = self.loop_slot_info(i)
        if not info:
            return
        from scipy.io import wavfile
        lp = self.audio.engine.looper
        d = self.loop_slot_dir(i)
        data = []
        try:
            for j, td in enumerate(info.get("tracks", [])[:TRACKS]):
                item = {k: td[k] for k in ("src", "fx", "reverse", "speed", "idx0") if k in td}
                if td.get("file"):
                    fs, x = wavfile.read(os.path.join(d, td["file"]))
                    x = x / float(np.iinfo(x.dtype).max) if x.dtype.kind == "i" else x.astype(np.float64)
                    if x.ndim == 1:
                        x = np.stack([x, x], 1)
                    if fs != lp.sr:
                        n = int(len(x) * lp.sr / fs)
                        pos = np.linspace(0, len(x) - 1, n)
                        x = np.stack([np.interp(pos, np.arange(len(x)), x[:, c]) for c in range(2)], 1)
                        if "idx0" in item:
                            item["idx0"] = int(item["idx0"] * lp.sr / fs)
                    item["buf"] = x[:, :2].astype(np.float32)
                if "vol" in td:
                    self.state.params.set_norm(f"lp.t{j + 1}.vol", float(td["vol"]))
                data.append(item)
        except Exception as e:
            log("load loops failed", e)
            self.show_toast("COULDN'T LOAD THOSE LOOPS")
            return
        lp.cmd("load", data)
        bpm = info.get("bpm", 0)
        self.show_toast(f"LOOP SET {i + 1} LOADED · TAP ALL PLAY" + (f" · SAVED AT {bpm:.0f} BPM" if bpm else ""), 2.5)
        self.close_overlay()
        self.root.after(300, lambda: self.save_loop_cfg())

    # ---------------------------------------------------------------- resample
    RS_SOURCES = {"Synth 1": "s1", "Synth 2": "s2", "Both synths": "synths", "FX returns": "fx", "Everything": "all"}
    RS_LENGTHS = {"1/2 bar": 0.5, "1 bar": 1, "2 bars": 2, "4 bars": 4}

    def draw_resample(self):
        eng = self.audio.engine
        self.overlay_base("Resample to a pad", "RECORDS WHAT YOU HEAR, THEN PUTS IT ON A DRUM PAD")
        self.button(1150, 172, 160, 56, "CLOSE", self.close_overlay, px=17)
        self.text(40, 215, "RECORD", 12, T["accent"], True, "w")
        self.seg(40, 232, 200, 52, list(self.RS_SOURCES), self.rs["src"], lambda o: self.rs.update(src=o), vertical=False)
        self.text(40, 318, "LENGTH", 12, T["accent"], True, "w")
        self.seg(40, 335, 200, 52, list(self.RS_LENGTHS), self.rs["len"], lambda o: self.rs.update(len=o), vertical=False)
        self.text(40, 421, "ONTO PAD", 12, T["accent"], True, "w")
        self.button(80, 470, 80, 56, "<", lambda: self.rs_pad(-1), px=22)
        self.readout(300, 470, 330, 56, f"PAD {self.sel_pad + 1} · {eng.drums.names[self.sel_pad][:16]}")
        self.button(520, 470, 80, 56, ">", lambda: self.rs_pad(1), px=22)
        cap = eng.capture
        if cap:
            msg = {"wait": "WAITING FOR THE NEXT BAR...", "rec": "RECORDING...", "done": "SAVING..."}[cap["state"]]
            self.rrect(40, 560, 600, 90, 14, T["btn_on"])
            self.text(340, 605, msg, 22, T["btn_text"], True)
            self.button(820, 605, 240, 70, "CANCEL", self.rs_cancel, px=17)
        else:
            self.button(340, 605, 600, 90, "START", self.rs_start, accent=True, px=26)
        self.text(40, 690, "If the BeatStep is playing, recording starts on the next bar so the loop lines up. "
                  "Stopped: it starts straight away.", 13, T["ink_dim"], False, "w")

    def rs_pad(self, d):
        self.sel_pad = (self.sel_pad + d) % 16

    def rs_cancel(self):
        self.audio.engine.capture = None

    def rs_start(self):
        eng = self.audio.engine
        bars = self.RS_LENGTHS[self.rs["len"]]
        need = int(bars * 4 * 60.0 / max(eng.bpm, 30.0) * eng.sr)
        sync = eng.playing
        eng.capture = dict(src=self.RS_SOURCES[self.rs["src"]], need=need, buf=[], got=0,
                           state="wait" if sync else "rec", bar_at=None if sync else 0, sync=sync, t0=time.time())

    def resample_tick(self):
        eng = self.audio.engine
        cap = eng.capture
        if not cap:
            return
        if cap["state"] == "wait" and (not eng.playing or time.time() - cap["t0"] > 12):
            cap["bar_at"] = 0
            cap["state"] = "rec"
        if cap["state"] != "done":
            return
        eng.capture = None
        x = np.concatenate(cap["buf"])[cap["bar_at"]: cap["bar_at"] + cap["need"]]
        mono = x.mean(axis=1)
        pk = float(np.abs(mono).max()) if len(mono) else 0.0
        if pk < 1e-4:
            self.show_toast("NOTHING HEARD - IS IT PLAYING?")
            return
        mono = mono * (0.9 / pk)
        fade = min(len(mono), int(0.004 * eng.sr))
        mono[-fade:] *= np.linspace(1.0, 0.0, fade)
        try:
            os.makedirs(RESAMPLE_DIR, exist_ok=True)
            label = f"Resample {time.strftime('%H%M%S')}"
            path = os.path.join(RESAMPLE_DIR, f"{label} {time.strftime('%Y-%m-%d')}.wav")
            write_wav(path, mono, eng.sr)
        except Exception as e:
            log("resample save failed", e)
            self.show_toast("COULDN'T SAVE THE RESAMPLE")
            return
        self.pe_assign(path, label)
        self.show_toast(f"PAD {self.sel_pad + 1}: {label.upper()}", 2.0)
        self.close_overlay()

    # ---------------------------------------------------------------- my setups
    def draw_setups(self):
        self.overlay_base("My setups", "A SETUP IS EVERYTHING: BOTH SYNTHS, THE KIT, MIX, FX, STEP LOCKS AND SCENES")
        self.button(1150, 172, 160, 56, "CLOSE", self.close_overlay, px=17)
        now = time.time()
        cur = getattr(self, "setup_loaded", None)
        for i in range(SLOTS):
            r, c = divmod(i, 4)
            x0, y0 = 34 + c * 305, 215 + r * 260
            slot = self.state.setups[i]
            on = cur == i and bool(slot)
            self.rect(x0, y0, 290, 245, fill=T["seg_active"] if on else T["seg_inactive"], outline=T["line"])
            self.text(x0 + 16, y0 + 24, f"SETUP {i+1}", 13, T["accent"] if on else T["ink_dim"], True, "w")
            self.readout(x0 + 145, y0 + 66, 258, 40, slot["name"] if slot else "EMPTY")
            if slot:
                self.text(x0 + 145, y0 + 104, f"saved {slot.get('saved', '')}"[:34], 12, T["ink_dim"])
                self.button(x0 + 145, y0 + 150, 258, 52, "LOAD", lambda j=i: self.load_setup(j), px=18)
            else:
                self.rrect(x0 + 16, y0 + 124, 258, 52, 12, T["well"])
                self.text(x0 + 145, y0 + 150, "NOTHING SAVED YET", 13, T["ink_faint"], True)
            armed = self.armed and self.armed[:2] == ("setup", i) and now - self.armed[2] < 3
            self.button(x0 + 145, y0 + 210, 258, 52, "TAP AGAIN TO REPLACE" if armed else "SAVE HERE",
                        lambda j=i: self.save_setup(j), accent=True, px=15 if armed else 18)

    def save_setup(self, i):
        now = time.time()
        st = self.state
        if st.setups[i] and not (self.armed and self.armed[:2] == ("setup", i) and now - self.armed[2] < 3):
            self.armed = ("setup", i, now)
            self.root.after(3100, self.request_redraw)
            return
        self.armed = None
        p = st.params
        st.setups[i] = {"name": f"Setup {i + 1}", "saved": time.strftime("%Y-%m-%d %H:%M"), "params": dict(p.norm),
                        "kit": json.loads(json.dumps(st.kit)), "preset_name": dict(st.preset_name),
                        "locks": st.locks_json(), "scenes": json.loads(json.dumps(p.scenes)),
                        "beat": self.audio.engine.beats.beat.to_json()}
        self.setup_loaded = i
        self.show_toast(f"SAVED SETUP {i + 1}" if st.save_setups() else "COULD NOT SAVE - SEE LOG")

    def load_setup(self, i):
        st = self.state
        su = st.setups[i]
        if not su:
            return
        self.lock_off()
        p = st.params
        st.load_scenes(su.get("scenes"))
        for k, n in su.get("params", {}).items():
            if k in SPECS and k != "sc.morph":
                p.norm[k] = float(n)
        for k in SPECS:
            p._apply(k)
        p.recompute_macros()
        p.norm["sc.morph"] = float(su.get("params", {}).get("sc.morph", 0.0))
        p._apply("sc.morph")
        p._scene_keys()
        st.load_locks(su.get("locks"))
        if isinstance(su.get("beat"), dict):
            self.audio.engine.beats.beat = Beat.from_json(su["beat"])
            st.beat = su["beat"]
        st.preset_name.update(su.get("preset_name", {}))
        if isinstance(su.get("kit"), dict):
            st.kit = su["kit"]
            self.audio.apply_kit()
        self.audio.engine.panic()
        self.setup_loaded = i
        st.dirty = True
        self.show_toast(f"SETUP {i + 1} LOADED")

    # ---------------------------------------------------------------- step locks
    def toggle_locks(self):
        if self.lock_mode:
            self.lock_off()
        else:
            self.lock_mode = True
            self.lock_sel = None
        self.request_redraw()

    def lock_off(self):
        self.lock_mode = False
        self.lock_sel = None
        p = self.state.params
        p.lock_step = None
        for k in list(p.locks):  # back from hearing the lock to your own setting
            if k in p.norm:
                p._apply(k)
        self.request_redraw()

    def lock_pick_clear(self):
        """Buttons that change many knobs at once work on your settings, not on a step."""
        if self.lock_sel is not None:
            self.lock_sel = None
            self.state.params.lock_step = None

    def lock_pick(self, i):
        self.lock_sel = None if self.lock_sel == i else i
        self.state.params.lock_step = self.lock_sel
        if self.lock_sel is None:
            for k in self.page_keys():
                self.state.params._apply(k)

    def lock_clear(self, scope):
        p = self.state.params
        if scope == "step" and self.lock_sel is not None:
            p.clear_locks(None, self.lock_sel)
            self.show_toast(f"STEP {self.lock_sel + 1} CLEARED")
        elif scope == "page":
            p.clear_locks(self.page_keys())
            self.show_toast("LOCKS ON THIS PAGE CLEARED")
        elif scope == "all":
            p.clear_locks()
            self.show_toast("ALL STEP LOCKS CLEARED")
        self.state.dirty = True

    def draw_locks(self):
        eng = self.audio.engine
        p = self.state.params
        y = 482
        self.frame(14, y, 1252, 250, "Step locks",
                   "TAP A STEP, THEN TURN KNOBS: ONLY THAT STEP CHANGES · LOCKS REPEAT EVERY 16 STEPS WHILE THE BEATSTEP PLAYS")
        keys = self.page_keys()
        for i in range(16):
            x0 = 30 + i * 76
            sel = self.lock_sel == i
            n_all = sum(1 for d in p.locks.values() if i in d)
            n_page = sum(1 for k in keys if i in p.locks.get(k, {}))
            fill = T["btn_on"] if sel else (T["seg_active"] if n_all else T["btn_bg"])
            playing = eng.playing and eng.step == i
            self.rrect(x0, y + 56, 70, 104, 10, fill, outline=T["accent"] if playing else "")
            self.text(x0 + 35, y + 84, str(i + 1), 22, T["btn_text"], True)
            if n_all:
                self.text(x0 + 35, y + 120, f"{n_page} HERE" if n_page else "", 10, T["btn_text"], True)
                self.text(x0 + 35, y + 140, f"{n_all} LOCK{'S' if n_all > 1 else ''}", 10, T["btn_text"] if sel else T["ink_dim"])
            self.hit(x0, y + 56, 70, 104, lambda j=i: self.lock_pick(j))
        tip = (f"STEP {self.lock_sel + 1}: KNOBS NOW SET THIS STEP ONLY" if self.lock_sel is not None
               else "PICK A STEP · TAP IT AGAIN TO GO BACK TO NORMAL KNOBS")
        self.text(30, y + 196, tip, 14, T["accent"], True, "w")
        self.button(700, y + 200, 150, 50, "CLEAR STEP", lambda: self.lock_clear("step"), px=14)
        self.button(862, y + 200, 150, 50, "CLEAR PAGE", lambda: self.lock_clear("page"), px=14)
        self.button(1024, y + 200, 150, 50, "CLEAR ALL", lambda: self.lock_clear("all"), px=14)
        self.button(1186, y + 200, 120, 50, "DONE", self.lock_off, accent=True, px=15)

    # ---------------------------------------------------------------- v2.0: synth sound browser
    BROWSE_COLS, BROWSE_ROWS = 4, 6

    def browse_state(self, pre):
        if not hasattr(self, "_browse"):
            self._browse = {"s1": {"cat": "ALL", "page": 0}, "s2": {"cat": "ALL", "page": 0}}
        return self._browse[pre]

    def browse_list(self, pre):
        """The sounds the browser shows for the chosen category (MY SOUNDS has its own category)."""
        cat = self.browse_state(pre)["cat"]
        if cat == "MINE":
            return [(sd["name"], sd["values"]) for sd in self.state.sounds[pre] if sd]
        return [(n, v) for n, v in PRESETS[pre] if cat == "ALL" or PRESET_CAT[pre].get(n) == cat]

    def browse_cat(self, pre, cat):
        b = self.browse_state(pre)
        b["cat"], b["page"] = cat, 0
        names = [n for n, _ in self.browse_list(pre)]
        cur = self.state.preset_name[pre]
        if cur in names:   # open on the page with the sound that's loaded
            b["page"] = names.index(cur) // (self.BROWSE_COLS * self.BROWSE_ROWS)

    def browse_load(self, pre, name, vals):
        self.state.params.apply_preset(pre, vals)
        self.state.preset_name[pre] = name
        names = [n for n, _ in self.sound_list(pre)]
        if name in names:
            self.state.preset[pre] = names.index(name)
        self.state.dirty = True
        self.test_note(pre)

    def browse_step(self, pre, d):
        """PREV / NEXT inside the category you're looking at."""
        lst = self.browse_list(pre)
        if not lst:
            return
        names = [n for n, _ in lst]
        cur = self.state.preset_name[pre]
        i = (names.index(cur) + d) % len(lst) if cur in names else (0 if d > 0 else len(lst) - 1)
        self.browse_load(pre, *lst[i])
        self.browse_state(pre)["page"] = i // (self.BROWSE_COLS * self.BROWSE_ROWS)

    def browse_page(self, pre, d):
        b = self.browse_state(pre)
        per = self.BROWSE_COLS * self.BROWSE_ROWS
        pages = max(1, -(-len(self.browse_list(pre)) // per))
        b["page"] = (b["page"] + d) % pages

    def draw_browser(self, pre):
        eng = self.audio.engine
        syn = eng.s1 if pre == "s1" else eng.s2
        title = "Synth 1" if pre == "s1" else "Synth 2"
        role = "BASS & MORE · PLAYED BY SEQ 1" if pre == "s1" else "LEADS, KEYS & CHORDS · PLAYED BY SEQ 2"
        self.frame(14, 100, 1252, 372, title + " sounds", f"{role} · CH {self.state.ch[pre]}", led=syn.amp.stage != 0)
        b = self.browse_state(pre)
        cats = PRESET_CATS + ["MINE"]
        # categories
        for i, cat in enumerate(cats):
            y = 150 + i * 35
            on = cat == b["cat"]
            n = len(self.browse_list_for(pre, cat))
            self.rrect(30, y, 150, 31, 7, T["seg_active"] if on else T["seg_inactive"])
            self.text(44, y + 15.5, "MY SOUNDS" if cat == "MINE" else cat, 14,
                      T["seg_active_tx"] if on else T["ink"], True, "w")
            self.text(168, y + 15.5, str(n), 11, T["seg_active_tx"] if on else T["ink_faint"], False, "e")
            self.hit(30, y, 150, 33, lambda c=cat: self.browse_cat(pre, c))
        # the list, on a display
        lst = self.browse_list(pre)
        per = self.BROWSE_COLS * self.BROWSE_ROWS
        pages = max(1, -(-len(lst) // per))
        b["page"] = min(b["page"], pages - 1)
        sx, sy, sw, sh = 196, 150, 806, 306
        glass = T.get("screen", T["well"])
        img = None
        if STYLE.get("glass") and skins is not None and getattr(skins, "HAVE", False):
            pw, ph = max(8, int(round(sw * self.scale))), max(8, int(round(sh * self.scale)))
            img = self.photo(("scr", pw, ph, glass), lambda: skins.screen(pw, ph, glass))
        if img is not None:
            self.cv.create_image(self.X(sx), self.Y(sy), image=img, anchor="nw")
        else:
            self.rect(sx, sy, sw, sh, fill=glass)
        self.rect(sx, sy, sw, sh, outline=T["line"])
        ink = T.get("lcd_ink", T["accent"])
        cw, rh = (sw - 16) / self.BROWSE_COLS, 42
        cur = self.state.preset_name[pre]
        for j, (name, vals) in enumerate(lst[b["page"] * per:(b["page"] + 1) * per]):
            col, row = j % self.BROWSE_COLS, j // self.BROWSE_COLS
            x, y = sx + 8 + col * cw, sy + 8 + row * rh
            if name == cur:
                self.rect(x + 2, y + 2, cw - 4, rh - 4, fill=ink)
            self.text_fit(x + 14, y + rh / 2, name.upper(), 15, cw - 24, T["screen"] if name == cur else ink,
                          name == cur, "w", minpx=10)
            self.hit(x, y, cw, rh, lambda nm=name, v=vals: self.browse_load(pre, nm, v))
        if not lst:
            self.text(sx + sw / 2, sy + sh / 2 - 12, "NO SOUNDS SAVED HERE YET", 17, ink, True)
            self.text(sx + sw / 2, sy + sh / 2 + 16, "Make a sound you like, then tap SAVE SOUND", 13, shade(ink, 0.7))
        # page strip along the bottom of the display
        if pages > 1:
            self.text(sx + sw / 2, sy + sh - 20, f"PAGE {b['page'] + 1} OF {pages}", 12, shade(ink, 0.75), True)
            self.text(sx + 24, sy + sh - 20, "◂ PAGE", 13, ink, True, "w")
            self.text(sx + sw - 24, sy + sh - 20, "PAGE ▸", 13, ink, True, "e")
            self.hit(sx, sy + sh - 40, 180, 40, lambda: self.browse_page(pre, -1))
            self.hit(sx + sw - 180, sy + sh - 40, 180, 40, lambda: self.browse_page(pre, 1))
        # right-hand keys
        rx = 1018
        self.readout(rx + 116, 168, 232, 36, cur[:24])
        self.button(rx + 56, 225, 112, 54, "◂ PREV", lambda: self.browse_step(pre, -1), px=17)
        self.button(rx + 176, 225, 112, 54, "NEXT ▸", lambda: self.browse_step(pre, 1), px=17)
        self.button(rx + 56, 289, 112, 54, "TEST", lambda: self.test_note(pre), px=17)
        self.button(rx + 176, 289, 112, 54, "RANDOM", lambda: self.random_sound(pre), px=17)
        self.button(rx + 116, 353, 232, 54, "SAVE SOUND", lambda: self.open_overlay(("sounds", pre)), px=17)
        self.button(rx + 116, 425, 232, 62, "EDIT SOUND ▸", lambda: self.synth_view(pre, True), accent=True, px=19)
        # knobs: BeatStep knobs 1-16 on this tab
        self.frame(14, 482, 1252, 250, "Knobs", "BEATSTEP PRO: PRESS CNTRL, THEN TURN KNOBS 1-16")
        for i, key in enumerate(self.page_keys()):
            row, col = divmod(i, 8)
            self.mini_knob(i, 14 + 78 + col * 156.5, 560 + row * 96, key, r=23, labw=140, prefix=False)

    def browse_list_for(self, pre, cat):
        if cat == "MINE":
            return [sd for sd in self.state.sounds[pre] if sd]
        return [n for n, _ in PRESETS[pre] if cat == "ALL" or PRESET_CAT[pre].get(n) == cat]

    # ---------------------------------------------------------------- v2.0: CAPTURE > STEMS
    BOUNCE_BARS = (1, 2, 4, 8)

    def bounce_text(self, b):
        bars = b["bars"]
        if b["state"] == "wait":
            return f"BOUNCE {bars} BAR{'S' if bars > 1 else ''}: WAITING FOR THE NEXT BAR"
        if b["state"] == "rec":
            if b.get("bar_at") is None:
                return "BOUNCE: STARTING..."
            done = max(0, b["got"] - b["bar_at"])
            bar = min(bars, 1 + int(done / max(b["need"], 1) * bars))
            return f"BOUNCING BAR {bar} OF {bars}"
        return "SAVING STEMS..."

    def bounce_short(self, b):
        """v2.3: the bounce's progress in a few words, for the JAM key."""
        if b["state"] == "wait":
            return "WAITING FOR THE BAR · STOP"
        if b["state"] == "rec" and b.get("bar_at") is not None:
            done = max(0, b["got"] - b["bar_at"])
            bar = min(b["bars"], 1 + int(done / max(b["need"], 1) * b["bars"]))
            return f"BOUNCING {bar} OF {b['bars']} · STOP"
        return "SAVING..."

    def bounce_send(self):
        """v2.3 JAM: BOUNCE + SEND. Bounces the next bars, then sends them to the MPC (whatever AUTO-SEND says).
        Tapped again while it's bouncing, it stops."""
        if self.audio.engine.bounce:
            self.bounce_cancel()
            self.show_toast("BOUNCE STOPPED")
            return
        self.bounce_start(send=True)

    def bounce_start(self, bars=None, send=False):
        eng = self.audio.engine
        if eng.bounce:
            self.show_toast("ALREADY BOUNCING - TAP CANCEL TO STOP")
            return
        bars = bars or self.state.bounce_bars
        need = int(bars * 4 * 60.0 / max(eng.bpm, 30.0) * eng.sr)
        sync = eng.playing
        eng.bounce = dict(bars=bars, bpm=eng.bpm, need=need, buf=[], got=0, sync=sync, t0=time.time(),
                          state="wait" if sync else "rec", bar_at=None if sync else 0, send=send)
        if not sync:
            self.show_toast("NOT PLAYING: RECORDING NOW (PLAY THE BEATSTEP TO START ON A BAR)", 2.5)

    def bounce_cancel(self):
        if self.audio.engine.bounce:
            self.audio.engine.bounce = None
            self.show_toast("BOUNCE CANCELLED")

    def save_capture(self, get_parts, bpm, bars, silent_msg, lead="SAVED", send=False, key=""):
        """Save a bounce or a grab as stems in Music > PotentialBox Loops (in the background), then list it
        under YOUR BOUNCES and auto-send it to the MPC if that's on."""
        eng = self.audio.engine
        pr = self.state.project
        what = projmod.NAMES[pr] if pr is not None else "Jam"
        if self.song_key():   # v2.4: a SONG START is playing: name it after its genre
            what = self.audio.engine.beats.parts.genre
        taken = {j["name"] for j in self.bounce_jobs}
        name = capture.bounce_name(what, bpm, bars, key)
        while name in taken:   # two saving at once: the take number isn't on disk yet
            n = int(name.rsplit(" ", 1)[1]) + 1
            name = f"{name.rsplit(' ', 1)[0]} {n:02d}"
        job = {"state": "saving", "name": name, "lead": lead, "send": send}
        self.bounce_jobs.append(job)
        self.bounce_job = job

        def work():
            try:
                parts = get_parts()
                mix = parts["mix"]
                if not len(mix) or float(np.max(np.abs(mix))) < capture.SILENT:
                    job.update(state="error", msg=silent_msg)
                    return
                folder, files = capture.save_bounce(parts, eng.sr, name)
                job.update(state="saved", folder=folder, files=files)
            except Exception as e:  # noqa: BLE001
                log("bounce save failed", traceback.format_exc())
                job.update(state="error", msg=f"COULDN'T SAVE THE STEMS ({e.__class__.__name__})")
        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- v2.2: GRAB the last bars you played
    def grab_start(self, bars=None):
        """Save the bars you've just played: the engine always keeps the last 34 seconds of the mix and
        every stem. It snaps to the nearest bar line: early in a bar it takes the bars before it, later in
        a bar it waits for the bar to finish and includes it."""
        eng = self.audio.engine
        bars = bars or self.state.bounce_bars
        if self.grab_wait:
            self.show_toast("ALREADY GRABBING - JUST A MOMENT")
            return
        first, now = eng.hist_room()
        if now - first < eng.sr * 0.5:
            self.show_toast("NOTHING PLAYED YET")
            return
        bar = 4 * 60.0 / max(eng.bpm, 30.0) * eng.sr
        marks = [m for m in list(eng.hist_marks) if m <= now]
        last = marks[-1] if marks else None
        if last is not None and now - last <= bar * 1.5:   # bars are running (BeatStep clock or the beat player)
            if now - last <= bar * 0.5:
                self.grab_finish(bars, last)
            else:
                self.grab_wait = {"bars": bars, "after": last, "t0": time.time(), "secs": (bar - (now - last)) / eng.sr}
                self.show_toast("GRAB: FINISHING THIS BAR...", 1.0)
        else:
            self.grab_finish(bars, now, on_bar=False)
        self.request_redraw()

    def grab_poll(self):
        g = self.grab_wait
        if not g:
            return
        eng = self.audio.engine
        marks = list(eng.hist_marks)
        if marks and marks[-1] > g["after"] and marks[-1] <= eng.hist_room()[1]:
            self.grab_wait = None
            self.grab_finish(g["bars"], marks[-1])
        elif time.time() - g["t0"] > g["secs"] + 0.6:   # the clock stopped: take it up to now
            self.grab_wait = None
            self.grab_finish(g["bars"], eng.hist_room()[1], on_bar=False)
        self.request_redraw()

    def grab_finish(self, bars, end, on_bar=True):
        eng = self.audio.engine
        bpm = eng.bpm
        pre = int(0.003 * eng.sr) if on_bar else 0
        end -= pre   # 3 ms early, so the downbeat's attack (and any humanize) is at the start, not the end
        first, _ = eng.hist_room(pre)
        got = bars
        while got > 1 and int(got * 4 * 60.0 / max(bpm, 30.0) * eng.sr) > end - first:
            got //= 2
        need = int(got * 4 * 60.0 / max(bpm, 30.0) * eng.sr)
        parts = eng.hist_cut(end - need, end, pre) if need <= end - first else None
        if parts is None:
            self.show_toast("PLAY A WHOLE BAR FIRST")
            return
        lead = "GRABBED" if got == bars else f"ONLY {got} BAR{'S' if got > 1 else ''} SO FAR · GRABBED"
        self.save_capture(lambda: parts, bpm, got, f"NOTHING PLAYED IN THE LAST {got} BAR{'S' if got > 1 else ''}", lead,
                          key=self.song_key() or eng.key_between(end - need, end))
        self.show_toast(f"GRABBING THE LAST {got} BAR{'S' if got > 1 else ''}...", 1.2)

    def set_grab_bars(self, label):
        self.state.bounce_bars = int(label.split()[0])
        self.state.dirty = True

    def bounce_tick(self):
        eng = self.audio.engine
        b = eng.bounce
        if b:
            if b["state"] == "wait" and (not eng.playing or time.time() - b["t0"] > 12):
                b["state"], b["bar_at"] = "rec", 0
            self.request_redraw()   # the display at the top shows the bounce on every screen
            if b["state"] == "done":
                eng.bounce = None
                self.save_capture(lambda: bounce_stems(b), b["bpm"], b["bars"], "NOTHING HEARD - IS IT PLAYING?",
                                  send=b.get("send", False),
                                  key=self.song_key() or eng.key_between(eng.samples - b["need"], eng.samples))
        self.grab_poll()
        for job in list(self.bounce_jobs):
            if job["state"] not in ("saved", "error"):
                continue
            self.bounce_jobs.remove(job)
            if job["state"] == "error":
                self.show_toast(job["msg"], 2.5)
            else:
                self.state.bounces = ([job["folder"]] + [f for f in self.state.bounces if f != job["folder"]])[:12]
                self.state.dirty = True
                self.show_toast(job.get("lead", "SAVED") + f" {len(job['files'])} FILES: {job['name'].upper()}", 2.5)
                if self.state.bounce_mpc or job.get("send"):
                    self.send_bounce(job["folder"])
            self.request_redraw()
        snd = self.mpc_sender
        if snd is not None and (snd.busy or snd.status != getattr(self, "_snd_seen", None)):
            self._snd_seen = snd.status
            self.request_redraw()
        if snd is not None and not snd.busy and not getattr(snd, "announced", True):
            snd.announced = True   # v2.3: say how it went, on whatever screen you're on
            if snd.error:
                self.show_toast("MPC: " + snd.error.upper()[:70], 3.5)
            elif snd.copied:
                self.sent_folders.add(snd.folder)
                self.show_toast(f"ON THE MPC ✓  {os.path.basename(snd.folder).upper()}", 2.5)
            if snd.error:
                self.send_queue.clear()   # the MPC isn't reachable: don't keep trying
            elif self.send_queue:
                self.send_bounce(self.send_queue.pop(0))
        au = self.audio.engine.audition
        if au is not None and self.state.page == "Capture" and time.time() - self._listen_draw > 0.1:
            self._listen_draw = time.time()   # move the playhead
            self.request_redraw()

    def send_bounce(self, folder):
        if self.mpc_sender is not None and self.mpc_sender.busy:
            if folder and folder != getattr(self.mpc_sender, "folder", None) and folder not in self.send_queue:
                self.send_queue.append(folder)   # v2.3: goes when the one before it is done
                self.show_toast("SENDS NEXT, AFTER THE ONE GOING NOW")
            else:
                self.show_toast("SENDING IT NOW")
            return
        if not folder or not os.path.isdir(folder):
            self.show_toast("NO BOUNCE TO SEND YET")
            return
        snd = self.mpc_sender = MpcSend(None, host=self.state.mpc_host or None)
        snd.busy = True
        snd.announced = False
        snd.status = "Connecting to the MPC..."
        snd.folder = folder
        threading.Thread(target=snd.send, args=(folder,), daemon=True).start()

    # ---------------------------------------------------------------- v2.3: ▶ listen before you send
    def listen(self, folder):
        """Loop a bounce's mix (tap again to stop). It's heard only: never recorded, grabbed or bounced."""
        eng = self.audio.engine
        au = eng.audition
        if au is not None and not au["stop"] and au["key"] == folder:
            eng.audition_stop()
            self.request_redraw()
            return
        path = capture.mix_file(folder) if folder and os.path.isdir(folder) else None
        if not path:
            self.show_toast("THAT BOUNCE HAS GONE FROM ITS FOLDER")
            return
        try:
            x = capture.read_wav(path, eng.sr)
        except Exception as e:  # noqa: BLE001
            log("listen failed", path, e)
            self.show_toast("COULDN'T PLAY THAT ONE")
            return
        if not len(x):
            self.show_toast("THAT BOUNCE IS EMPTY")
            return
        eng.audition_play(x, folder)
        self.request_redraw()

    def listen_last(self):
        self.listen(next((f for f in self.state.bounces if os.path.isdir(f)), None))

    def listen_stop(self):
        self.audio.engine.audition_stop()

    def send_last_bounce(self):
        last = next((f for f in self.state.bounces if os.path.isdir(f)), None)
        self.send_bounce(last)

    def open_folder(self, path):
        try:
            os.makedirs(path, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(path)
            else:
                self.show_toast(path[-40:])
        except Exception as e:  # noqa: BLE001
            log("open folder failed", e)

    def capture_pad(self, i):
        if i < 4:
            self.state.bounce_bars = self.BOUNCE_BARS[i]
            self.bounce_start(self.BOUNCE_BARS[i])
        elif i == 4:
            self.send_last_bounce()
        elif i == 5:
            self.toggle_rec()
        elif i == 6:
            self.bounce_cancel()
        elif i == 7:
            self.grab_start()
        elif i == 8:
            self.listen_last()
        elif i == 9:
            self.bounce_send()
        elif i == 15:
            self.set_page(self.state.last_tab)
        self.request_redraw()

    def set_bounce_bars(self, label):
        self.state.bounce_bars = int(label.split()[0])
        self.state.dirty = True

    def toggle_bounce_mpc(self):
        self.state.bounce_mpc = not self.state.bounce_mpc
        self.state.dirty = True

    def draw_capture(self):
        eng = self.audio.engine
        bars = self.state.bounce_bars
        secs = bars * 4 * 60.0 / max(eng.bpm, 30.0)
        # ---- bounce
        self.frame(14, 100, 830, 400, "Bounce stems", "PADS: 1-4 BOUNCE 1/2/4/8 · 5 SEND · 8 GRAB · 9 LISTEN · 10 BOUNCE + SEND")
        self.text(36, 160, "LENGTH", 12, T.get("title", T["accent"]), True, "w")
        opts = [f"{n} BAR" + ("S" if n > 1 else "") for n in self.BOUNCE_BARS]
        for i, o in enumerate(opts):
            on = self.BOUNCE_BARS[i] == bars
            self.rrect(36 + i * 196, 174, 186, 56, 10, T["btn_on"] if on else T["btn_bg"])
            self.text(36 + i * 196 + 93, 202, o, 21, T["btn_text"], True)
            self.hit(36 + i * 196, 174, 186, 56, lambda o=o: self.set_bounce_bars(o))
        b = eng.bounce
        if b:
            self.rrect(36, 250, 600, 104, 14, T["well"])
            self.text(336, 283, self.bounce_text(b), 20, T.get("lcd_ink", T["accent"]), True)
            frac = 0.0
            if b["state"] == "rec" and b.get("bar_at") is not None:
                frac = min(1.0, max(0, b["got"] - b["bar_at"]) / max(b["need"], 1))
            self.rect(60, 316, 552, 16, fill=shade(T["well"], 1.3))
            self.rect(60, 316, 552 * frac, 16, fill=T["accent"])
            for k in range(1, b["bars"]):
                self.cv.create_line(self.X(60 + 552 * k / b["bars"]), self.Y(314), self.X(60 + 552 * k / b["bars"]),
                                    self.Y(334), fill=T["bg"])
            self.button(728, 302, 180, 104, "CANCEL", self.bounce_cancel, px=20)
        else:
            self.button(280, 302, 488, 104, f"●  BOUNCE NEXT {bars} BAR" + ("S" if bars > 1 else ""),
                        self.bounce_start, accent=True, px=26)
            self.button(669, 302, 274, 104, "GRABBING..." if self.grab_wait else f"GRAB LAST {bars} BAR" + ("S" if bars > 1 else ""),
                        self.grab_start, accent=True, px=20)
        self.text(36, 384, "YOU GET", 12, T.get("title", T["accent"]), True, "w")
        self.text(110, 384, "MIX  +  DRUMS  +  SYNTH 1  +  SYNTH 2  +  FX  +  LOOPER   (silent parts are left out)",
                  14, T["ink"], False, "w")
        self.text(36, 418, f"{bars} bar{'s' if bars > 1 else ''} at {eng.bpm:.0f} BPM = {secs:.1f} seconds. Every file is "
                  "exactly that long, so they loop.", 14, T["ink_dim"], False, "w")
        self.text(36, 446, "BOUNCE records the next bars (from the next bar line). GRAB saves the bars you just played.",
                  14, T["ink_dim"], False, "w")
        self.text(36, 474, "Saved in Music > PotentialBox Loops, named with the tempo, key and a take number.", 14, T["ink_dim"], False, "w")
        # ---- MPC
        self.frame(854, 100, 412, 400, "Send to MPC", "OVER WI-FI, LIKE MPC TOOLS")
        snd = self.mpc_sender
        host = self.state.mpc_host or mpc_host_guess()
        self.readout(1060, 172, 376, 40, host if host else "MPC ADDRESS: OPEN MPC TOOLS ONCE", "")
        self.button(1060, 242, 376, 64, "SEND LAST BOUNCE", self.send_last_bounce, px=20,
                    on=bool(snd and snd.busy))
        self.button(1060, 318, 376, 56, "AUTO-SEND: " + ("ON" if self.state.bounce_mpc else "OFF"),
                    self.toggle_bounce_mpc, on=self.state.bounce_mpc, px=17)
        msg = (snd.status if snd else "") or "Every bounce can go straight to the MPC's SD card, in PotentialBox Loops."
        col = "#ff8a6a" if (snd and snd.error) else T["ink"]
        for k, ln in enumerate(self.wrap(msg, 46)[:3]):
            self.text(872, 384 + k * 22, ln, 14, col, False, "w")
        self.text(872, 470, "Uses MPC TOOLS' SSH login and its saved MPC address.", 12, T["ink_faint"], False, "w")
        # ---- recent bounces + recording
        self.frame(14, 510, 1252, 222, "Your bounces", "▶ LISTEN FIRST · TAP A NAME TO OPEN ITS FOLDER")
        recent = [f for f in self.state.bounces if os.path.isdir(f)][:4]
        if not recent:
            self.text(36, 590, "Nothing yet. Play something, then tap GRAB or BOUNCE.", 16, T["ink_dim"], False, "w")
        au = eng.audition
        for k, f in enumerate(recent):
            y = 556 + k * 42
            nfiles = len([x for x in os.listdir(f) if x.lower().endswith(".wav")]) if os.path.isdir(f) else 0
            playing = au is not None and not au["stop"] and au["key"] == f
            self.button(60, y + 18, 60, 36, "■" if playing else "▶", lambda p=f: self.listen(p), on=playing, px=17)
            self.rrect(98, y, 592, 36, 7, T["btn_on"] if playing else T["seg_inactive"])
            if playing:
                frac = au["pos"] / max(len(au["x"]), 1)
                self.rect(104, y + 30, 580 * frac, 3, fill=T["accent_hi"])
            ink = T["btn_text"] if playing else T["ink"]
            self.text_fit(112, y + 18, os.path.basename(f).upper(), 15, 450, ink, True, "w")
            self.text(676, y + 18, f"{nfiles} FILES", 12, ink if playing else T["ink_dim"], False, "e")
            self.hit(98, y, 592, 38, lambda p=f: self.open_folder(p))
            sending = bool(snd and snd.busy and getattr(snd, "folder", None) == f)
            sl = "SENDING..." if sending else ("SENT ✓" if f in self.sent_folders else "SEND")
            self.button(770, y + 18, 130, 34, sl, lambda p=f: self.send_bounce(p), on=sending, px=14)
        rec = eng.recorder is not None
        self.button(1078, 592, 340, 58, "■ STOP RECORDING" if rec else "● RECORD (ANY LENGTH)",
                    self.toggle_rec, on=rec, px=17)
        self.button(966, 662, 112, 52, "OPEN LOOPS", lambda: self.open_folder(capture.loops_dir()), px=12)
        self.button(1078, 662, 104, 52, "RECORDINGS", self.open_recordings, px=12)
        self.button(1190, 662, 112, 52, "RESAMPLE PAD", lambda: self.open_overlay(("resample",)), px=12)
        self.text(1078, 708, "RECORD saves mix + stems until you stop it", 11, T["ink_faint"])

    def draw_tabs(self):
        """The five big section keys along the bottom, each with its LED."""
        self.rect(0, 742, W, 58, fill=T["bg"])
        self.cv.create_line(self.X(0), self.Y(742), self.X(W), self.Y(742), fill=T["line"])
        cur = SECTION_OF.get(self.state.page, "JAM")
        gap, x0 = 12, 24
        kw = (W - 2 * x0 - gap * (len(SECTIONS) - 1)) / len(SECTIONS)
        for i, (sec, _subs) in enumerate(SECTIONS):
            x = x0 + i * (kw + gap)
            on = sec == cur
            self.rrect(x, 749, kw, 42, 10, T["btn_on"] if on else T["btn_bg"])
            lx = x + 26
            self.cv.create_oval(self.X(lx - 6), self.Y(770 - 6), self.X(lx + 6), self.Y(770 + 6),
                                fill=T["accent_hi"] if on else "#4a463e", outline=shade(T["btn_text"], 1.0))
            self.text(x + kw / 2 + 10, 770, sec, 20, T["btn_text"], True)
            self.hit(x, 744, kw, 54, lambda sc=sec: self.set_section(sc))

    def draw_setup(self):
        # audio
        self.frame(14, 100, 820, 470, "Audio output", "ASIO = LOWEST LAG. NO ASIO DRIVER? TRY WASAPI EXCLUSIVE")
        devs = self.audio.devices()
        cur = self.state.device or {}
        rows = 7
        self.dev_scroll = max(0, min(self.dev_scroll, max(0, len(devs) - rows)))
        for j, d in enumerate(devs[self.dev_scroll:self.dev_scroll + rows]):
            y = 146 + j * 46
            on = d["name"] == cur.get("name") and d["hostapi"] == cur.get("hostapi") and d["exclusive"] == cur.get("exclusive")
            self.rect(34, y, 700, 42, fill=T["seg_active"] if on else T["seg_inactive"])
            bad = d["label"] in self.state.bad_audio
            self.text(50, y + 21, d["label"][:62] + ("   (DID NOT RESPOND)" if bad else ""), 15,
                      T["accent"] if on else (T["ink_faint"] if bad else T["ink"]), on, "w")
            self.hit(34, y, 700, 42, lambda dd=d: self.pick_device(dd))
        if not devs:
            self.text(384, 260, "No audio outputs found", 18, T["ink_dim"])
        for cy, d in ((190, -1), (380, 1)):
            self.button(782, cy, 80, 80, "", lambda d=d: self.scroll_dev(3 * d))
            pts = [(782 - 18, cy - 9 * d), (782 + 18, cy - 9 * d), (782, cy + 12 * d)]
            self.cv.create_polygon([c for x, y in pts for c in (self.X(x), self.Y(y))], fill=T["ink"], outline="")
        self.text(34, 498, "BUFFER: SMALLER = LESS LAG · CRACKLES? GO ONE BIGGER", 12, T["ink_dim"], False, "w")
        self.seg(34, 512, 74, 44, [64, 128, 256, 512, 1024, 2048], self.state.blocksize, self.pick_buffer, vertical=False)
        lat = f"{self.audio.latency_ms:.1f} ms" if self.audio.stream else "-"
        self.readout(600, 534, 190, 44, f"LAG {lat}")
        if self.audio.stream:
            load = min(self.audio.engine.load, 9.99) * 100
            drops = self.audio.underruns
            self.text(710, 522, f"LOAD {load:.0f}%", 12, "#d9534f" if load > 70 else T["ink_dim"], True, "w")
            self.text(710, 544, f"DROPOUTS {drops}", 12, "#d9534f" if drops else T["ink_dim"], True, "w")
        if self.audio.error:
            e = self.audio.error
            self.text(424, 470, e[:100], 12, "#d9534f")
            if len(e) > 100:
                self.text(424, 488, e[100:200], 12, "#d9534f")
        # midi
        self.frame(844, 100, 422, 470, "MIDI in", "TAP A PORT TO TURN IT ON/OFF")
        names = self.midi.names()
        for j, n in enumerate(names[:5]):
            y = 146 + j * 46
            on = n in self.midi.ports
            self.rect(864, y, 382, 42, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(880, y + 21, n[:34], 14, T["accent"] if on else T["ink_dim"], on, "w")
            self.hit(864, y, 382, 42, lambda nn=n: self.toggle_port(nn))
        if not names:
            self.text(1055, 200, "Plug in the BeatStep Pro,", 15, T["ink_dim"])
            self.text(1055, 224, "then tap RESCAN", 15, T["ink_dim"])
        self.button(1055, 400, 382, 50, "RESCAN MIDI", self.rescan, px=17)
        for j, (pre, label) in enumerate((("s1", "SYNTH 1"), ("s2", "SYNTH 2"), ("dr", "DRUMS"))):
            y = 452 + j * 38
            self.text(870, y + 17, f"{label} CHANNEL", 13, T["ink_dim"], False, "w")
            self.button(1090, y + 17, 50, 34, "−", lambda p=pre: self.step_ch(p, -1), px=20)
            self.readout(1150, y + 17, 56, 34, str(self.state.ch[pre]))
            self.button(1210, y + 17, 50, 34, "+", lambda p=pre: self.step_ch(p, 1), px=20)
        # knobs
        self.frame(14, 580, 1252, 152, "Knobs", f"CCs: {', '.join(str(c) for c in self.state.cc_map)}")
        self.button(140, 670, 220, 80, "LEARN KNOBS", self.learn_start, accent=True, px=20)
        self.button(380, 670, 220, 80, "FACTORY CCs", self.factory_ccs, px=20)
        self.text(520, 640, "KNOB MODE", 12, T["ink_dim"], False, "w")
        self.seg(520, 656, 140, 44, ["absolute", "relative"], self.state.knob_mode, self.pick_knob_mode, vertical=False)
        self.button(866, 670, 164, 80, "ALL NOTES OFF", self.panic, px=16)
        self.button(1040, 670, 164, 80, "PAD ACTIONS", lambda: self.open_overlay(("actions",)), accent=True, px=16)
        self.button(1194, 670, 124, 80, "MY SETUPS", lambda: self.open_overlay(("setups",)), px=15)

    # ---------------------------------------------------------------- input
    def to_design(self, e):
        return (e.x - self.ox) / self.scale, (e.y - self.oy) / self.scale

    def find_hit(self, x, y):
        for h in reversed(self.hits):
            if h[0] <= x <= h[2] and h[1] <= y <= h[3]:
                return h
        return None

    def on_press(self, e):
        x, y = self.to_design(e)
        h = self.find_hit(x, y)
        self.drag = None
        if h and h[5] == "knob":
            self.drag = dict(key=h[4](), y=e.y, x=x, cx=(h[0] + h[2]) / 2, moved=False,
                             start=self.state.params.cur_norm(h[4]()))
        elif h and h[5] == "hold":
            h[4](True)
            self.drag = dict(kind="hold", fn=h[4])
            self.request_redraw()
        elif h and h[5] == "slider":
            self.drag = dict(kind="slider", h=h)
            h[4](min(max((x - h[0]) / (h[2] - h[0]), 0.0), 1.0))
            self.request_redraw()
        elif h:
            h[4]()
            self.request_redraw()

    def on_motion(self, e):
        d = self.drag
        if not d:
            return
        if d.get("kind") == "slider":
            x, _ = self.to_design(e)
            h = d["h"]
            h[4](min(max((x - h[0]) / (h[2] - h[0]), 0.0), 1.0))
            self.request_redraw()
            return
        if d.get("kind"):
            return
        dy = (d["y"] - e.y) / self.scale
        if abs(dy) > 6:
            d["moved"] = True
        if d["key"].startswith("mc."):
            self.last_macro = int(d["key"][3:]) - 1
        if d["moved"]:
            self.state.params.set_norm(d["key"], d["start"] + dy / 200.0)
            self.state.dirty = True
            self.request_redraw()

    def on_release(self, e):
        d = self.drag
        self.drag = None
        if d and d.get("kind") == "hold":
            d["fn"](False)
            self.request_redraw()
            return
        if d and d.get("kind"):
            return
        if d and not d["moved"]:
            self.state.params.nudge(d["key"], -1 if d["x"] < d["cx"] else 1)
            self.state.dirty = True
            self.request_redraw()

    def on_wheel(self, e, delta=None):
        delta = delta if delta is not None else e.delta
        if self.overlay:
            return
        x, y = self.to_design(e)
        h = self.find_hit(x, y)
        if h and h[5] == "knob":
            self.state.params.nudge(h[4](), 1 if delta > 0 else -1)
            self.state.dirty = True
            self.request_redraw()
        elif self.state.page == "Setup" and x < 834:
            self.scroll_dev(-1 if delta > 0 else 1)

    def on_resize(self, e):
        self.fonts = {}
        self.request_redraw()

    # ---------------------------------------------------------------- actions
    def show_toast(self, msg, secs=1.6):
        self.toast = (msg, time.time() + secs)
        self.request_redraw()

    def set_page(self, name, tapped=False):
        """Go to a page. `tapped`: from the header's sub-tab keys, where tapping a synth again goes back to its
        sound browser. From a BeatStep pad, pressing the page's pad again steps through its sub-pages."""
        self.overlay = None
        sub = None
        if name in OLD_PAGES:
            name, sub = OLD_PAGES[name]
        if name not in TABS:
            return
        if name != "Capture":
            self.listen_stop()   # v2.3: a bounce you were listening to stops when you leave CAPTURE
        if sub is not None and name in SUBPAGES:
            self.state.subpage[name] = sub
        elif name == self.state.page:
            if name in ("Synth 1", "Synth 2"):
                pre = "s" + name[-1]
                if tapped:
                    self.state.synth_edit[pre] = False
                elif not self.state.synth_edit[pre]:
                    self.state.synth_edit[pre] = True
                else:
                    self.state.subpage[name] = (self.state.subpage.get(name, 0) + 1) % len(SUBPAGES[name])
            elif name in SUBPAGES and not tapped:
                self.state.subpage[name] = (self.state.subpage.get(name, 0) + 1) % len(SUBPAGES[name])
        if name != self.state.page:
            if self.state.page not in OWN_SCREEN_PAGES:
                self.state.last_tab = self.state.page
            if name in NO_LOCK_PAGES:
                self.lock_off()
        self.state.page = name
        self.state.sec_page[SECTION_OF[name]] = name
        self.state.dirty = True

    def set_section(self, sec):
        """One of the five big keys: back to the sub-tab you were last on in that section."""
        if SECTION_OF.get(self.state.page) == sec and not self.overlay:
            return
        page = self.state.sec_page.get(sec) or dict(SECTIONS)[sec][0][1]
        self.set_page(page)

    def synth_view(self, pre, edit):
        self.state.synth_edit[pre] = edit
        if not edit:
            self.lock_off()
        self.state.dirty = True

    def pick_subpage(self, label):
        names = [lab for lab, _ in SUBPAGES[self.state.page]]
        self.state.subpage[self.state.page] = names.index(label)
        self.state.dirty = True

    # ---------------------------------------------------------------- mod routing menu
    def draw_route(self, pre, j):
        p = self.state.params
        v = p.val
        name = "Synth 1" if pre == "s1" else "Synth 2"
        self.overlay_base(f"Mod slot {j} · {name}", f"PICK A SOURCE AND A TARGET  ·  KNOB {8 + j} ON THE MOD PAGE SETS THE AMOUNT")
        si = int(v[f"{pre}.m{j}src"])
        di = int(v[f"{pre}.m{j}dst"])
        self.text(34, 168, "SOURCE", 14, T["accent"], True, "w")
        for i, src in enumerate(MOD_SOURCES):
            y0 = 182 + i * 50
            on = i == si
            self.rect(34, y0, 340, 44, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(50, y0 + 22, src.upper(), 15, T["accent"] if on else T["ink"], on, "w")
            self.hit(34, y0, 340, 44, lambda ii=i: (p.set_val(f"{pre}.m{j}src", ii), self.mark_dirty()))
        self.text(400, 168, "TARGET", 14, T["accent"], True, "w")
        dests = MOD_DESTS[pre]
        for i, dst in enumerate(dests):
            c, r = divmod(i, 6)
            x0, y0 = 400 + c * 290, 182 + r * 50
            on = i == di
            self.rect(x0, y0, 280, 44, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(x0 + 16, y0 + 22, dst.upper(), 15, T["accent"] if on else T["ink"], on, "w")
            self.hit(x0, y0, 280, 44, lambda ii=i: (p.set_val(f"{pre}.m{j}dst", ii), self.mark_dirty()))
        key = f"{pre}.m{j}amt"
        self.text(1000, 168, "AMOUNT", 14, T["accent"], True, "w")
        self.readout(1120, 230, 240, 52, SPECS[key].fmt(p.base_val(key)))
        self.button(1060, 300, 116, 60, "−", lambda: (p.nudge(key, -1), self.mark_dirty()), px=28)
        self.button(1180, 300, 116, 60, "+", lambda: (p.nudge(key, 1), self.mark_dirty()), px=28)
        self.button(1120, 376, 240, 52, "ZERO", lambda: (p.set_val(key, 0.0), self.mark_dirty()), px=16)
        self.text(1000, 430, "Negative amounts turn the", 13, T["ink_dim"], False, "w")
        self.text(1000, 450, "movement upside down.", 13, T["ink_dim"], False, "w")
        prev_j, next_j = (j - 2) % 8 + 1, j % 8 + 1
        self.button(560, 640, 220, 60, f"< SLOT {prev_j}", lambda: self.open_overlay(("route", pre, prev_j)), px=16)
        self.button(800, 640, 220, 60, f"SLOT {next_j} >", lambda: self.open_overlay(("route", pre, next_j)), px=16)
        self.button(1120, 640, 240, 70, "DONE", self.close_overlay, accent=True, px=20)
        self.button(160, 640, 250, 60, "CLEAR SLOT", lambda: (p.set_val(f"{pre}.m{j}src", 0), p.set_val(key, 0.0),
                                                            self.mark_dirty()), px=16)

    def mark_dirty(self):
        self.state.dirty = True
        self.request_redraw()

    def preset_step(self, pre, d):
        lst = self.sound_list(pre)
        names = [n for n, _ in lst]
        cur = self.state.preset_name[pre]
        i = names.index(cur) if cur in names else (self.state.preset.get(pre, 0) - (1 if d > 0 else 0))
        i = (i + d) % len(lst)
        self.state.preset[pre] = i
        name, vals = lst[i]
        self.state.params.apply_preset(pre, vals)
        self.state.preset_name[pre] = name
        self.state.dirty = True
        self.test_note(pre)

    def random_sound(self, pre):
        self.state.params.randomize(pre)
        self.state.preset_name[pre] = f"RANDOM #{np.random.randint(100, 999)}"
        self.state.dirty = True
        self.test_note(pre)

    def test_note(self, pre):
        eng = self.audio.engine
        note = 48 if pre == "s1" else 60
        eng.note_on(pre, note, 110)
        tok = time.time()
        self.test_notes[pre] = tok

        def off():
            if self.test_notes.get(pre) == tok:
                self.audio.engine.note_off(pre, note)
        self.root.after(450, off)

    def test_pad(self, pad):
        self.sel_pad = pad
        self.audio.engine.note_on("dr", pad, 110)

    def open_overlay(self, ov):
        self.overlay = ov
        self.armed = None

    def close_overlay(self):
        self.overlay = None
        self.armed = None
        self.request_redraw()

    # synth sound slots
    def zero_macros(self):
        self.lock_pick_clear()
        p = self.state.params
        for i in range(len(MACROS)):
            k = f"mc.{i + 1}"
            p.set_val(k, SPECS[k].default)
        self.state.dirty = True
        self.show_toast("MACROS BACK TO ZERO")

    def init_kind(self, page):
        """Which INIT a synth sub-page offers: the whole synth (Main) or just that page's part."""
        for tail, kind in (("Mod", "mod"), ("Mod 2", "mod"), ("Osc+", "osc"), ("Uni+FX", "unifx"), ("Arp", "arp"), ("Env", "env"),
                           ("LFO1 Steps", "steps1"), ("LFO2 Steps", "steps2")):
            if page.endswith(" " + tail):
                return kind
        return "all"

    def init_keys(self, page):
        """Keys reset by the INIT key on a synth page: Main = the whole synth, every other page = only its own part."""
        pre = "s1" if page.startswith("Synth 1") else "s2"
        main = PAGES["Synth 1" if pre == "s1" else "Synth 2"]
        kind = self.init_kind(page)
        if kind == "mod":
            tail = ("l1shape", "l1rate", "l1sync", "l2shape", "l2rate", "l2sync", "mea", "med")
            keys = [f"{pre}.{t}" for t in tail]
            for j in range(1, 13):
                keys += [f"{pre}.m{j}src", f"{pre}.m{j}dst", f"{pre}.m{j}amt"]
            return [k for k in keys if k in SPECS]
        if kind == "osc":
            return [k for k in PAGES[page] if k not in main]
        if kind == "arp":
            return [k for k in SPECS if k.startswith(pre + ".arp")]
        if kind == "unifx":
            return [f"{pre}.{t}" for t in ("uni", "unidet", "uniwid", "supersaw", "fdrive", "dist", "distamt", "sfx", "subtype",
                                            "sfxamt", "warp", "warpamt") if f"{pre}.{t}" in SPECS]
        if kind == "env":
            return [k for k in PAGES[page] if not k.endswith((".vol", ".glide", ".glmode", ".velamp"))]
        if kind in ("steps1", "steps2"):
            return [f"{pre}.l{kind[-1]}step{i}" for i in range(16)]
        return [k for k in SPECS if k.startswith(pre + ".") and not k.endswith((".mute", ".solo"))]

    def init_label(self):
        page = self.page_name()
        return {"mod": "INIT MODULATION", "osc": "INIT OSC+ PAGE", "unifx": "INIT UNI+FX", "arp": "INIT ARP", "env": "INIT ENVELOPES",
                "steps1": "INIT LFO 1 STEPS", "steps2": "INIT LFO 2 STEPS"}.get(self.init_kind(page), "INIT " + page.upper())

    def init_page(self):
        self.lock_pick_clear()
        page = self.page_name()
        p = self.state.params
        keys = self.init_keys(page)
        before = {k: p.norm[k] for k in keys}
        for k in keys:
            p.set_val(k, SPECS[k].default)
        p.clear_locks(keys)
        if self.init_kind(page) == "all":
            pre = "s1" if page.startswith("Synth 1") else "s2"
            self.state.preset_name[pre] = "Init"
            self.state.preset[pre] = 0
        self.init_undo = (page, before, time.time() + 8)
        self.root.after(8100, self.request_redraw)
        self.state.dirty = True
        self.show_toast(self.init_label().replace("INIT ", "") + " BACK TO INIT")

    def undo_init(self):
        self.lock_pick_clear()
        undo = getattr(self, "init_undo", None)
        if not undo:
            return
        p = self.state.params
        for k, n in undo[1].items():
            p.set_norm(k, n)
        self.init_undo = None
        self.state.dirty = True
        self.show_toast("UNDONE")

    def reset_all(self):
        """Two taps: every knob (both synths, all drum pads, mix and delay) back to its starting value.
        Saved sounds, the loaded drum kit and setup (audio, MIDI, knob CCs) are kept."""
        now = time.time()
        if now - getattr(self, "reset_armed", 0) > 3:
            self.reset_armed = now
            self.root.after(3100, self.request_redraw)
            return
        self.reset_armed = 0
        p = self.state.params
        self.lock_off()
        p.clear_locks()
        p.scenes = {str(i): None for i in range(1, 9)}
        p._scene_keys()
        for k, spec in SPECS.items():
            p.set_val(k, spec.default)
        for pre in ("s1", "s2"):
            self.state.preset_name[pre] = "Init"
            self.state.preset[pre] = 0
        self.audio.engine.panic()
        self.state.dirty = True
        self.show_toast("EVERYTHING RESET TO INIT")

    def sound_list(self, pre):
        lst = [("Init", {})] + [(name, vals) for name, vals in PRESETS[pre]]
        lst += [(s["name"], s["values"]) for s in self.state.sounds[pre] if s]
        return lst

    def save_slot(self, pre, i):
        now = time.time()
        slot = self.state.sounds[pre][i]
        if slot and not (self.armed and self.armed[:2] == (pre, i) and now - self.armed[2] < 3):
            self.armed = (pre, i, now)
            self.root.after(3100, self.request_redraw)
            return
        self.armed = None
        p = self.state.params
        values = {k.split(".", 1)[1]: p.base_val(k) for k in SPECS if k.startswith(pre + ".") and not k.endswith(".vol")}
        src = self.state.preset_name[pre]
        if slot and src == slot.get("name"):
            src = slot.get("from", "")
        name = f"My Sound {i+1}"
        self.state.sounds[pre][i] = {"name": name, "from": src, "values": values, "saved": time.strftime("%Y-%m-%d %H:%M")}
        self.state.preset_name[pre] = name
        self.state.dirty = True
        self.show_toast(f"SAVED TO SLOT {i+1}" if self.state.save_sounds() else "COULD NOT SAVE - SEE LOG")

    def load_slot(self, pre, i):
        slot = self.state.sounds[pre][i]
        if not slot:
            return
        self.state.params.apply_preset(pre, slot["values"])
        self.state.preset_name[pre] = slot["name"]
        self.state.dirty = True
        self.test_note(pre)

    # drum kits
    def select_kit(self, kind, ref, preview=True):
        eng = self.audio.engine
        if kind == "factory":
            eng.drums.load_factory(ref)
            self.state.kit = {"factory": ref}
        else:
            entry = {kind: list(ref) if kind == "library" else ref}
            if kind == "library":
                ok = self.audio.load_library_kit(eng, *ref)
            else:
                ok = os.path.isdir(ref) and eng.drums.load_folder(ref)
            if entry in self.state.recent:
                self.state.recent.remove(entry)
            if not ok:
                self.show_toast("KIT MISSING OR NO READABLE WAVS")
                self.state.dirty = True
                return
            self.state.kit = entry
            self.state.recent.insert(0, entry)
            del self.state.recent[8:]
        self.state.dirty = True
        if preview:
            self.play_pattern([[0], [4], [2], [4]], 130)

    def kit_step(self, d):
        cur = self.state.kit.get("library")
        lib = self.audio.library()
        if cur and lib.ok() and cur[0] in lib.machines:  # step through this machine's kits, then the next machine
            m = cur[0]
            ks = [k["name"] for k in lib.kits(m)]
            i = ks.index(cur[1]) + d if cur[1] in ks else 0
            mi = lib.machines.index(m)
            while not (0 <= i < len(ks)):
                mi = (mi + (1 if i >= len(ks) else -1)) % len(lib.machines)
                m = lib.machines[mi]
                ks = [k["name"] for k in lib.kits(m)]
                i = 0 if d > 0 else len(ks) - 1
            self.select_kit("library", [m, ks[i]])
            return
        ch = self.kit_choices()
        cur = next((i for i, (k, ref, _) in enumerate(ch) if self.kit_is_current(k, ref)), 0)
        k, ref, name = ch[(cur + d) % len(ch)]
        self.select_kit(k, ref)

    def play_pattern(self, steps, ms):
        for i, pads in enumerate(steps):
            for p in pads:
                self.root.after(i * ms, lambda p=p: self.audio.engine.note_on("dr", p, 105))

    def demo_beat(self):
        pat = [[0, 4], [4], [4], [4, 9], [2, 4], [4], [0, 4], [5],
               [4], [0, 4], [4], [4, 9], [2, 4, 3], [4], [4, 0], [5]]
        self.play_pattern(pat, 125)

    def reset_pads(self):
        p = self.state.params
        for i in range(1, 17):
            for part in ("tune", "decay", "level"):
                k = f"dr.p{i}.{part}"
                p.set_val(k, SPECS[k].default)
        self.state.dirty = True
        self.show_toast("PAD KNOBS RESET")

    def pick_brand(self, b):
        self.lib_brand = b
        self.lib_machine = None
        self.lib_scroll["machines"] = 0

    def pick_machine(self, m):
        self.lib_machine = m
        self.lib_scroll["kits"] = 0
        ks = self.audio.library().kits(m)
        if len(ks) == 1:
            self.select_kit("library", [m, ks[0]["name"]])

    def back_to_machines(self):
        self.lib_machine = None

    def _locked_pad_data(self):
        eng = self.audio.engine
        out = {}
        for p in self.state.locked_pads:
            out[p] = (list(eng.drums.samples[p]), eng.drums.names[p], dict(eng.drums.sources[p]))
        return out

    def _restore_locked_pads(self, data):
        eng = self.audio.engine
        for p, (s, n, src) in data.items():
            eng.drums.samples[p] = s
            eng.drums.names[p] = n
            eng.drums.sources[p] = src

    def random_machine(self):
        lib = self.audio.library()
        m, ki = lib.random_kit()
        if m is None:
            return
        self.lib_brand = next(b for b, ms in lib.brands.items() if m in ms)
        self.lib_machine = m
        self.lib_scroll["kits"] = ki // 12 * 12
        self.select_kit("library", [m, lib.kits(m)[ki]["name"]])
        self.show_toast(library_kit_label(m, lib.kits(m)[ki]["name"]).upper()[:34], 1.2)

    def pick_library(self):
        folder = filedialog.askdirectory(title="Pick your Drum Machine Collection folder (the one holding the machine folders)")
        if folder:
            self.state.library_root = folder
            self.state.dirty = True
            self.lib_brand = self.lib_machine = None
            self.rescan_samples(quiet=False)
            self.request_redraw()

    def load_kit(self):
        folder = filedialog.askdirectory(title="Pick a folder of WAV drum samples (first 16 go on pads 1-16)")
        if not folder:
            return
        if self.audio.engine.drums.load_folder(folder):
            self.select_kit("folder", folder)
            self.show_toast(f"LOADED {os.path.basename(folder).upper()[:24]}")
        else:
            self.show_toast("NO WAV FILES IN THAT FOLDER")

    def start_audio(self, dev=None, fallback=False):
        """ASIO drivers must be opened on the main thread (COM), so ASIO opens here directly; a crash or
        freeze is still caught next launch by the audio_pending marker. Other outputs open on a worker
        thread with a timeout so a stuck driver can't freeze the app."""
        if self.audio.busy():
            self.show_toast("AUDIO DRIVER STILL BUSY - TRY ANOTHER OUTPUT")
            return
        target = dev or self.audio.find(self.state.device)
        label = (target or {}).get("label", "")
        self.audio.label = "STARTING AUDIO..."
        self.audio.error = ""
        if target and target.get("hostapi") == "ASIO":
            self.draw()
            self.root.update_idletasks()
            ok = self.audio.start(target)
            if ok:
                self.show_toast("AUDIO ON")
            elif fallback:
                self.fallback_audio(label)
            else:
                self.show_toast("COULD NOT OPEN THAT OUTPUT")
            return
        w = threading.Thread(target=self.audio.start, args=(dev,), daemon=True)
        self.audio._worker = w
        w.start()
        t0 = time.time()

        def check():
            if w.is_alive():
                if time.time() - t0 > 8:
                    if label and label not in self.state.bad_audio:
                        self.state.bad_audio.append(label)
                    self.state.audio_pending = None
                    self.state.device = None
                    self.state.save()
                    self.audio.label = "AUDIO ERROR"
                    self.audio.error = f"{label[:50]} is not responding - pick another output"
                    self.state.page = "Setup"
                    log("audio open timed out:", label)
                    return
                self.root.after(200, check)
            else:
                self.show_toast("AUDIO ON" if not self.audio.error else "COULD NOT OPEN THAT OUTPUT")
        self.root.after(200, check)

    def fallback_audio(self, failed_label):
        """Startup: the chosen ASIO driver would not open (often another app is using it). Play through the
        normal Windows output for now, but keep the ASIO choice so the next launch tries it again."""
        keep = self.state.device
        err = self.audio.error
        win = [d for d in self.audio.devices() if d["hostapi"] == "Windows WASAPI" and not d["exclusive"]]
        try:
            default_out = sd.default.device[1]
        except Exception:
            default_out = None
        win.sort(key=lambda d: d["index"] != default_out)
        if win and self.audio.start(win[0]):
            self.state.device = keep
            self.audio.error = (f"{failed_label[:40]} would not open - is FL Studio / Voicemeeter / a DAW using it? "
                                f"Playing through Windows audio for now. Close that app, then tap the ASIO output.")
            log("fallback to", win[0]["label"], "after:", err)
            self.state.page = "Setup"
            self.show_toast("ASIO BUSY - USING WINDOWS AUDIO", 2.5)
        else:
            self.audio.error = err

    def pick_device(self, d):
        if d["label"] in self.state.bad_audio:
            self.state.bad_audio.remove(d["label"])  # the user chose it on purpose: try again
        self.state.dirty = True
        self.start_audio(d)

    def scroll_dev(self, d):
        self.dev_scroll += d
        self.request_redraw()

    def pick_buffer(self, b):
        self.state.blocksize = int(b)
        self.state.dirty = True
        self.start_audio()

    def pick_knob_mode(self, m):
        self.state.knob_mode = m
        self.state.dirty = True

    def toggle_port(self, name):
        if name in self.midi.ports:
            self.midi.close(name)
            if name not in self.state.midi_off:
                self.state.midi_off.append(name)
        else:
            if name in self.state.midi_off:
                self.state.midi_off.remove(name)
            self.midi.open(name)
        self.state.dirty = True

    def rescan(self):
        self.midi.open_all()
        self.show_toast(self.midi.status())

    def step_ch(self, pre, d):
        self.state.ch[pre] = (self.state.ch[pre] - 1 + d) % 16 + 1
        self.state.dirty = True

    def learn_start(self):
        self.state.page = "Perform"
        self.midi.learn = 0
        self.midi.learn_last_cc = None

    def learn_skip(self):
        if self.midi.learn is not None:
            self.midi.learn += 1
            if self.midi.learn >= 16:
                self.midi.learn = None

    def learn_stop(self):
        self.midi.learn = None
        self.state.dirty = True

    def factory_ccs(self):
        self.state.cc_map = list(FACTORY_CCS)
        self.state.dirty = True
        self.show_toast("FACTORY KNOB CCs RESTORED")

    def panic(self):
        self.audio.engine.panic()
        self.show_toast("ALL NOTES OFF")

    def save_now(self):
        self.state.save()
        self.show_toast("SAVED")

    # ---------------------------------------------------------------- loop
    def tick(self):
        try:
            eng = self.audio.engine
            for syn in (eng.s1, eng.s2):
                syn.active *= 0.8
            eng.drums.active = [a * 0.75 for a in eng.drums.active]
            while self.action_q:
                a = self.action_q.popleft()
                if isinstance(a, tuple):
                    self.run_beat_q(a)
                else:
                    self.run_action(a)
            self.resample_tick()
            self.bounce_tick()
            self.samples_tick()
            self.loop_tick()
            self.beat_tick()
            self.voice_tick()
            self.mutate_tick()
            now = time.time()
            if self.redraw_wanted or now - self.last_draw > 0.1:
                self.draw()
                self.redraw_wanted = False
                self.last_draw = now
            if self.state.dirty and time.time() - self.last_save > 2.0:
                self.state.save()
                self.last_save = time.time()
        except Exception:
            log("gui error", traceback.format_exc())
        self.root.after(50, self.tick)

    def quit(self):
        try:
            self.voice.stop()
            self.state.save()
            self.midi.close_all()
            self.audio.stop()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    # The audio callback, MIDI and the screen share one Python interpreter lock. By default a thread that
    # wants it can wait 5 ms - as long as a whole 256-sample buffer - which is what made the audio crackle
    # while the screen redrew. 1 ms lets the audio thread in on time.
    sys.setswitchinterval(0.001)
    try:
        App().run()
    except Exception:
        log("fatal", traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
