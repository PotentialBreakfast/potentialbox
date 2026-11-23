# PotentialBox v2.0 roadmap (Milestone B first)

Keeps the **BeatStep Pro as the master sequencer** (MIDI ch 1/2/10/16). Look: Hi-Fi (v2.0 has one look).

## Milestone B — Sound engine (in progress)
- Supersaw oscillator blend (detuned saw stack) on Synth 1
- FM 4-op option (in addition to 2-op)
- Granular/sample oscillator for Synth 2 (load a sample as a wavetable source)
- Comb filter (metallic/resonant) and formant filter (vowel) added to FTYPES
- Multi-stage envelope: attack -> decay1 -> decay2 -> sustain -> release
- Expanded mod matrix: 12 slots (was 8), new sources (step index, Euclidean, random-per-step), new targets (FX params, sample start, pan spread)
- User wavetable import: load a folder of single-cycle WAVs into Synth 2's table list
- LFO as step sequencer (per-step values) in addition to free shapes

## Milestone C — Performance & arrangement
- Scene snapshots (8) with morph
- Mute/solo per track, track levels
- Arrangement view (pattern chain with repeats/mutes)
- MIDI export of patterns

## Milestone D — Drums & sampling
- Per-pad sample layers (velocity/round-robin), choke groups
- Sample editor (trim, normalize, fade, pitch, time-stretch)
- Kit randomiser with constraints
- Resample FX returns to pads

## Milestone E — FX & mix
- Chorus, phaser, flanger, distortion, compressor, per-track EQ
- Master FX chain reordering
- Sidechain source selection + ducking curve
- Limiter + LUFS metering + spectrum

## Milestone F — UI & integration
- Resizable/zoom, full-screen, multi-monitor
- Undo/redo stack
- Keyboard shortcuts for every action
- MIDI learn for non-BeatStep controllers
- Ableton Link
- User skin slot (JSON palette)

## Notes
- Each milestone is delivered as its own commit so it can be tested before the next.
- BeatStep Pro factory mapping stays the default; MIDI learn is additive.