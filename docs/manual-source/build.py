"""PotentialBox user manual: HTML -> PDF with headless Chrome. Knob, pad and genre tables come from the app's own
code, so they always match the version being documented.

    python3.12 build.py <potentialbox repo> <screenshots dir> <out.pdf>
"""
import os
import sys
import html
import subprocess

REPO, IMG, OUT = sys.argv[1], os.path.abspath(sys.argv[2]), os.path.abspath(sys.argv[3])
os.environ.setdefault("APPDATA", "/tmp/pbman")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from potentialbox.engine import PAGES, SPECS, MACROS, PRESETS, PUNCH_FX, DEFAULT_ROUTES, TABLE_NAMES, CHORDS  # noqa
from potentialbox import kits, beats  # noqa
from potentialbox.app import (VERSION, ACTIONS, PAD_ACTIONS, LIVE_PADS, LOOP_PADS, BEAT_PADS, KNOB_GROUPS,  # noqa
                              SUBPAGES, TABS, TAB_LABEL)
from desc import describe  # noqa

E = html.escape
H = []          # the document
CH = [0]        # chapter counter
TOC = []


def add(s):
    H.append(s)


def p(s):
    add(f"<p>{s}</p>")


def chapter(title, intro=None, newpage=True):
    CH[0] += 1
    TOC.append((CH[0], title))
    add(f'<section class="chapter{" np" if newpage else ""}"><h1><span class="num">{CH[0]}</span>{E(title)}</h1>')
    if intro:
        p(intro)


def end():
    add("</section>")


def h2(s):
    add(f"<h2>{E(s)}</h2>")


def h3(s):
    add(f"<h3>{E(s)}</h3>")


def img(name, caption="", cls=""):
    add(f'<figure class="{cls}"><img src="file://{IMG}/{name}.png"><figcaption>{caption}</figcaption></figure>')


def ul(items):
    add("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")


def steps(items):
    add('<ol class="steps">' + "".join(f"<li>{i}</li>" for i in items) + "</ol>")


def note(s, kind="tip"):
    add(f'<div class="note {kind}">{s}</div>')


