"""GET MPC ONE-SHOTS: copy the MPC's "DRUM ONE SHOTS" folder (made by MPC TOOLS, sorted into Kicks, Snares, Claps,
Hats, Cymbals, Toms and Percs) to this PC, over SSH.

It uses Windows' own OpenSSH client and the same key login MPC TOOLS sets up (no password prompts), and the MPC's
address from MPC TOOLS' settings (%AppData%\\MPC TOOLS\\settings.ini: host=, user=, ssh=). Only files that aren't
on the PC yet are copied, a batch at a time with tar, and each file is written under a temporary name first, so a
dropped connection never leaves half a sample behind.
"""
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import threading

FOLDER = "DRUM ONE SHOTS"
WANT_EXT = (".wav", ".aif", ".aiff")
OTHER_EXT = (".flac", ".mp3")
BATCH = 120


class SyncError(Exception):
    pass


def mpc_tools_settings():
    """host / user / ssh from MPC TOOLS' settings, if it's installed."""
    out = {}
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    for p in (os.path.join(base, "MPC TOOLS", "settings.ini"),):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "=" in line and not line.lstrip().startswith(("#", ";")):
                        k, v = line.split("=", 1)
                        k = k.strip().lower()
                        if k == "ip":
                            k = "host"
                        if k in ("host", "user", "ssh") and v.strip():
                            out[k] = v.strip()
        except OSError:
            pass
    return out


def find_ssh(pref=None):
    if pref and os.path.isfile(pref):
        return pref
    w = shutil.which("ssh")
    if w:
        return w
    if sys.platform == "win32":
        p = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
        if os.path.isfile(p):
            return p
    return None


def shq(s):
    return "'" + s.replace("'", "'\\''") + "'"


LIST_SCRIPT = r"""
for d in /media/*/"DRUM ONE SHOTS" "/SDMPC/DRUM ONE SHOTS" /sdcard/"DRUM ONE SHOTS"; do
  if [ -d "$d" ]; then
    echo "D|$d"
    cd "$d" || exit 3
    command -v tar >/dev/null 2>&1 && echo "T|1"
    echo "L|"
    find . -type f
    exit 0
  fi
done
echo "NONE"
"""


