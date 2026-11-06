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

from potentialbox.engine import (Engine, ParamStore, SPECS, PAGES, PRESETS, MACROS, SUBPAGES, SUBPAGE_NAMES,  # noqa: E402
                                 HIDDEN_PAGES, MOD_SOURCES, MOD_DESTS)
from potentialbox import kits  # noqa: E402
from potentialbox.library import Library, map_kit, brand_of, build_index, filter_index, GROUPS, PAD_GROUP  # noqa: E402

APP = "PotentialBox"
VERSION = "1.5.0"
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
ACTIONS = [("rand_s1", "Random Synth 1"), ("rand_s2", "Random Synth 2"), ("rand_kit", "Random Drum Kit"),
           ("next_kit", "Next Kit"), ("prev_tab", "Previous Tab"), ("next_tab", "Next Tab"),
           ("tab:Perform", "Perform Tab"), ("tab:Synth 1", "Synth 1 Tab"), ("tab:Synth 2", "Synth 2 Tab"),
           ("tab:Drums 1-8", "Drums 1-8 Tab"), ("tab:Drums 9-16", "Drums 9-16 Tab"), ("tab:Mix", "Mix Tab"),
           ("next_s1", "Synth 1 Next Sound"), ("next_s2", "Synth 2 Next Sound"), ("tab:Macros", "Macros Tab"),
           ("panic", "All Notes Off")]
ACTION_NAMES = dict(ACTIONS)


