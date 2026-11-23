"""What each knob does, in plain words, for the manual's knob tables. Keys are parameter keys; synth keys are
written once without their s1./s2. prefix (SYN) and can be overridden per synth."""

SYN = {
    "cutoff": "How bright the sound is. Low = dark and muffled, high = open and bright.",
    "reso": "Boosts the frequencies around the cutoff. High settings squelch and whistle.",
    "envamt": "How far each note opens the filter. The heart of acid and pluck sounds.",
    "fdecay": "How quickly the filter closes again after each note.",
    "wave": "Blends the oscillator from a saw wave (buzzy) to a square wave (hollow).",
    "pw": "Shape of the square wave. 50% is hollow, small values are thin and nasal.",
    "detune": "Detunes the second oscillator (Synth 2: the unison voices) for a thicker sound.",
    "sub": "Adds a sine wave one octave down for weight.",
    "attack": "How long the note takes to fade in.",
    "decay": "How long the note takes to fall to the sustain level. Also sets how fast the filter envelope closes.",
    "sustain": "The level the note holds at while the step is held.",
    "release": "How long the note rings after the step ends.",
    "decay2": "Multi-stage envelope. 0 = off. Above 0, after Decay the level moves on to Sustain 2 over this time.",
    "sustain2": "The level the note settles at after Decay 2 (only when Decay 2 is above 0).",
    "glide": "Slide time between notes on tied or slid BeatStep steps.",
    "octave": "Moves the synth up or down in octaves.",
    "drive": "Saturation after the filter: warmth at low settings, grit at high.",
    "vol": "The synth's level in the mix.",
    "osc2": "Tunes oscillator 2 in semitones (+7 = a fifth, +12 = an octave). With Hard sync on, it sets the sync tone.",
    "fm": "Oscillator 2 bends oscillator 1's waveform: metallic, bell-like and growly tones.",
    "ring": "Multiplies the two oscillators together: clangy, bell-like tones.",
    "sync": "Locks oscillator 2 to oscillator 1. Sweep Osc 2 pitch (or modulate it) for the classic sync scream. Tap to switch.",
    "noise": "Adds white noise before the filter.",
    "chord": "Plays a chord on every step, even though the BeatStep sequences are one note at a time.",
    "voicing": "Close, Open (the middle note goes up an octave) or Wide (spread further).",
    "pan": "Places the synth left or right in the mix.",
    "ftype": "LP 24 (smooth), LP 12 (brighter), HP 12 (thin), Band-pass (nasal), Notch (hollow), Comb (metallic, tuned "
             "by the cutoff) or Formant (vowels: the cutoff sweeps A, E, I, O, U).",
    "keytrk": "Higher notes open the filter more, like an acoustic instrument.",
    "velamp": "How much step velocity changes the volume. 0% makes every step the same level.",
    "drift": "Slow random detuning of each voice, like an old analog synth.",
    "penv": "A quick pitch drop or rise at the start of each note, in semitones. Great for zaps and kicks.",
    "pdec": "How quickly the pitch envelope settles.",
    "glmode": "Slides only: glide on tied or slid steps. Always: every new note glides from the last one. Tap to switch.",
    "supersaw": "Blends oscillator 1 into a stack of 7 detuned saws. More = wider, bigger and brighter.",
    "l1shape": "Sine, Triangle, Saw up, Saw down, Square, Random, Smooth random, or Step (plays the LFO 1 step knobs).",
    "l2shape": "Sine, Triangle, Saw up, Saw down, Square, Random, Smooth random, or Step (plays the LFO 2 step knobs).",
    "l1rate": "Speed in Hz when LFO 1 sync is Free (shows Synced otherwise).",
    "l2rate": "Speed in Hz when LFO 2 sync is Free (shows Synced otherwise).",
    "l1sync": "Free, or locked to the tempo: 4 bars down to 1/32, plus triplets.",
    "l2sync": "Free, or locked to the tempo: 4 bars down to 1/32, plus triplets.",
    "mea": "How long the mod envelope takes to rise. It restarts on every new note.",
    "med": "How long the mod envelope takes to fall back to zero.",
    "arp": "Off, Up, Down, Up-down, Random or As played (the order the notes arrived).",
    "arprate": "How fast it plays, locked to the tempo: 1/4, 1/8, 1/8T, 1/16, 1/16T, 1/32.",
    "arpoct": "Plays the notes over 1 to 4 octaves.",
    "arpgate": "How long each arp note lasts. At 100% the notes slide into each other.",
    "arpswing": "Pushes every second arp note later for a shuffle.",
    "arphold": "On: the arp keeps playing after the BeatStep's note ends, until the next new note. Tap to switch.",
    "arpchance": "Below 100%, some arp notes are skipped at random.",
    "arpacc": "Makes every 2nd, 3rd or 4th arp note louder and the others softer.",
    "mute": "Silences the synth. It keeps running in time, so it comes back exactly in place. Tap to switch.",
    "solo": "Solo: while any track is soloed, only soloed tracks play. Tap to switch.",
    # Synth 2
    "pos": "Where in the wavetable you are. Each table morphs as you turn this.",
    "posenv": "How much each note moves the wave position (up or down).",
    "lforate": "Speed of the LFO that sweeps the wave position.",
    "lfoamt": "How far that LFO moves the wave position.",
    "table": "Chooses the wavetable: 30 built in (list below), plus any you add yourself.",
}
# v1.12-2.0 settings
SYN.update({
    "uni": "How many copies of the sound play at once (1-7), detuned and spread across the stereo field.",
    "unidet": "How far apart the unison voices are tuned. A little = thick, a lot = a reese or hoover.",
    "uniwid": "How wide the unison voices spread across the stereo field. 0 = all in the middle.",
    "fdrive": "Pushes the sound into the filter for an overdriven analog filter's grit and weight.",
    "dist": "Distortion type: Tube, Tape, Fold (wavefolder), Crush (bits and sample rate) or Hard clip.",
    "distamt": "How much distortion. Level-matched, so it adds grit rather than volume.",
    "sfx": "This synth's own effect: Chorus, Ensemble, Dimension, Phaser or Flanger.",
    "sfxamt": "How much of the synth's own effect.",
    "subtype": "Where the sub sits: an octave down through the filter, an octave down kept clean, or a clean sine at "
               "the note itself (a deep, solid sub that skips the filter and distortion).",
    "hkey": "The key the Scale chords are built in (C to B).",
    "hscale": "The scale the Scale chords are built from: Minor, Major, Dorian, Phrygian, Mixolydian or Harmonic minor.",
    "lane": "On: BeatStep drum tracks 9-15 pick the chord (track 9 = chord I ... track 15 = chord VII) instead of "
            "playing drums.",
    "trim": "This sound's own level, set by each preset so sounds play at the same loudness. Your volume knob stays "
            "where it is.",
})
SYN_OVERRIDE = {
    "s2.detune": "Unison detune: how far apart the unison voices are tuned. More = wider and thicker.",
    "s2.warp": "Reshapes how the wave is read: Bend +/-, Mirror, Sync, Squeeze, Phase FM or Quantize.",
    "s2.warpamt": "How far the warp goes.",
    "s2.envamt": "How far each note opens the filter (Synth 2 uses the amp envelope's decay for it).",
}
for j in range(1, 13):
    SYN[f"m{j}amt"] = (f"Amount for mod slot {j}. The label shows its routing; tap the label to change it. "
                       "Negative turns the movement upside down.")

