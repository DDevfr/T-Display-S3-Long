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
│ SSD1 100%  38°C          123/1832 GB │  ← Titre SSD1, santé SMART, temp. centrée, capa. droite
│  R - W  [══════]             16 KB/s │  ← R et W en vert si actifs (> 512 KB/s), gauge centrée entre les 2 textes
│ SSD2 100%   32°C           480/1863GB│  ← ligne partagée : SSD2 (santé+temp.+capa.) si UPD == 0, sinon msg sur le nombre de maj disponibles
│                                      │
│      Zorin OS 18.1 (6.17.040)        │  ← ligne de statut (bas d'écran) : OSKV si connecté, sinon "En attente du PC..."
└──────────────────────────────────────┘
```

> La ligne SSD2 ci-dessus n'est visible que quand `UPD == 0` (aucune mise à jour dispo) — sinon cette même ligne affiche `N mises à jour disponibles` (orange, centré), comme avant l'ajout de SSD2.

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
├── serial_parser.h     # Parser CSV non-bloquant
├── AXS15231B.h / .cpp  # Driver écran QSPI (DMA, veille lcd_sleep/lcd_wake)
└── pins_config.h       # Brochage et résolution

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
SREAD:51200,SWRIT:20480,STEMP:38,SCAP:123,STOT:1832,SHLTH:100,
S2TMP:32,S2CAP:480,S2TOT:1863,S2HLTH:100,
VUSED:1489,VTOT:8192,WNAM:Olympe,WSIG:56,VPN:1,
NTOT:512,CFRQ:32,CPWR:45,UPTS:50998,
OSKV:Zorin OS 18.1 (6.17.040),UPD:3,SCR:1,
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
| `SHLTH` | % de santé SMART SSD1 (`100 - percent_used`, via UDisks2/D-Bus, sans root). `255` = indisponible (pas de NVMe, ou D-Bus/UDisks2 absent) — non affiché sur l'écran dans ce cas |
| `S2TMP` | Température SSD2 °C. Pas de sysfs hwmon pour ce pont USB-SATA : lue via UDisks2/D-Bus (`Drive.Ata.SmartTemperature`, sans root). `0` si indisponible |
| `S2CAP` / `S2TOT` | Espace utilisé / total SSD2 en GB |
| `S2HLTH` | Santé SSD2 : `100` (vert, sain) / `20` (rouge, WARN — `SmartFailing`, attribut en échec, ou secteur défectueux) / `255` = indisponible. Pas de % d'usure fiable sur ATA générique (contrairement au NVMe), d'où un statut binaire affiché en valeurs symboliques. Affiché sur la ligne des mises à jour, uniquement quand `UPD == 0` |
| `VUSED` / `VTOT` | VRAM utilisée / totale en MB (sysfs amdgpu) |
| `WNAM` | SSID WiFi (max 8 chars, sanitisé) |
| `WSIG` | Qualité signal WiFi % (nmcli) — colore le SSID, non affiché en chiffre |
| `VPN` | VPN actif : 1 / inactif : 0 (interface tun/wg détectée) |
| `NTOT` | Débit réseau total lissé en KB/s (upload + download, EMA α=0.25, interface WiFi) |
| `CFRQ` | Fréquence CPU moyenne × 10 (ex: `32` = 3.2 GHz, `psutil.cpu_freq()`) |
| `CPWR` | Puissance CPU en Watts via RAPL (0 si non lisible sans root) |
| `UPTS` | Uptime système en secondes (`time.time() − psutil.boot_time()`) |
| `OSKV` | Nom OS + version + noyau tronqué, ex `Zorin OS 18.1 (6.17.040)` (max 40 chars, affiché sur la ligne du bas quand connecté) |
| `UPD` | Nombre de mises à jour dispo (`/var/lib/update-notifier/updates-available`, rafraîchi ~1-2x/jour par `apt-daily.timer` — pas temps réel). Ligne orange affichée uniquement si > 0 |
| `SCR` | État souhaité de l'écran ESP32 : `1` = allumé, `0` = veille (rétroéclairage coupé + AXS15231B en sleep). Absent → `1` |
| `CX` | 16 valeurs % par cœur séparées par `;` (ex: `CX:55;12;8;...;1`) |

> **Note SSD2** : les débits SSD2 (`S2RD`/`S2WR`) ne sont plus envoyés — le pont USB-SATA ASMedia ASM235C (driver `uas`) ne remonte pas les lectures dans `/proc/diskstats`. Le firmware sait encore les parser (compatibilité) mais ne les affiche pas. SSD2 n'apparaît qu'à travers `S2HLTH`/`S2TMP`/`S2CAP`/`S2TOT`, sur la ligne partagée avec les mises à jour.

---

## Installation

### Dépendances Python (NUC)

```bash
pip install psutil pyserial
sudo apt install python3-dbus   # optionnel (déjà présent sur Zorin) : santé SMART SSD1/SSD2 + veille écran ESP32
```

### Lancer manuellement

```bash
python tools/monitor_sender.py                     # auto-détecte /dev/ttyACM*
python tools/monitor_sender.py --port /dev/ttyACM0
python tools/monitor_sender.py --interval 0.25     # rafraîchissement 0.25 s (défaut)
python tools/monitor_sender.py --sleep-delay 600   # veille ESP32 600 s après l'extinction de l'écran du NUC (défaut, 0 = jamais)
```

Le script effectue un preflight check au démarrage (port, CPU/GPU/SSD temp, santé SMART, WiFi, VPN, RAM, VRAM, SSD, veille écran) et reconnecte automatiquement en cas de déconnexion USB.

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

`deploy.sh` enchaîne automatiquement : arrêt du service → flash ESP32 (sauf avec
`--no-flash`) → mise à jour du fichier service si modifié → redémarrage. Affiche
le statut systemd à la fin.

Utiliser `--no-flash` dès que seul `monitor_sender.py` (ou `nuc-monitor.service`)
a changé : ça évite de recompiler/reflasher l'ESP32 pour rien, et redémarre le
service avec le code Python à jour en quelques secondes.

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
- **Protocole compact** : les 16 cœurs CPU sont encodés dans un seul champ `CX:v;v;...;v` (séparateur `;`) au lieu de 16 champs `C0`…`C15`. Les débits SSD sont en KB/s entier (pas en MB/s décimal) pour une meilleure précision sub-MB/s. Taille typique d'un message : ~295 octets mesurés, pire cas estimé ~385 octets (OSKV à 40 caractères, 16 cœurs à 100 %, débits SSD à 7 chiffres), soit plus de 120 octets de marge sous les 510 du buffer. Vérifier ce budget avant tout ajout de champ.
- **Troncature `OSKV`** : la version noyau (`platform.release()`, ex: `6.17.0-40-generic`) est compactée en jetant les segments alphabétiques (`generic`, `lowlatency`, ...) et en concaténant sans tiret les segments numériques restants avec le premier segment : `6.17.0-40-generic` → `6.17.040`. La chaîne finale `OS_NAME OS_VERSION (kernel)` est tronquée à 40 caractères et nettoyée des `,`/`:` (délimiteurs du protocole) avant envoi. Calculée une seule fois au démarrage du script (ne change pas en cours d'exécution), comme le SSID WiFi tronqué à 8 caractères.
- **Débit réseau EMA** : `get_net_avg_kbps()` calcule le total upload + download sur l'interface WiFi (`wl*`) et le lisse via une moyenne exponentielle (α=0.25 ≈ constante de temps ~1 s). Affiché en KB/s ou MB/s selon le débit, identique à un indicateur de copie de fichier.
- **Fréquence CPU** : `psutil.cpu_freq()` retourne la fréquence courante en MHz ; transmise × 10 pour conserver une décimale entière (ex: 32 = 3.2 GHz). Décodée côté firmware avec division entière.
- **Puissance CPU RAPL** : `/sys/class/powercap/intel-rapl:0/energy_uj` — lecture root uniquement par défaut. Retourne 0 si non accessible ; l'affichage s'adapte (`X.X GHz` seul, sans `XXW`). Pour l'activer sans root : `SUBSYSTEM=="powercap", ACTION=="add", RUN+="/bin/chmod o+r /sys/class/powercap/intel-rapl:0/energy_uj"` dans `/etc/udev/rules.d/99-rapl.rules`.
- **LVGL %f** : `lv_snprintf` (LVGL 8.3) ne supporte pas `%f`. Toutes les valeurs float sont converties en entiers avant formatage (`(int)(val + 0.5f)`).
- **VRAM source** : `/sys/class/drm/card1/device/mem_info_vram_used` et `mem_info_vram_total` (driver amdgpu, pas besoin de ROCm).
- **Temp NVMe** : `/sys/class/nvme/nvme0/hwmon*/temp1_input` (millidegrés → divisé par 1000).
- **VPN detection** : `psutil.net_if_stats()` — toute interface contenant `tun`, `tap`, `vpn` ou `wg` et marquée UP est considérée VPN actif (couvre `qtun`, `tun0`, `wg0`, etc.).
- **Rétroéclairage PWM** : backlight sur `TFT_BL` (GPIO 1) via LEDC, canal 0, 5 kHz, 8-bit. `BL_BRIGHTNESS = 153` ≈ 60 % dans `sys_monitor.ino` — modifier cette valeur pour ajuster la luminosité (0–255).
- **Gauge SSD1** : barre unique affichant `R+W` cumulés en KB/s, centrée entre les labels `R - W` et le débit affiché à droite. Échelle : 20 000 KB/s (≈ 20 MB/s) = 100 %. Affichage dynamique : `KB/s` sous 10 240 KB/s, `MB/s` au-dessus. Les indicateurs R et W s'allument en vert au-dessus de 512 KB/s.
- **Santé SMART SSD1** : lue via l'interface D-Bus `org.freedesktop.UDisks2.NVMe.Controller` (méthode `SmartGetAttributes`, propriété `percent_used`), exposée par le service `UDisks2` déjà actif sur le système — **aucun droit root requis** (contrairement à `smartctl`/`nvme-cli` classiques, qui nécessitent un accès direct au device `/dev/nvme0`). Uniquement disponible pour le disque NVMe (SSD1) ; le module Python `dbus` (paquet système `python3-dbus`, déjà présent) est optionnel — son absence désactive juste la fonctionnalité. La lecture D-Bus est throttlée à 1×/60 s côté script (`_SSD_HEALTH_INTERVAL`), la santé SMART ne variant pas assez vite pour justifier un appel à chaque cycle de 0.25 s.
- **Santé + température SSD2** : SSD2 (Crucial CT2000MX500SSD1, pont USB-SATA ASMedia ASM235C) n'a pas d'attribut SMART standardisé de type "% d'usure" comme le NVMe (les attributs ATA propriétaires varient par fabricant) — lu à la place via l'interface `org.freedesktop.UDisks2.Drive.Ata` (ATA passthrough/SAT à travers le pont USB, toujours sans root). Statut de santé basé sur `SmartFailing` (agrégat officiel, équivalent `smartctl -H`), `SmartNumAttributesFailing` et `SmartNumBadSectors` : affiché en valeurs symboliques `100 %` (sain, vert) / `20 %` (WARN, rouge) plutôt qu'un vrai pourcentage mesuré, pour rester visuellement cohérent avec la jauge SSD1 sans donner une fausse précision. La température (`SmartTemperature`, absente de tout sysfs hwmon pour ce pont USB) est lue sur la même interface. Contrairement au NVMe, UDisks2 ne rafraîchit pas ces valeurs en continu (`SmartUpdated` peut dater de plus d'une heure) : le script appelle explicitement `SmartUpdate()` avant chaque lecture throttlée à 60 s (`_refresh_ssd2_smart()`), pour éviter d'afficher une valeur figée.
- **Pas de débit SSD2** : le pont USB-SATA ASMedia ASM235C (driver `uas`, `/dev/sdc`) ne met pas à jour `/proc/diskstats` pour les lectures — seules les écritures fsync'd sont comptabilisées avec délai. La gauge SSD2 a été supprimée et `S2RD`/`S2WR` ne sont plus transmis ; seuls santé, température et capacité SSD2 sont affichés (ligne partagée avec les mises à jour, visible quand `UPD == 0`).
- **Détection SSD** : `_detect_ssd_devices()` filtre les périphériques avec `taille ≥ 1 GB` pour exclure les gadgets USB 0-octet (sda/sdb exposés par l'ESP32 en mass-storage). Le NVMe est toujours sélectionné en premier.
- **Intervalle polling Python** : 0.25 s par défaut dans `monitor_sender.py`. Configurable via `--interval`.
- **Veille de l'écran ESP32** : le script lit toutes les secondes `PowerSaveMode` de `org.gnome.Mutter.DisplayConfig` sur le bus D-Bus de session (`/run/user/<uid>/bus`, accessible au service car il tourne en `User=daniel`) — c'est l'état DPMS réel de l'écran du NUC (0 = allumé, 3 = éteint), qui s'éteint après le délai GNOME « Écran noir » (`org.gnome.desktop.session idle-delay`, 600 s ici). `--sleep-delay` s après l'extinction (600 s par défaut, soit ~20 min d'inactivité au total), le script envoie `SCR:0` : l'ESP32 coupe le rétroéclairage, met l'AXS15231B en veille (`0x28` + `0x10`) et arrête le rendu LVGL (les données continuent d'être reçues et appliquées). Dès que souris/clavier rallument l'écran du NUC (y compris sur l'écran de verrouillage), `SCR:1` est envoyé immédiatement → réveil en ≤ 1 s (`0x11`, 120 ms, `0x29` + redessin complet). `ScreenSaver.Active` n'est pas utilisé car il reste vrai tant que l'écran de verrouillage est affiché. Sans session GNOME (boot, greeter), l'état est inconnu et l'écran reste allumé ; si le PC ne transmet plus rien pendant 5 s, l'ESP32 se réveille pour afficher « En attente du PC... ». Pendant la veille, l'ESP32 reste actif (pas de deep/light sleep) car il doit continuer à écouter l'USB CDC. Test rapide : `python tools/monitor_sender.py --sleep-delay 10` puis `xset dpms force off`.

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

**L'écran ESP32 ne se met jamais en veille**
→ Vérifier dans `sudo journalctl -u nuc-monitor` la ligne du preflight `Veille écran` : si elle affiche `n/a`, le bus D-Bus de session ou Mutter n'est pas accessible (pas de session GNOME ouverte, ou `python3-dbus` absent). Vérifier aussi que GNOME éteint bien l'écran (Paramètres → Énergie → « Écran noir ») et que `--sleep-delay` n'est pas à `0`. Test : `busctl --user get-property org.gnome.Mutter.DisplayConfig /org/gnome/Mutter/DisplayConfig org.gnome.Mutter.DisplayConfig PowerSaveMode` doit renvoyer `i 3` après `xset dpms force off`.

**Le service systemd ne démarre pas**
→ `sudo journalctl -u nuc-monitor -f` pour voir les erreurs. Vérifier que l'ESP32 est branché ou laisser le service : il reconnecte automatiquement.

---

## Bibliothèques

- [LVGL 8.3.0](https://github.com/lvgl/lvgl) — ne pas mettre à jour (rotation logicielle forcée)
- [XPowersLib](https://github.com/lewisxhe/XPowersLib)
- psutil, pyserial (Python)
