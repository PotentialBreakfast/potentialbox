"""Projects tab: sounds for the 16 BeatStep Pro genre sets (PotentialBreaks' "BeatStep Pro Genre Sets").

Each BeatStep project N holds an evolving 16-pattern set in one genre. Loading project N here gives
Synth 1 (Seq 1) a bass, Synth 2 (Seq 2) a lead, the drums a genre kit laid out the way the sets play it,
and sets the effects and tempo to suit.

The genre sets put their drums on these BeatStep drum tracks:
    1 kick · 2 clap · 3 snare · 4 percussion · 5 closed hat · 6 open hat · 7 rim · 8 shaker
PotentialBox's own kits use 1 kick · 2 808 · 3 snare · 4 clap · 5 hat · 6 open hat · 10 rim · 13 shaker,
so a project kit is the genre kit with its pads moved into the sets' order (set_order).
"""

# Pads of PotentialBox's shared kit layout (0-based), see beats.ROLE_PAD
KICK, K808, SNARE, CLAP, HAT, OPEN, LTOM, MTOM, HTOM, RIM, COWBELL, CLAVE, SHAKER, CYMBAL, FX, CONGA = range(16)

KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def set_order(perc):
    """For each BeatStep drum track (0-based), the PotentialBox kit pad that should play on it."""
    order = [KICK, CLAP, SNARE, perc, HAT, OPEN, RIM, SHAKER]
    return order + [p for p in range(16) if p not in order]


# Effects and mix settings a project sets. They are put back to their defaults first, so moving from
# one project to the next never carries the last one's effects over.
FX_KEYS = ("fx.s1", "fx.s2", "fx.dr", "fx.time", "fx.fb", "rv.s1", "rv.s2", "rv.dr", "rv.size",
           "m.crush", "m.chorus", "m.phaser", "dk.s1", "dk.s2", "dr.drive", "dr.filter", "m.glue")

# Synth 1 notes from the sets sit around C1-C3 and Synth 2 around C4-C6, so both play at octave 0.
_B = dict(octave=0)
_L = dict(octave=0)


def _b(**kw):
    d = dict(_B)
    d.update(kw)
    return d


def _l(**kw):
    d = dict(_L)
    d.update(kw)
    return d


