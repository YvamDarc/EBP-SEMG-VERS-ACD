import io
import json
import zipfile
from datetime import datetime
import streamlit as st
from converter import read_csv, automatic_accounts, convert, csv_bytes, FIELDS, date

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
