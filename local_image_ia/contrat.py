"""Compilateur de contrat : l'optimiseur proprement dit.

Règles (vérifiables par le code, sans confiance dans un modèle de langage) :
1. Demande figée : stockée mot pour mot, avec une empreinte.
2. Contrat : chaque ligne reçoit un identifiant et une destination parmi les
   cinq mécanismes. Une ligne qu'aucune règle ne classe va en instruction,
   marquée « défaut » (option : arrêt déclaré à la place).
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
    MODES, TYPES_DEMANDE, Principe, Socle, charger_socle, chercher_conflit, chercher_couverture,
    detecter_types,
)

COMPLETE = "complete"
CONDENSEE = "condensee"

ENTETE_SOCLE = (
    "Additional principles (added by the optimizer; lower priority than every line above; "
    "if one of them conflicts with a line above, the line above wins):"
)
ORPHELINES = ("instruction", "arret")
FORMAT = "contrat-local-image-ia/2"
# Estimation grossière (E) : environ 4 caractères par jeton pour un texte anglais.
CARACTERES_PAR_JETON = 4
# L'encodeur de texte de ComfyUI pour FLUX.2 klein complète à 512 jetons et ne coupe
# pas (vérifié dans son code) ; au-delà, le risque est la dilution, pas la coupure (E).
JETONS_REPERE = 512


def estimer_jetons(texte: str) -> int:
    return max(1, round(len(texte) / CARACTERES_PAR_JETON))


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
    statut: str  # "actif", "suspendu", "couvert", "hors type", "hors mode"
    conflit_avec: str | None = None  # ligne en conflit (suspendu) ou qui couvre déjà (couvert)


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
    mode: str = "edition"
    modules: list[str] = field(default_factory=list)

    # ----- texte envoyé au modèle -------------------------------------------------

    def _retirable(self, e: EntreeDemande) -> bool:
        if e.role == "ligne":
            return e.mecanisme in self.garants
        if e.role == "titre":
            # Un titre ne sort que si toutes ses lignes sortent : sinon « Preserve: »
            # disparaîtrait et laisserait ses lignes sans leur verbe.
            enfants = [self.entree(i) for i in e.enfants]
            if any(not self._retirable(x) for x in enfants):
                return False
            if e.mecanisme is not None:
                return e.mecanisme in self.garants
            return bool(enfants)
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
            ordre = {m: i for i, m in enumerate(self.modules)}
            par_module: dict[str, list[EntreeSocle]] = {}
            for a in ajouts:
                par_module.setdefault(a.principe.module, []).append(a)
            for module in sorted(par_module, key=lambda m: ordre.get(m, len(ordre))):
                lignes.append(f"[{module}]")
                lignes += [f"- {a.principe.directive}" for a in par_module[module]]
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
            "format": FORMAT,
            "mode": self.mode,
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
                "modules": self.modules,
                "principes": [
                    {**s.principe.to_dict(), "statut": s.statut, "conflit_avec": s.conflit_avec}
                    for s in self.socle
                ],
            },
            "instruction_complete": self.instruction(COMPLETE),
            "instruction_condensee": self.instruction(CONDENSEE),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Contrat":
        if d.get("format") != FORMAT:
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
            EntreeSocle(principe=Principe.from_dict(p), statut=p["statut"],
                        conflit_avec=p["conflit_avec"])
            for p in d["socle"]["principes"]
        ]
        contrat = cls(
            demande=demande, entrees=entrees, socle_version=d["socle"]["version"], socle=socle,
            types=list(d["types"]), manques=list(d["manques"]),
            avertissements=list(d["avertissements"]),
            garants=frozenset(Mecanisme(m) for m in d["garants"]),
            mode=d["mode"], modules=list(d["socle"]["modules"]),
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
    mode: str = "edition",
    orphelines: str = "instruction",
    socle_complet: bool = False,
) -> Contrat:
    """Compile la demande en contrat.

    ``mode`` : « edition » (une photo est modifiée, le verrou s'applique),
    « reference » (une ou plusieurs images servent de modèle à une image nouvelle),
    « creation » (aucune image). Hors édition, rien n'est garanti par le masque :
    aucune ligne ne sort du texte condensé.

    ``socle_complet`` : ajouter aussi les principes que la demande dit déjà
    (par défaut, un principe couvert par une ligne de la demande n'est pas répété).
    """
    demande.verifier_integrite()
    socle = socle if socle is not None else charger_socle()
    if mode not in MODES:
        raise ArretDeclare(f"Mode inconnu : {mode}", [f"Modes possibles : {', '.join(MODES)}"])
    if orphelines not in ORPHELINES:
        raise ArretDeclare(f"Politique inconnue pour les lignes sans destination : {orphelines}")
    garants = GARANTS_PAR_DEFAUT if mode == "edition" else frozenset()
    defaut = Mecanisme.INSTRUCTION if orphelines == "instruction" else None

    inconnues = [
        f"{l.id} : étiquette [{etiquette_inconnue(l.texte)}]"
        for l in demande.lignes if etiquette_inconnue(l.texte)
    ]
    if inconnues:
        raise ArretDeclare(
            "Étiquettes de routage inconnues.",
            inconnues + [f"Étiquettes possibles : {', '.join(m.value for m in Mecanisme)}"],
        )

    routes = router(demande.lignes, routage_manuel, defaut)
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
        if role == "titre":
            titre_courant = e
        elif role == "ligne" and titre_courant is not None:
            titre_courant.enfants.append(e.id)
        entrees.append(e)

    for e in entrees:
        # Un titre sans destination ni ligne rattachée (« IMAGE-EDITING TASK » suivi
        # d'un autre titre) suit la même politique que les lignes sans destination.
        if e.role == "titre" and e.mecanisme is None and not e.enfants and defaut is not None:
            e.mecanisme, e.routage = defaut, "défaut"

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

    contrat_partiel = Contrat(demande, entrees, socle.version, [], [], [], [], garants, mode,
                              list(socle.modules))
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
        # Les premières lignes portent l'objectif, quel que soit le mécanisme qui les a
        # reçues (« preserving the same camera angle » envoie l'objectif en conditionnement).
        types = detecter_types([
            e.texte_modele for e in entrees
            if e.porte_contenu and e.mecanisme != Mecanisme.VERIFICATION
        ])
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

    verrous = contrat_partiel.entrees_par_mecanisme(Mecanisme.VERROU)
    if mode == "edition" and not verrous:
        manques.append(
            "Aucune ligne de verrou : seul le masque définit ce qui est protégé."
        )
    if mode != "edition" and verrous:
        avertissements.append(
            f"Mode {mode} : pas de photo à recopier, les {len(verrous)} ligne(s) de verrou ne "
            "sont garanties par aucun mécanisme. Elles restent dans le texte du modèle."
        )
    par_defaut = [e.id for e in entrees if e.porte_contenu and e.routage == "défaut"]
    if par_defaut:
        avertissements.append(
            f"{len(par_defaut)} ligne(s) sans mécanisme plus fort, envoyée(s) au modèle comme "
            "instruction (routage « défaut ») : " + ", ".join(par_defaut[:12])
            + (" …" if len(par_defaut) > 12 else "") + "."
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

    # Pour les conflits, une ligne de liste se lit avec son titre : « - DSLR studio
    # photography » sous « Do not convert the image into: » est une interdiction.
    parent = {enfant: t for t in entrees if t.role == "titre" for enfant in t.enfants}
    lignes_utilisateur = [
        (e.id, (parent[e.id].texte_modele + " " if e.id in parent else "") + e.texte_modele)
        for e in entrees if e.porte_contenu
    ]
    entrees_socle = []
    for p in socle.principes:
        if not p.s_applique_au_mode(mode):
            entrees_socle.append(EntreeSocle(p, "hors mode"))
            continue
        if not p.s_applique_a(types):
            entrees_socle.append(EntreeSocle(p, "hors type"))
            continue
        conflit = chercher_conflit(p, lignes_utilisateur)
        couvert = (
            None if socle_complet or p.mecanisme != Mecanisme.INSTRUCTION
            else chercher_couverture(p, lignes_utilisateur)
        )
        if couvert and not conflit:
            entrees_socle.append(EntreeSocle(p, "couvert", couvert))
            continue
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
        mode=mode, modules=list(socle.modules),
    )
    jetons = estimer_jetons(contrat.instruction(COMPLETE))
    if jetons > JETONS_REPERE:
        avertissements.append(
            f"Instruction complète ≈ {jetons} jetons (estimation). ComfyUI ne la coupe pas, "
            f"mais au-delà d'environ {JETONS_REPERE} jetons le modèle risque de diluer la "
            f"consigne (E). Version condensée ≈ {estimer_jetons(contrat.instruction(CONDENSEE))} "
            "jetons."
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