# name, file number, BPM, key, kits (built-in kit index: main, alternative), Kit Maker style,
# percussion pad, [(bass name, Synth 1 sound)...], [(lead name, Synth 2 sound)...], effects
PROJECTS = [
    dict(name="Boom bap", bpm=90, key="D minor", kits=(5, 16), drums="Boom Bap", style="BOOM BAP", perc=CONGA,
         bass=[("Dusty Bass", _b(wave=0.7, sub=0.6, cutoff=500, reso=0.15, envamt=0.25, fdecay=0.3, attack=0.004,
                                 decay=0.5, sustain=0.6, release=0.12, drive=0.25, drift=0.3)),
               ("Boom Sub", _b(wave=1, sub=0.9, cutoff=260, reso=0.05, envamt=0.1, attack=0.003, decay=0.8,
                               sustain=0.8, release=0.15, drive=0.2))],
         lead=[("Dusty Keys", _l(table=8, pos=0.3, posenv=0, lfoamt=0, cutoff=4000, reso=0.1, envamt=0.2,
                                 attack=0.003, decay=1.2, sustain=0.4, release=0.6, detune=0.1, drift=0.3)),
               ("Old Flute", _l(table=23, pos=0.4, posenv=0, lforate=5, lfoamt=0.05, cutoff=5000, reso=0.05,
                                envamt=0.1, attack=0.04, decay=1.0, sustain=0.7, release=0.4, detune=0.05, drift=0.4))],
         fx={"rv.s2": 0.25, "fx.s2": 0.15, "fx.time": 2, "m.crush": 0.15, "dr.drive": 0.25, "m.glue": 0.3,
             "rv.dr": 0.05}),
    dict(name="Lo-fi", bpm=78, key="F Dorian", kits=(17, 5), drums="Lo-fi", style="LO-FI", perc=CONGA,
         bass=[("Warm Muted Bass", _b(wave=0.5, sub=0.5, cutoff=380, reso=0.1, envamt=0.2, fdecay=0.3,
                                      attack=0.005, decay=0.6, sustain=0.5, release=0.2, drift=0.4, drive=0.1)),
               ("Round Sub", _b(wave=1, sub=0.9, cutoff=220, reso=0.05, envamt=0.05, attack=0.004, decay=0.9,
                                sustain=0.8, release=0.2, drift=0.3))],
         lead=[("Tape Rhodes", _l(table=8, pos=0.25, posenv=0, lfoamt=0, cutoff=3000, reso=0.05, envamt=0.15,
                                  attack=0.004, decay=1.5, sustain=0.35, release=0.8, detune=0.15, drift=0.6,
                                  l1rate=5.0, m1amt=0.03)),
               ("Muted Guitar", _l(table=20, pos=0.3, posenv=0.2, lfoamt=0, cutoff=2500, reso=0.1, envamt=0.3,
                                   attack=0.002, decay=0.35, sustain=0, release=0.25, detune=0.05, drift=0.4))],
         fx={"m.crush": 0.35, "rv.s2": 0.3, "fx.s2": 0.2, "fx.time": 3, "dr.filter": 9000, "m.glue": 0.35,
             "rv.dr": 0.1}),
    dict(name="Breakbeat", bpm=110, key="E minor", kits=(11, 12), drums="Breakbeat", style="JUNGLE", perc=CONGA,
         bass=[("Breaks Bass", _b(wave=1, detune=14, sub=0.5, cutoff=900, reso=0.3, envamt=0.4, fdecay=0.2,
                                  attack=0.002, decay=0.3, sustain=0.6, release=0.08, drive=0.35)),
               ("FM Bass", _b(wave=0, fm=0.55, osc2=0, sub=0.3, cutoff=800, reso=0.25, envamt=0.45, fdecay=0.2,
                              attack=0.001, decay=0.3, sustain=0.5, release=0.08, drive=0.4))],
         lead=[("Rave Stab", _l(table=28, pos=0.5, posenv=0.2, lfoamt=0, cutoff=5000, reso=0.2, envamt=0.3,
                                attack=0.002, decay=0.35, sustain=0.2, release=0.25, detune=0.45)),
               ("Big Beat Lead", _l(table=6, pos=0.3, posenv=0.4, lfoamt=0, cutoff=6000, reso=0.15, envamt=0.2,
                                    attack=0.005, decay=0.6, sustain=0.6, release=0.3, glide=0.06, detune=0.3))],
         fx={"fx.s2": 0.2, "fx.time": 2, "rv.s2": 0.15, "dr.drive": 0.35, "m.glue": 0.4}),
    dict(name="Jungle", bpm=170, key="F minor", kits=(12, 11), drums="Jungle", style="JUNGLE", perc=CONGA,
         bass=[("Jungle Sub", _b(wave=1, sub=1.0, cutoff=180, reso=0, envamt=0.05, attack=0.003, decay=1.0,
                                 sustain=1.0, release=0.15, glide=0.05)),
               ("Reese", _b(wave=0, detune=30, supersaw=0.3, sub=0.5, cutoff=400, reso=0.2, envamt=0.1,
                            attack=0.004, decay=1.0, sustain=0.9, release=0.15, l1rate=0.3, m2amt=0.2, drive=0.3))],
         lead=[("Rave Pad", _l(table=3, pos=0.2, posenv=0, lforate=0.4, lfoamt=0.5, cutoff=3500, reso=0.1,
                               envamt=0.1, attack=0.2, decay=1.5, sustain=0.8, release=1.2, detune=0.45)),
               ("Ragga Bell", _l(table=4, pos=0.4, posenv=0.3, lfoamt=0, cutoff=9000, reso=0.1, envamt=0.2,
                                 attack=0.002, decay=1.0, sustain=0.1, release=0.8, detune=0.15))],
         fx={"rv.s2": 0.35, "fx.s2": 0.25, "fx.time": 3, "dr.drive": 0.2}),
    dict(name="House", bpm=124, key="A minor", kits=(2, 9), drums="House", style="HOUSE", perc=CONGA,
         bass=[("Deep House Bass", _b(wave=0.2, sub=0.5, cutoff=600, reso=0.25, envamt=0.45, fdecay=0.18,
                                      attack=0.002, decay=0.25, sustain=0.4, release=0.08, drive=0.15)),
               ("Organ Bass", _b(wave=1, pw=0.5, osc2=12, sub=0.6, cutoff=900, reso=0.1, envamt=0.2, fdecay=0.2,
                                 attack=0.002, decay=0.3, sustain=0.5, release=0.06, drive=0.1))],
         lead=[("House Organ Stab", _l(table=7, pos=0.4, posenv=0, lfoamt=0, chord=9, voicing=1, cutoff=4000,
                                       reso=0.1, envamt=0.2, attack=0.002, decay=0.3, sustain=0, release=0.2,
                                       detune=0.2)),
               ("Piano Stab", _l(table=8, pos=0.35, posenv=0, lfoamt=0, chord=5, voicing=0, cutoff=6000, reso=0.05,
                                 envamt=0.15, attack=0.002, decay=0.6, sustain=0.1, release=0.4, detune=0.1))],
         fx={"dk.s1": 0.35, "dk.s2": 0.3, "rv.s2": 0.2, "fx.s2": 0.2, "fx.time": 3, "m.glue": 0.3}),
    dict(name="Techno", bpm=130, key="E Phrygian", kits=(2, 8), drums="Techno", style="TECHNO", perc=COWBELL,
         bass=[("Rolling Techno", _b(wave=0, sub=0.4, cutoff=350, reso=0.45, envamt=0.5, fdecay=0.12,
                                     attack=0.001, decay=0.15, sustain=0.2, release=0.05, drive=0.45)),
               ("Sync Rumble", _b(wave=0, sync=1, osc2=7, sub=0.5, cutoff=300, reso=0.3, envamt=0.3, fdecay=0.15,
                                  attack=0.001, decay=0.25, sustain=0.3, release=0.06, drive=0.5))],
         lead=[("Dub Chord", _l(table=0, pos=0.4, posenv=0, lfoamt=0, chord=5, voicing=1, cutoff=1500, reso=0.2,
                                envamt=0.4, attack=0.002, decay=0.25, sustain=0, release=0.2, detune=0.25)),
               ("Metal Pluck", _l(table=13, pos=0.3, posenv=0.5, lfoamt=0, cutoff=7000, reso=0.25, envamt=0.3,
                                  attack=0.001, decay=0.2, sustain=0, release=0.15, detune=0.1))],
         fx={"fx.s2": 0.45, "fx.time": 3, "fx.fb": 0.55, "rv.s2": 0.3, "dk.s1": 0.4, "dk.s2": 0.3,
             "dr.drive": 0.2}),
    dict(name="Acid", bpm=126, key="A minor", kits=(2, 1), drums="Techno", style="TECHNO", perc=COWBELL,
         bass=[("303 Acid", _b(wave=0, sub=0, cutoff=320, reso=0.85, envamt=0.7, fdecay=0.16, attack=0.001,
                               decay=0.3, sustain=0.6, release=0.05, glide=0.07, drive=0.55, velamp=0.4)),
               ("Square Acid", _b(wave=1, pw=0.5, sub=0, cutoff=380, reso=0.8, envamt=0.65, fdecay=0.14,
                                  attack=0.001, decay=0.3, sustain=0.6, release=0.05, glide=0.07, drive=0.6,
                                  velamp=0.4))],
         lead=[("Acid Stab", _l(table=28, pos=0.4, posenv=0.3, lfoamt=0, chord=3, cutoff=3000, reso=0.4, envamt=0.5,
                                attack=0.001, decay=0.25, sustain=0, release=0.2, detune=0.3)),
               ("Rave Lead", _l(table=6, pos=0.5, posenv=0.3, lfoamt=0, cutoff=5000, reso=0.2, envamt=0.3,
                                attack=0.003, decay=0.5, sustain=0.5, release=0.3, glide=0.05, detune=0.35))],
         fx={"fx.s1": 0.15, "fx.s2": 0.3, "fx.time": 3, "dk.s1": 0.2, "dr.drive": 0.25}),
    dict(name="Trap", bpm=140, key="C minor", kits=(4, 14), drums="Trap", style="TRAP", perc=CONGA,
         bass=[("808 Bass", _b(wave=1, sub=1.0, cutoff=300, reso=0, envamt=0, attack=0.002, decay=2.5,
                               sustain=0, release=0.4, glide=0.08, penv=7, pdec=0.04, drive=0.35)),
               ("Distorted 808", _b(wave=1, sub=1.0, cutoff=500, reso=0, envamt=0, attack=0.002, decay=2.0,
                                    sustain=0, release=0.35, glide=0.08, penv=9, pdec=0.04, drive=0.8))],
         lead=[("Trap Bell", _l(table=4, pos=0.4, posenv=0.2, lfoamt=0, cutoff=9000, reso=0.05, envamt=0.1,
                                attack=0.002, decay=0.8, sustain=0, release=0.6, detune=0.1)),
               ("Dark Pluck", _l(table=19, pos=0.3, posenv=0.3, lfoamt=0, cutoff=4000, reso=0.15, envamt=0.3,
                                 attack=0.001, decay=0.4, sustain=0, release=0.3, detune=0.15))],
         fx={"rv.s2": 0.3, "fx.s2": 0.15, "fx.time": 3, "m.glue": 0.25}),
    dict(name="Trip hop", bpm=88, key="G minor", kits=(5, 13), drums="Boom Bap", style="DUSTY JAZZ", perc=CONGA,
         bass=[("Dub Bass", _b(wave=0.8, sub=0.8, cutoff=350, reso=0.1, envamt=0.15, attack=0.004, decay=0.8,
                               sustain=0.7, release=0.25, drift=0.3, drive=0.2)),
               ("Muted Bass", _b(wave=0.4, sub=0.5, cutoff=450, reso=0.15, envamt=0.3, fdecay=0.25, attack=0.003,
                                 decay=0.4, sustain=0.3, release=0.15, drift=0.3))],
         lead=[("Moody Strings", _l(table=15, pos=0.3, posenv=0, lforate=0.3, lfoamt=0.2, cutoff=3000, reso=0.1,
                                    envamt=0.1, attack=0.25, decay=2.0, sustain=0.8, release=1.5, detune=0.4,
                                    drift=0.4)),
               ("Theremin", _l(table=27, pos=0.3, posenv=0, lfoamt=0, cutoff=6000, reso=0.05, envamt=0.05,
                               attack=0.06, decay=1.5, sustain=0.9, release=0.5, glide=0.2, glmode=1, l1rate=5.5,
                               m1amt=0.05, detune=0))],
         fx={"rv.s2": 0.45, "rv.size": 0.75, "fx.s2": 0.2, "fx.time": 4, "m.crush": 0.2, "dr.filter": 12000}),
    dict(name="UK garage", bpm=132, key="G Dorian", kits=(10, 2), drums="UK Garage", style="HOUSE", perc=CONGA,
         bass=[("Garage Sub", _b(wave=0.6, sub=0.8, cutoff=500, reso=0.15, envamt=0.3, fdecay=0.2, attack=0.002,
                                 decay=0.4, sustain=0.6, release=0.1, glide=0.05, drive=0.15)),
               ("2-Step Wobble", _b(wave=0.6, sub=0.6, ftype=1, cutoff=300, reso=0.5, envamt=0.1, l1sync=6,
                                    m2amt=0.4, attack=0.002, decay=0.5, sustain=0.9, release=0.1, drive=0.4))],
         lead=[("Garage Organ", _l(table=7, pos=0.4, posenv=0, lfoamt=0, chord=9, voicing=1, cutoff=4500,
                                   reso=0.1, envamt=0.2, attack=0.002, decay=0.3, sustain=0, release=0.2, detune=0.2)),
               ("Vocal Chop", _l(table=9, pos=0.5, posenv=0.3, lfoamt=0, cutoff=7000, reso=0.1, envamt=0.2,
                                 attack=0.003, decay=0.25, sustain=0, release=0.15, detune=0.15))],
         fx={"dk.s1": 0.25, "rv.s2": 0.2, "fx.s2": 0.2, "fx.time": 3, "m.glue": 0.3}),
    dict(name="Dubstep", bpm=140, key="F Phrygian", kits=(13, 8), drums="Dubstep", style="DUB", perc=CONGA,
         bass=[("Wobble Bass", _b(wave=0.6, sub=0.6, ftype=1, cutoff=250, reso=0.55, envamt=0.1, l1sync=6,
                                  m2amt=0.55, attack=0.002, decay=0.5, sustain=0.9, release=0.1, drive=0.5)),
               ("Sub Hold", _b(wave=1, sub=1.0, cutoff=200, reso=0, envamt=0.05, attack=0.004, decay=1.5,
                               sustain=1.0, release=0.2, drive=0.2))],
         lead=[("Dark Pad", _l(table=10, pos=0.3, posenv=0, lfoamt=0, l2shape=6, l2rate=0.15, m3amt=0.5,
                               cutoff=2500, reso=0.2, envamt=0.1, attack=0.5, decay=2.5, sustain=0.9, release=2.0,
                               detune=0.5, sub=0.2)),
               ("Eerie Bell", _l(table=4, pos=0.6, posenv=0.2, lfoamt=0, cutoff=8000, reso=0.1, envamt=0.1,
                                 attack=0.002, decay=1.5, sustain=0.1, release=1.2, detune=0.3))],
         fx={"rv.s2": 0.4, "fx.s2": 0.3, "fx.time": 3, "m.glue": 0.3}),
    dict(name="Electro", bpm=120, key="D minor", kits=(6, 1), drums="Electro", style="ELECTRO", perc=COWBELL,
         bass=[("Electro Bass", _b(wave=1, pw=0.35, sub=0.4, cutoff=700, reso=0.35, envamt=0.5, fdecay=0.14,
                                   attack=0.001, decay=0.2, sustain=0.5, release=0.06, drive=0.3)),
               ("FM Bass", _b(wave=0, fm=0.55, osc2=0, sub=0.3, cutoff=800, reso=0.25, envamt=0.45, fdecay=0.2,
                              attack=0.001, decay=0.3, sustain=0.5, release=0.08, drive=0.4))],
         lead=[("Robot Lead", _l(table=1, pos=0.3, posenv=0.3, lforate=0.8, lfoamt=0.3, cutoff=6000, reso=0.15,
                                 envamt=0.2, attack=0.003, decay=0.4, sustain=0.6, release=0.15, detune=0.1)),
               ("Chip Zap", _l(table=12, pos=0.2, posenv=0.4, lfoamt=0, cutoff=9000, reso=0.1, envamt=0.1,
                               attack=0.001, decay=0.2, sustain=0.3, release=0.1, glide=0.03, glmode=1, detune=0.05))],
         fx={"fx.s2": 0.3, "fx.time": 2, "rv.s2": 0.15, "m.chorus": 0.2}),
    dict(name="Disco", bpm=118, key="A Dorian", kits=(16, 2), drums="Disco", style="HOUSE", perc=CONGA,
         bass=[("Disco Octave Bass", _b(wave=0.3, sub=0.3, cutoff=1100, reso=0.2, envamt=0.35, fdecay=0.15,
                                        attack=0.001, decay=0.25, sustain=0.5, release=0.06, drive=0.15)),
               ("Slap Bass", _b(wave=0.6, sub=0.4, cutoff=1400, reso=0.25, envamt=0.5, fdecay=0.08, penv=5,
                                pdec=0.02, attack=0.001, decay=0.2, sustain=0.4, release=0.06, drive=0.2))],
         lead=[("Disco Strings", _l(table=15, pos=0.3, posenv=0, lforate=0.3, lfoamt=0.2, cutoff=6000, reso=0.05,
                                    envamt=0.1, attack=0.08, decay=1.0, sustain=0.8, release=0.6, detune=0.5)),
               ("Funky Clav", _l(table=20, pos=0.4, posenv=0.3, lfoamt=0, cutoff=5000, reso=0.2, envamt=0.4,
                                 attack=0.001, decay=0.25, sustain=0.1, release=0.1, detune=0.05))],
         fx={"m.chorus": 0.25, "rv.s2": 0.25, "fx.s2": 0.1, "fx.time": 2, "dk.s1": 0.15, "m.glue": 0.3}),
    dict(name="Reggaeton", bpm=96, key="G minor", kits=(15, 4), drums="Reggaeton", style="TRAP", perc=CONGA,
         bass=[("Reggaeton 808", _b(wave=1, sub=1.0, cutoff=320, reso=0, envamt=0, attack=0.002, decay=0.8,
                                    sustain=0, release=0.25, glide=0.06, penv=5, pdec=0.03, drive=0.3)),
               ("Round Bass", _b(wave=0.8, sub=0.8, cutoff=400, reso=0.1, envamt=0.15, attack=0.003, decay=0.5,
                                 sustain=0.5, release=0.15, drive=0.15))],
         lead=[("Marimba Pluck", _l(table=26, pos=0.3, posenv=0.2, lfoamt=0, cutoff=8000, reso=0.05, envamt=0.2,
                                    attack=0.001, decay=0.35, sustain=0, release=0.25, detune=0.05)),
               ("Latin Pluck", _l(table=19, pos=0.4, posenv=0.2, lfoamt=0, cutoff=6000, reso=0.1, envamt=0.3,
                                  attack=0.001, decay=0.45, sustain=0, release=0.3, detune=0.1))],
         fx={"rv.s2": 0.2, "fx.s2": 0.15, "fx.time": 3, "m.glue": 0.3}),
    dict(name="Synthwave", bpm=100, key="A minor", kits=(6, 8), drums="Electro", style="ELECTRO", perc=COWBELL,
         bass=[("Pulsing Saw Bass", _b(wave=0, detune=10, sub=0.3, cutoff=700, reso=0.2, envamt=0.35, fdecay=0.1,
                                       attack=0.001, decay=0.15, sustain=0.3, release=0.05, drive=0.15)),
               ("Square Pulse", _b(wave=1, pw=0.4, sub=0.4, cutoff=650, reso=0.2, envamt=0.3, fdecay=0.1,
                                   attack=0.001, decay=0.15, sustain=0.3, release=0.05, drive=0.1))],
         lead=[("Retro Poly Lead", _l(table=28, pos=0.4, posenv=0.1, lfoamt=0, cutoff=5500, reso=0.15, envamt=0.2,
                                      attack=0.01, decay=1.0, sustain=0.7, release=0.5, glide=0.08, detune=0.45)),
               ("80s Brass", _l(table=0, pos=0.5, posenv=0.3, lfoamt=0, cutoff=3500, reso=0.15, envamt=0.4,
                                attack=0.05, decay=0.8, sustain=0.7, release=0.4, detune=0.35))],
         fx={"m.chorus": 0.35, "rv.s2": 0.4, "rv.size": 0.7, "fx.s2": 0.25, "fx.time": 2, "rv.dr": 0.2}),
    dict(name="Footwork", bpm=160, key="C minor pentatonic", kits=(1, 14), drums="Footwork", style="TRAP", perc=CONGA,
         bass=[("Juke 808", _b(wave=1, sub=1.0, cutoff=320, reso=0, envamt=0, attack=0.002, decay=1.2,
                               sustain=0, release=0.3, glide=0.05, penv=6, pdec=0.03, drive=0.3)),
               ("Short Sub", _b(wave=1, sub=0.9, cutoff=250, reso=0, envamt=0.05, attack=0.002, decay=0.35,
                                sustain=0.2, release=0.1, drive=0.2))],
         lead=[("Vocal Chop", _l(table=9, pos=0.5, posenv=0.3, lfoamt=0, cutoff=7000, reso=0.1, envamt=0.2,
                                 attack=0.003, decay=0.25, sustain=0, release=0.15, detune=0.15)),
               ("Chop Stab", _l(table=18, pos=0.4, posenv=0.3, lfoamt=0, cutoff=6000, reso=0.1, envamt=0.2,
                                attack=0.002, decay=0.3, sustain=0, release=0.2, detune=0.2))],
         fx={"rv.s2": 0.15, "fx.s2": 0.25, "fx.time": 0}),
]

