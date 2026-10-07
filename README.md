# LOCAL-IMAGE-IA

Système local d'édition visuelle par IA. Tu déposes une photo et une demande écrite ;
après un temps de traitement, tu récupères la photo modifiée et un rapport qui dit,
ligne par ligne, ce qui a été tenu.

Ce dépôt contient la **couche de contrat, de verrous, d'optimiseur et de mesures**.
Elle tourne sur le processeur et ne dépend pas du GPU. Le moteur de génération
(ComfyUI + FLUX.2 klein 4B en phase 0) est une pièce interchangeable, utilisée à côté.

> **Ce que ce code garantit, et ce qu'il ne garantit pas.**
> Garanti par construction : aucune ligne de ta demande n'est perdue ni réécrite ;
> hors du masque, la photo est identique au pixel près (en PNG). Mesuré : grain,
> netteté, continuité au raccord. **Pas garanti** : l'anatomie, la lumière posée sur
> le nouveau volume, la justesse de la transformation. Ça reste le travail du modèle,
> et c'est ton œil qui juge.

## Installation (Windows 11)

```powershell
cd LOCAL-IMAGE-IA
py -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
pytest
```

Python 3.10 ou plus récent. Dépendances : numpy et Pillow.

## Utilisation en trois temps

### 1. Compiler la demande

Écris ta demande dans un fichier texte (UTF-8), puis :

```powershell
python -m local_image_ia compiler ma_demande.txt -o sortie
```

Le système fige ta demande (empreinte SHA-256), donne à chaque ligne un identifiant
et une destination parmi les cinq mécanismes, ajoute le socle de principes (étiqueté
comme ajout), et écrit dans `sortie/` :

| Fichier | Contenu |
|---|---|
| `instruction_complete.txt` | Le texte à coller dans ComfyUI : toutes tes lignes, dans l'ordre, puis le socle |
| `instruction_condensee.txt` | La même chose sans les lignes déjà garanties par le masque (à n'utiliser qu'après comparaison) |
| `rapport_contrat.md` | La destination de chaque ligne et la raison du routage. **Relis-le.** |
| `contrat.json` | Le contrat complet, réutilisé à l'étape 3 |

Si une ligne ne trouve aucune destination, la compilation **s'arrête** et nomme la
ligne. Tu la corriges en ajoutant une étiquette en tête de ligne :

```text
[instruction] Une BMW élégante, propre mais pas neuve.
[verrou] le panneau de sortie
```

Étiquettes possibles : `verrou`, `conditionnement`, `instruction`, `signature`,
`verification`. L'étiquette sert au routage ; elle est retirée du texte envoyé au
modèle, ta ligne ne l'est jamais.

### 2. Générer les candidats dans ComfyUI

Ouvre le workflow « Flux.2 [Klein] 4B Distilled: Image Edit », colle
`instruction_complete.txt`, et produis plusieurs candidats (graines différentes).
Enregistre-les en PNG.

Dessine aussi le **masque** : une image de la même taille que la photo, **blanc** sur
la zone à modifier, **noir** partout ailleurs. Tout ce qui est noir sera recopié de
l'original. N'importe quel logiciel de dessin convient (Paint, GIMP, Photopea).

### 3. Finaliser

```powershell
python -m local_image_ia finaliser --contrat sortie/contrat.json `
    --original photo.jpg --masque masque.png `
    --candidats c1.png c2.png c3.png -o sortie
```

Pour chaque candidat : remise à la taille de l'original, recopie de l'original hors
masque (avec un fondu entièrement **à l'intérieur** du masque), réapplication du grain
manquant, mesures. Sortie : `candidat_01.png`, `candidat_02.png`… et `rapport.md`.

Le rapport classe les candidats sur les défauts **mesurables** et donne, pour chaque
ligne de ta demande et du socle, un état par candidat :

| État | Signification |
|---|---|
| garantie | garantie par le code, écart hors masque mesuré à zéro |
| conforme / NON conforme | vérifiée par une mesure, dans ou hors des seuils |
| à l'œil | non vérifiable par le code : c'est toi qui juges |
| absent (phase 0) | mécanisme pas encore branché ; la ligne reste dans le texte du modèle |

Il finit par une liste de contrôle à cocher à l'œil.

## Commandes utiles

```powershell
python -m local_image_ia socle      # liste les principes du socle
python -m local_image_ia compiler ma_demande.txt --type volume_forme
python -m local_image_ia compiler ma_demande.txt --routage routage.json
```

Le fichier de routage manuel est lié à l'empreinte de la demande : si la demande
change, il est refusé (les numéros de ligne ont pu bouger).

```json
{"empreinte_sha256": "…", "lignes": {"L012": "instruction"}}
```

## Exemples

- `exemples/demande_corps.txt` : transformation corporelle (cas test), en anglais.
- `exemples/demande_voiture_fr.txt` : remplacement d'objet, en français.

Ces exemples sont **reconstruits à partir de la synthèse**, ce ne sont pas tes prompts
d'origine. Tes prompts restent la référence.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) : les cinq mécanismes, l'optimiseur,
  la règle de non-suppression, la gouvernance par le Protocole LAB.
- [docs/FEUILLE_DE_ROUTE.md](docs/FEUILLE_DE_ROUTE.md) : où en est la phase 0, ce qui
  reste ouvert.

## Données personnelles

Les photos et les sorties ne sont jamais versionnées (`.gitignore`). Le système
travaille sur tes propres images, ou sur celles de personnes qui ont donné leur accord.
