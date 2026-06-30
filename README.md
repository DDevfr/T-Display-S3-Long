# NUC Monitor — T-Display-S3-Long

Moniteur système graphique pour NUC AMD (Ryzen 9 7940HS + Radeon 780M) affiché sur un écran T-Display-S3-Long (ESP32-S3, 180×640 px portrait).

Les métriques sont envoyées du NUC vers l'ESP32 via USB-Serial (CSV) par le script Python `tools/monitor_sender.py`.

---

## Matériel

| Composant | Détail |
|-----------|--------|
| Afficheur | LILYGO T-Display-S3-Long |
| SOC | ESP32-S3R8 (240 MHz) |
| Flash / PSRAM | 16 MB / 8 MB OPI |
| Résolution | 180×640 px |
| Connexion NUC | USB-JTAG / CDC (`/dev/ttyACM0`) |

---

## Layout de l'écran

```
┌──────────────────────────────────────┐
│ Olympe |||..                  VPN ON │  ← ligne 1 : SSID + barres (font_12) | VPN (font_12)
│ 512 KB/s                    14h 09m  │  ← ligne 2 : débit réseau (font_12) | uptime (font_12)
├──────────────────────────────────────┤  ← séparateur header / CPU
│         Arc CPU  %  °C               │  ← CPU % (font_20) + °C, couleur dynamique
│            3.2 GHz                   │  ← fréquence CPU (font_10)
│     CPU  ·  Ryzen 9 7940HS           │  ← labels fixes (font_8)
├──────────────────────────────────────┤
│  Barres 16 cœurs (0-7 / 8-15)        │  ← 2 rangées × 8, numéros colorés sous chaque barre
├──────────────────────────────────────┤
│         Arc GPU  %  °C               │  ← GPU % + °C (Radeon 780M)
│            GPU                       │  ← "GPU" + "Radeon 780M" dessous
├──────────────────────────────────────┤
│ RAM          14/62 GB                │  ← Label gauche, valeur droite, barre dessous
| [════════]                           |
│ VRAM          1/8 GB                 │  ← Idem, VRAM iGPU
| [════════]                           |
├──────────────────────────────────────┤
│ SSD1  38°C               123/1832 GB │  ← Titre SSD1 : temp. centrée, capa. droite
│ R - W [════════]             16 KB/s │  ← R et W en vert si actifs (> 512 KB/s)
├ ─ ─ ─ ─ ─ ─ ─ ─  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤
│ SSD2  --°C               111/1863 GB │  ← SSD2 (USB Crucial — temp n/a, pas de gauge)
└──────────────────────────────────────┘
```

**Couleurs dynamiques** (tous les widgets) :
- Pourcentage : < 50 % → vert · < 70 % → jaune · < 85 % → orange · ≥ 85 % → rouge
- Température CPU/GPU : < 60 °C → vert · < 75 °C → jaune · < 85 °C → orange · ≥ 85 °C → rouge
- Signal WiFi : ≥ 70 % → colore le SSID en vert · ≥ 40 % → orange · < 40 % → rouge
- VPN : actif → vert · inactif → gris
- % CPU et GPU : affichés en bleu (`CLR_GPU`)
- Numéros de cœurs : colorés selon leur activité (même couleur que la barre, > 5 %)

---

## Structure du projet

```
examples/sys_monitor/
├── sys_monitor.ino     # Boucle principale (setup/loop)
├── ui.h / ui.cpp       # Interface LVGL (init + update)
└── serial_parser.h     # Parser CSV non-bloquant

tools/
├── monitor_sender.py       # Script Python NUC → ESP32
├── nuc-monitor.service     # Fichier service systemd
├── install-autostart.sh    # Script d'installation autostart pour linux
├── dev-mode.sh             # Arrête/relance le service pour développement ESP32
└── deploy.sh               # Déploiement complet : arrêt → flash → redémarrage service

lib/
└── lv_conf.h           # Config LVGL (fonts activés)
```

---

## Métriques envoyées (protocole CSV)

```
CPU:65,CTEMP:78,GPU:23,GTEMP:62,RAM:68,RTOT:62,
SREAD:51200,SWRIT:20480,STEMP:38,SCAP:123,STOT:1832,
S2TMP:0,S2CAP:480,S2TOT:1863,
VUSED:1489,VTOT:8192,WNAM:Olympe,WSIG:56,VPN:1,
NTOT:512,CFRQ:32,CPWR:45,UPTS:50998,
CX:55;12;8;6;4;3;2;1;78;45;12;8;5;3;2;1
```