def table(head, rows, cls=""):
    out = [f'<table class="{cls}"><thead><tr>' + "".join(f"<th>{E(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    add("".join(out))


def b(s):
    return f"<b>{E(s)}</b>"


def key(s):
    return f'<span class="key">{E(s)}</span>'


def label_for(page, k):
    lab = SPECS[k].label
    if k.startswith("dr.p"):
        pad = int(k.split(".")[1][1:])
        return f"Pad {pad} {lab.lower()}"
    if k[:2] in ("s1", "s2") and "Synth" not in lab and page in ("Perform", "Mix", "Mix EQ", "FX", "Track Mute/Solo",
                                                                    "Master FX", "Live", "Beats", "Arrangement"):
        lab = k[:2].upper() + " " + lab
    return lab


def group_of(page, i):
    for a, z, lab in KNOB_GROUPS.get(page, []):
        if a <= i < z:
            return lab.split(" · ")[0]
    return ""


def knob_table(page, with_desc=True, desc=None):
    rows = []
    for i, k in enumerate(PAGES[page]):
        if with_desc:
            d = (desc or {}).get(k) or describe(k, MACROS)
            rows.append((f'<span class="kn">{i + 1}</span>', b(label_for(page, k)), E(d)))
        else:
            rows.append((f'<span class="kn">{i + 1}</span>', b(label_for(page, k)), E(group_of(page, i))))
    table(["Knob", "Control", "What it does" if with_desc else "Group"], rows, "knobs" if with_desc else "knobs short")


def pads_table(names, head="Pad", what="Does"):
    half = (len(names) + 1) // 2
    rows = []
    for i in range(half):
        r = [f'<span class="kn">{i + 1}</span>', E(names[i])]
        if i + half < len(names):
            r += [f'<span class="kn">{i + half + 1}</span>', E(names[i + half])]
        else:
            r += ["", ""]
        rows.append(r)
    table([head, what, head, what], rows, "pads")


# ============================================================================ cover
add(f"""<section class="cover">
<div class="kicker">User manual</div>
<div class="title">POTENTIALBOX</div>
<div class="sub">A groovebox for Windows, played by the Arturia BeatStep Pro</div>
<div class="meta">Version {VERSION} · two synths · 16-pad drum sampler · beat generator · looper · ASIO</div>
<div class="shot"><img src="file://{IMG}/perform.png"></div>
<div class="foot"><span>by PotentialBreaks</span><span>Free and open source · MIT licence</span></div>
</section>""")
add("@@TOC@@")

# ============================================================================ 1 welcome
chapter("Welcome", "PotentialBox turns your Arturia BeatStep Pro into a complete groovebox. The BeatStep Pro is the "
        "sequencer and the controller; PotentialBox makes the sound on your Windows PC.", newpage=False)
ul([f"{b('Sequencer 1')} plays {b('Synth 1')}, an analog-style synth for basslines, acid, leads and supersaws.",
    f"{b('Sequencer 2')} plays {b('Synth 2')}, a wavetable synth for leads, pads and bells.",
    f"The {b('Drum sequencer')} plays a {b('16-pad drum sampler')}: 9 built-in kits, your own samples, and a browser "
    "for whole drum machine collections.",
    "Each synth has 2 LFOs (with a 16-step mode), a mod envelope, 12 mod slots, seven filter types, chords and an "
    "arpeggiator.",
    f"The {b('Beats')} tab makes beats in 24 genres and can record them straight into the BeatStep's drum sequencer; "
    f"the {b('Arrangement')} tab chains beats into a song.",
    f"The {b('Live')} tab has hold-to-play effects, 8 scenes you can morph between, recording to WAV and resampling.",
    f"The {b('Loop')} tab is a 5-track looper in the style of a BOSS RC-505.",
    "Step locks, mute and solo, side-chain ducking, EQ, delay, reverb and a master effects chain.",
    "The BeatStep's 16 knobs control the 16 knobs of whichever page is open, and its pads run actions on MIDI channel 16."])
p("Everything is pre-wired for the BeatStep Pro's factory settings, so you can plug it in and press play. Every control "
  "is a big key you can tap, and everything saves by itself: there is no typing anywhere in the app.")
note(f"<b>New in {VERSION}:</b> cleaner sound (no more crackles from the master effects), a real look-ahead limiter, "
     "a playable Arrangement, one-tap mute and solo, 8 working scenes, LOAD and DROPOUTS on the Setup tab. "
     "The full list is in the CHANGELOG file that comes with PotentialBox.")
end()

# ============================================================================ 2 what you need
chapter("What you need")
table(["You need", "Notes"], [
    (b("A Windows PC"), "Windows 10 or 11, 64-bit."),
    (b("An Arturia BeatStep Pro"), "Connected with USB. Factory MIDI settings work straight away."),
    (b("Internet, once"), "The installer downloads Python 3.12 and the audio libraries (about 150 MB). After that "
                          "PotentialBox works offline."),
    (b("Speakers or headphones"), "Any Windows audio output works.")])
h2("Nice to have")
table(["Optional", "Why"], [
    (b("An audio interface with an ASIO driver"), "The lowest lag between pressing play and hearing sound, and "
                                                  "inputs for the looper. Without one PotentialBox uses Windows audio (WASAPI)."),
    (b("A folder of drum samples"), "For example a drum machine collection: one folder per machine, named after the "
                                    "hardware. PotentialBox reads them where they are."),
    (b("Arturia MIDI Control Center"), "Arturia's free app, to put the BeatStep's Control Mode pads on MIDI channel 16 "
                                       "for pad actions (chapter 5).")])
end()

# ============================================================================ 3 installing
chapter("Installing")
steps([f"Download {b(f'PotentialBox-{VERSION}-windows.zip')} from the Releases page of the PotentialBox GitHub repository.",
       f"Right-click the zip and choose {b('Extract All')}. Open the extracted {b('PotentialBox')} folder.",
       f"Double-click {b('Install PotentialBox.bat')}.",
       f"Wait for the window to say {b('DONE')}. PotentialBox opens by itself, and there is a PotentialBox icon on "
       "your Desktop and in the Start menu (with a shortcut to this manual)."])
note("<b>“Windows protected your PC”?</b> PotentialBox is free and not code-signed, so Windows may show this the first "
     "time. Click <b>More info</b>, then <b>Run anyway</b>.")
h2("What the installer does")
ul(["Installs a private copy of Python 3.12 in your user folder if you don't have it. It doesn't change any other "
    "Python you have.",
    "Copies PotentialBox to <code>%LOCALAPPDATA%\\PotentialBox</code> and installs its libraries there: numpy, scipy, "
    "sounddevice (with ASIO), mido and python-rtmidi.",
    "Lists the ASIO outputs and MIDI inputs it can see, so you know the BeatStep was found.",
    "Adds the Desktop and Start menu shortcuts, then starts the app."])
h2("Updating")
p("Download the new release and run its <b>Install PotentialBox.bat</b>. The installer closes PotentialBox if it's open, "
  "updates it and keeps all your settings, sounds, kits, setups and loops.")
h2("Uninstalling")
p("Open <code>%LOCALAPPDATA%\\PotentialBox</code>, right-click <b>uninstall.ps1</b> and choose <b>Run with PowerShell</b>. "
  "This removes the app, its shortcuts <b>and your saved settings, sounds, kits and setups</b>, so copy them first if you "
  "want to keep them (chapter 23). Your recordings and loops in the Music folder stay. Python 3.12 stays too; remove it "
  "in Windows Settings &gt; Apps if you like.")
end()

# ============================================================================ 4 setup
chapter("First start: Setup", "Open the SETUP tab (bottom right) the first time you start PotentialBox.")
img("setup", "The Setup tab: audio outputs on the left, MIDI on the right, knob settings at the bottom.")
h2("Audio output")
p("Tap an output to use it. The list is sorted best first:")
table(["Output type", "When to use it"], [
    (b("ASIO"), "Lowest lag. Choose your audio interface's own ASIO driver. PotentialBox picks it by itself the first "
                "time, ahead of generic drivers like ASIO4ALL."),
    (b("WASAPI EXCLUSIVE"), "Very low lag with no extra driver. Other apps go quiet while PotentialBox uses the output."),
    (b("WASAPI"), "Works everywhere, with a little more lag. Other apps keep playing.")])
h3("Buffer, lag, load and dropouts")
ul([f"{b('BUFFER')} sets the lag: smaller is faster. 128 or 256 is a good start; 1024 and 2048 are there for slow PCs.",
    f"{b('LAG')} shows the result in milliseconds.",
    f"{b('LOAD')} shows how much of each buffer's time the sound takes to make. Keep it well under 100% (it turns red above 70%).",
    f"{b('DROPOUTS')} counts the buffers the sound card had to play without fresh sound. Each one is a crackle. "
    "If it climbs, tap the next buffer size up."])
note("<b>ASIO busy?</b> Many interfaces let only one app use their ASIO driver at a time. If a DAW, FL Studio or "
     "Voicemeeter is open, PotentialBox can't get the driver, so it plays through Windows audio and tells you why. Close "
     "the other app, then tap the ASIO output again.")
p("If an output ever freezes, PotentialBox remembers it, skips it next time and marks it (DID NOT RESPOND). "
  "Tapping it again tries it once more.")
h2("MIDI in")
p("PotentialBox finds the BeatStep Pro by itself and listens to every port it offers. Tap a port to switch it off or on, "
  "and tap <b>RESCAN MIDI</b> after plugging in. The channel boxes set which MIDI channel plays each instrument "
  "(factory: Synth 1 = 1, Synth 2 = 2, Drums = 10).")
h2("Look")
p("The <b>LOOK</b> key (bottom right) steps through the looks: <b>Print Plate</b> (the default), <b>Night Rack</b>, "
  "<b>Colour Block</b> and <b>Vintage</b> (used for the pictures in this manual). The change shows at once and is remembered. "
  "If you make a file called <code>user-look.json</code> in <code>%APPDATA%\\PotentialBox</code>, it becomes a fifth "
  "look the next time PotentialBox starts; any colour it leaves out comes from Print Plate.")
end()

# ============================================================================ 5 beatstep
chapter("Setting up the BeatStep Pro")
h2("The sequencers")
p("Nothing to set up: on factory settings Sequencer 1 sends on channel 1, Sequencer 2 on channel 2 and the Drum "
  "sequencer on channel 10 with notes 36-51, which is exactly what PotentialBox listens to.")
ul(["Press PLAY on the BeatStep Pro. PotentialBox follows its tempo (shown in the header), so the delay, LFOs, arp and "
    "step locks always land on the beat.",
    "Stop also sends All Notes Off, so no note hangs.",
    "Tied and slid steps glide from note to note. Set the slide time with the synth's Glide knob.",
    "Swing, randomness and probability are the BeatStep's own: they change the pattern before PotentialBox plays it."])
h2("The knobs: Control Mode")
p("The knobs only send to PotentialBox in Control Mode. Press <b>CONTROL MODE</b> on the BeatStep Pro; the sequencers "
  "keep playing. Turn a knob and the matching knob on screen lights up.")
p("If a knob does nothing, open SETUP, tap <b>LEARN KNOBS</b> and turn knobs 1 to 16 in order (top row first). "
  "<b>FACTORY CCs</b> undoes this. If your knobs send relative values (set in MIDI Control Center), switch "
  "<b>KNOB MODE</b> to RELATIVE.")
img("learn", "LEARN KNOBS: turn each BeatStep knob when asked.", "small")
h2("The pads: channel 16")
p("To use the pads for pad actions (chapter 22), set the BeatStep Pro's Control Mode pads to MIDI channel 16 in "
  "Arturia's free MIDI Control Center app. Out of the box pads 1-16 send notes 36-51, which PotentialBox already "
  "expects. Any other notes or CCs work too: assign them in SETUP &gt; PAD ACTIONS.")
end()

# ============================================================================ 6 the screen
chapter("The screen")
img("perform", "The Perform tab with the BeatStep Pro connected.")
h2("Header")
ul([f"{b('AUDIO')}: the output in use and its lag. Messages also pop up here for a moment.",
    f"{b('MIDI')}: whether the BeatStep Pro is connected. The light flashes when MIDI arrives.",
    f"{b('TEMPO')}: the tempo PotentialBox is playing at. {b('LEVEL')}: the output meter (red means you are pushing the "
    "limiter or soft clip)."])
h2("Tabs and pages")
p("The tabs along the bottom choose what the 16 knobs control. The knob area is laid out like the BeatStep's knobs: "
  "top row 1-8, bottom row 9-16, in labelled groups. Some tabs have more than one page: the page keys sit at the top "
  "of the knob area, and tapping the tab again goes to the next page.")
table(["Tab", "Pages"], [(b(TAB_LABEL.get(t, t)) + ("" if TAB_LABEL.get(t, t) == t else f" ({E(t)})"),
                          " · ".join(lab.upper() for lab, _ in SUBPAGES[t])) for t in TABS if t in SUBPAGES])
h2("Using the controls")
ul(["Tap the left or right half of a knob to step it down or up, drag up and down, or use the mouse wheel.",
    "The coloured ring round a knob shows its value. Settings that go both ways (pan, EQ, tuning) fill from the top.",
    f"Settings that are just on or off (mute, solo, hard sync, arp hold, glide mode) are {b('one-tap keys')} instead of "
    "knobs. The BeatStep knob for that spot still switches them.",
    "A knob that a macro is moving shows a small ring where your own setting is.",
    f"{b('STEP LOCKS')} (top right of the knob area) gives a knob a different value on each step: chapter 19. A small L on "
    "a knob means it has step locks."])
h2("Keyboard shortcuts")
table(["Keys", "What they do"], [
    (key("Ctrl") + " + " + key("Z"), "Undo the last change: a whole knob turn, sound load or scene load at a time."),
    (key("Ctrl") + " + " + key("Y"), "Redo."),
    (key("Ctrl") + " + " + key("1") + " … " + key("9"), " · ".join(TAB_LABEL.get(t, t) for t in TABS[:9]) + "."),
    (key("F11"), "Full screen on and off."),
    (key("Esc"), "Closes a menu.")])
h2("The three panels")
p("Under the knobs, Synth 1, Synth 2 and Drums each have a panel. The light next to a synth's name shows when it is "
  "playing; drum pads light up when they hit. The keys are explained in chapters 11 and 12.")
end()

# ============================================================================ 7 synth 1
chapter("Synth 1", "An analog-style synth: two oscillators that blend from saw to square, a supersaw, a sub "
        "oscillator, a resonant filter with its own envelope, and drive. It is played by Sequencer 1.")
p("The Synth 1 tab has eight pages: MAIN, OSC+, MOD, MOD2, ARP+, ENV and the two LFO step pages. This chapter covers "
  "MAIN, OSC+ and ENV; chapter 9 covers modulation and chapter 10 the arpeggiator.")
note("<b>Start again in one tap:</b> each page has an <b>INIT</b> key beside the page keys. On MAIN it resets the whole "
     "synth; on every other page it resets only that page (INIT OSC+ PAGE, INIT MODULATION, INIT ARP, INIT ENVELOPES, "
     "INIT LFO STEPS). Afterwards <b>UNDO INIT</b> appears for a few seconds.")
img("synth1-main", "Synth 1, MAIN page.")
h2("MAIN page")
knob_table("Synth 1")
h2("OSC+ page")
img("synth1-oscplus", "Synth 1, OSC+ page.")
knob_table("Synth 1 Osc+")
h2("ENV page")
p("All the envelopes in one place, including the multi-stage amp envelope: with Decay 2 above zero the note falls to "
  "Sustain over Decay, then moves on to Sustain 2 over Decay 2 (a pluck that settles into a quieter pad, for example).")
img("synth1-env", "Synth 1, ENV page.")
knob_table("Synth 1 Env")
end()

# ============================================================================ 8 synth 2
chapter("Synth 2", "A wavetable synth: tables that morph as you move the wave position, an LFO that sweeps it, two "
        "detuned unison voices in stereo, and a resonant filter. It is played by Sequencer 2.")
p("Synth 2 has the same eight pages as Synth 1.")
img("synth2-main", "Synth 2, MAIN page.")
h2("MAIN page")
knob_table("Synth 2")
h2("OSC+ page")
img("synth2-oscplus", "Synth 2, OSC+ page.")
knob_table("Synth 2 Osc+")
h2("ENV page")
knob_table("Synth 2 Env")
h2("The 30 wavetables")
p("<b>Built in:</b> Analog (sine to triangle to saw to square), Vowel, Harmonic, PWM, FM Bell, Digital.")
p("<b>From the AKWF collection</b> (each morphs through 16 related single-cycle waves): " + ", ".join(TABLE_NAMES[6:30]) + ".")
p("<b>Your own:</b> put single-cycle WAV files in <code>%APPDATA%\\PotentialBox\\Wavetables</code> and restart "
  "PotentialBox. Each file is added after the 30 built-in tables, named after the file.")
end()

# ============================================================================ 9 modulation
chapter("Modulation, step LFOs and chords", "Modulation makes a sound move by itself: a wobbling filter, vibrato, a "
        "sweeping wavetable, auto-pan. Each synth has its own, on its MOD, MOD2 and LFO step pages.")
img("synth1-mod", "Synth 1, MOD page: LFOs and mod envelope on top, mod slots 1-8 below.")
h2("The movers")
ul([f"{b('LFO 1')} and {b('LFO 2')}: Sine, Triangle, Saw up, Saw down, Square, Random, Smooth random or Step. Set the "
    "speed in Hz, or lock them to the tempo with sync (4 bars down to 1/32, plus triplets).",
    f"The {b('mod envelope')} rises and falls once on every new note: sweeps, zaps and plucks.",
    "Four more sources need no setting up: the amp envelope, the step's velocity, the note itself (higher notes give "
    "more) and Random (a new value on every note)."])
h2("Mod slots")
p("Each synth has <b>12 mod slots</b>; each connects one source to one target. Slots 1-8 are the bottom row of the MOD "
  "page and slots 9-12 start the MOD2 page. Each knob is labelled with its routing, for example “LFO 1 &gt; Cutoff”.")
ul(["All amounts start at 0, so nothing moves until you turn one up. A negative amount turns the movement upside down.",
    "Tap a slot's label to choose a different source and target. Slots 9-12 start empty.",
    "INIT MODULATION puts both LFOs, the mod envelope and all 12 slots back to how they started."])
img("route", "The routing menu: tap a source, tap a target. CLEAR SLOT switches the slot off.", "small")
rows = []
for j in range(8):
    a, z = DEFAULT_ROUTES["s1"][j], DEFAULT_ROUTES["s2"][j]
    rows.append((f'<span class="kn">{j + 1}</span>', f"{a[0]} &gt; {a[1]}", f"{z[0]} &gt; {z[1]}"))
rows.append(('<span class="kn">9-12</span>', "empty", "empty"))
table(["Slot", "Synth 1", "Synth 2"], rows, "knobs short")
from potentialbox.engine import MOD_DESTS, MOD_SOURCES  # noqa
p(f"<b>Sources:</b> {', '.join(MOD_SOURCES[1:])}.")
p(f"<b>Synth 1 targets:</b> {', '.join(MOD_DESTS['s1'])}. <b>Synth 2 targets:</b> {', '.join(MOD_DESTS['s2'])}.")
h2("MOD2 page")
img("synth1-mod2", "Synth 1, MOD2 page.")
knob_table("Synth 1 Mod 2")
h2("Step LFOs")
p("Set an LFO's shape to <b>Step</b> and it plays the 16 knobs of its step page (LFO1 STEPS or LFO2 STEPS) one after "
  "another, from -100% to +100%: a little 16-step sequence for the filter, the pitch, the pan or anything else.")
steps(["On the MOD page, set LFO 1 shape to <b>Step</b>.",
       "Route LFO 1 somewhere in a mod slot (slot 2 is LFO 1 &gt; Cutoff out of the box) and turn its amount up.",
       "Open the <b>LFO1 STEPS</b> page and set the 16 steps."])
ul(["While the BeatStep plays, step 1 is the first 16th after you press Play, and the steps follow its clock.",
    "When it's stopped, the steps run at the LFO's own speed or sync (one cycle = all 16 steps).",
    "Each step glides into the next over 3 ms, so even big jumps don't click."])
img("synth1-lfo1steps", "Synth 1, LFO1 STEPS page.")
h2("Recipes")
table(["Sound", "How"], [
    (b("Vibrato"), "Slot 1 (LFO 1 &gt; Pitch) at about +3%, LFO 1 speed around 5 Hz."),
    (b("Wobble bass"), "LFO 1 sync 1/8, slot 2 (LFO 1 &gt; Cutoff) at +40 to +60%, filter LP 12, some resonance."),
    (b("Sync scream"), "Hard sync On, Osc 2 pitch +12, then a slot routed Mod env &gt; Osc 2 pitch at +60%."),
    (b("Auto-pan"), "Slot 6 (LFO 2 &gt; Pan) at +50%, LFO 2 sync 1/2."),
    (b("Acid sequence"), "LFO 1 shape Step, slot 2 (LFO 1 &gt; Cutoff) at +50%, then draw a pattern on LFO1 STEPS."),
    (b("Supersaw lead"), "Supersaw (Synth 1 OSC+, knob 16) at 70%, a little reverb, slot routed LFO 2 &gt; Supersaw for movement."),
    (b("Evolving pad"), "Synth 2: LFO 2 shape Smooth random, slow speed, slot 3 (LFO 2 &gt; Wave position) at +40%.")])
h2("Chords")
p("The BeatStep's sequencers play one note at a time, but <b>Chord</b> on the OSC+ page turns every step into a chord: "
  + ", ".join(c[0] for c in CHORDS[1:]) + ". <b>Chord voicing</b> spreads it: Close, Open, Wide. All the chord's notes "
  "go through the same filter and envelopes, like a classic paraphonic synth.")
note("<b>Heavy patches</b> (chords and supersaw on both synths with lots of modulation) use more of your PC. Watch LOAD "
     "on the Setup tab and choose the next buffer size up if you hear crackles.")
end()

# ============================================================================ 10 arp
chapter("The arpeggiator", "Each synth has an arpeggiator on its ARP+ page, together with its duck, EQ, pan and sends.")
img("synth1-arpplus", "Synth 1, ARP+ page.")
knob_table("Synth 1 Arp")
h2("Using the arpeggiator")
ul(["Turn Arp on and play a long note on the BeatStep (a tied step or a long gate). The arp plays from it.",
    "With Chord on (OSC+ page), the arp plays the chord's notes one at a time: the classic way to get arpeggios from a "
    "one-note sequencer.",
    "Short BeatStep steps also work: each new step plays the next note of the pattern, so a plain 16-step sequence walks "
    "through the chord.",
    "INIT ARP turns the arpeggiator off and resets it in one tap. Synth 2's ARP+ page works the same way."])
end()

# ============================================================================ 11 sounds
chapter("Sounds and save slots")
h2("The synth panels")
ul([f"{b('< PREV')} and {b('NEXT >')} step through sounds and play a test note. The list starts with Init (a plain "
    "starting point), then the presets, then your saved sounds.",
    f"{b('TEST')} plays a note so you can hear the synth without the BeatStep.",
    f"{b('RANDOM')} rolls a brand-new playable sound.",
    f"{b('MY SOUNDS')} opens your save slots."])
p(f"<b>Synth 1 presets:</b> {', '.join(n for n, _ in PRESETS['s1'])}.")
p(f"<b>Synth 2 presets:</b> {', '.join(n for n, _ in PRESETS['s2'])}.")
h2("My Sounds")
img("sounds", "My Sounds: 8 slots for each synth.", "small")
ul([f"{b('SAVE HERE')} stores the sound you are hearing. No typing: slots are named My Sound 1 to 8 and remember which "
    "sound they were made from.",
    "On a full slot, SAVE HERE asks you to tap again within 3 seconds, so one slip can't overwrite a sound.",
    f"{b('LOAD')} plays the saved sound back. Saved sounds also appear in PREV / NEXT."])
note("<b>Start from scratch:</b> pick Init with PREV / NEXT, tap INIT SYNTH on the synth's MAIN page, or tap "
     "<b>RESET ALL TO INIT</b> on the Mix tab (tap twice) to reset every knob in the app. Saved sounds, kits and setups are kept.")
end()

# ============================================================================ 12 drums
chapter("Drums and kits", "The drum sampler has 16 pads, played by the BeatStep's Drum sequencer (notes 36-51). Every "
        "kit uses the same pad layout, so a drum pattern keeps making sense when you change kits.")
layout = ["Kick", "Kick 2 (second kick or 808)", "Snare", "Clap", "Closed hat (cuts the open hat)", "Open hat",
          "Low tom", "Mid tom", "High tom", "Rim", "Percussion (cowbell)", "Percussion (clave)",
          "Percussion (shaker)", "Cymbal (crash or ride)", "FX", "Percussion (conga)"]
rows = [(f'<span class="kn">{i + 1}</span>', str(36 + i), E(layout[i]),
         f'<span class="kn">{i + 9}</span>', str(44 + i), E(layout[i + 8])) for i in range(8)]
table(["Pad", "Note", "Sound", "Pad", "Note", "Sound"], rows, "layout")
p("Tap a pad on screen to hear it and select it. Pad 5 cuts off pad 6, like a real hi-hat; the CHOKE page (below) "
  "lets any pads cut each other off.")
h2("Kit menu")
p("Tap <b>KIT MENU</b> on the drum panel, or &lt; and &gt; to step through kits.")
img("kits", "The Kit menu: built-in kits, recent kits, My Kits and the drum machine library.")
table(["Kit", "Sound"], [(b(k), d) for k, d in zip(kits.NAMES, [
    "The original all-rounder", "Round booming kick, classic metal hats", "Clicky driven kick, noisy snare, rides",
    "Small, snappy and crisp", "Punch kick, long distorted 808 to tune", "12-bit boom bap, crunchy and warm",
    "Gated snare, big pitch-drop toms", "Clicks, blips and tight kicks", "Distorted, metallic and heavy"])])
ul(["Tap a kit to load it and hear a short preview. PLAY DEMO BEAT plays a one-bar pattern.",
    "RESET PAD KNOBS puts every pad's tune, length and level back to normal.",
    "RECENT KITS lists the kits you used last. ADD FOLDER loads a folder of WAV files: the first 16 (in A-Z order) go on "
    "pads 1-16. Name them <code>01 kick.wav</code>, <code>02 808.wav</code> and so on to choose the order."])
h2("Drum machine library")
p("Point PotentialBox at a drum machine collection (one folder per machine, such as Roland TR-808) and tap <b>DRUM "
  "MACHINES</b>. PotentialBox looks for a folder called <b>Drum Machine Collection</b> in your Downloads, Documents, "
  "Music or Desktop folder; or use CHANGE FOLDER.")
img("machines", "Drum machines: brands on the left, machines on the right.")
ul(["Pick a brand, then a machine, then one of its kits. Brands with fewer than three machines are under Other.",
    "RANDOM MACHINE picks any machine and kit for you.",
    "Samples are read straight from your folder; nothing is copied.",
    "PotentialBox sorts the sounds onto the right pads by their names (BD, Kick, SD, Snare, CH, OH, Hat, Tom, Rim, Clap "
    "and many more). Spare sounds fill any empty pads.",
    "With a machine kit loaded, &lt; and &gt; step through that machine's kits, then on to the next machine."])
img("machinekits", "The kits inside one machine. Tap one to load and hear it.", "small")
h2("Drum knobs")
p("The Drums 1-8 and Drums 9-16 tabs each have four pages:")
ul([f"{b('MAIN')}: a tune knob (semitones) and a length knob (shortens the sound) for each pad.",
    f"{b('MIX')}: a level and a pan knob for each pad.",
    f"{b('GROOVE')}: chance and plays-when for each pad (below).",
    f"{b('CHOKE')}: a choke group (1-8) for each of the 16 pads. When a pad plays, it cuts off every other pad in its "
    "group: put an open hat and a pedal hat together, or a long 808 and a second 808."])
img("drums1-8-groove", "Drums 1-8, GROOVE page.")
h3("Chance and conditions")
p("These make a short BeatStep pattern feel longer and more alive, like Elektron's trig conditions.")
ul([f"{b('Chance')}: at 100% the pad always plays. At 70% about 3 hits in 10 are skipped, at random. Great on hats and "
    "percussion.",
    f"{b('Plays when')}: " + ", ".join(SPECS["dr.p1.cond"].choices) + ".",
    "1st of 4 means “only in the first bar of every four”: build a crash on bar 1 or a fill on bar 4 from a one-bar "
    "pattern. Bars are counted from when you press Play on the BeatStep.",
    "Fill only pads play only while you hold FILL; Not in fill pads drop out while you hold it."])
img("drums1-8-choke", "Drums 1-8, CHOKE page.")
end()

# ============================================================================ 13 build your own kit
chapter("Build your own kit", "Put any single drum sound on any pad, shape it, and save the result as your own kit.")
steps(["Tap a pad on the drum panel. It plays and gets highlighted.",
       "Tap <b>EDIT PAD</b>.",
       "Pick a type on the left: Kick, Snare, Clap, Hats, Toms, Perc, Cymbal, FX or All. The list shows every matching "
       "sound in your whole collection, with the machine it comes from.",
       "Tap a sound. It goes on the pad and plays straight away. Keep tapping until you like it.",
       "Use the pad strip along the top to move to the next pad.",
       "Tap <b>SAVE MY KIT</b> and choose a slot."])
img("pad", "The pad editor.")
ul([f"{b('RANDOM')} picks a random sound of the chosen type: great for happy accidents.",
    f"{b('ALL / MACHINE')}: MACHINE limits the list to the drum machine you have loaded.",
    f"{b('FROM FILE...')} takes any WAV file on your PC.",
    f"{b('LOCK PAD')} keeps this pad's sound when you roll a {b('Random Drum Kit')} (pad action or Live pad 14).",
    "Silence at the start of every drum sound is trimmed automatically, so hits land exactly on the beat."])
h2("Edit this pad's sound")
table(["Key", "What it does"], [
    (b("TRIM"), "Cuts silence off the start and end."),
    (b("NORMALIZE"), "Makes the sound as loud as it can be without clipping."),
    (b("FADE IN / FADE OUT"), "A 50 ms fade at the start or the end (softens clicks)."),
    (b("PITCH −1 / PITCH +1"), "Re-pitches the sample by a semitone, like a sampler (it gets shorter or longer). "
                              "For tuning without changing the sample, use the pad's Tune knob.")])
note("Sound edits last until you put another sound on the pad or close PotentialBox. They aren't saved in My Kits, which "
     "remember the sample files themselves.", "warn")
h2("My Kits")
img("mykits", "My Kits: 8 slots for your own kits.", "small")
p("Open it from the Kit menu or the pad editor. SAVE HERE stores every pad of the current kit; a full slot needs two "
  "taps to replace. LOAD brings the kit back. An edited kit shows a * after its name and comes back when you restart, "
  "even before you save it.")
end()

# ============================================================================ 14 macros
chapter("Macros", "The MACROS tab turns the BeatStep's 16 knobs into performance controls. Each macro moves several "
        "settings at once in a musical way: sweeps, throws, risers and drops.")
img("macros", "The Macros tab. The top of the page describes the last macro you touched.")
note("<b>Macros never overwrite your sound.</b> They work on top of your settings, so turning a macro back to zero puts "
     "everything back exactly where it was. DJ Filter rests in the centre. ZERO ALL MACROS resets them all at once.")
knob_table("Macros")
h2("Ideas")
ul(["Build-Up then back to zero gives an instant drop: the kick comes back on the way down.",
    "Ride Dub Throw on the last beat of a phrase, then pull it back.",
    "DJ Filter left for a muffled breakdown, right for a thin, tense one.",
    "Acid plus a little Glide on Synth 1 basslines."])
end()

# ============================================================================ 15 beats
chapter("The Beats tab", "The Beats tab makes drum beats in the style of a genre. Tap a genre and you get a beat; tap "
        "NEW BEAT for another take, as often as you like. When you have one you like, SEND TO BEATSTEP records it "
        "into the BeatStep's drum sequencer, where it carries on like a beat you programmed yourself.")
img("beats", "The Beats tab: knobs on top, the genres, the beat (tap a dot to change it), and the keys.")
h2("Make a beat")
steps(["Tap a genre. With GENRE KIT: ON its usual kit loads too, and if the BeatStep is stopped the tempo is set for it.",
       "Tap <b>PLAY</b>. While the BeatStep plays, the beat locks to its clock; when it's stopped, the beat runs on its "
       "own tempo (change it with − and +).",
       "Tap <b>NEW BEAT</b> for a different take and <b>MUTATE</b> to change just one part.",
       "<b>BUSIER</b> adds a layer each tap (16th hats, ghost snares, an extra kick, shaker or congas); <b>SIMPLER</b> "
       "takes one away. You see each change in the grid.",
       "Tap any dot to remove it, or an empty spot to add a hit."])
h2("Length and endings")
ul(["Beats are 2 bars long out of the box. LENGTH switches between 1, 2 and 4 bars.",
    "The last bar ends with a change that leads back to the start: a snare roll or pickup, a tom run, an open hat, a "
    "kick run, or a drop-out with a crash back in on the one. Its steps are shaded in the grid.",
    "NEW ENDING keeps the beat and picks a different ending.",
    "In the grid, big dots are accents, normal dots hits, small dots ghost notes, and dots with a ? play about half the "
    "time, so the beat never repeats exactly.",
    "HOLD FOR FILL plays a fill in the genre's style for as long as you hold it. The mute keys silence the kick, snares, "
    "hats or percussion."])
h2("Send it to the BeatStep")
steps(["On the BeatStep, choose the drum sequencer and an empty drum pattern. Set its length to the number of steps "
       "shown on screen (32 for 2 bars, 64 for 4) and, if the genre swings, the same swing (shown on the bottom line).",
       "In PotentialBox, tap <b>SEND TO BEATSTEP</b> (or Beats pad 15). It shows WAITING FOR REC + PLAY.",
       "On the BeatStep, press REC and PLAY. PotentialBox sends the beat once, from step 1, on the drum channel.",
       "When it says SENT, press REC on the BeatStep to stop recording. From now on the BeatStep plays the pattern."])
p("While sending, PotentialBox plays the beat itself and ignores the notes the BeatStep plays back, so you don't hear "
  "it twice. Maybe-hits (?) are decided once as they're sent, so the BeatStep gets one exact take.")
h2("Clock out: PotentialBox sets the tempo")
p("Turn on <b>CLOCK OUT</b> and PotentialBox becomes the clock: it sends MIDI clock, Start and Stop, so the BeatStep "
  "plays at the beat's tempo.")
steps(["Once, on the BeatStep: press its SYNC button until <b>USB</b> is chosen.",
       "Tap <b>CLOCK OUT</b> on the Beats tab (it stays on next time).",
       "PLAY now starts the BeatStep and the beat together; STOP stops both.",
       "Sending is easier too: tap SEND TO BEATSTEP, press REC on the BeatStep during the 4-second countdown, and "
       "PotentialBox starts everything and plays the beat in."])
p("To go back to the BeatStep being the clock, turn CLOCK OUT off and set the BeatStep's SYNC back to INT.")
h2("Save it as a MIDI file")
p("<b>MIDI FILE</b> saves the beat as a .mid file in <b>Music &gt; PotentialBox Recordings</b>, on the drum channel, "
  "with pad 1 on note 36 up to pad 16 on note 51 (the BeatStep's layout), ready for a DAW or an MPC.")
h2("Genres")
rows = []
for g in beats.GENRES:
    name, bpm, swing, native, kit = g[:5]
    rows.append((b(name), str(bpm), "straight" if swing <= 50 else f"{swing}%", "1 bar" if native == 16 else "2 bars",
                 E(kits.NAMES[kit])))
table(["Genre", "Tempo", "Swing", "Pattern", "Kit"], rows, "compact")
h2("Knobs")
knob_table("Beats", with_desc=False)
p("Random hits makes the ? hits more or less likely; Variation adds the odd extra hit now and then; Swing at “Genre” "
  "uses the genre's own swing; Humanize loosens the timing and velocity a little.")
h2("The BeatStep's pads on the Beats tab")
pads_table(BEAT_PADS, "Pad", "Beats pad")
end()

# ============================================================================ 16 arrangement
chapter("The Arrangement tab", "The Arrangement tab chains beats into a song: they play in order, each for its own "
        "length (1, 2 or 4 bars), then round again. The tab bar calls it ARRANGE.")
img("arrangement", "The Arrangement tab: the song on the left, the keys on the right. Beat 3 is playing.")
steps(["Make a beat on the Beats tab.",
       "On the Arrangement tab, tap <b>ADD CURRENT BEAT</b> (or the “+ ADD THE BEAT” space). Up to 16 beats.",
       "Go back to the Beats tab, make the next beat, add it, and so on.",
       "Tap <b>PLAY SONG</b>. With CLOCK OUT on, it starts the BeatStep too."])
ul([f"{b('Tap a beat')} while the song plays to jump to it. While it's stopped, tapping a beat puts it on the Beats tab "
    "to hear and change (add it again to keep the change).",
    f"{b('REMOVE LAST')} takes the last beat off; {b('CLEAR SONG')} (tap twice) empties the song.",
    f"{b('SAVE SONG AS MIDI FILE')} saves the whole song as one .mid file in Music &gt; PotentialBox Recordings.",
    "The bottom line shows how many beats and bars the song has and how long it lasts at the current tempo.",
    "The song is saved with your settings."])
h2("Knobs")
knob_table("Arrangement")
end()

# ============================================================================ 17 live
chapter("The Live tab", "The Live tab is for playing: hold-to-play effects, scenes, fill, recording and resampling, all "
        "one tap away.")
img("live", "The Live tab.")
h2("Knobs")
knob_table("Live", with_desc=False)
h2("Punch-in effects")
p("Hold a pad to play an effect over the whole mix; let go and the music carries on as before.")
table(["Pad", "Effect", "What it does"], [(f'<span class="kn">{i + 1}</span>', b(n), d) for i, (n, d) in enumerate(zip(PUNCH_FX, [
    "Loops the eighth note you pressed on, over and over (beat repeat).", "The same with a sixteenth: a stutter.",
    "A fast drum-roll buzz.", "The music slows to a stop over one beat, like a turntable switched off.",
    "Plays the music backwards from the moment you pressed.", "A resonant low-pass closes over two beats; it opens again when you let go.",
    "Chops the sound on and off in sixteenths (trance gate).", "Sends the mix into a long dub echo that keeps ringing after you let go."]))],
    "knobs")
p("Only one of pads 1-5 works at a time (the last one you pressed); pads 6-8 can be held on top.")
h2("Scenes")
p("A scene is a snapshot of every setting. There are 8, and the morph bar blends between any two of them.")
steps(["Get a sound you like and tap <b>SAVE 1</b>.",
       "Change anything: filters, effects, levels, drum tuning, macros. Then tap <b>SAVE 2</b>.",
       "<b>FROM</b> and <b>TO</b> choose the two scenes to morph between (1 and 2 out of the box; tap to step through 1-8).",
       "Drag the morph bar, or turn BeatStep knob 1, to blend from one to the other. Only the settings that differ move; "
       "the line under the bar says how many.",
       "<b>HOLD FOR SCENE</b> (Live pad 10) jumps to the TO scene while held and goes back when you let go: an instant drop."])
ul([f"{b('LOAD')} 1-8 puts a saved scene back straight away. Empty slots say EMPTY.",
    "Morphing sets the knobs it moves. If you change one of them by hand, moving the morph again takes it back to the "
    "blend. Save the scene again to keep your change.",
    "Scenes saved by version 1.9.0 or earlier (A and B) come back as scenes 1 and 2."])
h2("Fill, record and resample")
ul([f"{b('HOLD FOR FILL')} (Live pad 9) plays the drum pads set to Fill only and silences those set to Not in fill.",
    f"{b('RECORD')} (Live pad 11) starts and stops recording. Recordings go into Music &gt; PotentialBox Recordings, one "
    "folder per take, as 24-bit WAV files. MIX + STEMS also saves Drums, Synth 1, Synth 2, FX returns and Looper as "
    "separate files that line up; MIX ONLY saves just the master.",
    f"{b('RESAMPLE TO A PAD')} records Synth 1, Synth 2, both synths, the FX returns or everything, for half a bar to 4 "
    "bars, onto a drum pad. If the BeatStep is playing it waits for the next bar so the loop lines up. Save the kit in "
    "My Kits to keep it."])
img("resample", "Resample: choose what to record, how long, and which pad.", "small")
h2("My setups")
p("A setup stores everything at once: both synth sounds, the drum kit, every knob, step locks, scenes and the beat. Tap "
  "<b>MY SETUPS</b>, then SAVE HERE on a slot (tap twice to replace one). LOAD brings the whole setup back, for "
  "example one per song.")
img("setups", "My setups: 8 slots for complete setups.", "small")
h2("The BeatStep's pads on the Live tab")
p("While the Live tab is open, the 16 pads that normally run pad actions play the Live pads instead:")
pads_table(LIVE_PADS, "Pad", "Live pad")
end()

# ============================================================================ 18 loop
chapter("The Loop tab", "A 5-track looper, inspired by the BOSS RC-505: record a phrase, it plays round and round, add "
        "more on top or on other tracks, and build a song live. It records the inputs of your audio interface (mic, "
        "guitar, keys) and PotentialBox's own synths and drums.")
img("loop", "The Loop tab: five tracks, the 16 knobs on top, settings on the right.")
h2("First loop in four taps")
steps(["Tap <b>INPUT OFF</b> at the top right and pick the input your mic or instrument is plugged into (for example "
       "IN 1, or IN 1+2 STEREO). This needs your interface's ASIO driver chosen in SETUP.",
       "Press pad 1 (or tap REC on track 1) and play.",
       "Press pad 1 again: the loop plays. Again starts an overdub; once more goes back to playing.",
       "Pad 2 records track 2, and so on. Hold a track's stop pad (9-13) for a second to clear it."])
img("loopinput", "Choosing the looper's input.", "small")
h2("Each track")
ul(["The big key shows what a tap does next: REC, PLAY or DUB. Red is recording, green playing, yellow overdubbing.",
    "FROM chooses what the track records: Input, PotentialBox or Both. “PotentialBox” records the synths and drums "
    "(with their effects) but not the loops, so nothing doubles up.",
    "FX picks the track's effect (Low-pass, High-pass, Lo-fi, Echo, Tremolo); its amount is the track's FX knob.",
    "REVERSE plays the track backwards. SPEED switches between 1/2, 1x and 2x. Overdubbing works at 1x."])
h2("Timing")
ul([f"{b('SYNC TO BEATSTEP')}: while the BeatStep plays, loop lengths snap to whole bars and the loops follow its Play "
    "and Stop, restarting in time with bar 1. With the BeatStep stopped, the first loop sets the length for the rest.",
    f"{b('START: WHEN I TAP')} starts recording the moment you press (the end still snaps); {b('START: ON THE BAR')} "
    "waits for the next bar. A press a little late still counts as on the bar.",
    f"{b('LENGTH')}: Free, 1, 2, 4 or 8 bars. With a length set, recording stops by itself and the loop starts playing.",
    "Your interface's delay is measured and made up for, so what you record lands in time."])
h2("Knobs")
knob_table("Loop")
h2("Undo, stop, clear and save")
ul([f"{b('UNDO / REDO')} (pad 6) takes back the last overdub on the last track you used.",
    f"{b('ALL STOP')} (pad 7) stops every track; pressed again it is ALL PLAY. Pad 8 records on the next empty track.",
    f"{b('CLEAR ALL')} empties every track (tap twice).",
    f"{b('MY LOOPS')} saves all five tracks in one of 8 slots, as WAV files in Music &gt; PotentialBox Loops, ready for a "
    "DAW or an MPC. LOAD brings them back stopped."])
img("myloops", "My loops: 8 loop sets.", "small")
h2("The BeatStep's pads on the Loop tab")
pads_table(LOOP_PADS, "Pad", "Loop pad")
note("With a mic, use headphones so the speakers don't feed back into it. If you hear yourself twice, turn down HEAR "
     "INPUT (knob 7).")
end()

# ============================================================================ 19 step locks
chapter("Step locks", "A step lock gives a knob a different value on one step of the pattern: a filter that opens on "
        "step 4, a pitch drop on the last step, a snare with a longer tail on step 13. The same idea as Elektron's "
        "parameter locks.")
img("locks", "Step locks on Synth 1: steps 3 and 11 have locks, step 3 is selected.")
steps(["Open the page with the knob you want, then tap <b>STEP LOCKS</b> at the top right.",
       "The panels at the bottom turn into 16 step keys. Tap a step: it lights up.",
       "Turn knobs (on screen or on the BeatStep). Now they only set that step, and the knob shows LOCK.",
       "Tap another step to lock that one, or the same step again to go back to normal knobs. DONE closes the panel."])
ul(["Locks play while the BeatStep is playing and follow its clock: step 1 is the first step after you press Play, and "
    "the 16 steps repeat (for longer patterns the locks repeat every 16).",
    "Every knob except the macros, scenes and master volume can be locked.",
    "A knob with locks shows a small L. Steps with locks show how many on their key.",
    "CLEAR STEP, CLEAR PAGE and CLEAR ALL remove locks. The INIT keys and RESET ALL TO INIT clear the locks they cover.",
    "Locks are saved with your settings and in My Setups, but not in My Sounds."])
end()

# ============================================================================ 20 mix
chapter("Mix", "The Mix tab has three pages: MAIN (levels, ducking, glue), EQ and MUTE/SOLO.")
img("mix-main", "The Mix tab, MAIN page.")
knob_table("Mix")
note("<b>RESET ALL TO INIT</b> at the top of the Mix tab resets every knob in the app (both synths, all pads, mix, "
     "effects and macros) and clears step locks and scenes. Tap it twice. Saved sounds, kits, setups and the audio setup "
     "are kept.")
h2("Side-chain duck")
p("Ducking makes the synths dip each time the kick plays, so the kick punches through: the “pumping” sound of house and "
  "techno. Duck Synth 1, Duck Synth 2 and Duck FX returns set how far each one dips; Duck from chooses the trigger pad (or "
  "Every beat, to pump without any kick); Duck release sets how quickly the sound comes back.")
h2("EQ page")
img("mix-eq", "The Mix tab, EQ page.")
knob_table("Mix EQ", with_desc=False)
p("Each EQ has a low shelf, a mid band around 1 kHz and a high shelf, from -12 to +12 dB. Low EQ freq and High EQ freq "
  "set where the shelves start, for all four EQs.")
h2("MUTE/SOLO page")
p("One-tap mute and solo for Synth 1, Synth 2 and the drums. While anything is soloed, only soloed tracks play. Muted "
  "tracks keep running in time, so they come back exactly in place.")
img("mix-mutesolo", "The Mix tab, MUTE/SOLO page.")
knob_table("Track Mute/Solo", with_desc=False)
end()

# ============================================================================ 21 FX
chapter("FX", "The FX tab has two pages: SENDS (delay and reverb) and MASTER (the effects on the whole mix).")
img("fx-sends", "The FX tab, SENDS page.")
knob_table("FX")
ul([f"{b('Delay')}: a ping-pong delay locked to the tempo, with a send from each instrument.",
    f"{b('Reverb')}: a smooth room-to-hall reverb with a send from each instrument.",
    f"{b('DJ filter')}: centre is off, left is low-pass, right is high-pass, on the whole mix."])
h2("MASTER page")
img("fx-master", "The FX tab, MASTER page.")
knob_table("Master FX")
p("The master chain runs in this order: chorus, flanger, phaser, compressor, distortion, DJ filter and lo-fi, EQ, glue, "
  "width, the Live tab's punch-in effects, then master level and drive into the limiter. With the limiter at 0 a gentle "
  "soft clip catches the peaks instead.")
end()

# ============================================================================ 22 pad actions
chapter("Pad actions", "With the BeatStep Pro's Control Mode pads on MIDI channel 16 (chapter 5), each pad runs a "
        "PotentialBox action. Notes on channel 16 never play the synths.")
rows = []
for i, (aid, name) in enumerate(ACTIONS):
    rows.append((f'<span class="kn">{i + 1}</span>', str(36 + i) if aid in PAD_ACTIONS else "not set", b(name)))
table(["Pad", "Note", "Action"], rows, "knobs short")
h2("Changing them")
img("actions", "SETUP &gt; PAD ACTIONS.")
steps(["Open SETUP and tap <b>PAD ACTIONS</b>.", "Tap the action you want to change. It lights up.",
       "Press the pad or step button on the BeatStep Pro you want to use for it. Notes and CCs both work, on any channel."])
p("Each card flashes when its action runs. RESET TO CHANNEL 16 DEFAULTS puts the table above back. Actions 17-22 have no "
  "pad out of the box. On the Beats, Live and Loop tabs the pads play those tabs' own pads instead (chapters 15, 17, 18).")
end()

# ============================================================================ 23 files
chapter("Your files", "PotentialBox saves everything by itself, a moment after each change and when you close it.")
table(["What", "Where"], [
    (b("The app"), "<code>%LOCALAPPDATA%\\PotentialBox</code>"),
    (b("Settings (knobs, setup, pad actions, kit, beat, song)"), "<code>%APPDATA%\\PotentialBox\\state.json</code>"),
    (b("My Sounds"), "<code>%APPDATA%\\PotentialBox\\my-sounds.json</code>"),
    (b("My Kits"), "<code>%APPDATA%\\PotentialBox\\my-kits.json</code>"),
    (b("My Setups"), "<code>%APPDATA%\\PotentialBox\\my-setups.json</code>"),
    (b("Resampled sounds"), "<code>%APPDATA%\\PotentialBox\\Resampled</code>"),
    (b("Your own wavetables"), "<code>%APPDATA%\\PotentialBox\\Wavetables</code>"),
    (b("Your own look"), "<code>%APPDATA%\\PotentialBox\\user-look.json</code>"),
    (b("Recordings and MIDI files"), "<code>Music\\PotentialBox Recordings</code>"),
    (b("My Loops"), "<code>Music\\PotentialBox Loops</code> (one folder per loop set)"),
    (b("Log (what went wrong, if anything)"), "<code>%APPDATA%\\PotentialBox\\log.txt</code>")])
p("To open one of these folders, paste the path (for example <code>%APPDATA%\\PotentialBox</code>) into the File "
  "Explorer address bar and press Enter.")
note("Back up your sounds, kits and setups by copying the three <code>my-…json</code> files somewhere safe. My Kits point "
     "to your sample files, so keep your sample folders where they are.")
end()

# ============================================================================ 24 troubleshooting
chapter("Troubleshooting")
for q, a in [
    ("The header says AUDIO ERROR", "Open SETUP and tap another output. If your interface's ASIO driver won't open, close "
     "any DAW, FL Studio or Voicemeeter that might be using it, then tap it again. WASAPI always works as a fallback."),
    ("I hear crackles", "Look at LOAD and DROPOUTS on the Setup tab. If DROPOUTS climbs, tap the next BUFFER size up "
     "(256 or 512). If LOAD is high, ease off chords and supersaw on both synths, or close heavy apps."),
    ("MIDI says NO BEATSTEP FOUND", "Check the USB cable, wait a few seconds after plugging in, then tap RESCAN MIDI in "
     "SETUP. A DAW can hold the BeatStep's MIDI port open; close it and rescan."),
    ("The sequencers play but the knobs do nothing", "Press CONTROL MODE on the BeatStep Pro. Still nothing? "
     "SETUP &gt; LEARN KNOBS."),
    ("The pads don't run actions", "Set the BeatStep's Control Mode pads to MIDI channel 16 in MIDI Control Center, or "
     "teach PotentialBox your pads in SETUP &gt; PAD ACTIONS."),
    ("Step locks, step LFOs, the arp or “1st of 4” don't follow the BeatStep", "They follow the BeatStep's MIDI clock. "
     "Press Play on the BeatStep and check the header shows its tempo. Stop and Play again to reset the step count."),
    ("With CLOCK OUT on, the BeatStep doesn't start", "Its SYNC must be on USB. In SETUP, make sure the BeatStep's MIDI "
     "port is on."),
    ("SEND TO BEATSTEP says no MIDI out was found", "Check the BeatStep is plugged in and switched on, then try again. "
     "The beat goes out on the drum channel set in SETUP (10 out of the box)."),
    ("The scene morph does nothing", "Save two different scenes and check FROM and TO point at them. The line under the "
     "morph bar says how many settings move."),
    ("The Loop tab says INPUT OFF, or lists no inputs", "Inputs come from the output chosen in SETUP. Pick your "
     "interface's ASIO driver there (WASAPI outputs have no inputs), then choose the input on the Loop tab."),
    ("A synth or drum sounds wrong", "A macro may be turned up (tap ZERO ALL MACROS), a track may be muted or another "
     "soloed (Mix &gt; MUTE/SOLO), or the master effects may be on (FX &gt; MASTER). For a fresh start, RESET ALL TO INIT."),
    ("A machine kit has odd sounds on some pads", "The sorter goes by file names. Use EDIT PAD to swap any pad, then save "
     "it in My Kits."),
    ("PotentialBox won't start", "Run the installer again. If it still won't start, the last lines of "
     "<code>%APPDATA%\\PotentialBox\\log.txt</code> say why; include them if you report a problem on GitHub.")]:
    add(f'<div class="qa"><h4>{E(q)}</h4><p>{a}</p></div>')
end()

# ============================================================================ 25 credits
chapter("Credits and licence", "PotentialBox is made by PotentialBreaks and is free and open source under the MIT licence.")
table(["Project", "Used for", "Licence"], [
    (b("Python 3.12"), "Runs the app", "PSF License"),
    (b("NumPy, SciPy"), "Sound processing", "BSD"),
    (b("sounddevice (with PortAudio)"), "Audio output, including ASIO", "MIT"),
    (b("mido, python-rtmidi"), "MIDI from and to the BeatStep Pro", "MIT"),
    (b("Tcl/Tk"), "The screen", "BSD-style"),
    (b("AKWF-FREE (Adventure Kid Waveforms)"), "24 of Synth 2's wavetables", "CC0 (public domain)")])
p("The libraries are downloaded by the installer from their official sources; they are not included in the PotentialBox "
  "zip. The AKWF wavetables are included, as CC0 allows. All drum sounds in the built-in kits are generated by "
  "PotentialBox itself.")
p("Arturia and BeatStep Pro are trademarks of Arturia. ASIO is a trademark of Steinberg Media Technologies GmbH. Machine "
  "names in your sample library belong to their owners. PotentialBox is an independent project and is not affiliated with "
  "or endorsed by any of them.")
end()

# ============================================================================ TOC + page
half = (len(TOC) + 1) // 2
cols = [TOC[:half], TOC[half:]]
toc = '<section class="toc"><h1 class="plain">Contents</h1><div class="cols">' + "".join(
    "<ol>" + "".join(f'<li><span class="n">{n}</span>{E(t)}</li>' for n, t in col) + "</ol>" for col in cols) + "</div></section>"
doc = "\n".join(H).replace("@@TOC@@", toc)
css = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual.css")).read()
page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>PotentialBox {VERSION} manual</title>
<style>{css}</style></head><body>{doc}</body></html>"""
html_path = os.path.splitext(OUT)[0] + ".html"
open(html_path, "w", encoding="utf-8").write(page)
subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw", "--virtual-time-budget=20000",
                f"--print-to-pdf={OUT}", "file://" + html_path], check=True, capture_output=True)
print("built", OUT, "chapters", CH[0])