# v1.12: the same curated sounds, finished with the pro engine (unison, filter drive, distortion, synth FX, warp).
# Indexes: uni 0=1 1=2 2=3 3=4 4=5 5=7 voices · dist 1 Tube 2 Tape 3 Fold 4 Crush 5 Hard clip ·
# sfx 1 Chorus 2 Ensemble 3 Dimension 4 Phaser 5 Flanger · warp 1 Bend+ 2 Bend- 3 Mirror 4 Sync 5 Squeeze 6 Phase FM 7 Quantize
_PRO = {
    "Dusty Bass": dict(dist=2, distamt=0.3, fdrive=0.2), "Boom Sub": dict(dist=2, distamt=0.2),
    "Dusty Keys": dict(sfx=1, sfxamt=0.35, dist=4, distamt=0.12), "Old Flute": dict(sfx=3, sfxamt=0.4),
    "Warm Muted Bass": dict(dist=2, distamt=0.3), "Round Sub": dict(dist=2, distamt=0.15),
    "Tape Rhodes": dict(sfx=1, sfxamt=0.5, dist=4, distamt=0.18), "Muted Guitar": dict(sfx=3, sfxamt=0.4),
    "Breaks Bass": dict(uni=1, unidet=0.2, uniwid=0.4, dist=1, distamt=0.4), "FM Bass": dict(fdrive=0.4),
    "Rave Stab": dict(uni=4, detune=0.4, uniwid=1.0, sfx=2, sfxamt=0.4),
    "Big Beat Lead": dict(warp=4, warpamt=0.3, dist=1, distamt=0.3),
    "Jungle Sub": dict(dist=2, distamt=0.15), "Reese": dict(uni=3, unidet=0.35, uniwid=0.4, fdrive=0.4, dist=1, distamt=0.3),
    "Rave Pad": dict(uni=4, detune=0.5, uniwid=1.0, sfx=2, sfxamt=0.6), "Ragga Bell": dict(sfx=3, sfxamt=0.3),
    "Deep House Bass": dict(fdrive=0.3), "Organ Bass": dict(dist=1, distamt=0.2),
    "House Organ Stab": dict(sfx=3, sfxamt=0.45, dist=1, distamt=0.2), "Piano Stab": dict(sfx=1, sfxamt=0.3),
    "Rolling Techno": dict(fdrive=0.5, dist=1, distamt=0.3), "Sync Rumble": dict(dist=3, distamt=0.3),
    "Dub Chord": dict(sfx=3, sfxamt=0.5, dist=2, distamt=0.25), "Metal Pluck": dict(warp=4, warpamt=0.3),
    "303 Acid": dict(fdrive=0.5, dist=1, distamt=0.4), "Square Acid": dict(fdrive=0.5, dist=5, distamt=0.2),
    "Acid Stab": dict(uni=2, detune=0.3, uniwid=0.8, sfx=4, sfxamt=0.3),
    "Rave Lead": dict(uni=5, detune=0.45, uniwid=1.0, sfx=2, sfxamt=0.4),
    "808 Bass": dict(dist=1, distamt=0.3), "Distorted 808": dict(dist=3, distamt=0.25),
    "Trap Bell": dict(sfx=1, sfxamt=0.3, warp=1, warpamt=0.15), "Dark Pluck": dict(uni=1, detune=0.2, sfx=3, sfxamt=0.4),
    "Dub Bass": dict(dist=2, distamt=0.3), "Muted Bass": dict(dist=2, distamt=0.2),
    "Moody Strings": dict(uni=3, detune=0.45, uniwid=1.0, sfx=2, sfxamt=0.6), "Theremin": dict(sfx=1, sfxamt=0.2),
    "Garage Sub": dict(dist=2, distamt=0.2), "2-Step Wobble": dict(fdrive=0.4, dist=3, distamt=0.25),
    "Garage Organ": dict(sfx=3, sfxamt=0.45, dist=1, distamt=0.2), "Vocal Chop": dict(warp=4, warpamt=0.25, sfx=1, sfxamt=0.3),
    "Wobble Bass": dict(uni=1, unidet=0.2, uniwid=0.3, fdrive=0.5, dist=3, distamt=0.45),
    "Sub Hold": dict(dist=2, distamt=0.2),
    "Dark Pad": dict(uni=3, detune=0.5, uniwid=1.0, sfx=2, sfxamt=0.5, warp=3, warpamt=0.2),
    "Eerie Bell": dict(sfx=5, sfxamt=0.3),
    "Electro Bass": dict(dist=5, distamt=0.2), "Robot Lead": dict(warp=7, warpamt=0.25, sfx=4, sfxamt=0.35),
    "Chip Zap": dict(warp=7, warpamt=0.3),
    "Disco Octave Bass": dict(dist=2, distamt=0.2), "Slap Bass": dict(fdrive=0.3),
    "Disco Strings": dict(uni=4, detune=0.45, uniwid=1.0, sfx=2, sfxamt=0.65), "Funky Clav": dict(sfx=4, sfxamt=0.45),
    "Reggaeton 808": dict(dist=1, distamt=0.3), "Round Bass": dict(dist=2, distamt=0.2),
    "Marimba Pluck": dict(sfx=3, sfxamt=0.3), "Latin Pluck": dict(uni=1, detune=0.15, sfx=1, sfxamt=0.3),
    "Pulsing Saw Bass": dict(uni=2, unidet=0.2, uniwid=0.5, fdrive=0.2), "Square Pulse": dict(sfx=1, sfxamt=0.3),
    "Retro Poly Lead": dict(uni=4, detune=0.45, uniwid=1.0, sfx=1, sfxamt=0.5),
    "80s Brass": dict(uni=2, detune=0.3, uniwid=0.9, sfx=2, sfxamt=0.4),
    "Juke 808": dict(dist=1, distamt=0.35), "Short Sub": dict(dist=2, distamt=0.2),
    "Chop Stab": dict(warp=7, warpamt=0.2, sfx=3, sfxamt=0.3),
}
for _pr in PROJECTS:
    for _part in ("bass", "lead"):
        for _name, _snd in _pr[_part]:
            for _k, _v in _PRO.get(_name, {}).items():
                if _part == "lead" and _k == "unidet":
                    _k = "detune"      # Synth 2's unison detune is its Unison knob
                if _part == "bass" and _k in ("detune", "warp", "warpamt"):
                    continue
                _snd.setdefault(_k, _v)

