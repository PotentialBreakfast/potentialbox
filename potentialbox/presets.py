"""Synth 1 and Synth 2 sound banks (v2.0).

Every sound here was made for the 1.12+ engine: unison, supersaw, clean subs, filter drive, the five distortions,
the synth's own chorus / ensemble / dimension / phaser / flanger, comb and formant filters, FM, ring mod, sync,
scale chords and the arpeggiator on Synth 1, and the 30 wavetables with the warp modes on Synth 2.

A sound is written the readable way: choices by name (dist="Tube", sfx="Ensemble", table="E-Piano", l1sync="1/8",
uni=4 for four unison voices) and modulation as mod(slot, source, target, amount). bank() turns that into the
engine's values once, when PotentialBox starts.

Synth 1 is played by Seq 1 (usually the bass line), Synth 2 by Seq 2 (leads, keys and chords). Both are mono
synths that can play chords (up to 4 notes) from one key, so pads and stabs use the CHORD setting.
"""
# Imported by engine.py once SPECS, MOD_SOURCES and MOD_DESTS exist (see the bottom of engine's page table).
from potentialbox.engine import SPECS, MOD_SOURCES, MOD_DESTS

PRESET_CATS = ["ALL", "BASS", "LEAD", "KEYS", "PAD", "PLUCK", "STAB", "FX"]


def mod(slot, src, dst, amt):
    """One modulation slot (1-12): mod(9, "LFO 1", "FM", 0.35)."""
    return {f"m{slot}src": src, f"m{slot}dst": dst, f"m{slot}amt": amt}


def S(**kw):
    """A sound: settings plus any mod(...) dicts passed as `mods=[...]`."""
    out = {}
    for m in kw.pop("mods", []):
        out.update(m)
    out.update(kw)
    return out


