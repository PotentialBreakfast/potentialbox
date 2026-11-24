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
from potentialbox.engine import (PAGES, SPECS, MACROS, PRESETS, PRESET_CAT, PRESET_CATS, PUNCH_FX,  # noqa
                                 DEFAULT_ROUTES, TABLE_NAMES, CHORDS)
from potentialbox import kits, beats, kitmaker  # noqa
from potentialbox import projects as projmod  # noqa
from potentialbox.app import (VERSION, ACTIONS, PAD_ACTIONS, LIVE_PADS, LOOP_PADS, BEAT_PADS, KNOB_GROUPS,  # noqa
                              SUBPAGES, SECTIONS, CAPTURE_PADS, PROJECT_PADS)
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


def img_hl(name, caption, boxes):
    """A screenshot with amber rings on what to press: boxes in the app's 1280 x 800 screen space."""
    rings = "".join(f'<div class="hl" style="left:{(x - 4) / 12.8:.2f}%;top:{(y - 4) / 8:.2f}%;'
                    f'width:{(w + 8) / 12.8:.2f}%;height:{(h + 8) / 8:.2f}%"></div>' for x, y, w, h in boxes)
    add(f'<figure class="hlfig"><div class="hlwrap"><img src="file://{IMG}/{name}.png">{rings}</div>'
        f'<figcaption>{caption}</figcaption></figure>')


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
                                                                    "Master FX", "Live", "Beats", "Arrangement",
                                                                    "Capture"):
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
<div class="sub">A groovebox for jamming on Windows, played by the Arturia BeatStep Pro</div>
<div class="meta">Version {VERSION} · two synths · 16-pad drum sampler · 16 genre projects · stem bouncing · looper · ASIO</div>
<div class="shot"><img src="file://{IMG}/projects.png"></div>
<div class="foot"><span>by PotentialBreaks</span><span>Free and open source · MIT licence</span></div>
</section>""")
add("@@TOC@@")
# ============================================================================ 1 welcome
chapter("Welcome", "PotentialBox turns your Arturia BeatStep Pro into a groovebox for jamming. The BeatStep Pro is the "
        "sequencer and the controller; PotentialBox makes the sound on your Windows PC, and catches what you play as "
        "loops and stems.", newpage=False)
p("Everything lives under five big keys along the bottom of the screen:")
table(["Section", "What's there"], [
    (b("JAM"), "PROJECTS (sounds for your 16 BeatStep genre sets, MUTATE, voice), LIVE FX (punch-in effects, scenes, "
               "fill, GRAB the last bars), KNOBS and MACROS."),
    (b("SOUNDS"), "SYNTH 1 and SYNTH 2 (a sound browser first, every setting under EDIT SOUND), DRUMS (kits, Kit Maker, "
                  "pad knobs), MIX and FX."),
    (b("BEATS"), "The beat generator in 24 genres, and ARRANGE to chain beats into a song."),
    (b("CAPTURE"), "STEMS: bounce what's playing as bar-exact loops (the mix and each part) and send them to your MPC. "
                   "LOOPER: a 5-track looper."),
    (b("SETUP"), "Audio, MIDI, knobs, pad actions and My Setups.")])
ul([f"{b('Sequencer 1')} plays {b('Synth 1')}, an analog-style synth: basses, acid, leads, supersaws, chords.",
    f"{b('Sequencer 2')} plays {b('Synth 2')}, a wavetable synth: leads, keys, pads, plucks and bells.",
    f"The {b('Drum sequencer')} plays a {b('16-pad drum sampler')}: built-in kits, your own samples, whole drum machine "
    "collections and the Kit Maker.",
    "The BeatStep's 16 knobs control the 16 knobs of whichever page is open, and its pads run actions on MIDI channel 16."])
p("Everything is pre-wired for the BeatStep Pro's factory settings, so you can plug it in and press play. Every control "
  "is a big key you can tap, and everything saves by itself: there is no typing anywhere in the app.")
note("<b>New to the layout?</b> The chapter <b>A jam, start to finish</b> walks through one whole session, from loading "
     "a project to chopping its stems on your MPC, with the screen for every step.")
note(f"<b>New in {VERSION}:</b> <b>BOUNCE NEXT + SEND</b> on JAM &gt; LIVE FX; <b>▶</b> in YOUR BOUNCES to listen "
     "before you send. <b>2.2:</b> <b>GRAB</b> saves the bars you just played; <b>◀ BACK</b> on BEATS.")
note("<b>New in 2.0:</b> a new layout with five sections instead of fourteen tabs; the Hi-Fi look, refreshed; "
     "a <b>sound browser</b> for each synth with sounds sorted by type; <b>77 new presets</b> made for the current synth "
     "engine, all level-matched; a new <b>PROJECTS</b> screen for jamming; and <b>CAPTURE &gt; STEMS</b>, which bounces "
     "bar-exact loops (mix + each part) and can send them straight to your MPC. The full list is in the CHANGELOG "
     "file that comes with PotentialBox.")
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
                                       "for pad actions (see Setting up the BeatStep Pro).")])
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
  "want to keep them (see Your files). Your recordings and loops in the Music folder stay. Python 3.12 stays too; remove it "
  "in Windows Settings &gt; Apps if you like.")
end()

# ============================================================================ 4 setup
chapter("First start: Setup", "Tap SETUP (bottom right) the first time you start PotentialBox.")
img("setup", "SETUP: audio outputs on the left, MIDI on the right, knobs, pad actions and My Setups at the bottom.")
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
h2("My Setups")
p("<b>MY SETUPS</b> (bottom right) stores everything at once: both synth sounds, the drum kit, every knob, step locks, "
  "scenes and the beat. Tap SAVE HERE on a slot (tap twice to replace one); LOAD brings the whole setup back, for "
  "example one per song.")
img("setups", "My Setups: 8 slots for complete setups.", "small")
end()

# ============================================================================ 5 beatstep
chapter("Setting up the BeatStep Pro")
h2("The sequencers")
p("Nothing to set up: on factory settings Sequencer 1 sends on channel 1, Sequencer 2 on channel 2 and the Drum "
  "sequencer on channel 10 with notes 36-51, which is exactly what PotentialBox listens to.")
ul(["Press PLAY on the BeatStep Pro. PotentialBox follows its tempo (shown at the top), so the delay, LFOs, arp and "
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
p("To use the pads for pad actions (see Pad actions), set the BeatStep Pro's Control Mode pads to MIDI channel 16 in "
  "Arturia's free MIDI Control Center app. Out of the box pads 1-16 send notes 36-51, which PotentialBox already "
  "expects. Any other notes or CCs work too: assign them in SETUP &gt; PAD ACTIONS.")
end()

# ============================================================================ 6 the screen
chapter("The screen")
img("projects", "JAM &gt; PROJECTS, the screen you jam from.")
h2("The five sections")
p("The five big keys along the bottom are the sections. Each section has a few sub-tabs, shown as keys at the top left "
  "of the screen. A section remembers the sub-tab you were on, so going back lands where you left it.")
table(["Section", "Sub-tabs"], [(b(sec), " · ".join(lab for lab, _ in subs)) for sec, subs in SECTIONS])
h2("The display and the lights")
ul([f"The {b('display')} at the top says what's loaded: the project, Synth 1's and Synth 2's sounds and the kit. While "
    "you record or bounce it shows that first, and messages pop up in it for a moment.",
    f"{b('BPM')}: the tempo PotentialBox is playing at. The {b('level meter')} beside it turns red when you push the "
    "limiter or soft clip.",
    f"The {b('AUDIO')} and {b('MIDI')} lights (under the meter) are green when the audio output and the BeatStep are "
    "working; the MIDI light flickers when MIDI arrives. Tap either to go to Setup. If the audio has a problem, the "
    "display says so in red."])
h2("Pages inside a sub-tab")
p("Some sub-tabs have pages of knobs: the synths' edit pages, Drums, Mix and FX. The page keys sit at the top of the "
  "knob area. The knobs are laid out like the BeatStep's: top row 1-8, bottom row 9-16, in labelled groups.")
table(["Sub-tab", "Pages"], [(b(t.upper()), " · ".join(lab.upper() for lab, _ in SUBPAGES[t])) for t in SUBPAGES])
h2("Using the controls")
ul(["Tap the left or right half of a knob to step it down or up, drag up and down, or use the mouse wheel.",
    "The coloured ring round a knob shows its value. Settings that go both ways (pan, EQ, tuning) fill from the top.",
    f"Settings that are just on or off (mute, solo, hard sync, arp hold, glide mode) are {b('one-tap keys')} instead of "
    "knobs. The BeatStep knob for that spot still switches them.",
    "A knob that a macro is moving shows a small ring where your own setting is.",
    f"{b('STEP LOCKS')} (top right of the knob area) gives a knob a different value on each step (see Step locks). A "
    "small L on a knob means it has step locks."])
h2("Keyboard shortcuts")
table(["Keys", "What they do"], [
    (key("Ctrl") + " + " + key("1") + " … " + key("5"), " · ".join(sec for sec, _ in SECTIONS) + "."),
    (key("Ctrl") + " + " + key("Z"), "Undo the last change: a whole knob turn, sound load or scene load at a time."),
    (key("Ctrl") + " + " + key("Y"), "Redo."),
    (key("F11"), "Full screen on and off."),
    (key("Esc"), "Closes a menu.")])
end()
# ============================================================================ a jam, start to finish
chapter("A jam, start to finish", "One session with the new layout: load the Acid project, shape it with the BeatStep, "
        "swap a sound, fatten the drums, perform, mutate, then bounce 4 bars of stems onto your MPC. The amber rings "
        "show what to press. Each step also says what to do on the BeatStep, and a hands-free way to do it.")
WF = [
    ("Load a project", "JAM &gt; PROJECTS", "wf-01", [(948, 146, 143, 82)],
     "Tap <b>7</b> ACID. Synth 1 gets an acid bass, Synth 2 a stab, the drums the Acid set kit with its drum bus, plus "
     "the project's effects and tempo.",
     "Hold <b>PROJECT</b> and press step <b>7</b>, so the BeatStep plays the Acid set too.",
     "Press BeatStep pad <b>7</b> while PROJECTS is open, or tap TALK and say “project seven”."),
    ("Press play", "JAM &gt; PROJECTS", "wf-02", [(236, 8, 712, 40), (14, 342, 760, 226)],
     "NOW PLAYING lists the bass, lead and kit. The display along the top always shows what's loaded, wherever you "
     "are in the app.",
     "Press <b>PLAY</b>. Seq 1 plays the bass, Seq 2 the chords, the drum sequencer the kit.",
     "Turn on CLOCK OUT (bottom row) and the BeatStep plays at the project's own 126 BPM."),
    ("Ride the knobs", "JAM &gt; KNOBS", "wf-03", [(20, 132, 612, 170)],
     "KNOBS shows exactly what the BeatStep's 16 knobs do while you jam: bass filter, resonance, envelope and drive "
     "first.",
     "Press <b>CNTRL</b>, then turn knob <b>1</b> to open the acid line and knob <b>2</b> to make it squelch.",
     "You don't need this screen open: the knobs do the same on PROJECTS. Come here to see the values."),
    ("Swap the bass", "SOUNDS &gt; SYNTH 1", "wf-04", [(26, 146, 154, 284), (194, 148, 810, 310)],
     "Tap <b>BASS</b>, then a sound, here Reese Rumble. It plays straight into the groove. PREV and NEXT step through "
     "the basses only.",
     "Nothing to change: Seq 1 keeps playing, now through the new sound.",
     "BeatStep pad <b>14</b> (Synth 1 Next Sound) steps through sounds without touching the screen."),
    ("Fatten the drums", "SOUNDS &gt; DRUMS &gt; BUS", "wf-05", [(20, 138, 612, 168)],
     "The project already set the bus for acid. Turn up <b>Punch</b> for weight and <b>Room</b> to put the kit in a "
     "space; Width spreads the hats.",
     "On this page the 16 knobs are the bus: knob 1 Punch, 2 Room, 4 Width, 5 Tone.",
     "Tap <b>JAM</b> at the bottom: it takes you straight back to PROJECTS."),
    ("Perform", "JAM &gt; LIVE FX", "wf-06", [(26, 262, 1230, 200)],
     "Hold <b>REPEAT 1/16</b> for a stutter or <b>FILTER SWEEP</b> for a build. Let go and it drops back in. SCENES "
     "saves and morphs whole setups.",
     "With LIVE FX open, pads 1-8 are these eight effects. Hold to play.",
     "Pad <b>9</b> holds a drum fill, pad <b>11</b> starts recording."),
    ("Mutate for the next section", "JAM &gt; PROJECTS", "wf-07", [(792, 376, 470, 180)],
     "Pick <b>MEDIUM</b>, tap <b>MUTATE ALL</b>. New bass, lead and drums land on the next bar, still in the acid "
     "style. Not feeling it? <b>BACK</b>.",
     "Keep playing: nothing stops while the sounds change.",
     "Say “mutate” or “mutate drums”, or set AUTO to every 16 bars and let it evolve."),
    ("Bounce the good bit", "CAPTURE &gt; STEMS", "wf-08", [(28, 166, 800, 196)],
     "Tap <b>4 BARS</b>, then <b>BOUNCE NEXT</b>. It waits for the next bar, then records exactly 4 bars: the mix plus "
     "drums, Synth 1, Synth 2 and FX as separate WAVs that loop. Already played it? <b>GRAB LAST</b> saves the 4 bars "
     "you just heard (also on LIVE FX, pad 15).",
     "Keep it playing until the bar counter finishes.",
     "With STEMS open, BeatStep pad <b>3</b> bounces 4 bars (pads 1-4 = 1, 2, 4, 8 bars)."),
    ("Chop it on the MPC", "CAPTURE &gt; STEMS", "wf-09", [(854, 100, 412, 400), (26, 552, 668, 170)],
     "Tap <b>▶</b> beside a bounce to hear it, then <b>SEND</b> the good one: it lands on the MPC's SD card in "
     "PotentialBox Loops. (AUTO-SEND: ON sends every bounce straight away.) Tap a bounce's name to open its folder "
     "on the PC.",
     "On the MPC, open the browser, go to PotentialBox Loops and load the stems into a program to chop.",
     "Pad <b>9</b> listens to the last bounce, pad <b>5</b> sends it. On JAM, <b>BOUNCE NEXT + SEND</b> does both "
     "steps in one tap."),
]
for n, (title, where, shot_name, boxes, screen, bsp, free) in enumerate(WF, 1):
    add(f'<div class="wfstep"><h2><span class="wfn">{n}</span>{E(title)}<span class="wfw">{where}</span></h2>')
    img_hl(shot_name, "", boxes)
    table(["", ""], [(b("On screen"), screen), (b("On the BeatStep"), bsp), (b("Hands-free"), free)], "wf")
    add("</div>")
note("BeatStep pad actions assume its Control Mode pads are on MIDI channel 16 (see Setting up the BeatStep Pro). "
     "Ctrl + 1 to 5 on the keyboard jump between the five sections.")
end()
# ============================================================================ projects
chapter("JAM: Projects", "PROJECTS is the screen to jam from. It gives your 16 BeatStep Pro genre sets their sounds: "
        "load a project here and Synth 1 gets a bass, Synth 2 a lead, the drums a genre kit, and the effects and tempo "
        "change to suit. MUTATE then changes the sounds while the music plays.")
img("projects", "JAM &gt; PROJECTS with project 7, Acid, loaded.")
h2("Load a project")
steps(["On the BeatStep, choose the project: hold PROJECT and press the step button with its number.",
       "In PotentialBox, tap the same number. With PROJECTS open you can also press the BeatStep pad with that number "
       "(Control Mode pads on MIDI channel 16), or tap TALK and say “project seven”.",
       "Press PLAY on the BeatStep. Seq 1 plays the bass, Seq 2 the melody as chords and the drum sequencer the kit."])
p("NOW PLAYING shows the project's tempo and key and the three sounds it loaded. Each has its own MUTATE key. "
  "Tapping the project that's already loaded loads it again, which puts back any knobs you've turned. PREVIOUS and NEXT "
  "step through the projects in order.")
h2("Chords and bass")
p("Each pattern of a genre set is 4 bars long, with a chord for each bar. Seq 1's bassline follows the chord roots. Seq "
  "2 plays a 4-bar melody, and every project's Synth 2 sound plays it as chords in the project's key: drum tracks 9-15 "
  "carry the progression (the Chord lane, see Modulation, step LFOs and chords), so each bar is voiced as the right "
  "chord with the melody on top. The basses keep a clean sine sub, and the chords leave the low end to them.")
h2("What each project loads")
rows = []
for i, pr in enumerate(projmod.PROJECTS):
    rows.append((f'<span class="kn">{i + 1}</span>', b(pr["name"]), str(pr["bpm"]), E(pr["key"]),
                 E(" / ".join(n for n, _ in pr["bass"])), E(" / ".join(n for n, _ in pr["lead"])),
                 E(" / ".join(kits.NAMES[k] for k in pr["kits"]))))
table(["#", "Genre", "BPM", "Key", "Synth 1 (Seq 1)", "Synth 2 (Seq 2)", "Kit"], rows, "compact")
h2("New sounds")
ul([f"{b('NEW SOUNDS')} steps through pairings of each project's two basses, two leads and two kits.",
    f"{b('KIT: MY SAMPLES')} makes the kit with the Kit Maker from your own one-shots, in a style that suits the genre. "
    f"{b('KIT: BUILT-IN')} goes back to the built-in kits.",
    f"{b('PROJECT FX + TEMPO')} on: a project also sets the delay, reverb, lo-fi, chorus, ducking, drum drive and "
    "filter, and the tempo. Turn it off to keep your own effects and tempo and change only the sounds.",
    "The BeatStep's knobs here are the same 16 as on JAM &gt; KNOBS: Synth 1's filter, resonance, envelope and drive, "
    "Synth 2's filter, wave position, envelope and decay, kick and snare tune, the drum filter and drive, delay, reverb, "
    "lo-fi and master."])
h2("Mutate: change the sounds while it plays")
p("MUTATE gives the bass, the lead and the drums new sounds without stopping the music. It stays inside the project's "
  "own sounds: each synth moves somewhere between the project's two sounds for that part, with a little randomness. So "
  "a Trap 808 stays an 808, and an acid line stays acid.")
ul([f"{b('MUTATE ALL')} changes all three; the MUTATE key on a NOW PLAYING row changes just that part.",
    f"{b('MILD')} nudges the sound, {b('MEDIUM')} moves it further and may swap a couple of drum sounds, {b('WILD')} goes "
    "to the edges and can swap the kick and snare too.",
    "While the BeatStep plays, the change waits for the next bar. New drums land on the one, and the synths glide to "
    "their new sound over a bar, so nothing jumps.",
    f"{b('BACK')} goes back to the sounds before the last mutation (16 steps of history).",
    f"{b('AUTO')}: every 8 or 16 bars, a mild mutation of the bass, lead or drums, so a long set keeps changing by itself.",
    "Project basses keep their clean sine sub: MUTATE never makes a bass grittier or takes sub away."])
h2("The drums are in the sets' order")
p("The genre sets play their drums on these BeatStep drum tracks, and a project kit puts the right sound on each one:")
table(["Drum track", "Plays"], [("1", "Kick"), ("2", "Clap"), ("3", "Snare"), ("4", "Percussion (conga, cowbell or clave)"),
                                ("5", "Closed hat"), ("6", "Open hat"), ("7", "Rim"), ("8", "Shaker"),
                                ("9-16", "The kit's other sounds: 808, toms, clave, cymbal, FX")], "knobs short")
h2("Play: tempo, clock, talk")
ul([f"{b('−')} and {b('+')} set the tempo while PotentialBox is its own clock.",
    f"{b('CLOCK OUT')} makes PotentialBox the clock: the BeatStep (SYNC set to USB) plays at each project's tempo.",
    f"{b('TALK (MIC)')} turns the microphone on. Say any of these; tap it again or say “stop listening” to turn it off."])
table(["Say", "What happens"], [
    ("“project one” … “project sixteen”", "Loads that project"),
    ("A genre: " + ", ".join(f"“{n.lower()}”" for n in projmod.NAMES), "Loads that genre's project"),
    ("“next project”, “previous project”", "Steps through the projects"),
    ("“new sounds”", "Same as NEW SOUNDS"),
    ("“mutate”, “mutate bass”, “mutate lead”, “mutate drums”", "Mutates at the next bar"),
    ("“mild”, “medium”, “wild”", "Sets how far MUTATE goes"),
    ("“go back”", "Same as BACK"),
    ("“auto mutate”, “stop mutating”", "Auto mutate every 8 bars, or off"),
    ("“stop listening”", "Turns the mic off")])
note("Voice uses Windows' own speech recognition and your default microphone. It works offline. If it says speech "
     "recognition isn't installed, add an English speech language in Windows: Settings &gt; Time &amp; language &gt; Speech.")
h2("The BeatStep's pads on PROJECTS")
pads_table(PROJECT_PADS, "Pad", "Projects pad")
end()
# ============================================================================ 17 live
chapter("JAM: Live FX", "JAM &gt; LIVE FX is for playing: hold-to-play effects over the whole mix, scenes you can "
        "morph between, fill and record, all one tap away.")
img("live", "JAM &gt; LIVE FX.")
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
h2("Grab what you just played")
p("The best bit always happens when you're not recording. PotentialBox is always listening: it keeps the last 34 "
  "seconds of the mix and every part, so you can save a loop after you've played it.")
steps(["Jam. When something good happens, tap <b>GRAB LAST 4 BARS</b> (or LIVE FX pad 15).",
       "It snaps to the nearest bar line. Tap early in a bar and it takes the 4 bars before it, straight away; tap "
       "later in a bar and the display says FINISHING THIS BAR, then it includes that bar too.",
       "It says GRABBED and the loop is saved like a bounce: the mix plus each part, exactly 4 bars, in Music &gt; "
       "PotentialBox Loops, listed under YOUR BOUNCES on CAPTURE, and sent to the MPC if AUTO-SEND is on."])
ul(["The keys under GRAB set the length: 1, 2, 4 or 8 bars. It's the same length as BOUNCE on CAPTURE.",
    "If it hasn't heard that many bars yet (you've only just started), it saves as many as it has.",
    "Bars come from the BeatStep's clock, CLOCK OUT or the beat generator. With nothing keeping time, it saves the "
    "length up to the moment you tapped."])
h2("Bounce and send from here")
p(f"{b('BOUNCE NEXT 4 BARS + SEND')} is BOUNCE and SEND in one tap, so you don't have to leave JAM. It waits for the "
  "next bar, records the bars (the key counts them and shows a line), saves the stems like any bounce, then sends "
  "them to the MPC, even if AUTO-SEND is off. A message pops up when they're on the MPC. Tap it again while it's "
  "bouncing to stop. The length is the same 1, 2, 4 or 8 bars as GRAB.")
h2("Fill and record")
ul([f"{b('HOLD FOR FILL')} (pad 9) plays the drum pads set to Fill only and silences those set to Not in fill.",
    f"{b('RECORD')} (pad 11) starts and stops recording, the same as RECORD on CAPTURE &gt; STEMS. "
    f"{b('STEMS: ON')} records each part as its own file too; OFF records the mix only.",
    f"{b('RESAMPLE TO A PAD')} and {b('MY SETUPS')} open the same screens as on CAPTURE and SETUP."])
h2("The BeatStep's pads on LIVE FX")
p("While LIVE FX is open, the 16 pads that normally run pad actions play the Live pads instead:")
pads_table(LIVE_PADS, "Pad", "Live pad")
end()

# ============================================================================ 14 macros
chapter("JAM: Knobs and Macros", "JAM &gt; KNOBS shows the BeatStep's 16 knobs as they work on PROJECTS: the "
        "moves you reach for first while jamming.")
img("perform", "JAM &gt; KNOBS.")
knob_table("Perform")
h2("Macros")
p("JAM &gt; MACROS turns the BeatStep's 16 knobs into performance controls. Each macro moves several "
  "settings at once in a musical way: sweeps, throws, risers and drops.")
img("macros", "JAM &gt; MACROS. The top of the page describes the last macro you touched.")
note("<b>Macros never overwrite your sound.</b> They work on top of your settings, so turning a macro back to zero puts "
     "everything back exactly where it was. DJ Filter rests in the centre. ZERO ALL MACROS resets them all at once.")
knob_table("Macros")
h2("Ideas")
ul(["Build-Up then back to zero gives an instant drop: the kick comes back on the way down.",
    "Ride Dub Throw on the last beat of a phrase, then pull it back.",
    "DJ Filter left for a muffled breakdown, right for a thin, tense one.",
    "Acid plus a little Glide on Synth 1 basslines."])
end()

# ============================================================================ 11 sounds
chapter("SOUNDS: the sound browser", "SOUNDS &gt; SYNTH 1 and SYNTH 2 open on a sound browser: every preset, "
        "sorted by type, one tap to load. The deep settings are one tap further, under EDIT SOUND.")
img("browser-s1", "SOUNDS &gt; SYNTH 1: the sound browser, showing the basses.")
ul([f"Tap a {b('type')} on the left (ALL, BASS, LEAD, KEYS, PAD, PLUCK, STAB, FX or MY SOUNDS) and the display "
    "shows its sounds. The number beside a type is how many sounds it has.",
    f"Tap a {b('sound')} to load it; it plays a test note. The loaded sound is lit.",
    f"{b('◂ PREV')} and {b('NEXT ▸')} step through the type you're looking at. ◂ PAGE and PAGE ▸ at the bottom of the "
    "display turn the page when a type has more than 24 sounds.",
    f"{b('TEST')} plays a note; {b('RANDOM')} rolls a brand-new playable sound.",
    f"{b('SAVE SOUND')} opens your 8 save slots (My Sounds). Saved sounds appear under MY SOUNDS.",
    f"{b('EDIT SOUND ▸')} opens the synth's edit pages (see Synth 1 and Synth 2). {b('◂ SOUNDS')} on the edit pages, or "
    "tapping the SYNTH sub-tab again, comes back here."])
h2("The knobs under the browser")
p("Under the browser are the 16 knobs you'll reach for most, and the BeatStep's knobs turn them while the browser is "
  "open. They're the same settings as on the edit pages.")
h3("Synth 1")
knob_table("Synth 1 Quick", with_desc=False)
h3("Synth 2")
knob_table("Synth 2 Quick", with_desc=False)
h2("The sounds")
p("Every sound was made for the current engine: unison and supersaw, clean subs, filter drive, the five distortions, "
  "the synth's own chorus, ensemble, dimension, phaser and flanger, comb and formant filters, FM, ring mod and sync on "
  "Synth 1, and the 30 wavetables with the warp modes on Synth 2. They are level-matched: each sound has its own "
  "Sound level (the last knob of the ENV page), so moving between them doesn't jump in volume, and your volume "
  "knob stays where you put it.")
for pre, title in (("s1", "Synth 1"), ("s2", "Synth 2")):
    h3(title)
    rows = []
    for cat in PRESET_CATS[1:]:
        names = [n for n, _ in PRESETS[pre] if PRESET_CAT[pre][n] == cat]
        if names:
            rows.append((b(cat), E(", ".join(names))))
    table(["Type", "Sounds"], rows)
note("Most stabs, pads and keys play <b>chords</b> from one note (Synth 1 and Synth 2 are mono synths that play up to "
     "4-note chords). Chord Memory, Scale 7th Keys and Scale 9th Pad use scale chords: set Chord key and Chord scale on "
     "the OSC+ page to your song's key (C minor out of the box).")
h2("My Sounds")
img("sounds", "My Sounds: 8 slots for each synth.", "small")
ul([f"{b('SAVE HERE')} stores the sound you are hearing. No typing: slots are named My Sound 1 to 8 and remember which "
    "sound they were made from.",
    "On a full slot, SAVE HERE asks you to tap again within 3 seconds, so one slip can't overwrite a sound.",
    f"{b('LOAD')} plays the saved sound back."])
p("The Synth panels on other pages (under the knobs) have < PREV, NEXT >, TEST, RANDOM and MY SOUNDS too; their PREV "
  "and NEXT step through every sound: Init, the presets, then your saved sounds.")
note("<b>Start from scratch:</b> tap INIT SYNTH on the synth's MAIN edit page, or <b>RESET ALL TO INIT</b> on SOUNDS &gt; "
     "MIX (tap twice) to reset every knob in the app. Saved sounds, kits and setups are kept.")
end()
# ============================================================================ 7 synth 1
chapter("Synth 1", "An analog-style synth: two oscillators that blend from saw to square, a supersaw, unison, a sub "
        "oscillator, a resonant filter with seven types, drive, distortion and its own effects. It is played by "
        "Sequencer 1.")
p("Tap <b>EDIT SOUND ▸</b> in the sound browser to open Synth 1's nine pages: MAIN, OSC+, UNI+FX, MOD, MOD2, ARP+, "
  "ENV and the two LFO step pages. <b>◂ SOUNDS</b> goes back to the browser. This chapter covers MAIN, OSC+, UNI+FX "
  "and ENV; modulation and the arpeggiator have their own chapters.")
note("<b>Start again in one tap:</b> each page has an <b>INIT</b> key beside the page keys. On MAIN it resets the whole "
     "synth; on every other page it resets only that page (INIT OSC+ PAGE, INIT UNI+FX, INIT MODULATION, INIT ARP, INIT ENVELOPES, "
     "INIT LFO STEPS). Afterwards <b>UNDO INIT</b> appears for a few seconds.")
img("synth1-main", "Synth 1, MAIN page.")
h2("MAIN page")
knob_table("Synth 1")
h2("OSC+ page")
img("synth1-oscplus", "Synth 1, OSC+ page.")
knob_table("Synth 1 Osc+")
h2("UNI+FX page: unison, drive, distortion and effects")
p("This page is where a sound gets the width, weight and character of a big software synth.")
img("synth1-uniplusfx", "Synth 1, UNI+FX page.")
ul([f"{b('Unison voices')}: 1, 2, 3, 4, 5 or 7 copies of the whole oscillator pair, each slightly detuned and spread "
    "across the stereo field. Unison detune sets how far apart (a little = thick, a lot = a reese or hoover), Unison "
    "width how wide. The sub stays in the middle, so basses keep a solid low end.",
    f"{b('Filter drive')} pushes the signal into the filter: the grit and thickness of an overdriven analog filter.",
    f"{b('Distortion')}: Tube (warm), Tape (soft and round), Fold (a wavefolder: buzzy, metallic, great on basses), "
    "Crush (fewer bits, lower sample rate), Hard clip. It's level-matched, so turning it up adds grit, not volume.",
    f"{b('Synth FX')}: Chorus, Ensemble (lush string-machine chorus), Dimension (subtle, wide), Phaser or Flanger, on "
    "this synth only.",
    f"{b('Sub mode')}: “-1 oct, filtered” goes through the filter; “-1 oct, clean” and “Root, clean” add a pure sine "
    "after the filter and distortion, so the low end stays deep however gritty the rest is."])
knob_table("Synth 1 Uni+FX")
h2("ENV page")
p("All the envelopes in one place, including the multi-stage amp envelope: with Decay 2 above zero the note falls to "
  "Sustain over Decay, then moves on to Sustain 2 over Decay 2 (a pluck that settles into a quieter pad, for example).")
img("synth1-env", "Synth 1, ENV page.")
knob_table("Synth 1 Env")
end()

# ============================================================================ 8 synth 2
chapter("Synth 2", "A wavetable synth: 30 tables that morph as you move the wave position, an LFO that sweeps it, "
        "warp modes, unison in stereo, a resonant filter, distortion and its own effects. It is played by Sequencer 2.")
p("Synth 2 has the same nine pages as Synth 1, under EDIT SOUND ▸ in its sound browser.")
img("synth2-main", "Synth 2, MAIN page.")
h2("MAIN page")
knob_table("Synth 2")
h2("OSC+ page")
img("synth2-oscplus", "Synth 2, OSC+ page.")
knob_table("Synth 2 Osc+")
h2("UNI+FX page: unison, warp, distortion and effects")
img("synth2-uniplusfx", "Synth 2, UNI+FX page.")
p("Unison, filter drive, distortion and the synth FX work as on Synth 1. Synth 2's unison detune is its Unison knob, and "
  "it starts with 2 voices.")
p("<b>Warp</b> reshapes how the wave is read, for new tones from any table: Bend + and Bend − push the wave's shape to "
  "one end, Mirror folds it into a symmetrical wave, Sync is classic hard sync (bright and tearing), Squeeze narrows it "
  "like pulse width, Phase FM adds FM-style overtones and Quantize steps it for a lo-fi, digital edge. Warp amount sets "
  "how far; mod slots can move it (target Warp).")
knob_table("Synth 2 Uni+FX")
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
    (b("Supersaw lead"), "Supersaw (Synth 1 UNI+FX, knob 4) at 70%, a little reverb, slot routed LFO 2 &gt; Supersaw for movement."),
    (b("Evolving pad"), "Synth 2: LFO 2 shape Smooth random, slow speed, slot 3 (LFO 2 &gt; Wave position) at +40%.")])
h2("Chords")
p("The BeatStep's sequencers play one note at a time, but <b>Chord</b> on the OSC+ page turns every step into a chord: "
  + ", ".join(c[0] for c in CHORDS[1:]) + ". <b>Chord voicing</b> spreads it: Close, Open, Wide. All the chord's notes "
  "go through the same filter and envelopes, like a classic paraphonic synth.")
h2("Chords in the key")
p("<b>Scale triad</b>, <b>Scale 7th</b> and <b>Scale 9th</b> build each chord from a scale instead of a fixed shape, "
  "with the note you play on top. Set <b>Chord key</b> and <b>Chord scale</b> on the OSC+ page to the key of your "
  "pattern and every note gets a chord that fits: a one-note melody on Seq 2 becomes a chord progression.")
p("<b>Chord lane</b> goes one step further. Turn it on and BeatStep drum tracks 9 to 15 stop playing drums and instead "
  "say which chord the music is on: track 9 is chord I, track 10 chord II, up to track 15, chord VII. Put one hit on the "
  "first step of a bar and every note in that bar is voiced as that chord, with the melody on top. The 16 genre sets "
  "have their chord progression written into these tracks.")
note("<b>Heavy patches</b> (chords and supersaw on both synths with lots of modulation) use more of your PC. Watch LOAD "
     "on SETUP and choose the next buffer size up if you hear crackles.")
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
p("Tap <b>KITS</b> on the drum panel (under the knobs on SOUNDS &gt; DRUMS), or &lt; and &gt; to step through kits. <b>KIT MAKER</b> beside it builds a new "
  "kit from your own samples (see Kit Maker).")
img("kits", "The Kit menu: built-in kits, recent kits, My Kits and the drum machine library.")
genre_of = {}
for G in beats.GENRES:
    genre_of.setdefault(G[4], []).append(G[0])
table(["Kit", "Sound", "BEATS genres that use it"],
      [(b(k["name"]), E(k["desc"]), E(", ".join(genre_of.get(i, [])) or "–")) for i, k in enumerate(kits.KITS)])
p("Every built-in kit is synthesized the way the original machine or instrument makes its sound: kicks with a "
  "two-stage pitch drop, a beater click and saturation; snares with two tuned drum modes and shaped snare wires; the "
  "808's six metal oscillators for hats and cymbals; modal toms, congas and log drums. Each pad is levelled for its "
  "role, and each sits in its own place in the stereo field (see the BUS page).")
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
h2("The drum bus")
p("The BUS page (the first page of SOUNDS &gt; DRUMS) processes the whole kit, like the drum bus on a mixing desk. "
  "Picking a genre on BEATS, or loading a project, sets it for that genre: a punchy, roomy break for boom bap and "
  "jungle, a tight dry kit for trap and drill, a big hall on the dub snare.")
img("drums-bus", "SOUNDS &gt; DRUMS, BUS page.")
ul([f"{b('Punch')}: parallel compression. A heavily squashed copy of the kit is blended in under the dry kit, so it "
    "gets thicker and punchier without losing its hits.",
    f"{b('Room')} and {b('Room size')}: a short room on the whole kit (without the kick's low end), so the drums sound "
    "like they were played in a space.",
    f"{b('Width')}: how far the hats, toms and percussion spread left and right, like a real kit. Kicks and snares stay "
    "in the middle. Each pad's own PAN (MIX pages) moves it from there.",
    f"{b('Tone')}: darker to the left, brighter to the right.",
    f"{b('Drive')}, {b('Crush')} (fewer bits and a lower sample rate, SP-1200 style) and {b('Filter')}.",
    f"{b('Kit tune')} tunes every pad up or down at once."])
knob_table("Drums Bus", with_desc=False)
h2("Drum knobs")
p("SOUNDS &gt; DRUMS also has seven pages, each for pads 1-8 or 9-16:")
ul([f"{b('TUNE 1-8')} and {b('TUNE 9-16')}: a tune knob (semitones) and a length knob (shortens the sound) for each pad.",
    f"{b('MIX 1-8')} and {b('MIX 9-16')}: a level and a pan knob for each pad.",
    f"{b('GROOVE 1-8')} and {b('GROOVE 9-16')}: chance and plays-when for each pad (below).",
    f"{b('CHOKE')}: a choke group (1-8) for each of the 16 pads. When a pad plays, it cuts off every other pad in its "
    "group: put an open hat and a pedal hat together, or a long 808 and a second 808."])
img("drums-groove1-8", "SOUNDS &gt; DRUMS, GROOVE 1-8 page.")
h3("Chance and conditions")
p("These make a short BeatStep pattern feel longer and more alive, like Elektron's trig conditions.")
ul([f"{b('Chance')}: at 100% the pad always plays. At 70% about 3 hits in 10 are skipped, at random. Great on hats and "
    "percussion.",
    f"{b('Plays when')}: " + ", ".join(SPECS["dr.p1.cond"].choices) + ".",
    "1st of 4 means “only in the first bar of every four”: build a crash on bar 1 or a fill on bar 4 from a one-bar "
    "pattern. Bars are counted from when you press Play on the BeatStep.",
    "Fill only pads play only while you hold FILL; Not in fill pads drop out while you hold it."])
img("drums-choke", "SOUNDS &gt; DRUMS, CHOKE page.")
end()

# ============================================================================ 13 build your own kit
chapter("Build your own kit", "Put any single drum sound on any pad, shape it, and save the result as your own kit.")
steps(["Tap a pad on the drum panel. It plays and gets highlighted.",
       "Tap <b>EDIT PAD</b>.",
       "Pick a type on the left: Kick, 808 / Bass, Snare, Clap, Hats, Toms, Perc, Cymbal, FX / Vox or All. The list shows "
       "every matching sound in your drum machine collection and your sample folders, with the machine or pack it "
       "comes from.",
       "Tap a sound. It goes on the pad and plays straight away. Keep tapping until you like it.",
       "Use the pad strip along the top to move to the next pad.",
       "Tap <b>SAVE MY KIT</b> and choose a slot."])
img("pad", "The pad editor.")
ul([f"{b('RANDOM')} picks a random sound of the chosen type: great for happy accidents.",
    f"{b('ALL / THIS SOURCE')}: THIS SOURCE limits the list to the drum machine or sample pack the pad's sound comes "
    "from.",
    f"{b('FROM FILE...')} takes any WAV file on your PC.",
    f"{b('LOCK PAD')} keeps this pad's sound when you make a new kit in the Kit Maker or roll a {b('Random Drum Kit')} "
    "(pad action or LIVE FX pad 14).",
    "Silence at the start of every drum sound is trimmed automatically, so hits land exactly on the beat."])
h2("Edit this pad's sound")
table(["Key", "What it does"], [
    (b("TRIM"), "Cuts silence off the start and end."),
    (b("NORMALIZE"), "Makes the sound as loud as it can be without clipping."),
    (b("FADE IN / FADE OUT"), "A 50 ms fade at the start or the end (softens clicks)."),
    (b("PITCH −1 / PITCH +1"), "Re-pitches the sample by a semitone, like a sampler (it gets shorter or longer). "
                              "For tuning without changing the sample, use the pad's Tune knob.")])
note("Sound edits last until you put another sound on the pad or close PotentialBox. They aren't saved in My Kits, which "
     "remember the sample files themselves (and, from version 1.10, each pad's pitch, length, level, pan and choke "
     "knobs).", "warn")
h2("My Kits")
img("mykits", "My Kits: 8 slots for your own kits.", "small")
p("Open it from the Kit menu or the pad editor. SAVE HERE stores every pad of the current kit; a full slot needs two "
  "taps to replace. LOAD brings the kit back. An edited kit shows a * after its name and comes back when you restart, "
  "even before you save it.")
end()

# ============================================================================ kit maker
chapter("Kit Maker", "The Kit Maker builds a whole 16-pad kit from your own one-shots in one tap, the way PotentialKits "
        "does on the MPC: a kick, a snare, hats, toms, percussion and a few surprises, from every drum machine and "
        "sample folder you have. Lock the pads you like and roll the rest.")
img("kitmaker", "The Kit Maker: the 16 pads, the styles, and the selected pad on the right.")
h2("Make a kit")
steps(["Tap <b>KIT MAKER</b> on the drum panel (or in the Kit menu).",
       "Tap <b>NEW KIT</b>, or a <b>STYLE</b>. The kit loads and plays a short preview. Levels are evened out for you.",
       "Tap a pad tile to hear it. Tap <b>LOCK</b> under a pad you want to keep.",
       "Tap NEW KIT or ROLL again until you like it. <b>PREVIOUS KIT</b> goes back, up to 12 kits.",
       "Tap <b>SAVE MY KIT</b> to keep it in a slot."])
h2("Rolling")
table(["Key", "What it does"], [
    (b("ROLL MILD"), "Up to four unlocked pads get another sound of the same type. Their pitch and length stay."),
    (b("ROLL MEDIUM"), "A new kit in the same style with a little pitch and length added."),
    (b("ROLL WILD"), "A new kit where any pad (except the kick and snare) can be any type, pitched up to 7 semitones "
                     "either way. Great for strange percussion kits.")])
h2("Styles")
p("A style decides what each pad draws from, how it is tuned, how long it rings, and which machines or packs it leans "
  "towards (by words in their folder names, such as 808, SP-1200 or Jazz). Tap one for a new kit in that style.")
table(["Style", "What you get"], [(b(st["name"]), E(st["desc"])) for st in kitmaker.STYLES])
p("On BEATS, <b>GENRE KIT: SAMPLES</b> makes each genre's kit in the Kit Maker: Trap gets a TRAP kit with an 808 "
  "on pad 2, Boom Bap a BOOM BAP kit, Afrobeats a PERCUSSION kit and so on.")
h2("The selected pad")
ul([f"{b('PLAY')} plays it, {b('NEW …')} puts another sound of the same type on it, {b('LOCK')} keeps it.",
    f"{b('TYPE')}: tap any type (kick, 808, snare, clap, rim, closed or open hat, tom, conga, shaker, cowbell, clave, "
    "perc, cymbal, FX, vox, stab, other) and the pad gets a sound of that type. The small number is how many you have.",
    f"{b('PITCH')}, {b('LENGTH')} and {b('LEVEL')}: one tap per step. These are the same as the pad's knobs on the "
    "Drums tab.",
    f"{b('PICK FROM LIST')} opens the pad editor (see Build your own kit) to choose a sound by name."])
h2("Where the sounds come from")
ul([f"{b('DRAW FROM')}: EVERYTHING, only your DRUM MACHINES (the Drum Machine Collection) or only MY FOLDERS.",
    f"{b('ONE SOURCE')}: the whole kit from one drum machine or sample pack where it has the sounds.",
    f"{b('MATCH LEVELS')} evens out every pad again (new kits do this by themselves), with hats and cymbals sitting a "
    "little lower than kicks and snares.",
    "The Random Drum Kit pad action (and LIVE FX pad 14) makes a Kit Maker kit in the current style once you have samples."])
h2("Sample folders")
img("ksources", "SAMPLE FOLDERS: your drum machines, your own folders, and GET MPC ONE-SHOTS.")
p("Tap <b>SAMPLE FOLDERS</b> to choose where sounds come from. Your Drum Machine Collection is always there; "
  "<b>ADD A FOLDER</b> adds any folder of one-shots (its subfolders are read too). PotentialBox sorts every sound by the "
  "words in its folder and file names (Kicks, Snare, OH, Conga, 808 ...), and leaves out loops and long files. WAV and "
  "AIFF files are read. Only new or changed files are looked at again, so it starts quickly.")
h3("GET MPC ONE-SHOTS")
p("MPC TOOLS' DRUM ONE SHOTS button gathers every drum one-shot on your MPC into one folder on its SD card, sorted into "
  "Kicks, Snares, Claps, Hats, Cymbals, Toms and Percs. <b>GET MPC ONE-SHOTS</b> copies that folder to "
  "<code>Music\\MPC Drum One Shots</code> on your PC and adds it to your sample folders.")
ul(["It uses Windows' own SSH and the login MPC TOOLS already set up, so there's no password to type. The MPC's address "
    "comes from MPC TOOLS (the first time only, if it can't find it, PotentialBox asks for it).",
    "Tap it again any time: only sounds that aren't on the PC yet are copied.",
    "FLAC and MP3 files are left on the MPC (PotentialBox plays WAV and AIFF)."])
end()

# ============================================================================ 20 mix
chapter("SOUNDS: Mix", "SOUNDS &gt; MIX has three pages: MAIN (levels, ducking, glue), EQ and MUTE/SOLO.")
img("mix-main", "The Mix tab, MAIN page.")
knob_table("Mix")
note("<b>RESET ALL TO INIT</b> at the top of MIX resets every knob in the app (both synths, all pads, mix, "
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
chapter("SOUNDS: FX", "SOUNDS &gt; FX has two pages: SENDS (delay and reverb) and MASTER (the effects on the whole mix).")
img("fx-sends", "The FX tab, SENDS page.")
knob_table("FX")
ul([f"{b('Delay')}: a ping-pong delay locked to the tempo, with a send from each instrument.",
    f"{b('Reverb')}: a smooth room-to-hall reverb with a send from each instrument.",
    f"{b('DJ filter')}: centre is off, left is low-pass, right is high-pass, on the whole mix."])
h2("MASTER page")
img("fx-master", "The FX tab, MASTER page.")
knob_table("Master FX")
p("The master chain runs in this order: chorus, flanger, phaser, compressor, distortion, DJ filter and lo-fi, EQ, glue, "
  "width, LIVE FX's punch-in effects, then master level and drive into the limiter. With the limiter at 0 a gentle "
  "soft clip catches the peaks instead.")
end()

# ============================================================================ 15 beats
chapter("BEATS: the beat generator", "The BEATS makes drum beats in the style of a genre. Tap a genre and you get a beat; tap "
        "NEW BEAT for another take, as often as you like. When you have one you like, SEND TO BEATSTEP records it "
        "into the BeatStep's drum sequencer, where it carries on like a beat you programmed yourself.")
img("beats", "BEATS: knobs on top, the genres, the beat (tap a dot to change it), and the keys.")
h2("Make a beat")
steps(["Tap a genre. With GENRE KIT: BUILT-IN its usual kit loads too (GENRE KIT: SAMPLES makes one from your own "
       "samples in the Kit Maker), and if the BeatStep is stopped the tempo is set for it.",
       "Tap <b>PLAY</b>. While the BeatStep plays, the beat locks to its clock; when it's stopped, the beat runs on its "
       "own tempo (change it with − and +).",
       "Tap <b>NEW BEAT</b> for a different take and <b>MUTATE</b> to change just one part. Lost one you liked? "
       "<b>◀ BACK</b> goes back to the beat before (Beats pad 3), as many times as you need.",
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
    "hats or percussion.",
    "◀ BACK undoes NEW BEAT, MUTATE, SIMPLER, BUSIER, NEW ENDING, LENGTH, genre changes and taps on the grid, up to 40 "
    "steps; the key shows how many are left. Going back past a genre change brings back that genre's kit, drum bus "
    "and tempo too."])
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
       "Tap <b>CLOCK OUT</b> on BEATS (it stays on next time).",
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
h2("The BeatStep's pads on BEATS")
pads_table(BEAT_PADS, "Pad", "Beats pad")
end()

# ============================================================================ 16 arrangement
chapter("BEATS: Arrange", "BEATS &gt; ARRANGE chains beats into a song: they play in order, each for its own "
        "length (1, 2 or 4 bars), then round again.")
img("arrangement", "BEATS &gt; ARRANGE: the song on the left, the keys on the right. Beat 3 is playing.")
steps(["Make a beat on BEATS.",
       "On ARRANGE, tap <b>ADD CURRENT BEAT</b> (or the “+ ADD THE BEAT” space). Up to 16 beats.",
       "Go back to BEATS, make the next beat, add it, and so on.",
       "Tap <b>PLAY SONG</b>. With CLOCK OUT on, it starts the BeatStep too."])
ul([f"{b('Tap a beat')} while the song plays to jump to it. While it's stopped, tapping a beat puts it on BEATS "
    "to hear and change (add it again to keep the change).",
    f"{b('REMOVE LAST')} takes the last beat off; {b('CLEAR SONG')} (tap twice) empties the song.",
    f"{b('SAVE SONG AS MIDI FILE')} saves the whole song as one .mid file in Music &gt; PotentialBox Recordings.",
    "The bottom line shows how many beats and bars the song has and how long it lasts at the current tempo.",
    "The song is saved with your settings."])
h2("Knobs")
knob_table("Arrangement")
end()

# ============================================================================ capture
chapter("CAPTURE: stems, recording and the MPC", "CAPTURE &gt; STEMS turns a jam into samples: one tap bounces what's "
        "playing as loops that are exactly 1, 2, 4 or 8 bars long, the mix plus a file for each part, ready to chop on "
        "your MPC or drop into a DAW.")
img("capture", "CAPTURE &gt; STEMS.")
h2("Bounce stems")
steps(["Play something: the BeatStep, a project, BEATS or the looper.",
       "Tap a <b>LENGTH</b>: 1, 2, 4 or 8 bars.",
       "Tap <b>BOUNCE NEXT</b>. While the BeatStep (or CLOCK OUT) is playing it waits for the next bar, then records exactly "
       "that many bars. The display and the progress bar show which bar it's on. CANCEL stops it.",
       "It says SAVED and the bounce appears under YOUR BOUNCES. Tap its name to open its folder."])
p("Each bounce is a folder in <b>Music &gt; PotentialBox Loops</b>, named with the project, tempo, length and time, "
  "for example <code>Acid 126bpm 4bar 211405</code>. Inside are 24-bit WAV files:")
table(["File", "What's in it"], [
    (b("… - Mix.wav"), "Everything you hear, after the master effects."),
    (b("… - Drums.wav"), "The drum sampler, with its EQ and ducking."),
    (b("… - Synth 1.wav, … - Synth 2.wav"), "Each synth with its own effects, EQ and ducking, dry of the delay and reverb."),
    (b("… - FX.wav"), "The delay and reverb returns."),
    (b("… - Looper.wav"), "The looper's tracks.")])
ul(["Every file is exactly the same length, sample for sample, so they loop and line up.",
    "Parts that were silent are left out.",
    "The parts are dry of the master effects (compressor, glue, limiter), which are on the mix only.",
    "When nothing is playing, BOUNCE records straight away instead of waiting for a bar."])
h2("Grab the last bars")
p("<b>GRAB LAST</b> is BOUNCE backwards: it saves the bars you've <i>just played</i>, from the last 34 seconds "
  "PotentialBox always keeps. Same length keys, same files, same folder, same AUTO-SEND. It's also on JAM &gt; LIVE FX "
  "(pad 15) and STEMS pad 8; the chapter on LIVE FX explains how it picks the bars.")
h2("Send to MPC")
p("PotentialBox can copy bounces to your MPC over Wi-Fi, the way MPC TOOLS does. They go to a "
  "<b>PotentialBox Loops</b> folder on the MPC's SD card (the drive with MPC TOOLS' DRUM ONE SHOTS or a MYMPC folder), "
  "one folder per bounce, so you'll find them in the MPC's browser.")
ul([f"{b('▶')} beside a bounce in YOUR BOUNCES loops its mix so you can check it's the good take; {b('■')} (or "
    "leaving CAPTURE) stops it. You only hear it: it never ends up in a GRAB, bounce or recording. STEMS pad 9 "
    "listens to the newest one.",
    f"{b('SEND LAST BOUNCE')} sends the newest one; {b('SEND')} beside any bounce in YOUR BOUNCES sends that one. It "
    "says SENT ✓ once it's on the MPC. Send another while one is going and it goes next.",
    f"{b('AUTO-SEND: ON')} sends every bounce as soon as it's saved. Leave it OFF to listen first and send the ones you "
    "like.",
    "It uses Windows' own SSH and the key login MPC TOOLS already set up, and the MPC's address from MPC TOOLS, so "
    "there's nothing to type. The status line says where the files went, or what went wrong."])
h2("Record and resample")
ul([f"{b('RECORD (ANY LENGTH)')} records until you tap it again: the mix plus Drums, Synth 1, Synth 2, FX returns "
    "and Looper as separate files that line up, in Music &gt; PotentialBox Recordings, one folder per take. The "
    "Record On/Off pad action and LIVE FX pad 11 do the same.",
    f"{b('RESAMPLE PAD')} records Synth 1, Synth 2, both synths, the FX returns or everything, for half a bar to 4 bars, "
    "onto a drum pad. Save the kit in My Kits to keep it.",
    f"{b('OPEN LOOPS')} opens the PotentialBox Loops folder; {b('RECORDINGS')} opens the recordings folder."])
img("resample", "Resample: choose what to record, how long, and which pad.", "small")
h2("Knobs")
p("While STEMS is open the BeatStep's knobs ride the levels, sends and filters, so you can shape a bounce as it records:")
knob_table("Capture", with_desc=False)
h2("The BeatStep's pads on STEMS")
pads_table([n or "–" for n in CAPTURE_PADS], "Pad", "Stems pad")
end()
# ============================================================================ 18 loop
chapter("CAPTURE: Looper", "A 5-track looper, inspired by the BOSS RC-505: record a phrase, it plays round and round, add "
        "more on top or on other tracks, and build a song live. It records the inputs of your audio interface (mic, "
        "guitar, keys) and PotentialBox's own synths and drums.")
img("loop", "CAPTURE &gt; LOOPER: five tracks, the 16 knobs on top, settings on the right.")
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
h2("The BeatStep's pads on the LOOPER")
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

# ============================================================================ 22 pad actions
chapter("Pad actions", "With the BeatStep Pro's Control Mode pads on MIDI channel 16 (see Setting up the BeatStep Pro), each pad runs a "
        "PotentialBox action. Notes on channel 16 never play the synths.")
rows = []
for i, (aid, name) in enumerate(ACTIONS):
    rows.append((f'<span class="kn">{i + 1}</span>', str(36 + i) if aid in PAD_ACTIONS else "not set", b(name)))
table(["Pad", "Note", "Action"], rows, "knobs short")
h2("Changing them")
img("actions", "SETUP &gt; PAD ACTIONS.")
steps(["Open SETUP and tap <b>PAD ACTIONS</b>.", "Tap the action you want to change. It lights up.",
       "Press the pad or step button on the BeatStep Pro you want to use for it. Notes and CCs both work, on any channel."])
p("Each card flashes when its action runs. RESET TO CHANNEL 16 DEFAULTS puts the table above back. Actions 17 and "
  "up have no pad out of the box. On PROJECTS, LIVE FX, BEATS, STEMS and the LOOPER the pads play those screens' own "
  "pads instead (listed in their chapters). The old Drums 1-8 and Drums 9-16 tab actions open SOUNDS &gt; DRUMS on "
  "those pads' pages.")
end()

# ============================================================================ 23 files
chapter("Your files", "PotentialBox saves everything by itself, a moment after each change and when you close it.")
table(["What", "Where"], [
    (b("The app"), "<code>%LOCALAPPDATA%\\PotentialBox</code>"),
    (b("Settings (knobs, setup, pad actions, kit, beat, song)"), "<code>%APPDATA%\\PotentialBox\\state.json</code>"),
    (b("My Sounds"), "<code>%APPDATA%\\PotentialBox\\my-sounds.json</code>"),
    (b("My Kits"), "<code>%APPDATA%\\PotentialBox\\my-kits.json</code>"),
    (b("The list of your samples (rebuilt by itself)"), "<code>%APPDATA%\\PotentialBox\\sample-index.json</code>"),
    (b("Your MPC's one-shots"), "<code>Music\\MPC Drum One Shots</code>"),
    (b("My Setups"), "<code>%APPDATA%\\PotentialBox\\my-setups.json</code>"),
    (b("Resampled sounds"), "<code>%APPDATA%\\PotentialBox\\Resampled</code>"),
    (b("Your own wavetables"), "<code>%APPDATA%\\PotentialBox\\Wavetables</code>"),
    (b("Recordings and MIDI files"), "<code>Music\\PotentialBox Recordings</code>"),
    (b("Bounced stems and My Loops"), "<code>Music\\PotentialBox Loops</code> (one folder per bounce or loop set)"),
    (b("Log (what went wrong, if anything)"), "<code>%APPDATA%\\PotentialBox\\log.txt</code>")])
p("To open one of these folders, paste the path (for example <code>%APPDATA%\\PotentialBox</code>) into the File "
  "Explorer address bar and press Enter.")
note("Back up your sounds, kits and setups by copying the three <code>my-…json</code> files somewhere safe. My Kits point "
     "to your sample files, so keep your sample folders where they are.")
end()

# ============================================================================ 24 troubleshooting
chapter("Troubleshooting")
for q, a in [
    ("The display says AUDIO PROBLEM", "Open SETUP and tap another output. If your interface's ASIO driver won't open, close "
     "any DAW, FL Studio or Voicemeeter that might be using it, then tap it again. WASAPI always works as a fallback."),
    ("I hear crackles", "Look at LOAD and DROPOUTS on SETUP. If DROPOUTS climbs, tap the next BUFFER size up "
     "(256 or 512). If LOAD is high, ease off chords and supersaw on both synths, or close heavy apps."),
    ("MIDI says NO BEATSTEP FOUND", "Check the USB cable, wait a few seconds after plugging in, then tap RESCAN MIDI in "
     "SETUP. A DAW can hold the BeatStep's MIDI port open; close it and rescan."),
    ("The sequencers play but the knobs do nothing", "Press CONTROL MODE on the BeatStep Pro. Still nothing? "
     "SETUP &gt; LEARN KNOBS."),
    ("The pads don't run actions", "Set the BeatStep's Control Mode pads to MIDI channel 16 in MIDI Control Center, or "
     "teach PotentialBox your pads in SETUP &gt; PAD ACTIONS."),
    ("Step locks, step LFOs, the arp or “1st of 4” don't follow the BeatStep", "They follow the BeatStep's MIDI clock. "
     "Press Play on the BeatStep and check the BPM at the top shows its tempo. Stop and Play again to reset the step count."),
    ("With CLOCK OUT on, the BeatStep doesn't start", "Its SYNC must be on USB. In SETUP, make sure the BeatStep's MIDI "
     "port is on."),
    ("SEND TO BEATSTEP says no MIDI out was found", "Check the BeatStep is plugged in and switched on, then try again. "
     "The beat goes out on the drum channel set in SETUP (10 out of the box)."),
    ("The scene morph does nothing", "Save two different scenes and check FROM and TO point at them. The line under the "
     "morph bar says how many settings move."),
    ("The LOOPER says INPUT OFF, or lists no inputs", "Inputs come from the output chosen in SETUP. Pick your "
     "interface's ASIO driver there (WASAPI outputs have no inputs), then choose the input on the LOOPER."),
    ("A synth or drum sounds wrong", "A macro may be turned up (tap ZERO ALL MACROS), a track may be muted or another "
     "soloed (SOUNDS &gt; MIX &gt; MUTE/SOLO), or the master effects may be on (SOUNDS &gt; FX &gt; MASTER). For a fresh start, RESET ALL TO INIT."),
    ("A machine kit has odd sounds on some pads", "The sorter goes by file names. Use EDIT PAD to swap any pad, then save "
     "it in My Kits."),
    ("SEND TO MPC says the MPC didn't answer, or wants a password", "PotentialBox uses MPC TOOLS' SSH "
     "login: open MPC TOOLS once and check it can reach the MPC. The MPC and the PC must be on the same network."),
    ("SEND TO MPC says there's no SD card", "Put an SD card or USB drive in the MPC. Bounces go to a PotentialBox Loops "
     "folder on it."),
    ("A bounce is shorter or longer than the bars", "It's timed from the tempo. If the BeatStep's tempo changes during "
     "a bounce, bounce again once it's steady."),
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
