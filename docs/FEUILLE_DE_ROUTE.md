# Feuille de route

## Phase 0 : le cas test sur ta machine

| Étape | Contenu | État |
|---|---|---|
| 1 | Installation de ComfyUI et de FLUX.2 klein 4B distillé, essai neutre, trois mesures | **à faire par toi** |
| 2 | Verrou par masque | fait dans ce dépôt (`verrou.py`) |
| 3 | Compilateur de contrat à partir de ton prompt condensé | fait dans ce dépôt (`contrat.py`) |
| 4 | Mesures : écart hors masque, grain et netteté, raccord, temps | fait dans ce dépôt (`mesures.py`) |

Les étapes 2 à 4 sont testées sur des images synthétiques, pas encore sur tes photos.

### Étape 1 : ce que j'attends de toi

1. Le temps du premier lancement.
2. Le temps du deuxième lancement (modèle déjà chargé).
3. Tout message d'erreur mémoire.

Fichiers attendus par ComfyUI, d'après sa documentation officielle :

```
ComfyUI/models/
├── diffusion_models/  flux-2-klein-4b-fp8.safetensors
├── text_encoders/     qwen_3_4b.safetensors
└── vae/               flux2-vae.safetensors
```

Repli déclaré en cas d'erreur mémoire : la version quantifiée Q4 (environ 2,6 Go).

### Premier essai réel de la chaîne

1. Une photo sans enjeu, convertie en JPEG ou PNG.
2. Une demande courte, par exemple changer la couleur d'un vêtement.
3. `compiler`, relecture du rapport de contrat.
4. Trois candidats dans ComfyUI, un masque dessiné à la main.
5. `finaliser`, puis comparaison de ton jugement à l'œil avec le classement mesuré.

Ce premier essai sert à **calibrer les seuils** : s'ils signalent des défauts que tu ne
vois pas, ou ratent ceux que tu vois, on les ajuste sur ces mesures.

## Phases suivantes (ordre esquissé)

1. Branchement direct sur l'API de ComfyUI (plus de copier-coller), budget de temps par
   photo.
2. Conditionnement : cartes de profondeur et de contours, pour faire passer les lignes
   caméra et pose de « absent » à « contraint ».
3. Comparaison complète contre condensée, pour décider de la condensation.
4. Juge distinct du générateur, lancé après lui, si la mémoire le permet.
5. Moteur plus compétent, selon la sortie matérielle choisie.
6. Entraînement (LoRA), quand le matériel le permettra.
7. Autres styles, puis vidéo en dernier.

## Points ouverts

- [ ] Choisir la photo du cas test.
- [ ] Choisir la version du prompt (la courte avec « Not too much arms » et « Snapchat quality », ou une autre).
- [ ] Rapporter les trois mesures de l'essai neutre.
- [ ] Confirmer ou ajuster le plafond de 5 minutes par photo (proposition non validée, non mesurée).
- [ ] Écrire le guide de prise de vue à l'iPhone 16.
- [ ] Concevoir l'étape où l'IA identifie ce que la photo représente, son intention et les parties du corps (et propose le masque).
- [ ] Ajouter tes prompts d'origine dans `exemples/` pour régler le routage dessus.
- [ ] Langue du texte envoyé au modèle : tes lignes partent telles quelles (non-suppression) ; l'effet d'une demande en français sur FLUX.2 klein n'est pas vérifié.
- [ ] Vérifier les éléments non contrôlés (Fizgig, Qwen-Image-i2L, Z-Image-Edit, besoins mémoire LoRA) et les obligations de marquage des contenus générés.
- [ ] Trancher plus tard la sortie matérielle : GPU loué, nouvelle machine ou API.
