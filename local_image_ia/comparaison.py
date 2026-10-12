"""Comparaison de variantes du texte envoyé au modèle, sur la même photo et les mêmes graines.

Sert à décider, à l'œil et sur preuve, ce que le socle apporte (ou retire) : ta demande
seule, ta demande + le socle limité en mots, ta demande + tout le socle. Seul le texte
change d'une variante à l'autre ; la photo, les graines et le traitement sont les mêmes.
Le classement mesuré ne juge ni l'anatomie ni la lumière : la planche est faite pour ton œil.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from local_image_ia.contrat import SOCLE_MOTS_MAX, estimer_jetons

COTE_VIGNETTE = 768
BANDEAU = 34


@dataclass
class Variante:
    nom: str
    reglages: dict
    description: str
    instruction: str = ""
    identique_a: str | None = None
    erreur: str | None = None


def variantes_standard(socle_mots_max: int) -> list[Variante]:
    n = socle_mots_max or SOCLE_MOTS_MAX
    return [
        Variante("demande_seule", {"socle_actif": False}, "ta demande seule, aucun principe ajouté"),
        Variante(f"socle_{n}", {"socle_actif": True, "socle_mots_max": n},
                 f"ta demande + les principes prioritaires du socle ({n} mots au plus)"),
        Variante("socle_complet", {"socle_actif": True, "socle_mots_max": 0},
                 "ta demande + tous les principes applicables"),
    ]


def _police(taille: int):
    try:
        return ImageFont.load_default(size=taille)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _taille_case(largeur: int, hauteur: int) -> tuple[int, int]:
    """Taille de l'image dans une case : proportions de la photo, côté le plus long ≤ 768."""
    k = min(1.0, COTE_VIGNETTE / max(largeur, hauteur))
    return max(1, round(largeur * k)), max(1, round(hauteur * k))


