"""Le routeur sur les prompts réels de Lazerr (sources/prompts)."""

from pathlib import Path

import pytest

from local_image_ia.contrat import CONDENSEE, compiler
from local_image_ia.demande import DemandeFigee
from local_image_ia.mecanismes import Mecanisme

PROMPTS = sorted((Path(__file__).parent.parent / "sources" / "prompts").glob("*"))


@pytest.mark.parametrize("chemin", PROMPTS, ids=lambda p: p.name)
def test_prompt_reel_compile_sans_perte(chemin):
    mode = "reference" if chemin.suffix == ".json" else "edition"
    c = compiler(DemandeFigee.depuis_fichier(chemin), mode=mode)
    contenu = [e for e in c.entrees if e.porte_contenu]
    # Les deux premières lignes portent l'objectif : jamais en verrou.
    assert all(e.mecanisme != Mecanisme.VERROU for e in contenu[:2])
    # Ce qui sort du texte condensé est du verrou pur, sans verbe de transformation.
    for e in c.retirees(CONDENSEE):
        assert e.mecanisme in (Mecanisme.VERROU, None)
        assert not any(v in e.texte_modele.lower() for v in ("replace", "make ", "add ", "transform"))