| Clé | Valeur |
|-----|--------|
| `CPU` | % utilisation CPU global (entier) |
| `CTEMP` | Température CPU °C (k10temp/Tctl, entier) |
| `GPU` | % utilisation GPU (gpu_busy_percent sysfs, entier) |
| `GTEMP` | Température GPU °C (amdgpu/edge, entier) |
| `RAM` | % RAM utilisée (entier) |
| `RTOT` | RAM totale en GB (entier) |
| `SREAD` / `SWRIT` | Débit SSD1 (NVMe) lecture/écriture en **KB/s** (entier, précision sub-MB/s) |
| `STEMP` | Température SSD1 °C (sysfs nvme hwmon, entier) |
| `SCAP` / `STOT` | Espace utilisé / total SSD1 en GB |
| `S2TMP` | Température SSD2 °C (0 si USB sans hwmon) |
| `S2CAP` / `S2TOT` | Espace utilisé / total SSD2 en GB |
| `VUSED` / `VTOT` | VRAM utilisée / totale en MB (sysfs amdgpu) |
| `WNAM` | SSID WiFi (max 8 chars, sanitisé) |
| `WSIG` | Qualité signal WiFi % (nmcli) — colore le SSID, non affiché en chiffre |
| `VPN` | VPN actif : 1 / inactif : 0 (interface tun/wg détectée) |
| `NTOT` | Débit réseau total lissé en KB/s (upload + download, EMA α=0.25, interface WiFi) |
| `CFRQ` | Fréquence CPU moyenne × 10 (ex: `32` = 3.2 GHz, `psutil.cpu_freq()`) |
| `CPWR` | Puissance CPU en Watts via RAPL (0 si non lisible sans root) |
| `UPTS` | Uptime système en secondes (`time.time() − psutil.boot_time()`) |
| `CX` | 16 valeurs % par cœur séparées par `;` (ex: `CX:55;12;8;...;1`) |

> **Note SSD2** : le pont USB-SATA ASMedia ASM235C (driver `uas`) ne remonte pas les lectures dans `/proc/diskstats`. La gauge de débit est donc absente pour SSD2 — seules la capacité et la température (toujours `--°C` côté USB) sont affichées.

---

## Installation

### Dépendances Python (NUC)

```bash
pip install psutil pyserial
```

### Lancer manuellement

```bash
python tools/monitor_sender.py                     # auto-détecte /dev/ttyACM*
python tools/monitor_sender.py --port /dev/ttyACM0
python tools/monitor_sender.py --interval 0.25     # rafraîchissement 0.25 s (défaut)
```

Le script effectue un preflight check au démarrage (port, CPU/GPU/SSD temp, WiFi, VPN, RAM, VRAM, SSD) et reconnecte automatiquement en cas de déconnexion USB.

### Démarrage automatique (Zorin OS 18 / systemd)

```bash
sudo bash tools/install-autostart.sh
```

Le script installe un service systemd qui démarre `monitor_sender.py` automatiquement au boot et le relance en cas d'erreur.

Commandes utiles après installation :
```bash
sudo systemctl status nuc-monitor      # état du service
sudo systemctl stop   nuc-monitor      # arrêter
sudo systemctl start  nuc-monitor      # démarrer
sudo systemctl disable nuc-monitor     # désactiver l'autostart
sudo journalctl -u nuc-monitor -f      # logs en direct
```

Pour désinstaller :
```bash
sudo systemctl disable --now nuc-monitor
sudo rm /etc/systemd/system/nuc-monitor.service
sudo systemctl daemon-reload
```

### Flash ESP32 (PlatformIO)

```bash
pio run -e sys_monitor -t upload
```

L'environnement `sys_monitor` dans `platformio.ini` active `-DARDUINO_USB_CDC_ON_BOOT=1` pour que `Serial` utilise le CDC USB-JTAG (HWCDC) et non l'UART0.

---

## Cycle de développement

### Déploiement rapide (cas normal)

```bash
# Firmware modifié (ou firmware + Python) :
bash tools/deploy.sh

# Python uniquement (monitor_sender.py) — pas besoin de reflasher :
bash tools/deploy.sh --no-flash
```

`deploy.sh` enchaîne automatiquement : arrêt du service → flash ESP32 → mise à jour
du fichier service si modifié → redémarrage. Affiche le statut systemd à la fin.

### Développement interactif (test manuel du script Python)

```bash
sudo bash tools/dev-mode.sh            # arrête le service, libère /dev/ttyACM0
python3 tools/monitor_sender.py        # test manuel (Ctrl+C pour arrêter)
sudo bash tools/dev-mode.sh resume     # relancer le service
```

### Commandes utiles

```bash
sudo systemctl status nuc-monitor      # état du service
sudo journalctl -u nuc-monitor -f      # logs en direct
```

---

## Points techniques notables

