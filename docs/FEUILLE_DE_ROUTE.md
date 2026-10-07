# Feuille de route

## Phase 0 : le cas test sur ta machine

| Étape | Contenu | État |
|---|---|---|
| 1 | Installation de ComfyUI et du modèle, essai neutre, trois mesures | **automatisée** : `installer.bat` puis `diagnostic.bat` ; à lancer par toi |
| 2 | Verrou (masque fourni ou automatique) | fait (`verrou.py`, `masque_auto.py`) |
| 3 | Compilateur de contrat et optimiseur | fait (`contrat.py`, `routage.py`, `socle.py`), testé sur tes 5 prompts |
| 4 | Mesures : hors zone, grain, netteté, raccord, temps | fait (`mesures.py`, durées dans chaque rapport) |
| 5 | Automatisation : dossier surveillé, candidats, budget, rapport | fait (`automate.py`, `comfy.py`, `workflows.py`) |

Tout est testé (53 tests) contre un faux ComfyUI qui imite l'API réelle, **pas encore
sur ta machine ni avec le vrai modèle**. C'est la prochaine étape.

### Ce que j'attends de toi

1. Lancer `windows\installer.bat`, puis `windows\diagnostic.bat`.
2. M'envoyer `boite\diagnostic\diagnostic.md` (durées de la première et de la deuxième
   création, de l'édition, et toute erreur mémoire), ou le message d'erreur si une étape
   s'arrête.
3. Premier essai réel : une photo sans enjeu + une demande courte (changer la couleur
   d'un vêtement) dans `boite\entree\`, puis ton jugement à l'œil comparé au classement.

### Repli si la mémoire ne suffit pas (déclaré, non installé)

La documentation officielle indique 8,4 Go de mémoire vidéo pour klein 4B distillé
**(F)** ; tu en as 6. ComfyUI déporte alors une partie en mémoire vive : plus lent, en
principe fonctionnel **(E)**. Si le diagnostic montre une erreur mémoire ou une durée
inacceptable, les replis, dans l'ordre :

1. lancer ComfyUI avec `--reserve-vram` ou `--disable-smart-memory` (options vérifiées
   dans son code) ;
2. l'encodeur de texte allégé `qwen_3_4b_fp4_flux2.safetensors` (3,8 Go au lieu de 8 Go,
   même dépôt officiel) ; sa compatibilité avec une RTX 3060 reste à vérifier ;
3. une version quantifiée Q4 du modèle (environ 2,6 Go), qui demande un nœud
   communautaire supplémentaire.

## Phases suivantes (ordre esquissé)

1. **Calibration** : ajuster les seuils (masque automatique, raccord, grain, netteté) sur
   tes vraies photos et ton jugement.
2. **Analyse de l'image par IA** : un modèle de vision local qui identifie le sujet,
   l'intention, les parties du corps, et propose la zone protégée (visage, mains). À
   choisir et vérifier selon la mémoire disponible.
3. **Conditionnement** : cartes de profondeur et de contours, pour faire passer les lignes
   caméra et pose de « absent » à « contraint ». Disponibilité pour FLUX.2 klein à vérifier.
4. **Comparaison complète contre condensée**, pour décider de la condensation.
5. **Juge distinct du générateur**, lancé après lui, si la mémoire le permet.
6. **Petite interface** (page locale) en plus du dossier surveillé, si tu le souhaites.
7. **Moteur plus compétent**, selon la sortie matérielle choisie (GPU loué, nouvelle
   machine 16–24 Go, API).
8. **Entraînement** (LoRA), quand le matériel le permettra.
9. **Autres styles**, puis **vidéo** en dernier.

## Décisions à confirmer par toi

- [ ] **Lignes sans destination** : je les envoie maintenant au modèle (« défaut ») au
  lieu d'arrêter, pour que l'automatisation ne bloque pas sur tes longs prompts (43 et 86
  lignes concernées sur le protocole master et le JSON). Rien n'est promis pour ces
  lignes. Réglage `orphelines` pour revenir à l'arrêt.
- [ ] **Principes déjà couverts** : non répétés dans le texte du modèle (réglage
  `socle_complet` pour tout répéter).
- [ ] **Grain** : ton prompt « 12 points » interdit d'injecter du bruit ; le système
  suspend donc la réapplication du grain quand cette ligne est présente. À garder ?
- [ ] **Plafond de 5 minutes par photo** (proposition, non mesurée).
- [ ] **Longueur des prompts** : tes prompts font 1 300 à 5 500 jetons (estimation) ;
  au-delà d'environ 512, le modèle risque de diluer la consigne **(E)**. La version
  condensée retire peu de chose. Il faudra comparer un prompt long et un prompt court
  sur la même photo.

## Points ouverts

- [ ] Choisir la photo du cas test.
- [ ] Choisir la version du prompt (13 points, 12 points avec signature, ou protocole master).
- [ ] Rapporter le diagnostic.
- [ ] Vérifier les éléments non contrôlés (Fizgig, Qwen-Image-i2L, Z-Image-Edit, besoins
  mémoire LoRA) et les obligations de marquage des contenus générés.
- [ ] Trancher plus tard la sortie matérielle.
