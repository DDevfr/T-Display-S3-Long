#!/usr/bin/env python3
"""
monitor_sender.py — Envoie les métriques système au T-Display-S3-Long (ESP32-S3).

Métriques envoyées :
  CPU global, température CPU (k10temp/Tctl), usage GPU (Radeon 780M),
  température GPU (amdgpu/edge), RAM %, 16 threads CPU individuels.
  + top 12 processus et leurs icônes pour l'écran 2 (voir proc_top.py).

Dépendances :
    pip install psutil pyserial
    Pillow (python3-pil) pour les icônes de l'écran 2 — optionnel

Usage :
    python monitor_sender.py                      # auto-détecte /dev/ttyACM*
    python monitor_sender.py --port /dev/ttyACM0
    python monitor_sender.py --port /dev/ttyACM0 --interval 0.5
"""

import argparse
import glob
import platform
import re
import subprocess
import time
import sys
import os
import termios
import fcntl

try:
    import dbus  # optionnel : santé SMART SSD1 via UDisks2 (voir get_ssd_health)
except ImportError:
    dbus = None

try:
    import psutil
except ImportError:
    sys.exit("Installez psutil :  pip install psutil")

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.exit("Installez pyserial :  pip install pyserial")

from proc_top import ProcTop


# Limite d'une ligne : buf[] de serial_parser = 512 octets (le buffer RX HWCDC,
# lui, fait 4096 octets). On garde 2 octets de marge (\0 + sécurité).
_SERIAL_MAX = 510

# ── Chemins sysfs détectés au démarrage ───────────────────────────────────────

def _find_sysfs(pattern: str) -> str | None:
    matches = glob.glob(pattern)
    return matches[0] if matches else None

_GPU_BUSY_PATH  = _find_sysfs("/sys/class/drm/card*/device/gpu_busy_percent")
_GPU_TEMP_PATH  = _find_sysfs("/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input")
_VRAM_USED_PATH = _find_sysfs("/sys/class/drm/card*/device/mem_info_vram_used")
_VRAM_TOTAL_PATH= _find_sysfs("/sys/class/drm/card*/device/mem_info_vram_total")

_UPDATES_PATH   = '/var/lib/update-notifier/updates-available'

# ── Détection disques SSD (au démarrage) ─────────────────────────────────────
_disk_prev      = {}   # {devname: SDiskIOCounters}
_disk_prev_time = None
_SSD_DEVICES    = []   # ['nvme0n1', 'sda'] — jusqu'à 2 devices
_SSD_TEMP_PATHS = []   # [path|None, ...]
_SSD_MOUNTS     = []   # ['/', '/media/...']

_NET_IFACE      = ''        # interface WiFi active (ex: 'wlp2s0')
_net_iface_last_check = 0.0 # dernier essai de (re)détection si _NET_IFACE vide
_net_prev_bytes = (0, 0)    # (bytes_sent, bytes_recv) snapshot précédent
_net_prev_time  = None
_net_ema        = 0.0       # EMA du débit total en KB/s (float, arrondi seulement à l'envoi)
_rapl_prev      = (0, 0.0)  # (energy_uj, monotonic_time)
_RAPL_PATH      = '/sys/class/powercap/intel-rapl:0/energy_uj'

_DBUS_SYSBUS            = None  # dbus.SystemBus(), ouvert une fois au démarrage
_SSD_HEALTH_DRIVE_PATH  = None  # chemin objet D-Bus UDisks2 du disque SSD1 (NVMe), None si indispo
_ssd_health_cache       = 255   # dernier % de santé lu (255 = indisponible/inconnu)
_ssd_health_cache_time  = 0.0
_SSD_HEALTH_INTERVAL    = 60.0  # throttle : la santé SMART ne varie jamais vite

_SSD2_HEALTH_DRIVE_PATH = None  # chemin objet D-Bus UDisks2 du disque SSD2 (ATA/USB), None si indispo
_ssd2_health_cache      = 255   # 100 = OK, 20 = WARN, 255 = indisponible/inconnu
_ssd2_temp_cache        = 0.0
_ssd2_smart_cache_time  = 0.0


def _get_os_label() -> str:
    """Nom + version de la distribution (ex: 'Zorin OS 18.1').
    VERSION_ID est parfois tronqué à la version majeure (ex: '18' alors que
    l'OS est en 18.1) : on préfère VERSION, plus complet, quand il existe."""
    try:
        info = platform.freedesktop_os_release()
        name = info.get('NAME', '').strip()
        version = (info.get('VERSION') or info.get('VERSION_ID', '')).strip()
        return f"{name} {version}".strip() or 'Linux'
    except Exception:
        return 'Linux'


def _get_kernel_label() -> str:
    """Version noyau tronquée : '6.17.0-40-generic' -> '6.17.040'
    (segments alphabétiques comme 'generic' jetés, le reste concaténé sans tiret)."""
    try:
        parts = platform.release().split('-')
        return parts[0] + ''.join(p for p in parts[1:] if p.isdigit())
    except Exception:
        return platform.release()


# Calculés une fois au chargement : ne changent pas en cours d'exécution.
_OS_KERNEL_LABEL = f"{_get_os_label()} ({_get_kernel_label()})"[:40].replace(',', ' ').replace(':', ' ')

def _detect_net_iface() -> None:
    """Détecte l'interface WiFi active ('wlp2s0', etc.)."""
    global _NET_IFACE
    try:
        for name, stats in sorted(psutil.net_if_stats().items()):
            if name.startswith('wl') and stats.isup:
                _NET_IFACE = name
                return
    except Exception:
        pass


