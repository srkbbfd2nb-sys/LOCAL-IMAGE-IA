# Sources externes du socle

Audit du 12 octobre 2026 : ce que chaque source apporte au texte envoyé à FLUX.2 klein 4B,
ce qui en a été pris, et pourquoi le reste ne l'a pas été. Marqueurs : **(F)** fait
vérifié dans la source, **(E)** estimation, **(O)** opinion.

## 1. La source qui pèse le plus : Black Forest Labs, l'éditeur du modèle

Le modèle exécuté est FLUX.2 klein ; ce que son éditeur dit de la façon de lui écrire
prime sur les recueils de prompts écrits pour d'autres modèles **(O)**.

| Source | Ce qu'elle établit |
|---|---|
| [Guide de prompt FLUX.2](https://docs.bfl.ai/guides/prompting_guide_flux2) (écrit pour les versions pro et max) | structure Sujet + Action + Style + Contexte ; le début du texte pèse le plus ; 30 à 80 mots « habituellement idéal » **(F)** |
| [Aide BFL : FLUX.2 et les prompts négatifs](https://help.bfl.ai/articles/7734566352-does-flux-2-support-negative-prompting) | pas de prompt négatif : décrire ce que l'on veut voir **(F)** |
| [Guide de génération rapide de klein](https://help.bfl.ai/articles/8642316687-flux-2-klein-fast-generation-guide) | réglages et conseils propres à klein **(F)** |
| [`system_messages.py`, dépôt black-forest-labs/flux2](https://github.com/black-forest-labs/flux2/blob/main/src/flux2/system_messages.py) | prompt système officiel d'édition (`SYSTEM_MESSAGE_UPSAMPLING_I2I`) : une instruction de 50 à 80 mots ; « Specify what changes AND what stays the same » ; « Turn negatives into positives » ; « Make abstractions concrete » **(F)** |
| [Fiche du modèle FLUX.2 klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) | « Prompt following is heavily influenced by the prompting style » **(F)** |
| Code de ComfyUI (encodeur de texte de klein) | le texte est complété à 512 jetons et n'est pas coupé **(F)** ; un texte long se dilue au lieu d'être tronqué **(E)** |

**Ce qui a changé dans le système à partir de ces constats :**

1. Les 50 principes du socle (version 2026-10-12) sont tous écrits **en positif**. Un test
   l'impose (`test_socle_entierement_en_positif`).
2. **Budget** : le socle ajoute au plus 80 mots (`socle_mots_max`), par ordre de
   priorité (0 = intégrité de la photo, puis 1, 2, 3). Un principe hors budget reste dans
   le contrat, marqué « hors budget », et le rapport le dit.
3. **En-tête court** : « Additional principles: ». La méta-consigne sur la priorité
   n'apporte rien au modèle d'image ; l'étiquetage complet reste dans le contrat.
4. **Conseils de formulation** : les lignes de ta demande écrites en négatif sont
   signalées dans le rapport, avec une reformulation positive proposée. **Ta demande
   n'est jamais modifiée** : c'est toi qui décides de reformuler.
5. **Avertissement de longueur** au-delà de 80 mots, avec la référence BFL.
6. **Commande « comparer »** : pour mesurer, sur ta photo, ce que le socle apporte
   vraiment (voir le README).

## 2. Les cinq sources que tu as fournies

| Source | Licence | Écrite pour | Verdict | Ce qui est pris |
|---|---|---|---|---|
| [wuyoscar/GPT-Image2-Skill](https://github.com/wuyoscar/GPT-Image2-Skill) | MIT **(F)** | GPT Image 2 | utile en partie | ses « Realism Guidelines » : profondeur de champ d'un téléphone (S-REA-01), cheveux et peau réels (S-REA-02), réécrites pour klein, en positif et en peu de mots |
| [rockbenben/img-prompt](https://github.com/rockbenben/img-prompt) | MIT **(F)** | générateur de prompts, tous modèles | utile comme lexique | rien dans le texte envoyé ; ses catégories Photography, Light et Material (environ 5 000 termes au total) sont une réserve de vocabulaire pour de futurs principes ou styles |
| [EvoLinkAI/awesome-gpt-image-2-API-and-Prompts](https://github.com/EvoLinkAI/awesome-gpt-image-2-API-and-Prompts) | CC0 revendiqué **(F)**, mais prompts d'auteurs tiers | GPT Image 2 | peu pertinent | rien : surtout des prompts publicitaires ou créatifs, longs, pensés pour un autre modèle ; le droit de chaque prompt n'est pas établi |
| [YouMind-OpenLab/ai-image-prompts-skill](https://github.com/YouMind-OpenLab/ai-image-prompts-skill) | code MIT ; prompts « collectés dans la communauté » au droit flou **(F)** | Nano Banana et autres | peu pertinent | rien : prompts créatifs de génération, pas d'édition photo réaliste |
| [aipromptgenerator.art](https://www.aipromptgenerator.art/) | — | — | sans valeur pour le socle | rien : générateur de mots aléatoires, sans données ni règles exploitables |

Pourquoi si peu est pris **(O)** : un recueil de prompts pour GPT Image ou Nano Banana
apprend à décrire une image nouvelle et spectaculaire ; ton besoin est inverse (une
photo de téléphone modifiée sans que cela se voie). Ajouter ces formulations
allongerait le texte, que BFL recommande court, et pousserait vers un rendu
« publicitaire » que ton socle cherche justement à éviter. Le « coffre » qui compte est
dans la précision de quelques consignes positives bien placées, pas dans leur nombre.

## 3. Agrandir le spectre sans diluer le texte

Le spectre (nombre de situations couvertes) grandit dans le **socle**, pas dans le texte
envoyé : chaque principe a un type (corps, volume ou forme, remplacement d'objet,
couleur ou matière), un mode (édition, référence, création) et une priorité. Pour une
demande donnée, seuls les principes du bon type et du bon mode, non déjà dits par toi,
sont candidats, et le budget garde les plus importants. On peut donc ajouter des
principes (styles, objets, scènes) sans allonger le texte d'une demande qui ne les
concerne pas.

Prochaines étapes possibles, **à décider après la comparaison sur tes photos** :

- **Lexique img-prompt** (Photography, Light, Material) pour écrire les principes des
  futurs styles, avec attribution MIT.
- **Reformulation par un modèle de langage local** (« upsampling » dans le vocabulaire
  BFL), sur la base de `SYSTEM_MESSAGE_UPSAMPLING_I2I`. Pour respecter la règle de
  non-suppression, la reformulation serait placée **avant** tes lignes, qui resteraient
  mot pour mot. À mesurer : mémoire disponible (6 Go déjà pris par klein), temps, et
  apport réel à l'œil.

## 4. Ce qui reste incertain

- La plage de 30 à 80 mots vient du guide écrit pour FLUX.2 pro et max, et du prompt
  système d'édition. Pour klein 4B distillé, rien ne dit si un texte plus long dégrade
  le résultat sur une photo donnée **(E)**. C'est la raison d'être de la commande
  « comparer ».
- Les reformulations proposées pour les lignes négatives sont des suggestions de
  vocabulaire, choisies par motif ; certaines tomberont à côté. Le rapport les présente
  comme des propositions.
