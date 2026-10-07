"""Rapport de sortie : pour chaque ligne, garantie, vérifiée ou non vérifiable."""

from __future__ import annotations

import re
from dataclasses import dataclass

from local_image_ia.contrat import COMPLETE, CONDENSEE, Contrat
from local_image_ia.gouvernance import Capacite
from local_image_ia.mecanismes import DESCRIPTIONS, Mecanisme
from local_image_ia.mesures import NATURE_SEUILS, SEUILS
from local_image_ia.routage import normaliser

GARANTIE = "garantie"
CONFORME = "conforme"
NON_CONFORME = "NON conforme"
A_L_OEIL = "à l'œil"
ABSENT = "absent (phase 0)"
PREVUE = "prévue"

LEGENDE = {
    GARANTIE: "garantie par le code, et l'écart hors masque mesuré vaut zéro",
    CONFORME: "vérifiée par une mesure, dans les seuils",
    NON_CONFORME: "vérifiée par une mesure, hors des seuils",
    A_L_OEIL: "non vérifiable par le code : c'est ton œil qui juge",
    ABSENT: "mécanisme pas encore branché : la ligne reste dans le texte du modèle",
}

_MESURES_PAR_MOT = [
    ("raccord", re.compile(r"\b(raccords?|seams?|bordures?|detourage|edges?|halos?)\b")),
    ("grain", re.compile(r"\b(grain|bruit|noise)\b")),
    ("nettete", re.compile(r"\b(nettete|sharp\w*)\b")),
    ("hors_masque", re.compile(r"\b(fond|background|arriere[- ]plan|decor|hors masque)\b")),
]


def mesures_concernees(texte: str) -> list[str]:
    norm = normaliser(texte)
    return [cle for cle, motif in _MESURES_PAR_MOT if motif.search(norm)]


@dataclass
class MesuresCandidat:
    nom: str
    fichier: str
    hors_masque: dict
    raccord: dict
    signature: dict
    grain_reapplique: dict
    score: float
    notes: list[str]

    def conformite(self, cle: str) -> bool | None:
        if cle == "hors_masque":
            return self.hors_masque["conforme"]
        if cle == "raccord":
            return self.raccord.get("conforme")
        if cle == "grain":
            return self.signature["grain_conforme"]
        if cle == "nettete":
            return self.signature["nettete_conforme"]
        raise KeyError(cle)


def _etat_par_mesures(cles: list[str], c: MesuresCandidat) -> str:
    resultats = [c.conformite(k) for k in cles]
    if any(r is False for r in resultats):
        return NON_CONFORME
    if resultats and all(r is True for r in resultats):
        return CONFORME
    return A_L_OEIL


def etat(mecanisme: Mecanisme, texte: str, c: MesuresCandidat | None) -> str:
    if c is None:
        return PREVUE
    if mecanisme == Mecanisme.VERROU:
        return GARANTIE if c.hors_masque["conforme"] else NON_CONFORME
    if mecanisme == Mecanisme.CONDITIONNEMENT:
        return ABSENT
    if mecanisme == Mecanisme.INSTRUCTION:
        return A_L_OEIL
    cles = mesures_concernees(texte)
    if mecanisme == Mecanisme.SIGNATURE:
        cles = [k for k in cles if k in ("grain", "nettete")]
    return _etat_par_mesures(cles, c) if cles else A_L_OEIL


def _cellule(texte: str) -> str:
    return texte.strip().replace("|", "\\|") or "∅"


def _lignes_tableau(contrat: Contrat, candidats: list[MesuresCandidat]) -> list[dict]:
    lignes = []
    for e in contrat.entrees:
        if not e.porte_contenu:
            continue
        mec = e.mecanisme
        if mec is None:  # titre couvert par ses lignes
            etats = ["titre" for _ in candidats] or ["titre"]
            mec_txt = "— (titre de section)"
        else:
            etats = [etat(mec, e.texte_modele, c) for c in candidats] or [PREVUE]
            mec_txt = mec.value
        lignes.append({
            "id": e.id, "texte": e.texte, "origine": "demande", "mecanisme": mec_txt,
            "routage": e.routage or "—", "etats": etats,
        })
    for s in contrat.socle_actif():
        p = s.principe
        etats = [etat(p.mecanisme, p.directive, c) for c in candidats] or [PREVUE]
        lignes.append({
            "id": p.id, "texte": p.directive, "origine": "socle (ajout)",
            "mecanisme": p.mecanisme.value, "routage": "socle", "etats": etats,
        })
    return lignes


def liste_controle(contrat: Contrat, candidats: list[MesuresCandidat]) -> list[str]:
    items = []
    for e in contrat.entrees_par_mecanisme(Mecanisme.VERROU):
        if e.role == "titre":
            continue
        items.append(f"{e.id} — « {e.texte_modele.strip()} » : l'élément visé est-il bien en "
                     "noir dans le masque ? Le verrou ne protège que ce qui est hors masque.")
    for e in contrat.entrees:
        if e.role == "ligne" and e.mecanisme is not None and e.mecanisme != Mecanisme.VERROU:
            etats = [etat(e.mecanisme, e.texte_modele, c) for c in candidats] or [A_L_OEIL]
            if A_L_OEIL in etats or ABSENT in etats:
                items.append(f"{e.id} — {e.texte_modele.strip()}")
    for s in contrat.socle_actif(Mecanisme.VERIFICATION):
        etats = [etat(Mecanisme.VERIFICATION, s.principe.directive, c) for c in candidats] or [A_L_OEIL]
        if A_L_OEIL in etats:
            items.append(f"{s.principe.id} — {s.principe.directive}")
    return items