# v1.12: deeper, cleaner basslines. Every project bass gets a clean sine sub at the note's own pitch, added after
# the filter, drive and distortion so the low end stays solid, and loses the heavy distortion and filter drive.
# The bass's character (acid squelch, reese movement, wobble, 808 punch) stays on top, kept light.
_BASS_CLEAN = {
    "303 Acid": dict(sub=0.55, drive=0.2, reso=0.75), "Square Acid": dict(sub=0.55, drive=0.18, reso=0.72),
    "FM Bass": dict(fm=0.3, sub=0.75), "Sync Rumble": dict(sub=0.9, cutoff=260),
    "Rolling Techno": dict(sub=0.9, reso=0.35), "Reese": dict(sub=0.8, cutoff=380),
    "Wobble Bass": dict(sub=0.85, reso=0.45), "2-Step Wobble": dict(sub=0.85, reso=0.4),
    "Breaks Bass": dict(sub=0.75, cutoff=600), "Electro Bass": dict(sub=0.7, cutoff=550),
    "Distorted 808": dict(sub=1.0, decay=3.0, penv=5, cutoff=260),
    "Pulsing Saw Bass": dict(sub=0.7, cutoff=550), "Deep House Bass": dict(sub=0.8, cutoff=480),
}
_RENAME = {"Distorted 808": "Long 808"}
for _pr in PROJECTS:
    for _i, (_name, _snd) in enumerate(_pr["bass"]):
        for _k in ("dist", "distamt", "fdrive"):
            _snd.pop(_k, None)
        _snd["drive"] = min(_snd.get("drive", 0.2), 0.12)
        _snd["subtype"] = 2                       # Root, clean
        _snd["sub"] = max(_snd.get("sub", 0.3), 0.7)
        _snd.update(_BASS_CLEAN.get(_name, {}))
        if _name in _RENAME:
            _pr["bass"][_i] = (_RENAME[_name], _snd)

