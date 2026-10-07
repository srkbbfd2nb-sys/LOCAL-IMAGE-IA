"""Chargement des images et du masque, filtres de base (numpy seul)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from local_image_ia.gouvernance import ArretDeclare

FORMATS_SANS_PERTE = {".png", ".tif", ".tiff"}


def charger_image(chemin: str | Path) -> np.ndarray:
    """Image RVB 8 bits, orientation EXIF appliquée (photos d'iPhone)."""
    chemin = Path(chemin)
    if chemin.suffix.lower() in (".heic", ".heif"):
        raise ArretDeclare(
            f"{chemin.name} : le format HEIC n'est pas lu par ce code.",
            ["Sur l'iPhone : Réglages > Appareil photo > Formats > « Le plus compatible » (JPEG),",
             "ou convertis la photo en JPEG ou PNG avant de la déposer."],
        )
    with Image.open(chemin) as im:
        im = ImageOps.exif_transpose(im)
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()


def charger_masque(chemin: str | Path, forme: tuple[int, int]) -> np.ndarray:
    """Masque booléen : blanc = zone à modifier, noir = zone verrouillée."""
    with Image.open(chemin) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA"):
            # Masque peint sur calque transparent : l'opacité fait foi.
            gris = np.asarray(im.getchannel("A"), dtype=np.uint8)
        else:
            gris = np.asarray(im.convert("L"), dtype=np.uint8)
    if gris.shape != forme:
        raise ArretDeclare(
            "Le masque n'a pas la taille de la photo.",
            [f"photo : {forme[1]}×{forme[0]}", f"masque : {gris.shape[1]}×{gris.shape[0]}",
             "Le masque doit être dessiné sur la photo d'origine, à la même taille."],
        )
    masque = gris >= 128
    if not masque.any():
        raise ArretDeclare("Le masque est entièrement noir : aucune zone à modifier.")
    if masque.all():
        raise ArretDeclare("Le masque est entièrement blanc : rien n'est verrouillé.")
    return masque


def adapter_candidat(candidat: np.ndarray, forme: tuple[int, int]) -> tuple[np.ndarray, str | None]:
    """Remet un candidat à la taille de l'original. Refuse un recadrage."""
    h, w = forme
    hc, wc = candidat.shape[:2]
    if (hc, wc) == (h, w):
        return candidat, None
    if abs(wc / hc - w / h) > 0.02 * (w / h):  # arrondis à 16 px du modèle : < 2 %
        raise ArretDeclare(
            "Le candidat n'a pas les proportions de l'original : il a été recadré.",
            [f"original : {w}×{h}", f"candidat : {wc}×{hc}",
             "Un recadrage décale les pixels : le verrou par masque ne peut pas s'appliquer."],
        )
    im = Image.fromarray(candidat).resize((w, h), Image.Resampling.LANCZOS)
    note = (f"Candidat redimensionné de {wc}×{hc} à {w}×{h} (Lanczos) : la zone éditée "
            "peut être plus douce que l'original, voir la mesure de netteté.")
    return np.asarray(im, dtype=np.uint8).copy(), note


def enregistrer_png(image: np.ndarray, chemin: str | Path) -> None:
    # Sans perte quel que soit le niveau ; 1 = compression rapide, fichier plus gros.
    Image.fromarray(image).save(chemin, format="PNG", compress_level=1)


def cadre_utile(masque: np.ndarray, marge: int) -> tuple[slice, slice]:
    """Rectangle englobant le masque, élargi de ``marge`` pixels (borné à l'image).

    Le fondu, l'anneau de référence et les mesures ne regardent jamais plus loin
    que cette marge : calculer sur ce cadre donne le même résultat, plus vite.
    """
    lignes = np.flatnonzero(masque.any(axis=1))
    colonnes = np.flatnonzero(masque.any(axis=0))
    h, w = masque.shape
    return (
        slice(max(0, lignes[0] - marge), min(h, lignes[-1] + 1 + marge)),
        slice(max(0, colonnes[0] - marge), min(w, colonnes[-1] + 1 + marge)),
    )


def flou_boite(a: np.ndarray, rayon: int) -> np.ndarray:
    """Moyenne sur une fenêtre (2r+1)², bords répliqués. Séparable, via sommes cumulées."""
    if rayon <= 0:
        return a.astype(np.float32)
    x = a.astype(np.float64)
    taille = 2 * rayon + 1
    for axe in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axe] = (rayon + 1, rayon)
        p = np.pad(x, pad, mode="edge")
        c = np.cumsum(p, axis=axe)
        if axe == 0:
            x = (c[taille:, :] - c[:-taille, :]) / taille
        else:
            x = (c[:, taille:] - c[:, :-taille]) / taille
    return x.astype(np.float32)


def dilater(masque: np.ndarray, rayon: int) -> np.ndarray:
    return flou_boite(masque, rayon) > 1e-6


def eroder(masque: np.ndarray, rayon: int) -> np.ndarray:
    return flou_boite(masque, rayon) > 1 - 1e-6


def alpha_interne(masque: np.ndarray, fondu: int) -> np.ndarray:
    """Fondu entièrement à l'intérieur du masque : alpha vaut 0 partout hors masque.

    Le fondu adoucit le raccord sans jamais toucher un pixel verrouillé.
    """
    m = masque.astype(np.float32)
    if fondu <= 0:
        return m
    rampe = np.clip((flou_boite(m, fondu) - 0.5) * 2.0, 0.0, 1.0)
    return (rampe * m).astype(np.float32)


def luminance(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
