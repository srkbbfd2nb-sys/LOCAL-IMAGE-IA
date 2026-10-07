"""Point d'entrée sous Windows : tourne avec le Python embarqué de ComfyUI.

Aucune installation de paquet : numpy et Pillow sont déjà fournis par ComfyUI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_image_ia.cli import main  # noqa: E402

raise SystemExit(main())
