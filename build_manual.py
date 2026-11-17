import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
from reportlab.lib import colors

src = os.path.dirname(os.path.abspath(__file__))
imgdir = os.path.join(src, "docs", "images")
out = os.path.join(src, "docs", "PotentialBox-Manual.pdf")

doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=0.8*inch, rightMargin=0.8*inch, topMargin=0.8*inch, bottomMargin=0.8*inch)
styles = getSampleStyleSheet()
title = ParagraphStyle("title", parent=styles["Title"], fontSize=28, spaceAfter=20, textColor=colors.HexColor("#0f6534"))
h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceBefore=16, spaceAfter=8, textColor=colors.HexColor("#0f6534"))
h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14, spaceBefore=12, spaceAfter=6)
body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=11, leading=14, spaceAfter=8)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=18, bulletIndent=8, spaceAfter=4)

story = []
story.append(Paragraph("PotentialBox", title))
story.append(Paragraph("A free groovebox for Windows, played by the Arturia BeatStep Pro", styles["Heading3"]))
story.append(Spacer(1, 12))
story.append(Paragraph("Made by PotentialBreaks. Free and open source (MIT).", body))
story.append(Paragraph("Version 1.9.1", body))
story.append(PageBreak())

def img(name, w=6.0):
    p = os.path.join(imgdir, name)
    if os.path.isfile(p):
        story.append(Image(p, width=w*inch, height=w*0.6*inch))
        story.append(Spacer(1, 8))

story.append(Paragraph("Table of contents", h1))
toc = [
    "1. What PotentialBox is",
    "2. What you need",
    "3. Install",
    "4. Quick start with the BeatStep Pro",
    "5. The pages",
    "6. Synths",
    "7. Drums",
    "8. Beats (beat generator)",
    "9. Live (performance)",
    "10. Loop (looper)",
    "11. Mix, FX and master",
    "12. Macros",
    "13. Scenes (snapshots)",
    "14. Looks (skins)",
    "15. Recording and resampling",
    "16. Setups",
    "17. Troubleshooting",
    "18. Credits and licence",
]
for t in toc:
    story.append(Paragraph(t, body))
story.append(PageBreak())

story.append(Paragraph("1. What PotentialBox is", h1))
story.append(Paragraph("PotentialBox is a free groovebox for Windows. The BeatStep Pro is the sequencer and controller; PotentialBox makes the sound. Sequencer 1 plays Synth 1, Sequencer 2 plays Synth 2, the Drum sequencer plays the 16-pad drum sampler, and the 16 knobs in Control Mode control whichever page is open.", body))
story.append(Paragraph("It is pre-wired for the BeatStep Pro's factory settings, so you can plug in and press play.", body))

story.append(Paragraph("2. What you need", h1))
story.append(Paragraph("Windows 10 or 11 (64-bit), a BeatStep Pro on USB, and an internet connection the first time.", body))

story.append(Paragraph("3. Install", h1))
story.append(Paragraph("1. Download PotentialBox-<version>-windows.zip from Releases.", body))
story.append(Paragraph("2. Right-click, Extract All, open the PotentialBox folder.", body))
story.append(Paragraph("3. Double-click Install PotentialBox.bat.", body))
story.append(Paragraph("The installer sets up a private Python 3.12 and the audio libraries in your user folder, adds Desktop and Start menu shortcuts, and starts PotentialBox.", body))
story.append(Paragraph("Update: run the new release's installer. Your settings, sounds and kits are kept. Uninstall: right-click uninstall.ps1 in %LOCALAPPDATA%\\PotentialBox and choose Run with PowerShell.", body))

