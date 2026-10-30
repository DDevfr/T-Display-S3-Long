# NUC Monitor — T-Display-S3-Long

🇬🇧 English | [🇫🇷 Français](README.fr.md)

> Fork of [Xinyuan-LilyGO/T-Display-S3-Long](https://github.com/Xinyuan-LilyGO/T-Display-S3-Long): the original LilyGo examples and libraries are kept in `examples/` and `lib/`, the NUC monitor lives in `examples/sys_monitor/` and `tools/`.

Graphical system monitor for an AMD NUC (Ryzen 9 7940HS + Radeon 780M), shown on a T-Display-S3-Long screen (ESP32-S3, 180×640 px portrait).

Metrics are sent from the NUC to the ESP32 over USB-Serial (CSV) by the Python script `tools/monitor_sender.py`. A second screen, opened with a touch or the BOOT button, shows the top 12 processes with their app icon (see [Screen 2 — Top processes](#screen-2--top-processes)).

<p align="center">
  <img src="images/screen-main.jpg" alt="Screen 1: system metrics (CPU, cores, GPU, RAM, SSD)" width="220">
  &nbsp;&nbsp;
  <img src="images/screen-top-processes.jpg" alt="Screen 2: top 12 processes with app icons" width="220">
</p>
<p align="center"><em>Screen 1: system metrics · Screen 2: top processes</em></p>

> The on-screen texts of the firmware (`En attente du PC...`, `N maj disponibles`…) are in French; they are quoted as-is below.

---

## Hardware

### Board

| Item | Detail |
|------|--------|
| Board | LILYGO T-Display-S3-Long, revision dated **2026-06-20** (CST3530 touch) |
| SoC | ESP32-S3R8: dual-core Xtensa LX7 at 240 MHz, 512 KB SRAM, 2.4 GHz Wi-Fi and Bluetooth LE |
| PSRAM | 8 MB OPI, in the package (the "R8" of ESP32-S3R8) |
| Flash | 16 MB QIO at 80 MHz, partitioned as `huge_app.csv` (3 MB application) |
| Display | 180×640 px, **AXS15231B** controller over QSPI at 32 MHz, PWM backlight |
| Touch | **CST3530** (Hynitron), I2C, chip separate from the display |
| Battery charger | **BQ25896** (Texas Instruments), I2C `0x6A` |
| USB | Type-C, native ESP32-S3 USB-Serial-JTAG (VID:PID `303A:1001`), seen as `/dev/ttyACM0` |
| Buttons | BOOT (GPIO0, used as screen toggle) and RST |

### Pinout used (`pins_config.h`)

| Function | GPIO |
|----------|------|
| Display QSPI: CS / SCK | 12 / 17 |
| Display QSPI: D0 / D1 / D2 / D3 | 13 / 18 / 21 / 14 |
| Display: reset | 16 |
| Backlight (LEDC channel 0, 5 kHz) | 1 |
| I2C (touch + BQ25896): SDA / SCL | 15 / 10 |
| Touch: INT / reset | 11 / 2 |
| BOOT button | 0 |

### Touch revisions

LilyGo changed the touch controller during production without renaming the board. The code for the new revision was published on 2026-05-19:

| Revision | Touch controller | I2C address | Touch reset | LilyGo code |
|----------|------------------|-------------|-------------|-------------|
| Old revision | Built into the AXS15231B | `0x3B` | GPIO16 (shared with the display) | `master` branch, `touch` example |
| CST3530 revision (this board) | Separate **CST3530** | `0x58` (`0x5A` in bootloader) | **GPIO2** | `T-Display-S3-Long-cst3530` branch, `cst3530_touch` example |

This project only supports the CST3530 revision. The LilyGo examples in `examples/` (`factory`, `lvgl_demo`, `TFT`, `QWIIC_Sensor`, `cst3530_touch`) are taken from the `T-Display-S3-Long-cst3530` branch (synced on 2026-10-23) and target this revision. Only `GFX_AXS15231B_Image`, identical in both branches, still queries the old touch controller.

To restore the factory firmware, rebuild the `factory` example (it inherits `HYN_POWER_ON_UPDATA = 0`) rather than flashing LilyGo's prebuilt `factory-cst3530.bin`, which is not included here. That binary is built with `HYN_POWER_ON_UPDATA = 1`: its embedded touch firmware has the same version as the chip on this board (`1010001`), so it should not reflash it, unless the chip had an older version or a failed boot.

The CST3530 of this board identifies itself at boot (driver `[HYN]` messages on the serial port): `ictype:caca220e`, `fw_project_id:2601093`, chip firmware `fw_ver:1010001`.

It is driven by the Hynitron driver supplied by LilyGo (`lib/hyn_driver_for_esp32`), with **`HYN_POWER_ON_UPDATA = 0`** in `hyn_cfg.h`. The driver therefore never reflashes the touch chip's internal firmware: the original cannot be backed up, and an update would be irreversible. Only set this value to `1` if you know what you are doing.

### Tested build environment

| Item | Version |
|------|---------|
| PlatformIO platform | `espressif32` 7.0.1 (pinned in `platformio.ini`) |
| Framework | Arduino-ESP32 2.0.17 (ESP-IDF 4.4) |
| LVGL | 8.3.0-dev, bundled in `lib/lvgl` |
| Touch driver | Hynitron V2.10 (20241111), bundled in `lib/hyn_driver_for_esp32` |

The Hynitron driver is written for ESP-IDF 4.4 (legacy I2C driver, pre-IDF 5 FreeRTOS types): moving to Arduino-ESP32 3.x would require porting it. It shares I2C port 0, already installed by `Wire`, hence the harmless `E (799) i2c: i2c driver install error` message at boot.

---

## Screen layout

```
┌──────────────────────────────────────┐
│ WifiSSID |||..                VPN ON │  ← line 1: SSID + bars (font_12) | VPN (font_12)
│ 512 KB/s                     14h 9m  │  ← line 2: network throughput (font_12) | uptime (font_12, `4j 16h9m` beyond one day)
├──────────────────────────────────────┤  ← header / CPU separator
│         Arc CPU  %  °C               │  ← CPU % (font_20) + °C, dynamic color
│          3.2 GHz  45W                │  ← CPU frequency + package power (font_10, soft orange, centered; `45W` hidden if `CPWR = 0`)
│     CPU  ·  Ryzen 9 7940HS           │  ← fixed labels (font_8)
├──────────────────────────────────────┤
│  16 core bars (0-7 / 8-15)           │  ← 2 rows × 8, colored numbers under each bar
├──────────────────────────────────────┤
│  KB      Arc GPU  %  °C       MS     │  ← GPU % + °C (Radeon 780M); keyboard (left) / mouse (right) batteries
│ [▮▮▮]       GPU              [▮  ]   │  ← "GPU" + "Radeon 780M" below; colored battery icon
│ 100%                          20%    │  ← battery %: green ≥ 60, yellow ≥ 35, orange ≥ 15, red < 15
├──────────────────────────────────────┤
│ RAM          14/62 GB                │  ← label left, value right, bar below
| [════════]                           |
│ VRAM          1/8 GB                 │  ← same, iGPU VRAM
| [════════]                           |
├──────────────────────────────────────┤
│ SSD1 100%  38°C          123/1832 GB │  ← SSD1 title, SMART health, centered temp, capacity right
│  R - W  [══════]             16 KB/s │  ← R and W green when active (> 512 KB/s), gauge centered between both texts
│ SSD2 100%   32°C           480/1863GB│  ← shared line: SSD2 (health + temp + capacity) if UPD == 0, otherwise number of available updates
│                                      │
│      Zorin OS 18.1 (6.17.040)        │  ← status line (bottom): OSKV when connected, otherwise "En attente du PC..." (waiting for the PC)
└──────────────────────────────────────┘
```

> The SSD2 line above is only visible when `UPD == 0` (no update available); otherwise the same line shows `N maj disponibles` (N updates available, orange, centered). If SSD2 health is unavailable (`S2HLTH = 255`) and there is no update, the line stays empty.

**Dynamic colors** (all widgets):
- Percentage: < 50 % → green · < 70 % → yellow · < 85 % → orange · ≥ 85 % → red
- CPU/GPU temperature: < 60 °C → green · < 75 °C → yellow · < 85 °C → orange · ≥ 85 °C → red
- WiFi signal: ≥ 70 % → SSID in green · ≥ 40 % → orange · < 40 % → red
- VPN: active → green · inactive → grey (compatible with most VPNs on the market, see [VPN detection](#vpn-detection))
- CPU and GPU %: shown in blue (`CLR_GPU`)
- CPU frequency + power (`3.2 GHz  45W`): fixed soft orange (`0xE0A060`), deliberately duller than the threshold orange (`0xFF8C00`) so it does not look like an alert
- Core numbers: colored by activity (same color as the bar, > 5 %)
- SSD SMART health: ≥ 90 % → green · ≥ 70 % → orange · < 70 % → red

---

## Project structure

```
examples/sys_monitor/
├── sys_monitor.ino     # Main loop (setup/loop)
├── ui.h / ui.cpp       # LVGL UI (init + update, screen 2 top processes)
├── serial_parser.h     # Non-blocking parser (CPU:, P:, I: frames)
├── icon_cache.h / .cpp # PSRAM cache of app icons (screen 2)
├── touch_cst3530.h / .c # Wrapper around the Hynitron touch driver (CST3530)
├── AXS15231B.h / .cpp  # QSPI display driver (DMA, lcd_sleep/lcd_wake standby)
└── pins_config.h       # Pinout (display, touch, BOOT) and resolution

tools/
├── monitor_sender.py       # Python script NUC → ESP32
├── proc_top.py             # Top 12 processes + app icons (screen 2)
├── nuc-monitor.service     # systemd service template
├── install-autostart.sh    # Autostart install script for Linux
├── dev-mode.sh             # Stops/restarts the service for ESP32 development
└── deploy.sh               # Full deployment: stop → flash → restart service

lib/
├── lv_conf.h              # LVGL config (enabled fonts)
├── lvgl/                  # LVGL 8.3
└── hyn_driver_for_esp32/  # Hynitron/LilyGo touch driver (HYN_POWER_ON_UPDATA = 0)
```

The other folders of `examples/` and `lib/` (`Arduino_GFX`, `Arduino_DriveBus`, `XPowersLib`) come from the original LilyGo repository and are not used by `sys_monitor`. `examples/ESPHome_LVGL_HelloWorld/` is an ESPHome configuration (YAML), outside PlatformIO. The CST3530 datasheet (in Chinese) is in `datasheet/`.

---

## Metrics sent (CSV protocol)

```
CPU:65,CTEMP:78,GPU:23,GTEMP:62,RAM:68,RTOT:62,
SREAD:51200,SWRIT:20480,STEMP:38,SCAP:123,STOT:1832,SHLTH:100,
S2TMP:32,S2CAP:480,S2TOT:1863,S2HLTH:100,
VUSED:1489,VTOT:8192,WNAM:Olympe,WSIG:56,VPN:1,
NTOT:512,CFRQ:32,CPWR:45,UPTS:50998,
OSKV:Zorin OS 18.1 (6.17.040),UPD:3,SCR:1,
KBAT:100,KCHG:0,MBAT:20,MCHG:0,
CX:55;12;8;6;4;3;2;1;78;45;12;8;5;3;2;1
```

| Key | Value |
|-----|-------|
| `CPU` | Overall CPU usage % (integer), average of the 16 threads of `CX` |
| `CTEMP` | CPU temperature °C (k10temp/Tctl, read directly from its hwmon file, integer) |
| `GPU` | GPU usage % (gpu_busy_percent sysfs, integer) |
| `GTEMP` | GPU temperature °C (amdgpu/edge, integer) |
| `RAM` | RAM used % (integer) |
| `RTOT` | Total RAM in GB (integer) |
| `SREAD` / `SWRIT` | SSD1 (NVMe) read/write throughput in **KB/s** (integer, sub-MB/s precision) |
| `STEMP` | SSD1 temperature °C (nvme hwmon sysfs, integer) |
| `SCAP` / `STOT` | SSD1 used / total space in GB |
| `SHLTH` | SSD1 SMART health % (`100 - percent_used`, via UDisks2/D-Bus, no root). `255` = unavailable (no NVMe, or D-Bus/UDisks2 missing), not shown on screen in that case |
| `S2TMP` | SSD2 temperature °C. No hwmon sysfs for this USB-SATA bridge: read via UDisks2/D-Bus (`Drive.Ata.SmartTemperature`, no root). `0` if unavailable |
| `S2CAP` / `S2TOT` | SSD2 used / total space in GB |
| `S2HLTH` | SSD2 health: `100` (green, healthy) / `20` (red, WARN: `SmartFailing`, failing attribute, or bad sector) / `255` = unavailable. No reliable wear % on generic ATA (unlike NVMe), hence a binary status sent as symbolic values. Shown on the updates line, only when `UPD == 0`; with `255`, the whole SSD2 line is hidden |
| `VUSED` / `VTOT` | VRAM used / total in MB (amdgpu sysfs) |
| `WNAM` | WiFi SSID (max 8 chars, sanitized), read from NetworkManager over D-Bus every 5 s |
| `WSIG` | WiFi signal quality % (NetworkManager `AccessPoint.Strength`, same value as `nmcli dev wifi`, refreshed every 5 s): colors the SSID and drives the 5 bars `\|\|\|..`, not shown as a number |
| `VPN` | VPN active: 1 / inactive: 0 (interface UP that is point-to-point or named tun/tap/wg/vpn/nord, checked 1×/s, see [VPN detection](#vpn-detection)) |
| `NTOT` | Smoothed total network throughput in KB/s (upload + download, EMA α=0.25, WiFi interface) |
| `CFRQ` | Average CPU frequency × 10 (e.g. `32` = 3.2 GHz, average of the 16 threads' `scaling_cur_freq`) |
| `CPWR` | APU package power in watts (amdgpu PPT, otherwise RAPL; `0` = no readable source → hidden) |
| `UPTS` | System uptime in seconds (`time.time() − psutil.boot_time()`) |
| `OSKV` | OS name + version + shortened kernel, e.g. `Zorin OS 18.1 (6.17.040)` (max 40 chars, shown on the bottom line when connected) |
| `UPD` | Number of available updates (`/var/lib/update-notifier/updates-available`, refreshed ~1-2×/day by `apt-daily.timer`, not real time). Orange line shown only if > 0 |
| `SCR` | Requested ESP32 screen state: `1` = on, `0` = standby (backlight off + AXS15231B asleep). Missing → `1` |
| `KBAT` / `MBAT` | Keyboard / mouse battery % (UPower via system D-Bus, no root, refreshed every 60 s). `255` = absent → empty column. Sorted by model name (`K780`, `MX Anywhere`…) because UPower reports the Logitech HID++ mouse as type *keyboard* |
| `KCHG` / `MCHG` | `1` = device charging → lightning icon instead of the battery |
| `CX` | 16 per-core % values separated by `;` (e.g. `CX:55;12;8;...;1`) |

> **SSD2 note**: SSD2 throughput (`S2RD`/`S2WR`) is no longer sent: the ASMedia ASM235C USB-SATA bridge (`uas` driver) does not report reads in `/proc/diskstats`. The firmware no longer reads them. SSD2 only appears through `S2HLTH`/`S2TMP`/`S2CAP`/`S2TOT`, on the line shared with updates.

---

## Power measurement (wattage)

The `nnW` figure next to the frequency, under the CPU arc, is the **APU package power** (PPT, *Package Power Tracking*): the whole Ryzen 9 7940HS chip.

| Counted | Not counted |
|---------|-------------|
| 8 Zen 4 cores (16 threads) and their L3 cache | RAM (DDR5 modules) |
| Radeon 780M iGPU | SSD, WiFi, Ethernet, external USB |
| SoC: memory controller, PCIe/USB, display engine, NPU… | Fan, motherboard regulators, power brick |

Power drawn at the wall is therefore higher than this figure (not measured here).

**Source**: `power1_average` of the amdgpu hwmon (label `PPT`, e.g. `/sys/class/drm/card1/device/hwmon/hwmon7/power1_average`, in µW, path resolved at startup), readable without root. It is an estimate computed by the SMU (the Ryzen's power-management microcontroller), which uses it itself to enforce its power limits and pick boost frequencies. The script reads it on every frame (0.25 s), rounds it to the watt and sends it in `CPWR`.

**Smoothing**: the SMU averages the value over ~1 to 2 s. It takes about 2 s to follow a sudden load change (5 to 55 W in ~2.5 s). `power1_input` (instantaneous value) is not used: it sometimes drops to 0 W under full load.

**Typical values measured on this NUC**:

| Situation | `CPWR` |
|-----------|--------|
| Idle (desktop, screen on) | ~5–6 W |
| 8 CPU threads saturated | ~55–58 W |
| iGPU loaded (`glxgears` without vsync, + the CPU feeding it) | ~50 W |

The 7940HS is rated for 35–54 W sustained; the exact value and allowed peaks are set by the NUC maker in the BIOS.

**RAPL fallback**: without the amdgpu hwmon, the script computes power from the RAPL energy counter (`/sys/class/powercap/intel-rapl:0/energy_uj`, `package-0` domain, difference between two reads). This counter exists on this Ryzen (`intel_rapl_msr` module) but is only readable by root since the fixes for the Platypus side-channel attacks (CVE-2020-8694 / CVE-2020-12912): for the service (which runs as the session user, not root), it returns 0. Do not reopen it to other users with a udev rule: PPT gives the same information without weakening that fix.

**No CPU / iGPU split**: this Ryzen (Phoenix, SMU 13.0.4) has no power sensor of its own for the iGPU. amdgpu's `gpu_metrics` file publishes per-core power (`CorePower[8]`) and two rails: `VDDCR_VDD`, which the driver puts in the `average_gfx_power` field despite its name and which actually follows CPU load (55 W under a pure CPU load, barely more than the sum of the cores with the iGPU loaded), so it is not the iGPU power; and `VDDCR_SOC` (~1–2 W). "Total − cores" would only give an approximation (iGPU + L3 + SoC, ~5 W even at idle): the total is therefore shown as is, under the CPU arc. In games or video, it can rise while CPU % stays low, because the iGPU is what draws the power.

**Manual check**:
```bash
cat /sys/class/drm/card*/device/hwmon/hwmon*/power1_label     # should print PPT
cat /sys/class/drm/card*/device/hwmon/hwmon*/power1_average   # µW (5100000 = 5.1 W)
sensors 'amdgpu-pci-*'                                        # line "PPT: 22.17 W (avg = 6.02 W)": avg is what is shown
sudo journalctl -u nuc-monitor | grep Puissance               # source picked when the service started
```
At startup, the preflight prints `Puissance OK n W (<path>)`, or `n/a` if neither PPT nor RAPL is readable (the screen then only shows the frequency).

---

## VPN detection

The `VPN` indicator in the header is **compatible with most VPNs on the market**: it depends neither on the provider nor on its app, but on the network interface the tunnel creates.

**Rule**: the VPN is considered active as soon as a network interface is UP and meets one of these conditions:
- it carries the `pointopoint` flag (point-to-point link). This is the case for WireGuard and OpenVPN (tun mode) tunnels, the two technologies used by nearly all consumer VPNs on Linux;
- its name contains `tun`, `tap`, `vpn`, `wg` or `nord` (`_VPN_NAMES` in `monitor_sender.py`). This safety net notably covers OpenVPN in TAP mode, which is not point-to-point.

Local network interfaces (Ethernet, WiFi, `lo`) and Docker or libvirt bridges do not have this flag: they do not trigger the indicator.

| VPN / technology | Typical interface | Detected |
|------------------|-------------------|----------|
| NordVPN, NordLynx (WireGuard) | `nordlynx` | ✅ tested (NordVPN 5.4.1) |
| NordVPN, OpenVPN | `nordtun` | ✅ |
| Mullvad, Proton VPN, Surfshark, PIA, ExpressVPN, CyberGhost, Windscribe, IVPN… (WireGuard or OpenVPN) | `wg0-mullvad`, `proton0`, `tun0`… | ✅ expected, not tested |
| WireGuard (`wg-quick`) or OpenVPN set up by hand or in NetworkManager | `wg0`, `tun0` | ✅ |
| Corporate VPN via OpenConnect (Cisco AnyConnect, GlobalProtect, Pulse) | `tun0`, `vpn0` | ✅ |
| FortiGate SSL-VPN (`openfortivpn`), L2TP | `ppp0` | ✅ |
| OpenVPN in TAP mode | `tap0` | ✅ (by name) |
| Native IPsec / IKEv2 (strongSwan, Libreswan) | none | ❌ these VPNs usually do not create an interface |

**Known false positives**: a PPPoE or 4G connection (`ppp0`) and Tailscale (`tailscale0`) are seen as a VPN, even when Tailscale is not used as an exit node. This does not happen on this NUC.

**Cost**: no extra cost. The script reuses the `net_if_stats()` call (~0.14 ms) and only adds a string comparison. Detection through the default route (`ip route get 1.1.1.1`), more accurate, was ruled out: it spawns a process on every check (~1.4 ms).

**Manual check**:
```bash
ip -br link                                                   # find the VPN interface (e.g. nordlynx)
python3 -c "import psutil; print({k: v.flags for k, v in psutil.net_if_stats().items()})"   # should contain pointopoint for it
sudo journalctl -u nuc-monitor | grep VPN                     # preflight line: "OK (actif)" or "inactif"
```
If a VPN is not recognized, add a pattern of its interface name to `_VPN_NAMES`.

---

## Installation

### Prerequisites (quick start)

Tested on Zorin OS 18 (Ubuntu 24.04 base). The steps follow those of the original LilyGo repository, adapted to Linux and to this project.

1. **Hardware**: a T-Display-S3-Long, CST3530 revision (see [Touch revisions](#touch-revisions)), and a USB-C cable that carries data (not a charge-only cable).
2. **Base packages**: `python3-venv` is required by the PlatformIO installer.
   ```bash
   sudo apt install git python3-venv
   ```
3. **Serial port access** (flashing and service): add your account to the `dialout` group, then log out and back in.
   ```bash
   sudo usermod -aG dialout $USER
   ```
4. **VS Code**: install [Visual Studio Code](https://code.visualstudio.com/) (`.deb` package) or `sudo snap install code --classic`.
5. **PlatformIO IDE extension**: in VS Code, Extensions tab, search for `PlatformIO IDE`, install it, then restart VS Code. It installs PlatformIO Core in `~/.platformio`, the path used by `tools/deploy.sh`.
6. **Clone the project**, then open it in VS Code (`File` → `Open Folder...`).
   ```bash
   git clone https://github.com/DDevfr/T-Display-S3-Long.git
   ```
7. **First load**: PlatformIO downloads the `espressif32` platform and the Arduino-ESP32 toolchain (several minutes, only once). LVGL and the touch driver are already in `lib/`: no library to install (versions in [Tested build environment](#tested-build-environment)).
8. **Build and flash**: `sys_monitor` is already the default environment in `platformio.ini` (no line to uncomment, unlike the LilyGo repository). Plug in the board, then click ✔ (build), → (upload) and 🔌 (serial monitor) at the bottom left. If flashing fails, see [Troubleshooting](#troubleshooting).
9. **On the NUC**: install the [Python dependencies](#python-dependencies-nuc), test the script by hand ([Run manually](#run-manually)), then install the [autostart](#autostart-zorin-os-18--systemd).

Without VS Code, PlatformIO Core can be installed on its own from the command line, in the same place (`~/.platformio/penv`):
```bash
curl -fsSL -o get-platformio.py https://raw.githubusercontent.com/platformio/platformio-core-installer/master/get-platformio.py
python3 get-platformio.py
```

The Arduino IDE is not supported: the project is only tested with PlatformIO.

### Python dependencies (NUC)

```bash
sudo apt install python3-psutil python3-serial   # the service runs with /usr/bin/python3; pip is blocked there (PEP 668)
sudo apt install python3-dbus   # optional (already on Zorin): WiFi, SSD1/SSD2 SMART health, ESP32 screen standby, mouse/keyboard batteries
sudo apt install python3-pil python3-gi gir1.2-gdkpixbuf-2.0   # optional (already on Zorin): screen 2 icons (Pillow required, GdkPixbuf for SVG)
```

### Run manually

```bash
python tools/monitor_sender.py                     # auto-detects /dev/ttyACM*
python tools/monitor_sender.py --port /dev/ttyACM0
python tools/monitor_sender.py --interval 0.25     # 0.25 s refresh (default)
python tools/monitor_sender.py --sleep-delay 600   # ESP32 standby 600 s after the NUC screen turns off (default, 0 = never)
```

The script runs a preflight check at startup (port, CPU/GPU/SSD temp, SMART health, WiFi, VPN, RAM, VRAM, SSD, power, screen standby) and reconnects automatically after a USB disconnect.

### Autostart (Zorin OS 18 / systemd)

```bash
sudo bash tools/install-autostart.sh
```

The script installs a systemd service that starts `monitor_sender.py` automatically at boot and restarts it on error. The service runs as the account that ran `sudo` (never root) and points to the location of the clone: `tools/nuc-monitor.service` is a template whose `@USER@`, `@GROUP@` and `@PROJECT_DIR@` markers are filled in by `install-autostart.sh` and `deploy.sh`.

Useful commands after installation:
```bash
sudo systemctl status nuc-monitor      # service status
sudo systemctl stop   nuc-monitor      # stop
sudo systemctl start  nuc-monitor      # start
sudo systemctl disable nuc-monitor     # disable autostart
sudo journalctl -u nuc-monitor -f      # live logs
```

To uninstall:
```bash
sudo systemctl disable --now nuc-monitor
sudo rm /etc/systemd/system/nuc-monitor.service
sudo systemctl daemon-reload
```

### Flash the ESP32 (PlatformIO)

```bash
~/.platformio/penv/bin/pio run -e sys_monitor -t upload   # pio is not in the PATH
```

The `sys_monitor` environment in `platformio.ini` enables `-DARDUINO_USB_CDC_ON_BOOT=1` so that `Serial` uses the USB-JTAG CDC (HWCDC) and not UART0.

---

## Development cycle

### Quick deployment (usual case)

```bash
# Firmware changed (or firmware + Python):
bash tools/deploy.sh

# Python only (monitor_sender.py), no reflash needed:
bash tools/deploy.sh --no-flash
```

`deploy.sh` chains automatically: stop the service → flash the ESP32 (except with
`--no-flash`) → update the service file if changed → restart. Shows the systemd
status at the end.

Use `--no-flash` whenever only `monitor_sender.py` (or `nuc-monitor.service`)
changed: it avoids recompiling/reflashing the ESP32 for nothing, and restarts the
service with the up-to-date Python code in a few seconds.

### Interactive development (manual test of the Python script)

```bash
sudo bash tools/dev-mode.sh            # stops the service, frees /dev/ttyACM0
python3 tools/monitor_sender.py        # manual test (Ctrl+C to stop)
sudo bash tools/dev-mode.sh resume     # restart the service
```

### Useful commands

```bash
sudo systemctl status nuc-monitor      # service status
sudo journalctl -u nuc-monitor -f      # live logs
```

---

## Screen 2 — Top processes

A **touch on the screen** or a press on the **BOOT button** (GPIO0) switches from the main screen to the top 12 processes; another touch or press goes back to the main screen (no automatic return). Pressing BOOT while running only switches screens: it only puts the ESP32 in flash mode if held during a press on RST. Each line: app icon (the same as in the GNOME system monitor) + process name + `top`-style CPU % (100 % = one saturated thread, up to 1600 % over the 16 threads), with a 4 px bar and the `pct_color()` color. The title shows the overall CPU.

```
┌──────────────────────────────────────┐
│ TOP CPU                     CPU 23%  │
├──────────────────────────────────────┤
│ [ic]  code                    75%    │  ← 32×32 icon received from the PC
│       ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬                │
│ [B ]  brave                   12%    │  ← badge (initial) until the icon has arrived
│       ▬▬▬                            │
│  …    12 lines of 48 px              │
└──────────────────────────────────────┘
```

### PC ↔ ESP32 exchanges

- **Python produces the data**: it does not know which screen is shown and sends the top processes all the time.
- **The ESP32 displays and switches locally**: the touch (or the BOOT button) does not go through the PC (instant switch, screen 2 already up to date).
- **The only case where the ESP32 talks to the PC**: it asks for an icon it is missing.

```
      NUC (Python)                          USB cable                    ESP32
 ═════════════════════════                                  ═══════════════════════════
 ┌─ Main loop ─────────────┐
 │                         │   ① every 0.25 s
 │  system metrics ────────┼──── CPU:45,CTEMP:62,...,CX:.. ──────►  Screen 1
 │                         │   ② every 1 s (+0.125 s)
 │  top 12 processes ──────┼──── P:a1b2;153;firefox|c3d4;42;code|.. ►  keeps the top 12
 │  (/proc)                │                                            │
 │                         │                                   icon a1b2 known?
 │                         │                                    ├─ yes → shown
 │                         │                                    └─ no → badge "F"
 │                         │   ③ icon request                           │
 │  reads requests ◄───────┼──────────────── ?I:a1b2 ◄───────────────┘ (retry / 2 s)
 │        ▼                │   ④ icon in 8 chunks
 │  send queue ────────────┼──── I:a1b2;0..7;8;<base64> ──────────►  PSRAM cache (48)
 │  (max 1 icon / 100 ms)  │                                         hash check → shown
 └─────────▲───────────────┘
 ┌─ Separate thread ───────┐                                    ┌─────────────────┐
 │  process → app          │                                    │ TOUCH / BOOT    │
 │  → theme icon           │                                    │ screen 1 ⇄ 2    │
 │  → 32×32 → hash (cache) │                                    │ (without the PC)│
 └─────────────────────────┘                                    └─────────────────┘
```

> `a1b2` is a shortened hash: actually 8 hexadecimal characters.

| Direction | Frame | Frequency | Content |
|-----------|-------|-----------|---------|
| PC → ESP | `P:h;pct;name\|h;pct;name\|…` | 1 s | 12 entries max. `h` = icon hash as 8 hex digits (`00000000` = no icon yet); `pct` = CPU % × 10 as integer (e.g. `153` = 15.3 %); `name` = process name (15 chars max, ASCII, `\|` `;` `,` `:` replaced by `_`). ~380 bytes worst case |
| PC → ESP | `I:h;idx;n;<base64>` | on request | Chunk `idx` (0–7) of `n` = 8 of a 32×32 big-endian RGB565 icon (2048 bytes, alpha pre-blended on the `0x0D0D0D` background): 256 bytes per chunk, 360 characters per line |
| ESP → PC | `?I:h` | when an icon is missing | Icon request, retried every 2 s until complete |

`h` is the **32-bit FNV-1a hash of the icon content** (never 0), computed on both sides.

| Situation | What happens |
|-----------|--------------|
| `P:` frame lost or corrupted | Screen 1 is not affected; the next one arrives 1 s later |
| The ESP32 reboots (empty cache) | It sees unknown hashes and requests the icons again on its own |
| Damaged icon chunk | The recomputed hash does not match → icon rejected then requested again |
| Process without an app (daemon, script, kernel thread) | Generic `application-x-executable` icon, like the system monitor |
| Several processes with the same icon | Same hash → sent and stored only once |
| No `P:` frame for 5 s | Screen 2 is cleared |

**NUC side** (`tools/proc_top.py`):
- CPU % is computed by reading `/proc/<pid>/stat` directly (~6 ms for ~480 processes, versus ~20 ms via psutil); name and executable are only read for the top 12.
- A process's app is found, in order, by: the app id of the systemd scope (`app-gnome-brave\x2dbrowser-….scope` → `brave-browser.desktop`), provided the executable lives in the app's folder (so a `bash` started in the VS Code terminal keeps the generic icon); the executable name (`Exec=`, `StartupWMClass=`); the app's private folder (Brave helpers, placed in the `org.chromium.Chromium` scope, are recognized by `/opt/brave.com/brave/`).
- The icon is looked up in the active theme (`org.gnome.desktop.interface icon-theme`, read without a graphical session since the service has no `DISPLAY`), its inherited themes, `hicolor` then `/usr/share/pixmaps`; loaded by GdkPixbuf (PNG/SVG/XPM) then converted by Pillow.
- Lookup and rendering run in a separate thread: until an icon is ready, the hash sent is `0` and the ESP32 shows the badge. Renders are cached in `~/.cache/nuc-monitor/icons/` (key = path + modification date of the image). No external command is spawned.
- Without Pillow, `P:` frames are sent without icons (badges only).

**Touch and button**: the CST3530 chip is described in [Hardware](#hardware). The driver reads touch points in its own task, on interrupt (GPIO11). `touch_cst3530.c` wraps it, because its header redefines `bool`, `NULL`, `HIGH`… and must not be included in the `.ino`. A finger only counts as down if an interrupt arrived within the last 200 ms, so that a lost release report does not leave a "stuck" press. A switch requires the finger to have been lifted for at least 150 ms, and 400 ms since the previous switch. The BOOT button has a 30 ms debounce. Neither screen scrolls: otherwise a finger swipe would move the whole content off screen (black screen). At boot, the driver writes its `[HYN]` messages to the serial port with `printf`, and the PC script ignores them.

**ESP32 side**: `icon_cache.cpp` keeps 48 icons in PSRAM (~96 KB, LRU eviction); `loop()` handles up to 16 lines per pass to absorb the 8 lines of an icon.

### Timing and offset of frames

The `CPU:` (0.25 s), `P:` (1 s) and `I:` (on request) frames do not interfere:

- **A single sender**: only one Python loop writes to the port, lines go out one after the other and cannot get mixed.
- **The ESP32 splits by line** (`\n`) and routes each line by its prefix (`P:`, `I:`, otherwise main frame).
- **Offset**: `P:` goes out 0.125 s after the main frame, and never in the same loop pass.
- **Single output buffer**: if the USB FIFO is full, `os.write` only writes part of it; the rest is kept and sent as soon as the FIFO has room (`select()` watches the port for writing) instead of being lost. If the ESP32 stops reading altogether (more than 1 KB pending), new screen frames are skipped rather than piled up.
- **Icons last**: the 8 lines of an icon (~2.9 KB) only go out when no screen frame is waiting, at most one icon every 100 ms. The ESP32 RX buffer is 4096 bytes.

```
0 ──── 0.125 ──── 0.25 ──── 0.5 ──── 0.75 ──── 1.0 ──── 1.125
[CPU]   [P:]      [CPU]     [CPU]    [CPU]     [CPU]    [P:]
```

---

## Notable technical points

- **HWCDC vs HardwareSerial**: the ESP32-S3 exposes `Serial` as HWCDC when `ARDUINO_USB_CDC_ON_BOOT=1`. Without this flag, `Serial.available()` always stays at 0.
- **HWCDC serial buffer**: the software RX buffer is extended to 4096 bytes via `Serial.setRxBufferSize(4096)` (default = 256) to absorb a full icon (8 `I:` lines) during an LVGL render. The line buffer of `serial_parser.h` stays at 512 bytes. `Serial.setTxTimeoutMs(0)`: `?I:` requests never block if the PC is not reading. The Python script truncates lines over 510 bytes before sending. If a line is too long on the firmware side, `serial_read_line()` rejects the whole line (`overflow` flag) rather than parsing truncated data.
- **Serial double-open**: opening `/dev/ttyACM0` on Linux triggers a USB-JTAG reset. The script opens the port twice (drain + close in between) to get a clean cdc-acm session.
- **Compact protocol**: the 16 CPU cores are encoded in a single `CX:v;v;...;v` field (`;` separator) instead of 16 `C0`…`C15` fields. SSD throughput is in integer KB/s (not decimal MB/s) for better sub-MB/s precision. Typical message size: ~330 bytes measured, computed worst case ~415 bytes (40-char OSKV, 16 cores at 100 %, 7-digit SSD throughput, 6-digit network throughput), i.e. ~95 bytes of margin under the 510-byte buffer. Check this budget before adding any field.
- **`OSKV` shortening**: the kernel version (`platform.release()`, e.g. `6.17.0-40-generic`) is compacted by dropping alphabetic segments (`generic`, `lowlatency`, ...) and concatenating the remaining numeric segments without a dash to the first segment: `6.17.0-40-generic` → `6.17.040`. The final `OS_NAME OS_VERSION (kernel)` string is truncated to 40 characters and stripped of `,`/`:` (protocol delimiters) before sending. Computed once at script startup (does not change while running).
- **Network throughput EMA**: `get_net_avg_kbps()` computes total upload + download on the WiFi interface (`wl*`) and smooths it with an exponential moving average (α=0.25 ≈ ~1 s time constant). Shown in KB/s or MB/s depending on the rate, like a file-copy indicator.
- **CPU frequency**: average of `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` (kHz, paths resolved at startup; this is what `psutil.cpu_freq()` averages, used as fallback); sent × 10 to keep one decimal as an integer (e.g. 32 = 3.2 GHz). Decoded on the firmware side by dividing by 10.
- **Package power (`CPWR`)**: read from `power1_average` of the amdgpu hwmon (PPT), RAPL as fallback. See [Power measurement (wattage)](#power-measurement-wattage).
- **LVGL %f**: `lv_snprintf` (LVGL 8.3) does not support `%f`. All float values are converted to integers before formatting (`(int)(val + 0.5f)`).
- **VRAM source**: `/sys/class/drm/card1/device/mem_info_vram_used` and `mem_info_vram_total` (amdgpu driver, no ROCm needed).
- **NVMe temp**: `/sys/class/nvme/nvme0/hwmon*/temp1_input` (millidegrees → divided by 1000).
- **VPN detection**: `psutil.net_if_stats()`, 1×/s (`_VPN_INTERVAL`), value cached in between. Criteria, compatibility and limits: see [VPN detection](#vpn-detection).
- **WiFi**: SSID and signal strength of the active access point are read from NetworkManager on the system D-Bus (`Device.Wireless.ActiveAccessPoint` → `AccessPoint.Ssid` / `Strength`), every 5 s (`_WIFI_INTERVAL`): NetworkManager only refreshes the strength when it scans. Previously, the script ran `nmcli` 4×/s: more than half of the service's CPU went into these processes, and `nmcli` sometimes took several seconds to answer (empty SSID). `nmcli` is now only a fallback if `python3-dbus` is missing, run with `LC_ALL=C` so as not to depend on the language (`yes`/`oui`).
- **Temperatures**: `CTEMP` is read directly from the `k10temp` hwmon file (`Tctl`), resolved at startup; `psutil.sensors_temperatures()`, which rereads every sensor (~2 ms), is only a fallback.
- **Send loop**: between passes, the script sleeps in `select()` until the next deadline (main frame, `P:` frame, standby check, icon), an `?I:` request from the ESP32 or room in the output FIFO (max 0.25 s). About 20 wake-ups/s instead of 100 with the former `sleep(0.01)`. The port is only read when `select()` reports it readable: in raw mode (`VMIN=0`), `read()` returns 0 bytes when there is nothing to read, and 0 bytes after "readable" means the port hung up (unplug → reconnect).
- **CPU cost**: ~2 % of one thread for the whole service (measured over 30 s), with no child process. To measure it: compare `usage_usec` in `/sys/fs/cgroup/system.slice/nuc-monitor.service/cpu.stat` a few minutes apart (`top` does not show the CPU of child processes).
- **PWM backlight**: backlight on `TFT_BL` (GPIO 1) via LEDC, channel 0, 5 kHz, 8-bit. `BL_BRIGHTNESS = 153` ≈ 60 % in `sys_monitor.ino`; change this value to adjust brightness (0–255).
- **Display DMA counters**: `transfer_num` (DMA transactions in flight) and `lcd_PushColors_len` (pixels left to queue) are modified both by `lcd_PushColors()` and by the end-of-transaction interrupt `spi_dma_cd()`, which runs on the same core as `loop()`. On the task side, they are updated with interrupts masked (`portSET_INTERRUPT_MASK_FROM_ISR()`). Without this masking, an interrupt landing in the middle of `transfer_num++` lost a decrement: the counter stayed at 1, `loop()` stopped calling `lv_timer_handler()` (frozen screen, touch ignored) and the next standby got stuck in `screen_sleep()`, backlight on. The freeze happened at random, after a few hours or days.
- **SSD1 gauge**: single bar showing combined `R+W` in KB/s, centered between the `R - W` labels and the throughput shown on the right. Scale: 20,000 KB/s (≈ 20 MB/s) = 100 %. Dynamic display: `KB/s` under 10,240 KB/s, `MB/s` above. The R and W indicators turn green above 512 KB/s.
- **SSD1 SMART health**: read via the D-Bus interface `org.freedesktop.UDisks2.NVMe.Controller` (`SmartGetAttributes` method, `percent_used` property), exposed by the `UDisks2` service already running on the system: **no root needed** (unlike classic `smartctl`/`nvme-cli`, which need direct access to the `/dev/nvme0` device). Only available for the NVMe drive (SSD1); the Python `dbus` module (system package `python3-dbus`, already present) is optional: without it, only this feature is disabled. The D-Bus read is throttled to 1×/60 s in the script (`_SSD_HEALTH_INTERVAL`), as SMART health does not change fast enough to justify a call every 0.25 s cycle.
- **SSD2 health + temperature**: SSD2 (Crucial CT2000MX500SSD1, ASMedia ASM235C USB-SATA bridge) has no standardized "wear %" SMART attribute like NVMe (proprietary ATA attributes vary by maker); it is read instead via the `org.freedesktop.UDisks2.Drive.Ata` interface (ATA passthrough/SAT through the USB bridge, still without root). The health status is based on `SmartFailing` (official aggregate, equivalent to `smartctl -H`), `SmartNumAttributesFailing` and `SmartNumBadSectors`: shown as symbolic values `100 %` (healthy, green) / `20 %` (WARN, red) rather than a really measured percentage, to stay visually consistent with the SSD1 gauge without implying false precision. The temperature (`SmartTemperature`, missing from any hwmon sysfs for this USB bridge) is read from the same interface. The script reads the values already cached in UDisks2, every 60 s (`_refresh_ssd2_smart()`). It does not call `SmartUpdate()`: this method requires a polkit authorization tied to an active session, which is denied (`NotAuthorizedCanObtain`) for a systemd service without a session. UDisks2 refreshes these values on its own, a few minutes late at most, which is enough for a slowly changing indicator.
- **No SSD2 throughput**: the ASMedia ASM235C USB-SATA bridge (`uas` driver, `/dev/sdc`) does not update `/proc/diskstats` for reads; only fsync'd writes are counted, with a delay. The SSD2 gauge was removed and `S2RD`/`S2WR` are no longer sent; only SSD2 health, temperature and capacity are shown (line shared with updates, visible when `UPD == 0`).
- **SSD detection**: `_detect_ssd_devices()` keeps devices with `size ≥ 1 GB` to exclude 0-byte USB gadgets (sda/sdb exposed by the ESP32 as mass storage). The NVMe is always picked first.
- **Python polling interval**: 0.25 s by default in `monitor_sender.py`. Configurable with `--interval`.
- **ESP32 screen standby**: every second, the script reads `PowerSaveMode` of `org.gnome.Mutter.DisplayConfig` on the session D-Bus (`/run/user/<uid>/bus`, reachable by the service because it runs as the session user): this is the real DPMS state of the NUC's screen (0 = on, 3 = off), which turns off after the GNOME "Blank screen" delay (`org.gnome.desktop.session idle-delay`, 600 s here). `--sleep-delay` s after it turns off (600 s by default, i.e. ~20 min of total inactivity), the script sends `SCR:0`: the ESP32 turns off the backlight, puts the AXS15231B to sleep (`0x28` + `0x10`) and stops LVGL rendering (data is still received and applied). As soon as mouse/keyboard turn the NUC's screen back on (including on the lock screen), `SCR:1` is sent immediately → wake-up in ≤ 1 s (`0x11`, 120 ms, `0x29` + full redraw). `ScreenSaver.Active` is not used because it stays true while the lock screen is shown. Without a GNOME session (boot, greeter), the state is unknown and the screen stays on; if the PC sends nothing for 5 s, the ESP32 wakes up to show "En attente du PC..." (waiting for the PC). During standby, the ESP32 stays awake (no deep/light sleep) because it must keep listening on USB CDC. Quick test: `python tools/monitor_sender.py --sleep-delay 10` then `xset dpms force off`.
- **Mouse / keyboard batteries**: read via `org.freedesktop.UPower` on the system D-Bus (`EnumerateDevices` then the `Percentage`, `State`, `Model`, `Type` properties), without root: UPower already aggregates the Logitech HID++ receiver (MX Anywhere 3S mouse, `hidpp_battery_*`) and BlueZ (K780 keyboard over Bluetooth). Only devices with `PowerSupply == false` and `IsPresent == true` are kept. UPower reports **both** as `Type = 6` (keyboard), hence sorting by model name (`keyboard|clavier|K###` → keyboard, `mouse|souris|MX Anywhere/Master/Vertical|M###` → mouse), `Type` only being a fallback. Read throttled to 1×/60 s (`_PERIPH_BAT_INTERVAL`). On screen, two columns on either side of the GPU arc (`KB` on the left, `MS` on the right): LVGL battery icon (`LV_SYMBOL_BATTERY_FULL/3/2/1/EMPTY`, or `LV_SYMBOL_CHARGE` when charging) + %, colored green (≥ 60 %), yellow (≥ 35 %), orange (≥ 15 %) or red (< 15 %). The Bluetooth keyboard % is the one stored by BlueZ: it is only updated when the keyboard sends it (infrequently), and stays shown even with the keyboard off.

---

## Troubleshooting

**The `/dev/ttyACM0` port does not appear**
→ Hold BOOT, press RST, release RST then BOOT, then flash.

**Data received but display frozen**
→ Check that `ARDUINO_USB_CDC_ON_BOOT=1` is in the build_flags of `[env:sys_monitor]`.
→ If the screen freezes after hours of operation (touch and BOOT button ignored, backlight staying on in standby): firmware older than the DMA counter fix (see [Notable technical points](#notable-technical-points)), reflash it with `bash tools/deploy.sh`.

**The green LED blinks without a battery**
→ Normal; the firmware sends `reg 0x09 = 0x64` to the BQ25896 to turn it off at boot.

**The systemd service does not exist / did not start after a reboot**
→ The install script has not been run yet. Run it once:
```bash
sudo bash tools/install-autostart.sh
```
Then check that the service is enabled:
```bash
sudo systemctl is-enabled nuc-monitor   # should print "enabled"
sudo systemctl status nuc-monitor
```

**The ESP32 screen never goes to standby**
→ Check the preflight line `Veille écran` in `sudo journalctl -u nuc-monitor`: if it shows `n/a`, the session D-Bus or Mutter is not reachable (no GNOME session open, or `python3-dbus` missing). Also check that GNOME does turn the screen off (Settings → Power → "Blank screen") and that `--sleep-delay` is not `0`. Test: `busctl --user get-property org.gnome.Mutter.DisplayConfig /org/gnome/Mutter/DisplayConfig org.gnome.Mutter.DisplayConfig PowerSaveMode` should return `i 3` after `xset dpms force off`.

**Mouse/keyboard batteries do not show (empty columns next to the GPU arc)**
→ Check that UPower sees the devices: `upower -d` should list the mouse (`hidpp_battery_*`) and the keyboard (`keyboard_dev_*`) with a `percentage`. If a device is listed but shown on the wrong side, its model name does not match the `_KBD_MODEL_RE` / `_MOUSE_MODEL_RE` patterns of `monitor_sender.py`: extend them. Values are refreshed every 60 s, so wait up to 1 min after a change (plugged in to charge, keyboard turned back on).

**The WiFi SSID is empty or the signal stays at 0**
→ Check that NetworkManager sees the access point: `busctl get-property org.freedesktop.NetworkManager /org/freedesktop/NetworkManager org.freedesktop.NetworkManager Devices` then, on the WiFi device, `ActiveAccessPoint` (`/` = not connected). Values are refreshed every 5 s: wait up to 5 s after a reconnection. Without `python3-dbus`, the script falls back to `nmcli`.

**The power (`nnW`) does not show next to the CPU frequency**
→ The script sends `CPWR:0`, which the screen hides. Check the `Puissance` preflight line (`sudo journalctl -u nuc-monitor | grep Puissance`): `n/a` means neither amdgpu PPT nor RAPL is readable. Check `cat /sys/class/drm/card*/device/hwmon/hwmon*/power1_average` (see [Power measurement](#power-measurement-wattage)). A service started with an old version of the script (which only read RAPL, root-only) always shows 0: redeploy with `bash tools/deploy.sh --no-flash`.

**Screen 2 stays empty or icons stay as badges**
→ Empty screen 2: the Python script has not sent a `P:` frame for 5 s (old script version, or script stopped); rerun `bash tools/deploy.sh --no-flash`. Permanent badges: Pillow is missing (`sudo apt install python3-pil`), or the app has no icon that can be found; the badge is then the normal behavior. Already rendered icons are in `~/.cache/nuc-monitor/icons/`, and this folder can be deleted safely.

**Touch does not respond (the BOOT button does)**
→ Look at the `[HYN]` messages sent at boot: stop the service (`sudo bash tools/dev-mode.sh`), open the serial port (`~/.platformio/penv/bin/pio device monitor`) and press RST. A line `IC_info ... ictype:caca220e` confirms that the CST3530 answers. Without it, the board may be the old revision (touch built into the AXS15231B at `0x3B`, see [Hardware](#hardware)), which this firmware does not support. Do not enable `HYN_POWER_ON_UPDATA` to "repair" the chip: updating its firmware is irreversible.

**The VPN indicator stays grey while the VPN is connected**
→ The script does not recognize the VPN interface. Before October 2026, only names containing `tun`/`tap`/`vpn`/`wg` were recognized: NordVPN with NordLynx (`nordlynx`) stayed grey. Redeploy the script (`bash tools/deploy.sh --no-flash`), then follow the check in [VPN detection](#vpn-detection). An IPsec VPN without an interface cannot be detected.

**The systemd service does not start**
→ `sudo journalctl -u nuc-monitor -f` to see the errors. Check that the ESP32 is plugged in, or leave the service running: it reconnects automatically.

---

## Libraries

- [LVGL 8.3.0](https://github.com/lvgl/lvgl): do not update (forced software rotation)
- Hynitron V2.10 touch driver, supplied by LilyGo ([`T-Display-S3-Long-cst3530` branch](https://github.com/Xinyuan-LilyGO/T-Display-S3-Long/tree/T-Display-S3-Long-cst3530)), `HYN_POWER_ON_UPDATA` left at `0`
- psutil, pyserial (Python)
- dbus-python (`python3-dbus`, optional: WiFi, SMART, standby, batteries)
- Pillow, PyGObject / GdkPixbuf (Python, optional: screen 2 icons)