def _vignette(image: Image.Image, titre: str, taille: tuple[int, int]) -> Image.Image:
    image = image.convert("RGB")
    image.thumbnail(taille, Image.Resampling.LANCZOS)
    case = Image.new("RGB", (taille[0], taille[1] + BANDEAU), (24, 24, 24))
    case.paste(image, ((taille[0] - image.width) // 2, BANDEAU))
    ImageDraw.Draw(case).text((8, 7), titre, fill=(240, 240, 240), font=_police(18))
    return case


def _rapport(dossier: Path) -> dict | None:
    chemin = dossier / "rapport.json"
    return json.loads(chemin.read_text("utf-8")) if chemin.exists() else None


def ecrire_planche(dossier: Path, variantes: list[Variante], original: np.ndarray | None,
                   graine: int) -> Path | None:
    """Une ligne par graine, une colonne par variante (plus l'original en tête)."""
    faites = [v for v in variantes if v.identique_a is None and v.erreur is None]
    lignes = max((len(list((dossier / v.nom).glob("candidat_[0-9][0-9].png"))) for v in faites),
                 default=0)
    if not lignes:
        return None
    if original is not None:
        l, h = original.shape[1], original.shape[0]
    else:
        premier = next(p for v in faites for p in sorted((dossier / v.nom).glob("candidat_01.png")))
        with Image.open(premier) as im:
            l, h = im.size
    taille = _taille_case(l, h)
    colonnes = (1 if original is not None else 0) + len(faites)
    planche = Image.new("RGB", (colonnes * taille[0], lignes * (taille[1] + BANDEAU)),
                        (24, 24, 24))
    for k in range(lignes):
        y = k * (taille[1] + BANDEAU)
        x = 0
        if original is not None:
            planche.paste(_vignette(Image.fromarray(original), "original", taille), (x, y))
            x += taille[0]
        for v in faites:
            chemin = dossier / v.nom / f"candidat_{k + 1:02d}.png"
            if chemin.exists():
                with Image.open(chemin) as im:
                    planche.paste(_vignette(im, f"{v.nom} - C{k + 1} (graine {graine + k})",
                                            taille), (x, y))
            x += taille[0]
    sortie = dossier / "planche.jpg"
    planche.save(sortie, format="JPEG", quality=92)
    return sortie


def _mesure(c: dict | None, cle: str) -> str:
    if not c:
        return "—"
    if cle == "score":
        v = c.get("score")
    elif cle == "raccord":
        v = (c.get("raccord") or {}).get("ratio")
    elif cle == "nettete":
        v = (c.get("signature") or {}).get("nettete_ratio")
    else:
        g = (c.get("signature") or {}).get("grain_ratios") or {}
        v = ", ".join(f"{k}: {x}" for k, x in g.items()) or None
    if c.get("rejete") and cle == "score":
        return f"rejeté ({c['rejete']})"
    return "—" if v is None else str(v)


def ecrire_rapport(dossier: Path, variantes: list[Variante], empreinte: str, graine: int,
                   texte: str, planche: Path | None) -> Path:
    o = [f"# Comparaison — {datetime.now():%Y-%m-%d %H:%M}", "",
         f"Empreinte de la demande (SHA-256) : `{empreinte}`  ",
         f"Graines : {graine}, {graine + 1}, … (les mêmes pour chaque variante)  ",
         f"Texte envoyé : version {texte}", "",
         "Seul le texte envoyé au modèle change d'une variante à l'autre. **Compare à l'œil "
         "une même ligne de la planche** (même graine) : c'est là que la différence vient du "
         "texte et pas du hasard." + (f" Planche : `{planche.name}`." if planche else ""), "",
         "## Variantes", "",
         "| Variante | Contenu | Mots envoyés | ≈ Jetons | Résultat retenu | Score | Raccord | Grain | Netteté | Durée |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    rapports = {}
    for v in variantes:
        mots = len(v.instruction.split())
        if v.identique_a:
            o.append(f"| {v.nom} | {v.description} | {mots} | {estimer_jetons(v.instruction)} | "
                     f"texte identique à {v.identique_a} : non relancée | | | | | |")
            continue
        if v.erreur:
            o.append(f"| {v.nom} | {v.description} | {mots} | {estimer_jetons(v.instruction)} | "
                     f"ÉCHEC : {v.erreur} | | | | | |")
            continue
        r = rapports[v.nom] = _rapport(dossier / v.nom) or {}
        retenu = next((c for c in r.get("candidats", []) if c.get("fichier") == r.get("retenu")), None)
        duree = (r.get("durees") or {}).get("total")
        o.append(
            f"| {v.nom} | {v.description} | {mots} | {estimer_jetons(v.instruction)} | "
            f"{retenu['nom'] if retenu else '—'} | {_mesure(retenu, 'score')} | "
            f"{_mesure(retenu, 'raccord')} | {_mesure(retenu, 'grain')} | "
            f"{_mesure(retenu, 'nettete')} | {duree if duree is not None else '—'} s |")
    o.append("")

    if rapports:
        noms = list(rapports)
        n = max(len(r.get("candidats", [])) for r in rapports.values())
        o += ["## Score de chaque candidat, à graine égale", "",
              "Score d'écart mesuré (plus bas = moins de défauts **mesurables**).", "",
              "| Graine | " + " | ".join(noms) + " |", "|---|" + "---|" * len(noms)]
        for k in range(n):
            cellules = []
            for nom in noms:
                c = next((c for c in rapports[nom].get("candidats", [])
                          if c.get("nom") == f"C{k + 1}"), None)
                cellules.append(_mesure(c, "score"))
            o.append(f"| {graine + k} | " + " | ".join(cellules) + " |")
        o.append("")

    o += ["## Ton verdict", "",
          "Les mesures ne voient ni l'anatomie, ni la lumière posée sur le changement, ni le "
          "naturel de la photo. Pour chaque ligne de la planche, note la colonne qui a le moins "
          "de défauts visibles, puis envoie-moi ce fichier avec ton choix :", "",
          "- [ ] demande seule meilleure", "- [ ] socle limité meilleur",
          "- [ ] socle complet meilleur", "- [ ] pas de différence visible", "",
          "## Textes envoyés", ""]
    for v in variantes:
        o += [f"### {v.nom}", "", f"{len(v.instruction.split())} mots.", "", "```",
              v.instruction.rstrip("\n"), "```", ""]
    chemin = dossier / "rapport_comparaison.md"
    chemin.write_text("\n".join(o), "utf-8")
    return chemin
