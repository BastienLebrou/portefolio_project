---
type: systeme
---

# Conventions du coffre « Veille GeoAI »

Ce dossier est un coffre Obsidian alimenté par l'agent de veille Grok et rangé par Claude.

## Circuit

```
Grok (veille auto) ──► 00 Inbox/ (texte brut)
                          │  Claude range
                          ▼
                 10 Rapports/  1 note par rapport (texte d'origine conservé)
                 20 Intel/     1 note par info, reliée au rapport
                 30 Entités/   1 note par acteur/outil récurrent
                 Actions.md    toutes les actions à cocher
```

Synchro PC ↔ téléphone : Git (plugin Obsidian Git), ce dépôt sert de point central.

## Nommage

| Dossier | Nom de fichier |
|---|---|
| `00 Inbox/` | `AAAA-MM-JJ grok brut.md` (supprimé une fois rangé) |
| `10 Rapports/` | `AAAA-MM-JJ - <titre court>.md` |
| `20 Intel/` | `AAAA-MM-JJ - <sujet>.md` |
| `30 Entités/` | `<Nom>.md` |

## Propriétés (frontmatter)

**Intel**
```yaml
type: intel
date: 2026-09-22          # date de l'événement
rapport: "[[...]]"        # rapport source
themes: [llm-spatial, lidar, open-source, eo-satellite, marche, evenement, recherche]
entites: ["[[BigGeo]]"]
impact: haut | moyen | bas  # impact estimé pour la géomatique / ScruTech
statut: a-lire | a-tester | teste | archive
sources: [url, ...]
```

**Rapport** : `type: rapport`, `periode_debut`, `periode_fin`, `source: grok`, `nb_intel`.

**Entité** : `type: entite`, `categorie: entreprise | outil | personne | evenement | constellation | institution`.

## Thèmes (liste fermée, à étendre ici si besoin)

`llm-spatial` · `geoai-modele` · `open-source` · `lidar` · `eo-satellite` · `sar` ·
`drone` · `jumeau-numerique` · `marche` · `financement` · `evenement` · `recherche` ·
`reglementation` · `donnee-ouverte`

## Actions

Chaque action est une case `- [ ]` dans la note Intel, suivie de ` 📅 AAAA-MM-JJ` si
elle a une échéance. [[Actions]] les regroupe (plugin Tasks ou Dataview).
