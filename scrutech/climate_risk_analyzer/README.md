# Climate Risk Analyzer (EUDR)

Plugin QGIS d'évaluation du **risque de déforestation EUDR** (EU Deforestation
Regulation) et du **stress climatique 2050** pour des localisations de fournisseurs
(supply chain / ESG).

- charge un CSV de coordonnées fournisseurs → couche de points temporaire ;
- génère des scores de risque EUDR + climat (mock pour l'instant), applique un style
  de risque ;
- affiche les résultats par fournisseur.

## Contenu

- [`eudr_climate_risk_analyzer/`](eudr_climate_risk_analyzer/) — le plugin QGIS
  (`metadata.txt`, `eudr_analyzer_plugin.py`, `eudr_analyzer_dialog.py`, `__init__.py`).

Statut : fondation (v0.1.0, `experimental`). Les données de test (`test.csv`,
`test_data/`) et le zip de build ne sont pas versionnés.
