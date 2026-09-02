# b2b — dossier de travail « valorisation commerciale »

Dossier ouvert le **2026-09-02**. Il rassemble le matériel d'analyse B2B produit à partir
du dépôt, **sans rien modifier du code des piliers**.

## Contenu

| Fichier | Rôle |
|---|---|
| [`../audit_b2b_2026-09-02.md`](../audit_b2b_2026-09-02.md) | **Le livrable** : inventaire factuel (Phase 1), 8 pistes B2B (Phase 2), priorisation et 3 tests à une semaine (Phase 3) |
| [`sources.md`](sources.md) | Journal des sources de demande : requête utilisée, lien, date, statut de vérification |
| [`inventaire_actifs.csv`](inventaire_actifs.csv) | Tableau 1 de l'audit en format exploitable (brique, maturité, dépendances, fichier source) |
| [`pistes.csv`](pistes.csv) | Tableau des 8 pistes avec notes d'effort, de preuve de demande et score |

## Règles appliquées dans ce dossier

1. **Aucune information non sourcée.** Toute donnée absente du dépôt ou des sources publiques
   est écrite « non documenté ». Rien n'est déduit d'une intention supposée.
2. **Lecture seule sur les piliers.** Aucun fichier de `scrutech/` n'a été modifié.
3. **Exclusion OneMW.** Aucune piste ne réutilise le code ni les données OneMW (prospection
   foncière photovoltaïque, base propriétaires/parcelles).
4. **Cibles.** Grands comptes, assureurs, développeurs ENR, bureaux d'études. Les petites
   communes sont hors périmètre.

## Limite majeure de cette itération

Le vault Obsidian `claude_vault` **n'était pas accessible** depuis l'environnement d'audit
(session distante, clone du seul dépôt GitHub). Tout ce qui en dépend — veille, contacts,
missions passées, compétences hors code — est marqué « non documenté ». **L'audit doit être
rejoué avec le vault monté** avant d'en tirer des décisions commerciales définitives.
