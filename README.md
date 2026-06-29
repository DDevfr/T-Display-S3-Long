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
│ Olympe |||..                  VPN ON │  ← Header : WiFi (SSID + barres)
│ 56%                                  │  ← % signal WiFi (font_12, coloré)
├──────────────────────────────────────┤
│         Arc CPU  %  °C               │  ← CPU % (font_20) + °C, couleur dynamique
│            CPU                       │  ← Label + "Ryzen 9 7940HS" dessous
├──────────────────────────────────────┤
│  Barres 16 cœurs (0-7 / 8-15)        │  ← 2 rangées × 8, numéros sous chaque barre
├──────────────────────────────────────┤
│         Arc GPU  %  °C               │  ← GPU % + °C (Radeon 780M)
│            GPU                       │  ← Label + "Radeon 780M" dessous
├──────────────────────────────────────┤
│ RAM          14.3/62 GB              │  ← Label gauche, valeur droite, barre dessous
| [════════]                           |
│ VRAM          1.5/8 GB               │  ← Idem, VRAM iGPU
| [════════]                           |
├──────────────────────────────────────┤
│ SSD   38°C               123/1832 GB │  ← Titre SSD : temp. centrée, capa. droite
│ R [════════]  12 MB/s                │
│ W [════════]   4 MB/s                │
└──────────────────────────────────────┘
```

**Couleurs dynamiques** (tous les widgets) :
- Pourcentage : < 50 % → vert · < 70 % → jaune · < 85 % → orange · ≥ 85 % → rouge
- Température CPU/GPU : < 60 °C → vert · < 75 °C → jaune · < 85 °C → orange · ≥ 85 °C → rouge
- Signal WiFi : ≥ 70 % → vert · ≥ 40 % → orange · < 40 % → rouge
- VPN : actif → vert · inactif → gris

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
└── install-autostart.sh    # Script d'installation autostart pour linux

lib/
└── lv_conf.h           # Config LVGL (fonts activés)
```

---

## Métriques envoyées (protocole CSV)

```
CPU:45.2,CTEMP:71.0,GPU:12.5,GTEMP:55.0,RAM:68.4,RTOT:62.0,
SREAD:12.3,SWRIT:4.1,STEMP:38.0,SCAP:123,STOT:1832,
VUSED:1489,VTOT:8192,WNAM:Olympe,WSIG:56,VPN:1,
C0:55,C1:12,...,C15:8
```

| Clé | Valeur |
|-----|--------|
| `CPU` | % utilisation CPU global |
| `CTEMP` | Température CPU °C (k10temp/Tctl) |
| `GPU` | % utilisation GPU (gpu_busy_percent sysfs) |
| `GTEMP` | Température GPU °C (amdgpu/edge) |
| `RAM` | % RAM utilisée |
| `RTOT` | RAM totale en GB |
| `SREAD` / `SWRIT` | Débit SSD lecture/écriture en MB/s |
| `STEMP` | Température NVMe °C (sysfs nvme hwmon) |
| `SCAP` / `STOT` | Espace utilisé / total SSD en GB (/) |
| `VUSED` / `VTOT` | VRAM utilisée / totale en MB (sysfs amdgpu) |
| `WNAM` | SSID WiFi (max 8 chars, sanitisé) |
| `WSIG` | Qualité signal WiFi % (nmcli) |
| `VPN` | VPN actif : 1 / inactif : 0 (interface tun/wg détectée) |
| `C0`…`C15` | % par cœur (16 threads) |

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
python tools/monitor_sender.py --interval 0.5      # rafraîchissement 0.5 s (défaut)
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

Procédure à suivre lorsque le service `nuc-monitor` est actif et qu'on souhaite modifier le code.

| Modification | Arrêt service requis | Commandes après édition |
|---|---|---|
| `monitor_sender.py` | Oui | `systemctl start nuc-monitor` |
| Firmware ESP32 | **Oui** (conflit port série) | `pio run … upload` puis `systemctl start` |
| `nuc-monitor.service` | Non | `cp` + `daemon-reload` + `restart` |

### Modifier le script Python (`monitor_sender.py`)

VSCode peut éditer le fichier librement pendant que le service tourne, mais les changements
ne sont actifs qu'après redémarrage du service.

```bash
sudo systemctl stop nuc-monitor        # arrêter le service
# → éditer tools/monitor_sender.py dans VSCode
python3 tools/monitor_sender.py        # test manuel optionnel (Ctrl+C pour arrêter)
sudo systemctl start nuc-monitor       # relancer le service
sudo journalctl -u nuc-monitor -f      # vérifier les logs
```

### Modifier le firmware ESP32 (`.ino` / `.cpp` / `.h`)

**Obligatoire** d'arrêter le service avant le flash : il monopolise `/dev/ttyACM0` et
PlatformIO ne peut pas accéder au port si le service est actif.

```bash
sudo systemctl stop nuc-monitor        # libère /dev/ttyACM0
# → éditer examples/sys_monitor/ dans VSCode
pio run -e sys_monitor -t upload       # compile + flash (depuis le terminal VSCode)
# L'ESP32 reboot automatiquement après le flash (~5 s)
sudo systemctl start nuc-monitor       # relancer le service
sudo journalctl -u nuc-monitor -f      # vérifier les logs
```

### Modifier le fichier service (`nuc-monitor.service`)

Pas besoin d'arrêter le service avant l'édition. Recopier le fichier vers systemd après
modification car c'est la copie dans `/etc/systemd/system/` qui est utilisée au boot.

```bash
# → éditer tools/nuc-monitor.service dans VSCode
sudo cp tools/nuc-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart nuc-monitor
sudo systemctl status nuc-monitor
```

---

## Points techniques notables

- **HWCDC vs HardwareSerial** : l'ESP32-S3 expose `Serial` en HWCDC quand `ARDUINO_USB_CDC_ON_BOOT=1`. Sans ce flag, `Serial.available()` reste toujours à 0.
- **Double-open série** : l'ouverture de `/dev/ttyACM0` sous Linux déclenche un reset USB-JTAG. Le script ouvre deux fois le port (drain + close entre les deux) pour obtenir une session cdc-acm propre.
- **LVGL %f** : `lv_snprintf` (LVGL 8.3) ne supporte pas `%f`. Toutes les valeurs float sont converties en entiers avant formatage (`(int)(val + 0.5f)`).
- **VRAM source** : `/sys/class/drm/card1/device/mem_info_vram_used` et `mem_info_vram_total` (driver amdgpu, pas besoin de ROCm).
- **Temp NVMe** : `/sys/class/nvme/nvme0/hwmon*/temp1_input` (millidegrés → divisé par 1000).
- **VPN detection** : `psutil.net_if_stats()` — toute interface contenant `tun`, `tap`, `vpn` ou `wg` et marquée UP est considérée VPN actif (couvre `qtun`, `tun0`, `wg0`, etc.).

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
