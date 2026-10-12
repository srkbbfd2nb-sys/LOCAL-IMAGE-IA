# Feuille de route

## Phase 0 : le cas test sur ta machine

| Étape | Contenu | État |
|---|---|---|
| 1 | Installation de ComfyUI et du modèle, essai neutre, trois mesures | **fait sur ta machine** (diagnostic ci-dessous) |
| 2 | Verrou (masque fourni ou automatique) | fait (`verrou.py`, `masque_auto.py`) |
| 3 | Compilateur de contrat et optimiseur | fait (`contrat.py`, `routage.py`, `socle.py`), testé sur tes 5 prompts |
| 4 | Mesures : hors zone, grain, netteté, raccord, temps | fait (`mesures.py`, durées dans chaque rapport) |
| 5 | Automatisation : dossier surveillé, candidats, budget, rapport | fait (`automate.py`, `comfy.py`, `workflows.py`) |

Tout est testé (67 tests) contre un faux ComfyUI qui imite l'API réelle, **pas encore
sur ta machine ni avec le vrai modèle**. C'est la prochaine étape.

### Diagnostic du 7 octobre 2026, 19 h 18 (ta machine)

| Essai | Durée | Lecture |
|---|---|---|
| création 1, chargement du modèle compris | 17 s | mesure valable **(F)** |
| création 2 | 0 s | **non valable** : graphe identique, ComfyUI a renvoyé son résultat en cache. Corrigé (graine différente par essai) |
| édition, image 1 Mpx | 21 s | mesure valable **(F)** |

Aucune erreur mémoire : les 6 Go suffisent pour klein 4B distillé, avec déport en
mémoire vive géré par ComfyUI **(F)**. Estimation pour une vraie photo de 24 Mpx avec
3 candidats : 1 à 2 minutes, dont environ 20 s de génération et jusqu'à une dizaine de
secondes de traitement par le code par candidat **(E, à mesurer)**.

### Premiers essais réels (t-shirt blanc → vert foncé)

| Essai | Résultat à l'œil | Ce qui a changé ensuite |
|---|---|---|
| 1 | bon dans l'ensemble, grosse tache sur une ombre du t-shirt | consigne de couleur réécrite (S-CM-01) |
| 2 | tache plus petite, toujours présente | ombrage repris de l'original par le code (S-LUM-03) |
| 3 | **pire** : taches noires pixelisées sur les zones éclairées, ombre non résolue ; l'application Photos de Windows n'ouvre pas un fichier | défaut de la recoloration reproduit et corrigé ; recoloration en simple variante à comparer ; copie JPEG des résultats |
| 4 (comparaison, 12 octobre) | **demande seule meilleure** : défauts de lumière avec le socle, absents sans ; résultats normaux bons ; variante recolorée laisse une trace ; Photos ouvre tout (le bug était ponctuel) | texte envoyé = ta demande seule par défaut ; recoloration désactivée ; taille de la photo écrite dans le rapport |

Comparaison du 12 octobre, même photo, mêmes trois graines **(F)** :

| Variante | Mots envoyés | Score par graine (plus bas = mieux) |
|---|---|---|
| demande seule | 20 | 1,70 · 1,27 · 1,38 |
| demande + 3 principes (socle limité à 80 mots) | 102 | 1,94 · 1,48 · 1,58 |
| demande + tout le socle | 498 | 2,65 · 1,81 · 1,91 |

Ton œil et les mesures donnent le même ordre sur les trois graines : plus le texte est
long, plus il y a de défauts. Portée : une photo, un changement de couleur **(E pour
les autres types)**. Le socle reste dans le code (verrou, grain, contrôles) et dans la
commande « comparer », pour tester les autres types de demande avant de conclure.

Mesures : 61 à 95 s par photo pour 3 candidats selon la longueur du texte ; zone modifiée
plus nette que le reste (×1,9 à ×2,2) et un peu plus bruitée (×1,2 à ×1,3), jugée bonne à
l'œil. La photo fait environ 1 Mpx (aucun candidat redimensionné) : l'écart ne vient pas
d'un agrandissement ; le modèle rend plus net qu'une photo de téléphone compressée **(E)**.

### Socle réécrit d'après les consignes officielles (12 octobre 2026)

Socle en positif, budget de 80 mots par priorité, conseils sur les lignes négatives,
commande « comparer » ([audit des sources](SOURCES_EXTERNES.md)). Rien de cela n'a encore
tourné sur ta machine.

### Ce que j'attends de toi

1. ~~Lancer `windows\installer.bat`, puis `windows\diagnostic.bat`.~~ Fait.
2. ~~M'envoyer `boite\diagnostic\diagnostic.md`.~~ Fait.
3. ~~Premier essai réel~~ : fait (t-shirt, trois essais).
4. ~~Comparaison sur la photo du t-shirt~~ : fait, demande seule retenue.
5. Prochain essai : un autre type de demande (volume, remplacement d'objet) dans
   `boite\comparer\`, pour vérifier que la conclusion tient hors changement de couleur.

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
- [x] **Texte envoyé au modèle** : ta demande seule (comparaison du 12 octobre). Le
  budget de 80 mots et l'en-tête court ne servent plus qu'avec `socle_actif: true`.
- [x] **Recoloration** : désactivée (traces visibles sur les essais 3 et 4).
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
