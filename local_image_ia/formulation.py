"""Conseils de formulation pour FLUX.2 : repérer les lignes négatives.

FLUX.2 ne gère pas les formulations négatives : il faut décrire ce que l'on veut voir
(F : guide FLUX.2 de Black Forest Labs, « No negative prompts » ; prompt système officiel
d'édition : « Turn negatives into positives (don't change X → keep X) »).

Ces conseils ne modifient jamais la demande (règle de non-suppression) : ils sont
proposés dans le rapport, c'est toi qui décides de reformuler.
"""

from __future__ import annotations

import re

from local_image_ia.routage import normaliser

NEGATION = re.compile(
    r"\b(no|not|never|don't|dont|do not|avoid\w*|without|forbidden|ne|n'|pas|jamais|sans"
    r"|evit\w*|interdit\w*|aucun\w*)\b")

# (motif sur le texte normalisé, reformulation positive proposée, en anglais pour le modèle)
SUGGESTIONS: list[tuple[str, str]] = [
    (r"\b(generat\w*|recreat\w*|reinterpret\w*|redesign\w*|redraw\w*)\b", "edit this exact photo, changing only the requested area"),
    (r"\b(change\w*|modif\w*|alter\w*|touch\w*)\b.{0,40}\b(face|visage|identity|identite)", "keep the face and identity exactly as in the photo"),
    (r"\b(change\w*|modif\w*|alter\w*|move|touch\w*)\b.{0,40}\b(background|fond|environment|environnement)", "keep the background exactly as in the photo"),
    (r"\b(change\w*|modif\w*|alter\w*)\b.{0,40}\b(pose|camera|perspective)", "keep the same pose, camera and perspective"),
    (r"\bplastic\w*|\bwaxy\b|\bporcelain\b", "natural skin texture with visible pores"),
    (r"\b(blur\w*|flou)\b", "sharp focus matching the rest of the photo"),
    (r"\bhdr\b", "natural, everyday dynamic range"),
    (r"\b(studio|magazine|cinematic|dslr|advertis\w*|showroom)\b", "ordinary casual smartphone photo"),
    (r"\bbeaut\w*|\bfitness[- ]model\b|\bglamou?r\w*", "natural, unretouched look"),
    (r"\b(extra|duplicat\w*)\b.{0,15}\b(finger\w*|limb\w*|arm\w*|doigt\w*)", "five fingers per hand, two arms, plausible anatomy"),
    (r"\b(warp\w*|bend\w*|distort\w*|liquify)\b", "straight, undistorted lines around the edit"),
    (r"\b(halo\w*|ringing|cutout|seam\w*)\b", "clean organic edges blending into the scene"),
    (r"\bbodybuild\w*|\bv[- ]?taper\b|\bhuge\b|\boversized\b|\benormous\b", "athletic, moderate and natural proportions"),
    (r"\bvein\w*|\bvascular\w*", "smooth skin over naturally defined muscles"),
    (r"\bsix[- ]?pack\b|\bdrawn\b|\bpainted\b", "subtle definition through soft natural shading"),
    (r"\b(text|logo\w*|watermark\w*|caption\w*|overlay\w*)\b", "only the photographed scene"),
    (r"\b(new|added|rim|key)\b.{0,10}\blight\w*", "only the light already present in the scene"),
    (r"\bcontrast\b", "the photo's existing contrast"),
    (r"\b(sharper|cleaner|brighter)\b", "the same sharpness, noise and brightness as the rest of the photo"),
    (r"\bnoise\b|\bgrain\b|\bartifact\w*|\bartefact\w*", "the same natural grain as the rest of the photo"),
    (r"\b(people|personne\w*|crowd)\b", "an empty scene"),
]


# Une proposition ne vaut que pour la proposition grammaticale qui porte la négation :
# dans « never generate a new one. Give him a beautiful… », « beautiful » n'est pas nié.
_PROPOSITIONS = re.compile(r"[.;:!?]\s+|\s+[—–]\s+")


def proposer(texte: str) -> str | None:
    """Reformulation positive pour la première négation reconnue, sinon None."""
    for partie in _PROPOSITIONS.split(normaliser(texte)):
        m = NEGATION.search(partie)
        if not m:
            continue
        suite = partie[m.start():]
        for motif, suggestion in SUGGESTIONS:
            if re.search(motif, suite):
                return suggestion
    return None


def lignes_negatives(lignes: list[tuple[str, str]]) -> list[dict]:
    """[(id, texte)] → lignes formulées en négatif, avec une reformulation proposée.

    Chaque ligne est lue seule : sous un titre « Do not alter: », c'est le titre qui est
    signalé, pas chacune de ses lignes.
    """
    return [
        {"id": id_ligne, "texte": texte.strip(), "proposition": proposer(texte)}
        for id_ligne, texte in lignes if NEGATION.search(normaliser(texte))
    ]
