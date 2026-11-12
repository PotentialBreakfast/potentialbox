POTENTIALBOX 1.4  -  BeatStep Pro groovebox for Windows
=======================================================

INSTALL: double-click "Install PotentialBox.bat".
The full manual is PotentialBox-Manual.pdf (also in the Start menu after installing).

WHAT PLAYS WHAT (factory BeatStep Pro settings)
  Seq 1   (MIDI ch 1)   -> SYNTH 1  analog-style mono synth (saw/square, sub, resonant filter)
  Seq 2   (MIDI ch 2)   -> SYNTH 2  wavetable mono synth (6 morphing tables, LFO, unison)
  Drum    (MIDI ch 10)  -> DRUMS    16 pads (notes 36-51), 9 machine-style kits or your own WAV folders
  16 knobs              -> the 16 knobs on the page you have open (bottom tabs)
  Tied / slid steps     -> glide (set with the "Glide (slides)" knob)
  Tempo                 -> read from the BeatStep Pro clock (sets the delay time)

BEATSTEP PRO SETUP
  1. Plug the BeatStep Pro into the PC with USB.
  2. Press PLAY on the BeatStep Pro: the sequencers play PotentialBox.
  3. Press CNTRL (Control mode) to make the 16 knobs send to PotentialBox.
     The sequencers keep playing in Control mode.
  4. A knob doing nothing? Go to SETUP > LEARN KNOBS and turn knobs 1 to 16 in order.

LOW LAG (ASIO)
  SETUP lists your audio outputs, best first:
    ASIO ...                  lowest lag. Audio interfaces come with an ASIO driver.
    WASAPI EXCLUSIVE ...      very low lag with no driver; other apps go quiet while it runs.
    WASAPI ...                works everywhere, a bit more lag.
  No audio interface? Install a free ASIO driver such as FlexASIO or ASIO4ALL, then
  pick it in SETUP. Smaller BUFFER = less lag (try 128; go up if you hear crackles).

SAVING YOUR SYNTH SOUNDS
  Tap MY SOUNDS on Synth 1 or Synth 2. 8 slots each.
  SAVE HERE stores the sound you hear now. On a full slot, tap twice to replace it.
  LOAD plays it back. Saved sounds also come up when you tap PREV / NEXT.
  They live in %APPDATA%\PotentialBox\my-sounds.json (copy it to back them up).

DRUM KITS
  Tap KIT MENU (or < > to step through). Kits: Potential, 808 Boom, 909 Punch,
  606 Tight, Trap 808, SP Dust (12-bit), Electro 80s, Minimal Tech, Industrial.
  Same pad layout in every kit: 1 kick, 2 kick 2, 3 snare, 4 clap, 5 closed hat,
  6 open hat, 7-9 toms, 10 rim, 11-13 percussion, 14 cymbal, 15 FX, 16 perc.
  ADD FOLDER: the first 16 WAV files (A-Z order) go on pads 1-16; name them
  01 kick.wav, 02 808.wav ... to choose the order. Folders stay in the menu.
  RESET PAD KNOBS puts every pad's tune / length / level back to normal.

DRUM MACHINE COLLECTION (your sampled hardware)
  KIT MENU > DRUM MACHINES. Pick a brand on the left, then a machine, then a kit.
  RANDOM MACHINE picks any machine and kit for you.
  PotentialBox reads the samples straight from your folder (nothing is copied) and
  sorts them onto the pads by name: kick 1, snare 3, hats 5/6, toms 7-9 and so on.
  Once a machine kit is loaded, < and > step through that machine's kits, then the next machine.
  It looks in Downloads\Drum Machine Collection; CHANGE FOLDER picks another place.

MACROS (performance knobs)
  The MACROS tab: 16 knobs that each move several settings at once. Turning a macro back to
  zero puts everything back exactly where you had it (DJ Filter: back to the centre).
   1 S1 Sweep   2 S2 Sweep   3 Acid        4 Wobble     5 Bright   6 Pluck      7 Glide  8 Wide
   9 Dub Throw 10 Space     11 DJ Filter  12 Build-Up 13 Lo-Fi    14 Drum Smash 15 Tighten 16 Glue
  The last macro you touched is described at the top of the page. ZERO ALL MACROS resets them.
  Knobs pushed by a macro show their value in amber, with a small ring where your setting is.

SYNTH PAGES: MAIN, OSC+, MOD (new in 1.5)
  Synth 1 and Synth 2 each have three pages. Tap the tab again (or its pad action) to flip.
  OSC+: osc 2 tuning, FM, ring mod and hard sync (Synth 1), sub (Synth 2), noise, chord and
  voicing, pan, filter type (LP 24 / LP 12 / HP / band-pass / notch), key tracking,
  velocity, drift, pitch envelope and glide mode.
  MOD: 2 LFOs (shape, speed, tempo sync), a mod envelope and the 8 mod slot amounts.
  Every slot starts at 0. Turn one up to hear it; tap its name to choose another source
  or target. Chords on both synths use more PC: if it crackles, pick BUFFER 256 in SETUP.
  Synth 2 has 30 wavetables, 24 of them from the free AKWF collection (CC0).
  INIT buttons (amber, top of each synth page) start again in one tap:
    MOD page: INIT MODULATION = both LFOs, mod envelope and all 8 slots (routing + amount).
    OSC+ page: INIT OSC+ PAGE.  MAIN page: INIT SYNTH 1 / 2 = the whole synth.
  UNDO INIT shows for a few seconds afterwards if you change your mind.