# ----------------------------------------------------------------------------- Synth 1: analog-style, 2 oscillators
SYNTH1 = [
    # ---- BASS
    ("BASS", "Sub Foundation", S(octave=-1, wave=1, pw=0.5, detune=0, sub=1.0, subtype="-1 oct, clean", cutoff=170,
                                 reso=0.0, envamt=0.04, attack=0.003, decay=0.6, sustain=0.92, release=0.12, glide=0.05,
                                 velamp=0.35)),
    ("BASS", "Acid 303", S(octave=-1, wave=0, detune=0, sub=0.15, subtype="-1 oct, clean", cutoff=240, reso=0.84,
                           envamt=0.72, fdecay=0.16, attack=0.001, decay=0.3, sustain=0.85, release=0.05, glide=0.07,
                           fdrive=0.35, dist="Tube", distamt=0.3, velamp=0.45,
                           mods=[mod(5, "Velocity", "Cutoff", 0.3)])),
    ("BASS", "Reese Rumble", S(octave=-1, wave=0, detune=14, uni=4, unidet=0.36, uniwid=0.45, sub=0.75,
                               subtype="-1 oct, clean", cutoff=650, reso=0.2, envamt=0.08, attack=0.006, decay=1.0,
                               sustain=1.0, release=0.16, fdrive=0.3, sfx="Phaser", sfxamt=0.4, l1rate=0.25,
                               mods=[mod(2, "LFO 1", "Cutoff", 0.14)])),
    ("BASS", "Moog Punch", S(octave=-1, wave=0.15, detune=7, sub=0.5, subtype="-1 oct, filtered", cutoff=360,
                             reso=0.36, envamt=0.46, fdecay=0.22, attack=0.002, decay=0.35, sustain=0.6,
                             release=0.08, fdrive=0.45, drive=0.2, glide=0.05)),
    ("BASS", "FM Growl", S(octave=-1, osc2=12, fm=0.5, detune=0, uni=2, unidet=0.1, uniwid=0.3, ftype="LP 12",
                           cutoff=1300, reso=0.3, envamt=0.2, fdecay=0.3, attack=0.002, decay=0.6, sustain=0.9,
                           release=0.1, sub=0.65, subtype="-1 oct, clean", dist="Fold", distamt=0.35,
                           l1sync="1/8", mods=[mod(9, "LFO 1", "FM", 0.35)])),
    ("BASS", "Wobble 1/8", S(octave=-1, wave=0.6, uni=3, unidet=0.2, uniwid=0.3, ftype="LP 12", cutoff=220,
                             reso=0.55, envamt=0.05, attack=0.002, decay=0.5, sustain=0.95, release=0.1,
                             sub=0.8, subtype="-1 oct, clean", fdrive=0.5, dist="Fold", distamt=0.3,
                             l1shape="Sine", l1sync="1/8", mods=[mod(2, "LFO 1", "Cutoff", 0.55)])),
    ("BASS", "808 Glide", S(octave=-1, wave=0, cutoff=140, reso=0.0, envamt=0.05, attack=0.001, decay=1.3,
                            sustain=0.0, release=0.35, sub=1.0, subtype="Root, clean", penv=7, pdec=0.05,
                            glide=0.12, glmode="Always", drive=0.3, velamp=0.4)),
    ("BASS", "Deep House", S(octave=-1, wave=0.8, pw=0.4, detune=6, sub=0.5, subtype="-1 oct, clean", cutoff=560,
                             reso=0.25, envamt=0.36, fdecay=0.24, attack=0.002, decay=0.32, sustain=0.3,
                             release=0.1, velamp=0.6)),
    ("BASS", "Garage Organ Bass", S(octave=-1, wave=1, pw=0.5, osc2=12, detune=3, sub=0.4,
                                    subtype="-1 oct, clean", cutoff=1050, reso=0.15, envamt=0.3, fdecay=0.12,
                                    attack=0.001, decay=0.22, sustain=0.5, release=0.06, dist="Tape", distamt=0.3)),
    ("BASS", "Neuro Hornet", S(octave=-1, sync="On", osc2=19, wave=0, ftype="Comb", cutoff=300, reso=0.7,
                               envamt=0.2, attack=0.002, decay=0.6, sustain=0.9, release=0.1, uni=2, unidet=0.15,
                               uniwid=0.4, sub=0.7, subtype="-1 oct, clean", dist="Fold", distamt=0.5,
                               l1sync="1/16", mods=[mod(2, "LFO 1", "Cutoff", 0.4), mod(9, "LFO 1", "Osc 2 pitch", 0.2)])),
    ("BASS", "Techno Rumble", S(octave=-1, wave=0, detune=10, cutoff=240, reso=0.4, envamt=0.26, fdecay=0.3,
                                attack=0.001, decay=0.42, sustain=0.0, release=0.3, fdrive=0.6, dist="Tape",
                                distamt=0.5, sub=0.6, subtype="-1 oct, clean")),
    ("BASS", "Electro Square", S(octave=-1, wave=1, pw=0.3, sub=0.5, subtype="-1 oct, clean", cutoff=880,
                                 reso=0.45, envamt=0.5, fdecay=0.14, attack=0.001, decay=0.2, sustain=0.4,
                                 release=0.05, l2rate=0.4, mods=[mod(3, "LFO 2", "Pulse width", 0.3)])),
    ("BASS", "Dub Sub", S(octave=-1, wave=0.3, detune=4, sub=0.9, subtype="-1 oct, clean", cutoff=300, reso=0.1,
                          envamt=0.1, attack=0.01, decay=1.0, sustain=0.9, release=0.3, drift=0.3, dist="Tape",
                          distamt=0.25)),
    # ---- LEAD
    ("LEAD", "Hyper Supersaw", S(octave=0, supersaw=0.85, uni=4, unidet=0.3, uniwid=0.9, cutoff=6500, reso=0.1,
                                 envamt=0.1, attack=0.004, decay=1.0, sustain=0.9, release=0.4, sfx="Ensemble",
                                 sfxamt=0.4)),
    ("LEAD", "Sync Scream", S(octave=0, sync="On", osc2=19, wave=0, cutoff=5000, reso=0.2, envamt=0.2,
                              attack=0.003, decay=0.8, sustain=0.8, release=0.2, uni=2, unidet=0.2, uniwid=0.8,
                              dist="Hard clip", distamt=0.25, glide=0.05, mea=0.001, med=0.6,
                              mods=[mod(7, "Mod env", "Osc 2 pitch", 0.5)])),
    ("LEAD", "80s Mono Lead", S(octave=0, wave=0.5, pw=0.35, detune=12, cutoff=2400, reso=0.3, envamt=0.35,
                                fdecay=0.4, attack=0.005, decay=0.6, sustain=0.7, release=0.25, glide=0.08,
                                l1rate=5.5, sfx="Chorus", sfxamt=0.35, mods=[mod(1, "LFO 1", "Pitch", 0.015)])),
    ("LEAD", "Square Whistle", S(octave=0, wave=1, pw=0.5, osc2=12, detune=4, cutoff=4500, reso=0.1, envamt=0.05,
                                 attack=0.02, decay=0.5, sustain=0.8, release=0.3, glide=0.1, noise=0.05, l1rate=5.0,
                                 mods=[mod(1, "LFO 1", "Pitch", 0.02)])),
    ("LEAD", "Hoover", S(octave=0, wave=0.5, pw=0.2, uni=5, unidet=0.5, uniwid=1.0, cutoff=3000, reso=0.1,
                         envamt=0.2, attack=0.01, decay=0.8, sustain=0.8, release=0.3, penv=-7, pdec=0.15,
                         glide=0.15, glmode="Always", sfx="Chorus", sfxamt=0.6, dist="Tube", distamt=0.2,
                         l2rate=1.5, mods=[mod(3, "LFO 2", "Pulse width", 0.4)])),
    ("LEAD", "Acid Screamer", S(octave=0, wave=0, detune=0, cutoff=600, reso=0.9, envamt=0.6, fdecay=0.2,
                                attack=0.001, decay=0.3, sustain=0.8, release=0.08, glide=0.06, dist="Hard clip",
                                distamt=0.4, fdrive=0.3)),
    ("LEAD", "Formant Talker", S(octave=0, wave=0, ftype="Formant", cutoff=600, reso=0.6, envamt=0.0,
                                 attack=0.01, decay=1.0, sustain=0.9, release=0.2, uni=2, unidet=0.15, uniwid=0.6,
                                 sfx="Chorus", sfxamt=0.3, l1sync="1/4", mods=[mod(2, "LFO 1", "Cutoff", 0.35)])),
    ("LEAD", "Ring Mod Lead", S(octave=0, wave=0.5, osc2=7, ring=0.6, cutoff=7000, reso=0.1, envamt=0.1,
                                attack=0.002, decay=0.8, sustain=0.5, release=0.4, sfx="Flanger", sfxamt=0.25)),
    # ---- KEYS
    ("KEYS", "Juno Keys", S(octave=0, wave=0.6, pw=0.35, cutoff=2000, reso=0.1, envamt=0.3, fdecay=0.5,
                            attack=0.003, decay=1.2, sustain=0.3, release=0.5, sfx="Chorus", sfxamt=0.7, l2rate=0.6,
                            mods=[mod(3, "LFO 2", "Pulse width", 0.2)])),
    ("KEYS", "Clav Funk", S(octave=0, wave=1, pw=0.15, osc2=12, detune=0, ftype="LP 12", cutoff=1800, reso=0.45,
                            envamt=0.5, fdecay=0.08, attack=0.001, decay=0.25, sustain=0.15, release=0.08,
                            keytrk=0.5, velamp=0.8, dist="Tape", distamt=0.2)),
    ("KEYS", "Drawbar Organ", S(octave=0, wave=1, pw=0.5, chord="Fifth + octave", cutoff=1600, reso=0.0,
                                envamt=0.0, attack=0.005, decay=0.1, sustain=1.0, release=0.05, sfx="Dimension",
                                sfxamt=0.6, l2rate=6.0, mods=[mod(8, "LFO 2", "Volume", 0.08)])),
    ("KEYS", "Scale 7th Keys", S(octave=0, wave=0.3, chord="Scale 7th", voicing="Open", cutoff=1700, reso=0.15,
                                 envamt=0.35, fdecay=0.35, attack=0.003, decay=1.0, sustain=0.3, release=0.5,
                                 sfx="Chorus", sfxamt=0.5)),
    # ---- PAD
    ("PAD", "Supersaw Pad", S(octave=0, supersaw=0.7, uni=5, unidet=0.3, uniwid=1.0, cutoff=2200, reso=0.1,
                              envamt=0.15, fdecay=1.5, attack=1.2, decay=2.0, sustain=0.9, release=1.8,
                              sfx="Ensemble", sfxamt=0.6)),
    ("PAD", "Warm Analog Pad", S(octave=0, wave=0.4, detune=15, chord="Fifth", drift=0.5, cutoff=1200, reso=0.2,
                                 envamt=0.1, attack=0.8, decay=2.0, sustain=0.8, release=1.5, sfx="Ensemble",
                                 sfxamt=0.5, l1rate=0.15, mods=[mod(2, "LFO 1", "Cutoff", 0.15)])),
    ("PAD", "PWM Strings", S(octave=0, wave=1, pw=0.3, chord="Octave", cutoff=3000, reso=0.0, envamt=0.0,
                             attack=0.4, decay=1.0, sustain=0.9, release=0.8, sfx="Ensemble", sfxamt=0.8, l2rate=0.7,
                             mods=[mod(3, "LFO 2", "Pulse width", 0.5)])),
    ("PAD", "Minor 9 Dream", S(octave=0, wave=0.2, detune=10, chord="Minor 9", voicing="Wide", cutoff=1500,
                               reso=0.15, envamt=0.12, attack=0.6, decay=2.5, sustain=0.75, release=2.0, drift=0.4,
                               sfx="Dimension", sfxamt=0.6)),
    ("PAD", "Dark Drone", S(octave=-1, wave=0, osc2=7, detune=20, ftype="Comb", cutoff=400, reso=0.3, envamt=0.0,
                            attack=1.5, decay=3.0, sustain=1.0, release=2.5, drift=0.6, sfx="Phaser", sfxamt=0.5,
                            l1rate=0.05, mods=[mod(2, "LFO 1", "Cutoff", 0.3)])),
    # ---- PLUCK
    ("PLUCK", "Supersaw Pluck", S(octave=0, supersaw=0.6, uni=3, unidet=0.25, uniwid=0.9, cutoff=900, reso=0.25,
                                  envamt=0.55, fdecay=0.12, attack=0.001, decay=0.25, sustain=0.0, release=0.25,
                                  sfx="Ensemble", sfxamt=0.4)),
    ("PLUCK", "Arp Bleeps", S(octave=0, wave=1, pw=0.25, chord="Minor", arp="Up", arprate="1/16", arpoct="2 octaves",
                              cutoff=1800, reso=0.5, envamt=0.4, fdecay=0.08, attack=0.001, decay=0.12, sustain=0.0,
                              release=0.08)),
    ("PLUCK", "Comb String", S(octave=0, wave=0, noise=0.6, ftype="Comb", cutoff=261.6, keytrk=1.0, reso=0.92,
                               envamt=0.0, attack=0.001, decay=0.5, sustain=0.0, release=0.35, velamp=0.8)),
    ("PLUCK", "FM Glass Pluck", S(octave=0, osc2=24, fm=0.15, wave=0, cutoff=8000, reso=0.0, envamt=0.0,
                                  attack=0.001, decay=0.5, sustain=0.0, release=0.4, mea=0.001, med=0.25,
                                  sfx="Chorus", sfxamt=0.3, mods=[mod(9, "Mod env", "FM", 0.4)])),
    # ---- STAB
    ("STAB", "Dub Chord Stab", S(octave=0, wave=0.3, chord="Minor 7", voicing="Open", cutoff=1100, reso=0.3,
                                 envamt=0.5, fdecay=0.18, attack=0.001, decay=0.28, sustain=0.0, release=0.3,
                                 sfx="Dimension", sfxamt=0.4, dist="Tape", distamt=0.25)),
    ("STAB", "Rave Organ Stab", S(octave=0, wave=1, pw=0.45, osc2=12, chord="Minor 7", cutoff=2600, reso=0.1,
                                  envamt=0.3, fdecay=0.15, attack=0.001, decay=0.3, sustain=0.1, release=0.2,
                                  dist="Hard clip", distamt=0.2)),
    ("STAB", "Deep House Chord", S(octave=0, wave=0.2, chord="Minor 9", cutoff=1500, reso=0.2, envamt=0.35,
                                   fdecay=0.2, attack=0.002, decay=0.4, sustain=0.1, release=0.35, sfx="Chorus",
                                   sfxamt=0.5)),
    ("STAB", "Power Stab", S(octave=0, wave=0, chord="Fifth + octave", uni=3, unidet=0.25, uniwid=0.8, cutoff=1400,
                             reso=0.2, envamt=0.55, fdecay=0.2, attack=0.005, decay=0.35, sustain=0.2, release=0.2,
                             fdrive=0.4, dist="Tube", distamt=0.3)),
    # ---- FX
    ("FX", "Laser Zap", S(octave=0, wave=1, cutoff=5000, reso=0.5, envamt=0.0, penv=24, pdec=0.15, attack=0.001,
                          decay=0.25, sustain=0.0, release=0.1)),
    ("FX", "Noise Riser", S(octave=0, wave=0, noise=1.0, ftype="Band-pass", cutoff=300, reso=0.5, envamt=0.0,
                            attack=2.0, decay=2.0, sustain=1.0, release=1.0, mea=2.0, med=4.0, sfx="Flanger",
                            sfxamt=0.6, mods=[mod(4, "Mod env", "Cutoff", 0.8)])),
    ("FX", "Sci-Fi Burble", S(octave=0, wave=0.5, osc2=-7, ring=0.8, cutoff=2000, reso=0.6, envamt=0.1,
                              attack=0.001, decay=1.0, sustain=0.7, release=0.3, l1shape="Random", l1sync="1/16",
                              mods=[mod(1, "LFO 1", "Pitch", 0.25)])),
]

