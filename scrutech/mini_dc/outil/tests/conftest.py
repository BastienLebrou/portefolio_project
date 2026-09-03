"""Put the mini_dc flat modules (config, generate_synthetic, …) on the path for tests."""

# pytest charge automatiquement tout fichier nommé conftest.py avant les tests du même
# dossier (voir sdbpi/tests/conftest.py pour le détail) : ici, comme mini_dc n'est pas
# un package installé, on ajoute son dossier à sys.path pour que `import
# generate_synthetic` fonctionne dans les tests qui suivent.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