def _detect_ssd_devices() -> None:
    """Détecte les disques physiques (NVMe en premier, puis USB/SATA)."""
    global _SSD_DEVICES, _SSD_TEMP_PATHS, _SSD_MOUNTS
    _SSD_DEVICES = []; _SSD_TEMP_PATHS = []; _SSD_MOUNTS = []
    try:
        counters = psutil.disk_io_counters(perdisk=True) or {}
    except Exception:
        counters = {}
    pat = re.compile(r'^(nvme\d+n\d+|[sh]d[a-z])$')

    def _dev_size(dev):
        try:
            return int(open(f'/sys/class/block/{dev}/size').read()) * 512
        except Exception:
            return 0

    devices = sorted(
        [d for d in counters if pat.match(d) and _dev_size(d) >= 1024**3],
        key=lambda n: (0 if n.startswith('nvme') else 1, n)
    )[:2]
    partitions = {p.device.replace('/dev/', ''): p.mountpoint
                  for p in psutil.disk_partitions(all=False)}
    for dev in devices:
        mount = partitions.get(dev)
        if mount is None:
            for pdev, mnt in partitions.items():
                if pdev.startswith(dev):
                    mount = mnt; break
        _SSD_MOUNTS.append(mount or '/')
        temp_path = None
        if dev.startswith('nvme'):
            nvme_id = re.match(r'(nvme\d+)', dev).group(1)
            cands = glob.glob(f"/sys/class/nvme/{nvme_id}/hwmon*/temp1_input")
            temp_path = cands[0] if cands else None
        else:
            cands = glob.glob(f"/sys/class/block/{dev}/device/hwmon*/temp1_input")
            temp_path = cands[0] if cands else None
        _SSD_TEMP_PATHS.append(temp_path)
    _SSD_DEVICES = devices


def _block_drive_path(dev: str):
    """Résout le chemin D-Bus UDisks2.Drive associé à un block device (ex: 'nvme0n1')."""
    block = _DBUS_SYSBUS.get_object(
        'org.freedesktop.UDisks2', f'/org/freedesktop/UDisks2/block_devices/{dev}')
    props = dbus.Interface(block, 'org.freedesktop.DBus.Properties')
    return props.Get('org.freedesktop.UDisks2.Block', 'Drive')


def _ensure_dbus_bus() -> bool:
    """Ouvre _DBUS_SYSBUS si besoin (au cas où l'ouverture initiale aurait échoué)."""
    global _DBUS_SYSBUS
    if _DBUS_SYSBUS is not None:
        return True
    if dbus is None:
        return False
    try:
        _DBUS_SYSBUS = dbus.SystemBus()
        return True
    except Exception:
        return False


def _detect_ssd1_health_path() -> None:
    """Résout (ou re-tente) le chemin D-Bus du disque SSD1 (NVMe.Controller)."""
    global _SSD_HEALTH_DRIVE_PATH
    if not _SSD_DEVICES or not _SSD_DEVICES[0].startswith('nvme'):
        return
    try:
        _SSD_HEALTH_DRIVE_PATH = _block_drive_path(_SSD_DEVICES[0])
    except Exception:
        _SSD_HEALTH_DRIVE_PATH = None


def _detect_ssd2_health_path() -> None:
    """Résout (ou re-tente) le chemin D-Bus du disque SSD2 (Drive.Ata). Séparée de
    _detect_ssd_health() pour pouvoir être ré-essayée en cours de route (cf.
    _refresh_ssd2_smart) : un flash ESP32 réinitialise le bus USB et peut rendre le
    pont USB-SATA temporairement invisible pile au démarrage du service."""
    global _SSD2_HEALTH_DRIVE_PATH
    if len(_SSD_DEVICES) < 2 or _SSD_DEVICES[1].startswith('nvme'):
        return
    try:
        drive_path = _block_drive_path(_SSD_DEVICES[1])
        drive = _DBUS_SYSBUS.get_object('org.freedesktop.UDisks2', drive_path)
        dprops = dbus.Interface(drive, 'org.freedesktop.DBus.Properties')
        if dprops.Get('org.freedesktop.UDisks2.Drive.Ata', 'SmartSupported'):
            _SSD2_HEALTH_DRIVE_PATH = drive_path
    except Exception:
        _SSD2_HEALTH_DRIVE_PATH = None


def _detect_ssd_health() -> None:
    """Résout les chemins D-Bus UDisks2 des disques SSD1 (NVMe.Controller) et SSD2 (Drive.Ata),
    utilisés pour lire la santé SMART sans droits root."""
    global _DBUS_SYSBUS
    if dbus is None or not _SSD_DEVICES:
        return
    try:
        _DBUS_SYSBUS = dbus.SystemBus()
    except Exception:
        _DBUS_SYSBUS = None
        return

    _detect_ssd1_health_path()
    _detect_ssd2_health_path()


# ── Lecture métriques ─────────────────────────────────────────────────────────

def get_cpu_temp() -> float:
    """Tctl depuis k10temp (AMD Ryzen)."""
    try:
        for entry in psutil.sensors_temperatures().get("k10temp", []):
            if entry.label in ("Tctl", "Tdie"):
                return round(entry.current, 1)
    except Exception:
        pass
    return 0.0


def get_gpu_temp() -> float:
    """edge depuis amdgpu hwmon (Radeon 780M)."""
    if _GPU_TEMP_PATH:
        try:
            return round(int(open(_GPU_TEMP_PATH).read()) / 1000.0, 1)
        except Exception:
            pass
    try:
        for entry in psutil.sensors_temperatures().get("amdgpu", []):
            if entry.label == "edge":
                return round(entry.current, 1)
    except Exception:
        pass
    return 0.0