# ----------------------------------------------------------------------------- Synth 2: wavetables
SYNTH2 = [
    # ---- LEAD
    ("LEAD", "Wide Saw Lead", S(table="Bright Saw", pos=0.5, posenv=0, lfoamt=0, uni=4, detune=0.35, uniwid=0.8,
                                cutoff=6000, reso=0.15, envamt=0.15, attack=0.003, decay=0.8, sustain=0.8,
                                release=0.25, glide=0.06, sfx="Chorus", sfxamt=0.3)),
    ("LEAD", "Vowel Lead", S(table="Vowel", pos=0.3, posenv=0, lforate=0.4, lfoamt=0.6, uni=2, detune=0.15,
                             cutoff=7000, reso=0.1, envamt=0.05, attack=0.01, decay=1.0, sustain=0.9, release=0.3,
                             l1rate=5.5, mods=[mod(1, "LFO 1", "Pitch", 0.012)])),
    ("LEAD", "Chip Lead", S(table="Chiptune", pos=0.3, posenv=0, lfoamt=0, uni=1, cutoff=12000, reso=0.0,
                            envamt=0.0, attack=0.001, decay=0.3, sustain=0.8, release=0.1, glide=0.04,
                            warp="Quantize", warpamt=0.4, l1rate=6.0, mods=[mod(1, "LFO 1", "Pitch", 0.02)])),
    ("LEAD", "Theremin", S(table="Theremin", pos=0.3, posenv=0, lfoamt=0, uni=1, cutoff=6000, reso=0.0,
                           envamt=0.0, attack=0.08, decay=1.0, sustain=1.0, release=0.5, glide=0.25,
                           glmode="Always", l1rate=5.8, mods=[mod(1, "LFO 1", "Pitch", 0.03)])),
    ("LEAD", "Phase FM Lead", S(table="Analog", pos=0.6, posenv=0, lfoamt=0, warp="Phase FM", warpamt=0.5, uni=2,
                                detune=0.15, cutoff=8000, reso=0.1, envamt=0.1, attack=0.002, decay=0.6,
                                sustain=0.7, release=0.3, dist="Tube", distamt=0.2, mea=0.001, med=0.4,
                                mods=[mod(9, "Mod env", "Warp", 0.4)])),
    ("LEAD", "Sync Sweep Lead", S(table="Bright Saw", pos=0.4, posenv=0, lfoamt=0, warp="Sync", warpamt=0.2,
                                  uni=3, detune=0.25, cutoff=7000, reso=0.15, envamt=0.1, attack=0.003, decay=1.0,
                                  sustain=0.8, release=0.3, dist="Hard clip", distamt=0.2, l2sync="1 bar",
                                  mods=[mod(9, "LFO 2", "Warp", 0.35)])),
    ("LEAD", "Breathy Flute", S(table="Flute", pos=0.4, posenv=0, lfoamt=0, uni=1, noise=0.08, cutoff=5000,
                                reso=0.1, envamt=0.1, attack=0.06, decay=1.0, sustain=0.85, release=0.35,
                                l1rate=5.0, mods=[mod(1, "LFO 1", "Pitch", 0.012)])),
    ("LEAD", "Folded Lead", S(table="Distorted", pos=0.5, posenv=0.2, lfoamt=0, uni=3, detune=0.3, cutoff=5000,
                              reso=0.15, envamt=0.15, attack=0.002, decay=0.7, sustain=0.8, release=0.25,
                              dist="Fold", distamt=0.3, glide=0.05)),
    # ---- KEYS
    ("KEYS", "Tremolo E-Piano", S(table="E-Piano", pos=0.25, posenv=0.25, lfoamt=0, uni=1, cutoff=4500, reso=0.05,
                                  envamt=0.2, attack=0.002, decay=1.6, sustain=0.2, release=0.6, velamp=0.8,
                                  l2rate=4.5, mods=[mod(8, "LFO 2", "Volume", 0.1), mod(6, "LFO 2", "Pan", 0.2)])),
    ("KEYS", "Glass Keys", S(table="FM Bell", pos=0.25, posenv=0.2, lfoamt=0, uni=2, detune=0.1, cutoff=9000,
                             reso=0.05, envamt=0.1, attack=0.002, decay=1.4, sustain=0.25, release=0.9,
                             sfx="Chorus", sfxamt=0.4)),
    ("KEYS", "Leslie Organ", S(table="E-Organ", pos=0.4, posenv=0, lfoamt=0, uni=1, cutoff=7000, reso=0.0,
                               envamt=0.0, attack=0.004, decay=0.2, sustain=1.0, release=0.08, sfx="Dimension",
                               sfxamt=0.6, l2rate=6.5, mods=[mod(8, "LFO 2", "Volume", 0.08)])),
    ("KEYS", "Clavinet", S(table="Clavinet", pos=0.4, posenv=0.3, lfoamt=0, uni=1, cutoff=4000, reso=0.3,
                           envamt=0.3, attack=0.001, decay=0.4, sustain=0.15, release=0.1, velamp=0.9)),
    ("KEYS", "Lo-fi Keys", S(table="E-Piano", pos=0.3, posenv=0.15, lfoamt=0, uni=1, warp="Quantize", warpamt=0.25,
                             dist="Crush", distamt=0.25, drift=0.5, cutoff=3500, reso=0.05, envamt=0.1,
                             attack=0.003, decay=1.3, sustain=0.25, release=0.5, l1rate=0.8,
                             mods=[mod(1, "LFO 1", "Pitch", 0.01)])),
    ("KEYS", "Chord Memory", S(table="Analog", pos=0.55, posenv=0.1, lfoamt=0, chord="Scale 7th", uni=2,
                               detune=0.15, cutoff=3000, reso=0.1, envamt=0.3, attack=0.003, decay=1.0, sustain=0.3,
                               release=0.6, sfx="Chorus", sfxamt=0.5)),
    # ---- PAD
    ("PAD", "Lush Pad", S(table="Analog", pos=0.66, posenv=0, lforate=0.2, lfoamt=0.1, uni=6, detune=0.35,
                          uniwid=1.0, cutoff=3000, reso=0.1, envamt=0.1, attack=1.0, decay=2.0, sustain=0.9,
                          release=2.0, sfx="Ensemble", sfxamt=0.5)),
    ("PAD", "Scale 9th Pad", S(table="Sine Harm", pos=0.4, posenv=0, lforate=0.15, lfoamt=0.3, chord="Scale 9th",
                               uni=2, detune=0.2, cutoff=6000, reso=0.05, envamt=0.05, attack=0.8, decay=2.0,
                               sustain=0.85, release=2.0, sfx="Ensemble", sfxamt=0.5)),
    ("PAD", "Choir Air", S(table="Voice", pos=0.4, posenv=0, lforate=0.2, lfoamt=0.4, noise=0.05, uni=3,
                           detune=0.25, cutoff=6000, reso=0.05, envamt=0.05, attack=1.0, decay=2.0, sustain=0.8,
                           release=2.0, sfx="Dimension", sfxamt=0.5)),
    ("PAD", "Evolving Texture", S(table="Granular", pos=0.2, posenv=0, lforate=0.07, lfoamt=0.7, warp="Mirror",
                                  warpamt=0.4, uni=2, detune=0.2, cutoff=5000, reso=0.1, envamt=0.05, attack=1.5,
                                  decay=3.0, sustain=0.9, release=2.5, sfx="Phaser", sfxamt=0.4, l2rate=0.1,
                                  mods=[mod(9, "LFO 2", "Warp", 0.3)])),
    ("PAD", "String Machine", S(table="String Box", pos=0.4, posenv=0, lfoamt=0, uni=4, detune=0.25, uniwid=0.9,
                                cutoff=4000, reso=0.05, envamt=0.05, attack=0.5, decay=1.0, sustain=0.9,
                                release=1.0, sfx="Ensemble", sfxamt=0.8)),
    ("PAD", "Deep Drone", S(table="Deep Bass", pos=0.5, octave=-1, posenv=0, lforate=0.05, lfoamt=0.5,
                            warp="Squeeze", warpamt=0.3, drift=0.7, uni=2, detune=0.2, cutoff=1200, reso=0.3,
                            envamt=0.05, attack=2.0, decay=3.0, sustain=1.0, release=3.0, sfx="Phaser", sfxamt=0.5)),
    ("PAD", "Glass Pad", S(table="FM Bell", pos=0.4, posenv=0, lforate=0.1, lfoamt=0.3, uni=4, detune=0.2,
                           cutoff=7000, reso=0.05, envamt=0.05, attack=0.8, decay=2.0, sustain=0.8, release=2.0,
                           sfx="Flanger", sfxamt=0.3)),
    # ---- PLUCK
    ("PLUCK", "Harp Pluck", S(table="Pluck", pos=0.3, posenv=0.5, lfoamt=0, uni=2, detune=0.1, cutoff=6000,
                              reso=0.05, envamt=0.3, attack=0.001, decay=0.6, sustain=0.0, release=0.5,
                              sfx="Chorus", sfxamt=0.3)),
    ("PLUCK", "Super Pluck", S(table="Bright Saw", pos=0.5, posenv=0.2, lfoamt=0, uni=5, detune=0.3, uniwid=0.9,
                               cutoff=1500, reso=0.2, envamt=0.55, attack=0.001, decay=0.3, sustain=0.0,
                               release=0.3)),
    ("PLUCK", "Marimba", S(table="Sine Harm", pos=0.1, posenv=0.3, lfoamt=0, uni=1, cutoff=8000, reso=0.0,
                           envamt=0.0, attack=0.001, decay=0.45, sustain=0.0, release=0.3)),
    ("PLUCK", "Chip Arp", S(table="Chiptune", pos=0.3, posenv=0, lfoamt=0, uni=1, chord="Minor", arp="Up",
                            arprate="1/16", arpoct="2 octaves", warp="Quantize", warpamt=0.3, cutoff=12000,
                            reso=0.0, envamt=0.0, attack=0.001, decay=0.12, sustain=0.3, release=0.05)),
    ("PLUCK", "Kalimba", S(table="FM Bell", pos=0.1, posenv=0.4, lfoamt=0, uni=1, cutoff=7000, reso=0.0,
                           envamt=0.0, attack=0.001, decay=0.7, sustain=0.0, release=0.5)),
    # ---- STAB
    ("STAB", "Hardcore Stab", S(table="Bright Saw", pos=0.5, posenv=0, lfoamt=0, chord="Stack", uni=3,
                                detune=0.4, cutoff=5000, reso=0.1, envamt=0.3, attack=0.001, decay=0.3, sustain=0.1,
                                release=0.25, dist="Hard clip", distamt=0.25)),
    ("STAB", "Digital Stab", S(table="Digital", pos=0.6, posenv=-0.3, lfoamt=0, chord="Minor 7", uni=2,
                               detune=0.15, warp="Sync", warpamt=0.2, cutoff=6000, reso=0.1, envamt=0.2,
                               attack=0.001, decay=0.35, sustain=0.0, release=0.3)),
    ("STAB", "Garage Organ Stab", S(table="E-Organ", pos=0.6, posenv=0, lfoamt=0, chord="Minor 9", uni=1,
                                    cutoff=3500, reso=0.1, envamt=0.3, attack=0.001, decay=0.25, sustain=0.1,
                                    release=0.15, sfx="Dimension", sfxamt=0.4)),
    ("STAB", "Vocal Chop", S(table="Vowel", pos=0.2, posenv=0.6, lfoamt=0, uni=2, detune=0.1, cutoff=6000,
                             reso=0.1, envamt=0.1, attack=0.002, decay=0.25, sustain=0.0, release=0.15)),
    # ---- BASS
    ("BASS", "Wavetable Sub Bass", S(table="Deep Bass", pos=0.4, octave=-1, posenv=0, lfoamt=0, sub=0.5, uni=1,
                                     cutoff=900, reso=0.2, envamt=0.3, attack=0.002, decay=0.5, sustain=0.7,
                                     release=0.1, glide=0.05)),
    ("BASS", "E-Bass", S(table="E-Bass", pos=0.3, octave=-1, posenv=0.3, lfoamt=0, uni=1, cutoff=1500, reso=0.1,
                         envamt=0.2, attack=0.002, decay=0.7, sustain=0.3, release=0.1, velamp=0.8)),
    ("BASS", "Vowel Growl Bass", S(table="Vowel", pos=0.3, octave=-1, posenv=0, lfoamt=0, sub=0.6, uni=2,
                                   detune=0.1, uniwid=0.3, cutoff=2500, reso=0.3, envamt=0.1, attack=0.002,
                                   decay=0.6, sustain=0.9, release=0.1, dist="Fold", distamt=0.35, l1sync="1/8",
                                   mods=[mod(9, "LFO 1", "Wave position", 0.5)])),
    # ---- FX
    ("FX", "Birdsong", S(table="Birds", pos=0.5, octave=1, posenv=0, lforate=3.0, lfoamt=0.9, uni=1, cutoff=9000,
                         reso=0.0, envamt=0.0, attack=0.01, decay=0.5, sustain=0.6, release=0.5, l1rate=7.0,
                         mods=[mod(1, "LFO 1", "Pitch", 0.1)])),
    ("FX", "Bitcrush Glitch", S(table="Bitcrushed", pos=0.5, posenv=0, lfoamt=0, uni=1, dist="Crush", distamt=0.5,
                                warp="Quantize", warpamt=0.5, cutoff=9000, reso=0.1, envamt=0.0, attack=0.001,
                                decay=0.6, sustain=0.6, release=0.2, l1shape="Random", l1sync="1/16",
                                mods=[mod(9, "LFO 1", "Wave position", 0.7)])),
    ("FX", "Game Laser", S(table="Video Game", pos=0.5, posenv=0, lfoamt=0, uni=1, penv=24, pdec=0.12,
                           cutoff=9000, reso=0.0, envamt=0.0, attack=0.001, decay=0.2, sustain=0.0, release=0.1)),
]

