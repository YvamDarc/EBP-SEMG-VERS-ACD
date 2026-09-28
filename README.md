# Moulinette CSV SEMG → FEC de reprise

## Utilisation sans installation sur votre ordinateur
1. Créer un dépôt GitHub et y déposer uniquement `app.py`, `converter.py`, `requirements.txt` et ce README, à la racine.
2. Sur https://share.streamlit.io créer une application, sélectionner ce dépôt et `app.py` comme fichier principal. Choisir Python 3.12 dans les paramètres avancés.
3. Ouvrir l'adresse de l'application puis déposer le CSV. Aucun compte ChatGPT n'est nécessaire pour utiliser l'application.
4. Vérifier la période. Les bornes sont inclusives, aucun filtrage sur le statut n'est effectué.
5. Corriger les comptes scientifiques depuis une source fiable ou déposer un nouvel export qui conserve les comptes sous forme de texte. La correspondance utilise **compte source + libellé**, car plusieurs tiers peuvent partager la même valeur scientifique arrondie. Ne pas transformer simplement `4,01E+11` en `401000000000` : cela ne restitue pas les chiffres perdus.
6. Examiner les regroupements, autoriser si approprié le regroupement par journal/date, puis télécharger le TXT et les contrôles.

Les fichiers privés du dossier `diagnostic_prive` accompagnant cette livraison ne doivent PAS être déposés dans GitHub.

## Portée
18 champs FEC, séparateur tabulation, UTF-8, dates AAAAMMJJ, montants exacts à deux décimales avec virgule. Tous les champs de l'export utilisés sont lus en texte. Pas de suppression des lignes nulles, de compensation, d'arrondi, de compte d'attente ni de dédoublonnage automatique.

Numéro d'écriture original absent : identifiants R0000001… reconstruits, triés par date et journal. Regroupement journal/date/pièce si chaque groupe est équilibré ; sinon blocage ou regroupement journal/date après accord. À-nouveaux : un groupe par journal/date conservant chaque ligne détaillée. Cette reconstruction ne prouve pas la structure des écritures historiques.

Date de validation absente : ValidDate vide, jamais remplacée arbitrairement par Date. Statuts 1 et 3 conservés. Auxiliaires laissés vides car aucune colonne auxiliaire distincte n'est fournie. CompteNum conserve le compte source ou sa correction explicite. Pièce vide : Document utilisé s'il existe, sinon référence vide signalée dans les contrôles. Les devises restent vides, faute de données. Aucun document joint n'est recréé.

Ce fichier de reprise n'est pas un FEC fiscal certifié. Certains importateurs peuvent refuser les ValidDate ou PieceRef vides ; adapter le processus de reprise dans le logiciel destinataire, sans inventer de dates historiques. Demander le FEC natif au logiciel d'origine pour une remise fiscale.

## Confidentialité
Streamlit Cloud traite le fichier sur son serveur, pas uniquement dans le navigateur. Le code ne stocke aucun CSV sur disque, ne journalise pas son contenu, ne fait aucun appel à un service tiers et n'utilise pas de cache partagé. Les données restent en mémoire pendant la session. Vérifier les conditions de l'hébergeur pour un déploiement cabinet.

## Références
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://bofip.impots.gouv.fr/bofip/9028-PGP.html/identifiant=BOI-CF-IOR-60-40-20-20170607

## Vérification du moteur
`python -m unittest discover -s tests` (tests synthétiques sans données client).
