"""Workflows ComfyUI au format API, construits par le code.

Le graphe reproduit celui du modèle officiel « Flux.2 [Klein] 4B Distilled: Image
Edit » (dépôt Comfy-Org/workflow_templates, vérifié le 7 octobre 2026) : mêmes
nœuds, mêmes réglages (4 étapes, cfg 1, euler, conditionnement négatif mis à zéro,
images de référence passées par ReferenceLatent). Deux écarts, déclarés :

- mise à l'échelle des images en « area » au lieu de « nearest-exact » : une photo
  de 24 Mpx réduite à 1 Mpx en plus proche voisin crée de l'aliasing (O) ;
- ``resolution_steps`` à 16 au lieu de 1 : la sortie a alors exactement la taille
  de l'image réduite, ce qui garde l'alignement au pixel pour le verrou.

Sans image, le graphe est celui du modèle « Flux.2 [Klein] 4B: Text to Image »
distillé (latent vide de taille fixe).
"""

from __future__ import annotations

from dataclasses import dataclass

NOEUDS_REQUIS = (
    "UNETLoader", "CLIPLoader", "VAELoader", "CLIPTextEncode", "ConditioningZeroOut",
    "LoadImage", "ImageScaleToTotalPixels", "GetImageSize", "VAEEncode", "ReferenceLatent",
    "EmptyFlux2LatentImage", "Flux2Scheduler", "KSamplerSelect", "RandomNoise", "CFGGuider",
    "SamplerCustomAdvanced", "VAEDecode", "SaveImage",
)


@dataclass(frozen=True)
class ConfigModele:
    nom: str
    unet: str
    clip: str
    vae: str
    etapes: int
    cfg: float
    negatif: str  # "zero" (distillé) ou "vide" (base : texte vide encodé)
    licence: str
    megapixels: float = 1.0


PRESETS: dict[str, ConfigModele] = {
    "klein4b": ConfigModele(
        nom="FLUX.2 klein 4B distillé (fp8)", unet="flux-2-klein-4b-fp8.safetensors",
        clip="qwen_3_4b.safetensors", vae="flux2-vae.safetensors", etapes=4, cfg=1.0,
        negatif="zero", licence="Apache 2.0",
    ),
    "klein4b_base": ConfigModele(
        nom="FLUX.2 klein 4B base (fp8)", unet="flux-2-klein-base-4b-fp8.safetensors",
        clip="qwen_3_4b.safetensors", vae="flux2-vae.safetensors", etapes=20, cfg=5.0,
        negatif="vide", licence="Apache 2.0",
    ),
}

# Formats de création (pas d'image source), multiples de 16, environ 1 Mpx.
FORMATS = {
    "portrait": (864, 1152),     # 3:4, comme un iPhone en vertical
    "paysage": (1152, 864),
    "carre": (1024, 1024),
    "vertical_9_16": (768, 1360),
}


def graphe_klein(
    config: ConfigModele,
    instruction: str,
    images: list[str],
    graine: int,
    format_creation: str = "portrait",
    prefixe: str = "local_image_ia",
) -> dict:
    """Graphe API. ``images`` : noms des images téléversées ; la première fixe la taille."""
    g: dict[str, dict] = {}

    def noeud(id_: str, classe: str, **entrees) -> list:
        g[id_] = {"class_type": classe, "inputs": entrees}
        return [id_, 0]

    modele = noeud("modele", "UNETLoader", unet_name=config.unet, weight_dtype="default")
    clip = noeud("clip", "CLIPLoader", clip_name=config.clip, type="flux2", device="default")
    vae = noeud("vae", "VAELoader", vae_name=config.vae)
    positif = noeud("texte", "CLIPTextEncode", text=instruction, clip=clip)
    if config.negatif == "zero":
        negatif = noeud("negatif", "ConditioningZeroOut", conditioning=positif)
    else:
        negatif = noeud("negatif", "CLIPTextEncode", text="", clip=clip)

    largeur: int | list
    hauteur: int | list
    if images:
        for i, nom in enumerate(images):
            charge = noeud(f"image_{i}", "LoadImage", image=nom)
            reduit = noeud(f"reduction_{i}", "ImageScaleToTotalPixels", image=charge,
                           upscale_method="area", megapixels=config.megapixels,
                           resolution_steps=16)
            latent = noeud(f"encodage_{i}", "VAEEncode", pixels=reduit, vae=vae)
            positif = noeud(f"reference_pos_{i}", "ReferenceLatent", conditioning=positif,
                            latent=latent)
            negatif = noeud(f"reference_neg_{i}", "ReferenceLatent", conditioning=negatif,
                            latent=latent)
            if i == 0:
                noeud("taille", "GetImageSize", image=reduit)
                largeur, hauteur = ["taille", 0], ["taille", 1]
    else:
        largeur, hauteur = FORMATS[format_creation]

    latent_vide = noeud("latent", "EmptyFlux2LatentImage", width=largeur, height=hauteur,
                        batch_size=1)
    sigmas = noeud("planificateur", "Flux2Scheduler", steps=config.etapes, width=largeur,
                   height=hauteur)
    echantillonneur = noeud("echantillonneur", "KSamplerSelect", sampler_name="euler")
    bruit = noeud("bruit", "RandomNoise", noise_seed=int(graine))
    guide = noeud("guide", "CFGGuider", model=modele, positive=positif, negative=negatif,
                  cfg=config.cfg)
    sortie = noeud("generation", "SamplerCustomAdvanced", noise=bruit, guider=guide,
                   sampler=echantillonneur, sigmas=sigmas, latent_image=latent_vide)
    pixels = noeud("decodage", "VAEDecode", samples=sortie, vae=vae)
    noeud("enregistrement", "SaveImage", images=pixels, filename_prefix=prefixe)
    return g
