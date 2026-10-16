# CLAUDE.md

Les instructions du projet sont communes à tous les assistants et maintenues dans un seul fichier :

@.github/copilot-instructions.md

## Spécifique à Claude Code

- Les commandes qui demandent sudo (`tools/deploy.sh`, `tools/dev-mode.sh`, `systemctl restart nuc-monitor`) : les donner à l'utilisateur au lieu de les lancer.
- Pour tester le script sans ESP32 : le lancer sur un pty (`--port /dev/pts/N`) et toujours tuer les instances de test ensuite, sinon elles se reconnectent au pty réutilisé.
- Ne pas recopier ici ce qui est dans `.github/copilot-instructions.md` : y ajouter les règles communes.
