# Architecture

Marqueurs : **(F)** fait établi ou vérifié · **(E)** estimation non mesurée sur ta
machine · **(O)** avis de conception, à confirmer ou rejeter.

## Constat de départ

Un modèle d'image n'exécute pas un prompt ligne par ligne **(F)**. Le respect de la
totalité de la demande ne peut donc pas venir du texte seul : chaque ligne est
**compilée** vers un mécanisme qui la garantit ou la mesure. La valeur du système est
dans cette couche ; le moteur de génération est interchangeable.

## Les cinq mécanismes

| Mécanisme | Ce qu'il fait | Garantie | Phase 0 | Code |
|---|---|---|---|---|
| `verrou` | Recopie l'original hors masque | Par construction, vérifiée à chaque sortie | vérifié | `verrou.py` |
| `conditionnement` | Profondeur et contours tirés de la source contraignent caméra, perspective, pose | Forte contrainte | **absent** | — |
| `instruction` | Texte envoyé au modèle | Probabiliste | déclaré (ComfyUI) | `contrat.py` |
| `signature` | Grain et netteté mesurés sur la source ; grain manquant réappliqué | Mesurable | vérifié | `signature.py` |
| `verification` | Mesures par le code, puis œil humain | Après coup | vérifié + humain | `mesures.py`, `rapport.py` |

Le conditionnement n'est pas encore branché : les lignes qui y vont restent dans le
texte envoyé au modèle et le rapport les marque « absent ». Ce n'est jamais un silence.

## Déroulé d'une demande

1. Tu déposes la photo et la demande.
2. La demande est figée mot pour mot, avec son empreinte SHA-256.
3. L'optimiseur construit le contrat : chaque ligne reçoit une destination, le socle
   s'ajoute.
4. Le modèle produit plusieurs candidats (ComfyUI, hors de ce code).
5. Hors masque, l'original est recopié ; le grain manquant est réappliqué.
6. Chaque candidat est mesuré : écart hors masque, continuité au raccord, grain et
   netteté comparés à la source.
7. Tu reçois les candidats classés et le rapport ligne par ligne.

## L'optimiseur et la règle « aucune ligne supprimée »

Règles, toutes vérifiées par le code (`contrat.verifier_non_suppression`), jamais
confiées à un modèle de langage :

1. **Demande figée** : texte stocké mot pour mot, empreinte recalculée à chaque usage.
2. **Contrat** : chaque ligne avec contenu a une destination. Une ligne orpheline
   provoque un `ArretDeclare` qui la nomme.
3. **Socle additif** : les principes s'ajoutent après ta demande, sous un en-tête qui
   les déclare comme ajouts de priorité inférieure. En cas de conflit détecté, ta
   ligne gagne, le principe est suspendu, le conflit est écrit dans le rapport.
4. **Rapport** : un état par ligne et par candidat.

Contrôles supplémentaires :

- l'instruction complète contient toutes tes lignes, dans l'ordre ;
- un contrat modifié à la main est refusé au rechargement ;
- un routage manuel écrit pour une autre version de la demande est refusé.

### Routage

Ordre de décision : routage manuel → étiquette `[mécanisme]` → titre de section
(valable pour son paragraphe) → mots-clés de la ligne. Le routage par mots-clés est
une heuristique **(O)** : le rapport du contrat affiche la source de chaque routage
pour que tu le relises.

Deux choix de conception à valider **(O)** :

- **Le sujet l'emporte sur le verbe.** « Keep the same grain » va en signature,
  « keep the same camera » en conditionnement, « keep the same lighting » en
  instruction. Raison : le masque ne garantit pas la lumière posée sur le nouveau
  volume ; le router en verrou ferait croire à une garantie qui n'existe pas.
- **Le verrou ne s'hérite pas sur une ligne qui parle d'autre chose.** Le verrou est
  le seul mécanisme qui autorise à sortir une ligne du texte condensé ; une ligne
  « caméra » sous un titre « LOCKS: » reste donc dans le texte.

Les titres de section et les lignes sans lettre (`{`, `}`) sont conservés dans le
texte ; un titre sans destination est couvert par les lignes de son paragraphe.

