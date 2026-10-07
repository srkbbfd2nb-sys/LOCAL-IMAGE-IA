# Architecture

Marqueurs : **(F)** fait établi ou vérifié · **(E)** estimation non mesurée sur ta
machine · **(O)** avis de conception, à confirmer ou rejeter.

## Constat de départ

Un modèle d'image n'exécute pas un prompt ligne par ligne **(F)**. Le respect de la
totalité de la demande ne peut donc pas venir du texte seul : chaque ligne est
**compilée** vers un mécanisme qui la garantit ou la mesure. La valeur du système est
dans cette couche ; le moteur de génération est interchangeable.

## Vue d'ensemble

```
boite/entree/  ──►  automate.py  ──►  contrat.py (optimiseur)  ──►  texte du modèle
  photo + demande        │                    │                          │
                         │                    └─► socle_principes.json   ▼
                         │                                         ComfyUI (API HTTP)
                         │                                         FLUX.2 klein 4B
                         ▼                                                │
                 pipeline.finaliser  ◄──────────── candidats bruts ◄──────┘
                 masque auto, dérive, verrou, grain, mesures
                         │
                         ▼
               boite/sortie/<date>_<nom>/  resultat.png + rapport.md
```

| Module | Rôle |
|---|---|
| `automate.py` | dossier surveillé, une tâche de bout en bout, budget de temps, diagnostic |
| `comfy.py` | client de l'API ComfyUI (routes vérifiées dans son `server.py`) |
| `workflows.py` | graphe FLUX.2 klein construit par le code, fidèle au modèle officiel |
| `demande.py`, `routage.py`, `contrat.py` | demande figée, routage, contrat, non-suppression |
| `socle.py`, `socle_principes.json` | principes ajoutés, conflits, couverture |
| `masque_auto.py` | zone modifiée déduite du candidat, dérive de couleur |
| `verrou.py`, `signature.py`, `mesures.py` | recopie de l'original, grain, mesures |
| `rapport.py` | rapport ligne par ligne |
| `gouvernance.py` | règles du Protocole LAB traduites en code |

## Les trois modes

| Mode | Déclencheur | Verrou | Classement |
|---|---|---|---|
| édition | une image à modifier | l'original est recopié hors de la zone modifiée | sur les défauts mesurables |
| référence | des images `.ref` seulement | aucun (image nouvelle) | aucun : ordre de génération, ton œil choisit |
| création | aucune image | aucun | aucun |

Hors édition, aucune ligne n'est garantie par le masque : rien ne sort du texte
condensé, et les principes propres à l'édition (verrou, grain, « smallest edit
region ») sont marqués « hors mode ».

## Les cinq mécanismes

| Mécanisme | Ce qu'il fait | Garantie | État | Code |
|---|---|---|---|---|
| `verrou` | Recopie l'original hors de la zone modifiée | Par construction, vérifiée à chaque sortie | vérifié | `verrou.py`, `masque_auto.py` |
| `conditionnement` | Profondeur et contours tirés de la source contraignent caméra, perspective, pose | Forte contrainte | **absent** | — |
| `instruction` | Texte envoyé au modèle | Probabiliste | vérifié (ComfyUI) | `contrat.py`, `workflows.py` |
| `signature` | Grain et netteté mesurés ; grain manquant réappliqué ; dérive de couleur corrigée | Mesurable | vérifié | `signature.py`, `masque_auto.py` |
| `verification` | Mesures par le code, puis œil humain | Après coup | vérifié + humain | `mesures.py`, `rapport.py` |

## La zone modifiée : masque automatique

Tu ne dessines pas de masque. Pour chaque candidat **(O : choix de conception)** :

1. Original et candidat sont réduits à 512 px de côté (plus robuste au bruit).
2. La **dérive de couleur** du modèle est estimée sur toute l'image (gain et décalage
   par canal, à partir de l'étendue entre 5e et 95e centiles, en écartant à chaque passe
   les pixels les plus modifiés).
3. Après correction, la différence est seuillée (au moins 12 niveaux sur 255, et au
   moins 6 écarts absolus médians au-dessus de la médiane) ; les points isolés sont
   retirés, les trous bouchés, une marge de 1,5 % est ajoutée.
4. La dérive est réestimée sur la zone stable seulement, puis appliquée au candidat.
5. Hors zone, l'original est recopié au pixel près ; le fondu reste à l'intérieur de
   la zone.

Limites déclarées :

- Ce masque protège tout ce que le modèle n'a pas voulu changer, **pas** une zone
  qu'il a changée à tort : un visage légèrement altéré fait partie de la différence.
  Parade : `ma_photo.protege.png`, ou plus tard une détection automatique du visage.
