"""Screenshots for the manual: Vintage look, Barlow Semi Condensed standing in for Bahnschrift,
stand-in audio and MIDI device names (nothing from a real PC)."""
import sys, os, time, subprocess
os.environ["HOME"] = "/tmp/pbhome"; os.environ["APPDATA"] = "/tmp/pbhome/AppData"
OUT = sys.argv[1]; S = 2  # capture at 2x for print
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, "/home/claude/potentialbox")
from potentialbox import app as A
from potentialbox.beats import Beat

class FakeStream:
    latency = (0.0053, 0.0053)
DEVS = [dict(index=0, name="Audio Interface ASIO", hostapi="ASIO", exclusive=False, label="ASIO  ·  Audio Interface ASIO"),
        dict(index=1, name="Speakers", hostapi="Windows WASAPI", exclusive=True, label="WASAPI EXCLUSIVE (low lag)  ·  Speakers"),
        dict(index=1, name="Speakers", hostapi="Windows WASAPI", exclusive=False, label="WASAPI  ·  Speakers"),
        dict(index=2, name="Headphones", hostapi="Windows WASAPI", exclusive=False, label="WASAPI  ·  Headphones"),
        dict(index=3, name="Speakers", hostapi="Windows DirectSound", exclusive=False, label="DirectSound  ·  Speakers")]
def fake_start(self, dev=None):
    self.stream = FakeStream(); self.error = ""; self.label = "ASIO · Audio Interface ASIO"; self.latency_ms = 5.3
    self.max_in = 8; self.in_chans = self.state.loop_input; self.underruns = 0
    self.state.device = {k: DEVS[0][k] for k in ("name", "hostapi", "exclusive", "label")}
    return True
A.Audio.start = fake_start
A.Audio.devices = lambda self: list(DEVS)
A.Audio.busy = lambda self: False
PORTS = ["Arturia BeatStep Pro", "Arturia BeatStep Pro MIDIIN2"]
A.Midi.names = lambda self: list(PORTS)
A.Midi.open = lambda self, n: self.ports.__setitem__(n, None)
A.Midi.close = lambda self, n: self.ports.pop(n, None)
A.Midi.open_out = lambda self: False
def fonts(self):
    self.fam = "Barlow Semi Condensed"; self.fam_b = "Barlow Semi Condensed SemiBold"; self.fonts = {}; self._fit = {}
A.App.pick_fonts = fonts
_text = A.App.text
def text(self, x, y, s, *a, **k):  # no sandbox paths in the pictures
    if "pbhome" in str(s).lower():
        s = "24 MACHINES  ·  DOWNLOADS \\ DRUM MACHINE COLLECTION"
    return _text(self, x, y, s, *a, **k)
A.App.text = text

app = A.App(); r = app.root
r.geometry(f"{1280*S}x{800*S}+0+0")
A.apply_look("vintage"); app.state.look = "vintage"; app.pick_fonts(); r.configure(bg=A.T["bg"]); app.cv.configure(bg=A.T["bg"])
for _ in range(30): r.update(); time.sleep(0.02)
app.audio.start(); app.midi.open_all(); app.midi.last_clock = time.perf_counter()
eng = app.audio.engine; p = app.state.params
eng.bpm = 124.0
app.select_kit("factory", 2, preview=False)

def shot(name, setup=None, page=None, sub=None, overlay=None, wait=0.05):
    app.overlay = None; app.toast = ("", 0)
    if page: app.state.page = page
    if sub is not None: app.state.subpage[page] = sub
    if setup: setup()
    if overlay: app.open_overlay(overlay)
    app.toast = ("", 0)
    app.draw(); r.update(); time.sleep(wait); app.draw()
    for it in app.cv.find_all():  # no sandbox paths in the pictures
        if app.cv.type(it) == "text":
            t = app.cv.itemcget(it, "text")
            if "PBHOME" in t.upper():
                app.cv.itemconfigure(it, text="24 MACHINES  ·  DOWNLOADS \\ DRUM MACHINE COLLECTION")
    r.update(); time.sleep(0.05)
    subprocess.run(["import", "-window", "root", "-crop", f"{1280*S}x{800*S}+0+0", os.path.join(OUT, name + ".png")], check=True)
    print("shot", name)

