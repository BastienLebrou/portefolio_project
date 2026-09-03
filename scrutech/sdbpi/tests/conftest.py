"""Put the SDBPi flat modules (config, processing, …) on the path for tests."""

# Un fichier nommé EXACTEMENT `conftest.py` est spécial pour pytest : il le charge
# automatiquement avant de lancer les tests du dossier (et ses sous-dossiers), sans
# qu'aucun test n'ait besoin de l'importer explicitement — l'endroit habituel pour de la
# configuration ou des "fixtures" partagées. Ici, son seul rôle est de rendre `import
# processing` possible dans les tests : sdbpi n'est pas un package installé (pas de
# pyproject.toml), donc sans ce sys.path.insert, Python ne saurait pas où le trouver.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