# ---- chords: every Synth 2 sound plays the set's melody as full chords in the project's key, following the
# chord lane (drum tracks 9-15 on the BeatStep) so each bar sits on the right chord. Kept crisp: quick release,
# bright filter, and the chords stay above the sub so the low end stays clean.
from .engine import CHORDS as _CHORDS, KEY_NAMES as _KEYS, HARM_SCALE_NAMES as _HSC
_CI = {c[0]: i for i, c in enumerate(_CHORDS)}
_PADS = {"Rave Pad", "Moody Strings", "Dark Pad", "Disco Strings", "Dub Chord", "Tape Rhodes", "Dusty Keys",
         "House Organ Stab", "Garage Organ", "Piano Stab", "Retro Poly Lead", "80s Brass", "Acid Stab", "Rave Stab"}
for _pr in PROJECTS:
    _root, _mode = _pr["key"].split(" ", 1)
    _sc = {"minor": "Minor", "major": "Major", "dorian": "Dorian", "phrygian": "Phrygian"}.get(
        _mode.split()[0].lower(), "Minor")
    for _name, _snd in _pr["lead"]:
        pad = _name in _PADS
        _snd["chord"] = _CI["Scale 7th" if pad else "Scale triad"]
        _snd["voicing"] = 1 if pad else 0
        _snd["hkey"] = _KEYS.index(_root)
        _snd["hscale"] = _HSC.index(_sc)
        _snd["lane"] = 1
        _snd["release"] = min(_snd.get("release", 0.3), 0.45 if pad else 0.22)
        _snd["cutoff"] = max(_snd.get("cutoff", 3000), 2600 if pad else 3400)
        _snd["sub"] = 0                          # the bass owns the sub
        _snd["uni"] = min(_snd.get("uni", 1), 2)  # 4-note chords x 2 unison = the 8-oscillator budget
        if _name in ("Robot Lead", "Chip Zap", "House Organ Stab", "Dark Pluck"):
            _snd["vol"] = 0.85                   # short sounds: a little louder so the chords sit level with the bass

