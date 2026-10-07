"""Socle de principes ajouté par l'optimiseur.

Le socle s'ajoute, étiqueté comme ajout. Il ne retire ni ne réécrit aucune
ligne de la demande. En cas de conflit, la ligne de la demande gagne : le
principe est suspendu et le conflit est signalé.

Chaque principe appartient à un module du prompt modulaire ([IMAGE SOURCE] …
[FINAL REALISM CHECK]) : les ajouts envoyés au modèle sont regroupés par module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from local_image_ia.gouvernance import ArretDeclare
from local_image_ia.mecanismes import Mecanisme
from local_image_ia.routage import normaliser

TYPES_DEMANDE = ("corps", "volume_forme", "remplacement_objet", "couleur_matiere")
MODES = ("edition", "reference", "creation")

_MOTIFS_TYPES: dict[str, re.Pattern[str]] = {
    "corps": re.compile(
        r"\b(muscl\w*|athlet\w*|physique|body|bodies|corps|anatom\w*|abdo\w*|biceps|pector\w*"
        r"|deltoid\w*|epaules?|shoulders?)\b"),
    "volume_forme": re.compile(
        r"\b(volume\w*|epaiss\w*|thick\w*|bigger|larger|broad\w*|wider|slim\w*|mince\w*"
        r"|maigr\w*|grossi\w*|forme|shape\w*|silhouette)\b"),
    "remplacement_objet": re.compile(
        r"\b(remplac\w*|replac\w*|swap\w*|a la place|instead of|substitu\w*)\b"),
    "couleur_matiere": re.compile(
        r"\b(couleur\w*|colou?r\w*|teinte\w*|matiere\w*|material\w*|cuir|leather|tissu|fabric"
        r"|peinture|paint\w*)\b"),
}

# Une ligne négative (« jamais studio ») ne contredit pas un principe qui dit la même chose.
_NEGATION = re.compile(
    r"\b(no|not|never|without|avoid\w*|forbidden|don't|dont|pas|jamais|sans|ni|evit\w*"
    r"|interdit\w*)\b")

@dataclass(frozen=True)
class Principe:
    id: str
    module: str
    domaine: str
    mecanisme: Mecanisme
    types: tuple[str, ...]
    modes: tuple[str, ...]
    directive: str
    description: str
    source: str
    conflits: tuple[str, ...] = ()
    conflits_explicites: tuple[str, ...] = ()
    couverture: tuple[str, ...] = ()

    def s_applique_a(self, types_demande: set[str]) -> bool:
        return "tous" in self.types or bool(types_demande & set(self.types))

    def s_applique_au_mode(self, mode: str) -> bool:
        return "tous" in self.modes or mode in self.modes

    def to_dict(self) -> dict:
        return {
            "id": self.id, "module": self.module, "domaine": self.domaine,
            "mecanisme": self.mecanisme.value, "types": list(self.types),
            "modes": list(self.modes), "directive": self.directive,
            "description": self.description, "source": self.source,
            "conflits": list(self.conflits), "conflits_explicites": list(self.conflits_explicites),
            "couverture": list(self.couverture),
        }

    @classmethod
    def from_dict(cls, p: dict) -> "Principe":
        return cls(
            id=p["id"], module=p.get("module", "CONSTRAINTS"), domaine=p["domaine"],
            mecanisme=Mecanisme(p["mecanisme"]), types=tuple(p["types"]),
            modes=tuple(p.get("modes", ["tous"])), directive=p["directive"],
            description=p["description"], source=p["source"],
            conflits=tuple(p.get("conflits", [])),
            conflits_explicites=tuple(p.get("conflits_explicites", [])),
            couverture=tuple(p.get("couverture", [])),
        )


@dataclass
class Socle:
    version: str
    principes: list[Principe] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)


def charger_socle(chemin: str | Path | None = None) -> Socle:
    if chemin is None:
        brut = resources.files("local_image_ia").joinpath("socle_principes.json").read_text("utf-8")
    else:
        brut = Path(chemin).read_text("utf-8")
    donnees = json.loads(brut)
    principes = []
    ids = set()
    modules = list(donnees.get("modules", []))
    for brut_p in donnees["principes"]:
        p = Principe.from_dict(brut_p)
        if p.id in ids:
            raise ArretDeclare(f"Principe en double dans le socle : {p.id}")
        ids.add(p.id)
        if modules and p.module not in modules:
            raise ArretDeclare(f"Principe {p.id} : module inconnu « {p.module} ».")
        for motif in p.conflits + p.conflits_explicites + p.couverture:
            re.compile(motif)  # un motif invalide doit casser au chargement, pas plus tard
        inconnus = set(p.types) - set(TYPES_DEMANDE) - {"tous"}
        if inconnus:
            raise ArretDeclare(f"Principe {p.id} : type inconnu {sorted(inconnus)}.")
        principes.append(p)
    return Socle(version=donnees.get("version", "?"), principes=principes, modules=modules)


def detecter_types(textes: list[str]) -> set[str]:
    """Types de la première ligne qui en nomme un : c'est l'objectif.

    Le reste d'un long prompt cite trop de sujets (« painted lines » dans l'analyse
    d'un garage ne fait pas d'un remplacement de voiture une demande de couleur).
    """
    for texte in textes:
        norm = normaliser(texte)
        types = {t for t, motif in _MOTIFS_TYPES.items() if motif.search(norm)}
        if types:
            if "corps" in types:
                types.discard("volume_forme")  # les principes « corps » couvrent déjà le volume
            return types
    return set()


def chercher_conflit(principe: Principe, lignes: list[tuple[str, str]]) -> str | None:
    """Retourne l'id de la première ligne de la demande qui contredit le principe.

    Les motifs « explicites » décrivent eux-mêmes une interdiction (« do not inject
    noise ») : ils s'appliquent même aux lignes négatives.
    """
    for id_ligne, texte in lignes:
        norm = normaliser(texte)
        for motif in principe.conflits_explicites:
            if re.search(motif, norm):
                return id_ligne
        if _NEGATION.search(norm):
            continue
        for motif in principe.conflits:
            if re.search(motif, norm):
                return id_ligne
    return None


def chercher_couverture(principe: Principe, lignes: list[tuple[str, str]]) -> str | None:
    """Retourne l'id de la première ligne de la demande qui dit déjà ce que dit le principe.

    Un principe couvert n'est pas ajouté une seconde fois au texte du modèle (il le
    diluerait) ; il reste visible dans le contrat et le rapport.
    """
    for id_ligne, texte in lignes:
        norm = normaliser(texte)
        for motif in principe.couverture:
            if re.search(motif, norm, flags=re.MULTILINE):
                return id_ligne
    return None
