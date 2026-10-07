"""Socle de principes ajouté par l'optimiseur.

Le socle s'ajoute, étiqueté comme ajout. Il ne retire ni ne réécrit aucune
ligne de la demande. En cas de conflit, la ligne de la demande gagne : le
principe est suspendu et le conflit est signalé.
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

TYPES_DEMANDE = ("volume_forme", "remplacement_objet", "couleur_matiere")

_MOTIFS_TYPES: dict[str, re.Pattern[str]] = {
    "volume_forme": re.compile(
        r"\b(muscl\w*|athlet\w*|volume\w*|epaiss\w*|thick\w*|bigger|larger|broad\w*|wider"
        r"|slim\w*|mince\w*|maigr\w*|grossi\w*|forme|shape\w*|physique|body|corps|silhouette)\b"),
    "remplacement_objet": re.compile(
        r"\b(remplac\w*|replac\w*|swap\w*|a la place|instead of|substitu\w*)\b"),
    "couleur_matiere": re.compile(
        r"\b(couleur\w*|colou?r\w*|teinte\w*|matiere\w*|material\w*|cuir|leather|tissu|fabric"
        r"|peinture|paint\w*)\b"),
}

# Une ligne négative (« jamais studio ») ne contredit pas un principe qui dit la même chose.
_NEGATION = re.compile(r"\b(no|not|never|without|avoid\w*|pas|jamais|sans|ni|evit\w*|interdit\w*)\b")


@dataclass(frozen=True)
class Principe:
    id: str
    domaine: str
    mecanisme: Mecanisme
    types: tuple[str, ...]
    directive: str
    description: str
    source: str
    conflits: tuple[str, ...] = ()

    def s_applique_a(self, types_demande: set[str]) -> bool:
        return "tous" in self.types or bool(types_demande & set(self.types))


@dataclass
class Socle:
    version: str
    principes: list[Principe] = field(default_factory=list)


def charger_socle(chemin: str | Path | None = None) -> Socle:
    if chemin is None:
        brut = resources.files("local_image_ia").joinpath("socle_principes.json").read_text("utf-8")
    else:
        brut = Path(chemin).read_text("utf-8")
    donnees = json.loads(brut)
    principes = []
    ids = set()
    for p in donnees["principes"]:
        if p["id"] in ids:
            raise ArretDeclare(f"Principe en double dans le socle : {p['id']}")
        ids.add(p["id"])
        for motif in p.get("conflits", []):
            re.compile(motif)  # un motif invalide doit casser au chargement, pas plus tard
        principes.append(Principe(
            id=p["id"], domaine=p["domaine"], mecanisme=Mecanisme(p["mecanisme"]),
            types=tuple(p["types"]), directive=p["directive"], description=p["description"],
            source=p["source"], conflits=tuple(p.get("conflits", [])),
        ))
    return Socle(version=donnees.get("version", "?"), principes=principes)


def detecter_types(textes_instruction: list[str]) -> set[str]:
    norm = normaliser("\n".join(textes_instruction))
    return {t for t, motif in _MOTIFS_TYPES.items() if motif.search(norm)}


def chercher_conflit(principe: Principe, lignes: list[tuple[str, str]]) -> str | None:
    """Retourne l'id de la première ligne de la demande qui contredit le principe."""
    for id_ligne, texte in lignes:
        norm = normaliser(texte)
        if _NEGATION.search(norm):
            continue
        for motif in principe.conflits:
            if re.search(motif, norm):
                return id_ligne
    return None