story.append(Paragraph("4. Quick start with the BeatStep Pro", h1))
story.append(Paragraph("1. Plug in the BeatStep Pro and start PotentialBox. In SETUP, pick your audio output (ASIO is best).", body))
story.append(Paragraph("2. Press PLAY on the BeatStep Pro. The sequencers play the synths and drums straight away.", body))
story.append(Paragraph("3. Press CONTROL MODE on the BeatStep Pro to make its 16 knobs control the open page.", body))
story.append(Paragraph("4. For pad actions, set the BeatStep's Control Mode pads to MIDI channel 16 in Arturia MIDI Control Center. Pads 1-16 (notes 36-51) do: Random Synth 1, Random Synth 2, Random Drum Kit, Next Kit, Previous Tab, Next Tab, then the Perform, Synth 1, Synth 2, Drums 1-8, Drums 9-16, Mix and Macros tabs, Synth 1 and 2 Next Sound, and All Notes Off. Re-assign any of them in SETUP > PAD ACTIONS.", body))
img("control-map.png")

story.append(Paragraph("5. The pages", h1))
pages = [
    ("Perform", "The 16 most-used knobs for live playing."),
    ("Beats", "The beat generator: 24 genres, mutate, busier/simpler, fills, tap-to-edit grid, Send to BeatStep, length, tempo."),
    ("Live", "8 hold-to-play punch-in effects, Scene A/B with morph, fill, and the BeatStep pads switch to these while the tab is open."),
    ("Loop", "5-track looper: record inputs and PotentialBox itself, overdub, undo/redo, per-track FX, reverse, half/double speed."),
    ("Macros", "16 performance macros. Turn one back to zero and your sound is exactly as it was."),
    ("Synth 1 / Synth 1 Osc+ / Mod / Arp+ / Env / LFO steps", "Analog-style synth: oscillators, filter, envelopes, modulation, arpeggiator, multi-stage envelope, LFO step sequencer."),
    ("Synth 2 ...", "Wavetable synth: 30 morphing tables, filter, envelopes, modulation, arpeggiator."),
    ("Drums 1-8 / 9-16 (Main, Mix, Groove)", "16 pads: tune, decay, level, pan, chance, play conditions."),
    ("Mix", "Volumes, master, side-chain ducking, glue compressor, stereo width, EQ, mute/solo."),
    ("Mix EQ", "3-band EQ per synth, drums and master."),
    ("FX", "Delay, reverb, DJ filter, lo-fi crush."),
    ("Setup", "Audio output, look, kits, pad actions, folders, resample."),
]
for name, desc in pages:
    story.append(Paragraph(f"<b>{name}</b> - {desc}", body))

story.append(Paragraph("6. Synths", h1))
story.append(Paragraph("Each synth has oscillators, a resonant filter (LP 24, LP 12, HP, band-pass, notch, comb, formant), envelopes (attack, decay, sustain, decay 2, sustain 2, release), glide, drive, unison, analog drift, pan, and a pitch envelope. Modulation: 2 tempo-syncable LFOs (7 shapes + Step) and a mod envelope, routed through 12 slots to pitch, filter, wave position, FM, ring mod, pan, volume and more. Chord mode turns every step into a chord (13 types, 3 voicings). Arpeggiator: 5 patterns, tempo-synced rate, octaves, gate, swing, hold, chance, accents.", body))
story.append(Paragraph("Oscillator extras on Synth 1: osc 2 pitch, FM, ring mod, hard sync, noise, sub. Supersaw blends in a detuned saw stack. Synth 2: 30 wavetables (6 built-in + 24 AKWF), wave position, unison, sub, noise. Drop single-cycle WAVs into %APPDATA%\\PotentialBox\\Wavetables to add your own.", body))

story.append(Paragraph("7. Drums", h1))
story.append(Paragraph("16-pad sampler with 9 synthesized kits (808 Boom, 909 Punch, 606 Tight, Trap 808, SP Dust 12-bit, Electro 80s, Minimal Tech, Industrial, Potential), all with the same pad layout. Build your own kits from any one-shots, save 8 of your own, and browse a drum machine library (one folder per machine). Per pad: tune, decay, level, pan, chance, play conditions (fill only, not in fill, 1st of 4, etc.). Drum filter, drive and volume on the mix.", body))