def get_disk_io_per_ssd() -> list[tuple[float, float]]:
    """Retourne [(r0,w0), (r1,w1)] en MB/s pour chaque SSD détecté."""
    global _disk_prev, _disk_prev_time
    fallback = [(0.0, 0.0)] * max(len(_SSD_DEVICES), 1)
    try:
        all_ctrs = psutil.disk_io_counters(perdisk=True) or {}
        now = time.monotonic()
        if not _disk_prev or _disk_prev_time is None:
            _disk_prev = {d: all_ctrs[d] for d in _SSD_DEVICES if d in all_ctrs}
            _disk_prev_time = now
            return fallback
        dt = now - _disk_prev_time
        result = []
        for dev in _SSD_DEVICES:
            c, p = all_ctrs.get(dev), _disk_prev.get(dev)
            if c and p and dt > 0:
                r = max(0.0, (c.read_bytes  - p.read_bytes)  / dt / 1024**2)
                w = max(0.0, (c.write_bytes - p.write_bytes) / dt / 1024**2)
                result.append((round(r, 1), round(w, 1)))
            else:
                result.append((0.0, 0.0))
        _disk_prev = {d: all_ctrs[d] for d in _SSD_DEVICES if d in all_ctrs}
        _disk_prev_time = now
        return result if result else fallback
    except Exception:
        return fallback


