# LOCAL-IMAGE-IA

Système local et automatique d'édition visuelle par IA. Tu déposes une demande
écrite, et une image si besoin (photo à modifier, ou image qui sert de modèle) ;
le système fait travailler le modèle, vérifie, et te rend le résultat avec un
rapport qui dit, ligne par ligne, ce qui a été tenu.

> **Ce qui est garanti, et ce qui ne l'est pas.**
> Garanti par le code : aucune ligne de ta demande n'est perdue ni réécrite ; en
> édition, tout ce que le modèle n'avait pas à changer est recopié de l'original au
> pixel près. Mesuré : raccords, grain, netteté, dérive de couleur. **Pas garanti** :
> l'anatomie, la lumière posée sur le nouveau volume, la justesse de la
> transformation. Ça reste le travail du modèle, et c'est ton œil qui juge.

## Installation sous Windows 11 (une seule fois)

Prérequis : carte NVIDIA à jour (pilote récent), environ 25 Go libres.

1. Télécharge ce dépôt (bouton **Code → Download ZIP** sur GitHub) et décompresse-le,
   par exemple dans `C:\LocalImageIA`.
2. Double-clic sur `windows\installer.bat`. Le script :
   - vérifie le pilote NVIDIA et l'espace disque ;
   - télécharge ComfyUI portable (archive officielle) dans `moteur\` ;
   - télécharge le modèle FLUX.2 klein 4B (Apache 2.0, environ 12,5 Go en trois fichiers),
     reprend les téléchargements interrompus, vérifie taille et empreinte SHA-256 ;
   - crée `boite\entree`, `boite\sortie`, `boite\archive` et `config.json`.
3. Double-clic sur `windows\diagnostic.bat` : il lance ComfyUI, fait deux créations et
   une édition, et écrit les durées dans `boite\diagnostic\diagnostic.md`. **Envoie-moi
   ce fichier** : ce sont les trois mesures de l'étape 1.

Les scripts Windows n'ont pas pu être exécutés dans mon environnement de travail (pas
de Windows) ; ils sont écrits sur les sources officielles vérifiées le 7 octobre 2026.
Si une étape échoue, le script s'arrête et dit pourquoi.

## Utilisation au quotidien

Double-clic sur `windows\demarrer.bat`, puis dépose tes fichiers dans `boite\entree\`.
Une tâche = des fichiers qui portent le même nom :

| Tu déposes | Mode | Ce que fait le système |
|---|---|---|
| `ma_photo.jpg` + `ma_photo.txt` | édition | modifie la photo selon la demande |
| `voiture.txt` + `voiture.ref.jpg` | référence | crée une image nouvelle en s'appuyant sur l'image modèle |
| `tasse.txt` seul | création | crée une image à partir du texte |

Options, toujours avec le même nom :

- `ma_photo.ref.jpg`, `ma_photo.ref2.jpg` : images de référence en plus (par exemple une
  photo de la vraie BMW pour un remplacement de voiture).
- `ma_photo.masque.png` : zone à modifier (blanc), si tu veux la fixer toi-même.
  Sinon, la zone est déduite automatiquement de ce que le modèle a changé.
- `ma_photo.protege.png` : zones à ne **jamais** toucher (blanc), par exemple le visage.

Le résultat arrive dans `boite\sortie\<date>_<nom>\` :

| Fichier | Contenu |
|---|---|
| `resultat.png` | le meilleur candidat selon les défauts mesurables (référence exacte) |
| `resultat.jpg` | la même image en JPEG, pour l'ouvrir ou la partager facilement |
| `resultat_recolore.png` | changement de couleur seulement : la variante avec l'ombrage de ta photo, à comparer |
| `candidat_01.png`, … | tous les candidats, verrouillés et corrigés |
| `masques\C1.png`, … | la zone prise du modèle (blanc) ; tout le noir est l'original |
| `rapport.md` | classement, état de chaque ligne, liste de contrôle à l'œil, durées |
| `instruction_envoyee.txt` | le texte exact envoyé au modèle |
| `bruts\` | les sorties du modèle avant traitement |

Les fichiers déposés sont rangés dans `boite\archive\`.

### Comparer les textes envoyés au modèle

Dépose la même tâche dans `boite\comparer\` au lieu de `boite\entree\`. Le système la
traite trois fois avec **les mêmes graines**, en ne changeant que le texte envoyé :

| Variante | Texte envoyé |
|---|---|
| `demande_seule` | ta demande, rien d'autre |
| `socle_80` | ta demande + les principes prioritaires du socle (80 mots ajoutés au plus) |
| `socle_complet` | ta demande + tous les principes applicables |

Résultat dans `boite\sortie\<date>_<nom>_comparaison\` : `planche.jpg` (l'original puis
une colonne par variante, une ligne par graine), `rapport_comparaison.md` (mots envoyés,
mesures, case à cocher pour ton verdict) et un sous-dossier complet par variante. Compte
environ trois fois la durée d'une demande. Une variante dont le texte serait identique à
une autre n'est pas relancée. Si quelque chose bloque, un
`ERREUR.md` explique quoi et comment corriger, et la boîte continue avec les tâches
suivantes.

Les photos HEIC de l'iPhone ne sont pas lues : règle l'iPhone sur « Le plus
compatible » (voir [le guide de prise de vue](docs/GUIDE_PRISE_DE_VUE_IPHONE16.md)).

## Réglages (`config.json`)

| Réglage | Défaut | Rôle |
|---|---|---|
| `candidats` | 3 | nombre d'essais par demande (graines différentes) |
| `budget_s` | 300 | temps maximum visé par demande ; au-delà, plus de nouveau candidat (proposition, à confirmer par la mesure) |
| `preset` | `klein4b` | `klein4b` (distillé, 4 étapes) ou `klein4b_base` (plus lent, à installer à part) |
| `texte` | `complete` | `condensee` seulement après comparaison (voir docs) |
| `orphelines` | `instruction` | ligne qu'aucune règle ne classe : envoyée au modèle (`instruction`) ou arrêt (`arret`) |
| `socle_complet` | `false` | `true` répète aussi les principes que ta demande dit déjà |
| `socle_actif` | `true` | `false` : seule ta demande est envoyée au modèle |
| `socle_mots_max` | `80` | mots ajoutés par le socle au plus, par priorité ; `0` = sans limite (voir [les sources](docs/SOURCES_EXTERNES.md)) |
| `format_creation` | `portrait` | taille en mode création : `portrait`, `paysage`, `carre`, `vertical_9_16` |
| `graine` | `null` | fixer une graine pour reproduire un résultat |
| `recoloration` | `"comparer"` | changement de couleur : `"comparer"` donne `resultat.png` plus une variante `resultat_recolore.png` (ombres, plis et texture repris de ta photo) ; `"oui"` ou `"non"` une fois ton choix fait |

## Comment ta demande est traitée

1. **Figée** mot pour mot, avec une empreinte SHA-256.
2. **Compilée** : chaque ligne reçoit un des cinq mécanismes (verrou, conditionnement,
   instruction, signature, vérification). Une ligne qu'aucune règle ne classe va au
   modèle telle quelle, marquée « défaut ».
3. **Complétée** par le socle de principes (50 règles tirées de tes prompts et des
   consignes officielles de Black Forest Labs, écrites en positif, rangées selon ton
   prompt modulaire de [IMAGE SOURCE] à [FINAL REALISM CHECK]). Un principe que ta
   demande dit déjà n'est pas répété ; un principe que ta demande contredit est
   suspendu ; au-delà de 80 mots ajoutés, les principes de priorité plus faible restent
   de côté. Le rapport dit tout cela, et signale les lignes de ta demande écrites en
   négatif (FLUX.2 ne comprend pas « no blur ») avec une reformulation proposée : ta
   demande, elle, n'est jamais modifiée.
4. **Générée** : plusieurs candidats dans ComfyUI.
5. **Vérifiée et assemblée** (édition) : zone modifiée délimitée, dérive de couleur
   corrigée, original recopié autour, grain réappliqué si besoin, mesures, classement.

Détails : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · sources du socle :
[docs/SOURCES_EXTERNES.md](docs/SOURCES_EXTERNES.md) · suite du projet :
[docs/FEUILLE_DE_ROUTE.md](docs/FEUILLE_DE_ROUTE.md) · tes prompts d'origine :
[sources/](sources/).

## Pour développer (Linux, macOS ou Windows avec Python 3.10+)

```bash
pip install -e .[dev]
pytest                      # 67 tests, dont la chaîne automatique contre un faux ComfyUI
python -m local_image_ia compiler sources/prompts/voiture_bmw_g70.txt -o sortie
```

## Données personnelles

Les photos, sorties, modèles et réglages ne sont jamais versionnés (`.gitignore`). Le
système travaille sur tes propres images, ou sur celles de personnes qui ont donné
leur accord.
