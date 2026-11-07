# Changelog

## 1.8.1
- Beats are now **2 bars** by default (LENGTH: 1, 2 or 4 bars), and the last bar **ends with a change that leads back to the start**: snare roll or pickup, tom run, open hat, kick run, kick skip or a drop-out with a crash back in. NEW ENDING picks another.
- **SIMPLER / BUSIER** now change the beat itself, one layer per tap (16th hats, ghost snares, extra kick, shaker, congas / no percussion, no maybe-hits, no ghosts, 8th hats), shown in the grid and sent to the BeatStep. The knob is now called Random hits.
- **CLOCK OUT TO BEATSTEP**: PotentialBox sends MIDI clock, Start and Stop at the beat's tempo (set the BeatStep's SYNC to USB). PLAY starts the BeatStep and the beat together; SEND TO BEATSTEP counts down 4 seconds so you can press REC, then starts everything itself.
- Clock ticks are time-stamped, so beat steps land evenly instead of on audio-block boundaries.
- Fixed: the "tempo comes from the BeatStep" check never noticed the BeatStep's clock.

## 1.8.0
- **Beats tab**: genre beat generator with 24 genres, each with its own tempo, swing, length (16 or 32 steps), fill style and matching kit.
  - NEW BEAT for another take, MUTATE one part, SIMPLER / BUSIER, HOLD FOR FILL, mutes for kick, snares, hats and percussion; tap the grid to add or remove hits.
  - Knobs: busy, variation, swing (genre or your own), humanize, drum bus and pad levels.
  - Plays locked to the BeatStep's clock (sample-accurate, with swing), or on its own tempo when the BeatStep is stopped. Hits respect the drum pads' chance and conditions, and trigger side-chain ducking.
  - **Send to BeatStep**: press REC + PLAY on the BeatStep and the beat is sent once over MIDI (drum channel, notes 36-51) from step 1, so the BeatStep's drum sequencer records it and keeps playing it. Echoed notes are ignored while sending.
  - While the Beats tab is open, BeatStep pads 1-16 run it (play, new beat, genre, fill, mutate, simpler/busier, mutes, tempo, send, back).
- Drum hits can now start at an exact sample inside an audio block.
- New pad action: Beats Tab. The current beat is saved with your settings and in My Setups.

## 1.7.0
- **Loop tab**: a 5-track stereo looper inspired by the BOSS RC-505.
  - Records the audio interface's inputs (pick mono or stereo inputs; needs the interface's ASIO driver), PotentialBox's own mix, or both, per track. Round-trip latency is compensated.
  - REC → PLAY → OVERDUB → PLAY on one pad per track; STOP pad per track (hold to clear); undo/redo of the last overdub; all stop/play; record on next empty track; clear all.
  - Synced to the BeatStep: loop lengths snap to whole bars, loops follow Play/Stop and restart in time with bar 1, with gentle varispeed to stay locked to its clock. Stopped: the first loop sets the length for the rest.
  - Start when you tap (end snaps) or on the bar (late presses still count); optional fixed length of 1, 2, 4 or 8 bars.
  - Per-track FX (low-pass, high-pass, lo-fi, echo, tremolo), reverse, half/double speed; overdub keep (feedback), loop bus filter and ducking, input level and monitoring.
  - My Loops: 8 loop sets saved as WAV files in Music > PotentialBox Loops.
  - While the Loop tab is open, BeatStep pads 1-16 play the looper (each column = one track).
- Recording on the Live tab also saves a Looper stem.
- New pad action: Loop Tab.