def get_wifi() -> tuple[str, int]:
    """(ssid sanitisé max 8 chars, signal %). Utilise nmcli."""
    try:
        out = subprocess.check_output(
            ['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL', 'dev', 'wifi'],
            text=True, timeout=1, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if line.startswith('oui:'):
                rest = line[4:]
                last = rest.rfind(':')
                if last >= 0:
                    ssid = rest[:last].replace(',', '').replace(':', '')[:8]
                    sig  = int(rest[last + 1:])
                    return ssid, sig
    except Exception:
        pass
    return '', 0


def get_vpn_status() -> bool:
    """True si une interface tun/tap/wg/vpn est UP."""
    try:
        for name, stats in psutil.net_if_stats().items():
            if stats.isup and any(p in name.lower() for p in ('tun', 'tap', 'vpn', 'wg')):
                return True
    except Exception:
        pass
    return False


def get_ssd_temps() -> list[float]:
    """Température de chaque SSD (0.0 si indisponible)."""
    temps = []
    for i, dev in enumerate(_SSD_DEVICES):
        path = _SSD_TEMP_PATHS[i] if i < len(_SSD_TEMP_PATHS) else None
        if path:
            try:
                temps.append(round(int(open(path).read()) / 1000.0, 1))
                continue
            except Exception:
                pass
        if dev.startswith('nvme'):
            try:
                for name, entries in psutil.sensors_temperatures().items():
                    if "nvme" in name.lower():
                        for e in entries:
                            if e.label in ("Composite", "Sensor 1", ""):
                                temps.append(round(e.current, 1))
                                break
                        else:
                            continue
                        break
                else:
                    temps.append(0.0)
            except Exception:
                temps.append(0.0)
        else:
            temps.append(get_ssd2_temp())
    return temps if temps else [0.0]


def get_ssd_capacities() -> list[tuple[int, int]]:
    """(used_gb, total_gb) pour chaque SSD."""
    caps = []
    for mount in _SSD_MOUNTS:
        try:
            u = psutil.disk_usage(mount)
            caps.append((int(u.used / 1024**3), int(u.total / 1024**3)))
        except Exception:
            caps.append((0, 0))
    return caps if caps else [(0, 0)]


def get_vram() -> tuple[float, float]:
    """Retourne (used_mb, total_mb) depuis sysfs amdgpu."""
    try:
        used  = int(open(_VRAM_USED_PATH).read())  / 1024**2
        total = int(open(_VRAM_TOTAL_PATH).read()) / 1024**2
        return round(used, 0), round(total, 0)
    except Exception:
        return 0.0, 0.0


def get_gpu_usage() -> float:
    """gpu_busy_percent depuis sysfs (natif, pas besoin de ROCm)."""
    if _GPU_BUSY_PATH:
        try:
            return float(open(_GPU_BUSY_PATH).read().strip())
        except Exception:
            pass
    return 0.0


def get_net_avg_kbps() -> int:
    """Débit total WiFi lissé par EMA α=0.25 (upload + download, KB/s)."""
    global _net_prev_bytes, _net_prev_time, _net_ema, _net_iface_last_check
    if not _NET_IFACE:
        # Le WiFi peut ne pas encore être associé au démarrage du service
        # (systemd After=network.target ne l'attend pas) : on retente
        # périodiquement au lieu de rester bloqué sur l'échec initial.
        now = time.monotonic()
        if now - _net_iface_last_check >= 5.0:
            _net_iface_last_check = now
            _detect_net_iface()
        if not _NET_IFACE:
            return 0
    try:
        now   = time.monotonic()
        stats = psutil.net_io_counters(pernic=True).get(_NET_IFACE)
        if not stats or _net_prev_time is None:
            _net_prev_bytes = (stats.bytes_sent, stats.bytes_recv) if stats else (0, 0)
            _net_prev_time  = now
            return 0
        dt    = now - _net_prev_time
        total = (((stats.bytes_sent - _net_prev_bytes[0])
                   + (stats.bytes_recv - _net_prev_bytes[1])) / dt / 1024) if dt > 0 else 0.0
        _net_prev_bytes = (stats.bytes_sent, stats.bytes_recv)
        _net_prev_time  = now
        _net_ema = 0.25 * max(0.0, total) + 0.75 * _net_ema
        return round(_net_ema)
    except Exception:
        return 0


def get_cpu_freq_x10() -> int:
    """Fréquence CPU moyenne × 10 (ex: 32 = 3.2 GHz)."""
    try:
        f = psutil.cpu_freq()
        return int(f.current / 100) if f else 0
    except Exception:
        return 0


def get_cpu_power_w() -> int:
    """Puissance CPU via RAPL (W). Retourne 0 si non accessible (permission root)."""
    global _rapl_prev
    try:
        e = int(open(_RAPL_PATH).read())
        now = time.monotonic()
        prev_e, prev_t = _rapl_prev
        _rapl_prev = (e, now)
        dt = now - prev_t
        if prev_e and dt > 0:
            return max(0, int((e - prev_e) / dt / 1e6))
    except Exception:
        pass
    return 0


def get_ssd_health() -> int:
    """% de santé SSD1 (100 - percent_used SMART, via UDisks2/D-Bus, sans root).
    Retourne 255 si indisponible (pas de NVMe, D-Bus absent, disque déconnecté...).
    Throttlé à 1 lecture/60s : la santé SMART ne varie pas assez vite pour justifier
    un appel D-Bus toutes les 0.25s. Si le chemin D-Bus n'a pas pu être résolu (D-Bus
    pas encore prêt au démarrage, glitch USB...), une nouvelle tentative est faite à
    chaque cycle throttlé plutôt que d'abandonner définitivement."""
    global _ssd_health_cache, _ssd_health_cache_time
    now = time.monotonic()
    if now - _ssd_health_cache_time < _SSD_HEALTH_INTERVAL:
        return _ssd_health_cache
    _ssd_health_cache_time = now
    if _SSD_HEALTH_DRIVE_PATH is None and _ensure_dbus_bus():
        _detect_ssd1_health_path()
    if _SSD_HEALTH_DRIVE_PATH is None:
        _ssd_health_cache = 255
        return _ssd_health_cache
    try:
        drive = _DBUS_SYSBUS.get_object('org.freedesktop.UDisks2', _SSD_HEALTH_DRIVE_PATH)
        ctrl = dbus.Interface(drive, 'org.freedesktop.UDisks2.NVMe.Controller')
        attrs = ctrl.SmartGetAttributes(dbus.Dictionary({}, signature='sv'))
        percent_used = int(attrs['percent_used'])
        _ssd_health_cache = max(0, min(100, 100 - percent_used))
    except Exception:
        _ssd_health_cache = 255
    return _ssd_health_cache


def _refresh_ssd2_smart() -> None:
    """Rafraîchit (throttlé, 60s) la santé + température SSD2 via UDisks2/D-Bus (ATA
    passthrough, sans root). Lit les propriétés déjà en cache côté daemon UDisks2 — PAS
    d'appel à SmartUpdate() : cette méthode nécessite une autorisation polkit liée à une
    session active, qui échoue silencieusement (NotAuthorizedCanObtain) pour un service
    systemd headless. UDisks2 rafraîchit ces valeurs tout seul périodiquement (constaté :
    quelques minutes de délai max), suffisant pour un indicateur qui varie lentement.
    Si le chemin D-Bus n'a pas pu être résolu (glitch USB au démarrage — un flash ESP32
    réinitialise le bus —, D-Bus pas encore prêt...), une nouvelle tentative est faite à
    chaque cycle throttlé plutôt que d'abandonner définitivement."""
    global _ssd2_health_cache, _ssd2_temp_cache, _ssd2_smart_cache_time
    now = time.monotonic()
    if now - _ssd2_smart_cache_time < _SSD_HEALTH_INTERVAL:
        return
    _ssd2_smart_cache_time = now
    if _SSD2_HEALTH_DRIVE_PATH is None and _ensure_dbus_bus():
        _detect_ssd2_health_path()
    if _SSD2_HEALTH_DRIVE_PATH is None:
        _ssd2_health_cache = 255
        _ssd2_temp_cache = 0.0
        return
    try:
        drive = _DBUS_SYSBUS.get_object('org.freedesktop.UDisks2', _SSD2_HEALTH_DRIVE_PATH)
        props = dbus.Interface(drive, 'org.freedesktop.DBus.Properties')
        failing      = bool(props.Get('org.freedesktop.UDisks2.Drive.Ata', 'SmartFailing'))
        num_failing  = int(props.Get('org.freedesktop.UDisks2.Drive.Ata', 'SmartNumAttributesFailing'))
        bad_sectors  = int(props.Get('org.freedesktop.UDisks2.Drive.Ata', 'SmartNumBadSectors'))
        temp_kelvin  = float(props.Get('org.freedesktop.UDisks2.Drive.Ata', 'SmartTemperature'))
        warn = failing or num_failing > 0 or bad_sectors > 0
        _ssd2_health_cache = 20 if warn else 100
        _ssd2_temp_cache = round(temp_kelvin - 273.15, 1) if temp_kelvin > 0 else 0.0
    except Exception:
        _ssd2_health_cache = 255
        _ssd2_temp_cache = 0.0


def get_ssd2_health() -> int:
    """100 = OK, 20 = WARN, 255 = indisponible. Cf. _refresh_ssd2_smart()."""
    _refresh_ssd2_smart()
    return _ssd2_health_cache


def get_ssd2_temp() -> float:
    """Température SSD2 °C (0.0 si indisponible). Cf. _refresh_ssd2_smart()."""
    _refresh_ssd2_smart()
    return _ssd2_temp_cache


def get_uptime_s() -> int:
    """Uptime système en secondes."""
    return int(time.time() - psutil.boot_time())


def get_updates_count() -> int:
    """Nombre de mises à jour dispo (update-notifier, rafraîchi ~1-2x/jour par
    apt-daily.timer — pas temps réel, mais lecture de fichier quasi gratuite)."""
    try:
        content = open(_UPDATES_PATH).read()
        m = re.search(r'(\d+)\s+updates?\s+can be applied', content)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


# ── Piles souris / clavier (UPower via D-Bus système) ─────────────────────────
# UPower déclare parfois une souris HID++ en Type=6 (keyboard) : on classe
# d'abord par nom de modèle, le Type ne sert que de repli.

_KBD_MODEL_RE   = re.compile(r'keyboard|clavier|\bK\d{3}\b', re.I)
_MOUSE_MODEL_RE = re.compile(r'mouse|souris|MX (Anywhere|Master|Vertical)|\bM\d{3}\b', re.I)
_UPOWER_TYPE_MOUSE    = 5
_UPOWER_TYPE_KEYBOARD = 6
_UPOWER_STATE_CHARGING = 1
_PERIPH_BAT_CACHE      = (255, 0, 255, 0)
_PERIPH_BAT_NEXT       = 0.0
_PERIPH_BAT_INTERVAL   = 60.0   # s — niveaux de pile qui bougent lentement


def get_peripheral_batteries() -> tuple[int, int, int, int]:
    """(clavier %, clavier en charge, souris %, souris en charge).
    % = 255 si périphérique absent ou UPower indisponible."""
    global _PERIPH_BAT_CACHE, _PERIPH_BAT_NEXT
    now = time.monotonic()
    if now < _PERIPH_BAT_NEXT:
        return _PERIPH_BAT_CACHE
    _PERIPH_BAT_NEXT = now + _PERIPH_BAT_INTERVAL

    kbd, mouse = (255, 0), (255, 0)
    if not _ensure_dbus_bus():
        _PERIPH_BAT_CACHE = (*kbd, *mouse)
        return _PERIPH_BAT_CACHE
    try:
        upower = _DBUS_SYSBUS.get_object('org.freedesktop.UPower',
                                         '/org/freedesktop/UPower')
        paths = dbus.Interface(upower, 'org.freedesktop.UPower').EnumerateDevices()
        for path in paths:
            dev   = _DBUS_SYSBUS.get_object('org.freedesktop.UPower', path)
            props = dbus.Interface(dev, 'org.freedesktop.DBus.Properties') \
                        .GetAll('org.freedesktop.UPower.Device')
            if props.get('PowerSupply', True) or not props.get('IsPresent', False):
                continue
            model = str(props.get('Model', ''))
            dtype = int(props.get('Type', 0))
            entry = (max(0, min(100, int(round(float(props.get('Percentage', 0)))))),
                     int(int(props.get('State', 0)) == _UPOWER_STATE_CHARGING))
            if _KBD_MODEL_RE.search(model):
                kbd = entry
            elif _MOUSE_MODEL_RE.search(model) or dtype == _UPOWER_TYPE_MOUSE:
                mouse = entry
            elif dtype == _UPOWER_TYPE_KEYBOARD:
                kbd = entry
    except Exception:
        pass
    _PERIPH_BAT_CACHE = (*kbd, *mouse)
    return _PERIPH_BAT_CACHE


# ── Veille écran NUC (Mutter PowerSaveMode via D-Bus session) ─────────────────
# PowerSaveMode = état DPMS réel (0 = allumé, 3 = éteint), piloté par gsd-power.
# Repasse à 0 dès que souris/clavier rallument l'écran, y compris sur l'écran
# de verrouillage (contrairement à ScreenSaver.Active).

_SESSION_BUS_ADDR       = f"unix:path=/run/user/{os.getuid()}/bus"
_SESSION_BUS            = None
_SESSION_BUS_RETRY_TIME = 0.0
_SESSION_BUS_RETRY      = 30.0   # s entre deux tentatives si session absente


def get_display_off() -> bool | None:
    """True si l'écran du NUC est éteint, False s'il est allumé,
    None si l'état est inconnu (pas de session GNOME, dbus absent...)."""
    global _SESSION_BUS, _SESSION_BUS_RETRY_TIME
    if dbus is None:
        return None
    if _SESSION_BUS is None:
        now = time.monotonic()
        if now < _SESSION_BUS_RETRY_TIME:
            return None
        _SESSION_BUS_RETRY_TIME = now + _SESSION_BUS_RETRY
        try:
            _SESSION_BUS = dbus.bus.BusConnection(_SESSION_BUS_ADDR)
        except Exception:
            return None
    try:
        obj   = _SESSION_BUS.get_object('org.gnome.Mutter.DisplayConfig',
                                        '/org/gnome/Mutter/DisplayConfig')
        props = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
        mode  = props.Get('org.gnome.Mutter.DisplayConfig', 'PowerSaveMode',
                          timeout=1.0)
        return int(mode) != 0
    except Exception:
        try:
            _SESSION_BUS.close()
        except Exception:
            pass
        _SESSION_BUS = None
        return None


def collect() -> dict:
    vm      = psutil.virtual_memory()
    cores   = psutil.cpu_percent(percpu=True)
    cores16 = (cores + [0.0] * 16)[:16]
    io      = get_disk_io_per_ssd()
    temps   = get_ssd_temps()
    caps    = get_ssd_capacities()
    vram_used, vram_total = get_vram()
    wifi_ssid, wifi_sig  = get_wifi()
    net_total            = get_net_avg_kbps()
    kbd_bat, kbd_chg, mouse_bat, mouse_chg = get_peripheral_batteries()

    def _io(i, j):  return io[i][j]   if i < len(io)    else 0.0
    def _tmp(i):    return temps[i]    if i < len(temps)  else 0.0
    def _cap(i, j): return caps[i][j]  if i < len(caps)   else 0

    return {
        "cpu_pct":    round(psutil.cpu_percent(), 1),
        "cpu_temp":   get_cpu_temp(),
        "gpu_pct":    get_gpu_usage(),
        "gpu_temp":   get_gpu_temp(),
        "ram_pct":    round(vm.percent, 1),
        "ram_gb":     round(vm.total / 1024**3, 1),
        "cores":      [int(c) for c in cores16],
        "ssd_read":   _io(0, 0),
        "ssd_write":  _io(0, 1),
        "ssd_temp":   _tmp(0),
        "ssd_used":   _cap(0, 0),
        "ssd_total":  _cap(0, 1),
        "ssd_health": get_ssd_health(),
        "ssd2_read":  _io(1, 0),
        "ssd2_write": _io(1, 1),
        "ssd2_temp":  _tmp(1),
        "ssd2_used":  _cap(1, 0),
        "ssd2_total": _cap(1, 1),
        "ssd2_health": get_ssd2_health(),
        "vram_used":  vram_used,
        "vram_total": vram_total,
        "wifi_ssid":  wifi_ssid,
        "wifi_sig":   wifi_sig,
        "vpn_on":     int(get_vpn_status()),
        "net_total":  net_total,
        "cpu_freq":   get_cpu_freq_x10(),
        "cpu_power":  get_cpu_power_w(),
        "uptime":     get_uptime_s(),
        "os_kernel":  _OS_KERNEL_LABEL,
        "updates":    get_updates_count(),
        "kbd_bat":    kbd_bat,
        "kbd_chg":    kbd_chg,
        "mouse_bat":  mouse_bat,
        "mouse_chg":  mouse_chg,
    }


def format_line(d: dict) -> str:
    parts = [
        f"CPU:{d['cpu_pct']:.0f}",
        f"CTEMP:{d['cpu_temp']:.0f}",
        f"GPU:{d['gpu_pct']:.0f}",
        f"GTEMP:{d['gpu_temp']:.0f}",
        f"RAM:{d['ram_pct']:.0f}",
        f"RTOT:{d['ram_gb']:.0f}",
        f"SREAD:{int(d['ssd_read']*1024)}",
        f"SWRIT:{int(d['ssd_write']*1024)}",
        f"STEMP:{d['ssd_temp']:.0f}",
        f"SCAP:{d['ssd_used']}",
        f"STOT:{d['ssd_total']}",
        f"SHLTH:{d['ssd_health']}",
        f"S2TMP:{d['ssd2_temp']:.0f}",
        f"S2CAP:{d['ssd2_used']}",
        f"S2TOT:{d['ssd2_total']}",
        f"S2HLTH:{d['ssd2_health']}",
        f"VUSED:{d['vram_used']:.0f}",
        f"VTOT:{d['vram_total']:.0f}",
        f"WNAM:{d['wifi_ssid']}",
        f"WSIG:{d['wifi_sig']}",
        f"VPN:{d['vpn_on']}",
    ]
    parts += [
        f"NTOT:{d['net_total']}",
        f"CFRQ:{d['cpu_freq']}",
        f"CPWR:{d['cpu_power']}",
        f"UPTS:{d['uptime']}",
        f"OSKV:{d['os_kernel']}",
        f"UPD:{d['updates']}",
        f"SCR:{d.get('screen_on', 1)}",
        f"KBAT:{d['kbd_bat']}",
        f"KCHG:{d['kbd_chg']}",
        f"MBAT:{d['mouse_bat']}",
        f"MCHG:{d['mouse_chg']}",
    ]
    parts.append("CX:" + ";".join(str(v) for v in d["cores"]))
    return ",".join(parts)


_send_count = 0

def print_dashboard(d: dict) -> None:
    global _send_count
    _send_count += 1
    cores_str = " ".join(f"{c:2d}" for c in d["cores"])
    print(
        f"[{_send_count:04d}] "
        f"CPU {d['cpu_pct']:5.1f}% {d['cpu_temp']:.0f}°C | "
        f"GPU {d['gpu_pct']:5.1f}% {d['gpu_temp']:.0f}°C | "
        f"RAM {d['ram_pct']:.1f}% | "
        f"SSD1 R:{d['ssd_read']:5.1f} W:{d['ssd_write']:5.1f} | "
        f"SSD2 R:{d['ssd2_read']:5.1f} W:{d['ssd2_write']:5.1f} MB/s | "
        f"KB {d['kbd_bat']}% MS {d['mouse_bat']}% | "
        f"C: {cores_str}",
        flush=True
    )


# ── Détection port série ──────────────────────────────────────────────────────

def auto_detect_port() -> str | None:
    for p in sorted(glob.glob("/dev/ttyACM*")):
        return p
    for port in serial.tools.list_ports.comports():
        if "CP210" in (port.description or "") or "USB Serial" in (port.description or ""):
            return port.device
    return None


# ── Contrôle au démarrage ─────────────────────────────────────────────────────

def preflight_check(port: str) -> None:
    """Vérifie que toutes les sources de métriques sont disponibles."""
    errors = []

    # Port série
    if os.path.exists(port):
        print(f"  Port série    OK  {port}")
    else:
        print(f"  Port série    MANQUANT  {port}")
        errors.append("port série introuvable")

    # Température CPU (k10temp / AMD Ryzen)
    cpu_temp = get_cpu_temp()
    if cpu_temp > 0:
        print(f"  Temp CPU      OK  {cpu_temp:.0f}°C  (k10temp)")
    else:
        print("  Temp CPU      MANQUANT  (k10temp non trouvé)")
        errors.append("température CPU")

    # Usage GPU
    if _GPU_BUSY_PATH:
        usage = get_gpu_usage()
        print(f"  Usage GPU     OK  {usage:.0f}%  ({_GPU_BUSY_PATH})")
    else:
        print("  Usage GPU     MANQUANT  (gpu_busy_percent non trouvé)")
        errors.append("usage GPU")

    # Température GPU
    gpu_temp = get_gpu_temp()
    if gpu_temp > 0:
        print(f"  Temp GPU      OK  {gpu_temp:.0f}°C  ({_GPU_TEMP_PATH or 'amdgpu/edge'})")
    else:
        print("  Temp GPU      MANQUANT  (amdgpu/edge non trouvé)")
        errors.append("température GPU")

    # RAM
    vm = psutil.virtual_memory()
    total_gb = vm.total / 1024**3
    print(f"  RAM           OK  {total_gb:.0f} GB  ({vm.percent:.1f}% utilisé)")

    # Disques SSD (détection)
    if _SSD_DEVICES:
        for i, dev in enumerate(_SSD_DEVICES):
            mount = _SSD_MOUNTS[i] if i < len(_SSD_MOUNTS) else '?'
            temp_src = _SSD_TEMP_PATHS[i] if i < len(_SSD_TEMP_PATHS) else None
            caps = get_ssd_capacities()
            cap = caps[i] if i < len(caps) else (0, 0)
            print(f"  SSD{i+1} ({dev})  OK  montage:{mount}  {cap[0]}/{cap[1]} GB"
                  + (f"  hwmon:{temp_src}" if temp_src else "  (pas de temp hwmon)"))
    else:
        print("  Disques SSD   MANQUANT  (aucun device nvme/sd détecté)")
        errors.append("disque I/O")

    # Santé SMART SSD1 (NVMe, via UDisks2/D-Bus, sans root)
    health = get_ssd_health()
    if health <= 100:
        print(f"  Santé SMART   OK  {health}%")
    elif dbus is None:
        print("  Santé SMART   n/a  (module python3-dbus absent)")
    else:
        print("  Santé SMART   n/a  (pas de NVMe / UDisks2 indisponible)")

    # Santé + température SSD2 (ATA/USB, via UDisks2/D-Bus, sans root)
    health2 = get_ssd2_health()
    if health2 <= 100:
        print(f"  Santé SMART2  {'OK' if health2 >= 90 else 'ATTENTION':<5} "
              f"{health2}%  {get_ssd2_temp():.0f}°C")
    elif dbus is None:
        print("  Santé SMART2  n/a  (module python3-dbus absent)")
    else:
        print("  Santé SMART2  n/a  (pas de SSD2 ATA / UDisks2 indisponible)")

    # WiFi
    ssid, sig = get_wifi()
    if ssid:
        print(f"  WiFi          OK  {ssid}  {sig}%")
    else:
        print("  WiFi          MANQUANT / déconnecté")

    # VPN
    vpn = get_vpn_status()
    print(f"  VPN           {'OK  (actif)' if vpn else 'inactif'}")

    # Températures SSD
    temps = get_ssd_temps()
    for i, t in enumerate(temps):
        if t > 0:
            print(f"  Temp SSD{i+1}     OK  {t:.0f}°C")
        elif i < len(_SSD_DEVICES) and not _SSD_TEMP_PATHS[i]:
            print(f"  Temp SSD{i+1}     n/a  (USB — pas de hwmon)")
        else:
            print(f"  Temp SSD{i+1}     MANQUANT")

    # VRAM GPU
    if _VRAM_USED_PATH:
        vused, vtotal = get_vram()
        print(f"  VRAM GPU      OK  {vused:.0f}/{vtotal:.0f} MB  ({_VRAM_USED_PATH})")
    else:
        print("  VRAM GPU      MANQUANT  (mem_info_vram_used non trouvé)")
        errors.append("VRAM GPU")

    # Veille écran (Mutter PowerSaveMode)
    off = get_display_off()
    if off is None:
        print("  Veille écran  n/a  (bus de session / Mutter indisponible — écran ESP32 toujours allumé)")
    else:
        print(f"  Veille écran  OK  (Mutter PowerSaveMode, écran NUC {'éteint' if off else 'allumé'})")

    # Threads CPU
    cores = psutil.cpu_percent(percpu=True)
    if len(cores) >= 16:
        print(f"  Threads CPU   OK  {len(cores)} threads détectés")
    else:
        print(f"  Threads CPU   ATTENTION  {len(cores)} threads (< 16)")

    print()
    if errors:
        print(f"Avertissement : {', '.join(errors)} non disponible(s).")
        print("Les valeurs manquantes seront affichées à 0 sur l'écran.\n")
    else:
        print("Tout est OK — démarrage...\n")


# ── Boucle principale ─────────────────────────────────────────────────────────

_DISPLAY_POLL_INTERVAL = 1.0   # s entre deux lectures de PowerSaveMode
_PROCS_INTERVAL = 1.0     # s entre deux trames P: (top processus, écran 2)
_PROCS_OFFSET   = 0.125   # s de décalage de P: par rapport à la trame principale
_ICON_INTERVAL  = 0.1     # s minimum entre deux icônes (8 lignes I:, ~2,9 Ko)
_OUT_MAX        = 1024    # o en attente au-delà desquels une trame d'écran est sautée


def _flush(fd: int, out: bytearray) -> None:
    """Écrit ce que le FIFO HWCDC accepte ; le reste attend le tour suivant
    (une écriture partielle ne coupe donc jamais une ligne)."""
    if not out:
        return
    try:
        n = os.write(fd, out)
    except BlockingIOError:
        return
    except OSError as exc:
        raise serial.SerialException(str(exc))
    del out[:n]


def _read_icon_requests(fd: int, rx: bytearray) -> list[int]:
    """Hashs des demandes d'icônes « ?I:<hash> » envoyées par l'ESP32."""
    try:
        rx += os.read(fd, 1024)
    except BlockingIOError:
        return []
    except OSError as exc:
        raise serial.SerialException(str(exc))
    if len(rx) > 4096:          # pas de \n depuis longtemps : ce n'est pas une demande
        del rx[:-64]
    reqs = []
    while b"\n" in rx:
        line, _, rest = rx.partition(b"\n")
        rx[:] = rest
        line = line.strip()
        if line.startswith(b"?I:"):
            try:
                reqs.append(int(line[3:11], 16))
            except ValueError:
                pass
    return reqs


def run(port: str, baud: int, interval: float, sleep_delay: float) -> None:
    psutil.cpu_percent(percpu=True)   # premier appel toujours à 0, on le jette
    time.sleep(0.2)

    reconnect_delay = 3.0

    # Veille écran ESP32 : sleep_delay s après l'extinction de l'écran du NUC
    display_off_since = None
    screen_on         = 1
    next_display_poll = 0.0

    procs = ProcTop()   # index .desktop + thread des icônes, gardés entre reconnexions

    while True:
        try:
            # DTR=False AVANT open() pour ne pas déclencher de reset intempestif.
            # L'ouverture du port sur Linux provoque tout de même un
            # USB_UART_CHIP_RESET via cdc-acm ; on le gère avec la double-ouverture.
            ser = serial.Serial()
            ser.port     = port
            ser.baudrate = baud
            ser.timeout  = 0
            ser.dsrdtr   = False
            ser.rtscts   = False
            ser.dtr      = False
            ser.rts      = False

            # 1re ouverture → reset ESP32 → on attend le boot puis on referme
            # pour que le driver cdc-acm libère ses URBs IN proprement.
            print("Connexion en cours...", flush=True)
            ser.open()
            time.sleep(3.0)
            ser.read(ser.in_waiting)   # vider le buffer de boot (messages ROM)
            ser.close()
            time.sleep(0.2)

            # 2e ouverture → nouveau reset + session cdc-acm fraîche avec des
            # URBs IN correctement soumis → lecture et écriture fonctionnelles.
            ser.dtr = False
            ser.rts = False
            ser.open()
            time.sleep(3.0)
            ser.read(ser.in_waiting)   # vider le buffer de boot

            # Mode raw, CRTSCTS désactivé, non-bloquant
            fd = ser.fileno()
            attrs = list(termios.tcgetattr(fd))
            attrs[2] = ((attrs[2]
                         & ~(termios.CRTSCTS | termios.CSIZE | termios.PARENB))
                        | termios.CLOCAL | termios.CREAD | termios.CS8)
            attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY
                          | termios.BRKINT | termios.ICRNL | termios.INPCK
                          | termios.ISTRIP)
            attrs[1] &= ~termios.OPOST
            attrs[3] &= ~(termios.ECHO | termios.ECHOE | termios.ECHOK
                          | termios.ECHONL | termios.ICANON | termios.ISIG
                          | termios.IEXTEN)
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            fcntl.fcntl(fd, fcntl.F_SETFL,
                        fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)

            print(f"Connecté — envoi toutes les {interval:.2f}s  (Ctrl+C pour arrêter)\n",
                  flush=True)
            next_send  = time.monotonic()
            next_procs = next_send + _PROCS_OFFSET
            next_icon  = 0.0
            out_buf    = bytearray()   # tampon de sortie unique (toutes les trames)
            rx_buf     = bytearray()
            icon_queue: list[int] = []

            try:
                while True:
                    now = time.monotonic()
                    frame_queued = False
                    if sleep_delay > 0 and now >= next_display_poll:
                        next_display_poll = now + _DISPLAY_POLL_INTERVAL
                        if get_display_off():
                            if display_off_since is None:
                                display_off_since = now
                                print("Écran NUC éteint — veille ESP32 dans "
                                      f"{sleep_delay:.0f}s", flush=True)
                        elif display_off_since is not None:
                            display_off_since = None
                            print("Écran NUC rallumé", flush=True)
                        new_on = int(display_off_since is None
                                     or now - display_off_since < sleep_delay)
                        if new_on != screen_on:
                            screen_on = new_on
                            print(f"Écran ESP32 → {'réveil' if screen_on else 'veille'}",
                                  flush=True)
                            next_send = now   # transmettre le changement sans attendre
                    # Une seule trame d'écran par tour ; si les deux sont dues (boucle
                    # ralentie par collect()), la plus en retard passe d'abord : la
                    # trame P: ne peut pas être affamée par la trame principale.
                    procs_due = now >= next_procs
                    if now >= next_send and not (procs_due and next_procs < next_send):
                        data       = collect()
                        data["screen_on"] = screen_on
                        line_bytes = (format_line(data) + "\n").encode("ascii")
                        if len(line_bytes) > _SERIAL_MAX:
                            print(f"[WARN] Ligne {len(line_bytes)}B > {_SERIAL_MAX} — tronquée", flush=True)
                            line_bytes = line_bytes[:_SERIAL_MAX - 1] + b"\n"
                        # ESP32 qui ne lit plus : on saute la trame plutôt que d'empiler
                        # des données périmées (la suivante arrive dans 0,25 s)
                        if len(out_buf) < _OUT_MAX:
                            out_buf += line_bytes
                            if _send_count < 5:
                                print_dashboard(data)
                            elif _send_count == 5:
                                print_dashboard(data)
                                print("(affichage arrêté — envoi continu en arrière-plan)", flush=True)
                        next_send    = now + interval
                        frame_queued = True
                    elif procs_due:
                        if len(out_buf) < _OUT_MAX:
                            out_buf += (procs.procs_line() + "\n").encode("ascii")
                        next_procs  += _PROCS_INTERVAL
                        if next_procs <= now:   # retard (démarrage lent) : on se recale
                            next_procs = now + _PROCS_INTERVAL
                        frame_queued = True

                    for h in _read_icon_requests(fd, rx_buf):
                        if h not in icon_queue and procs.icons.blob(h) is not None:
                            icon_queue.append(h)
                    # Icônes : seulement quand aucune trame d'écran n'attend
                    if icon_queue and not frame_queued and not out_buf and now >= next_icon:
                        out_buf  += b"".join(procs.icon_lines(icon_queue.pop(0)))
                        next_icon = now + _ICON_INTERVAL

                    _flush(fd, out_buf)
                    time.sleep(0.01)
            finally:
                ser.close()

        except serial.SerialException as e:
            print(f"\nDéconnecté : {e}")
            print(f"Reconnexion dans {reconnect_delay:.0f}s...")
            time.sleep(reconnect_delay)
        except OSError as e:
            print(f"\nErreur port : {e}")
            time.sleep(reconnect_delay)


# ── Entrée ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envoie les métriques système au T-Display-S3-Long"
    )
    parser.add_argument("--port", default=None,
                        help="Port série (ex: /dev/ttyACM0). Auto-détecté si absent.")
    parser.add_argument("--baud",     type=int,   default=115200)
    parser.add_argument("--interval", type=float, default=0.25,
                        help="Intervalle d'envoi en secondes (défaut: 0.25)")
    parser.add_argument("--sleep-delay", type=float, default=600,
                        help="Délai (s) après l'extinction de l'écran du NUC avant "
                             "la veille de l'écran ESP32 (défaut: 600, 0 = jamais)")
    args = parser.parse_args()

    port = args.port or auto_detect_port()
    if port is None:
        sys.exit("Aucun port série trouvé. Branchez l'ESP32 et réessayez, "
                 "ou spécifiez --port /dev/ttyACMx")

    print("=== NUC Monitor — vérification démarrage ===")
    _detect_ssd_devices()
    _detect_ssd_health()
    _detect_net_iface()
    preflight_check(port)

    try:
        run(port, args.baud, args.interval, args.sleep_delay)
    except KeyboardInterrupt:
        print("\nArrêté.")


if __name__ == "__main__":
    main()
