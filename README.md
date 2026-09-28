# Application Streamlit — CSV SEMG vers FEC de reprise, version 2

## Mise à jour
Remplacer app.py et converter.py dans le dépôt GitHub existant. Garder requirements.txt. Streamlit redéploie après le commit.

## Déploiement initial
Déposer app.py, converter.py, requirements.txt à la racine du dépôt. Sur https://share.streamlit.io choisir le dépôt, main, app.py. Dans Advanced settings sélectionner Python 3.12.

## Fonctionnement
Déposer le CSV, choisir la période, télécharger le TXT ou le ZIP de contrôles. Aucune correction manuelle des comptes scientifiques n'est imposée.

- Comptes alphanumériques acceptés, y compris avec un préfixe alphabétique.
- Longueur maximale de 10 caractères par défaut, réglable de 6 à 20.
- Comptes courts conservés. Comptes longs ou comportant des caractères spéciaux : trois premiers caractères alphanumériques puis suffixe unique. Collisions contrôlées, y compris avec les comptes conservés.
- Comptes scientifiques : conservation du préfixe numérique de trois caractères puis suffixe unique par couple compte source/libellé. Ce sont des codes de reprise, pas les numéros historiques retrouvés. Deux comptes déjà confondus sous le même couple dans le CSV ne peuvent pas être distingués.
- Correspondance complète téléchargeable, incluse au ZIP. Elle est construite sur tout le fichier avant filtrage de période.
- Regroupement journal/date/pièce ; regroupement journal/date activé par défaut lorsque les pièces sont déséquilibrées. À-nouveaux regroupés par journal/date. Toutes les lignes détaillées restent conservées.
- Montants exacts, contrôles d'équilibre, aucune suppression automatique de lignes.

## Limites
Fichier de reprise à 18 colonnes, UTF-8, tabulations, dates AAAAMMJJ. Ce n'est pas un FEC fiscal natif : numéros d'écriture reconstitués, ValidDate vide faute de donnée, auxiliaires non déduits, références de pièces vides conservées si aucun document n'est disponible. L'acceptation finale dépend des paramètres de l'importateur ACD.

## Confidentialité
Le CSV est traité en mémoire sur le serveur Streamlit Cloud, pas uniquement dans le navigateur. Le code ne l'écrit pas sur disque et ne le met pas en cache partagé. Aucun fichier client n'est inclus dans cette archive de code.

## Vérifications
7 tests moteur réussis. Conversion complète du fichier SEMG fourni : 57 692 lignes conservées, débit et crédit 39 375 259,42 €, écart nul, comptes de 10 caractères maximum. Interface Streamlit non exécutée dans l'environnement de préparation.
