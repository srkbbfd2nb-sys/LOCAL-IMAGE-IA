import numpy as np
import pytest
from PIL import Image

from local_image_ia.contrat import compiler
from local_image_ia.demande import DemandeFigee
from local_image_ia.gouvernance import ArretDeclare, verifier_circularite
from local_image_ia.images import adapter_candidat, alpha_interne, charger_masque, flou_boite
from local_image_ia.mesures import continuite_raccord, ecart_hors_masque
from local_image_ia.pipeline import finaliser
from local_image_ia.signature import grain_par_bande, reappliquer_grain, zone_editee, zone_reference
from local_image_ia.images import luminance
from local_image_ia.verrou import composer

H, W = 240, 320


def scene(rng, bruit=4.0):
    yy, xx = np.mgrid[0:H, 0:W]
    base = np.stack([80 + 60 * xx / W, 100 + 50 * yy / H, 120 + 0 * xx], -1)
    return np.clip(base + rng.normal(0, bruit, (H, W, 1)), 0, 255).astype(np.uint8), base


def masque_carre():
    m = np.zeros((H, W), bool)
    m[60:180, 100:220] = True
    return m


def test_flou_boite_conserve_une_constante():
    a = np.full((20, 30), 7.0)
    assert np.allclose(flou_boite(a, 3), 7.0)


def test_alpha_nul_hors_masque():
    m = masque_carre()
    a = alpha_interne(m, 8)
    assert (a[~m] == 0).all()
    assert a[120, 160] == pytest.approx(1.0)


def test_verrou_hors_masque_exact():
    rng = np.random.default_rng(0)
    orig, _ = scene(rng)
    cand = rng.integers(0, 256, orig.shape, dtype=np.uint8)
    m = masque_carre()
    final = composer(orig, cand, alpha_interne(m, 8))
    r = ecart_hors_masque(orig, final, m)
    assert r["conforme"] and r["ecart_max"] == 0
    assert not np.array_equal(final[m], orig[m])


def test_grain_reapplique_sur_zone_lisse():
    rng = np.random.default_rng(1)
    orig, base = scene(rng, bruit=5.0)
    lisse = np.clip(base, 0, 255).astype(np.uint8)
    m = masque_carre()
    a = alpha_interne(m, 4)
    composee = composer(orig, lisse, a)
    final, rapport = reappliquer_grain(composee, a, m, graine=3)
    assert rapport.ajout_par_bande
    y = luminance(final)
    ref = grain_par_bande(y, zone_reference(m))
    edit = grain_par_bande(y, zone_editee(a))
    for k in ref:
        if ref[k] and edit[k]:
            assert 0.8 < edit[k] / ref[k] < 1.25
    assert ecart_hors_masque(orig, final, m)["conforme"]


def test_raccord_detecte_un_saut():
    rng = np.random.default_rng(2)
    orig, base = scene(rng, bruit=1.0)
    m = masque_carre()
    a = alpha_interne(m, 0)
    sans_saut = composer(orig, orig, a)
    cand = orig.astype(np.int16) + 60
    avec_saut = composer(orig, np.clip(cand, 0, 255).astype(np.uint8), a)
    r0 = continuite_raccord(sans_saut, m, a)["ratio"]
    r1 = continuite_raccord(avec_saut, m, a)["ratio"]
    assert r1 > 1.5 > r0


def test_masque_de_mauvaise_taille_arrete(tmp_path):
    Image.fromarray(np.zeros((10, 10), np.uint8)).save(tmp_path / "m.png")
    with pytest.raises(ArretDeclare):
        charger_masque(tmp_path / "m.png", (H, W))


def test_candidat_recadre_refuse():
    with pytest.raises(ArretDeclare):
        adapter_candidat(np.zeros((100, 100, 3), np.uint8), (H, W))
    redim, note = adapter_candidat(np.zeros((H * 2, W * 2, 3), np.uint8), (H, W))
    assert redim.shape == (H, W, 3) and note


def test_circularite():
    with pytest.raises(ArretDeclare):
        verifier_circularite("FLUX.2 klein", "flux.2 klein")


def test_finaliser_de_bout_en_bout(tmp_path):
    rng = np.random.default_rng(4)
    orig, base = scene(rng)
    Image.fromarray(orig).save(tmp_path / "orig.png")
    m = masque_carre()
    Image.fromarray((m * 255).astype(np.uint8)).save(tmp_path / "masque.png")
    cand = np.clip(base + 10, 0, 255).astype(np.uint8)
    Image.fromarray(cand).resize((W * 2, H * 2)).save(tmp_path / "c1.png")
    Image.fromarray(orig).save(tmp_path / "c2.png")

    contrat = compiler(DemandeFigee.depuis_texte(
        "Make the body muscular.\nKeep the background unchanged.\nCheck the seams.\n"))
    res = finaliser(contrat, tmp_path / "orig.png", tmp_path / "masque.png",
                    [tmp_path / "c1.png", tmp_path / "c2.png"], tmp_path / "sortie")
    assert len(res) == 2
    assert all(c.hors_masque["conforme"] for c in res)
    rapport = (tmp_path / "sortie" / "rapport.md").read_text("utf-8")
    assert "| L002 |" in rapport and "garantie" in rapport
    sortie = np.asarray(Image.open(tmp_path / "sortie" / res[0].fichier))
    assert np.array_equal(sortie[~m], orig[~m])


def test_masque_au_bord_de_l_image(tmp_path):
    rng = np.random.default_rng(5)
    orig, base = scene(rng)
    Image.fromarray(orig).save(tmp_path / "orig.png")
    m = np.zeros((H, W), bool)
    m[:100, :120] = True
    Image.fromarray((m * 255).astype(np.uint8)).save(tmp_path / "masque.png")
    Image.fromarray(np.clip(base + 20, 0, 255).astype(np.uint8)).save(tmp_path / "c.png")
    contrat = compiler(DemandeFigee.depuis_texte("Make the body muscular.\n"))
    res = finaliser(contrat, tmp_path / "orig.png", tmp_path / "masque.png",
                    [tmp_path / "c.png"], tmp_path / "s")
    sortie = np.asarray(Image.open(tmp_path / "s" / res[0].fichier))
    assert np.array_equal(sortie[~m], orig[~m])
    assert not np.array_equal(sortie[m], orig[m])
