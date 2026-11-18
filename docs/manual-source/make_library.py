"""A small stand-in drum machine collection for the manual's screenshots (sounds come from the built-in kits)."""
import os, sys, wave
import numpy as np
sys.path.insert(0, "/home/claude/potentialbox")
from potentialbox import kits
root = sys.argv[1]
machines = ["Roland TR-808", "Roland TR-909", "Roland TR-606", "Roland CR-78", "Roland TR-707", "Linn LinnDrum",
            "Linn LM-1", "Linn 9000", "E-mu SP-1200", "E-mu Drumulator", "E-mu SP-12", "Oberheim DMX", "Korg KR-55",
            "Korg DDM-110", "Korg Minipops", "Yamaha RX5", "Yamaha RX11", "Yamaha RY30", "Boss DR-55", "Simmons SDS-V",
            "Casio RZ-1", "Alesis HR-16", "Sequential Circuits Drumtraks", "Sequential Circuits TOM"]
names = ["BD01", "BD02", "SD01", "CP01", "CH01", "OH01", "LT01", "MT01", "HT01", "RS01", "CB01", "CL01", "MA01", "CY01", "FX01", "CG01"]
def write(path, x, sr):
    x = np.clip(x[: int(sr * 0.6)], -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32000).astype("<i2").tobytes())
for i, m in enumerate(machines):
    _, smp = kits.build(i % len(kits.KITS), 22050)
    d = os.path.join(root, m); os.makedirs(d, exist_ok=True)
    for j, nm in enumerate(names):
        write(os.path.join(d, f"{m.split()[-1]} {nm}.wav"), np.asarray(smp[j], float), 22050)
    if i < 6:
        for k in ("Kit 2", "Kit 3"):
            dk = os.path.join(d, k); os.makedirs(dk, exist_ok=True)
            for j, nm in enumerate(names):
                write(os.path.join(dk, f"{nm}.wav"), np.asarray(smp[(j + 3) % 16], float), 22050)
print("ok", len(machines))
