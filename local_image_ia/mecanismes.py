"""Les cinq mécanismes vers lesquels chaque ligne de la demande est compilée.

Un modèle d'image n'exécute pas un prompt ligne par ligne : chaque ligne
doit donc aller vers un mécanisme qui la garantit ou la mesure.
"""

from __future__ import annotations

from enum import Enum

from local_image_ia.gouvernance import Capacite, EtatCapacite


class Mecanisme(str, Enum):
    VERROU = "verrou"
    CONDITIONNEMENT = "conditionnement"
    INSTRUCTION = "instruction"
    SIGNATURE = "signature"
    VERIFICATION = "verification"


DESCRIPTIONS: dict[Mecanisme, dict[str, str]] = {
    Mecanisme.VERROU: {
        "libelle": "Verrou par masque",
        "moyen": "Les pixels hors masque sont recopiés depuis l'original",
        "garantie": "Garanti par le code (hors masque)",
    },
    Mecanisme.CONDITIONNEMENT: {
        "libelle": "Conditionnement",
        "moyen": "Cartes de profondeur et de contours tirées de la source",
        "garantie": "Fortement contraint",
    },
    Mecanisme.INSTRUCTION: {
        "libelle": "Instruction au modèle",
        "moyen": "Texte envoyé au modèle d'édition",
        "garantie": "Probabiliste",
    },
    Mecanisme.SIGNATURE: {
        "libelle": "Signature photographique",
        "moyen": "Grain et netteté mesurés sur la source, grain réappliqué",
        "garantie": "Mesurable",
    },
    Mecanisme.VERIFICATION: {
        "libelle": "Vérification après coup",
        "moyen": "Mesures par le code, puis œil humain (juge distinct du générateur)",
        "garantie": "Vérifié après coup",
    },
}

# Étiquettes acceptées en tête de ligne : « [verrou] Garder le fond ».
ALIAS_ETIQUETTES: dict[str, Mecanisme] = {
    "verrou": Mecanisme.VERROU,
    "lock": Mecanisme.VERROU,
    "conditionnement": Mecanisme.CONDITIONNEMENT,
    "condition": Mecanisme.CONDITIONNEMENT,
    "instruction": Mecanisme.INSTRUCTION,
    "signature": Mecanisme.SIGNATURE,
    "verification": Mecanisme.VERIFICATION,
    "controle": Mecanisme.VERIFICATION,
    "check": Mecanisme.VERIFICATION,
}


def capacites_phase0() -> list[Capacite]:
    """État réel des mécanismes en phase 0, déclaré sans optimisme."""
    return [
        Capacite("Verrou par masque", EtatCapacite.VERIFIE, "code (numpy)",
                 "Écart hors masque mesuré à chaque sortie."),
        Capacite("Conditionnement profondeur / contours", EtatCapacite.ABSENT, "aucune",
                 "Pas encore branché dans ComfyUI : les lignes caméra/pose restent dans le texte."),
        Capacite("Générateur (modèle d'édition)", EtatCapacite.DECLARE, "ComfyUI, hors de ce code",
                 "Les candidats sont produits à part ; ce code ne voit que les images."),
        Capacite("Signature : grain", EtatCapacite.VERIFIE, "code (numpy)",
                 "Mesuré par bande de luminance, réappliqué si la zone éditée en manque."),
        Capacite("Signature : netteté", EtatCapacite.VERIFIE, "code (numpy)",
                 "Mesurée et comparée, pas corrigée."),
        Capacite("Juge vision local", EtatCapacite.ABSENT, "repli : œil humain + rapport de mesures",
                 "Un juge sérieux ne tient pas dans 6 Go à côté du générateur."),
    ]


# Mécanismes dont la garantie autorise, par défaut, à retirer la ligne du
# texte condensé. Toute extension doit être décidée après une comparaison
# même photo, même graine, version complète contre version condensée.
GARANTS_PAR_DEFAUT: frozenset[Mecanisme] = frozenset({Mecanisme.VERROU})
