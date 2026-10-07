"""Automatisation : tu déposes, le système travaille, tu récupères.

Dans ``boite/entree/``, une tâche est un groupe de fichiers de même nom :

    ma_photo.txt            la demande (obligatoire ; .txt, .md ou .json)
    ma_photo.jpg            l'image à modifier            → mode « edition »
    ma_photo.ref.jpg        image servant de modèle (ou .ref1, .ref2 …)
    ma_photo.masque.png     facultatif : zone à modifier (blanc), sinon masque automatique
    ma_photo.protege.png    facultatif : zones à ne jamais toucher (blanc), ex. le visage

Sans image à modifier mais avec des références : mode « reference ». Sans aucune
image : mode « creation ». Le résultat arrive dans ``boite/sortie/<date>_<nom>/``
(``resultat.png`` + ``rapport.md``), et les fichiers déposés sont rangés dans
``boite/archive/``.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from local_image_ia.comfy import ClientComfy
from local_image_ia.contrat import COMPLETE, CONDENSEE
from local_image_ia.gouvernance import ArretDeclare, Capacite, EtatCapacite
from local_image_ia.images import charger_image, enregistrer_png
from local_image_ia.mecanismes import capacites_phase0
from local_image_ia.pipeline import compiler_demande, finaliser, finaliser_sans_original
from local_image_ia.workflows import FORMATS, NOEUDS_REQUIS, PRESETS, graphe_klein

EXT_DEMANDE = (".txt", ".md", ".json")
EXT_IMAGE = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif")
_ROLE = re.compile(r"^(?P<nom>.+?)\.(?P<role>masque|protege|ref\w*)$", re.IGNORECASE)
DELAI_PREMIERE_GENERATION = 1200.0  # le premier passage charge le modèle (E : plusieurs minutes)


@dataclass
class Tache:
    nom: str
    demande: Path
    image: Path | None = None
    references: list[Path] = field(default_factory=list)
    masque: Path | None = None
    protege: Path | None = None

    @property
    def mode(self) -> str:
        if self.image is not None:
            return "edition"
        return "reference" if self.references else "creation"

    @property
    def fichiers(self) -> list[Path]:
        return [p for p in [self.demande, self.image, self.masque, self.protege, *self.references] if p]


@dataclass
class ConfigAutomate:
    url: str = "http://127.0.0.1:8188"
    preset: str = "klein4b"
    candidats: int = 3
    budget_s: float = 300.0       # proposition, non validée : voir la feuille de route
    fondu: int = 8
    orphelines: str = "instruction"
    socle_complet: bool = False
    texte: str = COMPLETE         # « condensee » seulement après comparaison
    format_creation: str = "portrait"
    graine: int | None = None

    @classmethod
    def charger(cls, chemin: str | Path | None) -> "ConfigAutomate":
        if not chemin or not Path(chemin).exists():
            return cls()
        d = json.loads(Path(chemin).read_text("utf-8"))
        inconnues = set(d) - set(cls.__dataclass_fields__)
        if inconnues:
            raise ArretDeclare(f"Réglages inconnus dans {chemin} : {', '.join(sorted(inconnues))}")
        config = cls(**d)
        config.verifier()
        return config

    def verifier(self) -> None:
        if self.preset not in PRESETS:
            raise ArretDeclare(f"Modèle inconnu : {self.preset}", [f"Possibles : {', '.join(PRESETS)}"])
        if self.texte not in (COMPLETE, CONDENSEE):
            raise ArretDeclare(f"Texte inconnu : {self.texte}", ["Possibles : complete, condensee"])
        if self.format_creation not in FORMATS:
            raise ArretDeclare(f"Format inconnu : {self.format_creation}",
                               [f"Possibles : {', '.join(FORMATS)}"])
        if self.candidats < 1:
            raise ArretDeclare("Il faut au moins un candidat.")


def lister_taches(dossier: str | Path) -> list[Tache]:
    dossier = Path(dossier)
    groupes: dict[str, dict] = {}
    for f in sorted(dossier.iterdir()) if dossier.exists() else []:
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        m = _ROLE.match(f.stem)
        nom, role = (m.group("nom"), m.group("role").lower()) if m else (f.stem, None)
        g = groupes.setdefault(nom, {"refs": []})
        if ext in EXT_DEMANDE and role is None:
            g["demande"] = f
        elif ext in EXT_IMAGE:
            if role is None:
                g["image"] = f
            elif role == "masque":
                g["masque"] = f
            elif role == "protege":
                g["protege"] = f
            else:
                g["refs"].append(f)
    taches = [
        Tache(nom=nom, demande=g["demande"], image=g.get("image"), references=g["refs"],
              masque=g.get("masque"), protege=g.get("protege"))
        for nom, g in groupes.items() if "demande" in g
    ]
    return sorted(taches, key=lambda t: t.demande.stat().st_mtime)


def fichiers_stables(fichiers: list[Path], attente: float = 2.0) -> bool:
    """Un fichier encore en cours de copie ne doit pas être lu."""
    try:
        return all(time.time() - f.stat().st_mtime >= attente for f in fichiers)
    except FileNotFoundError:
        return False


class Automate:
    def __init__(self, config: ConfigAutomate | None = None, client: ClientComfy | None = None,
                 journal: Callable[[str], None] = print):
        self.config = config or ConfigAutomate()
        self.config.verifier()
        self.client = client or ClientComfy(self.config.url)
        self.journal = journal
        self._sonde: list[Capacite] | None = None
        self._derniere_duree: float | None = None

    @property
    def modele(self):
        return PRESETS[self.config.preset]

    def sonder(self) -> list[Capacite]:
        if self._sonde is None:
            m = self.modele
            self._sonde = self.client.sonder(NOEUDS_REQUIS, {
                ("UNETLoader", "unet_name"): m.unet,
                ("CLIPLoader", "clip_name"): m.clip,
                ("VAELoader", "vae_name"): m.vae,
            })
        return self._sonde

    # ----- une tâche ----------------------------------------------------------------

    def traiter(self, tache: Tache, dossier: str | Path) -> Path:
        """Traite une tâche dans ``dossier`` (créé). Lève ArretDeclare en cas d'échec."""
        debut = time.monotonic()
        dossier = Path(dossier)
        (dossier / "entree").mkdir(parents=True, exist_ok=True)
        for f in tache.fichiers:
            shutil.copy2(f, dossier / "entree" / f.name)
        for f in [tache.image, *tache.references]:
            if f is not None and f.suffix.lower() in (".heic", ".heif"):
                charger_image(f)  # lève un arrêt déclaré explicite (format non lu)

        contrat = compiler_demande(tache.demande, dossier, mode=tache.mode,
                                   orphelines=self.config.orphelines,
                                   socle_complet=self.config.socle_complet)
        durees: dict[str, float] = {"compilation du contrat": round(time.monotonic() - debut, 1)}
        capacites = capacites_phase0() + self.sonder() + [
            Capacite(f"Générateur : {self.modele.nom}", EtatCapacite.VERIFIE, "ComfyUI",
                     f"Licence {self.modele.licence}"),
        ]
        instruction = contrat.instruction(self.config.texte)
        (dossier / "instruction_envoyee.txt").write_text(instruction, "utf-8")

        noms = []
        for i, f in enumerate([tache.image, *tache.references] if tache.image else tache.references):
            # On envoie l'image déjà orientée (EXIF appliqué) : le modèle et le verrou
            # voient exactement les mêmes pixels.
            prepare = dossier / "entree" / f"envoi_{i}.png"
            enregistrer_png(charger_image(f), prepare)
            noms.append(self.client.televerser(prepare, f"lia_{secrets.token_hex(4)}_{i}.png"))

        base = self.config.graine if self.config.graine is not None else secrets.randbelow(2**31)
        bruts: list[Path] = []
        (dossier / "bruts").mkdir(exist_ok=True)
        for k in range(self.config.candidats):
            ecoule = time.monotonic() - debut
            if k > 0 and self._derniere_duree and ecoule + self._derniere_duree > self.config.budget_s:
                self.journal(f"  budget de {int(self.config.budget_s)} s atteint : {k} candidat(s).")
                durees["arrêt sur budget"] = round(ecoule, 1)
                break
            graine = base + k
            graphe = graphe_klein(self.modele, instruction, noms, graine,
                                  format_creation=self.config.format_creation)
            t = time.monotonic()
            delai = (DELAI_PREMIERE_GENERATION if self._derniere_duree is None
                     else max(120.0, 3 * self._derniere_duree))
            sorties = self.client.attendre(self.client.soumettre(graphe), delai)
            images = self.client.images_de_sortie(sorties)
            if not images:
                raise ArretDeclare("ComfyUI n'a renvoyé aucune image.")
            chemin = dossier / "bruts" / f"C{k + 1}_graine{graine}.png"
            chemin.write_bytes(self.client.telecharger(images[0]))
            bruts.append(chemin)
            self._derniere_duree = time.monotonic() - t
            durees[f"génération C{k + 1} (graine {graine})"] = round(self._derniere_duree, 1)
            self.journal(f"  candidat {k + 1} : {self._derniere_duree:.0f} s")

        t = time.monotonic()
        generateur = f"{self.modele.nom} dans ComfyUI"
        if tache.mode == "edition":
            finaliser(contrat, tache.image, tache.masque, bruts, dossier, fondu=self.config.fondu,
                      graine=base, generateur=generateur, chemin_protege=tache.protege,
                      capacites=capacites, durees=durees)
        else:
            finaliser_sans_original(contrat, bruts, dossier, generateur=generateur,
                                    capacites=capacites, durees=durees)
        durees["vérification et assemblage"] = round(time.monotonic() - t, 1)
        durees["total"] = round(time.monotonic() - debut, 1)
        # Les durées finales sont ajoutées au rapport JSON.
        rapport = dossier / "rapport.json"
        d = json.loads(rapport.read_text("utf-8"))
        d["durees"] = durees
        d["config"] = asdict(self.config)
        rapport.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", "utf-8")
        with open(dossier / "rapport.md", "a", encoding="utf-8") as md:
            md.write(f"Durée totale de la demande : {durees['total']} s "
                     f"(budget visé : {int(self.config.budget_s)} s).\n")
        return dossier

    # ----- boucle de surveillance -----------------------------------------------------

    def surveiller(self, boite: str | Path, une_fois: bool = False, intervalle: float = 2.0) -> None:
        boite = Path(boite)
        entree, sortie, archive = boite / "entree", boite / "sortie", boite / "archive"
        for d in (entree, sortie, archive):
            d.mkdir(parents=True, exist_ok=True)
        self.journal(f"Dépose tes demandes dans {entree}")
        while True:
            for tache in lister_taches(entree):
                if not fichiers_stables(tache.fichiers):
                    continue
                horodatage = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                dossier = sortie / f"{horodatage}_{tache.nom}"
                self.journal(f"Tâche « {tache.nom} » (mode {tache.mode})")
                try:
                    self.traiter(tache, dossier)
                    self.journal(f"  → {dossier / 'resultat.png'}")
                except ArretDeclare as exc:
                    _ecrire_erreur(dossier, exc)
                    self.journal(f"  ARRÊT DÉCLARÉ : {exc.motif} (voir {dossier / 'ERREUR.md'})")
                except Exception as exc:  # une tâche ratée ne doit pas arrêter la boîte
                    _ecrire_erreur(dossier, exc, traceback.format_exc())
                    self.journal(f"  ERREUR inattendue : {exc} (voir {dossier / 'ERREUR.md'})")
                finally:
                    rangement = archive / f"{horodatage}_{tache.nom}"
                    rangement.mkdir(parents=True, exist_ok=True)
                    for f in tache.fichiers:
                        if f.exists():
                            shutil.move(str(f), rangement / f.name)
            if une_fois:
                return
            time.sleep(intervalle)

    # ----- diagnostic (les trois mesures de la phase 0) --------------------------------

    def diagnostic(self, dossier: str | Path) -> Path:
        dossier = Path(dossier)
        dossier.mkdir(parents=True, exist_ok=True)
        lignes = [f"# Diagnostic — {datetime.now():%Y-%m-%d %H:%M}", ""]
        try:
            capacites = self.sonder()
            lignes += ["## Capacités", ""] + [f"- {c.nom} : {c.etat.value}. {c.note}" for c in capacites]
        except ArretDeclare as exc:
            lignes += ["## Échec de la sonde", "", f"- {exc}"]
            (dossier / "diagnostic.md").write_text("\n".join(lignes) + "\n", "utf-8")
            return dossier / "diagnostic.md"
        lignes += ["", "## Mesures", "", "| Essai | Durée | Résultat |", "|---|---|---|"]
        essais = [
            ("création 1 (inclut le chargement du modèle)", "A plain white ceramic mug on a wooden table, ordinary smartphone photo.", []),
            ("création 2 (modèle déjà chargé)", "A plain white ceramic mug on a wooden table, ordinary smartphone photo.", []),
            ("édition (couleur d'un objet)", "Change the mug colour to blue. Keep everything else identical.", None),
        ]
        image_creee: Path | None = None
        for n, (titre, texte, images) in enumerate(essais, start=1):
            t = time.monotonic()
            try:
                if images is None:
                    if image_creee is None:
                        raise ArretDeclare("Pas d'image créée pour l'essai d'édition.")
                    images = [self.client.televerser(image_creee, "lia_diagnostic.png")]
                graphe = graphe_klein(self.modele, texte, images, 1234, format_creation="carre")
                sorties = self.client.attendre(self.client.soumettre(graphe), DELAI_PREMIERE_GENERATION)
                imgs = self.client.images_de_sortie(sorties)
                sortie = dossier / f"diagnostic_{n}.png"
                sortie.write_bytes(self.client.telecharger(imgs[0]))
                image_creee = image_creee or sortie
                lignes.append(f"| {titre} | {time.monotonic() - t:.0f} s | `{sortie.name}` |")
            except ArretDeclare as exc:
                lignes.append(f"| {titre} | {time.monotonic() - t:.0f} s | ÉCHEC : {exc.motif} "
                              + " ".join(exc.details) + " |")
        lignes += ["", "Envoie ce fichier tel quel : il contient les trois mesures de l'étape 1."]
        (dossier / "diagnostic.md").write_text("\n".join(lignes) + "\n", "utf-8")
        return dossier / "diagnostic.md"


def _ecrire_erreur(dossier: Path, exc: Exception, trace: str | None = None) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    if isinstance(exc, ArretDeclare):
        corps = [f"# Arrêt déclaré", "", exc.motif, ""] + [f"- {d}" for d in exc.details]
    else:
        corps = ["# Erreur inattendue", "", str(exc), "", "```", trace or "", "```"]
    corps += ["", "Les fichiers déposés ont été rangés dans boite/archive/. Corrige puis redépose-les."]
    (dossier / "ERREUR.md").write_text("\n".join(corps) + "\n", "utf-8")
