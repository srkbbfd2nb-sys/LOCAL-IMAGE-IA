"""Mécanisme 4 : signature photographique.

Le grain et la netteté sont mesurés sur la source autour de la zone, puis
comparés à la zone éditée. Le grain manquant est réappliqué ; un excès de
grain ou une différence de netteté sont mesurés et signalés, pas corrigés.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from local_image_ia.images import dilater, flou_boite, luminance

BANDES = ((0, 64), (64, 128), (128, 192), (192, 256))
PIXELS_MIN = 400
# Pour un bruit blanc d'écart type s, le résidu « pixel moins moyenne 3×3 »
# a un écart type s·sqrt(8/9).
_FACTEUR_RESIDU = float(np.sqrt(8.0 / 9.0))


def residu(y: np.ndarray) -> np.ndarray:
    return y - flou_boite(y, 1)


def sigma_robuste(v: np.ndarray) -> float:
    """Écart type estimé par la médiane des écarts absolus, peu sensible aux contours."""
    if v.size == 0:
        return float("nan")
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def zone_reference(masque: np.ndarray, largeur: int = 48) -> np.ndarray:
    """Anneau de pixels d'origine autour du masque."""
    anneau = dilater(masque, largeur) & ~masque
    if anneau.sum() < PIXELS_MIN * 4:
        anneau = ~masque
    return anneau


def zone_editee(alpha: np.ndarray) -> np.ndarray:
    return alpha >= 0.99


def grain_par_bande(
    y: np.ndarray, zone: np.ndarray, r: np.ndarray | None = None
) -> dict[str, float | None]:
    r = residu(y) if r is None else r
    sortie: dict[str, float | None] = {}
    for bas, haut in BANDES:
        sel = zone & (y >= bas) & (y < haut)
        sortie[f"{bas}-{haut}"] = sigma_robuste(r[sel]) if sel.sum() >= PIXELS_MIN else None
    return sortie


def nettete(y: np.ndarray, zone: np.ndarray) -> float | None:
    lap = np.zeros_like(y)
    lap[1:-1, 1:-1] = (
        y[:-2, 1:-1] + y[2:, 1:-1] + y[1:-1, :-2] + y[1:-1, 2:] - 4.0 * y[1:-1, 1:-1]
    )
    sel = zone.copy()
    sel[[0, -1], :] = False
    sel[:, [0, -1]] = False
    if sel.sum() < PIXELS_MIN:
        return None
    return float(np.var(lap[sel]))


@dataclass
class ReapplicationGrain:
    graine: int
    ajout_par_bande: dict[str, float] = field(default_factory=dict)
    exces_par_bande: dict[str, float] = field(default_factory=dict)
    bandes_sans_donnees: list[str] = field(default_factory=list)


def reappliquer_grain(
    image: np.ndarray, alpha: np.ndarray, masque: np.ndarray, graine: int = 0
) -> tuple[np.ndarray, ReapplicationGrain]:
    """Ajoute dans la zone éditée le grain qui lui manque par rapport à la source.

    Le bruit est pondéré par alpha : hors masque, rien ne change.
    """
    y = luminance(image)
    r = residu(y)
    ref = grain_par_bande(y, zone_reference(masque), r)
    edit = grain_par_bande(y, zone_editee(alpha), r)
    rapport = ReapplicationGrain(graine=graine)

    ajout_residu = np.zeros_like(y)
    for bas, haut in BANDES:
        cle = f"{bas}-{haut}"
        s_ref, s_edit = ref[cle], edit[cle]
        if s_ref is None or s_edit is None:
            rapport.bandes_sans_donnees.append(cle)
            continue
        if s_ref > s_edit:
            besoin = float(np.sqrt(s_ref**2 - s_edit**2))
            rapport.ajout_par_bande[cle] = round(besoin / _FACTEUR_RESIDU, 3)
            ajout_residu[(y >= bas) & (y < haut)] = besoin
        elif s_edit > s_ref * 1.05:
            rapport.exces_par_bande[cle] = round(s_edit / s_ref, 3) if s_ref > 0 else float("inf")

    if not rapport.ajout_par_bande:
        return image, rapport
    rng = np.random.default_rng(graine)
    bruit = rng.standard_normal(y.shape).astype(np.float32)
    ecart = ajout_residu / _FACTEUR_RESIDU * alpha
    # Grain de luminance : même valeur sur les trois canaux.
    sortie = image.astype(np.float32) + (bruit * ecart)[..., None]
    sortie = np.clip(np.rint(sortie), 0, 255).astype(np.uint8)
    return np.where((alpha == 0.0)[..., None], image, sortie), rapport