flash = lambda *idx: [app.midi.flash.__setitem__(i, time.time() + 30) for i in idx]
# --- knob pages
shot("perform", page="Perform", setup=lambda: (flash(1), eng.s1.amp.gate_on()))
eng.s1.amp.stage = 0
for t, subs in A.SUBPAGES.items():
    for i, (lab, pg) in enumerate(subs):
        nm = (t + "-" + lab).lower().replace(" ", "").replace("/", "").replace("+", "plus")
        shot(nm, page=t, sub=i)
for t in ("Macros",):
    shot("macros", page=t, setup=lambda: setattr(app, "last_macro", 11))
# --- step locks
def locks():
    app.state.subpage["Synth 1"] = 0
    app.lock_mode = True; app.lock_pick(2); p.set_val("s1.cutoff", 2400); p.set_norm("s1.reso", 0.7)
    app.lock_pick(10); p.set_val("s1.cutoff", 600); app.lock_pick(2)
shot("locks", page="Synth 1", sub=0, setup=locks)
app.lock_off()
# --- beats
def beats():
    bp = eng.beats; bp.beat = Beat(1, seed=4, bars=2); app.beat_save(); bp.on = True; bp.step = 9
shot("beats", page="Beats", setup=beats)
# --- arrangement
def arr():
    for g, bars in ((1, 2), (1, 1), (2, 2), (0, 2), (1, 4)):
        eng.beats.beat = Beat(g, seed=g + bars, bars=bars); app.arr_add()
    eng.beats.beat = Beat(1, seed=4, bars=2)
    eng.beats.chain_on = True; eng.beats.on = True; eng.beats.chain_i = 2
shot("arrangement", page="Arrangement", setup=arr)
eng.beats.on = False; eng.beats.chain_on = False
# --- live
def live():
    p.set_val("s1.cutoff", 400); app.save_scene(1); p.set_val("s1.cutoff", 4000); p.set_norm("m.filter", 0.75); app.save_scene(2)
    p.set_norm("s2.pos", 0.8); app.save_scene(3); p.set_val("sc.dst", 2); app.set_morph(0.35); flash(0)
shot("live", page="Live", setup=live)
# --- loop
def loop():
    app.state.loop_input = [0, 1]; app.audio.in_chans = [0, 1]
shot("loop", page="Loop", setup=loop)
shot("loopinput", page="Loop", overlay=("loopinput",))
shot("myloops", page="Loop", overlay=("myloops",))
# --- setup + overlays
shot("setup", page="Setup")
shot("learn", page="Perform", setup=lambda: setattr(app.midi, "learn", 4))
app.midi.learn = None
shot("actions", page="Setup", overlay=("actions",))
shot("setups", page="Live", overlay=("setups",))
shot("resample", page="Live", overlay=("resample",))
shot("sounds", page="Perform", overlay=("sounds", "s1"))
shot("route", page="Synth 1", sub=2, overlay=("route", "s1", 2))
shot("kits", page="Perform", overlay=("kits",))
def lib():
    app.state.library_root = "/tmp/pbhome/Downloads/Drum Machine Collection"
    app.audio.lib = None
    app.pick_brand("Roland")
shot("machines", page="Perform", setup=lib, overlay=("machines",))
def machine():
    app.pick_brand("Roland"); app.pick_machine("Roland TR-808")
shot("machinekits", page="Perform", setup=machine, overlay=("machines",))
app.select_kit("factory", 2, preview=False)
def pad():
    app.open_pad_editor(0)
    for _ in range(100):
        if app.sound_index is not None: break
        time.sleep(0.05); r.update()
shot("pad", page="Perform", setup=pad, wait=0.3)
shot("mykits", page="Perform", overlay=("mykits",))
r.destroy()