- Si le modèle a modifié plus de 60 % de l'image, le rapport prévient que le verrou
  protège peu.
- Un candidat sans modification nette est écarté (« rejeté ») du classement.
- Les seuils (12 niveaux, 6 MAD, 1,5 %) sont des estimations **(E)** à calibrer sur
  tes photos.

## Le moteur : FLUX.2 klein 4B dans ComfyUI

- Graphe identique au modèle officiel « Flux.2 [Klein] 4B Distilled: Image Edit »
  (vérifié dans le dépôt Comfy-Org/workflow_templates) : 4 étapes, cfg 1, euler,
  conditionnement négatif mis à zéro, références passées par `ReferenceLatent` **(F)**.
- Deux écarts déclarés **(O)** : réduction en `area` au lieu de `nearest-exact`
  (moins d'aliasing sur une photo de 24 Mpx), et `resolution_steps` à 16 pour que la
  sortie garde exactement la géométrie de l'image réduite (alignement au pixel du
  verrou).
- L'encodeur de texte de ComfyUI pour klein ne coupe pas le prompt
  (`max_length=99999999`, vérifié dans son code) **(F)** ; il complète à 512 jetons,
  ce qui suggère une longueur d'entraînement de cet ordre **(E)**. Au-delà, le risque
  est la dilution, pas la coupure : le rapport donne l'estimation en jetons.
- Le système vérifie avant chaque série (sonde) que les nœuds et les trois fichiers
  du modèle sont présents ; sinon, arrêt déclaré avec la marche à suivre.

## L'optimiseur et la règle « aucune ligne supprimée »

Règles vérifiées par le code (`contrat.verifier_non_suppression`), jamais confiées à
un modèle de langage :

1. **Demande figée** : texte stocké mot pour mot, empreinte recalculée à chaque usage.
2. **Contrat** : chaque ligne avec contenu a une destination. Par défaut, une ligne
   qu'aucune règle ne classe va en instruction, marquée « défaut » ; l'option
   `orphelines: "arret"` rétablit l'arrêt déclaré.
3. **Socle additif** : les principes s'ajoutent après ta demande, sous un en-tête qui
   les déclare comme ajouts de priorité inférieure, regroupés par module.
4. **Rapport** : un état par ligne et par candidat.

Contrôles supplémentaires : l'instruction complète contient toutes tes lignes dans
l'ordre ; un contrat modifié à la main est refusé ; un routage manuel écrit pour une
autre version de la demande est refusé.

### Routage

Ordre : routage manuel → étiquette `[mécanisme]` → titre de section → mots-clés de la
ligne → défaut (instruction). Le rapport du contrat affiche la source de chaque
routage.

Règles de prudence **(O)**, toutes dans le sens « ne jamais promettre à tort » :

- **Le sujet l'emporte sur le verbe.** « Keep the same grain » va en signature,
  « keep the same camera » en conditionnement, « keep the same lighting » en
  instruction (le masque ne garantit pas la lumière posée sur le nouveau volume).
- **Le verrou est réservé aux lignes pures.** Il faut un vocabulaire de verrou
  explicite (« LOCK », « VERROUS », « PROTECTION ») ou un verbe de conservation qui
  porte sur ce qui peut rester hors du masque (fond, visage, mains, murs, objets…), et
  rien d'autre à demander au modèle. « PRESERVE THE ORIGINAL PHOTOGRAPH », « Preserve
  the photographic character » ou « 12. IDENTITY: … No beautification » restent des
  instructions. Raison : le verrou est le seul mécanisme qui autorise à sortir une
  ligne du texte condensé.
- **Une ligne qui demande une transformation n'est jamais un verrou** (« REPLACE THE
  CAR, ORIGINAL PHOTO PRESERVED » est l'objectif).
- **Portée des titres** : un titre vaut pour sa section ; un titre de verrou ne
  s'hérite que dans son paragraphe ; « 6. SILHOUETTE: … » ou « GOAL: … » ouvrent leur
  propre section ; « 1. Preserve original identity » reste un élément de la liste
  au-dessus.
- **Un titre ne sort du texte condensé que si toutes ses lignes en sortent.**

Résultat mesuré sur tes cinq prompts : aucune ligne-objectif en verrou ; les verrous
retenus sont « BACKGROUND PROTECTION », « LOCK THE BACKGROUND », « Preserve the
person's identity completely », « - Background and environment: … » et équivalents.

### Condensation

Une ligne ne sort du texte envoyé au modèle que si un mécanisme la garantit déjà (par
défaut : le verrou). Étendre cette liste demande une comparaison : même photo, même
graine, version complète contre version condensée. La décision t'appartient.

## Le socle de principes

