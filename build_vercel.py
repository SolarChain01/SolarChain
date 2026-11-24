"""Copy Flask assets to Vercel's CDN while preserving /static URLs."""
from pathlib import Path
from shutil import copytree


def build():
    root = Path(__file__).resolve().parent
    copytree(root / "main" / "static", root / "public" / "static", dirs_exist_ok=True)


if __name__ == "__main__":
    build()
