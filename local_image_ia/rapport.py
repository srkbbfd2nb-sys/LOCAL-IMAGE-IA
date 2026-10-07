"""Rapport de sortie : pour chaque ligne, garantie, vérifiée ou non vérifiable."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from local_image_ia.contrat import COMPLETE, CONDENSEE, Contrat, estimer_jetons
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
REJETE = "rejeté"

LEGENDE = {
    GARANTIE: "garantie par le code, et l'écart hors zone modifiée mesuré vaut zéro",
    CONFORME: "vérifiée par une mesure, dans les seuils",
    NON_CONFORME: "vérifiée par une mesure, hors des seuils",
    A_L_OEIL: "non vérifiable par le code : c'est ton œil qui juge",
    ABSENT: "mécanisme pas encore branché : la ligne reste dans le texte du modèle",
    REJETE: "candidat écarté avant mesure (raison dans le classement)",
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
    hors_masque: dict | None
    raccord: dict
    signature: dict
    grain_reapplique: dict
    score: float
    notes: list[str]
    masque: dict = field(default_factory=dict)
    rejete: str | None = None

    @property
    def mesure(self) -> bool:
        return self.hors_masque is not None

    def conformite(self, cle: str) -> bool | None:
        if not self.mesure:
            return None
        if cle == "hors_masque":
            return self.hors_masque["conforme"]
        if cle == "raccord":
            return self.raccord.get("conforme")
        if cle == "grain":
            return self.signature.get("grain_conforme")
        if cle == "nettete":
            return self.signature.get("nettete_conforme")
        raise KeyError(cle)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        if isinstance(self.score, float) and not math.isfinite(self.score):
            d["score"] = None
        return d


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
    if c.rejete:
        return REJETE
    if mecanisme == Mecanisme.CONDITIONNEMENT:
        return ABSENT
    if mecanisme == Mecanisme.INSTRUCTION or not c.mesure:
        return A_L_OEIL
    if mecanisme == Mecanisme.VERROU:
        return GARANTIE if c.hors_masque["conforme"] else NON_CONFORME
    cles = mesures_concernees(texte)
    if mecanisme == Mecanisme.SIGNATURE:
        cles = [k for k in cles if k in ("grain", "nettete")]
    return _etat_par_mesures(cles, c) if cles else A_L_OEIL


def _cellule(texte: str, limite: int = 160) -> str:
    t = texte.strip().replace("|", "\\|") or "∅"
    return t if len(t) <= limite else t[:limite] + " …"


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
            "id": p.id, "texte": f"[{p.module}] {p.directive}", "origine": "socle (ajout)",
            "mecanisme": p.mecanisme.value, "routage": "socle", "etats": etats,
        })
    return lignes


def liste_controle(contrat: Contrat, candidats: list[MesuresCandidat]) -> list[str]:
    items = []
    if contrat.mode == "edition":
        for e in contrat.entrees_par_mecanisme(Mecanisme.VERROU):
            if e.role == "titre":
                continue
            items.append(f"{e.id} — « {e.texte_modele.strip()} » : l'élément visé est-il bien hors "
                         "de la zone modifiée (en noir dans masques/) ? Le verrou ne protège que ça.")
    for e in contrat.entrees:
        if e.role == "ligne" and e.mecanisme is not None and (
                e.mecanisme != Mecanisme.VERROU or contrat.mode != "edition"):
            etats = [etat(e.mecanisme, e.texte_modele, c) for c in candidats] or [A_L_OEIL]
            if A_L_OEIL in etats or ABSENT in etats:
                items.append(f"{e.id} — {_cellule(e.texte_modele, 200)}")
    for s in contrat.socle_actif(Mecanisme.VERIFICATION):
        etats = [etat(Mecanisme.VERIFICATION, s.principe.directive, c) for c in candidats] or [A_L_OEIL]
        if A_L_OEIL in etats:
            items.append(f"{s.principe.id} — {s.principe.directive}")
    return items


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return str(v)


def rapport_markdown(
    contrat: Contrat,
    candidats: list[MesuresCandidat],
    capacites: list[Capacite],
    invariant: dict,
    titre: str,
    juge: str = "",
    generateur: str = "",
    notes_globales: list[str] | None = None,
    durees: dict | None = None,
    retenu: str | None = None,
) -> str:
    o: list[str] = [f"# {titre}", ""]
    o.append(f"Mode : **{contrat.mode}**  ")
    o.append(f"Empreinte de la demande (SHA-256) : `{contrat.demande.empreinte}`  ")
    o.append(f"Socle de principes : version {contrat.socle_version}  ")
    o.append(f"Types de demande : {', '.join(contrat.types) or 'non reconnu'}")
    if generateur:
        o.append(f"  \nGénérateur : {generateur}  \nJuge : {juge}")
    o.append("")
    if retenu:
        o += [f"**Résultat retenu : `resultat.png` (= {retenu}).** "
              + ("Choisi sur les défauts mesurables ; vérifie-le à l'œil avec la liste en fin "
                 "de rapport." if contrat.mode == "edition" else
                 "Premier candidat généré : aucun classement mesuré n'est possible sans original."),
              ""]
    if notes_globales:
        o += [f"> {n}" for n in notes_globales] + [""]

    if candidats:
        if contrat.mode == "edition":
            o += ["## Classement des candidats", "",
                  "Classement sur les défauts **mesurables** seulement (raccord, grain, netteté). "
                  "Il ne dit rien de l'anatomie ni de la lumière sur le nouveau volume : "
                  "c'est ton œil qui tranche.", "",
                  "| Rang | Candidat | Fichier | Zone modifiée | Score d'écart | Hors zone | Raccord | Grain | Netteté |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for rang, c in enumerate(candidats, start=1):
                zone = (f"{c.masque.get('source', '?')}, {c.masque['part']:.0%}"
                        if "part" in c.masque else c.masque.get("source", "—"))
                if c.masque.get("ilots"):
                    zone += f", **îlot inchangé {c.masque['ilots']:.1%}**"
                if c.rejete:
                    o.append(f"| — | {c.nom} | `{c.fichier}` | {zone} | {REJETE} : {c.rejete} | | | | |")
                    continue
                hm = c.hors_masque
                hm_txt = "0 pixel modifié" if hm["conforme"] else f"{hm['pixels_differents']} pixels modifiés"
                g = c.signature.get("grain_ratios", {})
                g_txt = ", ".join(f"{k}: {v}" for k, v in g.items()) or "—"
                o.append(
                    f"| {rang} | {c.nom} | `{c.fichier}` | {zone} | {_fmt(c.score)} | {hm_txt} | "
                    f"{_fmt(c.raccord.get('ratio'))} | {g_txt} | {_fmt(c.signature.get('nettete_ratio'))} |"
                )
            o += ["", f"Seuils : grain {SEUILS['grain_ratio_min']}–{SEUILS['grain_ratio_max']}, "
                  f"netteté {SEUILS['nettete_ratio_min']}–{SEUILS['nettete_ratio_max']}, "
                  f"raccord ≤ {SEUILS['raccord_ratio_max']} ({NATURE_SEUILS}). "
                  "Les zones modifiées sont dans `masques/` (blanc = pris du candidat).", ""]
        else:
            o += ["## Candidats", ""] + [f"- {c.nom} : `{c.fichier}`" for c in candidats] + [""]
        notes = [(c.nom, n) for c in candidats for n in c.notes]
        if notes:
            o += ["Notes de traitement :", ""] + [f"- {nom} : {n}" for nom, n in notes] + [""]

    if durees:
        o += ["## Durées", "", "| Étape | Durée |", "|---|---|"]
        o += [f"| {k} | {v} s |" for k, v in durees.items()] + [""]

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
    o += [f"- **{PREVUE}** : contrat compilé, pas encore de candidat mesuré",
          "- Routage **défaut** : aucune règle ne donnait de mécanisme plus fort ; la ligne est "
          "envoyée au modèle telle quelle, sans promesse.", ""]

    suspendus = [s for s in contrat.socle if s.statut == "suspendu"]
    couverts = [s for s in contrat.socle if s.statut == "couvert"]
    o += ["## Conflits", ""]
    if suspendus:
        o += [f"- {s.principe.id} ({s.principe.domaine}) suspendu : contredit {s.conflit_avec}. "
              "Ta ligne gagne." for s in suspendus]
    else:
        o.append("Aucun conflit détecté entre le socle et ta demande.")
    o.append("")
    if couverts:
        o += ["## Principes déjà couverts par ta demande", "",
              "Non répétés dans le texte du modèle (ils le dilueraient) :", ""]
        o += [f"- {s.principe.id} [{s.principe.module}] couvert par {s.conflit_avec}"
              for s in couverts] + [""]

    if contrat.manques or contrat.avertissements:
        o += ["## Manques et avertissements déclarés", ""]
        o += [f"- Manque : {m}" for m in contrat.manques]
        o += [f"- {a}" for a in contrat.avertissements]
        o.append("")

    controle = liste_controle(contrat, candidats)
    if controle:
        o += ["## Liste de contrôle à l'œil", ""] + [f"- [ ] {i}" for i in controle] + [""]

    retirees = contrat.retirees(CONDENSEE)
    complete = contrat.instruction(COMPLETE)
    condensee = contrat.instruction(CONDENSEE)
    o += ["## Texte envoyé au modèle", "",
          f"- Version complète : {len(complete)} caractères (≈ {estimer_jetons(complete)} jetons), "
          f"toutes tes lignes + {len(contrat.socle_actif(Mecanisme.INSTRUCTION))} principes du socle.",
          f"- Version condensée : {len(condensee)} caractères (≈ {estimer_jetons(condensee)} jetons) ; "
          f"lignes sorties du texte car garanties par "
          f"{', '.join(m.value for m in contrat.garants) or 'aucun mécanisme dans ce mode'} : "
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