class MpcSync:
    """Run with run(); progress goes to self.status / self.done / self.total (read them from the screen thread)."""

    def __init__(self, dest, host=None, user=None, ssh=None, runner=None):
        cfg = mpc_tools_settings()
        self.host = host or cfg.get("host")
        self.user = user or cfg.get("user") or "root"
        self.ssh = ssh or find_ssh(cfg.get("ssh"))
        self.dest = dest
        self.runner = runner      # tests: a function(script_bytes) -> Popen-like, instead of ssh
        self.status = ""
        self.done = 0
        self.total = 0
        self.copied = 0
        self.skipped_other = 0
        self.busy = False
        self.error = None
        self.cancel = False

    # ---------------------------------------------------------------- ssh
    def _popen(self, script, err=True):
        if self.runner:
            return self.runner(script)
        if not self.ssh:
            raise SyncError("Windows' SSH client isn't installed (Settings > Apps > Optional features > OpenSSH Client).")
        if not self.host:
            raise SyncError("I don't know your MPC's address. Open MPC TOOLS once (it saves it), or type it in.")
        args = [self.ssh, "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                f"{self.user}@{self.host}", "sh -s"]
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE if err else subprocess.DEVNULL, creationflags=flags)
        p.stdin.write(script.replace("\r", "").encode("utf-8"))
        p.stdin.close()
        return p

    def _run_text(self, script, timeout=120):
        p = self._popen(script)
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        try:
            errbuf = []
            t = threading.Thread(target=lambda: errbuf.append(p.stderr.read() if p.stderr else b""), daemon=True)
            t.start()
            out = p.stdout.read()
            t.join(5)
            err = errbuf[0] if errbuf else b""
            p.wait()
        finally:
            timed_out = not timer.is_alive() and p.returncode not in (0, None) and not out
            timer.cancel()
        if timed_out:
            raise SyncError("The MPC took too long to answer.")
        if p.returncode not in (0, None) and not out:
            msg = (err or b"").decode("utf-8", "replace").strip()
            if "denied" in msg.lower() or "password" in msg.lower():
                raise SyncError("The MPC wants a password. Set up MPC TOOLS' SSH login first, then try again.")
            raise SyncError("The MPC didn't answer. Is it on and on the same network? " + msg[-160:])
        return out.decode("utf-8", "replace")

    # ---------------------------------------------------------------- the copy
    def remote_list(self):
        out = self._run_text(LIST_SCRIPT)
        rdir, files, has_tar, listing = None, [], False, False
        for line in out.splitlines():
            if listing:
                if line.startswith("./"):
                    rel = line[2:]
                    if not any(p.startswith(".") for p in rel.split("/")):
                        files.append(rel)
            elif line.startswith("D|"):
                rdir = line[2:]
            elif line.startswith("T|"):
                has_tar = True
            elif line.startswith("L|"):
                listing = True
        if not rdir:
            raise SyncError("There's no DRUM ONE SHOTS folder on the MPC yet. Make it with MPC TOOLS "
                            "(Plugins tab > DRUM ONE SHOTS), then try again.")
        return rdir, files, has_tar

    def missing(self, files):
        want, other = [], 0
        for rel in files:
            if not rel.lower().endswith(WANT_EXT):
                other += rel.lower().endswith(OTHER_EXT)
                continue
            if ".." in rel.split("/"):
                continue
            local = self._safe_local(rel)
            if local and not os.path.isfile(local):
                want.append(rel)
        return want, other

    def _safe_local(self, name):
        name = name[2:] if name.startswith("./") else name
        parts = [p for p in name.split("/") if p not in ("", ".")]
        if not parts or ".." in parts or posixpath.isabs(name):
            return None
        # names Windows can't hold (: ? * " < > | and trailing dots or spaces) get those characters swapped for _
        parts = [re.sub(r'[<>:"\\|?*\x00-\x1f]', "_", p).rstrip(" .") or "_" for p in parts]
        return os.path.join(self.dest, *parts)

    def fetch(self, rdir, rels, has_tar=True):
        for i in range(0, len(rels), BATCH):
            if self.cancel:
                return
            chunk = rels[i:i + BATCH]
            if has_tar:
                script = "cd " + shq(rdir) + " && exec tar cf - " + " ".join(shq("./" + r) for r in chunk) + "\n"
                p = self._popen(script, err=False)
                try:
                    with tarfile.open(fileobj=p.stdout, mode="r|") as tf:
                        for m in tf:
                            if self.cancel:
                                break
                            if not m.isfile():
                                continue
                            local = self._safe_local(m.name)
                            if not local:
                                continue
                            try:
                                self._write(local, tf.extractfile(m))
                            except OSError:
                                continue
                            self.done += 1
                            self.copied += 1
                            self.status = f"Copying {self.done} of {self.total}"
                finally:
                    try:
                        p.stdout.close()
                    except Exception:
                        pass
                    p.wait()
            else:  # no tar on the MPC: one file at a time
                for r in chunk:
                    if self.cancel:
                        return
                    p = self._popen("exec cat " + shq(rdir + "/" + r) + "\n", err=False)
                    local = self._safe_local(r)
                    if local:
                        try:
                            self._write(local, p.stdout)
                        except OSError:
                            pass
                    p.wait()
                    self.done += 1
                    self.copied += 1
                    self.status = f"Copying {self.done} of {self.total}"

    def _write(self, local, src):
        os.makedirs(os.path.dirname(local), exist_ok=True)
        tmp = local + ".part"
        with open(tmp, "wb") as f:
            shutil.copyfileobj(src, f, 1 << 16)
        if os.path.getsize(tmp) == 0:
            os.remove(tmp)
            return
        os.replace(tmp, local)

    def run(self):
        self.busy, self.error, self.done, self.total, self.copied = True, None, 0, 0, 0
        try:
            self.status = "Asking the MPC what it has..."
            rdir, files, has_tar = self.remote_list()
            want, self.skipped_other = self.missing(files)
            self.total = len(want)
            if not want:
                self.status = f"Up to date: all {len(files) - self.skipped_other} one-shots are on this PC."
                return 0
            self.status = f"Copying {len(want)} new one-shots..."
            self.fetch(rdir, want, has_tar)
            self.status = f"Copied {self.copied} new one-shots." if not self.cancel else "Stopped."
            return self.copied
        except SyncError as e:
            self.error = str(e)
            self.status = self.error
        except Exception as e:  # noqa: BLE001
            self.error = f"Copy failed: {e}"
            self.status = self.error
        finally:
            self.busy = False
        return self.copied


