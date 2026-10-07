"""Routage de chaque ligne vers un des cinq mécanismes.

Ordre de décision, du plus sûr au moins sûr :
1. routage manuel (fichier JSON lié à l'empreinte de la demande) ;
2. étiquette en tête de ligne : ``[verrou]``, ``[instruction]``... ;
3. héritage du titre de section (« VERROUS : » s'applique aux lignes de son
   paragraphe, jusqu'à la ligne vide suivante) ;
4. mots-clés de la ligne (heuristique, affichée comme telle dans le rapport).

Une ligne qui porte du contenu et ne trouve aucune destination est orpheline :
la compilation s'arrête et le déclare.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from local_image_ia.demande import Ligne
from local_image_ia.mecanismes import ALIAS_ETIQUETTES, Mecanisme

M = Mecanisme


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, apostrophes unifiées."""
    decompose = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return sans_accents.casefold().replace("’", "'")


# L'ordre compte : le sujet de la ligne l'emporte sur le verbe.
# « Keep the same grain » va en signature, « keep the same camera » en
# conditionnement, « keep the same lighting » en instruction (le masque ne
# garantit pas la lumière posée sur le nouveau volume), « keep the face » en verrou.
REGLES: list[tuple[Mecanisme, re.Pattern[str]]] = [
    # L'ordre de priorité en cas de conflit est une consigne au modèle, quel que soit son contenu.
    (M.INSTRUCTION, re.compile(r"\b(priorit\w*|ordre de priorite)\b")),
    (M.VERIFICATION, re.compile(
        r"\b(controle final|controle de coherence|final check|final control|quality check"
        r"|verifi\w*|verify|check|checklist|controle\w*|test du spectateur|viewer test)\b")),
    (M.SIGNATURE, re.compile(
        r"\b(grain|bruit|noise|nettete|sharp\w*|compression|jpe?g|artefacts?|artifacts?"
        r"|flou|blur\w*|micro[- ]?contrastes?|micro[- ]?contrast|resolution|snapchat"
        r"|aberrations?|profondeur de champ|depth of field|bokeh|vignet\w*)\b")),
    (M.CONDITIONNEMENT, re.compile(
        r"\b(camera|perspective|focale|focal|lens|angle|point de vue|viewpoint|pose|posture"
        r"|cadrage|framing|crop\w*|horizon|raccourcis?|foreshortening|plongee|plongeante"
        r"|high[- ]angle|low[- ]angle|vanishing)\b")),
    (M.INSTRUCTION, re.compile(
        r"\b(lumiere|lighting|light|eclairage|ombres?|shadows?|reflets?|reflections?"
        r"|highlights?)\b")),
    (M.VERROU, re.compile(
        r"\b(conserv\w*|garde[rz]?|gardant|preserv\w*|inchange\w*|identiques?|intact\w*"
        r"|verrou\w*|keep|kept|unchanged|untouched|identical|locked|locks?)\b"
        r"|\bne (pas|jamais|rien) (modifier|toucher|changer|alterer)\b"
        r"|\bne (modifie|touche|change|altere)\w* (pas|jamais|rien)\b"
        r"|\b(do not|don't|never|must not) (alter|change|modify|touch|move)\b"
        r"|\bmust (stay|remain)\b")),
    (M.INSTRUCTION, re.compile(
        r"\b(rend\w*|ajout\w*|augment\w*|remplac\w*|chang\w*|transform\w*|modifi\w*"
        r"|epaissi\w*|epaisseur|muscl\w*|athlet\w*|harmoni\w*|proportion\w*|volume\w*|forme"
        r"|couleur\w*|matiere\w*|teinte|interdit\w*|evit\w*|make|add\w*|increas\w*"
        r"|replac\w*|swap\w*|turn\w*|convert\w*|enlarg\w*|thick\w*|muscular|athletic"
        r"|broad\w*|wider|slim\w*|colou?r\w*|material\w*|avoid\w*|never|sans|jamais"
        r"|natur\w*|realis\w*|photoreal\w*|subtil\w*|subtle|moder\w*|gain|epaules?"
        r"|shoulders?|bras|arms?|poitrine|chest|abdo\w*|taille|waist|torse|torso|dos"
        r"|corps|body|physique|silhouette|voiture|car|vehicule|vehicle|objet|object"
        r"|objective|forbidden|negative|prompt negatif|position\w*|echelle|scale|plac\w*)\b")),
]

