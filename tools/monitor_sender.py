#!/usr/bin/env python3
"""
monitor_sender.py — Envoie les métriques système au T-Display-S3-Long (ESP32-S3).

Métriques envoyées :
  CPU global, température CPU (k10temp/Tctl), usage GPU (Radeon 780M),
  température GPU (amdgpu/edge), RAM %, 16 threads CPU individuels.

Dépendances :
    pip install psutil pyserial

Usage :
    python monitor_sender.py                      # auto-détecte /dev/ttyACM*
    python monitor_sender.py --port /dev/ttyACM0
    python monitor_sender.py --port /dev/ttyACM0 --interval 0.5
"""

import argparse
import glob
import re
import subprocess
import time
import sys
import os
import termios
import fcntl

try:
    import psutil
except ImportError:
    sys.exit("Installez psutil :  pip install psutil")

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.exit("Installez pyserial :  pip install pyserial")


# Limite matérielle HWCDC : buffer SW ESP32 = 512 octets (setRxBufferSize(512)),
# buf[] serial_parser = 512 octets. On garde 2 octets de marge (\0 + sécurité).
_SERIAL_MAX = 510

# ── Chemins sysfs détectés au démarrage ───────────────────────────────────────

def _find_sysfs(pattern: str) -> str | None:
    matches = glob.glob(pattern)
    return matches[0] if matches else None

_GPU_BUSY_PATH  = _find_sysfs("/sys/class/drm/card*/device/gpu_busy_percent")
_GPU_TEMP_PATH  = _find_sysfs("/sys/class/drm/card*/device/hwmon/hwmon*/temp1_input")
_VRAM_USED_PATH = _find_sysfs("/sys/class/drm/card*/device/mem_info_vram_used")
_VRAM_TOTAL_PATH= _find_sysfs("/sys/class/drm/card*/device/mem_info_vram_total")

# ── Détection disques SSD (au démarrage) ─────────────────────────────────────
_disk_prev      = {}   # {devname: SDiskIOCounters}
_disk_prev_time = None
_SSD_DEVICES    = []   # ['nvme0n1', 'sda'] — jusqu'à 2 devices
_SSD_TEMP_PATHS = []   # [path|None, ...]
_SSD_MOUNTS     = []   # ['/', '/media/...']

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
            temps.append(0.0)
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


def collect() -> dict:
    vm      = psutil.virtual_memory()
    cores   = psutil.cpu_percent(percpu=True)
    cores16 = (cores + [0.0] * 16)[:16]
    io      = get_disk_io_per_ssd()
    temps   = get_ssd_temps()
    caps    = get_ssd_capacities()
    vram_used, vram_total = get_vram()
    wifi_ssid, wifi_sig  = get_wifi()

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
        "ssd2_read":  _io(1, 0),
        "ssd2_write": _io(1, 1),
        "ssd2_temp":  _tmp(1),
        "ssd2_used":  _cap(1, 0),
        "ssd2_total": _cap(1, 1),
        "vram_used":  vram_used,
        "vram_total": vram_total,
        "wifi_ssid":  wifi_ssid,
        "wifi_sig":   wifi_sig,
        "vpn_on":     int(get_vpn_status()),
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
        f"S2TMP:{d['ssd2_temp']:.0f}",
        f"S2CAP:{d['ssd2_used']}",
        f"S2TOT:{d['ssd2_total']}",
        f"VUSED:{d['vram_used']:.0f}",
        f"VTOT:{d['vram_total']:.0f}",
        f"WNAM:{d['wifi_ssid']}",
        f"WSIG:{d['wifi_sig']}",
        f"VPN:{d['vpn_on']}",
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

def run(port: str, baud: int, interval: float) -> None:
    psutil.cpu_percent(percpu=True)   # premier appel toujours à 0, on le jette
    time.sleep(0.2)

    reconnect_delay = 3.0

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
            next_send = time.monotonic()

            try:
                while True:
                    now = time.monotonic()
                    if now >= next_send:
                        data       = collect()
                        line_bytes = (format_line(data) + "\n").encode("ascii")
                        if len(line_bytes) > _SERIAL_MAX:
                            print(f"[WARN] Ligne {len(line_bytes)}B > {_SERIAL_MAX} — tronquée", flush=True)
                            line_bytes = line_bytes[:_SERIAL_MAX - 1] + b"\n"
                        try:
                            os.write(fd, line_bytes)
                            if _send_count < 5:
                                print_dashboard(data)
                            elif _send_count == 5:
                                print_dashboard(data)
                                print("(affichage arrêté — envoi continu en arrière-plan)", flush=True)
                        except BlockingIOError:
                            pass   # HWCDC FIFO plein, on réessaie au prochain tour
                        except OSError as exc:
                            raise serial.SerialException(str(exc))
                        next_send = now + interval
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
    args = parser.parse_args()

    port = args.port or auto_detect_port()
    if port is None:
        sys.exit("Aucun port série trouvé. Branchez l'ESP32 et réessayez, "
                 "ou spécifiez --port /dev/ttyACMx")

    print("=== NUC Monitor — vérification démarrage ===")
    _detect_ssd_devices()
    preflight_check(port)

    try:
        run(port, args.baud, args.interval)
    except KeyboardInterrupt:
        print("\nArrêté.")


if __name__ == "__main__":
    main()