NAMES = [p["name"] for p in PROJECTS]

# "New sounds" steps through these (bass, lead, kit) choices, so four taps cover every pairing
TAKES = [(0, 0, 0), (1, 1, 1), (0, 1, 0), (1, 0, 1)]


def take(project, n):
    b, l, k = TAKES[n % len(TAKES)]
    return project["bass"][b], project["lead"][l], project["kits"][k]


# ---- voice: phrases Windows speech recognition listens for, and what each one does
_NUM = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen"]
_GENRE_WORDS = {
    0: ["boom bap"], 1: ["lo-fi", "lo fi", "low fi"], 2: ["breakbeat", "break beat", "breaks"],
    3: ["jungle"], 4: ["house"], 5: ["techno"], 6: ["acid", "acid house"], 7: ["trap"],
    8: ["trip hop"], 9: ["garage", "uk garage", "two step"], 10: ["dubstep", "dub step"],
    11: ["electro"], 12: ["disco"], 13: ["reggaeton"], 14: ["synthwave", "synth wave"], 15: ["footwork", "juke"],
}
COMMANDS = {}
for _i, _w in enumerate(_NUM):
    COMMANDS[f"project {_w}"] = ("project", _i)
    COMMANDS[f"project number {_w}"] = ("project", _i)
for _i, _ws in _GENRE_WORDS.items():
    for _w in _ws:
        COMMANDS[_w] = ("project", _i)
