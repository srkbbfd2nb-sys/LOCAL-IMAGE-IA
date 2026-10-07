"""Déroulé d'une demande, côté code.

1. La demande est figée (empreinte) et compilée en contrat.        → ``compiler_demande``
2. Le modèle produit des candidats (ComfyUI).                       → ``automate``
3. Édition : la zone modifiée est délimitée (masque fourni ou automatique), la
   dérive de couleur du modèle est corrigée, l'original est recopié hors de cette
   zone, le grain manquant est réappliqué ; chaque candidat est mesuré.
   Référence et création : pas d'original à recopier, les candidats sont rendus
   tels quels avec le rapport.                                       → ``finaliser``
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from local_image_ia.contrat import (
    COMPLETE, CONDENSEE, Contrat, charger_routage_manuel, compiler, verifier_non_suppression,
)
from local_image_ia.demande import DemandeFigee
from local_image_ia.gouvernance import ArretDeclare, Capacite, verifier_circularite
from local_image_ia.images import (
    FORMATS_SANS_PERTE, adapter_candidat, alpha_interne, cadre_utile, charger_image,
    charger_masque, enregistrer_png,
)
from local_image_ia.masque_auto import estimer_derive, masque_par_difference, reduire
from local_image_ia.mecanismes import capacites_phase0
from local_image_ia.mesures import continuite_raccord, ecart_hors_masque, mesurer_signature, score_defauts
from local_image_ia.rapport import MesuresCandidat, rapport_markdown
from local_image_ia.signature import reappliquer_grain
from local_image_ia.socle import charger_socle
from local_image_ia.verrou import composer

MARGE_CADRE = 64
JUGE_PAR_DEFAUT = "œil humain, aidé des mesures du code"
GENERATEUR_PAR_DEFAUT = "modèle d'édition dans ComfyUI (déclaré, non vu par ce code)"
PRINCIPE_GRAIN = "S-SIG-01"
PRINCIPE_DERIVE = "S-SIG-03"


def compiler_demande(
    chemin_demande: str | Path,
    dossier_sortie: str | Path,
    chemin_routage: str | Path | None = None,
    types: list[str] | None = None,
    chemin_socle: str | Path | None = None,
    mode: str = "edition",
    orphelines: str = "instruction",
    socle_complet: bool = False,
) -> Contrat:
    demande = DemandeFigee.depuis_fichier(chemin_demande)
    manuel = charger_routage_manuel(chemin_routage, demande) if chemin_routage else None
    contrat = compiler(demande, charger_socle(chemin_socle), manuel, types, mode=mode,
                       orphelines=orphelines, socle_complet=socle_complet)
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


def statut_principe(contrat: Contrat, id_principe: str) -> tuple[str, str | None]:
    for s in contrat.socle:
        if s.principe.id == id_principe:
            return s.statut, s.conflit_avec
    return "absent", None


def finaliser(
    contrat: Contrat,
    chemin_original: str | Path,
    chemin_masque: str | Path | None,
    chemins_candidats: list[str | Path],
    dossier_sortie: str | Path,
    fondu: int = 8,
    graine: int = 0,
    generateur: str = GENERATEUR_PAR_DEFAUT,
    juge: str = JUGE_PAR_DEFAUT,
    chemin_protege: str | Path | None = None,
    capacites: list[Capacite] | None = None,
    durees: dict | None = None,
) -> list[MesuresCandidat]:
    """Édition. ``chemin_masque`` à None : masque automatique, candidat par candidat."""
    debut = time.monotonic()
    verifier_circularite(generateur, juge)
    invariant = verifier_non_suppression(contrat)
    if not chemins_candidats:
        raise ArretDeclare("Aucun candidat fourni.")

    original = charger_image(chemin_original)
    forme = original.shape[:2]
    masque_fourni = charger_masque(chemin_masque, forme) if chemin_masque else None
    protege = charger_masque(chemin_protege, forme) if chemin_protege else None
    sortie = Path(dossier_sortie)
    (sortie / "masques").mkdir(parents=True, exist_ok=True)

    statut_grain, ligne_grain = statut_principe(contrat, PRINCIPE_GRAIN)
    statut_derive, _ = statut_principe(contrat, PRINCIPE_DERIVE)
    notes_globales: list[str] = []
    if statut_grain == "suspendu":
        notes_globales.append(
            f"Grain non réappliqué : ta ligne {ligne_grain} l'interdit (le principe "
            f"{PRINCIPE_GRAIN} est suspendu). Le grain est seulement mesuré.")

    resultats: list[MesuresCandidat] = []
    for i, chemin in enumerate(chemins_candidats, start=1):
        notes: list[str] = []
        candidat, note = adapter_candidat(charger_image(chemin), forme)
        if note:
            notes.append(note)

        if masque_fourni is not None:
            masque = masque_fourni if protege is None else masque_fourni & ~protege
            derive = estimer_derive(reduire(original), reduire(candidat),
                                    zone=_reduire_masque(~masque, reduire(original).shape[:2]))
            info_masque = {"source": "fourni", "part": round(float(masque.mean()), 4)}
        else:
            auto = masque_par_difference(original, candidat, protege)
            masque, derive = auto.masque, auto.derive
            notes += auto.notes
            info_masque = {"source": "automatique", "part": round(auto.part, 4), "seuil": auto.seuil,
                           "ilots": auto.ilots}
        info_masque["derive"] = derive.to_dict()
        enregistrer_png((masque.astype(np.uint8) * 255), sortie / "masques" / f"C{i}.png")

        nom = f"candidat_{i:02d}.png"
        if not masque.any():
            enregistrer_png(original, sortie / nom)
            resultats.append(MesuresCandidat(
                nom=f"C{i}", fichier=nom, hors_masque=None, raccord={}, signature={},
                grain_reapplique={}, score=float("inf"), notes=notes, masque=info_masque,
                rejete="aucune modification détectée"))
            continue

        if statut_derive == "actif":
            candidat = derive.appliquer(candidat)
        cadre = cadre_utile(masque, MARGE_CADRE + max(fondu, 0))
        m_c, o_c = masque[cadre], original[cadre]
        alpha = alpha_interne(m_c, fondu)
        final_c = composer(o_c, candidat[cadre], alpha)
        grain_info: dict = {}
        if statut_grain == "actif":
            final_c, grain = reappliquer_grain(final_c, alpha, m_c, graine=graine + i)
            grain_info = {"graine": grain.graine, "ajout_par_bande": grain.ajout_par_bande}
            if grain.exces_par_bande:
                notes.append("Zone éditée plus bruitée que la source (non corrigé) : "
                             + ", ".join(f"{k} ×{v}" for k, v in grain.exces_par_bande.items()))
            if grain.bandes_sans_donnees:
                notes.append("Grain non mesurable dans les bandes de luminance "
                             + ", ".join(grain.bandes_sans_donnees) + " (trop peu de pixels).")
        final = original.copy()
        final[cadre] = final_c
        hors = ecart_hors_masque(original, final, masque)
        if not hors["conforme"]:
            raise ArretDeclare(
                f"Verrou violé sur {Path(chemin).name} : des pixels hors masque ont changé.",
                [f"{hors['pixels_differents']} pixels, écart max {hors['ecart_max']}"],
            )
        raccord = continuite_raccord(final_c, m_c, alpha)
        signature = mesurer_signature(final_c, m_c, alpha)
        enregistrer_png(final, sortie / nom)
        resultats.append(MesuresCandidat(
            nom=f"C{i}", fichier=nom, hors_masque=hors, raccord=raccord,
            signature=signature.to_dict(), grain_reapplique=grain_info,
            score=score_defauts(signature, raccord), notes=notes, masque=info_masque,
        ))

    resultats.sort(key=lambda c: c.score)
    if Path(chemin_original).suffix.lower() not in FORMATS_SANS_PERTE:
        notes_globales.append(
            "Original en JPEG : les sorties sont en PNG pour que le verrou reste exact. "
            "Une conversion en JPEG ensuite modifierait légèrement tous les pixels.")
    _ecrire_sorties(contrat, resultats, sortie, invariant, capacites, durees, generateur, juge,
                    notes_globales, debut, {"original": str(chemin_original),
                                            "masque": str(chemin_masque) if chemin_masque else "automatique",
                                            "protege": str(chemin_protege) if chemin_protege else None,
                                            "fondu": fondu})
    return resultats


def finaliser_sans_original(
    contrat: Contrat,
    chemins_candidats: list[str | Path],
    dossier_sortie: str | Path,
    generateur: str = GENERATEUR_PAR_DEFAUT,
    juge: str = JUGE_PAR_DEFAUT,
    capacites: list[Capacite] | None = None,
    durees: dict | None = None,
) -> list[MesuresCandidat]:
    """Référence et création : rien à recopier ni à comparer, aucun classement mesuré."""
    debut = time.monotonic()
    verifier_circularite(generateur, juge)
    invariant = verifier_non_suppression(contrat)
    sortie = Path(dossier_sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    resultats = []
    for i, chemin in enumerate(chemins_candidats, start=1):
        nom = f"candidat_{i:02d}.png"
        enregistrer_png(charger_image(chemin), sortie / nom)
        resultats.append(MesuresCandidat(
            nom=f"C{i}", fichier=nom, hors_masque=None, raccord={}, signature={},
            grain_reapplique={}, score=float("nan"), notes=[], masque={"source": "aucun"}))
    notes = [f"Mode {contrat.mode} : pas d'original à recopier ni de mesure de comparaison. "
             "Les candidats sont dans l'ordre de génération ; c'est ton œil qui choisit."]
    _ecrire_sorties(contrat, resultats, sortie, invariant, capacites, durees, generateur, juge,
                    notes, debut, {})
    return resultats


def _reduire_masque(masque: np.ndarray, forme: tuple[int, int]) -> np.ndarray:
    im = Image.fromarray(masque.astype(np.uint8) * 255).resize((forme[1], forme[0]),
                                                               Image.Resampling.NEAREST)
    return np.asarray(im) > 127


def _ecrire_sorties(contrat, resultats, sortie, invariant, capacites, durees, generateur, juge,
                    notes_globales, debut, entrees) -> None:
    capacites = capacites if capacites is not None else capacites_phase0()
    retenu = next((c for c in resultats if not c.rejete), None)
    if retenu is not None:
        shutil.copyfile(sortie / retenu.fichier, sortie / "resultat.png")
    duree = round(time.monotonic() - debut, 1)
    titre = f"Rapport — {datetime.now():%Y-%m-%d %H:%M}"
    md = rapport_markdown(contrat, resultats, capacites, invariant, titre, juge=juge,
                          generateur=generateur, notes_globales=notes_globales, durees=durees,
                          retenu=retenu.nom if retenu else None)
    md += f"\nDurée du traitement par le code : {duree} s (hors génération).\n"
    (sortie / "rapport.md").write_text(md, "utf-8")
    (sortie / "rapport.json").write_text(json.dumps({
        "empreinte_demande": contrat.demande.empreinte, "mode": contrat.mode,
        **entrees, "generateur": generateur, "juge": juge, "duree_code_s": duree,
        "durees": durees or {}, "invariant": invariant,
        "retenu": retenu.fichier if retenu else None,
        "notes": notes_globales,
        "candidats": [c.to_dict() for c in resultats],
    }, ensure_ascii=False, indent=2) + "\n", "utf-8")
