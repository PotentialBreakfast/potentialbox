"""PotentialBox - drum sampler + 2 synths, pre-wired to the Arturia BeatStep Pro.

Seq 1 (MIDI ch 1)  -> Synth 1 (analog-style)
Seq 2 (MIDI ch 2)  -> Synth 2 (wavetable)
Drum  (MIDI ch 10) -> Drums  (16 pads, notes 36-51)
16 knobs (CNTRL mode) -> the 16 knobs on the current page

Look: the shared Potential* dark theme (shared/potential-theme.conf).
"""
import os
import sys
import json
import math
import time
import traceback
import threading
import collections

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
                                 HIDDEN_PAGES, MOD_SOURCES, MOD_DESTS, PUNCH_FX)
from potentialbox.recorder import Recorder, write_wav, recordings_dir  # noqa: E402
from potentialbox.looper import TRACKS, SOURCES, FX_TYPES, SPEEDS, LENGTHS, STATE_TEXT  # noqa: E402
from potentialbox.beats import (Beat, GENRES, GENRE_NAMES, ROLE_PAD, ROLE_NAME, GROUP_NAMES,  # noqa: E402
                               GROUPS as BEAT_GROUPS, BAR_CHOICES)
from potentialbox import kits  # noqa: E402
from potentialbox.library import Library, map_kit, brand_of, build_index, filter_index, GROUPS, PAD_GROUP  # noqa: E402

APP = "PotentialBox"
VERSION = "1.8.1"
W, H = 1280, 800
FACTORY_CCS = [10, 74, 71, 76, 77, 93, 73, 75, 114, 18, 19, 16, 17, 91, 79, 72]
TABS = [p for p in PAGES if p not in HIDDEN_PAGES] + ["Setup"]
SHORT_DEST = {"Wave position": "Wave pos", "Saw > Square": "Wave", "Pulse width": "Pulse w.", "Osc 2 pitch": "Osc 2",
              "Resonance": "Reso", "Velocity": "Vel", "Smooth random": "Smooth"}
CFG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), APP)
CFG_FILE = os.path.join(CFG_DIR, "state.json")
LOG_FILE = os.path.join(CFG_DIR, "log.txt")
SOUNDS_FILE = os.path.join(CFG_DIR, "my-sounds.json")
SLOTS = 8
KITS_FILE = os.path.join(CFG_DIR, "my-kits.json")
SETUPS_FILE = os.path.join(CFG_DIR, "my-setups.json")
RESAMPLE_DIR = os.path.join(CFG_DIR, "Resampled")
NO_LOCK_PAGES = ("Macros", "Beats", "Live", "Loop", "Setup")
OWN_SCREEN_PAGES = ("Beats", "Live", "Loop")  # tabs that draw their own screen and turn the pads into their own pads
LOOP_PADS = [f"Track {t} rec / play / dub" for t in range(1, 6)] + ["Undo / redo", "All stop / play",
             "Record next empty track"] + [f"Track {t} stop (hold: clear)" for t in range(1, 6)] + [
             "Reverse last track", "Speed last track", "Back to last tab"]
BEAT_PADS = ["Play / stop", "New beat", "Previous genre", "Next genre", "Hold: Fill", "Mutate", "Simpler", "Busier",
             "Mute kick", "Mute snare", "Mute hats", "Mute perc", "Tempo down", "Tempo up", "Send to BeatStep",
             "Back to last tab"]
ACTIONS = [("rand_s1", "Random Synth 1"), ("rand_s2", "Random Synth 2"), ("rand_kit", "Random Drum Kit"),
           ("next_kit", "Next Kit"), ("prev_tab", "Previous Tab"), ("next_tab", "Next Tab"),
           ("tab:Perform", "Perform Tab"), ("tab:Synth 1", "Synth 1 Tab"), ("tab:Synth 2", "Synth 2 Tab"),
           ("tab:Drums 1-8", "Drums 1-8 Tab"), ("tab:Drums 9-16", "Drums 9-16 Tab"), ("tab:Mix", "Mix Tab"),
           ("next_s1", "Synth 1 Next Sound"), ("next_s2", "Synth 2 Next Sound"), ("tab:Macros", "Macros Tab"),
           ("panic", "All Notes Off"),
           # v1.6: no default pad, tap the card and press a pad or step to use them
           ("tab:Live", "Live Tab"), ("tab:FX", "FX Tab"), ("rec", "Record On/Off"), ("fill", "Fill (hold)"),
           ("tab:Loop", "Loop Tab"), ("tab:Beats", "Beats Tab")]
ACTION_NAMES = dict(ACTIONS)
PAD_ACTIONS = [aid for aid, _ in ACTIONS[:16]]
HOLD_ACTIONS = {"fill"}
# On the Live tab the 16 BeatStep pads (the ones set to pad actions 1-16) play these instead
LIVE_PADS = [f"Hold: {n}" for n in PUNCH_FX] + ["Hold: Fill", "Hold: Scene B", "Record on/off", "Random Synth 1",
                                                 "Random Synth 2", "Random Drum Kit", "Next Kit", "Back to last tab"]


def default_actions():
    """BeatStep Pro pads in CNTRL mode, MIDI channel 16, notes 36-51 -> the first 16 actions in order."""
    d = {aid: {"t": "note", "ch": 16, "n": 36 + i} for i, aid in enumerate(PAD_ACTIONS)}
    d.update({aid: None for aid, _ in ACTIONS[16:]})
    return d


