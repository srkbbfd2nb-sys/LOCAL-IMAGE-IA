"""Couche de contrat, de verrous, d'optimiseur et de mesures.

Le moteur de génération (ComfyUI + modèle d'édition) est une pièce
interchangeable : ce paquet ne dépend pas du GPU. Il garantit que rien
n'est perdu de la demande, que les ajouts sont visibles, et dit ce qui a
été tenu.
"""

__version__ = "0.1.0"
