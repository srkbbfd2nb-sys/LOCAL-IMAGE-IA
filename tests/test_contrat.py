import json

import pytest

from local_image_ia.contrat import (
    COMPLETE, CONDENSEE, Contrat, charger_routage_manuel, compiler, verifier_non_suppression,
)
from local_image_ia.demande import DemandeFigee
from local_image_ia.gouvernance import ArretDeclare
from local_image_ia.mecanismes import Mecanisme

DEMANDE = """OBJECTIVE:
Make the visible physique naturally muscular and athletic.

LOCKS:
Keep the face, hair and hands identical.
Keep the same camera height, distance and tilt.

Snapchat quality: same grain as the rest of the photo.
FINAL CHECK:
Viewer test: someone who never saw the original notices nothing.
"""


def contrat(texte=DEMANDE, **kw):
    return compiler(DemandeFigee.depuis_texte(texte), **kw)


def test_empreinte_et_integrite():
    d = DemandeFigee.depuis_texte(DEMANDE)
    d.verifier_integrite()
    falsifiee = DemandeFigee(texte=d.texte + "x", empreinte=d.empreinte, lignes=d.lignes)
    with pytest.raises(ArretDeclare):
        falsifiee.verifier_integrite()


def test_chaque_ligne_a_une_destination():
    c = contrat()
    m = {e.id: e.mecanisme for e in c.entrees}
    assert m["L002"] == Mecanisme.INSTRUCTION
    assert m["L005"] == Mecanisme.VERROU
    # Sous un titre de verrou, une ligne caméra reste du conditionnement.
    assert m["L006"] == Mecanisme.CONDITIONNEMENT
    assert m["L008"] == Mecanisme.SIGNATURE
    assert m["L010"] == Mecanisme.VERIFICATION


def test_instruction_complete_contient_toutes_les_lignes_dans_l_ordre():
    c = contrat()
    texte = c.instruction(COMPLETE)
    pos = [texte.index(l.texte) for l in c.demande.lignes if l.texte.strip()]
    assert pos == sorted(pos)


def test_condensation_ne_retire_que_les_lignes_garanties():
    c = contrat()
    retirees = {e.id for e in c.retirees(CONDENSEE)}
    # Seule la ligne visage sort : le titre « LOCKS: » reste, car une de ses lignes
    # (la caméra) reste dans le texte et ne doit pas perdre son contexte.
    assert retirees == {"L005"}
    condense = c.instruction(CONDENSEE)
    assert "LOCKS:\nKeep the same camera height" in condense
    assert "Keep the face" not in condense


def test_ligne_mixte_verrou_et_transformation_reste_une_instruction():
    c = contrat("REPLACE THE PARKED CAR WITH A BMW, ORIGINAL PHOTO PRESERVED\n"
                "Preserve the original image's photographic character.\n"
                "Keep the face identical. No beautification.\n"
                "Keep the background unchanged.\n")
    m = {e.id: e.mecanisme for e in c.entrees}
    assert m["L001"] == Mecanisme.INSTRUCTION   # objectif, jamais retiré du texte condensé
    assert m["L002"] == Mecanisme.INSTRUCTION   # « character » : rien que le masque garantisse
    assert m["L003"] == Mecanisme.INSTRUCTION   # mixte : « No beautification » est une consigne
    assert m["L004"] == Mecanisme.VERROU
    assert "REPLACE THE PARKED CAR" in c.instruction(CONDENSEE)


def test_modes_reference_et_creation_ne_condensent_rien():
    texte = "Change the top to white.\nKeep the background unchanged.\n"
    for mode in ("reference", "creation"):
        c = contrat(texte, mode=mode)
        assert c.retirees(CONDENSEE) == []
        assert c.instruction(CONDENSEE) == c.instruction(COMPLETE)
        hors_mode = {s.principe.id for s in c.socle if s.statut == "hors mode"}
        assert "S-VER-01" in hors_mode and "S-SIG-01" in hors_mode


