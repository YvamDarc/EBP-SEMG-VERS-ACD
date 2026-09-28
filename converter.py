"""Conversion de reprise : aucun numéro de compte n'est deviné."""
import csv
import io
import re
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
            if not re.fullmatch(r'[0-9]{3}[A-Za-z0-9]*', account):
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
    warnings = ['Numéros de reprise reconstitués ; numéros originaux absents.', 'ValidDate laissée vide : date de validation absente de la source.', 'Comptes auxiliaires non déduits ; comptes sources conservés ou corrigés explicitement.', 'Toutes les lignes et tous les statuts sélectionnés sont conservés, sans dédoublonnage.', f'{fallback_days} regroupements journal/date remplacent des groupes par pièce déséquilibrés.']
    total_d = sum(amount(r['Debit']) for r in out)
    total_c = sum(amount(r['Credit']) for r in out)
    stats = {'lignes_source': len(rows), 'lignes_selectionnees': selected, 'lignes_export': len(out), 'ecritures_reconstituees': len(grouped), 'debit': money(total_d), 'credit': money(total_c), 'ecart': money(total_d-total_c), 'regroupements_jour': fallback_days, 'pieces_vides': sum(not r['PieceRef'] for r in out)}
    if len(out) != selected:
        errors.append({'LigneSource': '', 'Erreur': 'Nombre de lignes exportées incohérent.'})
    return out, trace, errors, warnings, stats