- **HWCDC vs HardwareSerial** : l'ESP32-S3 expose `Serial` en HWCDC quand `ARDUINO_USB_CDC_ON_BOOT=1`. Sans ce flag, `Serial.available()` reste toujours à 0.
- **Buffer série HWCDC** : le buffer RX logiciel est étendu à 512 octets via `Serial.setRxBufferSize(512)` (défaut = 256). Les buffers de `serial_parser.h` sont également à 512 octets. Le script Python tronque les lignes dépassant 510 octets avant envoi. En cas de ligne trop longue côté firmware, `serial_read_line()` rejette la ligne entière (flag `overflow`) plutôt que de parser des données tronquées.
- **Double-open série** : l'ouverture de `/dev/ttyACM0` sous Linux déclenche un reset USB-JTAG. Le script ouvre deux fois le port (drain + close entre les deux) pour obtenir une session cdc-acm propre.
- **Protocole compact** : les 16 cœurs CPU sont encodés dans un seul champ `CX:v;v;...;v` (séparateur `;`) au lieu de 16 champs `C0`…`C15`. Les débits SSD sont en KB/s entier (pas en MB/s décimal) pour une meilleure précision sub-MB/s. Taille typique d'un message : ~280 octets (max ~295 octets, sous les 510 du buffer).
- **Débit réseau EMA** : `get_net_avg_kbps()` calcule le total upload + download sur l'interface WiFi (`wl*`) et le lisse via une moyenne exponentielle (α=0.25 ≈ constante de temps ~1 s). Affiché en KB/s ou MB/s selon le débit, identique à un indicateur de copie de fichier.
- **Fréquence CPU** : `psutil.cpu_freq()` retourne la fréquence courante en MHz ; transmise × 10 pour conserver une décimale entière (ex: 32 = 3.2 GHz). Décodée côté firmware avec division entière.
- **Puissance CPU RAPL** : `/sys/class/powercap/intel-rapl:0/energy_uj` — lecture root uniquement par défaut. Retourne 0 si non accessible ; l'affichage s'adapte (`X.X GHz` seul, sans `XXW`). Pour l'activer sans root : `SUBSYSTEM=="powercap", ACTION=="add", RUN+="/bin/chmod o+r /sys/class/powercap/intel-rapl:0/energy_uj"` dans `/etc/udev/rules.d/99-rapl.rules`.
- **LVGL %f** : `lv_snprintf` (LVGL 8.3) ne supporte pas `%f`. Toutes les valeurs float sont converties en entiers avant formatage (`(int)(val + 0.5f)`).
- **VRAM source** : `/sys/class/drm/card1/device/mem_info_vram_used` et `mem_info_vram_total` (driver amdgpu, pas besoin de ROCm).
- **Temp NVMe** : `/sys/class/nvme/nvme0/hwmon*/temp1_input` (millidegrés → divisé par 1000).
- **VPN detection** : `psutil.net_if_stats()` — toute interface contenant `tun`, `tap`, `vpn` ou `wg` et marquée UP est considérée VPN actif (couvre `qtun`, `tun0`, `wg0`, etc.).
- **Rétroéclairage PWM** : backlight sur `TFT_BL` (GPIO 1) via LEDC, canal 0, 5 kHz, 8-bit. `BL_BRIGHTNESS = 153` ≈ 60 % dans `sys_monitor.ino` — modifier cette valeur pour ajuster la luminosité (0–255).
- **Gauge SSD1** : barre unique affichant `R+W` cumulés en KB/s. Échelle : 20 000 KB/s (≈ 20 MB/s) = 100 %. Affichage dynamique : `KB/s` sous 10 240 KB/s, `MB/s` au-dessus. Les indicateurs R et W s'allument en vert au-dessus de 512 KB/s.
- **SSD2 sans gauge** : le pont USB-SATA ASMedia ASM235C (driver `uas`, `/dev/sdc`) ne met pas à jour `/proc/diskstats` pour les lectures — seules les écritures fsync'd sont comptabilisées avec délai. La gauge est donc supprimée ; seules la capacité et la température sont affichées.
- **Détection SSD** : `_detect_ssd_devices()` filtre les périphériques avec `taille ≥ 1 GB` pour exclure les gadgets USB 0-octet (sda/sdb exposés par l'ESP32 en mass-storage). Le NVMe est toujours sélectionné en premier.
- **Intervalle polling Python** : 0.25 s par défaut dans `monitor_sender.py`. Configurable via `--interval`.

---

## Problèmes courants

**Le port `/dev/ttyACM0` n'apparaît pas**
→ Maintenir BOOT enfoncé, appuyer sur RST, relâcher RST puis BOOT, puis flasher.

**Données reçues mais affichage figé**
→ Vérifier que `ARDUINO_USB_CDC_ON_BOOT=1` est bien dans les build_flags de `[env:sys_monitor]`.

**La LED verte clignote sans batterie**
→ Normal ; le firmware envoie `reg 0x09 = 0x64` au BQ25896 pour l'éteindre au démarrage.

**Le service systemd n'existe pas / n'a pas démarré après un reboot**
→ Le script d'installation n'a pas encore été exécuté. Lancer une seule fois :
```bash
sudo bash tools/install-autostart.sh
```
Vérifier ensuite que le service est bien activé :
```bash
sudo systemctl is-enabled nuc-monitor   # doit afficher "enabled"
sudo systemctl status nuc-monitor
```

**Le service systemd ne démarre pas**
→ `sudo journalctl -u nuc-monitor -f` pour voir les erreurs. Vérifier que l'ESP32 est branché ou laisser le service : il reconnecte automatiquement.

---

## Bibliothèques

- [LVGL 8.3.0](https://github.com/lvgl/lvgl) — ne pas mettre à jour (rotation logicielle forcée)
- [XPowersLib](https://github.com/lewisxhe/XPowersLib)
- psutil, pyserial (Python)