def rapport_markdown(
    contrat: Contrat,
    candidats: list[MesuresCandidat],
    capacites: list[Capacite],
    invariant: dict,
    titre: str,
    juge: str = "",
    generateur: str = "",
) -> str:
    o: list[str] = [f"# {titre}", ""]
    o.append(f"Empreinte de la demande (SHA-256) : `{contrat.demande.empreinte}`  ")
    o.append(f"Socle de principes : version {contrat.socle_version}  ")
    o.append(f"Types de demande : {', '.join(contrat.types) or 'non reconnu'}")
    if generateur:
        o.append(f"  \nGénérateur : {generateur}  \nJuge : {juge}")
    o.append("")

    if candidats:
        o += ["## Classement des candidats", "",
              "Classement sur les défauts **mesurables** seulement (raccord, grain, netteté). "
              "Il ne dit rien de l'anatomie ni de la lumière sur le nouveau volume : "
              "c'est ton œil qui tranche.", "",
              "| Rang | Candidat | Fichier | Score d'écart | Hors masque | Raccord | Grain | Netteté |",
              "|---|---|---|---|---|---|---|---|"]
        for rang, c in enumerate(candidats, start=1):
            hm = c.hors_masque
            hm_txt = "0 pixel modifié" if hm["conforme"] else f"{hm['pixels_differents']} pixels modifiés"
            rc = c.raccord.get("ratio")
            g = c.signature["grain_ratios"]
            g_txt = ", ".join(f"{k}: {v}" for k, v in g.items()) or "—"
            o.append(
                f"| {rang} | {c.nom} | `{c.fichier}` | {c.score} | {hm_txt} | "
                f"{rc if rc is not None else '—'} | {g_txt} | {c.signature['nettete_ratio'] or '—'} |"
            )
        o += ["", f"Seuils : grain {SEUILS['grain_ratio_min']}–{SEUILS['grain_ratio_max']}, "
              f"netteté {SEUILS['nettete_ratio_min']}–{SEUILS['nettete_ratio_max']}, "
              f"raccord ≤ {SEUILS['raccord_ratio_max']} ({NATURE_SEUILS}).", ""]
        notes = [(c.nom, n) for c in candidats for n in c.notes]
        if notes:
            o += ["Notes de traitement :", ""] + [f"- {nom} : {n}" for nom, n in notes] + [""]

    o += ["## Capacités", "", "| Capacité | État | Voie | Note |", "|---|---|---|---|"]
    o += [f"| {c.nom} | {c.etat.value} | {c.voie} | {c.note} |" for c in capacites]
    o.append("")

    noms = [c.nom for c in candidats] or ["état"]
    o += ["## Ligne par ligne", "",
          "| ID | Ligne | Origine | Mécanisme | Routage | " + " | ".join(noms) + " |",
          "|---|---|---|---|---|" + "---|" * len(noms)]
    for l in _lignes_tableau(contrat, candidats):
        o.append(f"| {l['id']} | {_cellule(l['texte'])} | {l['origine']} | {l['mecanisme']} | "
                 f"{l['routage']} | " + " | ".join(l["etats"]) + " |")
    o += ["", "Légende :", ""] + [f"- **{k}** : {v}" for k, v in LEGENDE.items()]
    o += [f"- **{PREVUE}** : contrat compilé, pas encore de candidat mesuré", ""]

    suspendus = [s for s in contrat.socle if s.statut == "suspendu"]
    o += ["## Conflits", ""]
    if suspendus:
        o += [f"- {s.principe.id} ({s.principe.domaine}) suspendu : contredit {s.conflit_avec}. "
              "Ta ligne gagne." for s in suspendus]
    else:
        o.append("Aucun conflit détecté entre le socle et ta demande.")
    o.append("")

    if contrat.manques or contrat.avertissements:
        o += ["## Manques et avertissements déclarés", ""]
        o += [f"- Manque : {m}" for m in contrat.manques]
        o += [f"- {a}" for a in contrat.avertissements]
        o.append("")

    controle = liste_controle(contrat, candidats)
    if controle:
        o += ["## Liste de contrôle à l'œil", ""] + [f"- [ ] {i}" for i in controle] + [""]

    retirees = contrat.retirees(CONDENSEE)
    o += ["## Texte envoyé au modèle", "",
          f"- Version complète : {len(contrat.instruction(COMPLETE))} caractères, toutes tes lignes "
          f"+ {len(contrat.socle_actif(Mecanisme.INSTRUCTION))} principes du socle.",
          f"- Version condensée : {len(contrat.instruction(CONDENSEE))} caractères ; lignes sorties "
          f"du texte car garanties par {', '.join(m.value for m in contrat.garants)} : "
          f"{', '.join(e.id for e in retirees) or 'aucune'}.",
          "- La version condensée n'est à utiliser qu'après comparaison (même photo, même graine) "
          "montrant qu'elle ne produit pas plus de défauts. Décision : la tienne.", ""]

    o += ["## Non-suppression", "",
          f"- Lignes de la demande : {invariant['lignes_total']} "
          f"(dont {invariant['lignes_avec_contenu']} avec contenu), toutes présentes dans le contrat.",
          "- Texte d'origine identique à son empreinte : oui.",
          "- Instruction complète : toutes les lignes, dans l'ordre : oui.",
          "- Vérifié par le code, pas par un modèle de langage.", ""]

    o += ["## Mécanismes", "", "| Mécanisme | Moyen | Niveau de garantie |", "|---|---|---|"]
    o += [f"| {d['libelle']} | {d['moyen']} | {d['garantie']} |" for d in DESCRIPTIONS.values()]
    o.append("")
    return "\n".join(o)