COMMANDS.update({"next project": ("step", 1), "previous project": ("step", -1), "last project": ("step", -1),
                 "new sounds": ("take", 1), "new sound": ("take", 1), "stop listening": ("mic_off", 0)})
PHRASES = sorted(COMMANDS)


def command(text):
    """Turn what was heard into ("project", i) / ("step", d) / ("take", 1) / ("mic_off", 0), or None."""
    return COMMANDS.get(" ".join(str(text).lower().split()))


# ---- mutate: new sounds that stay inside each project's own curated sounds
# A synth mutation picks a point between the project's two curated sounds for that part, adds a little
# randomness, and keeps every setting within the range those two sounds span (plus a margin), so a Trap
# 808 stays an 808 and an acid line stays acid. Settings neither curated sound uses are left alone.
AMOUNTS = ["MILD", "MEDIUM", "WILD"]
_MUT = {  # randomness (0-1 of the knob's range), how far it may move towards the other curated sound, margin
    "MILD": (0.04, 0.3, 0.06),
    "MEDIUM": (0.09, 0.7, 0.12),
    "WILD": (0.16, 1.0, 0.2),
}
_TONE = {
    "s1": ("cutoff", "reso", "envamt", "fdecay", "decay", "sustain", "release", "drive", "detune", "sub", "wave",
           "fdrive", "distamt", "sfxamt", "unidet", "uniwid"),
    "s2": ("cutoff", "reso", "envamt", "pos", "posenv", "decay", "sustain", "release", "detune", "lfoamt",
           "fdrive", "distamt", "sfxamt", "warpamt", "uniwid"),
}
_NEVER = ("octave", "vol", "pan", "glmode", "velamp", "glide", "attack", "subtype", "hkey", "hscale", "lane")
_BASS_NO_MORE = ("drive", "fdrive", "distamt", "reso", "fm")
PART_PRE = {"bass": "s1", "lead": "s2"}


