"""Validate the committed CDN assets (no generated copy is required)."""
from pathlib import Path


def build():
    root = Path(__file__).resolve().parent
    for name in ("style.css", "home_page.js", "transaction.js", "Resources/images/solar1.jpg"):
        asset = root / "public" / "static" / name
        if not asset.is_file():
            raise FileNotFoundError(f"Missing public asset: {asset}")
    print("Static assets are ready in public/static.")


if __name__ == "__main__":
    build()
