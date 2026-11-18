# Manual source

The PotentialBox manual (docs/PotentialBox-Manual.pdf) is built from these files. Knob, pad and genre tables are
read from the app's own code, so they always match the version.

1. `python make_library.py <dir>` makes a small stand-in drum library for the screenshots.
2. `xvfb-run -s "-screen 0 2560x1600x24" python shots.py <img dir>` takes the screenshots (Vintage look, stand-in
   audio and MIDI names, nothing from a real PC). Needs the Barlow fonts in ~/.fonts.
3. `python build.py <repo> <img dir> <out.pdf>` writes the HTML and prints it to PDF with headless Chrome.
