# Changelog

## 1.11.0
- **Vintage look** rebuilt to match the BeatStep Pro: charcoal faceplate, walnut cabinet round the window, cream
  keys and pads, amber LEDs, orange accents and a green VFD-style display in the readouts.
- **Hi-fi skin drawing** (new `skins.py`): encoders, keys and displays are rendered with Pillow - domed knobs with a
  cast shadow and specular highlight, moulded keys with gradient, lit top edge and drop shadow, glass display windows -
  and cached, so a page redraws at the same speed. Needs Pillow (added to `requirements.txt`); without it the app falls
  back to its flat vector drawing.
- Small hardware touches on the Vintage look: serif logo, cross-head screws on the drum pads and a brighter core in the
  value arcs.
- The Kit Maker and Sample folders screens use the hi-fi keys too.

## 1.10.2
- Fixed: 1.10.1 showed a blank window icon and Python's icon on the taskbar. The window now uses a small plain .ico of the PB logo.

## 1.10.1
- The window and taskbar show the PotentialBox (PB) icon instead of Python's feather, and PotentialBox gets its own taskbar button.
- The desktop shortcut uses the new PB icon.

## 1.10.0
More drums: the **Kit Maker** builds kits from all your own one-shots, PotentialKits-style.

**Kit Maker** (KIT MAKER on the drum panel, or in the Kit menu)
- **NEW KIT** builds a 16-pad kit in one tap from every one-shot you have: the Drum Machine Collection plus any sample folders. It keeps PotentialBox's pad layout (kick 1, snare 3, hats 5/6, toms 7-9 ...), so BeatStep patterns and the Beats tab carry on working.
- **12 styles**: Classic, Boom Bap, Lo-Fi, Trap, House, Techno, Jungle, Electro, Dusty Jazz, Percussion, Dub and Weird. A style sets what each pad draws from, its pitch and length, and the machines or packs it leans towards (808s for Trap, SP-1200 and MPC for Boom Bap, 909 and 707 for House ...).
- **LOCK** any pad to keep it. **ROLL MILD** swaps up to 4 pads, **ROLL MEDIUM** makes a new kit with a little pitch and length, **ROLL WILD** lets any pad be any type. **PREVIOUS KIT** goes back (12 kits).
- Tap a pad, then one of **18 types** (kick, 808, snare, clap, rim, closed / open hat, tom, conga, shaker, cowbell, clave, perc, cymbal, FX, vox, stab, other) for a new sound of that type. **PITCH**, **LENGTH** and **LEVEL** step with one tap each.
- New kits have their **levels evened out** (hats and cymbals sit a little under kicks and snares); **MATCH LEVELS** does the whole kit again.
- **DRAW FROM**: everything, only drum machines or only your folders. **ONE SOURCE** builds the whole kit from one machine or pack where it can.
- The **Random Drum Kit** pad action (and Live pad 14) makes a Kit Maker kit once you have samples.

**Sample folders**
- **SAMPLE FOLDERS** (in the Kit Maker): add any folders of one-shots. Sounds are sorted by the words in their folder and file names, the way MPC TOOLS' drumsort does; loops and long files are left out. WAV and AIFF are read. Only new or changed files are read again, so it starts quickly.
- **GET MPC ONE-SHOTS** copies the DRUM ONE SHOTS folder that MPC TOOLS makes on the MPC's SD card (Kicks, Snares, Claps, Hats, Cymbals, Toms, Percs) to *Music\MPC Drum One Shots*, over SSH with MPC TOOLS' key login and its saved MPC address. Tap it again later and only new sounds are copied.