KEY = {
    # mix and buses
    "dr.vol": "The drums' level in the mix.",
    "dr.filter": "A filter on the whole drum bus: down = darker.",
    "dr.drive": "Saturation on the drum bus: punch at low settings, crunch at high.",
    "dr.comp": "Parallel compression on the drum bus: thicker and punchier.",
    "dr.room": "A short room on the whole kit.",
    "dr.roomsize": "How big the drum room is.",
    "dr.width": "How far hats, toms and percussion spread left and right.",
    "dr.tone": "Darker to the left, brighter to the right.",
    "dr.crush": "Fewer bits and a lower sample rate on the drum bus (SP-1200 style crunch).",
    "dr.kittune": "Tunes every drum pad up or down at once.",
    "m.master": "The final output level.",
    "m.drive": "Drives the whole mix into a warm saturator.",
    "m.filter": "DJ filter on the whole mix. Centre is off, left is low-pass, right is high-pass.",
    "m.crush": "Lowers the sample rate and bit depth of the whole mix.",
    "m.glue": "One-knob bus compressor on the whole mix: more squeeze, with the level made up for you.",
    "m.gluespd": "How fast the glue compressor reacts: Fast, Medium or Slow.",
    "m.width": "Stereo width: 100% is normal, 0% is mono, up to 200% is extra wide.",
    "m.chorus": "Stereo chorus on the whole mix: two swept voices per side. More = deeper and faster.",
    "m.flanger": "Jet-plane flanger on the whole mix, with feedback.",
    "m.phaser": "A 4-stage phaser sweeping from 200 Hz to 3 kHz.",
    "m.distortion": "Distortion on the whole mix. It fades in from zero, so turning it up never jumps.",
    "m.limiter": "Look-ahead limiter at the very end: pushes the mix up to +12 dB louder but never over the ceiling.",
    "m.compressor": "Master compressor: more = lower threshold and higher ratio, with make-up gain.",
    "dk.s1": "Side-chain duck: Synth 1 dips each time the trigger pad plays. 0% is off.",
    "dk.s2": "Side-chain duck for Synth 2.",
    "dk.fx": "Side-chain duck for the delay and reverb returns.",
    "dk.src": "Which pad triggers the duck (pad 1, the kick, out of the box), or Every beat.",
    "dk.rel": "How quickly the ducked sound comes back: short for a tight bounce, long for big pumping.",
    "eq.lof": "Where the low shelf of all four EQs starts.",
    "eq.hif": "Where the high shelf of all four EQs starts.",
    "dr.mute": "Silences the drums (they keep running in time). Tap to switch.",
    "dr.solo": "Solo the drums. Tap to switch.",
    # FX
    "fx.s1": "Delay send from Synth 1.", "fx.s2": "Delay send from Synth 2.", "fx.dr": "Delay send from the drums.",
    "fx.time": "Delay time, locked to the tempo: 1/16, 1/8T, 1/8, 3/16, 1/4, 3/8.",
    "fx.fb": "How many times the delay repeats.",
    "fx.tone": "Delay tone: lower = darker, dubbier repeats.",
    "rv.s1": "Reverb send from Synth 1.", "rv.s2": "Reverb send from Synth 2.", "rv.dr": "Reverb send from the drums.",
    "rv.size": "How big the room is and how long the reverb rings.",
    "rv.tone": "Reverb tone: lower = darker.",
    "rv.level": "Level of the reverb return.",
    # beats
    "bt.busy": "Makes the ? hits more or less likely and thins the extras out as they play.",
    "bt.var": "Adds the odd extra hit (a ghost snare, a hat roll) now and then.",
    "bt.swing": "Genre = the genre's own swing; turn it up for your own.",
    "bt.human": "Loosens timing and velocity a little, like a drummer.",
    # live
    "sc.morph": "Blends from the FROM scene to the TO scene. Only settings that differ move.",
    # looper
    "lp.in": "How loud the interface input is recorded. Watch the meter under the INPUT button.",
    "lp.mon": "How loud you hear the input live. Turn it down if your interface already lets you hear it.",
    "lp.vol": "Level of all the loops together.",
    "lp.fb": "How much of the old loop stays each time round while overdubbing. Below 100% older layers fade.",
    "lp.filter": "DJ filter on all the loops: left low-pass, right high-pass.",
    "lp.duck": "The loops dip when the kick plays, using the side-chain settings on the Mix tab.",
}
for t in range(1, 6):
    KEY[f"lp.t{t}.vol"] = f"Track {t}'s level."
    KEY[f"lp.t{t}.fx"] = f"Amount of track {t}'s effect (0% = off)."
for band, lab in (("lo", "Low shelf"), ("mid", "Mid band around 1 kHz"), ("hi", "High shelf")):
    for k, who in (("s1", "Synth 1"), ("s2", "Synth 2"), ("dr", "the drums"), ("m", "the master")):
        KEY[f"eq.{k}.{band}"] = f"{lab} for {who}, -12 to +12 dB."


def describe(key, macros=None):
    if key in SYN_OVERRIDE:
        return SYN_OVERRIDE[key]
    if key in KEY:
        return KEY[key]
    if key[:3] in ("s1.", "s2.") and key[3:] in SYN:
        return SYN[key[3:]]
    if key.startswith("dr.p"):
        what = key.split(".")[2]
        return {"tune": "Tunes the pad in semitones.", "decay": "Shortens the pad's sound.", "level": "The pad's level.",
                "pan": "Places the pad left or right.", "chance": "How often the pad plays.",
                "cond": "Which bars the pad plays in.", "choke": "The pad's choke group."}[what]
    if key.startswith("mc.") and macros:
        return macros[int(key[3:]) - 1][1]
    raise KeyError(key)
