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

The look uses the shared Potential* dark theme (potential-theme.conf).
