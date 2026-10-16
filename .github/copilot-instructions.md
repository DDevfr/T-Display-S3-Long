# Instructions pour assistants IA — NUC Monitor (T-Display-S3-Long)

Moniteur système d'un NUC AMD (Ryzen 9 7940HS, 16 threads, iGPU Radeon 780M) affiché sur une LilyGo T-Display-S3-Long (ESP32-S3, écran 180×640 portrait, tactile CST3530). Un script Python sur le NUC envoie des trames texte sur l'USB série ; le firmware les affiche avec LVGL. Linux uniquement (Zorin OS 18) : pas de version Windows.

Le détail (protocole, matériel, choix techniques, dépannage) est dans `README.fr.md` / `README.md` : s'y référer plutôt que de deviner, et ne pas le recopier ici.

## Organisation

- `examples/sys_monitor/` : **seul firmware actif** (env PlatformIO `sys_monitor`). `sys_monitor.ino` (boucle), `ui.cpp` (LVGL, écrans 1 et 2), `serial_parser.h` (struct `SysData`, parsing des clés), `icon_cache.cpp` (icônes en PSRAM), `touch_cst3530.c` (enveloppe du pilote tactile), `AXS15231B.cpp` (écran QSPI).
- `tools/monitor_sender.py` : collecte des métriques et boucle d'envoi ; `tools/proc_top.py` : top 12 processus et icônes (écran 2).
- `tools/deploy.sh`, `dev-mode.sh`, `install-autostart.sh`, `nuc-monitor.service` : service systemd `nuc-monitor`.
- Les autres dossiers de `examples/` et de `lib/` (sauf `lib/lvgl`, `lib/lv_conf.h`, `lib/hyn_driver_for_esp32`) viennent du dépôt LilyGo d'origine : ne pas les modifier.

## Commandes

- Compiler : `~/.platformio/penv/bin/pio run -e sys_monitor` (`pio` n'est pas dans le PATH).
- Flasher + redémarrer le service : `bash tools/deploy.sh` ; Python seul : `bash tools/deploy.sh --no-flash`. Ces scripts demandent sudo.
- Tester le script à la main : `sudo bash tools/dev-mode.sh`, puis `python3 tools/monitor_sender.py`, puis `sudo bash tools/dev-mode.sh resume`.
- Pas de suite de tests. Vérifier au minimum `python3 -m py_compile tools/*.py` et la compilation du firmware ; le preflight du script (au démarrage) vérifie chaque source de métrique.

## Règles impératives

- **Ne jamais reprogrammer le firmware de la puce tactile CST3530** : `HYN_POWER_ON_UPDATA` reste à `0` dans `lib/hyn_driver_for_esp32/hyn_cfg.h`. Le firmware d'origine n'est pas sauvegardable, la mise à jour serait irréversible.
- **Ne pas mettre à jour LVGL** (8.3, rotation logicielle forcée) ni passer à Arduino-ESP32 3.x / ESP-IDF 5 (le pilote Hynitron dépend d'IDF 4.4).
- **Aucun droit root pour le service** (`User=daniel`) : lire via sysfs, D-Bus (UDisks2, UPower, NetworkManager, Mutter) ou hwmon. Ne pas proposer de règle udev qui rouvre RAPL `energy_uj` (correctif Platypus).
- **Coût CPU** : le service tourne en permanence (~2 % d'un thread). Pas de `subprocess` ni de lecture coûteuse dans la boucle d'envoi ; préférer sysfs/D-Bus aux commandes externes. Les réécritures en C/Go ont été jugées non rentables.

## Protocole série

- Trame principale : `CLE:val,CLE:val,...,CX:c0;c1;...;c15` (16 valeurs CPU, une par thread : ne jamais moyenner par cœur physique). Trames annexes `P:` (top processus), `I:` (icônes), `?I:` (demande ESP32 → PC).
- Ligne de 510 octets max (tampon de 512 dans `serial_parser.h`) : vérifier le budget (pire cas ~415 octets) avant tout ajout de champ. Les chaînes envoyées doivent être nettoyées de `,` et `:`.
- Ajouter une métrique = modifier ensemble : `collect()` et `format_line()` dans `monitor_sender.py`, la struct `SysData` et le parsing dans `serial_parser.h`, l'affichage dans `ui.cpp`, le tableau des clés dans les deux README.
- Valeur « indisponible » : une sentinelle (`255`, `0`) que le firmware masque, jamais une erreur.

## Conventions de code

- Code et commentaires en français, identifiants en anglais ; suivre le style du fichier modifié.
- Python : dépendances optionnelles (`dbus`, Pillow, GdkPixbuf) importées dans un `try/except ImportError`, la fonction se désactive si absente. Les lectures lentes sont mises en cache avec le motif `_X_CACHE` / `_X_NEXT` / `_X_INTERVAL` et `time.monotonic()`. Les chemins sysfs/hwmon sont résolus une fois au démarrage.
- Firmware : `lv_snprintf` ne gère pas `%f` (convertir en entier). Couleurs via les `CLR_*` de `ui.cpp`. Écrans non défilables (un glissé tactile pousserait le contenu hors de l'écran). Ne pas inclure l'en-tête du pilote Hynitron dans le `.ino` (il redéfinit `bool`, `NULL`, `HIGH`).
- Port série ouvert en raw `VMIN=0` : ne lire que si `select()` le signale lisible.

## Documentation

- La doc existe en deux langues : `README.fr.md` en **français**, `README.md` en **anglais** (affiché par défaut sur GitHub et Gitea).
- **Toute mise à jour de la documentation doit être faite en français ET en anglais, chacune dans son fichier** : rédiger le texte français dans `README.fr.md`, sa traduction anglaise dans `README.md`, dans le même changement. Ne jamais mettre à jour une seule langue ni mélanger les langues dans un fichier.
- **Les deux fichiers ont la même structure** : chaque section (titres `##` et `###`) de l'un a son équivalent traduit dans l'autre, au même niveau et **dans le même ordre**. Ajouter, supprimer, renommer ou déplacer une section se fait donc des deux côtés. Les tableaux, blocs de code et listes d'une section se correspondent aussi ligne à ligne.
- Vérifier que les liens internes (ancres) de chaque fichier pointent vers ses propres titres traduits.
- Les textes affichés par le firmware sont en français (`En attente du PC...`, `N maj disponibles`) : les citer tels quels dans la version anglaise.
- Messages de commit en français.