KNOB_GROUPS = {
    "Perform": [(0, 4, "Synth 1"), (4, 8, "Synth 2"), (8, 12, "Drums"), (12, 13, "Bus"), (13, 16, "Volumes")],
    "Synth 1": [(0, 4, "Filter"), (4, 8, "Oscillators"), (8, 12, "Amp envelope"), (12, 16, "Play & output")],
    "Synth 2": [(0, 4, "Wavetable"), (4, 8, "Filter & table"), (8, 12, "Amp envelope"), (12, 16, "Play & output")],
    "Drums 1-8": [(0, 8, "Tune · pads 1-8"), (8, 16, "Length · pads 1-8")],
    "Drums 9-16": [(0, 8, "Tune · pads 9-16"), (8, 16, "Length · pads 9-16")],
    "Macros": [(0, 8, "Synth moves"), (8, 16, "Space & performance")],
    "Synth 1 Osc+": [(0, 4, "Oscillator 2"), (4, 5, "Noise"), (5, 7, "Chord"), (7, 8, "Pan"), (8, 10, "Filter"),
                     (10, 12, "Feel"), (12, 14, "Pitch env"), (14, 16, "Glide & level")],
    "Synth 1 Mod": [(0, 3, "LFO 1"), (3, 6, "LFO 2"), (6, 8, "Mod env"), (8, 16, "Mod slots · tap a name to change it")],
    "Synth 2 Osc+": [(0, 2, "Chord"), (2, 4, "Sub & noise"), (4, 6, "Pan & drift"), (6, 8, "Pitch env"),
                     (8, 10, "Filter"), (10, 12, "Feel"), (12, 16, "Quick access")],
    "Synth 2 Mod": [(0, 3, "LFO 1"), (3, 6, "LFO 2"), (6, 8, "Mod env"), (8, 16, "Mod slots · tap a name to change it")],
    "Mix": [(0, 4, "Levels"), (4, 8, "Bus & DJ filter"), (8, 13, "Side-chain duck"), (13, 16, "Glue & width")],
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
           (11, 14, "Reverb"), (14, 16, "Bus")],
}
LIBRARY_GUESSES = [os.path.join(os.path.expanduser("~"), sub, "Drum Machine Collection")
                   for sub in ("Downloads", "Documents", "Music", "Desktop")]


def log(*a):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------- theme
DEFAULT_THEME = dict(
    bg="17191d", panel="24282d", line="3a3f47", ink="e6e9ee", ink_dim="8b929c", ink_faint="5b616b",
    accent="f2b34a", accent_hi="f5ab3d", knob_face="2a2e34", knob_ring="3a3f47", knob_dot="dc9b3c",
    seg_active="3a2c0f", seg_inactive="1c1e22", seg_active_tx="f2b34a", btn_text="e6e9ee", btn_bg="2a2e34",
    btn_on="a86f1a", tab_on="3a2c0f", tab_on_tx="f2b34a", lcd="0c0e10", well="0c0e10", chrome_ink="e6e9ee",
)


