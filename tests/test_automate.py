import json
import os
import time

import numpy as np
import pytest
from PIL import Image

from faux_comfy import FauxComfy
from local_image_ia.automate import Automate, ConfigAutomate, Tache, lister_taches
from local_image_ia.comfy import ClientComfy
from local_image_ia.gouvernance import ArretDeclare
from local_image_ia.masque_auto import masque_par_difference
from local_image_ia.workflows import FORMATS, NOEUDS_REQUIS, PRESETS, graphe_klein

H, W = 480, 640
DEMANDE = "Make the visible physique naturally muscular.\nKeep the background unchanged.\n"


@pytest.fixture
def comfy():
    serveur = FauxComfy()
    yield serveur
    serveur.arreter()


def photo(tmp_path, nom="photo.jpg"):
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:H, 0:W]
    base = np.stack([60 + 80 * xx / W, 90 + 60 * yy / H, 110 + 0 * xx], -1)
    img = np.clip(base + rng.normal(0, 4, (H, W, 1)), 0, 255).astype(np.uint8)
    chemin = tmp_path / nom
    Image.fromarray(img).save(chemin, quality=95)
    return chemin


def automate(comfy, **reglages):
    config = ConfigAutomate(url=comfy.url, graine=7, **reglages)
    return Automate(config, journal=lambda m: None)


def vieillir(*chemins):
    t = time.time() - 60
    for c in chemins:
        os.utime(c, (t, t))


def test_graphe_klein_fidele_au_modele_officiel():
    g = graphe_klein(PRESETS["klein4b"], "Change the mug colour.", ["a.png", "b.png"], 5)
    classes = [n["class_type"] for n in g.values()]
    assert set(classes) <= set(NOEUDS_REQUIS)
    assert classes.count("ReferenceLatent") == 4         # positif et négatif, par image
    assert g["planificateur"]["inputs"]["steps"] == 4 and g["guide"]["inputs"]["cfg"] == 1.0
    assert g["negatif"]["class_type"] == "ConditioningZeroOut"
    assert g["reduction_0"]["inputs"]["resolution_steps"] == 16
    assert g["latent"]["inputs"]["width"] == ["taille", 0]
    for n in g.values():                                  # tous les liens pointent vers un nœud
        for v in n["inputs"].values():
            if isinstance(v, list):
                assert v[0] in g
    creation = graphe_klein(PRESETS["klein4b"], "A mug.", [], 1, format_creation="portrait")
    assert (creation["latent"]["inputs"]["width"], creation["latent"]["inputs"]["height"]) == FORMATS["portrait"]
    base = graphe_klein(PRESETS["klein4b_base"], "A mug.", [], 1)
    assert base["negatif"]["class_type"] == "CLIPTextEncode" and base["negatif"]["inputs"]["text"] == ""


def test_lister_taches_et_modes(tmp_path):
    for nom in ["a.txt", "a.jpg", "a.masque.png", "a.protege.png", "b.txt", "b.ref.jpg",
                "b.ref2.png", "c.md", "d.jpg"]:
        (tmp_path / nom).write_bytes(b"x")
    taches = {t.nom: t for t in lister_taches(tmp_path)}
    assert set(taches) == {"a", "b", "c"}                  # d.jpg attend sa demande
    assert taches["a"].mode == "edition" and taches["a"].masque.name == "a.masque.png"
    assert taches["a"].protege.name == "a.protege.png"
    assert taches["b"].mode == "reference" and len(taches["b"].references) == 2
    assert taches["c"].mode == "creation"


def test_masque_automatique_ignore_la_derive_globale():
    rng = np.random.default_rng(1)
    original = np.clip(120 + rng.normal(0, 4, (H, W, 3)), 0, 255).astype(np.uint8)
    candidat = original.astype(np.float32) * 1.05 + 3          # dérive sur toute l'image
    candidat[200:300, 250:400] += 50                             # modification locale
    candidat = np.clip(candidat, 0, 255).astype(np.uint8)
    auto = masque_par_difference(original, candidat)
    assert auto.masque[250, 320] and not auto.masque[20, 20]
    assert 0.03 < auto.part < 0.3
    corrige = auto.derive.appliquer(candidat).astype(float)
    assert abs(corrige[20:120, 20:120].mean() - original[20:120, 20:120].mean()) < 1.5
    protege = np.zeros((H, W), bool)
    protege[:, :320] = True
    auto2 = masque_par_difference(original, candidat, protege)
    assert not auto2.masque[:, :320].any() and auto2.masque[250, 350]


def test_derive_de_couleur_estimee_sur_une_image_contrastee():
    yy, xx = np.mgrid[0:H, 0:W]
    original = np.stack([20 + 200 * xx / W, 30 + 180 * yy / H, 40 + 150 * xx / W], -1).astype(np.uint8)
    candidat = np.clip(original.astype(np.float32) * 1.06 - 4, 0, 255).astype(np.uint8)
    candidat[200:300, 250:400] = 255
    auto = masque_par_difference(original, candidat)
    assert auto.derive.gains[0] == pytest.approx(1 / 1.06, abs=0.02)
    hors = ~auto.masque
    ecart = np.abs(auto.derive.appliquer(candidat).astype(int) - original.astype(int))[hors]
    assert ecart.mean() < 2