NEW IN 1.9.0
  THREE LOOKS: Print Plate (new, the default), Night Rack and Colour Block. Setup tab > tap the LOOK key
  to step through them. It changes at once and is remembered.

NEW IN 1.8.1
  Beats are 2 bars (LENGTH: 1/2/4) with an ending that leads back to the start; NEW ENDING.
  SIMPLER / BUSIER now add or take away a layer each tap.
  CLOCK OUT TO BEATSTEP: set the BeatStep's SYNC to USB, then PLAY in PotentialBox starts both
  at the beat's tempo. SEND TO BEATSTEP then counts down: press REC on the BeatStep and wait.

NEW IN 1.8: THE BEATS TAB (genre beat generator)
  Tap a genre (24 of them), PLAY, NEW BEAT for another take. Tap dots to edit.
  SEND TO BEATSTEP: pick an empty drum pattern on the BeatStep, tap SEND TO BEATSTEP, then
  press REC + PLAY on the BeatStep. The beat is sent once from step 1 and the BeatStep keeps it.
  Pads on the Beats tab: 1 play, 2 new beat, 3/4 genre, 5 fill, 6 mutate, 7 simpler, 8 busier,
  9-12 mutes, 13/14 tempo, 15 send to BeatStep, 16 back.

NEW IN 1.7: THE LOOP TAB (5-track looper, like a BOSS RC-505)
  1. Tap INPUT OFF (top right) and pick your mic/instrument input (needs your interface's
     ASIO driver in SETUP). 2. Press pad 1 to record, again to play, again to overdub.
  Pads on the Loop tab: 1-5 rec/play/dub tracks 1-5, 9-13 stop (hold = clear), 6 undo/redo,
  7 all stop/play, 8 record next empty track, 14 reverse, 15 speed, 16 back.
  Loops snap to whole bars while the BeatStep plays and follow its Play/Stop.
  MY LOOPS saves all tracks as WAVs in Music > PotentialBox Loops. Use headphones with a mic.

NEW IN 1.6
  LIVE TAB: hold the 8 effect pads (repeat, roll, tape stop, reverse, filter sweep, gate,
  echo). SAVE A, change things, SAVE B, then morph with the bar or BeatStep knob 1.
  HOLD FOR SCENE B / HOLD FOR FILL. RECORD saves WAVs in Music > PotentialBox Recordings.
  RESAMPLE TO A PAD records a synth or the mix onto a drum pad. MY SETUPS saves everything.
  While the Live tab is open, BeatStep pads 1-16 play: 1-8 effects, 9 fill, 10 scene B,
  11 record, 12-13 random synths, 14 random kit, 15 next kit, 16 back.
  ARP+ PAGE on each synth: arpeggiator. STEP LOCKS button: tap a step, turn knobs.
  DRUMS tabs: MAIN / MIX (level, pan) / GROOVE (chance, plays when).
  MIX tab: ducking, glue, width; EQ page.

FX AND MIX TABS
  FX: delay sends and settings, reverb sends and settings, DJ filter, lo-fi crush.
  MIX: synth and drum levels, drum bus, master drive, DJ filter, levels for pads 1-8.

BUILD YOUR OWN KIT (one sound per pad)
  Tap a drum pad (it plays and gets an amber outline), then EDIT PAD.
  Pick a type on the left (KICK, SNARE, HATS...) and tap any sound from your whole collection
  to put it on that pad. RANDOM picks one for you. ALL / MACHINE limits the list to the
  machine you loaded. FROM FILE... takes any WAV on your PC. Silence at the start of every
  drum sound is trimmed automatically so hits land right on the beat.
  Save the result in KIT MENU > MY KITS (8 slots, tap twice to replace a full slot).

PAD ACTIONS (BeatStep Pro channel 16)
  Set the BeatStep Pro's CNTRL-mode pads to MIDI channel 16 (in Arturia MIDI Control Center).
  Out of the box, pads 1-16 send notes 36-51 and do:
    1 Random Synth 1     2 Random Synth 2     3 Random drum kit    4 Next kit
    5 Previous tab       6 Next tab           7 Perform tab        8 Synth 1 tab
    9 Synth 2 tab       10 Drums 1-8 tab     11 Drums 9-16 tab    12 Mix tab
   13 Synth 1 next sound 14 Synth 2 next sound 15 Macros tab      16 All notes off
  Your pads or step buttons send something else? SETUP > PAD ACTIONS, tap an action, press
  the pad or step you want. Notes and CCs both work.

IF AUDIO WON'T START
  PotentialBox opens audio after the window appears. A driver that freezes is skipped
  next time and SETUP opens so you can pick another (your audio interface's own ASIO
  driver is tried first, before ASIO4ALL / Voicemeeter / FL Studio ASIO).

Everything saves by itself. Running the installer again updates the app and keeps your settings and sounds. Settings live in %APPDATA%\PotentialBox.
Problems? %APPDATA%\PotentialBox\log.txt says what went wrong.
Uninstall: right-click uninstall.ps1 in %LOCALAPPDATA%\PotentialBox > Run with PowerShell.

The three looks (Print Plate, Night Rack, Colour Block) are in potentialbox/app.py (LOOKS).
