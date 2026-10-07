"""Recoloration par l'ombrage d'origine (changement de couleur d'un objet uni).

Pour un changement de couleur, la lumière n'a pas à être confiée au modèle : une
photo est, en première approximation, couleur propre de l'objet × éclairage. Si
l'objet était uniforme, l'éclairage de chaque pixel (ombres, plis, reflets, texture
du tissu) se lit dans l'original ; la nouvelle couleur se lit dans le candidat, là
où l'objet est pleinement éclairé. Le résultat :

    nouveau = original × (couleur cible éclairée / couleur d'origine éclairée)

calculé canal par canal en lumière linéaire. Les ombres que le modèle n'a pas su
recolorer sont reprises (îlots entourés par l'objet, de même couleur d'origine),
sans toucher à ce qui n'a pas la couleur de l'objet (un bras, un logo coloré).

Limites déclarées : objet de couleur d'origine uniforme ; une matière nouvelle à
reflets différents (cuir brillant, métal) n'est pas rendue par ce calcul ; un objet
d'origine très sombre amplifie le bruit (rapport borné).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from local_image_ia.images import alpha_interne, cadre_utile, dilater, eroder
from local_image_ia.masque_auto import reduire, trous

GAMMA = 2.2
ECART_CHANGE = 40.0        # écart (sur 255) pour qu'un pixel compte comme recoloré par le modèle (E)
TOLERANCE_CHROMA = 0.07    # écart de chromaticité toléré autour de la couleur cible ou d'origine (E)
PART_MIN = 0.002           # en dessous de 0,2 % de l'image recolorée : rien à faire
RAPPORT_MAX = 8.0          # borne du rapport cible / origine (objet d'origine très sombre)


@dataclass
class Recoloration:
    appliquee: bool
    note: str
    part: float = 0.0
    ombres_reprises: float = 0.0
    cible: list[int] = field(default_factory=list)
    origine: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _lineaire(x: np.ndarray) -> np.ndarray:
    return (x.astype(np.float32) / 255.0) ** GAMMA


def _srgb(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.clip(x, 0.0, 1.0) ** (1.0 / GAMMA) * 255.0), 0, 255).astype(np.uint8)


def _chroma(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    return x / (x.sum(axis=-1, keepdims=True) + 1e-3)


def _agrandir(m: np.ndarray, forme: tuple[int, int]) -> np.ndarray:
    im = Image.fromarray(m.astype(np.uint8) * 255).resize((forme[1], forme[0]), Image.Resampling.NEAREST)
    return np.asarray(im) > 127


def recolorer(
    original: np.ndarray, candidat: np.ndarray, masque: np.ndarray,
    protege: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, Recoloration]:
    """Renvoie (candidat recoloré, zone modifiée élargie aux ombres reprises, compte rendu)."""
    forme = original.shape[:2]
    o, c = reduire(original), reduire(candidat)
    m = np.asarray(Image.fromarray(masque.astype(np.uint8) * 255).resize(
        (o.shape[1], o.shape[0]), Image.Resampling.NEAREST)) > 127
    ecart = np.abs(c - o).mean(axis=-1)
    change = m & (ecart > ECART_CHANGE)
    if change.mean() < PART_MIN:
        return candidat, masque, Recoloration(False, "Recoloration non appliquée : pas de changement "
                                                     "de couleur net dans la zone modifiée.")
    cible_chroma = np.median(_chroma(c)[change], axis=0)
    objet = m & (np.abs(_chroma(c) - cible_chroma).sum(axis=-1) < TOLERANCE_CHROMA) & (ecart > 15)
    objet = dilater(eroder(objet, 1), 1)
    if objet.mean() < PART_MIN:
        return candidat, masque, Recoloration(False, "Recoloration non appliquée : couleur cible "
                                                     "trop dispersée (objet non uniforme ?).")
    origine_chroma = np.median(_chroma(o)[objet], axis=0)
    compatible = np.abs(_chroma(o) - origine_chroma).sum(axis=-1) < TOLERANCE_CHROMA
    # Ombres oubliées : zones entourées par l'objet, de la même couleur d'origine.
    reprises = trous(objet) & compatible

    # Pleine résolution, dans le cadre de la zone utile seulement.
    zone_basse = objet | reprises
    zone = _agrandir(dilater(zone_basse, 1), forme)
    if protege is not None:
        zone &= ~protege
    cadre = cadre_utile(zone, 8)
    O = _lineaire(original[cadre])
    C = _lineaire(candidat[cadre])
    chroma_c = _chroma(candidat[cadre])
    chroma_o = _chroma(original[cadre])
    ecart_plein = np.abs(candidat[cadre].astype(np.float32) - original[cadre]).mean(axis=-1)
    objet_plein = (np.abs(chroma_c - cible_chroma).sum(axis=-1) < TOLERANCE_CHROMA) & (ecart_plein > 15)
    reprises_plein = _agrandir(dilater(reprises, 1), forme)[cadre] & (
        np.abs(chroma_o - origine_chroma).sum(axis=-1) < TOLERANCE_CHROMA)
    z = zone[cadre] & (objet_plein | reprises_plein)
    z = dilater(eroder(z, 1), 1)
    if z.sum() < 100:
        return candidat, masque, Recoloration(False, "Recoloration non appliquée : zone trop petite.")

    lum = 0.2126 * O[..., 0] + 0.7152 * O[..., 1] + 0.0722 * O[..., 2]
    ref = float(np.percentile(lum[z], 90))
    eclaire = z & objet_plein & (lum > 0.8 * ref) & (lum < 1.2 * ref)
    if eclaire.sum() < 100:
        return candidat, masque, Recoloration(False, "Recoloration non appliquée : trop peu de zone "
                                                     "pleinement éclairée pour lire la couleur cible.")
    couleur_origine = np.median(O[eclaire], axis=0)
    couleur_cible = np.median(C[eclaire], axis=0)
    rapport = np.clip(couleur_cible / np.maximum(couleur_origine, 1e-3), 0.0, RAPPORT_MAX)
    nouveau = O * rapport
    alpha = alpha_interne(z, 2)[..., None]
    resultat = _srgb(C * (1 - alpha) + nouveau * alpha)

    sortie = candidat.copy()
    sortie[cadre] = np.where(alpha > 0, resultat, candidat[cadre])
    zone_finale = np.zeros(forme, bool)
    zone_finale[cadre] = z
    part = float(zone_finale.mean())
    ombres = float((zone_finale & ~masque).mean())
    note = (f"Recoloration par l'ombrage d'origine sur {part:.1%} de l'image : ombres, plis et "
            f"texture viennent de ta photo, la couleur du modèle."
            + (f" Ombres reprises que le modèle avait laissées : {ombres:.1%} de l'image." if ombres else ""))
    return sortie, masque | zone_finale, Recoloration(
        True, note, round(part, 4), round(ombres, 4),
        [int(v) for v in _srgb(couleur_cible)], [int(v) for v in _srgb(couleur_origine)])
