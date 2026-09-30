"""
proc_top.py — Top 12 processus CPU + icônes d'applis pour l'écran 2 du T-Display-S3-Long.

Trames produites (voir README, « Écran 2 — Top processus ») :
    P:h;pct10;nom|h;pct10;nom|...     top 12, %CPU façon top × 10
    I:h;idx;n;<base64>                morceau idx/n d'une icône 32×32 RGB565 big-endian

L'icône d'un processus est celle de son appli (fichier .desktop + thème d'icônes
actif), comme dans le moniteur système GNOME. La résolution et le rendu tournent
dans un thread dédié : la boucle d'envoi ne fait que des lectures de dict.

Linux uniquement (lit /proc). Dépendances : Pillow (icônes), PyGObject/GdkPixbuf (icônes SVG).
"""

import base64
import hashlib
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor


try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, Gio
except (ImportError, ValueError):
    GdkPixbuf = None
    Gio = None


TOP_N        = 12
ICON_W       = 32
ICON_BYTES   = ICON_W * ICON_W * 2            # RGB565
ICON_CHUNKS  = 8
CHUNK_BYTES  = ICON_BYTES // ICON_CHUNKS      # 256 o → ~344 car. base64 par ligne
ICON_BG      = (0x0D, 0x0D, 0x0D)             # CLR_BG de ui.cpp : alpha pré-mélangé
GENERIC_ICON = "application-x-executable"
NAME_MAX     = 15

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "nuc-monitor", "icons")
_HOME      = os.path.expanduser("~")

# Dossiers partagés par beaucoup de programmes : inutilisables pour la
# correspondance « même dossier que l'appli »
_SHARED_DIRS = {"/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin",
                "/usr/games", "/usr/lib", "/usr/libexec", "/snap/bin", ""}


# ── Index des fichiers .desktop ───────────────────────────────────────────────