UNI_CHOICES = ("1", "2", "3", "4", "5", "7")


def _value(pre, key, v):
    """Readable value -> the engine's value (choices by name, mod routes by name, unison by voice count)."""
    full = f"{pre}.{key}"
    if key == "uni" and not isinstance(v, str):
        return UNI_CHOICES.index(str(min(c for c in (1, 2, 3, 4, 5, 7) if c >= v)))
    if key.startswith("m") and key.endswith("src") and isinstance(v, str):
        return MOD_SOURCES.index(v)
    if key.startswith("m") and key.endswith("dst") and isinstance(v, str):
        return MOD_DESTS[pre].index(v)
    if isinstance(v, str):
        return SPECS[full].choices.index(v)
    return v


# Each sound's level (dB), measured so they all play at about the same loudness (see the note at the top).
TRIM = {
    "s1": {
        "Sub Foundation": -3, "Acid 303": -2, "Reese Rumble": 0, "Moog Punch": 0.5, "FM Growl": -0.5,
        "Wobble 1/8": 0, "808 Glide": 3, "Deep House": 5, "Garage Organ Bass": 3, "Neuro Hornet": 0.5,
        "Techno Rumble": 3, "Electro Square": 5, "Dub Sub": 2, "Hyper Supersaw": 2.5, "Sync Scream": -1,
        "80s Mono Lead": 7.5, "Square Whistle": -0.5, "Hoover": 2, "Acid Screamer": -2, "Formant Talker": 7,
        "Ring Mod Lead": 12, "Juno Keys": 6, "Clav Funk": 6, "Drawbar Organ": -3, "Scale 7th Keys": 11,
        "Supersaw Pad": 5, "Warm Analog Pad": 10, "PWM Strings": 0, "Minor 9 Dream": 7, "Dark Drone": 5.5,
        "Supersaw Pluck": 9, "Arp Bleeps": 7, "Comb String": 3, "FM Glass Pluck": 6, "Dub Chord Stab": 9,
        "Rave Organ Stab": 2.5, "Deep House Chord": 10.5, "Power Stab": 2, "Laser Zap": 4.5, "Noise Riser": 12,
        "Sci-Fi Burble": 12,
    },
    "s2": {
        "Wide Saw Lead": 7.5, "Vowel Lead": 5, "Chip Lead": 3.5, "Theremin": -1, "Phase FM Lead": 0.5,
        "Sync Sweep Lead": 2, "Breathy Flute": -0.5, "Folded Lead": -0.5, "Tremolo E-Piano": 4, "Glass Keys": 3.5,
        "Leslie Organ": 2.5, "Clavinet": 9.5, "Lo-fi Keys": 4.5, "Chord Memory": 6, "Lush Pad": 5.5,
        "Scale 9th Pad": 3, "Choir Air": 11.5, "Evolving Texture": 11, "String Machine": 3, "Deep Drone": 11,
        "Glass Pad": 3, "Harp Pluck": 5, "Super Pluck": 7.5, "Marimba": 4.5, "Chip Arp": 8.5, "Kalimba": 2,
        "Hardcore Stab": 7, "Digital Stab": 6.5, "Garage Organ Stab": 7, "Vocal Chop": 9, "Wavetable Sub Bass": 3.5,
        "E-Bass": 6.5, "Vowel Growl Bass": 1.5, "Birdsong": 2, "Bitcrush Glitch": 2.5, "Game Laser": 6,
    },
}


def bank(pre, rows):
    presets, cats = [], {}
    for cat, name, vals in rows:
        vals = dict(vals)
        if pre == "s1" and cat != "BASS":
            vals.setdefault("sub", 0.0)   # Synth 1's sub osc is on by default: only basses keep it
        if name in TRIM[pre]:
            vals.setdefault("trim", TRIM[pre][name])
        out = {}
        for k, v in vals.items():
            if f"{pre}.{k}" not in SPECS:
                raise KeyError(f"{name}: no setting {pre}.{k}")
            out[k] = _value(pre, k, v)
        presets.append((name, out))
        cats[name] = cat
    return presets, cats


_s1, _c1 = bank("s1", SYNTH1)
_s2, _c2 = bank("s2", SYNTH2)
PRESETS = {"s1": _s1, "s2": _s2}
PRESET_CAT = {"s1": _c1, "s2": _c2}
