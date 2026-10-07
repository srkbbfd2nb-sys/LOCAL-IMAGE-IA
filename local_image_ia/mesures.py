"""Mécanisme 5 (partie code) : mesures après coup.

Les seuils sont des estimations (E) à calibrer sur tes propres photos.
Toute modification d'un seuil doit s'appuyer sur une mesure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from local_image_ia.images import dilater, eroder, luminance
from local_image_ia.signature import grain_par_bande, nettete, residu, zone_editee, zone_reference

SEUILS = {
    "grain_ratio_min": 0.8,
    "grain_ratio_max": 1.25,
    "nettete_ratio_min": 0.5,
    "nettete_ratio_max": 2.0,
    "raccord_ratio_max": 1.5,
}
NATURE_SEUILS = "E — estimation non calibrée sur tes photos"


def ecart_hors_masque(original: np.ndarray, final: np.ndarray, masque: np.ndarray) -> dict:
    hors = ~masque
    diff = np.abs(original.astype(np.int16) - final.astype(np.int16)).max(axis=-1)
    d = diff[hors]
    return {
        "ecart_max": int(d.max()) if d.size else 0,
        "pixels_differents": int((d > 0).sum()),
        "pixels_hors_masque": int(hors.sum()),
        "conforme": bool(d.size == 0 or d.max() == 0),
    }


def _gradient(y: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(y)
    gy = np.zeros_like(y)
    gx[:, 1:-1] = (y[:, 2:] - y[:, :-2]) / 2.0
    gy[1:-1, :] = (y[2:, :] - y[:-2, :]) / 2.0
    return np.hypot(gx, gy)


def continuite_raccord(final: np.ndarray, masque: np.ndarray, alpha: np.ndarray) -> dict:
    """Compare l'intensité des contours sur le raccord à celle de son voisinage.

    Un rapport proche de 1 : le raccord ne se distingue pas. Nettement au-dessus :
    une bordure de détourage est probable.
    """
    g = _gradient(luminance(final))
    bord = masque & ~eroder(masque, 1)
    transition = ((alpha > 0) & (alpha < 1)) | bord
    exterieur = dilater(masque, 14) & ~dilater(masque, 2)
    coeur = zone_editee(alpha)
    interieur = coeur & ~eroder(coeur, 12)
    if transition.sum() < 50 or exterieur.sum() < 50 or interieur.sum() < 50:
        return {"ratio": None, "conforme": None, "note": "Zone trop petite pour mesurer le raccord."}
    voisinage = (float(g[exterieur].mean()) + float(g[interieur].mean())) / 2.0
    ratio = float(g[transition].mean()) / voisinage if voisinage > 1e-6 else None
    return {
        "ratio": None if ratio is None else round(ratio, 3),
        "conforme": None if ratio is None else ratio <= SEUILS["raccord_ratio_max"],
    }


@dataclass
class Signature:
    grain_source: dict
    grain_edite: dict
    grain_ratios: dict
    grain_conforme: bool | None
    nettete_source: float | None
    nettete_editee: float | None
    nettete_ratio: float | None
    nettete_conforme: bool | None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def mesurer_signature(final: np.ndarray, masque: np.ndarray, alpha: np.ndarray) -> Signature:
    y = luminance(final)
    ref, edit = zone_reference(masque), zone_editee(alpha)
    r = residu(y)
    gs, ge = grain_par_bande(y, ref, r), grain_par_bande(y, edit, r)
    ratios = {}
    for cle in gs:
        if gs[cle] and ge[cle] is not None and gs[cle] > 0:
            ratios[cle] = round(ge[cle] / gs[cle], 3)
    grain_ok = (
        all(SEUILS["grain_ratio_min"] <= r <= SEUILS["grain_ratio_max"] for r in ratios.values())
        if ratios else None
    )
    ns, ne = nettete(y, ref), nettete(y, edit)
    nr = round(ne / ns, 3) if ns and ne is not None else None
    net_ok = None if nr is None else SEUILS["nettete_ratio_min"] <= nr <= SEUILS["nettete_ratio_max"]
    return Signature(
        grain_source={k: _arrondi(v) for k, v in gs.items()},
        grain_edite={k: _arrondi(v) for k, v in ge.items()},
        grain_ratios=ratios, grain_conforme=grain_ok,
        nettete_source=_arrondi(ns), nettete_editee=_arrondi(ne),
        nettete_ratio=nr, nettete_conforme=net_ok,
    )


def _arrondi(v: float | None) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3)


def score_defauts(signature: Signature, raccord: dict) -> float:
    """Somme d'écarts mesurables (plus bas = mieux). Ne dit rien de l'anatomie."""
    s = 0.0
    for r in signature.grain_ratios.values():
        s += abs(math.log(r)) if r > 0 else 5.0
    if signature.nettete_ratio:
        s += abs(math.log(signature.nettete_ratio))
    if raccord.get("ratio"):
        s += max(0.0, raccord["ratio"] - 1.0)
    return round(s, 4)