story.append(Paragraph("8. Beats (beat generator)", h1))
story.append(Paragraph("24 genres. One tap for a new take, mutate, busier/simpler, fills, mutes, tap-to-edit grid. Beats are 1, 2 or 4 bars with an ending that leads back to the top. Send to BeatStep records the beat into the BeatStep's drum sequencer over MIDI. Clock out makes the BeatStep follow PotentialBox's tempo. Export MIDI writes the current beat as a MIDI file to %APPDATA%\\PotentialBox\\Recordings.", body))
img("beats.png")

story.append(Paragraph("9. Live (performance)", h1))
story.append(Paragraph("8 hold-to-play punch-in effects (beat repeat, roll, tape stop, reverse, filter sweep, gate, echo throw), Scene A/B with a morph knob and hold-for-B drops, a fill button. The BeatStep's pads switch to these while the tab is open. Scene snapshots: 8 slots, save/load, morph between any two (FROM/TO selectors).", body))
img("live.png")

story.append(Paragraph("10. Loop (looper)", h1))
story.append(Paragraph("5-track looper inspired by the BOSS RC-505: record interface inputs and PotentialBox itself, overdub, undo/redo, per-track FX, reverse, half/double speed, loops snapped to the BeatStep's bars and following its Play/Stop, played from the BeatStep's pads, saved as WAV loop sets.", body))
img("loop.png")

story.append(Paragraph("11. Mix, FX and master", h1))
story.append(Paragraph("Kick-triggered side-chain ducking (or every beat), 3-band EQ on each synth, the drums and the master, a one-knob glue compressor, stereo width. Effects: tempo-synced ping-pong delay, reverb, DJ filter, lo-fi crusher. Mute/solo per track (Track Mute/Solo subpage). Record to WAV: mix plus separate drum, synth and FX stems, 24-bit, into Music > PotentialBox Recordings. Resample to a pad: record half a bar to 4 bars of a synth or the whole mix, in time with the bar, onto a drum pad.", body))

story.append(Paragraph("12. Macros", h1))
story.append(Paragraph("16 performance macros: S1 Sweep, S2 Sweep, Acid, Wobble, Bright, Pluck, Glide, Wide, Dub Throw, Space, DJ Filter, Build-Up, Lo-Fi, Drum Smash, Tighten, Glue. Turn one back to zero and your sound is exactly as it was.", body))
img("macros.png")

story.append(Paragraph("13. Scenes (snapshots)", h1))
story.append(Paragraph("8 scene slots. SAVE writes the current full state to a slot; LOAD replaces the current settings with that slot. FROM/TO select the two endpoints; the morph knob blends only the parameters that differ. HOLD FOR SCENE B (pad 10) holds the morph at 100% while held.", body))

story.append(Paragraph("14. Looks (skins)", h1))
story.append(Paragraph("Four looks: Print Plate (default), Night Rack, Colour Block, Vintage. Tap LOOK on the Setup tab; it changes at once and is remembered. A user skin can be loaded from %APPDATA%\\PotentialBox\\user-look.json.", body))

story.append(Paragraph("15. Setups", h1))
story.append(Paragraph("8 setup slots save everything at once (sounds, kit, mix, effects, locks, scenes). Init sounds and Reset All to start fresh.", body))

story.append(Paragraph("16. Troubleshooting", h1))
story.append(Paragraph("No sound: check audio output in SETUP (ASIO first). BeatStep not playing: check USB and that PLAY is pressed. Pads do nothing: set Control Mode pads to MIDI channel 16. Plugins not loading: switch on External Plugin Support on MPC OS 3.10.1+.", body))

story.append(Paragraph("17. Credits and licence", h1))
story.append(Paragraph("MIT licence. Built on numpy, scipy, sounddevice, mido, python-rtmidi. Not affiliated with or endorsed by Arturia or Steinberg. ASIO is a trademark of Steinberg Media Technologies GmbH. BeatStep Pro is a trademark of Arturia.", body))

doc.build(story)
print("built", out)