def default_actions():
    """BeatStep Pro pads in CNTRL mode, MIDI channel 16, notes 36-51 -> the 16 actions in order."""
    return {aid: {"t": "note", "ch": 16, "n": 36 + i} for i, (aid, _) in enumerate(ACTIONS)}


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
    "Mix": [(0, 4, "Levels"), (4, 8, "Bus & DJ filter"), (8, 16, "Drum levels · pads 1-8")],
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
        self.subpage = {"Synth 1": 0, "Synth 2": 0}
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
                self.subpage[t] = int(sp.get(t, 0)) % 3
        self.midi_off = d.get("midi_off", [])
        self.bad_audio = [x for x in d.get("bad_audio", []) if isinstance(x, str)]
        self.audio_pending = d.get("audio_pending")

    def save(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            d = dict(params=self.params.norm, cc_map=self.cc_map, knob_mode=self.knob_mode, ch=self.ch,
                     device=self.device, blocksize=self.blocksize, kit=self.kit, recent=self.recent, library_root=self.library_root,
                     preset=self.preset, preset_name=self.preset_name, page=self.page, subpage=self.subpage, midi_off=self.midi_off,
                     bad_audio=self.bad_audio, audio_pending=self.audio_pending, actions=self.actions)
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
        for sr in rates:
            try:
                if sr != self.engine.sr:
                    self.rebuild_engine(sr)
                self.stream = sd.OutputStream(device=dev["index"], samplerate=sr, channels=2, dtype="float32",
                                              blocksize=self.state.blocksize, latency="low",
                                              extra_settings=extra, callback=self.callback)
                self.stream.start()
                self.latency_ms = float(self.stream.latency) * 1000.0
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
            self.ports[name] = mido.open_input(name, callback=self.on_msg)
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

    def on_msg(self, msg):
        try:
            self._handle(msg)
        except Exception:
            log("midi error", traceback.format_exc())

    def _handle(self, msg):
        app = self.app
        eng = app.audio.engine
        t = msg.type
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
        if t == "stop":
            eng.panic()
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
                if val > 0:
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
            return SUBPAGES[page][self.state.subpage.get(page, 0) % 3]
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
        n = p.shown(key)
        moved = abs(n - p.norm[key]) > 0.004
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
        shown = spec.fmt(p.val[key])
        if key[2:5] in (".l1", ".l2") and key.endswith("rate") and p.val[key[:5] + "sync"] >= 0.5:
            shown = "Synced"
        self.text(cx, cy + r + 46, shown, 15, T["accent"] if (hot or moved) else T["ink_dim"])
        self.text(cx - r - 4, cy - r - 2, str(idx + 1), 10, T["ink_faint"], False, "e")
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
        if self.page_name() in ("Perform", "Mix", "FX") and key[:2] in ("s1", "s2") and "Synth" not in lab:
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
        else:
            self.draw_knobs()
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
        msg, until = self.toast
        if msg and time.time() < until:
            self.rrect(300, 30, 430, 48, 12, T["btn_on"])
            self.text(515, 54, msg[:40], 16, T["btn_text"], True)

    def draw_header(self):
        self.rect(0, 0, W, 90, fill=T["bg"])
        self.text(24, 34, "POTENTIALBOX", 30, T["accent"], True, "w")
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
        if self.state.page in SUBPAGES:
            sub = "TAP THE TAB AGAIN (OR ITS PAD) FOR THE NEXT PAGE  ·  TAP LEFT / RIGHT OF A KNOB TO NUDGE"
            cur = SUBPAGE_NAMES[self.state.subpage.get(self.state.page, 0) % 3]
            self.seg(300, 105, 110, 32, SUBPAGE_NAMES, cur, self.pick_subpage, vertical=False)
        self.frame(14, 100, 1252, 372, self.state.page, sub)
        if mix and self.midi.learn is None:
            armed = time.time() - getattr(self, "reset_armed", 0) < 3
            self.button(680, 121, 320, 32, "TAP AGAIN TO RESET EVERYTHING" if armed else "RESET ALL TO INIT",
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
            r, c = divmod(i, 4)
            x0, y0 = 34 + c * 305, 212 + r * 116
            learning = self.midi.action_learn == aid
            hot = now - self.action_flash.get(aid, 0) < 0.4
            fill = T["btn_on"] if learning else (T["seg_active"] if hot else T["btn_bg"])
            self.rrect(x0, y0, 290, 104, 12, fill)
            self.text(x0 + 16, y0 + 24, str(i + 1), 12, T["ink_dim"], True, "w")
            self.text(x0 + 145, y0 + 44, name.upper(), 16, T["accent"] if hot else T["btn_text"], True)
            sub = "PRESS A PAD OR STEP NOW" if learning else self.trig_text(self.state.actions.get(aid))
            self.text(x0 + 145, y0 + 76, sub, 12, T["btn_text"] if learning else T["ink_dim"])
            self.hit(x0, y0, 290, 104, lambda a=aid: self.learn_action(a))
        self.button(250, 700, 420, 48, "RESET TO CHANNEL 16 DEFAULTS", self.reset_actions, px=14)

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
        self.request_redraw()

    def draw_tabs(self):
        self.rect(0, 742, W, 58, fill=T["well"])
        tw = W / len(TABS)
        for i, name in enumerate(TABS):
            x = i * tw
            on = name == self.state.page
            if on:
                self.rect(x + 4, 746, tw - 8, 50, fill=T["tab_on"])
                self.rect(x + 4, 742, tw - 8, 4, fill=T["accent"])
            self.text(x + tw / 2, 771, name.upper(), 17, T["tab_on_tx"] if on else T["chrome_ink"], on)
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
                             start=self.state.params.norm[h[4]()])
        elif h:
            h[4]()
            self.request_redraw()

    def on_motion(self, e):
        d = self.drag
        if not d:
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
            self.state.subpage[name] = (self.state.subpage.get(name, 0) + 1) % 3
        self.state.page = name
        self.state.dirty = True

    def pick_subpage(self, label):
        self.state.subpage[self.state.page] = SUBPAGE_NAMES.index(label)
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
        p = self.state.params
        for i in range(len(MACROS)):
            k = f"mc.{i + 1}"
            p.set_val(k, SPECS[k].default)
        self.state.dirty = True
        self.show_toast("MACROS BACK TO ZERO")

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
                self.run_action(self.action_q.popleft())
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