def test_ligne_sans_regle_va_en_instruction_par_defaut():
    c = contrat("Make the body muscular.\nLorem ipsum dolor.\n")
    assert c.entree("L002").mecanisme == Mecanisme.INSTRUCTION
    assert c.entree("L002").routage == "défaut"
    assert any("défaut" in a for a in c.avertissements)


def test_ligne_orpheline_arrete_la_compilation():
    with pytest.raises(ArretDeclare) as exc:
        contrat("Make the body muscular.\nLorem ipsum dolor.\n", orphelines="arret")
    assert "L002" in str(exc.value)


def test_etiquette_explicite_route_et_disparait_du_texte_modele():
    c = contrat("Make the body muscular.\n- [verification] Lorem ipsum dolor.\n")
    e = c.entree("L002")
    assert e.mecanisme == Mecanisme.VERIFICATION and e.routage == "étiquette"
    assert e.texte == "- [verification] Lorem ipsum dolor."
    assert "- Lorem ipsum dolor." in c.instruction(COMPLETE)


def test_etiquette_inconnue_arrete():
    with pytest.raises(ArretDeclare):
        contrat("Make the body muscular.\n[blabla] Lorem.\n")


def test_sections_du_prompt_modulaire_ne_sont_pas_des_etiquettes():
    c = contrat("[OBJECTIF DE LA RETOUCHE]\nMake the body muscular.\n[CAMÉRA À CONSERVER]\nsame height\n")
    assert c.entree("L001").role == "titre"
    assert c.entree("L004").mecanisme == Mecanisme.CONDITIONNEMENT
    assert c.entree("L004").routage == "hérité de L003"


def test_sans_instruction_arrete():
    with pytest.raises(ArretDeclare):
        contrat("Keep the background unchanged.\n")


def test_socle_s_ajoute_etiquete_et_apres_la_demande():
    c = contrat()
    texte = c.instruction(COMPLETE)
    assert "Additional principles (added by the optimizer" in texte
    assert texte.index("Viewer test") < texte.index("Additional principles")
    assert c.types == ["corps"]
    actifs = {s.principe.id for s in c.socle_actif()}
    assert "S-COR-02" in actifs and "S-REM-01" not in actifs
    # Les ajouts sont regroupés par module du prompt modulaire.
    assert "[LIGHTING]\n- Keep the original light" in texte


def test_principe_deja_dit_par_la_demande_n_est_pas_repete():
    c = contrat("Make the body muscular.\nAdd contact shadows where the arms touch the torso.\n")
    omb = next(s for s in c.socle if s.principe.id == "S-OMB-01")
    assert omb.statut == "couvert" and omb.conflit_avec == "L002"
    assert "contact shadows where surfaces touch" not in c.instruction(COMPLETE)
    complet = contrat("Make the body muscular.\nAdd contact shadows where the arms touch.\n",
                      socle_complet=True)
    assert "contact shadows where surfaces touch" in complet.instruction(COMPLETE)


def test_conflit_la_ligne_de_la_demande_gagne():
    c = contrat("Make the body muscular.\nMake it look like a studio magazine shot.\n")
    pip = next(s for s in c.socle if s.principe.id == "S-PIP-02")
    assert pip.statut == "suspendu" and pip.conflit_avec == "L002"
    assert "ordinary smartphone photograph" not in c.instruction(COMPLETE)
    assert any("S-PIP-02" in a for a in c.avertissements)


def test_interdiction_de_bruit_suspend_la_reapplication_du_grain():
    c = contrat("Make the body muscular.\n- Do NOT inject artificial noise, artifacts or degradation.\n")
    grain = next(s for s in c.socle if s.principe.id == "S-SIG-01")
    assert grain.statut == "suspendu" and grain.conflit_avec == "L002"


def test_element_de_liste_sous_une_interdiction_n_est_pas_un_conflit():
    c = contrat("Make the body muscular.\nDo not convert the image into:\n- DSLR studio photography\n")
    pip = next(s for s in c.socle if s.principe.id == "S-PIP-02")
    assert pip.statut != "suspendu"


