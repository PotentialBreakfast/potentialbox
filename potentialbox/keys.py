"""v2.4: guess the key of a loop from the notes the synths played in it (Krumhansl-Kessler key profiles), so
bounces can be named like "Acid 126bpm Am 4bar 03". Says nothing when it can't tell."""
import numpy as np

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def name(root, minor):
    """"Am", "F#m", "Bb", ... spelled the way the key is written (flats for F, Bb, Eb ... major and D, G, C ... minor)."""
    from potentialbox.parts import short_key
    return short_key(root, minor)


def profile(notes, start, end):
    """Pitch-class weights: how long each one sounded inside [start, end). notes = [(on, off_or_None, note), ...]
    in samples; a note still held counts up to `end`. Low notes count a bit more (the bass sets the key)."""
    w = np.zeros(12)
    for on, off, nt in notes:
        off = end if off is None else off
        a, b = max(on, start), min(off, end)
        if b <= a:
            continue
        w[nt % 12] += (b - a) * (1.0 + 0.5 * (nt < 48))
    return w


def estimate(weights, min_classes=3, min_corr=0.6):
    """(root, minor, corr) for the best-fitting key, or None if there isn't enough to go on or nothing fits well."""
    w = np.asarray(weights, float)
    if np.count_nonzero(w > w.sum() * 0.02) < min_classes or w.sum() <= 0:
        return None
    best = None
    for minor, prof in ((False, _MAJ), (True, _MIN)):
        for r in range(12):
            c = np.corrcoef(w, np.roll(prof, r))[0, 1]
            if best is None or c > best[2]:
                best = (r, minor, c)
    return best if best[2] >= min_corr else None


def key_of(notes, start, end):
    """"Am", "F#", ... or "" when it can't tell."""
    k = estimate(profile(notes, start, end))
    return name(k[0], k[1]) if k else ""