_ETIQUETTE = re.compile(r"^(\s*(?:[-*•]\s*)?)\[([^\]]+)\]\s*")
_PUCE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


@dataclass(frozen=True)
class Routage:
    mecanisme: Mecanisme | None
    source: str  # "manuel", "étiquette", "hérité de Lxxx", "heuristique", ""
    est_titre: bool = False
    texte_modele: str = ""  # la ligne telle qu'envoyée au modèle (étiquette retirée)


def lire_etiquette(texte: str) -> tuple[Mecanisme | None, str]:
    """Retourne (mécanisme, texte sans l'étiquette). Étiquette inconnue : arrêt plus loin."""
    m = _ETIQUETTE.match(texte)
    if not m:
        return None, texte
    cle = normaliser(m.group(2).strip())
    if cle not in ALIAS_ETIQUETTES:
        return None, texte
    return ALIAS_ETIQUETTES[cle], m.group(1) + texte[m.end():]


def etiquette_inconnue(texte: str) -> str | None:
    m = _ETIQUETTE.match(texte)
    if m and normaliser(m.group(2).strip()) not in ALIAS_ETIQUETTES:
        return m.group(2)
    return None


def est_titre(texte: str) -> bool:
    contenu = texte.strip()
    if not contenu:
        return False
    if re.match(r"^#{1,6}\s", contenu):
        return True
    if contenu.endswith(("{", "[")):
        return True
    sans_puce = _PUCE.sub("", contenu)
    mots = sans_puce.rstrip(":").split()
    if sans_puce.endswith(":") and 0 < len(mots) <= 6:
        return True
    lettres = [c for c in sans_puce if c.isalpha()]
    return bool(lettres) and sans_puce.upper() == sans_puce and len(mots) <= 6


def par_mots_cles(texte: str) -> Mecanisme | None:
    norm = normaliser(texte)
    for mecanisme, motif in REGLES:
        if motif.search(norm):
            return mecanisme
    return None


def router(lignes: tuple[Ligne, ...], manuel: dict[str, Mecanisme] | None = None) -> dict[str, Routage]:
    """Route chaque ligne. Les lignes vides et de structure reçoivent ``mecanisme=None``."""
    manuel = manuel or {}
    resultat: dict[str, Routage] = {}
    # Pile de titres actifs : (id, mécanisme ou None, est_json)
    pile: list[tuple[str, Mecanisme | None, bool]] = []

    for ligne in lignes:
        if ligne.est_vide:
            # Un titre de texte vaut pour son paragraphe : la ligne vide le ferme.
            pile = [p for p in pile if p[2]]
            resultat[ligne.id] = Routage(None, "")
            continue
        if ligne.est_structure:
            fermetures = ligne.texte.count("}") + ligne.texte.count("]")
            for _ in range(fermetures):
                if pile and pile[-1][2]:
                    pile.pop()
            resultat[ligne.id] = Routage(None, "", texte_modele=ligne.texte)
            continue

        etiquette, texte_modele = lire_etiquette(ligne.texte)
        titre = est_titre(texte_modele)
        propre = par_mots_cles(texte_modele)

        if ligne.id in manuel:
            mecanisme, source = manuel[ligne.id], "manuel"
        elif etiquette is not None:
            mecanisme, source = etiquette, "étiquette"
        elif titre:
            mecanisme, source = propre, ("heuristique" if propre else "")
        else:
            herite = next(((i, m) for i, m, _ in reversed(pile) if m is not None), None)
            # Le verrou est le seul mécanisme qui autorise à sortir une ligne du texte :
            # une ligne n'y va par héritage que si elle ne parle pas d'autre chose
            # (« Keep the same camera » sous « LOCKS: » reste du conditionnement).
            if herite is not None and herite[1] == M.VERROU and propre not in (None, M.VERROU):
                herite = None
            if herite is not None:
                mecanisme, source = herite[1], f"hérité de {herite[0]}"
            elif propre is not None:
                mecanisme, source = propre, "heuristique"
            else:
                mecanisme, source = None, ""

        if titre:
            est_json = texte_modele.strip().endswith(("{", "["))
            if not est_json:
                # Un titre de texte remplace les titres de texte précédents.
                pile = [p for p in pile if p[2]]
            pile.append((ligne.id, mecanisme, est_json))

        resultat[ligne.id] = Routage(mecanisme, source, est_titre=titre, texte_modele=texte_modele)
    return resultat