**Everywhere else**
- The **pad editor** lists sounds from your sample folders too, with new 808 / Bass and FX / Vox groups, and THIS SOURCE (the machine or pack the pad's sound comes from).
- **My Kits** now keep each pad's pitch, length, level, pan and choke.
- Beats tab: **GENRE KIT** has three settings: OFF, BUILT-IN, and **SAMPLES**, which makes each genre's kit in the Kit Maker (Trap gets an 808 on pad 2, Boom Bap an SP-1200-leaning kit, Afrobeats a percussion kit ...).
- The drum panel's keys are now < KITS > KIT MAKER EDIT.
- Drum samples you've used are kept in memory, so rolling kits is quick.

## 1.9.2
Fixes for the crackling audio and the screens added in 1.9.1.

**Sound**
- **Crackles fixed.** The new Chorus, Flanger and Phaser lost their place at the edge of every audio buffer (and with buffers of 512 or more they read audio that hadn't been written yet), and the Compressor restarted every buffer. All four are rebuilt so they run smoothly at any buffer size.
- **Limiter** is a real look-ahead limiter now (it used to hard-clip, which crackles). More = louder, never over the ceiling.
- **Distortion** fades in from zero instead of jumping in level the moment you touch it.
- The audio thread gets in on time while the screen redraws (it could wait up to 5 ms, as long as a whole 256 buffer).
- **Comb filter** on Synth 2 silenced everything (it crashed on every buffer); fixed on both synths, and it no longer clicks when the note changes.
- **Formant filter** is three proper vowel peaks; the cutoff glides smoothly A > E > I > O > U.
- **Supersaw** is a real supersaw now: 7 detuned saws (it used to be 5 copies of one saw at the same pitch).
- **Envelopes**: slides and ties glide again once a note reaches its sustain (they had started retriggering), and Decay 2 / Sustain 2 never jump.
- **Step LFO** steps glide over 3 ms (no clicks) and step along with the LFO's speed when the BeatStep is stopped.
- Muted tracks keep running in time, so unmuting doesn't bring back stuck notes.
- Setup tab shows the sound engine's **LOAD** and how many **DROPOUTS** the sound card has had. Crackles? Go one buffer size up.

**Screens**
- **Toasts, My Setups, My Loops and the loop Input picker were invisible** (their drawing code had ended up inside the MIDI export). They're back.
- **Synth 1 Main** stopped drawing half way (17 knobs on a 16-knob page) and **Synth 2 Env** didn't draw at all. Supersaw moved to Osc+; every page has exactly 16 different knobs (Mod 2, Env and Mute/Solo had the same knob two or three times).
- **Scenes**: the morph never worked (it read the slot numbers wrongly), HOLD FOR SCENE always said "save A and B first" and the TO key crashed. All fixed; scenes saved in 1.9.0 come back as scenes 1 and 2. New layout for the Scenes panel.
- **INIT** on the Mod 2, Env and LFO step pages reset the whole synth. Now each resets only its own page.
- **Undo** (Ctrl+Z) undoes a whole knob turn, sound load or scene load, not one tiny step of it.
- **Mute / Solo** (and other on/off settings) are one-tap keys instead of knobs.
- **Arrangement** actually plays now: PLAY SONG plays the beats in order, each for its own length, then round again. Tap a beat to jump to it (or to hear it on the Beats tab), remove the last one, clear, and SAVE SONG AS MIDI FILE. MIDI files use the BeatStep's notes (pad 1 = note 36) and go to Music > PotentialBox Recordings.
- **Master FX** is now a page of the FX tab (FX > Master), so the tab bar fits.
- Tidier layouts: tab names, the synth page bar (no more INIT key on top of it), the pad editor's buttons, the Setup buffer row (1024 and 2048 were hidden), Beats tab bottom row.
- Knobs show their value as a ring, and the window can be made small again (a big minimum size pushed the tabs off smaller screens).

## 1.9.0
- **Three looks.** PotentialBox has a new default look, **Print Plate** (a warm printed panel), plus **Night Rack** (dark rack unit) and **Colour Block** (flat and bold), all in PotentialBox's own colour, emerald. Tap the **LOOK** key on the Setup tab to step through them. The change shows at once and is remembered.
- The name at the top now reads **PotentialBox**, as it is written everywhere else.
- Sounds, settings and everything saved carry over unchanged.

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
