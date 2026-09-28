import io
import json
import zipfile
from datetime import datetime
import streamlit as st
from converter import read_csv, read_mapping, account_template, convert, csv_bytes, FIELDS, date

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
template = account_template(selected)
mapping = {}
st.subheader('2. Vérifier les comptes')
if template:
    st.warning(f'{len(template)} couples compte/libellé en notation scientifique. Les chiffres perdus ne peuvent pas être retrouvés par un simple changement de format. Réexporter les comptes en texte depuis le logiciel source ou renseigner les comptes exacts ci-dessous.')
    fields = ['CompteSource', 'LibelleSource', 'CompteCorrige', 'NbLignes']
    st.download_button('Télécharger la liste à compléter', csv_bytes(template, fields), 'correspondance_comptes.csv', 'text/csv')
    mp = st.file_uploader('Réimporter la correspondance complétée (UTF-8, point-virgule)', type=['csv'], key='mapping')
    if mp:
        try:
            mapping = read_mapping(mp.getvalue())
        except (ValueError, UnicodeError) as exc:
            st.error(str(exc))
            st.stop()
    for t in template:
        t['CompteCorrige'] = mapping.get((t['CompteSource'], t['LibelleSource']), '')
    edited = st.data_editor(template, disabled=['CompteSource', 'LibelleSource', 'NbLignes'], hide_index=True, use_container_width=True, key=upload.name + str(start) + str(end))
    mapping = {(t['CompteSource'], t['LibelleSource']): t['CompteCorrige'].strip() for t in edited if t['CompteCorrige'] and t['CompteCorrige'].strip()}
    st.download_button('Sauvegarder la correspondance saisie', csv_bytes(edited, fields), 'correspondance_completee.csv', 'text/csv')
else:
    st.success('Aucun compte en notation scientifique dans la sélection.')
st.subheader('3. Reconstruire les écritures')
st.write('Regroupement par journal, date et pièce. Les à-nouveaux sont regroupés par journal et date. Les références de pièces restent conservées ligne par ligne.')
fallback = st.checkbox('Autoriser un regroupement journal/date lorsque les pièces ne permettent pas de reconstruire des écritures équilibrées')
ack = st.checkbox('Je confirme utiliser le résultat pour une reprise et avoir vérifié les comptes ainsi que les regroupements proposés')
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
st.download_button('Télécharger le FEC de reprise (.txt)', fec, 'REPRISE_FEC_' + end.strftime('%Y%m%d') + '.txt', 'text/plain', disabled=not ack)
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('REPRISE_FEC.txt', fec)
    z.writestr('tracabilite.csv', csv_bytes(trace, list(trace[0])))
    z.writestr('controle.json', json.dumps({'controles': stats, 'limites': warnings}, ensure_ascii=False, indent=2))
st.download_button('Télécharger le FEC + traçabilité + contrôles', buf.getvalue(), 'reprise_controles.zip', 'application/zip', disabled=not ack)
