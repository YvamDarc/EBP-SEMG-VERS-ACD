import unittest
from converter import convert, read_csv, csv_bytes, FIELDS, read_mapping, automatic_accounts

def row(account='401TEST', debit='10', credit='0', piece='P1', n=2):
    return {'Code journal':'AC', 'Description du journal':'Achats', 'Date':'01/01/2026', 'N° de compte':account, 'Intitulé du compte':'Tiers', 'Pièce':piece, 'Date de pièce':'01/01/2026', 'Libellé':'Facture', 'Débit':debit, 'Crédit':credit, 'Lettrage':'', 'Date de lettrage':'', '_line':n}

class TestConversion(unittest.TestCase):
    def test_automatic_shortening(self):
        rows=[row('411010E10390'),row('411010E10391'),row('4,01E+11'),row('4,01E+11'),row('CLIENTABC'),row('411ABC')]
        rows[3]['Intitulé du compte']='Autre tiers'
        mapping, report=automatic_accounts(rows)
        self.assertEqual(len(set(mapping.values())),6)
        self.assertTrue(all(len(a)<=10 and a.isalnum() for a in mapping.values()))
        self.assertEqual(mapping[('CLIENTABC','Tiers')],'CLIENTABC')
        self.assertEqual(mapping,automatic_accounts(list(reversed(rows)))[0])
        for r in rows:
            contra=row('601000','0','10')
            self.assertFalse(convert([r,contra],mapping)[2])
    def test_exact_and_schema(self):
        rows=[row(),row('601000','0','10',n=3)]
        out,trace,errors,_,stats=convert(rows)
        self.assertFalse(errors)
        self.assertEqual(stats['ecart'],'0,00')
        self.assertEqual(len(trace),2)
        self.assertEqual(list(out[0]),FIELDS)
        self.assertEqual(out[0]['ValidDate'],'')
        self.assertEqual(out[0]['EcritureNum'],out[1]['EcritureNum'])
    def test_scientific_blocked_then_mapping(self):
        rows=[row('4,01E+11'),row('601000','0','10')]
        self.assertTrue(convert(rows)[2])
        self.assertFalse(convert(rows,{('4,01E+11','Tiers'):'401EXACT'})[2])
    def test_fallback_explicit_and_balance(self):
        rows=[row(piece='A'),row('601000','0','10','B')]
        self.assertTrue(convert(rows)[2])
        self.assertFalse(convert(rows,daily_fallback=True)[2])
        rows[1]['Crédit']='9,99'
        self.assertTrue(convert(rows,daily_fallback=True)[2])
    def test_bad_amount_and_date(self):
        for key,value in [('Débit','0,001'),('Débit','NaN'),('Date','31/02/2026'),('Débit','-1')]:
            r=row(); r[key]=value
            self.assertTrue(convert([r])[2])
    def test_filter_boundaries_and_preserve_duplicates(self):
        rows=[row(),row('601000','0','10')]*2
        self.assertEqual(len(convert(rows,start='20260101',end='20260101')[0]),4)
        self.assertEqual(len(convert(rows,start='20260102')[0]),0)
    def test_mapping_conflict(self):
        with self.assertRaises(ValueError):
            read_mapping(b'CompteSource;LibelleSource;CompteCorrige\na;b;4011\na;b;4012\n')

if __name__=='__main__':
    unittest.main()