def test_traiter_edition_de_bout_en_bout(comfy, tmp_path):
    demande = tmp_path / "corps.txt"
    demande.write_text(DEMANDE, "utf-8")
    original = photo(tmp_path)
    a = automate(comfy, candidats=2)
    dossier = a.traiter(Tache("corps", demande, image=original), tmp_path / "sortie")

    assert (dossier / "resultat.png").exists() and (dossier / "rapport.md").exists()
    rapport = json.loads((dossier / "rapport.json").read_text("utf-8"))
    assert rapport["mode"] == "edition" and len(rapport["candidats"]) == 2
    assert rapport["candidats"][0]["masque"]["source"] == "automatique"
    assert "total" in rapport["durees"]
    # Le texte envoyé au modèle est l'instruction complète du contrat.
    envoye = comfy.graphes[0]["texte"]["inputs"]["text"]
    assert envoye.startswith(DEMANDE) and envoye == (dossier / "instruction_envoyee.txt").read_text("utf-8")
    # Hors zone modifiée, l'original est recopié au pixel près, pour chaque candidat.
    orig = np.asarray(Image.open(original).convert("RGB"))
    for i in (1, 2):
        sortie = np.asarray(Image.open(dossier / f"candidat_0{i}.png"))
        masque = np.asarray(Image.open(dossier / "masques" / f"C{i}.png")) > 127
        assert 0.05 < masque.mean() < 0.5
        assert masque[H // 2, W // 2] and not masque[5, 5]
        assert np.array_equal(sortie[~masque], orig[~masque])
    texte = (dossier / "rapport.md").read_text("utf-8")
    assert "Résultat retenu" in texte and "automatique" in texte


def test_traiter_creation_sans_image(comfy, tmp_path):
    demande = tmp_path / "tasse.txt"
    demande.write_text("A plain white ceramic mug on a wooden table.\n", "utf-8")
    dossier = automate(comfy, candidats=1).traiter(Tache("tasse", demande), tmp_path / "s")
    assert (dossier / "resultat.png").exists()
    assert json.loads((dossier / "rapport.json").read_text("utf-8"))["mode"] == "creation"
    assert "LoadImage" not in [n["class_type"] for n in comfy.graphes[0].values()]


def test_surveiller_une_fois(comfy, tmp_path):
    boite = tmp_path / "boite"
    entree = boite / "entree"
    entree.mkdir(parents=True)
    (entree / "corps.txt").write_text(DEMANDE, "utf-8")
    photo(entree, "corps.jpg")
    (entree / "tasse.txt").write_text("A mug on a table.\n", "utf-8")
    vieillir(*entree.iterdir())
    automate(comfy, candidats=1).surveiller(boite, une_fois=True)
    sorties = sorted(p.name for p in (boite / "sortie").iterdir())
    assert len(sorties) == 2 and all((boite / "sortie" / s / "resultat.png").exists() for s in sorties)
    assert list(entree.iterdir()) == []
    assert len(list((boite / "archive").iterdir())) == 2


def test_erreur_memoire_declaree_et_boite_continue(tmp_path):
    serveur = FauxComfy(erreur_generation="CUDA out of memory. Tried to allocate 2.00 GiB")
    try:
        boite = tmp_path / "boite"
        (boite / "entree").mkdir(parents=True)
        (boite / "entree" / "x.txt").write_text("A mug.\n", "utf-8")
        vieillir(boite / "entree" / "x.txt")
        automate(serveur, candidats=1).surveiller(boite, une_fois=True)
        (erreur,) = (boite / "sortie").glob("*/ERREUR.md")
        texte = erreur.read_text("utf-8")
        assert "out of memory" in texte and "Mémoire insuffisante" in texte
    finally:
        serveur.arreter()


def test_comfyui_absent_arret_declare():
    client = ClientComfy("http://127.0.0.1:9", delai=1)
    assert not client.joignable()
    with pytest.raises(ArretDeclare) as exc:
        client.stats()
    assert "ne répond pas" in exc.value.motif


def test_diagnostic(comfy, tmp_path):
    rapport = automate(comfy).diagnostic(tmp_path / "diag")
    texte = rapport.read_text("utf-8")
    assert texte.count("| création") == 2 and "| édition" in texte and "ÉCHEC" not in texte


def test_cli_traiter(comfy, tmp_path, capsys):
    from local_image_ia.cli import main

    demande = tmp_path / "corps.txt"
    demande.write_text(DEMANDE, "utf-8")
    code = main(["traiter", "--demande", str(demande), "--image", str(photo(tmp_path)),
                 "--url", comfy.url, "--candidats", "1", "--graine", "3", "-o", str(tmp_path / "s")])
    assert code == 0
    assert (tmp_path / "s" / "resultat.png").exists()
    assert "Résultat" in capsys.readouterr().out
