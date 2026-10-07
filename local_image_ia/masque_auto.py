"""Masque automatique par différence, et correction de dérive colorimétrique.

Quand aucun masque n'est fourni, la zone modifiée est déduite du candidat : là où
il diffère nettement de l'original (après correction de la dérive de couleur que
le modèle applique souvent à toute l'image). Tout le reste est recopié depuis
l'original, en pleine résolution.

Limite déclarée : ce masque protège tout ce que le modèle n'a pas voulu changer,
mais pas une zone qu'il a changée à tort (un visage légèrement altéré fait partie
de la différence). Un masque « protégé » peut être fourni pour ces zones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from local_image_ia.images import dilater, eroder, flou_boite

COTE_ANALYSE = 512        # la différence est calculée sur une version réduite (plus robuste au bruit)
SEUIL_MIN = 12.0          # écart minimal (sur 255) pour compter comme modification (E)
FACTEUR_MAD = 6.0
PART_MAX_SIGNALEE = 0.6   # au-delà, le verrou protège peu : déclaré
GAIN_BORNES = (0.8, 1.25)
DECALAGE_BORNES = (-30.0, 30.0)


@dataclass
class Derive:
    gains: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    decalages: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def appliquer(self, image: np.ndarray) -> np.ndarray:
        x = image.astype(np.float32)
        for c in range(3):
            x[..., c] = x[..., c] * self.gains[c] + self.decalages[c]
        return np.clip(np.rint(x), 0, 255).astype(np.uint8)

    def to_dict(self) -> dict:
        return {"gains": [round(g, 4) for g in self.gains],
                "decalages": [round(d, 2) for d in self.decalages]}


ILOT_SIGNALE = 0.002     # îlot inchangé de plus de 0,2 % de l'image : signalé (E)


@dataclass
class MasqueAuto:
    masque: np.ndarray
    part: float
    seuil: float
    derive: Derive
    notes: list[str] = field(default_factory=list)
    ilots: float = 0.0


def trous(masque: np.ndarray) -> np.ndarray:
    """Zones hors masque entièrement entourées par le masque (non reliées au bord)."""
    libre = ~masque
    atteint = np.zeros_like(libre)
    atteint[0, :], atteint[-1, :] = libre[0, :], libre[-1, :]
    atteint[:, 0], atteint[:, -1] = libre[:, 0], libre[:, -1]
    while True:
        n = atteint.copy()
        n[1:, :] |= atteint[:-1, :]
        n[:-1, :] |= atteint[1:, :]
        n[:, 1:] |= atteint[:, :-1]
        n[:, :-1] |= atteint[:, 1:]
        n &= libre
        if np.array_equal(n, atteint):
            return libre & ~atteint
        atteint = n


def reduire(image: np.ndarray, cote: int = COTE_ANALYSE) -> np.ndarray:
    h, w = image.shape[:2]
    f = cote / max(h, w)
    if f >= 1:
        return image.astype(np.float32)
    taille = (max(1, round(w * f)), max(1, round(h * f)))
    return np.asarray(Image.fromarray(image).resize(taille, Image.Resampling.BOX), np.float32)


def estimer_derive(original: np.ndarray, candidat: np.ndarray, zone: np.ndarray | None = None,
                   iterations: int = 3) -> Derive:
    """Ajuste, canal par canal, candidat × gain + décalage ≈ original sur la zone stable.

    Le gain vient du rapport des étendues (5e à 95e centile) : contrairement à une
    régression, il n'est pas biaisé par le bruit ni par le lissage du modèle. Sur une
    zone sans contraste (étendue < 40 niveaux), seul le décalage est corrigé.
    Sans zone, l'estimation écarte à chaque passe les pixels les plus différents
    (ceux que le modèle a vraiment modifiés).
    """
    o = original.reshape(-1, 3).astype(np.float64)
    c = candidat.reshape(-1, 3).astype(np.float64)
    garder = np.ones(len(o), bool) if zone is None else zone.reshape(-1)
    if garder.sum() < 100:
        return Derive()
    derive = Derive()
    for _ in range(iterations):
        for k in range(3):
            x, y = c[garder, k], o[garder, k]
            px, py = np.percentile(x, [5, 50, 95]), np.percentile(y, [5, 50, 95])
            etendue = px[2] - px[0]
            gain = float(np.clip((py[2] - py[0]) / etendue, *GAIN_BORNES)) if etendue >= 40 else 1.0
            dec = float(np.clip(py[1] - gain * px[1], *DECALAGE_BORNES))
            derive.gains[k], derive.decalages[k] = gain, dec
        if zone is not None:
            break
        corrige = c * np.array(derive.gains) + np.array(derive.decalages)
        ecart = np.abs(corrige - o).mean(axis=1)
        garder = ecart <= np.percentile(ecart, 70)
    return derive


def masque_par_difference(
    original: np.ndarray, candidat: np.ndarray, protege: np.ndarray | None = None,
) -> MasqueAuto:
    """``protege`` (booléen, pleine résolution) : zones toujours recopiées de l'original."""
    h, w = original.shape[:2]
    o = reduire(original)
    c = reduire(candidat)
    derive = estimer_derive(o, c)
    c_corr = derive.appliquer(np.clip(c, 0, 255).astype(np.uint8)).astype(np.float32)
    d = flou_boite(np.abs(c_corr - o).mean(axis=-1), 2)
    med = float(np.median(d))
    mad = float(np.median(np.abs(d - med))) * 1.4826
    seuil = max(SEUIL_MIN, med + FACTEUR_MAD * mad)
    m = d > seuil
    notes: list[str] = []
    if m.any():
        m = dilater(eroder(m, 1), 1)          # ouverture : retire les points isolés
        m = eroder(dilater(m, 6), 6)          # fermeture : bouche les trous
        marge = max(3, round(0.015 * max(m.shape)))
        m = dilater(m, marge)                 # inclut les transitions du modèle
    # Îlot : zone que le modèle a laissée telle quelle au milieu de ce qu'il a modifié.
    # Le masque vient de la différence, donc un îlot est toujours un choix du modèle
    # (souvent un oubli : partie claire d'un vêtement restée dans l'ancienne couleur).
    ilots = float(trous(m).mean()) if m.any() else 0.0
    plein = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.Resampling.NEAREST)) > 127
    if protege is not None:
        if (plein & protege).any():
            notes.append("Une partie de la zone modifiée par le modèle est dans la zone protégée : "
                         "elle a été recopiée de l'original.")
        plein &= ~protege
    part = float(plein.mean())
    if part == 0:
        notes.append("Aucune modification nette détectée : le candidat ressemble à l'original.")
    elif part > PART_MAX_SIGNALEE:
        notes.append(f"Le modèle a modifié {part:.0%} de l'image : le verrou protège peu ici.")
    if ilots >= ILOT_SIGNALE:
        notes.append(f"Îlot inchangé de {ilots:.1%} de l'image au milieu de la zone modifiée : le "
                     "modèle y a laissé l'original (visible en noir dans masques/). Vérifie à l'œil : "
                     "c'est souvent un oubli, sauf si c'est une zone qui devait rester (visage…).")
    # Dérive réestimée sur la seule zone stable, en pleine définition d'analyse.
    stable = np.asarray(Image.fromarray((~plein).astype(np.uint8) * 255).resize(
        (o.shape[1], o.shape[0]), Image.Resampling.NEAREST)) > 127
    if stable.sum() > 1000:
        derive = estimer_derive(o, c, stable)
    return MasqueAuto(masque=plein, part=part, seuil=round(seuil, 2), derive=derive, notes=notes,
                      ilots=round(ilots, 4))