def mutate_synth(specs, pr, part, cur_norm, amount, rng):
    """Targets for one synth: {key: norm}. Step settings (wavetable, chord, filter type, LFO sync) only ever take
    one of the two curated values, and only on MEDIUM (sometimes) and WILD."""
    pre = PART_PRE[part]
    jit, reach, margin = _MUT[amount]
    a, b = pr[part][0][1], pr[part][1][1]
    if rng.random() < 0.5:
        a, b = b, a
    t = rng.random() * reach
    out = {}
    for k in sorted(set(a) | set(b) | set(_TONE[pre])):
        key = f"{pre}.{k}"
        sp = specs.get(key)
        if sp is None or k in _NEVER:
            continue
        va, vb = a.get(k, sp.default), b.get(k, sp.default)
        if sp.choices or sp.step:
            if va != vb and (amount == "WILD" and rng.random() < 0.5 or amount == "MEDIUM" and rng.random() < 0.2):
                out[key] = sp.to_norm(vb)
            continue
        na, nb = sp.to_norm(va), sp.to_norm(vb)
        lo, hi = min(na, nb) - margin, max(na, nb) + margin
        if part == "bass" and k in _BASS_NO_MORE:   # never grittier than the curated basses
            hi = max(na, nb)
        if part == "bass" and k == "sub":           # and never less sub
            lo = min(na, nb)
        n = na + (nb - na) * t
        if amount == "MILD":  # stays close to what's playing now
            n = cur_norm.get(key, n) * 0.65 + n * 0.35
        n += rng.uniform(-jit, jit)
        out[key] = min(max(n, lo, 0.0), hi, 1.0)
    return out


# Drum tracks a mutation may swap, per amount (set order: 0 kick 1 clap 2 snare 3 perc 4 hat 5 open 6 rim 7 shaker)
DRUM_SWAP = {"MILD": ((), 0), "MEDIUM": ((1, 3, 4, 5, 6, 7), 2), "WILD": ((0, 1, 2, 3, 4, 5, 6, 7), 4)}


def mutate_drums_plan(amount, rng):
    """Which tracks get a new sound and which just get re-tuned: (swap, tweak)."""
    pool, n = DRUM_SWAP[amount]
    swap = sorted(rng.sample(pool, min(n, len(pool)))) if n else []
    tweak = sorted(rng.sample([t for t in range(8) if t not in swap], 2 if amount == "MILD" else 3))
    return swap, tweak


def drum_tweak(amount, track, rng):
    """(tune in semitones, length 0-1) for a re-tuned drum track: kick and snare move least."""
    span = {"MILD": 1, "MEDIUM": 2, "WILD": 3}[amount]
    if track in (0, 2):
        span = min(span, 1)
    return rng.randint(-span, span), rng.uniform(0.6 if amount != "MILD" else 0.75, 1.0)


# voice
COMMANDS.update({"mutate": ("mutate", "all"), "mutate all": ("mutate", "all"), "mutate bass": ("mutate", "bass"),
                 "mutate lead": ("mutate", "lead"), "mutate melody": ("mutate", "lead"),
                 "mutate drums": ("mutate", "drums"), "go back": ("back", 0), "undo mutate": ("back", 0),
                 "mild": ("amount", "MILD"), "medium": ("amount", "MEDIUM"), "wild": ("amount", "WILD"),
                 "auto mutate": ("auto", 1), "stop mutating": ("auto", 0)})
PHRASES = sorted(COMMANDS)
