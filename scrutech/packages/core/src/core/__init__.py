"""ScruTech shared geodata core."""

# Ce fichier __init__.py transforme le dossier core/ en "package" Python importable
# (ex: `from core import resolve_aoi`). Il ré-exporte ici les quelques fonctions/classes
# que les autres piliers (vegevigie, sdbpi, mini_dc, ...) ont le droit d'utiliser :
# c'est la "façade publique" du socle commun. Le détail de leur fonctionnement est
# dans aoi.py et io.py.
from core.aoi import Aoi, resolve_aoi
from core.io import read_vector, write_geoparquet

# __all__ liste ce qu'un `from core import *` importerait : ça documente explicitement
# l'API publique du package (les fonctions internes des autres modules ne sont pas ici).
__all__ = ["Aoi", "read_vector", "resolve_aoi", "write_geoparquet"]