## 1.6.0
- **Live tab**: hold-to-play punch-in effects (Repeat 1/8, Repeat 1/16, Roll 1/32, Tape stop, Reverse, Filter sweep, Gate 1/16, Echo throw), Scene A/B snapshots with a morph bar (BeatStep knob 1) and HOLD FOR SCENE B, HOLD FOR FILL, Record, Resample and My Setups. While the Live tab is open, BeatStep pads 1-16 play the Live pads.
- **Arpeggiator** on both synths (new ARP+ page): Up, Down, Up-down, Random, As played; 1/4 to 1/32 synced; 1-4 octaves; gate, swing, hold, chance, accents. Arpeggiates the chord from chord mode.
- **Step locks** on every knob page: tap STEP LOCKS, pick one of 16 steps, turn knobs. Follows the BeatStep's clock.
- **Drums**: new MIX page (level and pan per pad) and GROOVE page (chance and play conditions per pad: Fill only, Not in fill, 1st/2nd of 2, 1st-4th of 4, 1st/8th of 8).
- **Mix**: side-chain duck for each synth and the FX returns (from any pad or every beat), glue compressor, stereo width; new EQ page with 3-band EQ on Synth 1, Synth 2, drums and master. Drum levels moved to the Drums tabs.
- **Record to WAV** (24-bit): master plus Drums, Synth 1, Synth 2 and FX stems, in Music > PotentialBox Recordings.
- **Resample to a pad**, synced to the bar while the BeatStep plays.
- **My Setups**: 8 slots for complete setups.
- Pad actions: 4 new ones (Live tab, FX tab, Record on/off, Fill hold) with no default pad.
- MIDI clock is followed from one BeatStep port only, so ticks aren't counted twice.

## 1.5.1
- One-tap **INIT** buttons on the synth pages: INIT MODULATION (LFOs, mod envelope, all 8 mod slots incl. routing), INIT OSC+ PAGE, and INIT SYNTH 1 / 2 on the Main page (the whole synth). Each one can be undone with UNDO INIT for a few seconds.

## 1.5.0
- Synth 1 and Synth 2 now have three pages each: **Main**, **Osc+** and **Mod**. Tap the tab again (or press its pad action) to flip pages.
- **Modulation**: 2 LFOs per synth (Sine, Triangle, Saw up/down, Square, Random, Smooth random; free or synced from 4 bars to 1/32 with triplets), a mod envelope and **8 mod slots**. Tap a slot's name to route any source (LFO 1/2, mod env, amp env, velocity, note, random) to any target.
- **Filter types**: LP 24, LP 12, HP 12, band-pass, notch, plus key tracking and velocity-to-volume.
- **Oscillator tricks**: Synth 1 osc 2 tuning, FM, ring mod, hard sync; noise, sub (Synth 2), pitch envelope, analog drift, pan and glide mode on both.
- **Chord mode** with 13 chords and Close/Open/Wide voicings.
- **24 new wavetables** from the AKWF collection (CC0), 30 in total.
- 8 new presets: Sync Lead, FM Bass, Wobble Bass, Minor 7 Stab, Chord Pad, Chip Lead, Voice Choir, Granular Drone.
- Synth 1 is now stereo. Saved sounds from earlier versions load unchanged.
- Manual: new chapter "Modulation and chords" and the new knob pages.

## 1.4.0
- **Macros tab**: 16 performance macros (S1 Sweep, S2 Sweep, Acid, Wobble, Bright, Pluck, Glide, Wide, Dub Throw, Space, DJ Filter, Build-Up, Lo-Fi, Drum Smash, Tighten, Glue). Macros work on top of your settings, so zero always returns your sound exactly.
- New effects: reverb with per-instrument sends, DJ filter, lo-fi crusher.
- Mix & FX split into **Mix** and **FX** tabs.
- Pad action 15 now opens the Macros tab.
- Manual (PDF) included, with a Start menu shortcut.

## 1.3.0
- **Pad editor**: put any one-shot from your collection on any pad (filtered by type, random pick, from file), and **My Kits** save slots.
- Silence at the start of drum sounds is trimmed when they load.
- **Pad actions** on MIDI channel 16 (random sounds, tabs, kits, all notes off), with learn.
- Labelled knob groups, tidier drum panel.

## 1.2.x
- **Drum machine library** browser (brand > machine > kit) with automatic pad sorting by file name.
- Safer audio start-up, hardware ASIO driver preferred, busy-driver fallback to Windows audio.
- Init sound and Reset All to Init.

## 1.1.0
- My Sounds save slots for both synths.
- 9 synthesized drum kits and the Kit menu.

## 1.0.0
- First version: two synths and a drum sampler pre-mapped to the BeatStep Pro, ASIO and WASAPI output.