# ----------------------------------------------------------------------------- v2.0: send loops to the MPC
SEND_FOLDER = "PotentialBox Loops"
ROOT_SCRIPT = r"""
pick=""
for d in /media/* /SDMPC /sdcard; do
  [ -d "$d" ] || continue
  case "$d" in *nternal*|*az01*) continue;; esac
  if [ -d "$d/DRUM ONE SHOTS" ] || [ -d "$d/MYMPC" ] || [ -d "$d/PotentialBox Loops" ]; then echo "R|$d"; exit 0; fi
  [ -z "$pick" ] && [ -w "$d" ] && pick="$d"
done
if [ -n "$pick" ]; then echo "R|$pick"; exit 0; fi
echo "NONE"
"""


class MpcSend(MpcSync):
    """Copy a folder of WAVs (one bounce) to <SD card>/PotentialBox Loops/<folder name>/ on the MPC, over SSH.
    The SD card is the drive that has MPC TOOLS' DRUM ONE SHOTS or a MYMPC folder (else the first one you can
    write to). Run with send(folder); progress in self.status like MpcSync."""

    def find_root(self):
        out = self._run_text(ROOT_SCRIPT, timeout=40)
        for line in out.splitlines():
            if line.startswith("R|"):
                return line[2:].strip()
        raise SyncError("No SD card or USB drive found on the MPC. Put one in and try again.")

    def _upload(self, remote_dir, files):
        """files: [(name, local path)]. One tar stream if the MPC has tar, else one file at a time."""
        q = shq(remote_dir)
        script = f"mkdir -p {q} && cd {q} && exec tar xf -\n"
        if self.runner:
            p = self.runner(script)
        else:
            if not self.ssh:
                raise SyncError("Windows' SSH client isn't installed (Settings > Apps > Optional features > OpenSSH Client).")
            if not self.host:
                raise SyncError("I don't know your MPC's address. Open MPC TOOLS once (it saves it), or type it in.")
            args = [self.ssh, "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                    f"{self.user}@{self.host}", script.strip()]
            flags = 0x08000000 if sys.platform == "win32" else 0
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 creationflags=flags)
        try:
            with tarfile.open(fileobj=p.stdin, mode="w|", format=tarfile.USTAR_FORMAT) as tf:
                for name, local in files:
                    if self.cancel:
                        break
                    tf.add(local, arcname=name)
                    self.done += 1
                    self.status = f"Sending {self.done} of {self.total}"
        finally:
            try:
                p.stdin.close()
            except Exception:
                pass
        err = b""
        try:
            err = p.stderr.read() if getattr(p, "stderr", None) else b""
        except Exception:
            pass
        p.wait()
        if p.returncode not in (0, None):
            msg = (err or b"").decode("utf-8", "replace").strip()
            if "denied" in msg.lower() or "password" in msg.lower():
                raise SyncError("The MPC wants a password. Set up MPC TOOLS' SSH login first, then try again.")
            raise SyncError("The MPC didn't take the files. " + msg[-160:])

    def send(self, folder):
        self.busy, self.error, self.done, self.total, self.copied = True, None, 0, 0, 0
        try:
            files = [(fn, os.path.join(folder, fn)) for fn in sorted(os.listdir(folder))
                     if fn.lower().endswith(".wav") and os.path.isfile(os.path.join(folder, fn))]
            if not files:
                raise SyncError("That bounce has no WAV files.")
            self.total = len(files)
            self.status = "Finding the MPC's SD card..."
            root = self.find_root()
            name = re.sub(r'[\\/:*?"<>|]', "_", os.path.basename(os.path.normpath(folder)))
            self.remote = posixpath.join(root, SEND_FOLDER, name)
            self.status = f"Sending {len(files)} files..."
            self._upload(self.remote, files)
            self.copied = self.done
            self.status = (f"On the MPC: {posixpath.basename(root)} > {SEND_FOLDER} > {name}"
                           if not self.cancel else "Stopped.")
            return self.copied
        except SyncError as e:
            self.error = str(e)
            self.status = self.error
        except Exception as e:  # noqa: BLE001
            self.error = f"Send failed: {e}"
            self.status = self.error
        finally:
            self.busy = False
        return self.copied