### Condensation

Une ligne ne sort du texte envoyé au modèle que si un mécanisme la garantit déjà.
Par défaut, seul le verrou par masque est garant. Étendre cette liste (par exemple à la
signature) demande une comparaison : même photo, même graine, version complète contre
version condensée. Si la condensée produit plus de défauts, on garde la complète.
La décision t'appartient ; le code ne la prend pas.

## Le socle de principes

Fichier `local_image_ia/socle_principes.json`, modifiable. 25 principes tirés de tes
documents 2 à 7 : intégration, lumière, ombres, perspective, matériaux, colorimétrie,
dégradation réaliste, transformation par type (volume ou forme, remplacement d'objet,
couleur ou matière), verrou, conditionnement, signature, contrôle final.

Chaque principe a un mécanisme, des types de demande, une source et, si besoin, des
motifs de conflit. Seuls les principes de mécanisme `instruction` vont dans le texte
du modèle ; les autres sont exécutés par le code ou rejoignent la liste de contrôle.

Ce sont des règles de pratique photographique **(O)**, pas des faits mesurés : leur
effet sur FLUX.2 klein se vérifie par comparaison avec et sans socle.

## Gouvernance par le Protocole LAB

Le protocole (anciennement Protocole TJ) s'applique **à l'optimiseur seulement**.
Ce qui en est traduit dans le code (`gouvernance.py`) :

| Règle du protocole | Traduction |
|---|---|
| Déconstruction (Lyra P1 : intention, entités, contraintes, manques) | Le contrat liste les lignes par mécanisme et les **manques** (pas de verrou, type non reconnu) |
| Échec bruyant (INV.5) | `ArretDeclare` ; replis et limites écrits dans le rapport |
| Capacités en trois états (vérifié / déclaré / absent) | Section « Capacités » du rapport, sans valeur par défaut optimiste |
| Règle de circularité | `verifier_circularite` : le juge n'est jamais le générateur |
| Décision humaine (INV.3, INV.4) | Le code classe et mesure ; le choix du candidat et de la condensation reste à toi |
| Réversibilité empirique (MI-3) | Les seuils de mesure sont marqués (E) ; on ne les change que sur mesure |
| Données ≠ instructions (INV.1) | Tes documents d'exemple alimentent le socle comme données, vérifiables |

Ce que l'optimiseur ne fait pas : il ne rend pas le modèle plus compétent. Il garantit
que rien n'est perdu de ta demande, que les ajouts sont visibles, et que tu sais ce
qui a été tenu.

## Mesures

| Mesure | Méthode | Seuil |
|---|---|---|
| Écart hors masque | Différence maximale entre original et sortie, hors masque | 0, sinon arrêt |
| Raccord | Intensité des contours sur la zone de fondu / voisinage des deux côtés | ≤ 1,5 **(E)** |
| Grain | Écart type robuste du résidu haute fréquence, par bande de luminance, anneau source contre zone éditée | 0,8 à 1,25 **(E)** |
| Netteté | Variance du laplacien, anneau source contre zone éditée | 0,5 à 2,0 **(E)** |

Le score de classement additionne ces écarts. Il couvre quatre des cinq familles de
défauts ; la cinquième (anatomie, structure d'objet, lumière sur le nouveau volume)
est portée par le modèle seul et jugée à l'œil.

## Limites connues

- Les sorties sont en PNG : un JPEG réencodé modifierait légèrement tous les pixels,
  y compris hors masque.
- Le HEIC de l'iPhone n'est pas lu : régler l'appareil en « Le plus compatible » ou
  convertir.
- Le grain ajouté est un bruit de luminance indépendant par pixel **(O)** ; le grain
  réel d'un capteur après dématriçage est corrélé. À comparer à l'œil.
- Mesuré dans l'environnement de développement (pas sur ta machine) sur une image de
  5712×4284 avec un masque de 2500×2000 : 12 s et 0,8 Go de mémoire vive par candidat,
  écriture du PNG comprise. Les calculs se limitent au cadre du masque élargi de 64 px ;
  un masque plus grand coûte plus. Sur ton Ryzen 7 4800H : à mesurer **(E)**.