def load_theme():
    t = dict(DEFAULT_THEME)
    try:
        with open(os.path.join(HERE, "potential-theme.conf"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("theme_") and "=" in line:
                    k, v = line[6:].split("=", 1)
                    t[k.strip()] = v.strip()
    except Exception:
        pass
    return {k: "#" + v for k, v in t.items()}


T = load_theme()


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
        self.page = "Perform"
        self.subpage = {t: 0 for t in SUBPAGES}
        self.last_tab = "Perform"
        self.setups = [None] * SLOTS
        self.rec_stems = True
        self.loop_input = None    # list of interface input channels (0-based) or None
        self.loop_cfg = {}
        self.beat = None          # Beat.to_json()
        self.beat_kit = True      # picking a genre also loads its kit
        self.beat_mutes = []
        self.beat_bars = 2
        self.clock_master = False   # PotentialBox sends clock + Start/Stop to the BeatStep
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
        p.scenes = {"A": None, "B": None}
        for w in ("A", "B"):
            sc = (d or {}).get(w)
            if isinstance(sc, dict):
                p.scenes[w] = {k: float(n) for k, n in sc.items() if k in SPECS}
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
        page = {"Mix & FX": "Mix"}.get(d.get("page"), d.get("page"))
        self.page = page if page in TABS else "Perform"
        sp = d.get("subpage", {})
        if isinstance(sp, dict):
            for t in self.subpage:
                self.subpage[t] = int(sp.get(t, 0)) % len(SUBPAGES[t])
        self.load_locks(d.get("locks"))
        self.load_scenes(d.get("scenes"))
        self.rec_stems = bool(d.get("rec_stems", True))
        li = d.get("loop_input")
        self.loop_input = [int(c) for c in li][:2] if isinstance(li, list) and li else None
        self.loop_cfg = d.get("loop_cfg", {}) if isinstance(d.get("loop_cfg"), dict) else {}
        self.beat = d.get("beat") if isinstance(d.get("beat"), dict) else None
        self.beat_kit = bool(d.get("beat_kit", True))
        self.beat_mutes = [g for g in d.get("beat_mutes", []) if g in GROUP_NAMES]
        self.beat_bars = int(d.get("beat_bars", 2)) if int(d.get("beat_bars", 2)) in BAR_CHOICES else 2
        self.clock_master = bool(d.get("clock_master", False))
        self.last_tab = d.get("last_tab", "Perform") if d.get("last_tab") in TABS else "Perform"
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
                     clock_master=self.clock_master)
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

    def callback(self, outdata, frames, t, status):
        try:
            outdata[:] = self.engine.render(frames)
        except Exception:
            outdata.fill(0)
            log("render error", traceback.format_exc())

    def duplex_callback(self, indata, outdata, frames, t, status):
        try:
            ch = self.in_chans
            x = indata[:, ch]
            if x.shape[1] == 1:
                x = np.repeat(x, 2, axis=1)
            outdata[:] = self.engine.render(frames, x)
        except Exception:
            outdata.fill(0)
            log("render error", traceback.format_exc())

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
        self.audio = Audio(self.state)
        self.audio.apply_kit()
        self.midi = Midi(self)

        self.root = tk.Tk()
        self.root.title(f"{APP} {VERSION}")
        self.root.configure(bg=T["bg"])
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        s = min(1.0, sw * 0.92 / W, sh * 0.86 / H)
        self.root.geometry(f"{int(W*s)}x{int(H*s)}")
        self.root.minsize(640, 400)
        self.cv = tk.Canvas(self.root, bg=T["bg"], highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.scale, self.ox, self.oy = s, 0, 0
        self.fonts = {}
        fams = set(tkfont.families(self.root))
        self.fam = next((f for f in ("Bahnschrift", "Segoe UI", "DejaVu Sans", "Helvetica") if f in fams), "TkDefaultFont")
        self.fam_b = next((f for f in ("Bahnschrift SemiBold", "Segoe UI Semibold") if f in fams), self.fam)
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
        self.cv.bind("<Button-4>", lambda e: self.on_wheel(e, 120))
        self.cv.bind("<Button-5>", lambda e: self.on_wheel(e, -120))
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.bind("<Escape>", lambda e: self.close_overlay())
        self.overlay = None  # None, ("sounds", "s1"/"s2") or ("kits",)
        self.armed = None  # (pre, slot, time) for "tap again to replace"
        self.lib_brand = None
        self.lib_machine = None
        self.lib_scroll = {"brands": 0, "machines": 0, "kits": 0}
        self.sel_pad = 0
        self.pe = {"group": None, "scope": "all", "scroll": 0}
        self.sound_index = None  # built on first use of the pad editor
        self.indexing = False
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
        self.send_countdown = None
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
        self.last_save = time.time()
        self.last_draw = 0.0
        self.root.after(40, self.tick)

    # ---------------------------------------------------------------- helpers
    def request_redraw(self):
        self.redraw_wanted = True

    def page_name(self):
        """The knob page shown: a tab, or the selected sub-page of a synth tab."""
        page = self.state.page if self.state.page in PAGES else "Perform"
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
        x0, y0, x1, y1 = X(x), Y(y), X(x + w), Y(y + h)
        r = min(r * s, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        self.cv.create_polygon(pts, smooth=True, fill=fill, outline=outline)

    def rect(self, x, y, w, h, fill="", outline=""):
        self.cv.create_rectangle(self.X(x), self.Y(y), self.X(x + w), self.Y(y + h), fill=fill, outline=outline)

    def text(self, x, y, s, px, color, bold=False, anchor="center"):
        self.cv.create_text(self.X(x), self.Y(y), text=s, font=self.font(px, bold), fill=color, anchor=anchor)

    def hit(self, x, y, w, h, fn, kind="tap"):
        self.hits.append((x, y, x + w, y + h, fn, kind))

    # ---------------------------------------------------------------- widgets (theme)
    def frame(self, x, y, w, h, title, sub="", led=None):
        self.rect(x, y, w, h, outline=T["line"])
        self.text(x + 18, y + 30, title.upper(), 22, T["accent"], True, "w")
        tw = self.font(22, True).measure(title.upper()) / self.scale
        if led is not None:
            self.led(x + 18 + tw + 16, y + 30, led)
            tw += 26
        self.cv.create_line(self.X(x + 18 + tw + 4), self.Y(y + 36), self.X(x + w - 18), self.Y(y + 36), fill=T["line"])
        if sub:
            self.text(x + w - 18, y + 22, sub, 12, T["ink_dim"], False, "e")

    def readout(self, cx, cy, w, h, s, label="", above=False):
        self.rect(cx - w / 2, cy - h / 2, w, h, fill=T["well"], outline=T["line"])
        self.text(cx, cy, s.upper(), 16, T["accent"], True)
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
            self.text(bx + bw / 2, by + bh / 2, str(opt).upper(), 13, T["seg_active_tx"] if on else T["ink_dim"], on)
            self.hit(bx, by, bw, bh, lambda o=opt: fn(o))

    def led(self, cx, cy, lit):
        r = 6
        self.cv.create_oval(self.X(cx - r), self.Y(cy - r), self.X(cx + r), self.Y(cy + r),
                            fill=T["accent"] if lit else T["well"], outline=T["line"])

    def knob(self, idx, cx, cy, r, key):
        spec = SPECS[key]
        p = self.state.params
        locked_here = p.lock_step is not None and p.lock_step in p.locks.get(key, {})
        n = p.cur_norm(key) if p.lock_step is not None else p.shown(key)
        moved = p.lock_step is None and abs(n - p.norm[key]) > 0.004
        hot = time.time() - self.midi.flash[idx] < 0.35
        X, Y, s = self.X, self.Y, self.scale
        # dotted ring
        dots = 31
        for i in range(dots):
            a = math.radians(225 - 270 * i / (dots - 1))
            rx, ry = cx + (r + 11) * math.cos(a), cy - (r + 11) * math.sin(a)
            lit = hot and i / (dots - 1) <= n + 1e-6
            d = 2.2 if lit else 1.8
            self.cv.create_oval(X(rx - d), Y(ry - d), X(rx + d), Y(ry + d), outline="",
                                fill=T["accent"] if lit else T["ink_faint"])
        self.cv.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r), fill=T["knob_face"],
                            outline=T["accent"] if hot else T["knob_ring"], width=max(1, int(2 * s)))
        if moved:  # where your own setting is, while a macro pushes the knob
            ab = math.radians(225 - 270 * p.norm[key])
            bx, by = cx + (r - 12) * math.cos(ab), cy - (r - 12) * math.sin(ab)
            self.cv.create_oval(X(bx - 4), Y(by - 4), X(bx + 4), Y(by + 4), fill="", outline=T["ink_faint"], width=max(1, int(2 * s)))
        a = math.radians(225 - 270 * n)
        dx, dy = cx + (r - 12) * math.cos(a), cy - (r - 12) * math.sin(a)
        self.cv.create_oval(X(dx - 7), Y(dy - 7), X(dx + 7), Y(dy + 7), fill=T["knob_dot"], outline="")
        self.text(cx, cy + r + 24, self.knob_label(key), 13, T["ink"], True)
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
        if len(key) == 8 and key[2:4] == ".m" and key.endswith("amt"):
            return key[:2], int(key[4])
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
        if self.page_name() in ("Perform", "Mix", "Mix EQ", "FX") and key[:2] in ("s1", "s2") and "Synth" not in lab:
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
        self.rect(0, 0, W, H, fill=T["bg"])
        self.draw_header()
        if self.state.page == "Setup":
            self.draw_setup()
        elif self.state.page == "Live":
            self.draw_live()
        elif self.state.page == "Loop":
            self.draw_loop()
        elif self.state.page == "Beats":
            self.draw_beats()
        else:
            self.draw_knobs()
            if self.lock_mode:
                self.draw_locks()
            else:
                self.draw_instruments()
        self.draw_tabs()
        if self.overlay and self.overlay[0] == "sounds":
            self.draw_sounds(self.overlay[1])
        elif self.overlay and self.overlay[0] == "kits":
            self.draw_kits()
        elif self.overlay and self.overlay[0] == "machines":
            self.draw_machines()
        elif self.overlay and self.overlay[0] == "pad":
            self.draw_pad_editor()
        elif self.overlay and self.overlay[0] == "mykits":
            self.draw_mykits()
        elif self.overlay and self.overlay[0] == "actions":
            self.draw_actions()
        elif self.overlay and self.overlay[0] == "route":
            self.draw_route(self.overlay[1], self.overlay[2])
        elif self.overlay and self.overlay[0] == "resample":
            self.draw_resample()
        elif self.overlay and self.overlay[0] == "setups":
            self.draw_setups()
        elif self.overlay and self.overlay[0] == "loopinput":
            self.draw_loop_input()
        elif self.overlay and self.overlay[0] == "myloops":
            self.draw_my_loops()
        msg, until = self.toast
        if msg and time.time() < until:
            self.rrect(300, 30, 430, 48, 12, T["btn_on"])
            self.text(515, 54, msg[:40], 16, T["btn_text"], True)

    def draw_header(self):
        self.rect(0, 0, W, 90, fill=T["bg"])
        self.text(24, 34, "POTENTIALBOX", 30, T["accent"], True, "w")
        rec = self.audio.engine.recorder
        if rec is not None:
            sec = int(rec.seconds())
            self.cv.create_oval(self.X(24), self.Y(58), self.X(36), self.Y(70), fill="#d9534f", outline="")
            self.text(44, 64, f"RECORDING {sec // 60:02d}:{sec % 60:02d}", 12, "#d9534f", True, "w")
        else:
            self.text(24, 64, "BEATSTEP PRO GROOVEBOX", 11, T["ink_dim"], False, "w")
        eng = self.audio.engine
        lat = f" · {self.audio.latency_ms:.0f} MS" if self.audio.stream else ""
        self.readout(510, 54, 400, 38, (self.audio.label + lat) if not self.audio.error else "AUDIO ERROR - TAP SETUP", "audio", True)
        self.readout(845, 54, 240, 38, self.midi.status(), "midi", True)
        self.led(950, 54, time.time() - self.midi.activity < 0.12)
        self.readout(1045, 54, 110, 38, f"{eng.bpm:.0f} BPM", "tempo", True)
        pk = min(eng.peak, 1.0)
        self.rect(1120, 35, 140, 38, fill=T["well"], outline=T["line"])
        if pk > 0.001:
            self.rect(1123, 38, 134 * pk, 32, fill=T["accent"] if pk < 0.98 else "#d9534f")
        self.text(1120, 25, "LEVEL", 11, T["ink_dim"], True, "w")
        self.cv.create_line(self.X(0), self.Y(90), self.X(W), self.Y(90), fill=T["line"])

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
            self.button(560, 121, 220, 32, "ZERO ALL MACROS", self.zero_macros, px=13)
        tab = self.state.page
        if tab in SUBPAGES:
            names = [lab for lab, _ in SUBPAGES[tab]]
            cur = names[self.state.subpage.get(tab, 0) % len(names)]
            self.seg(270, 105, 96, 32, names, cur, self.pick_subpage, vertical=False)
            if self.midi.learn is None and tab in ("Synth 1", "Synth 2"):
                undo = getattr(self, "init_undo", None)
                if undo and undo[0] == self.page_name() and time.time() < undo[2]:
                    self.button(760, 121, 190, 32, "UNDO INIT", self.undo_init, px=14)
                else:
                    self.button(760, 121, 190, 32, self.init_label(), self.init_page, accent=True, px=14)
        if tab not in NO_LOCK_PAGES:
            sub = ""
        self.frame(14, 100, 1252, 372, tab, sub)
        if tab not in NO_LOCK_PAGES and self.midi.learn is None:
            self.button(1160, 121, 180, 32, "LOCKS ON" if self.lock_mode else "STEP LOCKS", self.toggle_locks,
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
            self.text(bx + 22, by + 15, str(i + 1), 11, T["btn_text"], True)
            self.text(bx + 22, by + 32, eng.drums.names[i][:5].upper(), 8, T["ink_dim"] if not on else T["btn_text"])
            self.hit(bx, by, 44, 44, lambda p=i: self.test_pad(p))
        self.button(x + 46, y + 222, 64, 42, "<", lambda: self.kit_step(-1), px=20)
        self.button(x + 150, y + 222, 130, 42, "KIT MENU", lambda: self.open_overlay(("kits",)), accent=True, px=15)
        self.button(x + 254, y + 222, 64, 42, ">", lambda: self.kit_step(1), px=20)
        self.button(x + 346, y + 222, 104, 42, f"EDIT PAD {self.sel_pad + 1}", self.open_pad_editor, px=13)

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
        for i, kit in enumerate(kits.KITS):
            r, c = divmod(i, 3)
            x0, y0 = 34 + c * 272, 156 + r * 118
            on = self.kit_is_current("factory", i)
            self.rrect(x0, y0, 260, 108, 12, T["seg_active"] if on else T["btn_bg"])
            self.text(x0 + 130, y0 + 42, kit["name"].upper(), 22, T["accent"] if on else T["btn_text"], True)
            self.text(x0 + 130, y0 + 76, kit["desc"], 12, T["ink_dim"])
            self.hit(x0, y0, 260, 108, lambda j=i: self.select_kit("factory", j))
        self.text(34, 530, "TAP A KIT TO HEAR IT. IT STAYS LOADED WHEN YOU CLOSE THIS MENU.", 13, T["ink_dim"], False, "w")
        lib = self.audio.library()
        n = len(lib.machines) if lib.ok() else 0
        self.button(164, 610, 260, 80, f"DRUM MACHINES ({n})" if n else "DRUM MACHINES",
                    lambda: self.open_overlay(("machines",)), accent=True, px=18)
        self.button(436, 610, 260, 80, "PLAY DEMO BEAT", self.demo_beat, px=18)
        self.button(708, 610, 260, 80, "RESET PAD KNOBS", self.reset_pads, px=18)
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
        self.button(1056, 610, 380, 70, "CLOSE", self.close_overlay, px=20)

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
        self.pe["group"] = PAD_GROUP[self.sel_pad]
        self.pe["scroll"] = 0
        self.open_overlay(("pad",))
        self.ensure_index()

    def ensure_index(self):
        lib = self.audio.library()
        if self.sound_index is not None or self.indexing or not lib.ok():
            return
        self.indexing = True

        def work():
            try:
                self.sound_index = build_index(lib)
            except Exception:
                log("index error", traceback.format_exc())
                self.sound_index = []
            self.indexing = False
            self.request_redraw()
        threading.Thread(target=work, daemon=True).start()

    def pad_list(self):
        if not self.sound_index:
            return []
        m = None
        if self.pe["scope"] == "machine":
            m = (self.state.kit.get("library") or [None])[0] or self.pe.get("machine")
        return filter_index(self.sound_index, self.pe["group"], m)

    def draw_pad_editor(self):
        eng = self.audio.engine
        p = self.sel_pad
        src = eng.drums.sources[p] if p < len(eng.drums.sources) else {}
        where = os.path.basename(os.path.dirname(os.path.dirname(src["file"]))) if "file" in src else "built-in"
        self.overlay_base(f"Pad {p + 1} · {eng.drums.names[p]}", "TAP A SOUND TO PUT IT ON THIS PAD  ·  SILENCE AT THE START IS TRIMMED")
        # pad strip
        for i in range(16):
            bx = 34 + i * 76
            on = i == p
            self.rrect(bx, 150, 70, 46, 8, T["seg_active"] if on else T["btn_bg"])
            self.text(bx + 35, 164, str(i + 1), 12, T["accent"] if on else T["btn_text"], True)
            self.text(bx + 35, 184, eng.drums.names[i][:7].upper(), 8, T["ink_dim"])
            self.hit(bx, 150, 70, 46, lambda j=i: self.pe_pick_pad(j))
        # categories
        for j, (g, _) in enumerate(GROUPS):
            y0 = 212 + j * 50
            on = g == self.pe["group"]
            self.rect(34, y0, 200, 44, fill=T["seg_active"] if on else T["seg_inactive"])
            self.text(50, y0 + 22, g.upper(), 15, T["accent"] if on else T["ink"], on, "w")
            self.hit(34, y0, 200, 44, lambda gg=g: self.pe_group(gg))
        # sound list
        lib = self.audio.library()
        x0, w = 250, 690
        if not lib.ok():
            self.text(x0 + w / 2, 380, "Your Drum Machine Collection folder isn't set.", 16, T["ink_dim"])
            self.button(x0 + w / 2, 440, 340, 60, "PICK LIBRARY FOLDER", self.pick_library, px=16)
        elif self.sound_index is None:
            self.text(x0 + w / 2, 400, "Reading your collection...", 18, T["ink_dim"])
            self.ensure_index()
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
        # actions
        rx = 1100
        self.button(rx, 240, 300, 64, f"RANDOM {self.pe['group'].upper()}", self.pe_random, accent=True, px=17)
        self.button(rx, 318, 300, 56, "PLAY PAD", lambda: self.test_pad(p), px=17)
        scope_m = (self.state.kit.get("library") or [None])[0]
        self.seg(950, 366, 150, 44, ["all", "machine"], self.pe["scope"], self.pe_scope, vertical=False)
        self.text(rx, 422, ("ONLY " + scope_m.upper())[:30] if scope_m else "LOAD A MACHINE KIT TO USE 'MACHINE'", 10, T["ink_dim"])
        self.button(rx, 476, 300, 52, "FROM FILE...", self.pe_from_file, px=16)
        self.button(rx, 540, 300, 52, "SAVE AS MY KIT", lambda: self.open_overlay(("mykits",)), px=16)
        self.text(rx, 590, f"NOW: {where.upper()[:28]}", 10, T["ink_dim"])
        self.button(rx, 650, 300, 60, "DONE", self.close_overlay, px=18)

    def pe_pick_pad(self, i):
        self.sel_pad = i
        self.pe["group"] = PAD_GROUP[i]
        self.pe["scroll"] = 0
        self.test_pad(i)

    def pe_group(self, g):
        self.pe["group"] = g
        self.pe["scroll"] = 0

    def pe_scope(self, s):
        if s == "machine" and not self.state.kit.get("library"):
            self.show_toast("LOAD A DRUM MACHINE KIT FIRST")
            return
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
        self.state.mykits[i] = {"name": name, "from": src, "pads": [dict(x) for x in d.sources],
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
        if aid in ("rand_s1", "rand_s2"):
            pre = aid[-2:]
            self.random_sound(pre)
            self.show_toast(f"SYNTH {pre[1]}: {self.state.preset_name[pre].upper()}", 1.2)
        elif aid in ("next_s1", "next_s2"):
            pre = aid[-2:]
            self.preset_step(pre, 1)
            self.show_toast(f"SYNTH {pre[1]}: {self.state.preset_name[pre].upper()}", 1.2)
        elif aid == "rand_kit":
            if self.audio.library().ok():
                self.random_machine()
            else:
                import random as _r
                self.select_kit("factory", _r.randrange(len(kits.KITS)))
                self.show_toast(self.audio.engine.drums.kit_name.upper(), 1.2)
        elif aid in ("next_kit", "prev_kit"):
            self.kit_step(1 if aid == "next_kit" else -1)
            self.show_toast(self.audio.engine.drums.kit_name.upper()[:34], 1.2)
        elif aid in ("next_tab", "prev_tab"):
            cur = tabs.index(self.state.page) if self.state.page in tabs else 0
            self.set_page(tabs[(cur + (1 if aid == "next_tab" else -1)) % len(tabs)])
        elif aid.startswith("tab:"):
            self.set_page(aid[4:])
        elif aid == "panic":
            self.panic()
        elif aid == "rec":
            self.toggle_rec()
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
            self.action_q.append({10: "rec", 11: "rand_s1", 12: "rand_s2", 13: "rand_kit", 14: "next_kit",
                                  15: "tab:" + self.state.last_tab}[i])
        self.request_redraw()

    def scene_hold(self, on):
        p = self.state.params
        if on:
            if not (p.scenes.get("A") and p.scenes.get("B")):
                self.show_toast("SAVE SCENE A AND B FIRST")
                return
            if self.midi.scene_hold is None:
                self.midi.scene_hold = p.norm["sc.morph"]
            p.set_norm("sc.morph", 1.0)
        elif self.midi.scene_hold is not None:
            p.set_norm("sc.morph", self.midi.scene_hold)
            self.midi.scene_hold = None
        self.state.dirty = True

    def save_scene(self, which):
        self.state.params.save_scene(which)
        p = self.state.params
        self.state.dirty = True
        n = len(p.scene_keys)
        self.show_toast(f"SCENE {which} SAVED" + (f" · {n} SETTINGS DIFFER" if p.scenes.get("A") and p.scenes.get("B") else ""))

    def set_morph(self, x):
        self.state.params.set_norm("sc.morph", x)
        self.state.dirty = True

    def mini_knob(self, idx, cx, cy, key):
        p = self.state.params
        n = p.shown(key)
        r = 19
        hot = time.time() - self.midi.flash[idx] < 0.35
        X, Y = self.X, self.Y
        self.cv.create_oval(X(cx - r), Y(cy - r), X(cx + r), Y(cy + r), fill=T["knob_face"],
                            outline=T["accent"] if hot else T["knob_ring"], width=max(1, int(2 * self.scale)))
        a = math.radians(225 - 270 * n)
        dx, dy = cx + (r - 7) * math.cos(a), cy - (r - 7) * math.sin(a)
        self.cv.create_oval(X(dx - 4), Y(dy - 4), X(dx + 4), Y(dy + 4), fill=T["knob_dot"], outline="")
        lab = SPECS[key].label
        lab = {"Build-Up": "Build-up", "Dub Throw": "Dub throw"}.get(lab, lab)
        if key.startswith("lp.t"):
            lab = lab.replace("Track ", "T")
        if key.startswith("dr.p"):
            pn = int(key.split(".")[1][1:]) - 1
            lab = f"{self.audio.engine.drums.names[pn][:7]} {lab.lower()}"
        if key[:2] in ("s1", "s2") and "Synth" not in lab:
            lab = key[:2].upper() + " " + lab
        self.text(cx, cy + r + 15, lab[:13], 11, T["ink"], True)
        self.text(cx, cy + r + 31, SPECS[key].fmt(p.val[key])[:12], 12, T["accent"] if hot else T["ink_dim"])
        self.text(cx - r - 2, cy - r, str(idx + 1), 9, T["ink_faint"], False, "e")
        self.hit(cx - 38, cy - r - 8, 76, 2 * r + 46, lambda k=key: k, "knob")

    def draw_live(self):
        eng = self.audio.engine
        p = self.state.params
        self.frame(14, 100, 1252, 372, "Live",
                   "BEATSTEP PADS HERE: 1-8 EFFECTS · 9 FILL · 10 SCENE B · 11 REC · 12-15 RANDOM / KITS · 16 BACK")
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
            self.text(x0 + 72, 430, f"PAD {i + 1}", 11, T["btn_text"] if on else T["ink_dim"], True)
            self.hit(x0, 276, 143, 180, lambda on, j=i: self.live_pad(j, on), "hold")
        # scenes
        y = 482
        self.frame(14, y, 626, 250, "Scenes", "SAVE A · CHANGE THINGS · SAVE B · THEN MORPH")
        A, B = p.scenes.get("A"), p.scenes.get("B")
        self.button(92, y + 82, 130, 56, "SAVE A", lambda: self.save_scene("A"), accent=not A, px=17)
        self.button(562, y + 82, 130, 56, "SAVE B", lambda: self.save_scene("B"), accent=not B, px=17)
        x0, x1 = 172, 482
        self.rect(x0, y + 72, x1 - x0, 20, fill=T["well"], outline=T["line"])
        m = p.norm["sc.morph"]
        self.rect(x0, y + 72, (x1 - x0) * m, 20, fill=T["accent"])
        hx = x0 + (x1 - x0) * m
        self.rrect(hx - 9, y + 62, 18, 40, 5, T["knob_dot"])
        self.text((x0 + x1) / 2, y + 120, f"MORPH {m * 100:.0f}%  ·  BEATSTEP KNOB 1", 12, T["ink_dim"], True)
        self.hit(x0 - 10, y + 52, x1 - x0 + 20, 60, self.set_morph, "slider")
        if A and B:
            k = len(p.scene_keys)
            info = f"{k} setting{'' if k == 1 else 's'} differ{'s' if k == 1 else ''} between A and B"
        else:
            info = "A: " + ("saved" if A else "empty") + "   ·   B: " + ("saved" if B else "empty")
        self.text(327, y + 152, info, 13, T["ink_dim"])
        on = self.midi.scene_hold is not None
        self.rrect(40, y + 176, 560, 60, 12, T["btn_on"] if on else T["btn_bg"])
        self.text(320, y + 206, "HOLD FOR SCENE B  ·  PAD 10", 17, T["btn_text"], True)
        self.hit(40, y + 176, 560, 60, self.scene_hold, "hold")
        # record
        rec = eng.recorder
        self.frame(650, y, 300, 250, "Record", "")
        self.button(800, y + 92, 260, 76, "STOP RECORDING" if rec else "● RECORD", self.toggle_rec, accent=True, px=19)
        self.seg(670, y + 146, 130, 34, ["MIX ONLY", "MIX + STEMS"], "MIX + STEMS" if self.state.rec_stems else "MIX ONLY",
                 self.pick_stems, vertical=False)
        if rec:
            sec = int(rec.seconds())
            self.text(800, y + 206, f"{sec // 60:02d}:{sec % 60:02d}  ·  PAD 11 STOPS", 14, "#d9534f", True)
        else:
            self.button(800, y + 212, 260, 40, "OPEN RECORDINGS FOLDER", self.open_recordings, px=12)
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
        name, bpm, swing, steps, kit, fill, parts = GENRES[g % len(GENRES)]
        eng.beats.beat = Beat(g, bars=self.state.beat_bars)
        if self.state.beat_kit:
            self.select_kit("factory", kit, preview=False)
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
            bp.beat = Beat(g, bars=self.state.beat_bars)
            self.beat_save()
        elif i in (2, 3):
            self.action_q.append(("genre", (g + (1 if i == 3 else -1)) % len(GENRES)))
        elif i == 5:
            bp.beat.mutate()
            self.beat_save()
        elif i in (6, 7):
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

    def beat_cell(self, role, step):
        bp = self.audio.engine.beats
        bp.beat.toggle(role, step)
        self.beat_save()

    def draw_beats(self):
        eng = self.audio.engine
        bp = eng.beats
        b = bp.beat
        gname, gbpm, gswing, steps, gkit, _, _ = GENRES[b.genre]
        self.frame(14, 100, 1252, 632, "Beats",
                   "PADS HERE: 1 PLAY · 2 NEW BEAT · 3/4 GENRE · 5 FILL · 6 MUTATE · 7/8 SIMPLER/BUSIER · 9-12 MUTES · 15 SEND · 16 BACK")
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
        self.button(105, cy, 150, 60, "STOP" if running else "▶ PLAY", lambda: self.beat_pad(0, True), accent=not running, px=20)
        self.button(275, cy, 170, 60, "NEW BEAT", lambda: self.beat_pad(1, True), accent=True, px=19)
        self.button(440, cy, 140, 60, "NEW ENDING", self.beat_new_ending, px=14)
        self.button(578, cy, 116, 60, "MUTATE", lambda: self.beat_pad(5, True), px=14)
        self.button(698, cy, 104, 60, "SIMPLER", lambda: self.beat_pad(6, True), px=13)
        self.button(808, cy, 96, 60, "BUSIER", lambda: self.beat_pad(7, True), px=13)
        fon = eng.fill or ("fill",) in self.live_held
        self.rrect(862, cy - 30, 130, 60, 12, T["btn_on"] if fon else T["btn_bg"])
        self.text(927, cy - 6, "HOLD FOR", 11, T["btn_text"], True)
        self.text(927, cy + 12, "FILL", 18, T["btn_text"], True)
        self.hit(862, cy - 30, 130, 60, lambda on: self.beat_pad(4, on), "hold")
        if self.send_countdown:
            sl = f"PRESS REC · STARTS IN {max(0, int(self.send_countdown - time.time()) + 1)}"
        else:
            sl = {"armed": "WAITING FOR STEP 1" if self.state.clock_master else "WAITING FOR REC + PLAY",
                  "sending": f"SENDING {bp.sent}/{b.steps}"}.get(bp.send, "SEND TO BEATSTEP")
        self.button(1130, cy, 250, 60, sl, lambda: self.beat_pad(14, True), accent=not bp.send, on=bool(bp.send), px=15)
        cy2 = 664
        for k, grp in enumerate(GROUP_NAMES):
            self.button(76 + k * 96, cy2, 90, 44, ("MUTED " if grp in bp.mutes else "") + grp.upper(),
                        lambda kk=k: self.beat_pad(8 + kk, True), on=grp in bp.mutes, px=11 if grp in bp.mutes else 12)
        live = self.clock_live()
        self.button(456, cy2, 44, 44, "−", lambda: self.beat_tempo(-1), px=20)
        self.readout(534, cy2, 104, 44, f"{eng.bpm:.0f} BPM")
        self.button(612, cy2, 44, 44, "+", lambda: self.beat_tempo(1), px=20)
        self.button(732, cy2, 176, 44, f"LENGTH: {b.steps // 16} BAR{'S' if b.steps > 16 else ''}", self.beat_bars_step,
                    on=b.steps > 16, px=13)
        self.button(916, cy2, 176, 44, "GENRE KIT: ON" if self.state.beat_kit else "GENRE KIT: OFF", self.toggle_beat_kit,
                    on=self.state.beat_kit, px=13)
        self.button(1130, cy2, 240, 44, "CLOCK OUT TO BEATSTEP: ON" if self.state.clock_master else "CLOCK OUT TO BEATSTEP: OFF",
                    self.toggle_clock_master, on=self.state.clock_master, px=13)
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

    def beat_bars_step(self):
        bp = self.audio.engine.beats
        i = BAR_CHOICES.index(self.state.beat_bars) if self.state.beat_bars in BAR_CHOICES else 1
        self.state.beat_bars = BAR_CHOICES[(i + 1) % len(BAR_CHOICES)]
        bp.beat = Beat(bp.beat.genre, bars=self.state.beat_bars)
        self.beat_save()
        n = self.state.beat_bars
        self.show_toast(f"{n} BAR{'S' if n > 1 else ''} · {bp.beat.steps} STEPS")

    def beat_new_ending(self):
        bp = self.audio.engine.beats
        bp.beat.new_ending()
        self.beat_save()
        self.show_toast("NEW ENDING: " + bp.beat.turn_text().upper())

    def toggle_beat_kit(self):
        self.state.beat_kit = not self.state.beat_kit
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
            self.text(x0 + 96, y0 + 126, "TAP TO", 10, "#111111" if col else T["ink_dim"], True)
            self.text(x0 + 96, y0 + 160, nxt, 30, "#111111" if col else T["btn_text"], True)
            self.text(x0 + 96, y0 + 200, f"PAD {i + 1}", 11, "#111111" if col else T["ink_dim"], True)
            self.hit(x0 + 14, y0 + 106, 164, 120, lambda j=i: self.loop_pad(j, True))
            held = i in self.loop_held
            self.rrect(x0 + 14, y0 + 236, 164, 62, 12, T["btn_on"] if held else T["btn_bg"])
            self.text(x0 + 96, y0 + 258, "STOP", 18, T["btn_text"], True)
            self.text(x0 + 96, y0 + 282, f"HOLD = CLEAR · PAD {9 + i}", 10, T["btn_text"] if held else T["ink_dim"], True)
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
    RS_SOURCES = {"Synth 1": "s1", "Synth 2": "s2", "Both synths": "synths", "Everything": "all"}
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

    def draw_tabs(self):
        self.rect(0, 742, W, 58, fill=T["well"])
        tw = W / len(TABS)
        for i, name in enumerate(TABS):
            x = i * tw
            on = name == self.state.page
            if on:
                self.rect(x + 4, 746, tw - 8, 50, fill=T["tab_on"])
                self.rect(x + 4, 742, tw - 8, 4, fill=T["accent"])
            self.text(x + tw / 2, 771, name.upper(), 16, T["tab_on_tx"] if on else T["chrome_ink"], on)
            self.hit(x, 742, tw, 58, lambda n=name: self.set_page(n))

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
        self.text(34, 498, "BUFFER (SMALLER = LESS LAG)", 12, T["ink_dim"], False, "w")
        self.seg(34, 512, 110, 44, [64, 128, 256, 512], self.state.blocksize, self.pick_buffer, vertical=False)
        lat = f"{self.audio.latency_ms:.1f} ms" if self.audio.stream else "-"
        self.readout(650, 534, 220, 44, f"LAG {lat}")
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
        self.button(940, 670, 220, 80, "ALL NOTES OFF", self.panic, px=18)
        self.button(1160, 670, 170, 80, "PAD ACTIONS", lambda: self.open_overlay(("actions",)), accent=True, px=16)

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

    def set_page(self, name):
        self.overlay = None
        if name == self.state.page and name in SUBPAGES:
            self.state.subpage[name] = (self.state.subpage.get(name, 0) + 1) % len(SUBPAGES[name])
        if name != self.state.page:
            if self.state.page not in OWN_SCREEN_PAGES:
                self.state.last_tab = self.state.page
            if name in NO_LOCK_PAGES:
                self.lock_off()
        self.state.page = name
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

    def init_keys(self, page):
        """Keys reset by the INIT button on a synth page: Main = the whole synth (all 3 pages),
        Osc+ = that page's own controls, Mod = LFOs, mod envelope and all 8 slots (routing + amount)."""
        pre = "s1" if page.startswith("Synth 1") else "s2"
        main = PAGES["Synth 1" if pre == "s1" else "Synth 2"]
        if page.endswith("Mod"):
            tail = ("l1shape", "l1rate", "l1sync", "l2shape", "l2rate", "l2sync", "mea", "med")
            keys = [f"{pre}.{t}" for t in tail]
            for j in range(1, 9):
                keys += [f"{pre}.m{j}src", f"{pre}.m{j}dst", f"{pre}.m{j}amt"]
            return keys
        if page.endswith("Osc+"):
            return [k for k in PAGES[page] if k not in main]
        if page.endswith("Arp"):
            return [k for k in SPECS if k.startswith(pre + ".arp")]
        return [k for k in SPECS if k.startswith(pre + ".")]

    def init_label(self):
        page = self.page_name()
        if page.endswith("Mod"):
            return "INIT MODULATION"
        if page.endswith("Osc+"):
            return "INIT OSC+ PAGE"
        if page.endswith("Arp"):
            return "INIT ARP"
        return "INIT " + page.upper()

    def init_page(self):
        self.lock_pick_clear()
        page = self.page_name()
        p = self.state.params
        keys = self.init_keys(page)
        before = {k: p.norm[k] for k in keys}
        for k in keys:
            p.set_val(k, SPECS[k].default)
        p.clear_locks(keys)
        if not (page.endswith("Mod") or page.endswith("Osc+") or page.endswith("Arp")):
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
        p.scenes = {"A": None, "B": None}
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
            self.loop_tick()
            self.beat_tick()
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
            self.state.save()
            self.midi.close_all()
            self.audio.stop()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        App().run()
    except Exception:
        log("fatal", traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
