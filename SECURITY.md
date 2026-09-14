# Politique de sécurité

## Signaler une vulnérabilité

Merci de signaler toute faille en privé, par e-mail à **bastienlebrou1@gmail.com**, plutôt que
par une issue publique. Décrivez le problème, les étapes pour le reproduire et l'impact estimé.
Réponse visée sous quelques jours.

## Périmètre

ScruTech est un **outil de bureau mono-utilisateur** (plugin QGIS + moteurs Python), pas un
service exposé. Les principaux points d'attention :

- **Secrets** : aucune clé n'est stockée dans le dépôt. Les identifiants (Google Earth Engine,
  Cloudflare R2) sont fournis par l'utilisateur via le coffre d'authentification de QGIS ou des
  variables d'environnement, jamais écrits sur disque ni committés. Ne jamais coller de clé dans
  le code, une issue, ou un commit.
- **Interpréteur externe** : les gros calculs tournent dans un sous-processus Python (`venv`).
  Les commandes sont toujours construites en liste d'arguments (pas de shell), et le process de
  rapport (Streamlit) est bindé sur `127.0.0.1` et privé de secrets.
- **Sources de données** : l'outil lit des services WFS et des rasters distants (`/vsicurl`)
  configurés par l'utilisateur. Sur un usage desktop c'est voulu ; un déploiement multi-
  utilisateurs devrait ajouter une allowlist d'hôtes (anti-SSRF).
- **SQL** : les identifiants interpolés dans DuckDB sont validés (`core.db`).

## Bonnes pratiques pour les contributeurs

- Ne jamais committer de fichier de credentials (`*.json` de service account, `.env`, clés).
  Le `.gitignore` est en liste blanche pour limiter les fuites accidentelles.
- Garder `verify=False` interdit (TLS toujours vérifié) et un `timeout` sur toute requête réseau.
- Préférer `yaml.safe_load`, éviter `eval`/`exec`/`pickle` sur des entrées non fiables.
- Dependabot surveille les dépendances ; traiter les alertes de sécurité en priorité.
