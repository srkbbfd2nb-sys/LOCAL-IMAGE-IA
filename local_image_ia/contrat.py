"""Compilateur de contrat : l'optimiseur proprement dit.

Règles (vérifiables par le code, sans confiance dans un modèle de langage) :
1. Demande figée : stockée mot pour mot, avec une empreinte.
2. Contrat : chaque ligne reçoit un identifiant et une destination parmi les
   cinq mécanismes. Une ligne sans destination provoque un arrêt déclaré.
3. Socle additif : les principes s'ajoutent, étiquetés comme ajouts. En cas
   de conflit, la ligne de la demande gagne et le conflit est signalé.
4. Rapport de sortie : pour chaque ligne, garantie, vérifiée ou non vérifiable.

Condensation : une ligne ne sort du texte envoyé au modèle que si un
mécanisme la garantit déjà (par défaut : le verrou par masque). La version
complète reste la référence tant qu'une comparaison n'a pas montré que la
version condensée ne dégrade pas la qualité.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from local_image_ia.demande import DemandeFigee
from local_image_ia.gouvernance import ArretDeclare
from local_image_ia.mecanismes import GARANTS_PAR_DEFAUT, Mecanisme
from local_image_ia.routage import etiquette_inconnue, lire_etiquette, router
from local_image_ia.socle import (
    TYPES_DEMANDE, Principe, Socle, charger_socle, chercher_conflit, detecter_types,
)

COMPLETE = "complete"
CONDENSEE = "condensee"

ENTETE_SOCLE = (
    "Additional principles (added by the optimizer; lower priority than every line above; "
    "if one of them conflicts with a line above, the line above wins):"
)


@dataclass
class EntreeDemande:
    id: str
    numero: int
    texte: str
    texte_modele: str
    role: str  # "ligne", "titre", "structure", "vide"
    mecanisme: Mecanisme | None
    routage: str
    enfants: list[str] = field(default_factory=list)

    @property
    def porte_contenu(self) -> bool:
        return self.role in ("ligne", "titre")


@dataclass
class EntreeSocle:
    principe: Principe
    statut: str  # "actif", "suspendu", "hors type"
    conflit_avec: str | None = None


@dataclass
class Contrat:
    demande: DemandeFigee
    entrees: list[EntreeDemande]
    socle_version: str
    socle: list[EntreeSocle]
    types: list[str]
    manques: list[str]
    avertissements: list[str]
    garants: frozenset[Mecanisme] = GARANTS_PAR_DEFAUT

    # ----- texte envoyé au modèle -------------------------------------------------

    def _retirable(self, e: EntreeDemande) -> bool:
        if e.role == "ligne":
            return e.mecanisme in self.garants
        if e.role == "titre":
            if e.mecanisme is not None:
                return e.mecanisme in self.garants
            enfants = [self.entree(i) for i in e.enfants]
            return bool(enfants) and all(self._retirable(x) for x in enfants)
        return False

    def lignes_modele(self, mode: str) -> list[EntreeDemande]:
        if mode not in (COMPLETE, CONDENSEE):
            raise ValueError(mode)
        return [
            e for e in self.entrees
            if e.role != "vide" and not (mode == CONDENSEE and self._retirable(e))
        ]

    def socle_actif(self, mecanisme: Mecanisme | None = None) -> list[EntreeSocle]:
        return [
            s for s in self.socle
            if s.statut == "actif" and (mecanisme is None or s.principe.mecanisme == mecanisme)
        ]

    def instruction(self, mode: str = COMPLETE) -> str:
        gardees = {e.id for e in self.lignes_modele(mode)}
        lignes: list[str] = []
        for e in self.entrees:
            if e.id in gardees:
                lignes.append(e.texte_modele)
            elif e.role == "vide" and lignes and lignes[-1] != "":
                lignes.append("")  # garde la mise en page, sans lignes vides en série
        while lignes and lignes[-1] == "":
            lignes.pop()
        ajouts = self.socle_actif(Mecanisme.INSTRUCTION)
        if ajouts:
            lignes += ["", ENTETE_SOCLE]
            lignes += [f"- {s.principe.directive}" for s in ajouts]
        return "\n".join(lignes) + "\n"

    def retirees(self, mode: str) -> list[EntreeDemande]:
        gardees = {e.id for e in self.lignes_modele(mode)}
        return [e for e in self.entrees if e.porte_contenu and e.id not in gardees]

    # ----- accès --------------------------------------------------------------------

    def entree(self, id_ligne: str) -> EntreeDemande:
        for e in self.entrees:
            if e.id == id_ligne:
                return e
        raise KeyError(id_ligne)

    def entrees_par_mecanisme(self, mecanisme: Mecanisme) -> list[EntreeDemande]:
        return [e for e in self.entrees if e.porte_contenu and e.mecanisme == mecanisme]

    # ----- sérialisation ------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "format": "contrat-local-image-ia/1",
            "demande": {"empreinte_sha256": self.demande.empreinte, "texte": self.demande.texte},
            "garants": sorted(m.value for m in self.garants),
            "types": self.types,
            "manques": self.manques,
            "avertissements": self.avertissements,
            "entrees": [
                {
                    "id": e.id, "numero": e.numero, "texte": e.texte, "texte_modele": e.texte_modele,
                    "role": e.role, "mecanisme": e.mecanisme.value if e.mecanisme else None,
                    "routage": e.routage, "enfants": e.enfants,
                }
                for e in self.entrees
            ],
            "socle": {
                "version": self.socle_version,
                "principes": [
                    {
                        "id": s.principe.id, "domaine": s.principe.domaine,
                        "mecanisme": s.principe.mecanisme.value, "types": list(s.principe.types),
                        "directive": s.principe.directive, "description": s.principe.description,
                        "source": s.principe.source, "conflits": list(s.principe.conflits),
                        "statut": s.statut, "conflit_avec": s.conflit_avec,
                    }
                    for s in self.socle
                ],
            },
            "instruction_complete": self.instruction(COMPLETE),
            "instruction_condensee": self.instruction(CONDENSEE),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Contrat":
        if d.get("format") != "contrat-local-image-ia/1":
            raise ArretDeclare("Format de contrat inconnu.", [str(d.get("format"))])
        demande = DemandeFigee.depuis_texte(d["demande"]["texte"])
        if demande.empreinte != d["demande"]["empreinte_sha256"]:
            raise ArretDeclare("Le texte de la demande ne correspond plus à son empreinte.")
        entrees = [
            EntreeDemande(
                id=e["id"], numero=e["numero"], texte=e["texte"], texte_modele=e["texte_modele"],
                role=e["role"], mecanisme=Mecanisme(e["mecanisme"]) if e["mecanisme"] else None,
                routage=e["routage"], enfants=list(e["enfants"]),
            )
            for e in d["entrees"]
        ]
        socle = [
            EntreeSocle(
                principe=Principe(
                    id=p["id"], domaine=p["domaine"], mecanisme=Mecanisme(p["mecanisme"]),
                    types=tuple(p["types"]), directive=p["directive"],
                    description=p["description"], source=p["source"],
                    conflits=tuple(p["conflits"]),
                ),
                statut=p["statut"], conflit_avec=p["conflit_avec"],
            )
            for p in d["socle"]["principes"]
        ]
        contrat = cls(
            demande=demande, entrees=entrees, socle_version=d["socle"]["version"], socle=socle,
            types=list(d["types"]), manques=list(d["manques"]),
            avertissements=list(d["avertissements"]),
            garants=frozenset(Mecanisme(m) for m in d["garants"]),
        )
        verifier_non_suppression(contrat)
        for mode, cle in ((COMPLETE, "instruction_complete"), (CONDENSEE, "instruction_condensee")):
            if contrat.instruction(mode) != d[cle]:
                raise ArretDeclare(
                    f"L'instruction {mode} enregistrée ne correspond plus au contrat.",
                    ["Le fichier contrat.json a été modifié à la main : recompile la demande."],
                )
        return contrat

    def enregistrer(self, chemin: str | Path) -> None:
        Path(chemin).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def charger(cls, chemin: str | Path) -> "Contrat":
        return cls.from_dict(json.loads(Path(chemin).read_text("utf-8")))


# ----- routage manuel -------------------------------------------------------------


def charger_routage_manuel(chemin: str | Path, demande: DemandeFigee) -> dict[str, Mecanisme]:
    """Fichier JSON : {"empreinte_sha256": "...", "lignes": {"L012": "instruction"}}."""
    d = json.loads(Path(chemin).read_text("utf-8"))
    if d.get("empreinte_sha256") != demande.empreinte:
        raise ArretDeclare(
            "Le routage manuel a été écrit pour une autre version de la demande.",
            [f"empreinte attendue : {demande.empreinte}",
             "Les identifiants de ligne ont pu changer : refais le routage."],
        )
    ids = {l.id for l in demande.lignes}
    sortie = {}
    for id_ligne, valeur in d.get("lignes", {}).items():
        if id_ligne not in ids:
            raise ArretDeclare(f"Routage manuel : la ligne {id_ligne} n'existe pas.")
        try:
            sortie[id_ligne] = Mecanisme(valeur)
        except ValueError as exc:
            raise ArretDeclare(
                f"Routage manuel : destination inconnue « {valeur} » pour {id_ligne}.",
                [f"Destinations possibles : {', '.join(m.value for m in Mecanisme)}"],
            ) from exc
    return sortie


# ----- compilation ----------------------------------------------------------------


def compiler(
    demande: DemandeFigee,
    socle: Socle | None = None,
    routage_manuel: dict[str, Mecanisme] | None = None,
    types_forces: list[str] | None = None,
    garants: frozenset[Mecanisme] = GARANTS_PAR_DEFAUT,
) -> Contrat:
    demande.verifier_integrite()
    socle = socle if socle is not None else charger_socle()

    inconnues = [
        f"{l.id} : étiquette [{etiquette_inconnue(l.texte)}]"
        for l in demande.lignes if etiquette_inconnue(l.texte)
    ]
    if inconnues:
        raise ArretDeclare(
            "Étiquettes de routage inconnues.",
            inconnues + [f"Étiquettes possibles : {', '.join(m.value for m in Mecanisme)}"],
        )

    routes = router(demande.lignes, routage_manuel)
    entrees: list[EntreeDemande] = []
    titre_courant: EntreeDemande | None = None
    for ligne in demande.lignes:
        r = routes[ligne.id]
        if ligne.est_vide:
            role = "vide"
        elif ligne.est_structure:
            role = "structure"
        elif r.est_titre:
            role = "titre"
        else:
            role = "ligne"
        e = EntreeDemande(
            id=ligne.id, numero=ligne.numero, texte=ligne.texte,
            texte_modele=r.texte_modele if role != "vide" else "",
            role=role, mecanisme=r.mecanisme, routage=r.source,
        )
        if role == "vide":
            titre_courant = None
        elif role == "titre":
            titre_courant = e
        elif role == "ligne" and titre_courant is not None:
            titre_courant.enfants.append(e.id)
        entrees.append(e)

    orphelines = [
        e for e in entrees
        if (e.role == "ligne" and e.mecanisme is None)
        or (e.role == "titre" and e.mecanisme is None and not e.enfants)
    ]
    if orphelines:
        raise ArretDeclare(
            "Lignes sans destination : la compilation s'arrête plutôt que de les perdre.",
            [f"{e.id} : {e.texte.strip()}" for e in orphelines]
            + ["Pour chacune, ajoute une étiquette en tête de ligne, par exemple "
               "« [instruction] … » ou « [verrou] … », ou utilise --routage."],
        )

    contrat_partiel = Contrat(demande, entrees, socle.version, [], [], [], [], garants)
    instruction_lignes = contrat_partiel.entrees_par_mecanisme(Mecanisme.INSTRUCTION)
    if not instruction_lignes:
        raise ArretDeclare(
            "Aucune ligne n'est destinée au modèle : il n'y a pas de transformation à faire.",
            ["Étiquette la ligne qui décrit la modification avec [instruction]."],
        )

    manques: list[str] = []
    avertissements: list[str] = []
    if types_forces:
        inconnus = [t for t in types_forces if t not in TYPES_DEMANDE]
        if inconnus:
            raise ArretDeclare(f"Type de demande inconnu : {', '.join(inconnus)}",
                               [f"Types possibles : {', '.join(TYPES_DEMANDE)}"])
        types = set(types_forces)
    else:
        types = detecter_types([e.texte_modele for e in instruction_lignes])
        if not types:
            manques.append(
                "Type de demande non reconnu (volume ou forme, remplacement d'objet, couleur "
                "ou matière) : seuls les principes communs du socle sont ajoutés. "
                "Précise-le avec --type."
            )
        elif len(types) > 1:
            avertissements.append(
                "Plusieurs types de demande détectés : " + ", ".join(sorted(types))
                + ". Le périmètre de départ prévoit un seul changement par photo."
            )

    if not contrat_partiel.entrees_par_mecanisme(Mecanisme.VERROU):
        manques.append(
            "Aucune ligne de verrou : seul le masque définit ce qui est protégé."
        )
    if not contrat_partiel.entrees_par_mecanisme(Mecanisme.VERIFICATION):
        avertissements.append(
            "Aucune ligne de contrôle final dans la demande : la liste de contrôle vient du socle."
        )
    heuristiques = [e.id for e in entrees if e.porte_contenu and e.routage == "heuristique"]
    if heuristiques:
        avertissements.append(
            f"{len(heuristiques)} ligne(s) routée(s) par mots-clés : relis leur destination "
            "dans le rapport du contrat."
        )
    if contrat_partiel.entrees_par_mecanisme(Mecanisme.CONDITIONNEMENT):
        avertissements.append(
            "Mécanisme de conditionnement absent en phase 0 : les lignes caméra, perspective "
            "et pose restent dans le texte envoyé au modèle et ne sont pas garanties."
        )

    lignes_utilisateur = [(e.id, e.texte_modele) for e in entrees if e.porte_contenu]
    entrees_socle = []
    for p in socle.principes:
        if not p.s_applique_a(types):
            entrees_socle.append(EntreeSocle(p, "hors type"))
            continue
        conflit = chercher_conflit(p, lignes_utilisateur)
        if conflit:
            entrees_socle.append(EntreeSocle(p, "suspendu", conflit))
            avertissements.append(
                f"Conflit : le principe {p.id} ({p.domaine}) contredit la ligne {conflit}. "
                "Ta ligne gagne, le principe est suspendu."
            )
        else:
            entrees_socle.append(EntreeSocle(p, "actif"))

    contrat = Contrat(
        demande=demande, entrees=entrees, socle_version=socle.version, socle=entrees_socle,
        types=sorted(types), manques=manques, avertissements=avertissements, garants=garants,
    )
    verifier_non_suppression(contrat)
    return contrat


# ----- invariant de non-suppression -------------------------------------------------


def _sous_suite(attendu: list[str], obtenu: list[str]) -> bool:
    it = iter(obtenu)
    return all(any(x == y for y in it) for x in attendu)


def verifier_non_suppression(contrat: Contrat) -> dict:
    """Vérifie par le code qu'aucune ligne de la demande n'a été perdue ou réécrite."""
    d = contrat.demande
    d.verifier_integrite()

    if [e.id for e in contrat.entrees] != [l.id for l in d.lignes]:
        raise ArretDeclare("Le contrat ne couvre pas exactement les lignes de la demande.")
    for e, l in zip(contrat.entrees, d.lignes):
        if e.texte != l.texte:
            raise ArretDeclare(f"La ligne {e.id} a été réécrite dans le contrat.")
        if e.role != "vide" and lire_etiquette(l.texte)[1] != e.texte_modele:
            raise ArretDeclare(f"Le texte envoyé au modèle pour {e.id} diffère de la ligne d'origine.")
        if e.role == "ligne" and e.mecanisme is None:
            raise ArretDeclare(f"La ligne {e.id} n'a pas de destination.")
        if e.role == "titre" and e.mecanisme is None and not e.enfants:
            raise ArretDeclare(f"Le titre {e.id} n'a ni destination ni ligne rattachée.")

    complete = [e for e in contrat.entrees if e.role != "vide"]
    texte_complet = contrat.instruction(COMPLETE).splitlines()
    if not _sous_suite([e.texte_modele for e in complete], texte_complet):
        raise ArretDeclare("L'instruction complète ne contient pas toutes les lignes, dans l'ordre.")

    gardees = contrat.lignes_modele(CONDENSEE)
    texte_condense = contrat.instruction(CONDENSEE).splitlines()
    if not _sous_suite([e.texte_modele for e in gardees], texte_condense):
        raise ArretDeclare("L'instruction condensée a perdu une ligne qu'elle devait garder.")
    for e in contrat.retirees(CONDENSEE):
        if not contrat._retirable(e):
            raise ArretDeclare(f"La ligne {e.id} est sortie du texte sans mécanisme garant.")

    return {
        "empreinte": d.empreinte,
        "lignes_total": len(d.lignes),
        "lignes_avec_contenu": sum(1 for e in contrat.entrees if e.porte_contenu),
        "lignes_retirees_du_texte_condense": [e.id for e in contrat.retirees(CONDENSEE)],
        "conforme": True,
    }
