# Version 3 — Application autonome, sans converter.py
"""Conversion de reprise : aucun numéro de compte n'est deviné."""
import csv
import io
import re
import hashlib
import unicodedata
from collections import defaultdict, Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

FIELDS = 'JournalCode JournalLib EcritureNum EcritureDate CompteNum CompteLib CompAuxNum CompAuxLib PieceRef PieceDate EcritureLib Debit Credit EcritureLet DateLet ValidDate Montantdevise Idevise'.split()
SCI = re.compile(r'^[+-]?[\d.,]+[eE][+-]?\d+$')
REQUIRED = ['Code journal', 'Description du journal', 'Date', 'N° de compte', 'Intitulé du compte', 'Pièce', 'Date de pièce', 'Libellé', 'Débit', 'Crédit', 'Lettrage', 'Date de lettrage']

def read_csv(raw):
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    else:
        raise ValueError('Encodage non reconnu : réexporter en UTF-8 ou Windows-1252.')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    missing = set(REQUIRED) - set(reader.fieldnames or [])
    if missing:
        raise ValueError('Colonnes absentes : ' + ', '.join(sorted(missing)))
    rows = []
    for n, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'Ligne {n} : nombre de colonnes incorrect.')
        row = {k: v.strip() for k, v in row.items()}
        row['_line'] = n
        rows.append(row)
    if not rows:
        raise ValueError('Fichier vide.')
    return rows, encoding

def date(s, optional=False):
    if not s and optional:
        return ''
    for fmt in ('%d/%m/%Y', '%Y%m%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y%m%d')
        except ValueError:
            pass
    raise ValueError('Date invalide : ' + repr(s))

def amount(s):
    try:
        d = Decimal(s.replace('\u00a0', '').replace('\u202f', '').replace(' ', '').replace(',', '.'))
        if not d.is_finite() or d != d.quantize(Decimal('.01')):
            raise ValueError('Montant non fini ou comportant plus de deux décimales : ' + s)
        return d
    except InvalidOperation as exc:
        raise ValueError('Montant invalide : ' + repr(s)) from exc

def money(d):
    return format(d, '.2f').replace('.', ',')

