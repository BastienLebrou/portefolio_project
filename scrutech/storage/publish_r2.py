"""Publier les données lourdes sur Cloudflare R2 (pour un utilisateur tiers léger).

Convertit un raster en COG (si besoin) puis l'envoie sur un bucket R2 (API compatible S3).
Ainsi un utilisateur tiers ne stocke rien : il lit le MNT/les couches par plage via ``/vsicurl``
(voir ``core.cog.raster_source`` et SCRUTECH_MNT / SCRUTECH_DATA_URL).

Identifiants via variables d'environnement (jamais dans le dépôt) :
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

Prérequis : ``pip install boto3``.

Exemples :
    python publish_r2.py mnt.tif --as mnt/france_cog.tif --cogify
    python publish_r2.py scrutech.duckdb --as db/scrutech.duckdb
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _client():
    """Client S3 pointé sur l'endpoint R2 du compte (identifiants depuis l'environnement)."""
    import boto3

    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def publish(src: Path, key: str, *, cogify: bool) -> str:
    """Optionnellement convertir en COG, puis téléverser ``src`` sous ``key`` dans le bucket."""
    bucket = os.environ["R2_BUCKET"]
    to_upload = src
    if cogify:
        from core.cog import to_cog

        out = src.with_suffix(".cog.tif")
        print(f"Conversion COG : {src.name} -> {out.name}")
        to_upload = to_cog(src, out)

    print(f"Téléversement : {to_upload} -> r2://{bucket}/{key}")
    _client().upload_file(str(to_upload), bucket, key)
    return f"https://{bucket}.<votre-domaine-r2>/{key}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publier un fichier sur R2 (option COG).")
    parser.add_argument("src", type=Path, help="fichier local à publier")
    parser.add_argument("--as", dest="key", required=True, help="chemin cible dans le bucket")
    parser.add_argument("--cogify", action="store_true", help="convertir le GeoTIFF en COG avant")
    args = parser.parse_args(argv)

    missing = [
        v
        for v in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
        if not os.environ.get(v)
    ]
    if missing:
        print(f"Variables d'environnement manquantes : {', '.join(missing)}", file=sys.stderr)
        return 2
    if not args.src.exists():
        print(f"Fichier introuvable : {args.src}", file=sys.stderr)
        return 2

    url = publish(args.src, args.key, cogify=args.cogify)
    print(f"OK. URL de lecture (à adapter) : {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