def test_ligne_negative_ne_cree_pas_de_conflit():
    c = contrat("Make the body muscular.\nNever studio or magazine rendering.\n")
    pip = next(s for s in c.socle if s.principe.id == "S-PIP-02")
    assert pip.statut != "suspendu"


def test_aller_retour_json(tmp_path):
    c = contrat()
    chemin = tmp_path / "contrat.json"
    c.enregistrer(chemin)
    relu = Contrat.charger(chemin)
    assert relu.instruction(COMPLETE) == c.instruction(COMPLETE)
    assert relu.demande.empreinte == c.demande.empreinte


def test_contrat_modifie_a_la_main_est_refuse(tmp_path):
    c = contrat()
    d = c.to_dict()
    d["instruction_complete"] = d["instruction_complete"].replace("Keep the face", "Change the face")
    chemin = tmp_path / "contrat.json"
    chemin.write_text(json.dumps(d), "utf-8")
    with pytest.raises(ArretDeclare):
        Contrat.charger(chemin)


def test_invariant_detecte_une_ligne_reecrite():
    c = contrat()
    c.entrees[1].texte = "Make the face different."
    with pytest.raises(ArretDeclare):
        verifier_non_suppression(c)


def test_routage_manuel_lie_a_l_empreinte(tmp_path):
    d = DemandeFigee.depuis_texte("Make the body muscular.\nLorem ipsum dolor.\n")
    f = tmp_path / "routage.json"
    f.write_text(json.dumps({"empreinte_sha256": d.empreinte, "lignes": {"L002": "verification"}}))
    c = compiler(d, routage_manuel=charger_routage_manuel(f, d))
    assert c.entree("L002").routage == "manuel"
    f.write_text(json.dumps({"empreinte_sha256": "autre", "lignes": {}}))
    with pytest.raises(ArretDeclare):
        charger_routage_manuel(f, d)


def test_demande_json_structure():
    texte = '{\n  "objective": "Replace the white car with a black car",\n  "camera": {\n    "height": "chest level"\n  }\n}\n'
    c = contrat(texte)
    assert c.entree("L001").role == "structure"
    assert c.entree("L004").mecanisme == Mecanisme.CONDITIONNEMENT
    assert "remplacement_objet" in c.types
    assert c.instruction(COMPLETE).startswith(texte.rstrip("\n").split("\n")[0])


def test_titre_vaut_pour_son_paragraphe():
    c = contrat("Make the body muscular.\n\nLOCKS:\nthe face\n")
    assert c.entree("L004").mecanisme == Mecanisme.VERROU
    # Après la ligne vide, la ligne n'hérite plus du verrou : sans mot-clé, elle est orpheline.
    with pytest.raises(ArretDeclare) as exc:
        contrat("Make the body muscular.\n\nLOCKS:\nthe face\n\nA tasteful result.\n",
                orphelines="arret")
    assert "L006" in str(exc.value)


def test_section_numerotee_n_herite_pas_du_titre_precedent():
    c = contrat("5. MUSCLES:\n- Arms: more volume.\n\n10. BACKGROUND: Untouched walls, floor, tiles.\n")
    assert c.entree("L002").routage == "hérité de L001"
    assert c.entree("L004").mecanisme == Mecanisme.VERROU


def test_cli_compiler_et_arret_declare(tmp_path, capsys):
    from local_image_ia.cli import main

    ok = tmp_path / "ok.txt"
    ok.write_text("Make the body muscular.\nKeep the background unchanged.\n", "utf-8")
    assert main(["compiler", str(ok), "-o", str(tmp_path / "s")]) == 0
    assert (tmp_path / "s" / "contrat.json").exists()
    assert (tmp_path / "s" / "instruction_complete.txt").read_text("utf-8").startswith(
        "Make the body muscular.\nKeep the background unchanged.\n")

    ko = tmp_path / "ko.txt"
    ko.write_text("Make the body muscular.\nLorem ipsum.\n", "utf-8")
    assert main(["compiler", str(ko), "-o", str(tmp_path / "s2"), "--orphelines", "arret"]) == 2
    assert "ARRÊT DÉCLARÉ" in capsys.readouterr().err
