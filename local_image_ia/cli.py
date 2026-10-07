"""Interface en ligne de commande.

Usage automatique (le plus simple) :
    python -m local_image_ia surveiller --boite boite
        puis dépose ma_photo.jpg + ma_photo.txt dans boite/entree/

Une seule tâche, sans dossier surveillé :
    python -m local_image_ia traiter --demande demande.txt --image photo.jpg -o sortie

Les trois mesures de l'étape 1 (ComfyUI doit tourner) :
    python -m local_image_ia diagnostic -o diagnostic

Étapes séparées (sans ComfyUI) :
    python -m local_image_ia compiler demande.txt -o sortie
    python -m local_image_ia finaliser --contrat sortie/contrat.json \\
        --original photo.jpg --candidats c1.png c2.png -o sortie   [--masque masque.png]
    python -m local_image_ia socle
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from pathlib import Path

from local_image_ia.automate import Automate, ConfigAutomate, Tache
from local_image_ia.contrat import ORPHELINES, Contrat
from local_image_ia.gouvernance import ArretDeclare
from local_image_ia.mecanismes import Mecanisme
from local_image_ia.pipeline import (
    GENERATEUR_PAR_DEFAUT, compiler_demande, finaliser, finaliser_sans_original,
)
from local_image_ia.socle import MODES, TYPES_DEMANDE, charger_socle
from local_image_ia.workflows import FORMATS, PRESETS


def _options_automate(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="Fichier JSON de réglages (voir config.exemple.json)")
    p.add_argument("--url", help="Adresse de ComfyUI (défaut http://127.0.0.1:8188)")
    p.add_argument("--candidats", type=int, help="Nombre de candidats par demande (défaut 3)")
    p.add_argument("--budget", type=float, dest="budget_s", help="Budget de temps en secondes (défaut 300)")
    p.add_argument("--modele", dest="preset", choices=list(PRESETS))
    p.add_argument("--texte", choices=["complete", "condensee"])
    p.add_argument("--format", dest="format_creation", choices=list(FORMATS))
    p.add_argument("--graine", type=int)


def _config(args) -> ConfigAutomate:
    config = ConfigAutomate.charger(args.config)
    for f in fields(ConfigAutomate):
        valeur = getattr(args, f.name, None)
        if valeur is not None:
            setattr(config, f.name, valeur)
    config.verifier()
    return config


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="local_image_ia", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = p.add_subparsers(dest="commande", required=True)

    s = sous.add_parser("surveiller", help="Surveiller boite/entree et traiter chaque dépôt")
    s.add_argument("--boite", default="boite")
    s.add_argument("--une-fois", action="store_true", help="Traiter ce qui est déposé puis s'arrêter")
    s.add_argument("--attendre-comfyui", type=float, default=600.0,
                   help="Secondes d'attente du démarrage de ComfyUI")
    _options_automate(s)

    t = sous.add_parser("traiter", help="Traiter une seule demande")
    t.add_argument("--demande", required=True)
    t.add_argument("--image", help="Image à modifier (mode édition)")
    t.add_argument("--ref", action="append", default=[], help="Image servant de modèle (répétable)")
    t.add_argument("--masque", help="Zone à modifier (blanc) ; sinon masque automatique")
    t.add_argument("--protege", help="Zones à ne jamais toucher (blanc)")
    t.add_argument("-o", "--sortie", default="sortie")
    _options_automate(t)

    d = sous.add_parser("diagnostic", help="Sonder ComfyUI et mesurer les temps de génération")
    d.add_argument("-o", "--sortie", default="diagnostic")
    d.add_argument("--attendre-comfyui", type=float, default=600.0,
                   help="Secondes d'attente du démarrage de ComfyUI")
    _options_automate(d)

    c = sous.add_parser("compiler", help="Figer la demande et la compiler en contrat")
    c.add_argument("demande", help="Fichier texte UTF-8 contenant la demande")
    c.add_argument("-o", "--sortie", default="sortie")
    c.add_argument("--mode", choices=MODES, default="edition")
    c.add_argument("--routage", help="Fichier JSON de routage manuel")
    c.add_argument("--type", action="append", choices=TYPES_DEMANDE, dest="types",
                   help="Type de demande (répétable) si la détection automatique échoue")
    c.add_argument("--orphelines", choices=ORPHELINES, default="instruction",
                   help="Lignes sans destination : en instruction (défaut) ou arrêt")
    c.add_argument("--socle-complet", action="store_true",
                   help="Ajouter aussi les principes que ta demande dit déjà")
    c.add_argument("--socle", help="Fichier de principes à utiliser à la place du socle intégré")

    f = sous.add_parser("finaliser", help="Verrouiller, corriger, mesurer et rapporter des candidats")
    f.add_argument("--contrat", required=True)
    f.add_argument("--original", help="Image d'origine (obligatoire en mode édition)")
    f.add_argument("--masque", help="Zone à modifier (blanc) ; sinon masque automatique")
    f.add_argument("--protege", help="Zones à ne jamais toucher (blanc)")
    f.add_argument("--candidats", nargs="+", required=True)
    f.add_argument("-o", "--sortie", default="sortie")
    f.add_argument("--fondu", type=int, default=8, help="Largeur du fondu, en pixels, dans la zone modifiée")
    f.add_argument("--graine", type=int, default=0)
    f.add_argument("--generateur", default=GENERATEUR_PAR_DEFAUT)

    sous.add_parser("socle", help="Lister les principes du socle")
    return p


def _afficher_contrat(contrat: Contrat, sortie: str) -> None:
    n = sum(1 for e in contrat.entrees if e.porte_contenu)
    print(f"Demande figée : {contrat.demande.empreinte[:16]}…  ({n} lignes avec contenu, "
          f"mode {contrat.mode})")
    for m in Mecanisme:
        k = len(contrat.entrees_par_mecanisme(m))
        if k:
            print(f"  {m.value:<16} {k} ligne(s)")
    compte = {st: sum(1 for s in contrat.socle if s.statut == st)
              for st in ("actif", "couvert", "suspendu")}
    print(f"Socle : {compte['actif']} principe(s) ajouté(s), {compte['couvert']} déjà couvert(s) "
          f"par ta demande, {compte['suspendu']} suspendu(s) pour conflit")
    for m in contrat.manques:
        print(f"MANQUE : {m}")
    for a in contrat.avertissements:
        print(f"AVERTISSEMENT : {a}")
    print(f"\nTexte pour le modèle : {sortie}/instruction_complete.txt")
    print(f"Routage à relire     : {sortie}/rapport_contrat.md")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # console Windows
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    try:
        if args.commande == "surveiller":
            automate = Automate(_config(args))
            print(f"Attente de ComfyUI sur {automate.config.url} …")
            automate.client.attendre_demarrage(args.attendre_comfyui)
            for c in automate.sonder():
                print(f"  {c.nom} : {c.etat.value}")
            automate.surveiller(args.boite, une_fois=args.une_fois)
        elif args.commande == "traiter":
            automate = Automate(_config(args))
            demande = Path(args.demande)
            tache = Tache(nom=demande.stem, demande=demande,
                          image=Path(args.image) if args.image else None,
                          references=[Path(r) for r in args.ref],
                          masque=Path(args.masque) if args.masque else None,
                          protege=Path(args.protege) if args.protege else None)
            dossier = automate.traiter(tache, args.sortie)
            print(f"Résultat : {dossier / 'resultat.png'}\nRapport  : {dossier / 'rapport.md'}")
        elif args.commande == "diagnostic":
            automate = Automate(_config(args))
            print(f"Attente de ComfyUI sur {automate.config.url} …")
            automate.client.attendre_demarrage(args.attendre_comfyui)
            print("Diagnostic en cours (le premier essai charge le modèle : plusieurs minutes) …")
            print(f"Rapport : {automate.diagnostic(args.sortie)}")
        elif args.commande == "compiler":
            contrat = compiler_demande(args.demande, args.sortie, args.routage, args.types,
                                       args.socle, mode=args.mode, orphelines=args.orphelines,
                                       socle_complet=args.socle_complet)
            _afficher_contrat(contrat, args.sortie)
        elif args.commande == "finaliser":
            contrat = Contrat.charger(args.contrat)
            if contrat.mode == "edition":
                if not args.original:
                    raise ArretDeclare("Mode édition : --original est obligatoire.")
                resultats = finaliser(contrat, args.original, args.masque, args.candidats,
                                      args.sortie, fondu=args.fondu, graine=args.graine,
                                      generateur=args.generateur, chemin_protege=args.protege)
                print("Classement sur défauts mesurables (l'anatomie reste à juger à l'œil) :")
                for rang, c in enumerate(resultats, start=1):
                    etat = f"rejeté : {c.rejete}" if c.rejete else f"score {c.score}"
                    print(f"  {rang}. {c.fichier}  {etat}")
            else:
                finaliser_sans_original(contrat, args.candidats, args.sortie,
                                        generateur=args.generateur)
            print(f"\nRésultat : {args.sortie}/resultat.png\nRapport  : {args.sortie}/rapport.md")
        elif args.commande == "socle":
            socle = charger_socle()
            print(f"Socle version {socle.version} — {len(socle.principes)} principes")
            for p in socle.principes:
                print(f"  {p.id:<9} [{p.module:<21}] {p.mecanisme.value:<15} "
                      f"{','.join(p.types):<18} {p.description}")
    except ArretDeclare as exc:
        print(f"ARRÊT DÉCLARÉ : {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
        return 130
    return 0
