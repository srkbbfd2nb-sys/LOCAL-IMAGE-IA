"""Gouvernance de l'optimiseur (Protocole LAB, anciennement Protocole TJ).

Le protocole s'applique à l'optimiseur seulement. Ce module en porte les
règles traduisibles en code :

- échec bruyant (INV.5) : une ligne orpheline, un repli ou une limite se
  déclarent par ``ArretDeclare``, jamais en silence ;
- capacités en trois états (vérifié / déclaré / absent), sans valeur par
  défaut optimiste ;
- nature des affirmations (F / E / O / P) ;
- règle de circularité : le juge n'est jamais le générateur ;
- décision humaine (INV.4) : le code prépare, l'humain tranche.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ArretDeclare(Exception):
    """Arrêt déclaré : le système refuse de continuer et dit pourquoi."""

    def __init__(self, motif: str, details: list[str] | tuple[str, ...] = ()):
        self.motif = motif
        self.details = list(details)
        message = motif
        if self.details:
            message += "\n" + "\n".join(f"  - {d}" for d in self.details)
        super().__init__(message)


class Nature(str, Enum):
    """Nature épistémique d'une affirmation du rapport."""

    FAIT = "F"
    ESTIMATION = "E"
    OPINION = "O"
    PREDICTION = "P"


class EtatCapacite(str, Enum):
    """Trois états seulement : l'inconnu se classe « absent »."""

    VERIFIE = "vérifié"
    DECLARE = "déclaré"
    ABSENT = "absent"


@dataclass
class Capacite:
    nom: str
    etat: EtatCapacite
    voie: str
    note: str = ""

    def to_dict(self) -> dict:
        return {"nom": self.nom, "etat": self.etat.value, "voie": self.voie, "note": self.note}


@dataclass
class Journal:
    """Avertissements et replis déclarés au fil d'un traitement."""

    avertissements: list[str] = field(default_factory=list)

    def declarer(self, message: str) -> None:
        self.avertissements.append(message)


def verifier_circularite(generateur: str, juge: str) -> None:
    """Le juge ne doit pas être le modèle qui a produit l'image."""
    if generateur.strip().casefold() == juge.strip().casefold():
        raise ArretDeclare(
            "Règle de circularité violée : le juge est le générateur.",
            [f"générateur : {generateur}", f"juge : {juge}"],
        )
