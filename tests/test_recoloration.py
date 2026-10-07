import numpy as np
from PIL import Image

from local_image_ia.contrat import compiler
from local_image_ia.demande import DemandeFigee
from local_image_ia.masque_auto import masque_par_difference
from local_image_ia.pipeline import finaliser
from local_image_ia.recoloration import recolorer

H, W = 480, 640
VERT = (40, 95, 55)


def scene():
    """T-shirt blanc avec une bande d'ombre et un bras posé dessus ; le « modèle » rate l'ombre."""
    rng = np.random.default_rng(0)
    original = np.empty((H, W, 3), np.float32)
    original[:] = (90, 110, 140)                                   # fond bleuté
    original[100:400, 150:500] = 235                               # t-shirt blanc
    original[220:300, 260:420] = 140                               # ombre portée sur le t-shirt
    original[330:370, 180:230] = (200, 150, 120)                   # bras posé sur le t-shirt
    original = np.clip(original + rng.normal(0, 3, (H, W, 1)), 0, 255).astype(np.uint8)
    candidat = original.copy()
    tshirt = np.zeros((H, W), bool)
    tshirt[100:400, 150:500] = True
    tshirt[220:300, 260:420] = False                               # le modèle laisse l'ombre grise
    tshirt[330:370, 180:230] = False                               # et le bras tel quel
    candidat[tshirt] = np.clip(np.array(VERT) + rng.normal(0, 2, (tshirt.sum(), 3)), 0, 255)
    return original, candidat


def test_ombre_oubliee_recoloree_avec_l_ombrage_d_origine():
    original, candidat = scene()
    auto = masque_par_difference(original, candidat)
    assert not auto.masque[260, 340]                               # l'ombre est un îlot inchangé
    sortie, zone, compte = recolorer(original, candidat, auto.masque)
    assert compte.appliquee and compte.ombres_reprises > 0.01
    ombre, eclaire = sortie[240:280, 280:400].astype(float), sortie[150:200, 200:450].astype(float)
    assert (ombre[..., 1] > ombre[..., 0] + 5).mean() > 0.95       # l'ombre est devenue verte
    assert ombre.mean() < eclaire.mean()                           # et reste plus sombre
    # Rapport ombre / éclairé en lumière linéaire : celui de la photo d'origine.
    lin = lambda x: (x / 255.0) ** 2.2
    attendu = lin(140.0) / lin(235.0)
    obtenu = lin(ombre[..., 1]).mean() / lin(eclaire[..., 1]).mean()
    assert abs(obtenu - attendu) < 0.08
    assert np.array_equal(sortie[340:360, 190:220], candidat[340:360, 190:220])   # bras intact
    assert zone[260, 340]                                          # ombre ajoutée à la zone modifiée


def test_recoloration_dans_la_chaine_complete(tmp_path):
    original, candidat = scene()
    Image.fromarray(original).save(tmp_path / "o.png")
    Image.fromarray(candidat).save(tmp_path / "c.png")
    contrat = compiler(DemandeFigee.depuis_texte("Change the colour of the t-shirt to dark green.\n"))
    assert "couleur_matiere" in contrat.types
    vert = lambda im: (im[240:280, 280:400, 1] > im[240:280, 280:400, 0] + 5).mean() > 0.95
    lire = lambda f: np.asarray(Image.open(f)).astype(float)

    # Défaut « comparer » : résultat sans recoloration + variante recolorée, copies JPEG.
    finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s")
    assert not vert(lire(tmp_path / "s" / "resultat.png"))
    variante = lire(tmp_path / "s" / "resultat_recolore.png")
    assert vert(variante)
    assert np.array_equal(variante[10:60, 10:60], original[10:60, 10:60])          # fond intact
    assert (tmp_path / "s" / "resultat.jpg").exists() and (tmp_path / "s" / "resultat_recolore.jpg").exists()
    assert "resultat_recolore.png" in (tmp_path / "s" / "rapport.md").read_text("utf-8")

    (oui,) = finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s2",
                       recoloration="oui")
    assert oui.masque["recoloration"]["appliquee"] and vert(lire(tmp_path / "s2" / "resultat.png"))
    finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s3",
              recoloration="non")
    assert not (tmp_path / "s3" / "resultat_recolore.png").exists()


def test_taches_et_reflets_mal_rendus_par_le_modele_sont_recolores():
    """Non-régression du 3e essai réel : taches sombres et reflet délavé du modèle."""
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:600, 0:450]
    tshirt = (np.abs(xx - 225) < 130) & (yy > 150) & (yy < 550)
    lumiere = 0.75 + 0.25 * np.cos((xx - 150) / 90.0)
    ombre = (yy - 350) ** 2 / 75 ** 2 + (xx - 280) ** 2 / 60 ** 2 < 1
    lumiere = lumiere * np.where(ombre, 0.55, 1.0)
    original = np.empty((600, 450, 3), np.float32)
    original[:] = (150, 140, 130)
    original[tshirt] = (250 * lumiere[tshirt])[:, None]
    original = np.clip(original + rng.normal(0, 3, (600, 450, 1)), 0, 255).astype(np.uint8)
    candidat = original.astype(np.float32)
    candidat[tshirt] = np.array(VERT, np.float32) * np.clip(lumiere[tshirt], 0.5, 1.1)[:, None] * 1.3
    candidat[tshirt & ombre] = original[tshirt & ombre]                             # ombre ratée
    reflet = tshirt & (np.cos((xx - 150) / 90.0) > 0.9)
    candidat[reflet] = candidat[reflet] * 0.5 + np.array([150, 165, 155]) * 0.5      # reflet délavé
    taches = tshirt & (np.sin(xx / 11.0) * np.sin(yy / 15.0) > 0.85)
    candidat[taches] *= 0.4                                                          # taches sombres
    candidat = np.clip(candidat + rng.normal(0, 4, candidat.shape), 0, 255).astype(np.uint8)

    auto = masque_par_difference(original, candidat)
    sortie, _, compte = recolorer(original, candidat, auto.masque)
    lin = lambda x: (np.asarray(x, np.float32) / 255.0) ** 2.2
    ideal = np.clip((lin(original) * lin(compte.cible) / lin(compte.origine)) ** (1 / 2.2) * 255, 0, 255)
    interieur = (np.abs(xx - 225) < 120) & (yy > 160) & (yy < 540)
    ecart = np.abs(sortie.astype(float) - ideal).mean(axis=-1)
    assert (ecart[interieur] > 25).mean() < 0.01
    assert abs(compte.cible[1] - 100) < 20                                           # vert lu sur le vrai rendu
    fond = ~((np.abs(xx - 225) < 145) & (yy > 135) & (yy < 565))
    assert np.array_equal(sortie[fond], candidat[fond])


def test_pas_de_recoloration_hors_demande_de_couleur(tmp_path):
    original, candidat = scene()
    Image.fromarray(original).save(tmp_path / "o.png")
    Image.fromarray(candidat).save(tmp_path / "c.png")
    contrat = compiler(DemandeFigee.depuis_texte("Make the body muscular.\n"))
    (res,) = finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s")
    assert "recoloration" not in res.masque
