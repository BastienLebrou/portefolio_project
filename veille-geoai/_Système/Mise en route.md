---
type: systeme
---

# Mise en route (PC + téléphone)

## 1. Ouvrir le coffre sur l'ordinateur

1. Cloner le dépôt : `git clone https://github.com/BastienLebrou/portefolio_project.git`
2. Obsidian → *Ouvrir un dossier comme coffre* → choisir `portefolio_project/veille-geoai`.
3. Plugins communautaires à activer : **Obsidian Git** (synchro), **Dataview** (tableaux), **Tasks** (actions).
4. Obsidian Git : cocher *Pull au démarrage* et *Auto pull toutes les 10 min*.

> Obsidian Git doit voir le dossier `.git` : s'il ne le trouve pas depuis le sous-dossier,
> ouvrir `portefolio_project` entier comme coffre, ou passer le coffre dans un dépôt dédié.

## 2. Sur le téléphone

- **Android** : Obsidian + plugin Obsidian Git (clone avec un jeton GitHub en lecture/écriture sur ce dépôt).
- **iPhone** : pareil, ou l'app *Working Copy* qui synchronise le dossier avec Obsidian.

## 3. Alimenter la veille

Coller la sortie de Grok dans la session Claude « Veille GeoAI », ou la déposer telle quelle
dans `00 Inbox/`. Claude la range selon [[Conventions]], commite et pousse ; Obsidian Git
la récupère sur les deux appareils.

## Consigne pour Claude (à chaque nouveau rapport)

1. Enlever le bavardage de Grok (« Je lance une veille… »).
2. Créer la note `10 Rapports/` avec le texte d'origine intact dans un encart repliable.
3. Une note `20 Intel/` par info : frontmatter complet, résumé reformulé, « Pourquoi ça compte »,
   « Lien ScruTech » si pertinent, actions en cases à cocher.
4. Si un acteur existe déjà dans `30 Entités/`, le relier ; sinon créer sa fiche.
5. Si une info prolonge une Intel déjà rangée, relier les deux (`Suite de [[...]]`) plutôt que dupliquer.
6. Vider `00 Inbox/`, commiter `veille(AAAA-MM-JJ): <titre>` et pousser.
