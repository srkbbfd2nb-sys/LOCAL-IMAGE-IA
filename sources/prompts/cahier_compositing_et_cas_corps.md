# Cahier des charges d'origine — protocole de compositing photoréaliste

Texte fourni par Lazerr le 7 octobre 2026 (sa demande d'origine à une autre IA),
conservé mot pour mot. C'est une **donnée de référence** : le socle de principes
(`local_image_ia/socle_principes.json`) en est tiré, il ne la remplace pas.

---

Dans un premier temps j'aimerais que tu mettes cette conversation à jour en analysant l'intégralité des fichiers disponible dans les fichiers du projet general. Ce sont les nouveaux documents du protocole. J'aimerais que tu les appliques à la conversation dans leurs intégralité de manière rigoureuse sans aucune omission. 

Ensuite après avoir appliqué cela et obtenu obligatoirement un résultat j'aimerais que à l'aide de ce même protocole et notamment de Lyra tu me construise un super prompt, qui a pour objectif de modifier à ma demande, selon mes critères une photo. Donc l'idée n'est pas simplement d'avoir un "prompt photoréaliste" ou un "super prompt" mais tout un protocole, tout un environnement de création et de travail et « protocole de compositing photoréaliste 

Les paramètres,structures et possibilités :

Analyse de l’image source
géométrie
sujet
environnement
lignes de fuite
horizon
surfaces
matériaux
objets secondaires
zones de contact
Caméra virtuelle
hauteur de caméra
azimut
inclinaison/pitch
roll
distance caméra-sujet
perspective
focale équivalente
format de capteur
angle de champ
projection
position du plan focal
Optique
profondeur de champ cohérente
bokeh
aberrations chromatiques discrètes
distorsion optique réaliste
vignettage
diffraction
netteté non uniforme
micro-contraste
comportement des hautes lumières
Lumière
source principale
direction
hauteur
taille apparente de la source
dureté/dispersion
température de couleur
lumière ambiante
lumière réfléchie
remplissage
contre-jour éventuel
occlusion ambiante
Ombres
direction
longueur
pénombre
densité
contact shadow
ombres projetées
ombres secondaires
interaction avec les surfaces
Perspective et géométrie
taille apparente
parallaxe
convergence
rapport sujet/arrière-plan
perspective atmosphérique
cohérence des plans
Intégration du sujet
contours
cheveux/fibres
semi-transparences
occlusions
contact avec le sol
déformations locales
interaction avec les objets
réflexion éventuelle
lumière de rebond
Matériaux et microstructure
peau
textile
métal
verre
plastique
bois
pierre
poussière
micro-rayures
pores
imperfections naturelles
Colorimétrie
exposition
balance des blancs
contraste
courbe tonale
saturation
luminance
température
teinte
réponse des couleurs
cohérence entre premier plan et arrière-plan
Pipeline photographique
RAW → développement → compositing → correction → export
espace colorimétrique
conservation des détails
tone mapping
compression finale

La gestion colorimétrique est importante : le principe consiste notamment à travailler dans un espace de travail cohérent avant de convertir vers l’espace de sortie. 

Texture photographique
grain dépendant de la luminance
bruit chromatique
bruit de lecture
micro-fluctuations
compression JPEG éventuelle
netteté naturelle
petites imperfections de capteur/objectif

Dégradation réaliste

C’est paradoxalement essentiel. Une image parfaitement propre et uniformément détaillée peut paraître moins photographique.

Contrôle de cohérence final

Importances du questionnement et des vérifications :

même perspective ?
même focale apparente ?
même direction lumineuse ?
mêmes températures de couleur ?
mêmes niveaux de contraste ?
ombres physiquement compatibles ?
profondeur de champ compatible ?
grain identique ?
netteté compatible ?
échelle correcte ?
contact physique crédible ?
aucune bordure de détourage ?
aucune texture « générée » incohérente ?

recommande d’utilisations des objets dynamiques et des masques pour conserver un workflow non destructif, et le flou d’objectif peut être utilisé pour rétablir une profondeur cohérente. 

Prompt modulaire qui peut être intéressant : 

[IMAGE SOURCE]

[ÉLÉMENT À MODIFIER]

[OBJECTIF DE LA RETOUCHE]

[CAMÉRA À CONSERVER]

[PERSPECTIVE]

[ÉCLAIRAGE]

[ENVIRONNEMENT]

[MATERIAUX]

[PHOTOGRAPHIC PIPELINE]

[INTEGRATION]

[COLOR SCIENCE]

[MICRO-DETAIL]

[IMPERFECTIONS]

[CONTRAINTES]

[NEGATIVE CONSTRAINTS]

[FINAL REALISM CHECK]

Je vais te fournir la photo qui va servir de référence à modifier et mes objectifs. Tu devra intégré le maximum d'éléments pertinent et fonctionnel pour un résultat complet, réaliste (c'est important il ne faut pas remarquer, au maximum les détails de l'IA).

Il faut aussi donc que tu adaptes les demande et la photo aux paramètres en y intégrant le plus possible pour rendre une photo la plus cohérente et réaliste. 

Il y a aussi un préparatif, ou plutôt un choix des photos qui peut rendre le résultat meilleur. Savoir quelle sont les type de photos, les lumières nécessaires, les qualités idéales pour retoucher de manière optimale les photos. Sachant que personnellement je prend les photos avec un iphone 16.

Très important aussi, la capacité à l'IA à identifié correctement ce que la photo représente, l'identité de la photo, les détails et l'intention de la photos, les parties du corps au plus précis et toutes autres paramètres. 

Donc l'objectif est de transformer le physique dans cette photo en un corps harmonieux, musclée, athlétiques, visibles, en ajoutant de l'épaisseur cohérente aux segments et aux muscles, rendre la photo homogènes avec les ajustements, aucune déformations mais plus arrangements, correction. La photo comporte des petits pièges, l'angle est inhabituel.
