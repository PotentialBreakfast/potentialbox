"""Voice control: Windows' own offline speech recognition (System.Speech), run by PowerShell.

It only listens for a fixed list of phrases ("project seven", "acid", "next project" ...), which keeps it
reliable without any extra download or internet. Lines come back on stdout:
    READY                 listening
    HEARD:<text>|<conf>   a phrase was recognised (confidence 0..1)
    ERR:<message>         it could not start (no microphone, no recogniser for the language)
"""
import base64
import queue
import subprocess
import sys
import threading

MIN_CONFIDENCE = 0.55

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName System.Speech
  $infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
  if ($infos.Count -eq 0) { [Console]::Out.WriteLine('ERR:NO_RECOGNIZER'); [Console]::Out.Flush(); exit 1 }
  $pick = $infos | Where-Object { $_.Culture.Name -eq 'en-GB' } | Select-Object -First 1
  if (-not $pick) { $pick = $infos | Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1 }
  if (-not $pick) { $pick = $infos[0] }
  $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine($pick)
  $ch = New-Object System.Speech.Recognition.Choices
  foreach ($p in @(__PHRASES__)) { [void]$ch.Add($p) }
  $gb = New-Object System.Speech.Recognition.GrammarBuilder
  $gb.Culture = $pick.Culture
  $gb.Append($ch)
  $rec.LoadGrammar((New-Object System.Speech.Recognition.Grammar($gb)))
  $rec.SetInputToDefaultAudioDevice()
  [Console]::Out.WriteLine('READY'); [Console]::Out.Flush()
  while ($true) {
    $r = $rec.Recognize([TimeSpan]::FromSeconds(4))
    if ($r -ne $null) {
      $c = $r.Confidence.ToString([System.Globalization.CultureInfo]::InvariantCulture)
      [Console]::Out.WriteLine('HEARD:' + $r.Text + '|' + $c); [Console]::Out.Flush()
    }
  }
} catch {
  [Console]::Out.WriteLine('ERR:' + $_.Exception.Message); [Console]::Out.Flush(); exit 1
}
"""


def build_script(phrases):
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in phrases)
    return _SCRIPT.replace("__PHRASES__", quoted)


def encoded(script):
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


class Voice:
    """One PowerShell listener. poll() returns ("ready",), ("heard", text, conf), ("error", msg) or ("ended",)."""

    def __init__(self, phrases):
        self.phrases = list(phrases)
        self.proc = None
        self.q = queue.Queue()
        self.state = "off"      # off / starting / listening / error
        self.error = ""

    @staticmethod
    def available():
        return sys.platform == "win32"

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        if not self.available():
            self.state, self.error = "error", "Voice needs Windows"
            self.q.put(("error", self.error))
            return
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-EncodedCommand", encoded(build_script(self.phrases))],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                creationflags=flags, text=True, encoding="utf-8", errors="replace")
        except Exception as e:
            self.state, self.error = "error", str(e)
            self.q.put(("error", self.error))
            return
        self.state = "starting"
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        try:
            for line in proc.stdout:
                line = line.strip()
                if line == "READY":
                    self.q.put(("ready",))
                elif line.startswith("HEARD:"):
                    text, _, conf = line[6:].rpartition("|")
                    try:
                        c = float(conf)
                    except ValueError:
                        c = 0.0
                    self.q.put(("heard", text, c))
                elif line.startswith("ERR:"):
                    self.q.put(("error", line[4:]))
        except Exception:
            pass
        self.q.put(("ended",))

    def stop(self):
        p, self.proc = self.proc, None
        self.state = "off"
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def poll(self):
        out = []
        while True:
            try:
                ev = self.q.get_nowait()
            except queue.Empty:
                return out
            if ev[0] == "ready":
                self.state = "listening"
            elif ev[0] == "error":
                self.state, self.error = "error", ev[1]
            elif ev[0] == "ended" and self.state != "error":
                if self.proc is None:
                    continue           # we stopped it ourselves
                self.state = "error"
                self.error = self.error or "The listener stopped"
            out.append(ev)


def friendly_error(msg):
    m = (msg or "").lower()
    if "no_recognizer" in m or "recognizer" in m and "not" in m:
        return "WINDOWS SPEECH RECOGNITION ISN'T INSTALLED: SETTINGS > TIME & LANGUAGE > SPEECH"
    if "audio" in m or "device" in m or "microphone" in m:
        return "NO MICROPHONE FOUND: PLUG ONE IN OR PICK A DEFAULT MIC IN WINDOWS SOUND SETTINGS"
    if "windows" in m:
        return "VOICE ONLY WORKS ON WINDOWS"
    return ("VOICE COULD NOT START: " + (msg or "")).upper()[:90]
