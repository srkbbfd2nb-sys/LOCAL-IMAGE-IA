# Sources

Documents fournis par Lazerr le 7 octobre 2026, conservés **mot pour mot** (fautes de
frappe comprises, par exemple « MAGE EDIT »). Ce sont des **données de référence** :
le socle de principes (`local_image_ia/socle_principes.json`) en est tiré et cite ses
sources fichier par fichier ; ces textes ne pilotent pas le code.

| Fichier | Contenu | Usage |
|---|---|---|
| `prompts/voiture_bmw_g70.txt` | remplacement d'une Peugeot par une BMW Série 7 G70, 12 points | principes `remplacement_objet`, test du routeur |
| `prompts/corps_condense_13_points.txt` | transformation corporelle condensée, avec « Not to much arms » et « Snapchat Quality » | cas test, principes `corps` |
| `prompts/corps_12_points_signature.txt` | transformation corporelle avec signature photographique et propreté technique | principes signature, conflit « Do NOT inject artificial noise » |
| `prompts/protocole_master_corps.txt` | protocole master en 30 sections | référence complète, principes `corps` et contrôle final |
| `prompts/selfie_reference_json.json` | reconstruction d'un selfie d'après référence, deux changements | mode `reference`, principes `couleur_matiere` |
| `prompts/cahier_compositing_et_cas_corps.md` | cahier des charges du protocole de compositing et prompt modulaire | modules du socle, guide de prise de vue |

Non conservé ici : la conversation sur le fine-tuning et les LoRA (document 1). Elle est
résumée dans la synthèse du 7 octobre ; ses affirmations non vérifiées y sont listées.

Le selfie JSON décrit une personne réelle : pour un service vendu, il faut son
consentement.

Vérification : chaque fichier compile sans arrêt (`python -m local_image_ia compiler
<fichier>`) ; les tests vérifient que les lignes-objectifs ne sont jamais routées en
verrou.