Fichier `local_image_ia/socle_principes.json`, modifiable, 47 principes tirés de tes
prompts (`sources/prompts/`). Chaque principe a :

- un **module** de ton prompt modulaire : IMAGE SOURCE, ELEMENT TO MODIFY, CAMERA TO
  PRESERVE, PERSPECTIVE, LIGHTING, ENVIRONMENT, MATERIALS, PHOTOGRAPHIC PIPELINE,
  INTEGRATION, COLOR SCIENCE, MICRO-DETAIL, IMPERFECTIONS, CONSTRAINTS, NEGATIVE
  CONSTRAINTS, FINAL REALISM CHECK ;
- un **mécanisme** (seuls les principes `instruction` vont dans le texte du modèle ;
  les autres sont exécutés par le code ou rejoignent la liste de contrôle) ;
- des **types** (`tous`, `corps`, `volume_forme`, `remplacement_objet`,
  `couleur_matiere`) et des **modes** ;
- sa **source** exacte (fichier et section) ;
- des motifs de **conflit** (ta ligne contredit le principe : il est suspendu) et de
  **couverture** (ta ligne dit déjà la même chose : il n'est pas répété).

Le type de demande est celui de la première ligne qui en nomme un (l'objectif).

Exemple mesuré : sur ton prompt « 13 points », 25 principes sont déjà couverts et 2
seulement sont ajoutés au texte du modèle (densité de micro-détail, aucun texte ni logo). Sur une demande
courte, tout le socle s'ajoute : c'est là que l'optimiseur apporte le plus.

### Conflit notable : le grain

Ton prompt « 12 points » dit : « Do NOT inject artificial noise … Noise and grain must
derive only from the scene and the source photograph's conditions. » La réapplication
du grain synthétise un bruit dont les statistiques viennent de la source : c'est un
conflit au sens strict. Ta ligne gagne : le principe S-SIG-01 est suspendu, le grain
est seulement mesuré, et le rapport le dit.

## Gouvernance par le Protocole LAB

Le protocole (anciennement Protocole TJ) s'applique **à l'optimiseur seulement**.

| Règle du protocole | Traduction dans le code |
|---|---|
| Lyra P1 : intention, entités, contraintes, **manques** | le contrat liste les lignes par mécanisme et les manques (pas de verrou, type non reconnu, prompt trop long) |
| Échec bruyant (INV.5) | `ArretDeclare` ; `ERREUR.md` par tâche ; replis et limites écrits dans le rapport |
| SONDE : capacités en trois états | section « Capacités » : vérifié / déclaré / absent, sans défaut optimiste ; la sonde ComfyUI vérifie nœuds et fichiers |
| Règle de circularité | `verifier_circularite` : le juge n'est jamais le générateur |
| Décision humaine (INV.3, INV.4) | le code classe et mesure ; le choix final, la condensation et la politique des lignes sans destination restent à toi |
| Réversibilité empirique (MI-3) | seuils marqués (E) ; on ne les change que sur mesure |
| Données ≠ instructions (INV.1) | tes prompts d'exemple alimentent le socle comme données ; ils ne pilotent pas le code |

Ce que l'optimiseur ne fait pas : il ne rend pas le modèle plus compétent.

## Mesures

| Mesure | Méthode | Seuil |
|---|---|---|
| Écart hors zone modifiée | différence maximale entre original et sortie | 0, sinon arrêt |
| Raccord | intensité des contours sur la zone de fondu / voisinage des deux côtés | ≤ 1,5 **(E)** |
| Grain | écart type robuste du résidu haute fréquence, par bande de luminance | 0,8 à 1,25 **(E)** |
| Netteté | variance du laplacien, anneau source contre zone éditée | 0,5 à 2,0 **(E)** |

Le score de classement additionne ces écarts. Il couvre quatre des cinq familles de
défauts ; la cinquième (anatomie, structure d'objet, lumière sur le nouveau volume)
est portée par le modèle seul et jugée à l'œil.

## Limites connues

- Sorties en PNG : un JPEG réencodé modifierait légèrement tous les pixels.
- HEIC non lu : régler l'iPhone en « Le plus compatible » ou convertir.
- Le modèle travaille à environ 1 Mpx ; sur une photo de 24 Mpx, la zone modifiée est
  agrandie et donc plus douce que le reste. La netteté est mesurée, pas corrigée.
- Grain ajouté : bruit de luminance indépendant par pixel **(O)** ; le grain réel d'un
  capteur est corrélé. À comparer à l'œil.
- Mesuré dans l'environnement de développement (pas sur ta machine), 5712×4284 avec une
  zone de 2500×2000 : 12 s et 0,8 Go par candidat pour le traitement par le code,
  génération non comprise.
