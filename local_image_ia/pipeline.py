"""Déroulé d'une demande, côté code.

1. La demande est figée (empreinte) et compilée en contrat.        → ``compiler_demande``
2. Le modèle produit des candidats dans ComfyUI, avec l'instruction. → hors de ce code
3. Hors masque, l'original est recopié ; le grain est réappliqué ;
   chaque candidat est mesuré ; rapport ligne par ligne.            → ``finaliser``
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from local_image_ia.contrat import (
    COMPLETE, CONDENSEE, Contrat, charger_routage_manuel, compiler, verifier_non_suppression,
)
from local_image_ia.demande import DemandeFigee
from local_image_ia.gouvernance import ArretDeclare, verifier_circularite
from local_image_ia.images import (
    FORMATS_SANS_PERTE, adapter_candidat, alpha_interne, cadre_utile, charger_image,
    charger_masque, enregistrer_png,
)
from local_image_ia.mecanismes import capacites_phase0
from local_image_ia.mesures import continuite_raccord, ecart_hors_masque, mesurer_signature, score_defauts
from local_image_ia.rapport import MesuresCandidat, rapport_markdown
from local_image_ia.signature import reappliquer_grain
from local_image_ia.socle import charger_socle
from local_image_ia.verrou import composer

MARGE_CADRE = 64
JUGE_PAR_DEFAUT = "œil humain, aidé des mesures du code"
GENERATEUR_PAR_DEFAUT = "modèle d'édition dans ComfyUI (déclaré, non vu par ce code)"


def compiler_demande(
    chemin_demande: str | Path,
    dossier_sortie: str | Path,
    chemin_routage: str | Path | None = None,
    types: list[str] | None = None,
    chemin_socle: str | Path | None = None,
) -> Contrat:
    demande = DemandeFigee.depuis_fichier(chemin_demande)
    manuel = charger_routage_manuel(chemin_routage, demande) if chemin_routage else None
    contrat = compiler(demande, charger_socle(chemin_socle), manuel, types)
    sortie = Path(dossier_sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    contrat.enregistrer(sortie / "contrat.json")
    (sortie / "instruction_complete.txt").write_text(contrat.instruction(COMPLETE), "utf-8")
    (sortie / "instruction_condensee.txt").write_text(contrat.instruction(CONDENSEE), "utf-8")
    invariant = verifier_non_suppression(contrat)
    (sortie / "rapport_contrat.md").write_text(
        rapport_markdown(contrat, [], capacites_phase0(), invariant, "Contrat compilé"), "utf-8"
    )
    return contrat


def finaliser(
    contrat: Contrat,
    chemin_original: str | Path,
    chemin_masque: str | Path,
    chemins_candidats: list[str | Path],
    dossier_sortie: str | Path,
    fondu: int = 8,
    graine: int = 0,
    generateur: str = GENERATEUR_PAR_DEFAUT,
    juge: str = JUGE_PAR_DEFAUT,
) -> list[MesuresCandidat]:
    debut = time.monotonic()
    verifier_circularite(generateur, juge)
    invariant = verifier_non_suppression(contrat)
    if not chemins_candidats:
        raise ArretDeclare("Aucun candidat fourni.")

    original = charger_image(chemin_original)
    masque = charger_masque(chemin_masque, original.shape[:2])
    # Tout ce qui suit ne regarde pas au-delà de l'anneau de référence (48 px) :
    # on calcule sur ce cadre, et l'original est recopié tel quel autour.
    cadre = cadre_utile(masque, MARGE_CADRE + max(fondu, 0))
    m_c = masque[cadre]
    o_c = original[cadre]
    alpha = alpha_interne(m_c, fondu)
    sortie = Path(dossier_sortie)
    sortie.mkdir(parents=True, exist_ok=True)

    resultats: list[MesuresCandidat] = []
    for i, chemin in enumerate(chemins_candidats, start=1):
        notes: list[str] = []
        candidat, note = adapter_candidat(charger_image(chemin), original.shape[:2])
        if note:
            notes.append(note)
        final_c = composer(o_c, candidat[cadre], alpha)
        final_c, grain = reappliquer_grain(final_c, alpha, m_c, graine=graine + i)
        final = original.copy()
        final[cadre] = final_c
        if grain.exces_par_bande:
            notes.append("Zone éditée plus bruitée que la source (non corrigé) : "
                         + ", ".join(f"{k} ×{v}" for k, v in grain.exces_par_bande.items()))
        if grain.bandes_sans_donnees:
            notes.append("Grain non mesurable dans les bandes de luminance "
                         + ", ".join(grain.bandes_sans_donnees) + " (trop peu de pixels).")
        hors = ecart_hors_masque(original, final, masque)
        if not hors["conforme"]:
            raise ArretDeclare(
                f"Verrou violé sur {Path(chemin).name} : des pixels hors masque ont changé.",
                [f"{hors['pixels_differents']} pixels, écart max {hors['ecart_max']}"],
            )
        raccord = continuite_raccord(final_c, m_c, alpha)
        signature = mesurer_signature(final_c, m_c, alpha)
        fichier = f"candidat_{i:02d}.png"
        enregistrer_png(final, sortie / fichier)
        resultats.append(MesuresCandidat(
            nom=f"C{i}", fichier=fichier, hors_masque=hors, raccord=raccord,
            signature=signature.to_dict(),
            grain_reapplique={"graine": grain.graine, "ajout_par_bande": grain.ajout_par_bande},
            score=score_defauts(signature, raccord), notes=notes,
        ))

    resultats.sort(key=lambda c: c.score)
    if Path(chemin_original).suffix.lower() not in FORMATS_SANS_PERTE:
        resultats[0].notes.append(
            "Original en JPEG : les sorties sont en PNG pour que le verrou reste exact. "
            "Une conversion en JPEG ensuite modifierait légèrement tous les pixels."
        )

    duree = round(time.monotonic() - debut, 1)
    titre = f"Rapport — {datetime.now():%Y-%m-%d %H:%M}"
    md = rapport_markdown(contrat, resultats, capacites_phase0(), invariant, titre,
                          juge=juge, generateur=generateur)
    md += f"\nDurée du traitement par le code : {duree} s (hors génération).\n"
    (sortie / "rapport.md").write_text(md, "utf-8")
    (sortie / "rapport.json").write_text(json.dumps({
        "empreinte_demande": contrat.demande.empreinte,
        "original": str(chemin_original), "masque": str(chemin_masque), "fondu": fondu,
        "generateur": generateur, "juge": juge, "duree_code_s": duree,
        "invariant": invariant,
        "candidats": [c.__dict__ for c in resultats],
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return resultats
