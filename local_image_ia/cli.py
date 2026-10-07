"""Interface en ligne de commande.

    python -m local_image_ia compiler demande.txt -o sortie
    python -m local_image_ia finaliser --contrat sortie/contrat.json \\
        --original photo.jpg --masque masque.png --candidats c1.png c2.png -o sortie
    python -m local_image_ia socle
"""

from __future__ import annotations

import argparse
import sys

from local_image_ia.contrat import Contrat
from local_image_ia.gouvernance import ArretDeclare
from local_image_ia.mecanismes import Mecanisme
from local_image_ia.pipeline import GENERATEUR_PAR_DEFAUT, compiler_demande, finaliser
from local_image_ia.socle import TYPES_DEMANDE, charger_socle


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="local_image_ia", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = p.add_subparsers(dest="commande", required=True)

    c = sous.add_parser("compiler", help="Figer la demande et la compiler en contrat")
    c.add_argument("demande", help="Fichier texte UTF-8 contenant la demande")
    c.add_argument("-o", "--sortie", default="sortie")
    c.add_argument("--routage", help="Fichier JSON de routage manuel")
    c.add_argument("--type", action="append", choices=TYPES_DEMANDE, dest="types",
                   help="Type de demande (répétable) si la détection automatique échoue")
    c.add_argument("--socle", help="Fichier de principes à utiliser à la place du socle intégré")

    f = sous.add_parser("finaliser", help="Verrouiller, réappliquer le grain, mesurer, rapporter")
    f.add_argument("--contrat", required=True)
    f.add_argument("--original", required=True)
    f.add_argument("--masque", required=True, help="Blanc = zone à modifier, noir = verrouillé")
    f.add_argument("--candidats", nargs="+", required=True)
    f.add_argument("-o", "--sortie", default="sortie")
    f.add_argument("--fondu", type=int, default=8, help="Largeur du fondu, en pixels, dans le masque")
    f.add_argument("--graine", type=int, default=0)
    f.add_argument("--generateur", default=GENERATEUR_PAR_DEFAUT)

    sous.add_parser("socle", help="Lister les principes du socle")
    return p


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # console Windows
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    try:
        if args.commande == "compiler":
            contrat = compiler_demande(args.demande, args.sortie, args.routage, args.types, args.socle)
            n = sum(1 for e in contrat.entrees if e.porte_contenu)
            print(f"Demande figée : {contrat.demande.empreinte[:16]}…  ({n} lignes avec contenu)")
            for m in Mecanisme:
                k = len(contrat.entrees_par_mecanisme(m))
                if k:
                    print(f"  {m.value:<16} {k} ligne(s)")
            print(f"Socle : {len(contrat.socle_actif())} principe(s) ajouté(s), "
                  f"{sum(1 for s in contrat.socle if s.statut == 'suspendu')} suspendu(s) pour conflit")
            for m in contrat.manques:
                print(f"MANQUE : {m}")
            for a in contrat.avertissements:
                print(f"AVERTISSEMENT : {a}")
            print(f"\nÀ coller dans ComfyUI : {args.sortie}/instruction_complete.txt")
            print(f"Routage à relire       : {args.sortie}/rapport_contrat.md")
        elif args.commande == "finaliser":
            contrat = Contrat.charger(args.contrat)
            resultats = finaliser(contrat, args.original, args.masque, args.candidats, args.sortie,
                                  fondu=args.fondu, graine=args.graine, generateur=args.generateur)
            print("Classement sur défauts mesurables (l'anatomie reste à juger à l'œil) :")
            for rang, c in enumerate(resultats, start=1):
                print(f"  {rang}. {c.fichier}  score {c.score}  raccord {c.raccord.get('ratio')}")
            print(f"\nRapport : {args.sortie}/rapport.md")
        elif args.commande == "socle":
            socle = charger_socle()
            print(f"Socle version {socle.version}")
            for p in socle.principes:
                print(f"  {p.id:<9} [{p.mecanisme.value:<15}] {', '.join(p.types):<20} {p.description}")
    except ArretDeclare as exc:
        print(f"ARRÊT DÉCLARÉ : {exc}", file=sys.stderr)
        return 2
    return 0