def csv_bytes(rows, fields, delimiter=';'):
    f = io.StringIO(newline='')
    w = csv.DictWriter(f, fieldnames=fields, delimiter=delimiter, lineterminator='\r\n', extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    return f.getvalue().encode('utf-8-sig' if delimiter == ';' else 'utf-8')

def account_template(rows):
    counts = Counter((r['N° de compte'], r['Intitulé du compte']) for r in rows if SCI.fullmatch(r['N° de compte']))
    return [{'CompteSource': a, 'LibelleSource': b, 'CompteCorrige': '', 'NbLignes': n} for (a, b), n in sorted(counts.items())]

def automatic_accounts(rows, max_length=10):
    """Codes de reprise déterministes, sans fusion entre identités distinctes."""
    if not 6 <= max_length <= 20:
        raise ValueError('Longueur des comptes : de 6 à 20 caractères.')
    def clean(s):
        return re.sub('[^A-Za-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode())
    def identity(r):
        a = r['N° de compte']
        return (a, r['Intitulé du compte'] if SCI.fullmatch(a) else '')
    identities = sorted({identity(r) for r in rows})
    assigned = {}
    used = set()
    # Réserver d'abord tous les comptes déjà utilisables.
    for key in identities:
        a = key[0]
        if re.fullmatch('[A-Za-z0-9]+', a) and len(a) <= max_length and not SCI.fullmatch(a) and a.upper() not in used:
            assigned[key] = a
            used.add(a.upper())
    for key in identities:
        if key in assigned:
            continue
        a = key[0]
        base = clean(a)
        if SCI.fullmatch(a):
            # Le développement ne sert qu'à conserver le préfixe comptable.
            base = format(Decimal(a.replace(',', '.')), 'f').split('.')[0]
        prefix = (base[:3] or 'TMP')
        salt = 0
        while True:
            digest = hashlib.sha256((repr(key) + ':' + str(salt)).encode()).hexdigest().upper()
            candidate = prefix + 'X' + digest[:max_length-len(prefix)-1]
            if candidate.upper() not in used:
                break
            salt += 1
        assigned[key] = candidate
        used.add(candidate.upper())
    mapping = {}
    report = []
    seen = set()
    for r in rows:
        pair = (r['N° de compte'], r['Intitulé du compte'])
        target = assigned[identity(r)]
        mapping[pair] = target
        if pair not in seen:
            reason = 'Code provisoire : source scientifique' if SCI.fullmatch(pair[0]) else ('Compte raccourci/nettoyé' if target != pair[0] else 'Conservé')
            report.append({'CompteSource': pair[0], 'LibelleSource': pair[1], 'CompteSortie': target, 'Traitement': reason})
            seen.add(pair)
    return mapping, report

def read_mapping(raw):
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    if not {'CompteSource', 'LibelleSource', 'CompteCorrige'} <= set(reader.fieldnames or []):
        raise ValueError('Correspondance : colonnes CompteSource, LibelleSource, CompteCorrige requises.')
    result = {}
    for row in reader:
        key = (row['CompteSource'].strip(), row['LibelleSource'].strip())
        value = (row['CompteCorrige'] or '').strip()
        if key in result and result[key] != value:
            raise ValueError('Correspondance contradictoire : ' + str(key))
        if value:
            result[key] = value
    return result

def convert(rows, mapping=None, start=None, end=None, daily_fallback=False):
    mapping = mapping or {}
    out, trace, errors, warnings = [], [], [], []
    days = defaultdict(list)
    selected = 0
    for r in rows:
        n = r['_line']
        try:
            dt = date(r['Date'])
            if (start and dt < start) or (end and dt > end):
                continue
            selected += 1
            if r.get('Date au format L47') and date(r['Date au format L47']) != dt:
                raise ValueError('Les deux dates comptables divergent.')
            account = mapping.get((r['N° de compte'], r['Intitulé du compte']), r['N° de compte'])
            if SCI.fullmatch(account):
                raise ValueError('Compte scientifique à corriger depuis le logiciel source : ' + account)
            if not re.fullmatch(r'[A-Za-z0-9]+', account):
                raise ValueError('Compte non exploitable : ' + account)
            debit, credit = amount(r['Débit']), amount(r['Crédit'])
            if debit < 0 or credit < 0:
                raise ValueError('Montant négatif : corriger le sens dans la source.')
            if debit and credit:
                raise ValueError('Débit et crédit simultanés.')
            for key in ('Code journal', 'Description du journal', 'Intitulé du compte', 'Libellé'):
                if not r[key]:
                    raise ValueError('Champ vide : ' + key)
            item = dict(zip(FIELDS, [r['Code journal'], r['Description du journal'], '', dt, account, r['Intitulé du compte'], '', '', r['Pièce'] or r.get('Document', ''), date(r['Date de pièce']), r['Libellé'], money(debit), money(credit), r['Lettrage'], date(r['Date de lettrage'], True), '', '', '']))
            if any(any(c in value for c in '\t\r\n') for value in item.values()):
                raise ValueError('Tabulation ou retour à la ligne dans un champ : corriger la source.')
            days[(dt, r['Code journal'])].append((r, item, debit-credit))
        except ValueError as exc:
            errors.append({'LigneSource': n, 'Erreur': str(exc)})
    if errors:
        return [], [], errors, [], {'lignes_selectionnees': selected}
    grouped = []
    fallback_days = 0
    for key, values in sorted(days.items()):
        if key[1] == '[AN]':
            candidates = [values]
        else:
            pieces = defaultdict(list)
            for v in values:
                pieces[v[1]['PieceRef']].append(v)
            candidates = list(pieces.values())
            if any(sum(v[2] for v in group) for group in candidates):
                if not daily_fallback:
                    errors.append({'LigneSource': '', 'Erreur': f'{key} : regroupement par pièce déséquilibré. Vérifier puis autoriser le regroupement journal/date.'})
                    continue
                candidates = [values]
                fallback_days += 1
        for group in candidates:
            balance = sum(v[2] for v in group)
            if balance:
                errors.append({'LigneSource': '', 'Erreur': f'{key} : écart débit/crédit {money(balance)}.'})
            grouped.append(group)
    for num, group in enumerate(grouped, 1):
        for r, item, _ in group:
            item['EcritureNum'] = f'R{num:07d}'
            out.append(item)
            trace.append({'LigneSource': r['_line'], 'EcritureNum': item['EcritureNum'], 'CompteSource': r['N° de compte'], 'CompteSortie': item['CompteNum'], 'StatutSource': r.get('Statut', ''), 'DocumentSource': r.get('Document', ''), 'IdLigneSource': r.get('N° de ligne pour les documents associés', '')})
    warnings = ['Numéros de reprise reconstitués ; numéros originaux absents.', 'ValidDate laissée vide : date de validation absente de la source.', 'Comptes auxiliaires non déduits ; comptes sources conservés ou remplacés selon la correspondance.', 'Toutes les lignes et tous les statuts sélectionnés sont conservés, sans dédoublonnage.', f'{fallback_days} regroupements journal/date remplacent des groupes par pièce déséquilibrés.']
    total_d = sum(amount(r['Debit']) for r in out)
    total_c = sum(amount(r['Credit']) for r in out)
    stats = {'lignes_source': len(rows), 'lignes_selectionnees': selected, 'lignes_export': len(out), 'ecritures_reconstituees': len(grouped), 'debit': money(total_d), 'credit': money(total_c), 'ecart': money(total_d-total_c), 'regroupements_jour': fallback_days, 'pieces_vides': sum(not r['PieceRef'] for r in out)}
    if len(out) != selected:
        errors.append({'LigneSource': '', 'Erreur': 'Nombre de lignes exportées incohérent.'})
    return out, trace, errors, warnings, stats


def main():
    import io
    import json
    import zipfile
    from datetime import datetime
    import streamlit as st

    st.set_page_config(page_title='CSV → FEC de reprise', page_icon='📒', layout='wide')
    st.title('CSV comptable → FEC de reprise')
    st.caption('Export SEMG • 18 colonnes • contrôle des montants • correspondance des comptes')
    st.info('Fichier destiné à une reprise comptable. Les numéros d’écriture sont reconstitués et la date de validation reste vide. Ce fichier ne remplace pas un FEC fiscal issu du logiciel source.')
    st.caption('Sur Streamlit Cloud, les fichiers sont transmis au serveur pour le traitement en mémoire. Cette application ne les écrit pas sur disque et ne les met pas en cache partagé.')
    upload = st.file_uploader('1. Déposer le CSV comptable (séparateur point-virgule)', type=['csv'])
    if upload is None:
        st.stop()
    try:
        rows, encoding = read_csv(upload.getvalue())
        dates = [date(r['Date']) for r in rows]
    except (ValueError, UnicodeError) as exc:
        st.error(str(exc))
        st.stop()
    st.write(f'{len(rows):,} lignes · encodage {encoding} · du {min(dates)} au {max(dates)}')
    c1, c2 = st.columns(2)
    start = c1.date_input('Du (inclus)', datetime.strptime(min(dates), '%Y%m%d').date())
    end = c2.date_input('Au (inclus)', datetime.strptime(max(dates), '%Y%m%d').date())
    if start > end:
        st.error('La date de début doit précéder la date de fin.')
        st.stop()
    selected = [r for r, d in zip(rows, dates) if start.strftime('%Y%m%d') <= d <= end.strftime('%Y%m%d')]
    st.subheader('2. Raccourcir les comptes automatiquement')
    length = st.number_input('Longueur maximale des comptes', min_value=6, max_value=20, value=10, step=1)
    mapping, correspondence = automatic_accounts(rows, int(length))
    changed = [r for r in correspondence if r['CompteSource'] != r['CompteSortie']]
    st.success(f'{len(changed)} correspondances adaptées. Comptes alphanumériques acceptés.')
    st.caption('Les comptes longs conservent leur préfixe et reçoivent un suffixe unique. Les comptes scientifiques reçoivent un code de reprise par couple compte/libellé ; les chiffres perdus ne sont pas reconstitués.')
    with st.expander('Voir les correspondances de comptes'):
        st.dataframe(changed, use_container_width=True)
    correspondence_bytes = csv_bytes(correspondence, ['CompteSource', 'LibelleSource', 'CompteSortie', 'Traitement'])
    st.download_button('Télécharger les correspondances', correspondence_bytes, 'correspondance_comptes.csv', 'text/csv')
    st.subheader('3. Reconstruire les écritures')
    st.write('Regroupement par journal, date et pièce. Les à-nouveaux sont regroupés par journal et date. Les références de pièces restent conservées ligne par ligne.')
    fallback = st.checkbox('Regrouper par journal/date lorsque les pièces ne permettent pas de reconstruire des écritures équilibrées', value=True)
    out, trace, errors, warnings, stats = convert(rows, mapping, start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), fallback)
    st.json(stats)
    if errors:
        st.error(f'{len(errors)} anomalies bloquent la génération. Aucune ligne ne sera ignorée silencieusement.')
        st.dataframe(errors[:200], use_container_width=True)
        st.download_button('Télécharger toutes les anomalies', csv_bytes(errors, ['LigneSource', 'Erreur']), 'anomalies.csv', 'text/csv')
        st.stop()
    for warning in warnings:
        st.caption(warning)
    if not out:
        st.warning('Aucune ligne dans cette période.')
        st.stop()
    st.dataframe(out[:100], use_container_width=True)
    fec = csv_bytes(out, FIELDS, '\t')
    st.download_button('Télécharger le FEC de reprise (.txt)', fec, 'REPRISE_FEC_' + end.strftime('%Y%m%d') + '.txt', 'text/plain')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('REPRISE_FEC.txt', fec)
        z.writestr('correspondance_comptes.csv', correspondence_bytes)
        z.writestr('tracabilite.csv', csv_bytes(trace, list(trace[0])))
        z.writestr('controle.json', json.dumps({'controles': stats, 'limites': warnings}, ensure_ascii=False, indent=2))
    st.download_button('Télécharger le FEC + traçabilité + contrôles', buf.getvalue(), 'reprise_controles.zip', 'application/zip')


if __name__ == "__main__":
    main()