def _data_dirs() -> list[str]:
    """Dossiers XDG de données, du plus prioritaire au moins prioritaire.
    Le service systemd n'a pas de XDG_DATA_DIRS : on ajoute flatpak/snap en dur."""
    dirs = [os.environ.get("XDG_DATA_HOME") or os.path.join(_HOME, ".local", "share")]
    dirs += (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    dirs += [os.path.join(_HOME, ".local", "share", "flatpak", "exports", "share"),
             "/var/lib/flatpak/exports/share",
             "/var/lib/snapd/desktop"]
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _parse_desktop(path: str) -> dict | None:
    """Clés non localisées de la section [Desktop Entry] (parseur minimal :
    configparser refuse les clés dupliquées présentes dans certains fichiers)."""
    entry, in_main = {}, False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    in_main = line == "[Desktop Entry]"
                elif in_main and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if "[" not in k:
                        entry.setdefault(k, v.strip())
    except OSError:
        return None
    if entry.get("Hidden", "").lower() == "true" or not entry.get("Icon"):
        return None
    return entry


def _exec_target(exec_line: str) -> str:
    """Chemin réel du programme lancé par Exec= (saute `env` et VAR=val)."""
    for tok in exec_line.split():
        tok = tok.strip('"')
        if tok == "env" or ("=" in tok and not tok.startswith("/")):
            continue
        path = tok if os.path.isabs(tok) else shutil.which(tok)
        return os.path.realpath(path) if path else ""
    return ""


class DesktopIndex:
    """Associe un id d'appli ou un nom de processus à l'entrée .desktop."""

    def __init__(self):
        self.by_id:   dict[str, dict] = {}   # id .desktop (minuscules)
        self.by_name: dict[str, dict] = {}   # exe / WMClass / dernier segment de l'id
        self.by_dir:  dict[str, dict] = {}   # dossier privé de l'appli (/opt/brave.com/brave)
        for base in _data_dirs():
            app_dir = os.path.join(base, "applications")
            try:
                files = sorted(os.listdir(app_dir))
            except OSError:
                continue
            for fn in files:
                if not fn.endswith(".desktop"):
                    continue
                entry = _parse_desktop(os.path.join(app_dir, fn))
                if entry is None:
                    continue
                app_id = fn[:-len(".desktop")]
                target = _exec_target(entry.get("Exec", ""))
                entry["_target_dir"] = os.path.dirname(target) if target else ""
                self.by_id.setdefault(app_id.lower(), entry)
                # Les entrées cachées (NoDisplay) ne servent qu'en dernier recours
                visible = entry.get("NoDisplay", "").lower() != "true"
                if visible and entry["_target_dir"] not in _SHARED_DIRS:
                    self.by_dir.setdefault(entry["_target_dir"], entry)
                names = [os.path.basename(target), entry.get("StartupWMClass", ""),
                         app_id, app_id.rsplit(".", 1)[-1]]
                for n in names:
                    n = n.lower()
                    if not n:
                        continue
                    cur = self.by_name.get(n)
                    if cur is None or (visible and cur.get("NoDisplay", "").lower() == "true"):
                        self.by_name[n] = entry


_SCOPE_RE = re.compile(r"^app-(.+?)(?:-[0-9a-f]+\.scope|@[^/]*\.service|\.service)$")


def _cgroup_app_id(pid: int) -> str | None:
    """Id d'appli systemd : app-[<lanceur>-]<id>-<n>.scope, '-' de l'id échappés en \\x2d."""
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            path = f.read().strip().split(":", 2)[-1]
    except OSError:
        return None
    for seg in reversed(path.split("/")):
        m = _SCOPE_RE.match(seg)
        if m:
            app_id = m.group(1).split("-")[-1]
            return re.sub(r"\\x([0-9a-fA-F]{2})", lambda x: chr(int(x.group(1), 16)), app_id)
    return None


# ── Recherche d'une icône dans le thème (sans session graphique) ──────────────

def _icon_theme_name() -> str:
    """Thème actif : GSettings (lu directement dans la base dconf, sans bus),
    puis settings.ini GTK, puis hicolor."""
    try:
        src = Gio.SettingsSchemaSource.get_default() if Gio else None
        if src and src.lookup("org.gnome.desktop.interface", True):
            name = Gio.Settings.new("org.gnome.desktop.interface").get_string("icon-theme")
            if name:
                return name
    except Exception:
        pass
    try:
        with open(os.path.join(_HOME, ".config", "gtk-3.0", "settings.ini")) as f:
            for line in f:
                if line.strip().startswith("gtk-icon-theme-name"):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "hicolor"


def _icon_bases() -> list[str]:
    return [os.path.join(_HOME, ".icons")] + \
           [os.path.join(d, "icons") for d in _data_dirs()]


class IconTheme:
    """Sous-ensemble de la spec freedesktop Icon Theme : thème + Inherits + hicolor."""

    def __init__(self, name: str):
        self.bases  = _icon_bases()
        self.themes = []   # [(racines, [(sous-dossier, taille, scalable)])]
        seen = set()
        todo = [name]
        while todo:
            t = todo.pop(0)
            if t in seen:
                continue
            seen.add(t)
            roots = [os.path.join(b, t) for b in self.bases if os.path.isdir(os.path.join(b, t))]
            dirs, inherits = self._read_index(roots)
            if roots:
                self.themes.append((roots, dirs))
            todo += inherits
            if not todo and "hicolor" not in seen:
                todo.append("hicolor")

    @staticmethod
    def _read_index(roots: list[str]) -> tuple[list, list[str]]:
        for root in roots:
            idx = os.path.join(root, "index.theme")
            if not os.path.isfile(idx):
                continue
            sections, cur = {}, None
            with open(idx, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        cur = sections.setdefault(line[1:-1], {})
                    elif cur is not None and "=" in line:
                        k, v = line.split("=", 1)
                        cur[k.strip()] = v.strip()
            main = sections.get("Icon Theme", {})
            dirs = []
            for d in (main.get("Directories", "") + "," + main.get("ScaledDirectories", "")).split(","):
                d = d.strip()
                info = sections.get(d)
                if not d or info is None or info.get("Scale", "1") != "1":
                    continue
                try:
                    size = int(info.get("Size", "0"))
                except ValueError:
                    continue
                dirs.append((d, size, info.get("Type", "Threshold") == "Scalable"))
            inherits = [i.strip() for i in main.get("Inherits", "").split(",") if i.strip()]
            return dirs, inherits
        return [], []

    @staticmethod
    def _rank(size: int, scalable: bool) -> tuple:
        # 32 exact, puis la plus petite ≥ 32, puis scalable, puis la plus grande < 32
        if size == ICON_W and not scalable:
            return (0, 0)
        if size > ICON_W and not scalable:
            return (1, size)
        if scalable:
            return (2, 0)
        return (3, -size)

    def lookup(self, name: str) -> str | None:
        if os.path.isabs(name):
            return name if os.path.isfile(name) else None
        for roots, dirs in self.themes:
            found = []
            for d, size, scalable in dirs:
                for root in roots:
                    for ext in (".png", ".svg", ".xpm"):
                        p = os.path.join(root, d, name + ext)
                        if os.path.isfile(p):
                            found.append((self._rank(size, scalable), p))
                            break
            if found:
                return min(found)[1]
        for ext in (".png", ".svg", ".xpm"):
            p = os.path.join("/usr/share/pixmaps", name + ext)
            if os.path.isfile(p):
                return p
        return None


# ── Rendu 32×32 RGB565 ────────────────────────────────────────────────────────

def _load_rgba(path: str):
    if GdkPixbuf is not None:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, ICON_W, ICON_W)
        mode = "RGBA" if pb.get_has_alpha() else "RGB"
        img = Image.frombytes(mode, (pb.get_width(), pb.get_height()),
                              pb.get_pixels(), "raw", mode, pb.get_rowstride())
        return img.convert("RGBA")
    if not path.endswith(".png"):
        return None
    img = Image.open(path).convert("RGBA")
    img.thumbnail((ICON_W, ICON_W), Image.LANCZOS)
    return img


def render_icon(path: str) -> bytes | None:
    """Image → 32×32 centrée, alpha mélangé sur le fond de l'écran, RGB565 big-endian
    (LV_COLOR_16_SWAP=1 dans lv_conf.h)."""
    img = _load_rgba(path)
    if img is None:
        return None
    if img.size != (ICON_W, ICON_W):
        img.thumbnail((ICON_W, ICON_W), Image.LANCZOS)
    canvas = Image.new("RGBA", (ICON_W, ICON_W), ICON_BG + (255,))
    layer  = Image.new("RGBA", (ICON_W, ICON_W), (0, 0, 0, 0))
    layer.paste(img, ((ICON_W - img.width) // 2, (ICON_W - img.height) // 2))
    canvas.alpha_composite(layer)
    out = bytearray(ICON_BYTES)
    for i, (r, g, b) in enumerate(canvas.convert("RGB").getdata()):
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[2 * i]     = v >> 8
        out[2 * i + 1] = v & 0xFF
    return bytes(out)


def fnv1a32(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h or 1   # 0 est réservé à « pas d'icône »


# ── Magasin d'icônes (thread worker) ──────────────────────────────────────────

class IconStore:
    """Nom d'icône → hash du rendu. Le rendu est fait une fois, dans un thread
    à part, avec cache disque ; tant qu'il n'est pas prêt, hash_for() renvoie 0."""

    def __init__(self):
        self.enabled  = Image is not None
        self._blobs:  dict[int, bytes] = {}
        self._by_key: dict[str, int]   = {}
        self._pending: set[str]        = set()
        self._lock    = threading.Lock()
        self._theme   = None
        self._pool    = ThreadPoolExecutor(max_workers=1, thread_name_prefix="icons") \
                        if self.enabled else None

    def hash_for(self, key: str) -> int:
        if not self.enabled:
            return 0
        h = self._by_key.get(key)
        if h is not None:
            return h
        with self._lock:
            if key not in self._pending:
                self._pending.add(key)
                self._pool.submit(self._resolve, key)
        return 0

    def blob(self, h: int) -> bytes | None:
        return self._blobs.get(h)

    def _resolve(self, key: str) -> None:
        h = 0
        try:
            if self._theme is None:
                self._theme = IconTheme(_icon_theme_name())
            path = self._theme.lookup(key)
            data = self._cached_render(path) if path else None
            if data is None and key != GENERIC_ICON:
                h = self._by_key.get(GENERIC_ICON) or self._resolve_now(GENERIC_ICON)
            elif data is not None:
                h = fnv1a32(data)
                self._blobs[h] = data
        except Exception as exc:   # une icône illisible ne doit jamais tuer le sender
            print(f"[icônes] {key} : {exc}", flush=True)
        self._by_key[key] = h
        with self._lock:
            self._pending.discard(key)

    def _resolve_now(self, key: str) -> int:
        self._resolve(key)
        return self._by_key.get(key, 0)

    @staticmethod
    def _cached_render(path: str) -> bytes | None:
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            return None
        name = hashlib.sha1(f"{path}\0{mtime}".encode()).hexdigest() + ".bin"
        cache = os.path.join(_CACHE_DIR, name)
        try:
            with open(cache, "rb") as f:
                data = f.read()
            if len(data) == ICON_BYTES:
                return data
        except OSError:
            pass
        data = render_icon(path)
        if data is not None:
            try:
                os.makedirs(_CACHE_DIR, mode=0o700, exist_ok=True)
                tmp = cache + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, cache)
            except OSError:
                pass
        return data


# ── Top processus ─────────────────────────────────────────────────────────────

def _clean_name(name: str) -> str:
    out = "".join(c if " " <= c <= "~" and c not in "|;,:" else "_" for c in name)
    return out[:NAME_MAX] or "?"


def _read_proc_stats() -> dict[tuple[int, int], tuple[int, str]]:
    """{(pid, starttime): (ticks CPU utime+stime, comm)} lus dans /proc/<pid>/stat.
    ~6 ms pour ~480 processus, contre ~20 ms via psutil.process_iter()."""
    out = {}
    for entry in os.scandir("/proc"):
        name = entry.name
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as f:
                raw = f.read()
        except OSError:
            continue   # processus terminé entre-temps
        lpar, rpar = raw.find(b"("), raw.rfind(b")")
        fields = raw[rpar + 2:].split()
        if len(fields) < 20:
            continue
        # champs 14/15 (utime/stime) et 22 (starttime) de proc(5), décalés de 3
        out[(int(name), int(fields[19]))] = (int(fields[11]) + int(fields[12]),
                                             raw[lpar + 1:rpar].decode("ascii", "replace"))
    return out


class ProcTop:
    """Produit la trame P: et les lignes I: d'une icône."""

    def __init__(self):
        self.desktop = DesktopIndex()
        self.icons   = IconStore()
        self._tick_hz = os.sysconf("SC_CLK_TCK")
        self._keys: dict[tuple[int, int], str] = {}   # (pid, starttime) → nom d'icône
        self._prev      = _read_proc_stats()
        self._prev_time = time.monotonic()

    def _icon_key(self, pid: int, name: str, exe: str) -> str:
        app_id = _cgroup_app_id(pid)
        if app_id:
            entry = self.desktop.by_id.get(app_id.lower())
            # Garde-fou : un bash lancé dans le terminal de VS Code partage le cgroup
            # de VS Code mais ne doit pas prendre son icône.
            if entry and exe and (os.path.dirname(exe) == entry["_target_dir"]
                                  or exe.startswith("/app/")):
                return entry["Icon"]
        for cand in (os.path.basename(exe), name):
            entry = self.desktop.by_name.get(cand.lower()) if cand else None
            if entry:
                return entry["Icon"]
        # Helpers d'une appli installée dans son propre dossier (Brave se range dans
        # le scope org.chromium.Chromium, sans .desktop correspondant)
        entry = self.desktop.by_dir.get(os.path.dirname(exe)) if exe else None
        if entry:
            return entry["Icon"]
        return GENERIC_ICON

    def sample(self) -> list[tuple[int, int, str]]:
        """[(hash icône, %CPU×10, nom)] des TOP_N processus, %CPU façon top
        (100 % = un thread saturé) sur l'intervalle depuis l'appel précédent."""
        now, cur = time.monotonic(), _read_proc_stats()
        dt = max(now - self._prev_time, 1e-3)
        scale = 1000.0 / (self._tick_hz * dt)   # ticks → %CPU × 10
        rows = []
        for k, (ticks, comm) in cur.items():
            prev = self._prev.get(k)
            if prev is not None and ticks > prev[0]:
                rows.append(((ticks - prev[0]) * scale, k, comm))
        self._prev, self._prev_time = cur, now
        rows.sort(key=lambda r: r[0], reverse=True)

        out = []
        top_keys = {k for _, k, _ in rows[:TOP_N]}
        for pct10, k, comm in rows[:TOP_N]:
            key = self._keys.get(k)
            if key is None:
                try:
                    exe = os.path.realpath(os.readlink(f"/proc/{k[0]}/exe"))
                except OSError:
                    exe = ""   # thread noyau ou processus d'un autre utilisateur
                key = self._keys[k] = self._icon_key(k[0], comm, exe)
            out.append((self.icons.hash_for(key), int(round(pct10)), _clean_name(comm)))
        # oublie les processus sortis du top (le dict reste petit)
        self._keys = {k: v for k, v in self._keys.items() if k in top_keys}
        return out

    def procs_line(self) -> str:
        return "P:" + "|".join(f"{h:08x};{pct};{name}" for h, pct, name in self.sample())

    def icon_lines(self, h: int) -> list[bytes]:
        data = self.icons.blob(h)
        if data is None:
            return []
        return [f"I:{h:08x};{i};{ICON_CHUNKS};".encode("ascii")
                + base64.b64encode(data[i * CHUNK_BYTES:(i + 1) * CHUNK_BYTES]) + b"\n"
                for i in range(ICON_CHUNKS)]
