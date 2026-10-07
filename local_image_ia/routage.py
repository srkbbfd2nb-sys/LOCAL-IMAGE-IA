"""Routage de chaque ligne vers un des cinq mécanismes.

Ordre de décision, du plus sûr au moins sûr :
1. routage manuel (fichier JSON lié à l'empreinte de la demande) ;
2. étiquette en tête de ligne : ``[verrou]``, ``[instruction]``... ;
3. héritage du titre de section ; un titre de verrou (« LOCKS: ») ne s'hérite
   que dans son paragraphe, jusqu'à la ligne vide suivante ;
4. mots-clés de la ligne (heuristique, affichée comme telle dans le rapport) ;
5. destination par défaut (instruction), affichée « défaut » dans le rapport.

Sans destination par défaut, une ligne qui porte du contenu et ne trouve aucune
destination est orpheline : la compilation s'arrête et le déclare.
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
        r"|aberrations?|profondeur de champ|depth[- ]of[- ]field|bokeh|vignet\w*)\b")),
    (M.CONDITIONNEMENT, re.compile(
        r"\b(camera|perspective|focale|focal|lens|angle|point de vue|viewpoint|pose|posture"
        r"|cadrage|framing|crop\w*|horizon|raccourcis?|foreshortening|plongee|plongeante"
        r"|high[- ]angle|low[- ]angle|vanishing|depth|profondeur)\b")),
    (M.INSTRUCTION, re.compile(
        r"\b(lumiere|lighting|light|eclairage|ombres?|shadows?|reflets?|reflections?"
        r"|highlights?)\b")),
    # Vocabulaire explicite du verrou (« LOCKS », « VERROUS », « BACKGROUND PROTECTION ») :
    # voir aussi _VERBE_CONSERVATION ci-dessous, qui ne suffit pas seul.
    (M.VERROU, re.compile(r"\b(verrou\w*|locked|locks?|protect\w*|protection)\b")),
    (M.INSTRUCTION, re.compile(
        r"\b(rend\w*|ajout\w*|augment\w*|remplac\w*|chang\w*|transform\w*|modifi\w*"
        r"|epaissi\w*|epaisseur|muscl\w*|athlet\w*|harmoni\w*|proportion\w*|volume\w*|forme"
        r"|couleur\w*|matiere\w*|teinte|interdit\w*|evit\w*|make|add\w*|increas\w*"
        r"|replac\w*|swap\w*|turn\w*|convert\w*|enlarg\w*|thick\w*|muscular|athletic"
        r"|broad\w*|wider|slim\w*|colou?r\w*|material\w*|avoid\w*|never|sans|jamais"
        r"|natur\w*|realis\w*|photoreal\w*|subtil\w*|subtle|moder\w*|gain|epaules?"
        r"|shoulders?|bras|arms?|poitrine|chest|abdo\w*|taille|waist|torse|torso|dos"
        r"|corps|body|physique|silhouette|voiture|car|vehicule|vehicle|objet|object"
        r"|objective|forbidden|negative|prompt negatif|position\w*|echelle|scale|plac\w*"
        r"|analy\w*|identif\w*|distinguish|interpret\w*|beautif\w*|aesthetic|appearance"
        r"|recreat\w*|regenerat\w*|generat\w*|redesign\w*|anatom\w*|muscles?|skin|peau)\b")),
]

# Un verbe de conservation ne fait un verrou que s'il porte sur ce qui peut rester
# hors du masque. « Preserve the photographic character » ou « keep the garment »
# ne sont pas garantis par le masque : ils restent des instructions.
_VERBE_CONSERVATION = re.compile(
    r"\b(conserv\w*|garde[rz]?|gardant|preserv\w*|inchange\w*|identiques?|intact\w*|keep|kept"
    r"|unchanged|untouched|identical)\b"
    r"|\bne (pas|jamais|rien) (modifier|toucher|changer|alterer)\b"
    r"|\bne (modifie|touche|change|altere)\w* (pas|jamais|rien)\b"
    r"|\b(do not|don't|never|must not) (alter|change|modify|touch|move)\b"
    r"|\bmust (stay|remain)\b")
_HORS_MASQUE = re.compile(
    r"\b(background|backgrounds|fond|arriere[- ]plan|decor|environment|environnement|scene"
    r"|surroundings|setting|face|faces|visage|hair|cheveux|beard|barbe|hands?|mains?|fingers?"
    r"|doigts?|identity|identite|person|personne|walls?|murs?|floor|sol|ceiling|plafond|tiles?"
    r"|objects?|objets?|pillar|pilier|parking|garage|sky|ciel|trees?|arbres?|other cars"
    r"|autres voitures)\b")

# Verbes de transformation. Une ligne qui en contient un (non nié) n'est jamais un
# verrou, même si elle dit aussi « preserved » : « REPLACE THE CAR, ORIGINAL PHOTO
# PRESERVED » est l'objectif, et le verrou l'aurait sorti du texte condensé.
_TRANSFORMATION = re.compile(
    r"\b(rend\w*|ajout\w*|augment\w*|remplac\w*|chang\w*|transform\w*|modifi\w*|make|add"
    r"|adds|adding|increas\w*|replac\w*|swap\w*|turn|convert\w*|enlarg\w*|thicken\w*|give"
    r"|grow\w*|recreat\w*)\b")
_NEGATION_VERBE = re.compile(r"\b(do not|don't|dont|never|must not|not|ne|n')\s*\w+")


def demande_une_transformation(norm: str) -> bool:
    return _TRANSFORMATION.search(_NEGATION_VERBE.sub(" ", norm)) is not None


_CONSIGNE = REGLES[-1][1]  # vocabulaire général des consignes au modèle

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
    reste = texte[m.end():]
    # « [INSTRUCTION] » seul sur sa ligne est un titre de section, pas une étiquette.
    if cle not in ALIAS_ETIQUETTES or not reste.strip():
        return None, texte
    return ALIAS_ETIQUETTES[cle], m.group(1) + reste


def etiquette_inconnue(texte: str) -> str | None:
    """Étiquette en minuscules non reconnue (faute de frappe probable : « [verou] »).

    Un intitulé en MAJUSCULES (« [IMAGE SOURCE] », « [CONTRAINTES] ») est une section
    du prompt modulaire, pas une étiquette de routage.
    """
    m = _ETIQUETTE.match(texte)
    if m and normaliser(m.group(2).strip()) not in ALIAS_ETIQUETTES and not m.group(2).isupper():
        return m.group(2)
    return None


# Ligne qui ouvre sa propre section tout en portant du contenu : « 6. SILHOUETTE: … »,
# « GOAL: … ». Elle n'hérite pas des titres au-dessus d'elle. Un simple élément de
# liste numérotée (« 1. Preserve original identity ») reste rattaché à son titre.
_LIGNE_SECTION = re.compile(r"^\s*(\d+[.)]\s+)?[A-Z][A-Z0-9 &/'-]{1,40}:")

_PARENTHESE_FINALE = re.compile(r"\s*\([^)]*\)\s*:?$")


def niveau_titre(texte: str) -> str | None:
    """« json », « majeur », « mineur », ou None si la ligne n'est pas un titre.

    Majeur : titre markdown, ou ligne courte en capitales (« 2. CAMERA LOCK »,
    « PRIORITY ORDER (on conflict) »). Mineur : étiquette courte terminée par
    deux-points (« Preserve: »). JSON : ligne qui ouvre un objet ou une liste.
    """
    contenu = texte.strip()
    if not contenu:
        return None
    if contenu.endswith(("{", "[")):
        return "json"
    if re.match(r"^#{1,6}\s", contenu) or re.fullmatch(r"\[[^\]]+\]:?", contenu):
        return "majeur"
    sans_puce = _PUCE.sub("", contenu)
    sans_parenthese = _PARENTHESE_FINALE.sub("", sans_puce)
    mots = sans_parenthese.rstrip(":").split()
    lettres = [c for c in sans_parenthese if c.isalpha()]
    if lettres and sans_parenthese.upper() == sans_parenthese and 0 < len(mots) <= 6:
        return "majeur"
    if sans_puce.endswith(":") and 0 < len(sans_puce.rstrip(":").split()) <= 6:
        return "mineur"
    return None


def est_titre(texte: str) -> bool:
    return niveau_titre(texte) is not None


def par_mots_cles(texte: str) -> Mecanisme | None:
    norm = normaliser(texte)
    for mecanisme, motif in REGLES:
        if mecanisme == M.VERROU:
            verrou = motif.search(norm) or (
                _VERBE_CONSERVATION.search(norm) and _HORS_MASQUE.search(norm))
            if not verrou:
                continue
            # Une ligne de verrou peut sortir du texte condensé : elle doit donc être
            # pure. Si elle demande aussi autre chose au modèle (« No beautification »),
            # elle reste une instruction.
            if demande_une_transformation(norm) or _CONSIGNE.search(_NEGATION_VERBE.sub(" ", norm)):
                return M.INSTRUCTION
            return M.VERROU
        if motif.search(norm):
            return mecanisme
    return None


@dataclass
class _Titre:
    id: str
    mecanisme: Mecanisme | None
    niveau: str
    paragraphe_ouvert: bool = True


def router(
    lignes: tuple[Ligne, ...],
    manuel: dict[str, Mecanisme] | None = None,
    defaut: Mecanisme | None = None,
) -> dict[str, Routage]:
    """Route chaque ligne. Les lignes vides et de structure reçoivent ``mecanisme=None``.

    ``defaut`` : destination des lignes qu'aucune règle ne classe. ``None`` les
    laisse orphelines (la compilation s'arrêtera). Une ligne routée par défaut
    est marquée « défaut » dans le rapport : ce n'est jamais un silence.
    """
    manuel = manuel or {}
    resultat: dict[str, Routage] = {}
    pile: list[_Titre] = []

    for ligne in lignes:
        if ligne.est_vide:
            # Un titre vaut pour sa section ; mais un verrou ne s'hérite que dans
            # son paragraphe (la ligne vide le ferme).
            for t in pile:
                if t.niveau != "json":
                    t.paragraphe_ouvert = False
            resultat[ligne.id] = Routage(None, "")
            continue
        if ligne.est_structure:
            fermetures = ligne.texte.count("}") + ligne.texte.count("]")
            for _ in range(fermetures):
                for i in range(len(pile) - 1, -1, -1):
                    if pile[i].niveau == "json":
                        del pile[i]
                        break
            resultat[ligne.id] = Routage(None, "", texte_modele=ligne.texte)
            continue

        etiquette, texte_modele = lire_etiquette(ligne.texte)
        niveau = niveau_titre(texte_modele)
        propre = par_mots_cles(texte_modele)
        if niveau is None and _LIGNE_SECTION.match(texte_modele):
            pile = [t for t in pile if t.niveau == "json"]

        if ligne.id in manuel:
            mecanisme, source = manuel[ligne.id], "manuel"
        elif etiquette is not None:
            mecanisme, source = etiquette, "étiquette"
        elif niveau is not None:
            mecanisme, source = propre, ("heuristique" if propre else "")
        else:
            herite = None
            for t in reversed(pile):
                if t.mecanisme is None:
                    continue
                if t.mecanisme == M.VERROU and not t.paragraphe_ouvert:
                    continue
                herite = t
                break
            # Le verrou est le seul mécanisme qui autorise à sortir une ligne du texte :
            # une ligne n'y va par héritage que si elle ne parle pas d'autre chose
            # (« Keep the same camera » sous « LOCKS: » reste du conditionnement).
            if herite is not None and herite.mecanisme == M.VERROU and propre not in (None, M.VERROU):
                herite = None
            if herite is not None:
                mecanisme, source = herite.mecanisme, f"hérité de {herite.id}"
            elif propre is not None:
                mecanisme, source = propre, "heuristique"
            elif defaut is not None:
                mecanisme, source = defaut, "défaut"
            else:
                mecanisme, source = None, ""

        if niveau == "majeur":
            pile = [t for t in pile if t.niveau == "json"]
        elif niveau == "mineur":
            pile = [t for t in pile if t.niveau != "mineur"]
        if niveau is not None:
            pile.append(_Titre(ligne.id, mecanisme, niveau))

        resultat[ligne.id] = Routage(mecanisme, source, est_titre=niveau is not None,
                                     texte_modele=texte_modele)
    return resultat
