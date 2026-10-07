"""Mécanisme 1 : verrou par masque.

Les pixels hors masque sont recopiés depuis l'original. Ce n'est pas une
consigne au modèle : c'est une opération du code, vérifiée après coup.
"""

from __future__ import annotations

import numpy as np


def composer(original: np.ndarray, candidat: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    if original.shape != candidat.shape:
        raise ValueError("original et candidat doivent avoir la même taille")
    a = alpha[..., None].astype(np.float32)
    melange = original.astype(np.float32) * (1.0 - a) + candidat.astype(np.float32) * a
    melange = np.clip(np.rint(melange), 0, 255).astype(np.uint8)
    # Copie stricte là où alpha vaut 0 : aucune approximation flottante hors masque.
    return np.where(a == 0.0, original, melange)
