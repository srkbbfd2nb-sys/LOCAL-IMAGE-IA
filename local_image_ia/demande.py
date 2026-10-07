"""Demande d'origine figée : stockée mot pour mot, avec une empreinte."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from local_image_ia.gouvernance import ArretDeclare

# Une ligne sans lettre ni chiffre (« { », « }, », « --- ») ne porte pas de demande.
_SANS_CONTENU = re.compile(r"^[\W_]*$")


def empreinte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Ligne:
    id: str
    numero: int
    texte: str

    @property
    def est_vide(self) -> bool:
        return not self.texte.strip()

    @property
    def est_structure(self) -> bool:
        return not self.est_vide and _SANS_CONTENU.match(self.texte.strip()) is not None

    @property
    def porte_contenu(self) -> bool:
        return not self.est_vide and not self.est_structure


@dataclass(frozen=True)
class DemandeFigee:
    texte: str
    empreinte: str
    lignes: tuple[Ligne, ...]

    @classmethod
    def depuis_texte(cls, texte: str) -> "DemandeFigee":
        if not texte.strip():
            raise ArretDeclare("La demande est vide.")
        lignes = tuple(
            Ligne(id=f"L{i:03d}", numero=i, texte=t)
            for i, t in enumerate(texte.splitlines(), start=1)
        )
        return cls(texte=texte, empreinte=empreinte(texte), lignes=lignes)

    @classmethod
    def depuis_fichier(cls, chemin: str | Path) -> "DemandeFigee":
        donnees = Path(chemin).read_bytes()
        try:
            # utf-8-sig retire seulement l'éventuel BOM de Windows, jamais le texte.
            texte = donnees.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ArretDeclare(
                f"La demande {chemin} n'est pas en UTF-8.",
                ["Réenregistre le fichier en UTF-8 (Bloc-notes : Enregistrer sous > Encodage UTF-8)."],
            ) from exc
        return cls.depuis_texte(texte)

    def verifier_integrite(self) -> None:
        if empreinte(self.texte) != self.empreinte:
            raise ArretDeclare("La demande figée a été modifiée : son empreinte ne correspond plus.")
        if tuple(l.texte for l in self.lignes) != tuple(self.texte.splitlines()):
            raise ArretDeclare("Les lignes de la demande ne correspondent plus au texte figé.")

    def ligne(self, id_ligne: str) -> Ligne:
        for l in self.lignes:
            if l.id == id_ligne:
                return l
        raise KeyError(id_ligne)
