POTENTIALBOX 2.1.1  -  a BeatStep Pro groovebox for jamming, on Windows
=====================================================================

INSTALL: double-click "Install PotentialBox.bat".
Updating from 1.x or 2.0? Same thing: your settings, saved sounds, kits, setups and loops are kept.
The full manual is PotentialBox-Manual.pdf (also in the Start menu after installing).

WHAT PLAYS WHAT (factory BeatStep Pro settings)
  Seq 1   (MIDI ch 1)   -> SYNTH 1  analog-style synth (basses, acid, leads, supersaws, chords)
  Seq 2   (MIDI ch 2)   -> SYNTH 2  wavetable synth (leads, keys, pads, plucks, bells)
  Drum    (MIDI ch 10)  -> DRUMS    16 pads (notes 36-51)
  16 knobs (CNTRL)      -> the 16 knobs of the screen you have open
  16 pads (CNTRL, ch16) -> pad actions, or the open screen's own pads
  Tempo                 -> from the BeatStep's clock (or CLOCK OUT: PotentialBox sets it)

THE FIVE SECTIONS (big keys along the bottom; sub-tabs top left)
  JAM      PROJECTS  tap 1-16 (or a pad, or say "project seven") for that genre set's bass,
                     lead, kit, effects and tempo. MUTATE: new sounds on the next bar.
           LIVE FX   hold-to-play effects, 8 scenes with morph, fill, record, and
                     GRAB LAST 4 BARS: saves what you just played as stems.
                     BOUNCE NEXT 4 BARS + SEND: bounces, then sends to the MPC.
           KNOBS     what the BeatStep knobs do on PROJECTS.   MACROS  16 performance knobs.
  SOUNDS   SYNTH 1 / SYNTH 2  a sound browser: pick a type (BASS, LEAD, KEYS, PAD, PLUCK,
                     STAB, FX, MY SOUNDS), tap a sound. EDIT SOUND opens every setting;
                     < SOUNDS (or tapping the sub-tab again) comes back.
           DRUMS     18 kits, KIT MAKER, the drum BUS (punch, room, width, tone, crush),
                     and pad tune / mix / groove / choke pages.
           MIX, FX   levels, ducking, EQ, mute/solo; delay, reverb and the master chain.
  BEATS    BEATS     beat generator in 24 genres, BACK to the last beat, SEND TO BEATSTEP.
           SONG START  one tap: a beat, a bass line and chords in one key. KEEP a part.
           ARRANGE     chain beats.
  CAPTURE  STEMS     BOUNCE NEXT or GRAB LAST 1/2/4/8 bars: mix + drums + synth 1 + synth 2 + FX + looper
                     as bar-exact WAV loops in Music > PotentialBox Loops. SEND TO MPC copies
                     them to the MPC's SD card (PotentialBox Loops folder) using MPC TOOLS'
                     SSH login. AUTO-SEND does it after every bounce.
                     YOUR BOUNCES: > to listen first, SEND to put that one on the MPC.
           LOOPER    5-track looper (mic, instruments and PotentialBox itself).
  SETUP    audio output (ASIO = lowest lag), MIDI, LEARN KNOBS, PAD ACTIONS, MY SETUPS.
  Ctrl+1 ... Ctrl+5 jump to the five sections.
  Tap the tempo at the top of any screen for TAP TEMPO and one-tap tempos.

BEATSTEP PRO SETUP
  1. Plug the BeatStep Pro into the PC with USB.
  2. Press PLAY on the BeatStep Pro: the sequencers play PotentialBox.
  3. Press CNTRL (Control mode) to make the 16 knobs send to PotentialBox.
  4. A knob doing nothing? SETUP > LEARN KNOBS and turn knobs 1 to 16 in order.
  5. For pad actions, put the BeatStep's Control Mode pads on MIDI channel 16
     (Arturia MIDI Control Center).

LOW LAG (ASIO)
  SETUP lists your audio outputs, best first:
    ASIO ...                  lowest lag. Audio interfaces come with an ASIO driver.
    WASAPI EXCLUSIVE ...      very low lag with no driver; other apps go quiet while it runs.
    WASAPI ...                works everywhere, a bit more lag.
  Smaller BUFFER = less lag (try 128 or 256; go up if you hear crackles).

NEW IN 2.1.1
  - A smoother, more musical Drum drive: warm crunch all the way up, no fizz, no jump in level.

NEW IN 2.1
  - Every drum sound rebuilt: proper 808/909/acoustic kicks, tuned snares with real
    snare-wire noise, band-limited metal hats, ringing rides and crashes, modal toms.
  - Kits are balanced (hats under the kick and snare) and spread in stereo like a real kit.
  - 9 new genre kits (18 in all), and a drum BUS page: punch, room, width, tone, crush.
  - Every BEATS genre and every project loads its own kit and drum bus.

NEW IN 2.0
  - Five sections (JAM, SOUNDS, BEATS, CAPTURE, SETUP) instead of 14 tabs, with sub-tabs
    and a display at the top that says what's loaded.
  - A new PROJECTS screen to jam from, laid out like the BeatStep's pads.
  - A sound browser for each synth, and 77 new presets made for the current engine
    (unison, supersaw, clean subs, drive, distortion, synth FX, comb and formant
    filters, FM, sync, wavetables and warp). All level-matched.
  - CAPTURE > STEMS: bar-exact stem bounces, and SEND TO MPC.
  - One look: Hi-Fi, refreshed. SOUNDS > DRUMS is one tab for all 16 pads.
  - Your 1.x saved sounds, kits and setups all still load.
  See CHANGELOG.md on GitHub for everything that changed.

WHERE THINGS ARE SAVED
  Settings, My Sounds, My Kits, My Setups:  %APPDATA%\PotentialBox
  Bounced stems and My Loops:              Music\PotentialBox Loops
  Recordings and MIDI files:               Music\PotentialBox Recordings
  If something goes wrong, the last lines of %APPDATA%\PotentialBox\log.txt say why.
