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
    (res,) = finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s")
    sortie = np.asarray(Image.open(tmp_path / "s" / res.fichier)).astype(float)
    assert (sortie[240:280, 280:400, 1] > sortie[240:280, 280:400, 0] + 5).mean() > 0.95
    assert res.masque["recoloration"]["appliquee"]
    assert np.array_equal(sortie[10:60, 10:60], original[10:60, 10:60])            # fond intact
    sans = finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s2",
                     recoloration=False)[0]
    gris = np.asarray(Image.open(tmp_path / "s2" / sans.fichier)).astype(float)[240:280, 280:400]
    assert np.abs(gris[..., 1] - gris[..., 0]).mean() < 5                         # sans : l'ombre reste grise


def test_pas_de_recoloration_hors_demande_de_couleur(tmp_path):
    original, candidat = scene()
    Image.fromarray(original).save(tmp_path / "o.png")
    Image.fromarray(candidat).save(tmp_path / "c.png")
    contrat = compiler(DemandeFigee.depuis_texte("Make the body muscular.\n"))
    (res,) = finaliser(contrat, tmp_path / "o.png", None, [tmp_path / "c.png"], tmp_path / "s")
    assert "recoloration" not in res.masque
