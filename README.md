# NUC Monitor — T-Display-S3-Long

Moniteur système graphique pour NUC AMD (Ryzen 9 7940HS + Radeon 780M) affiché sur un écran T-Display-S3-Long (ESP32-S3, 180×640 px portrait).

Les métriques sont envoyées du NUC vers l'ESP32 via USB-Serial (CSV) par le script Python `tools/monitor_sender.py`. Un second écran, affiché avec le bouton BOOT, montre le top 12 des processus avec l'icône de leur appli (voir [Écran 2 — Top processus](#écran-2--top-processus)).

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
│ WifiSSID |||..                VPN ON │  ← ligne 1 : SSID + barres (font_12) | VPN (font_12)
│ 512 KB/s                    14h 09m  │  ← ligne 2 : débit réseau (font_12) | uptime (font_12)
├──────────────────────────────────────┤  ← séparateur header / CPU
│         Arc CPU  %  °C               │  ← CPU % (font_20) + °C, couleur dynamique
│            3.2 GHz                   │  ← fréquence CPU (font_10)
│     CPU  ·  Ryzen 9 7940HS           │  ← labels fixes (font_8)
├──────────────────────────────────────┤
│  Barres 16 cœurs (0-7 / 8-15)        │  ← 2 rangées × 8, numéros colorés sous chaque barre
├──────────────────────────────────────┤
│  KB      Arc GPU  %  °C       MS     │  ← GPU % + °C (Radeon 780M) ; piles clavier (gauche) / souris (droite)
│ [▮▮▮]       GPU              [▮  ]   │  ← "GPU" + "Radeon 780M" dessous ; icône pile colorée
│ 100%                          20%    │  ← % pile : vert ≥ 60, jaune ≥ 35, orange ≥ 15, rouge < 15
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
├── ui.h / ui.cpp       # Interface LVGL (init + update, écran 2 top processus)
├── serial_parser.h     # Parser non-bloquant (trames CPU:, P:, I:)
├── icon_cache.h / .cpp # Cache PSRAM des icônes d'applis (écran 2)
├── AXS15231B.h / .cpp  # Driver écran QSPI (DMA, veille lcd_sleep/lcd_wake)
└── pins_config.h       # Brochage et résolution

tools/
├── monitor_sender.py       # Script Python NUC → ESP32
├── proc_top.py             # Top 12 processus + icônes d'applis (écran 2)
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
KBAT:100,KCHG:0,MBAT:20,MCHG:0,
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
| `KBAT` / `MBAT` | % pile clavier / souris (UPower via D-Bus système, sans root, rafraîchi toutes les 60 s). `255` = absent → colonne vide. Classement par nom de modèle (`K780`, `MX Anywhere`…) car UPower déclare la souris HID++ Logitech en type *keyboard* |
| `KCHG` / `MCHG` | `1` = périphérique en charge → icône éclair à la place de la pile |
| `CX` | 16 valeurs % par cœur séparées par `;` (ex: `CX:55;12;8;...;1`) |

> **Note SSD2** : les débits SSD2 (`S2RD`/`S2WR`) ne sont plus envoyés — le pont USB-SATA ASMedia ASM235C (driver `uas`) ne remonte pas les lectures dans `/proc/diskstats`. Le firmware sait encore les parser (compatibilité) mais ne les affiche pas. SSD2 n'apparaît qu'à travers `S2HLTH`/`S2TMP`/`S2CAP`/`S2TOT`, sur la ligne partagée avec les mises à jour.

---

## Installation

### Dépendances Python (NUC)

```bash
pip install psutil pyserial
sudo apt install python3-dbus   # optionnel (déjà présent sur Zorin) : santé SMART SSD1/SSD2 + veille écran ESP32 + piles souris/clavier
sudo apt install python3-pil python3-gi gir1.2-gdkpixbuf-2.0   # optionnel (déjà présents sur Zorin) : icônes de l'écran 2 (Pillow requis, GdkPixbuf pour les SVG)
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

## Écran 2 — Top processus

Un appui sur le **bouton BOOT** (GPIO0) bascule de l'écran principal vers le top 12 des processus ; un nouvel appui revient à l'écran principal (pas de retour automatique). Le toucher fait la même chose, mais le contrôleur tactile de la carte actuelle ne répond pas (voir « Tactile » ci-dessous). Appuyer sur BOOT pendant le fonctionnement ne fait que changer d'écran : il ne fait passer l'ESP32 en mode flash que s'il est maintenu pendant un appui sur RST. Chaque ligne : icône de l'appli (la même que dans le moniteur système GNOME) + nom du processus + %CPU façon `top` (100 % = un thread saturé, jusqu'à 1600 % sur les 16 threads), avec une barre de 4 px et la couleur `pct_color()`. Le titre rappelle le CPU global.

```
┌──────────────────────────────────────┐
│ TOP CPU                     CPU 23%  │
├──────────────────────────────────────┤
│ [ic]  code                    75%    │  ← icône 32×32 reçue du PC
│       ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬                │
│ [B ]  brave                   12%    │  ← pastille (initiale) tant que l'icône n'est pas arrivée
│       ▬▬▬                            │
│  …    12 lignes de 48 px             │
└──────────────────────────────────────┘
```

### Échanges PC ↔ ESP32

- **Le Python produit les données** : il ne sait pas quel écran est affiché et envoie le top processus en permanence.
- **L'ESP32 affiche et bascule localement** : le bouton BOOT (ou le toucher) ne passe pas par le PC (bascule instantanée, écran 2 déjà à jour).
- **Seul cas où l'ESP32 parle au PC** : il demande une icône qui lui manque.

```
      NUC (Python)                          câble USB                    ESP32
 ═════════════════════════                                  ═══════════════════════════
 ┌─ Boucle principale ─────┐
 │                         │   ① toutes les 0,25 s
 │  métriques système ─────┼──── CPU:45,CTEMP:62,...,CX:.. ──────►  Écran 1
 │                         │   ② toutes les 1 s (+0,125 s)
 │  top 12 processus ──────┼──── P:a1b2;153;firefox|c3d4;42;code|.. ►  garde le top 12
 │  (/proc)                │                                            │
 │                         │                                   icône a1b2 connue ?
 │                         │                                    ├─ oui → affichée
 │                         │                                    └─ non → pastille « F »
 │                         │   ③ demande d'icône                        │
 │  lit les demandes ◄─────┼──────────────── ?I:a1b2 ◄───────────────┘ (relance / 2 s)
 │        ▼                │   ④ icône en 8 morceaux
 │  file d'envoi ──────────┼──── I:a1b2;0..7;8;<base64> ──────────►  cache PSRAM (48)
 │  (max 1 icône / 100 ms) │                                         vérif hash → affichée
 └─────────▲───────────────┘
 ┌─ Thread séparé ─────────┐                                    ┌─────────────────┐
 │  processus → appli      │                                    │ BOUTON BOOT     │
 │  → icône du thème       │                                    │ écran 1 ⇄ 2     │
 │  → 32×32 → hash (cache) │                                    │ (sans le PC)    │
 └─────────────────────────┘                                    └─────────────────┘
```

> `a1b2` est un hash abrégé : en réalité 8 caractères hexadécimaux.

| Sens | Trame | Fréquence | Contenu |
|------|-------|-----------|---------|
| PC → ESP | `P:h;pct;nom\|h;pct;nom\|…` | 1 s | 12 entrées max. `h` = hash de l'icône en 8 hexa (`00000000` = pas encore d'icône) ; `pct` = %CPU × 10 entier (ex. `153` = 15,3 %) ; `nom` = nom du processus (15 car. max, ASCII, `\|` `;` `,` `:` remplacés par `_`). ~380 octets au pire |
| PC → ESP | `I:h;idx;n;<base64>` | à la demande | Morceau `idx` (0–7) sur `n` = 8 d'une icône 32×32 RGB565 big-endian (2048 o, alpha pré-mélangé sur le fond `0x0D0D0D`) : 256 o par morceau, 360 caractères par ligne |
| ESP → PC | `?I:h` | si une icône manque | Demande d'icône, relancée toutes les 2 s tant qu'elle n'est pas complète |

`h` est le hash **FNV-1a 32 bits du contenu** de l'icône (jamais 0), calculé des deux côtés.

| Situation | Ce qui se passe |
|-----------|-----------------|
| Trame `P:` perdue ou corrompue | L'écran 1 n'est pas touché ; la suivante arrive 1 s plus tard |
| L'ESP32 redémarre (cache vide) | Il voit des hash inconnus et redemande les icônes tout seul |
| Morceau d'icône abîmé | Le hash recalculé ne correspond pas → icône rejetée puis redemandée |
| Processus sans appli (démon, script, thread noyau) | Icône générique `application-x-executable`, comme le moniteur système |
| Plusieurs processus avec la même icône | Même hash → envoyée et stockée une seule fois |
| Plus de trame `P:` pendant 5 s | L'écran 2 est vidé |

**Côté NUC** (`tools/proc_top.py`) :
- Le %CPU est calculé en lisant directement `/proc/<pid>/stat` (~6 ms pour ~480 processus, contre ~20 ms via psutil) ; nom et exécutable ne sont lus que pour le top 12.
- L'appli d'un processus est trouvée, dans l'ordre, par : l'id d'appli du scope systemd (`app-gnome-brave\x2dbrowser-….scope` → `brave-browser.desktop`), à condition que l'exécutable soit dans le dossier de l'appli (un `bash` lancé dans le terminal de VS Code garde donc l'icône générique) ; le nom de l'exécutable (`Exec=`, `StartupWMClass=`) ; le dossier privé de l'appli (les helpers de Brave, rangés dans le scope `org.chromium.Chromium`, sont reconnus par `/opt/brave.com/brave/`).
- L'icône est cherchée dans le thème actif (`org.gnome.desktop.interface icon-theme`, lu sans session graphique car le service n'a pas de `DISPLAY`), ses thèmes hérités, `hicolor` puis `/usr/share/pixmaps` ; chargée par GdkPixbuf (PNG/SVG/XPM) puis convertie par Pillow.
- Recherche et rendu tournent dans un thread séparé : tant qu'une icône n'est pas prête, le hash envoyé est `0` et l'ESP32 affiche la pastille. Les rendus sont mis en cache dans `~/.cache/nuc-monitor/icons/` (clé = chemin + date de modification de l'image). Aucune commande externe n'est lancée.
- Sans Pillow, les trames `P:` sont envoyées sans icônes (pastilles uniquement).

**Tactile** : sur la carte actuelle, le contrôleur tactile de l'AXS15231B ne répond pas à son adresse `0x3B`. Il reste en mode bootloader : il répond en `0x58` et renvoie des octets de firmware. Le firmware `factory` de LilyGo reste lui aussi bloqué (écran noir), et une coupure d'alimentation n'y change rien : le problème vient de la carte. La bascule passe donc par le bouton BOOT, avec un anti-rebond de 30 ms. Le code du tactile reste en place : il suit l'ordre de démarrage des exemples LilyGo, sonde `0x3B` toutes les 2 s et n'accepte que des réponses plausibles (1 ou 2 doigts, coordonnées dans l'écran). Il prendra le relais si le contrôleur se remet à répondre.

**Côté ESP32** : `icon_cache.cpp` garde 48 icônes en PSRAM (~96 Ko, éviction LRU) ; `loop()` traite jusqu'à 16 lignes par tour pour absorber les 8 lignes d'une icône.

### Cadence et décalage des envois

Les trames `CPU:` (0,25 s), `P:` (1 s) et `I:` (à la demande) ne se gênent pas :

- **Un seul envoyeur** : une seule boucle Python écrit sur le port, les lignes partent l'une après l'autre et ne peuvent pas se mélanger.
- **L'ESP32 découpe par ligne** (`\n`) et dirige chaque ligne selon son préfixe (`P:`, `I:`, sinon trame principale).
- **Décalage** : `P:` part 0,125 s après la trame principale, et jamais dans le même tour de boucle.
- **Tampon de sortie unique** : si le FIFO USB est plein, `os.write` n'écrit qu'une partie ; le reste est gardé et envoyé au tour suivant (10 ms plus tard) au lieu d'être perdu. Si l'ESP32 ne lit plus du tout (plus de 1 Ko en attente), les nouvelles trames d'écran sont sautées plutôt qu'empilées.
- **Icônes en dernier** : les 8 lignes d'une icône (~2,9 Ko) ne partent que si aucune trame d'écran n'attend, au maximum une icône toutes les 100 ms. Le tampon RX de l'ESP32 fait 4096 octets.

```
0 ──── 0.125 ──── 0.25 ──── 0.5 ──── 0.75 ──── 1.0 ──── 1.125
[CPU]   [P:]      [CPU]     [CPU]    [CPU]     [CPU]    [P:]
```

---

## Points techniques notables

- **HWCDC vs HardwareSerial** : l'ESP32-S3 expose `Serial` en HWCDC quand `ARDUINO_USB_CDC_ON_BOOT=1`. Sans ce flag, `Serial.available()` reste toujours à 0.
- **Buffer série HWCDC** : le buffer RX logiciel est étendu à 4096 octets via `Serial.setRxBufferSize(4096)` (défaut = 256) pour absorber une icône complète (8 lignes `I:`) pendant un rendu LVGL. Le buffer de ligne de `serial_parser.h` reste à 512 octets. `Serial.setTxTimeoutMs(0)` : les demandes `?I:` ne bloquent jamais si le PC ne lit pas. Le script Python tronque les lignes dépassant 510 octets avant envoi. En cas de ligne trop longue côté firmware, `serial_read_line()` rejette la ligne entière (flag `overflow`) plutôt que de parser des données tronquées.
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
- **Piles souris / clavier** : lues via `org.freedesktop.UPower` sur le bus D-Bus système (`EnumerateDevices` puis propriétés `Percentage`, `State`, `Model`, `Type`), sans root — UPower agrège déjà le récepteur Logitech HID++ (souris MX Anywhere 3S, `hidpp_battery_*`) et BlueZ (clavier K780 en Bluetooth). Seuls les périphériques `PowerSupply == false` et `IsPresent == true` sont gardés. UPower déclare **les deux** en `Type = 6` (keyboard), d'où un classement par nom de modèle (`keyboard|clavier|K###` → clavier, `mouse|souris|MX Anywhere/Master/Vertical|M###` → souris), le `Type` ne servant que de repli. Lecture throttlée à 1×/60 s (`_PERIPH_BAT_INTERVAL`). Côté écran, deux colonnes de part et d'autre de l'arc GPU (`KB` à gauche, `MS` à droite) : icône pile LVGL (`LV_SYMBOL_BATTERY_FULL/3/2/1/EMPTY`, ou `LV_SYMBOL_CHARGE` en charge) + %, colorés en vert (≥ 60 %), jaune (≥ 35 %), orange (≥ 15 %) ou rouge (< 15 %). Le % du clavier Bluetooth est celui mémorisé par BlueZ : il n'est mis à jour que lorsque le clavier le transmet (peu fréquent), et reste affiché même clavier éteint.

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

**Les piles souris/clavier n'apparaissent pas (colonnes vides à côté de l'arc GPU)**
→ Vérifier qu'UPower voit les périphériques : `upower -d` doit lister la souris (`hidpp_battery_*`) et le clavier (`keyboard_dev_*`) avec un `percentage`. Si un périphérique est listé mais affiché du mauvais côté, son nom de modèle ne correspond pas aux motifs `_KBD_MODEL_RE` / `_MOUSE_MODEL_RE` de `monitor_sender.py` : les compléter. Les valeurs étant rafraîchies toutes les 60 s, attendre jusqu'à 1 min après un changement (branchement en charge, rallumage du clavier).

**L'écran 2 reste vide ou les icônes restent des pastilles**
→ Écran 2 vide : le script Python ne transmet plus de trame `P:` depuis 5 s (ancienne version du script, ou script arrêté) ; relancer `bash tools/deploy.sh --no-flash`. Pastilles permanentes : Pillow est absent (`sudo apt install python3-pil`), ou l'appli n'a pas d'icône trouvable ; la pastille est alors le comportement normal. Les icônes déjà rendues sont dans `~/.cache/nuc-monitor/icons/`, et ce dossier peut être supprimé sans risque.

**Le service systemd ne démarre pas**
→ `sudo journalctl -u nuc-monitor -f` pour voir les erreurs. Vérifier que l'ESP32 est branché ou laisser le service : il reconnecte automatiquement.

---

## Bibliothèques

- [LVGL 8.3.0](https://github.com/lvgl/lvgl) — ne pas mettre à jour (rotation logicielle forcée)
- [XPowersLib](https://github.com/lewisxhe/XPowersLib)
- psutil, pyserial (Python)
- Pillow, PyGObject / GdkPixbuf (Python, optionnels : icônes de l'écran 2)
