from pathlib import Path
import unittest
import pandas as pd
from engine import Bank,Feeder,ModelError,annual,compare,validate_profile,candidates

D=Path(__file__).resolve().parents[1]/'sample_data'
class CheckPhysics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=Feeder(pd.read_csv(D/'nodes.csv'),pd.read_csv(D/'sections.csv'),'N0')
        cls.profiles=validate_profile(pd.read_csv(D/'profiles.csv'))
    def test_annual_profile(self):
        self.assertEqual(int(self.profiles.hours.sum()),8760)
        self.assertGreater(annual(self.f,self.profiles)['annual_kwh'],0)
    def test_voltage_flow(self):
        x=self.f.run(1.0)
        self.assertGreater(x['grid_current_a'],0)
        self.assertLess(x['min_pu'],1.0)
        self.assertGreater(x['loss_kw'],0)
        self.assertAlmostEqual(x['source_kw'],float(self.f.nodes.peak_kw.sum())+x['loss_kw'],places=4)
    def test_cap_saves_energy(self):
        x=compare(self.f,self.profiles,[Bank('N8',450,'fixed')])
        self.assertGreater(x['saved_kwh'],0)
        self.assertGreater(x['saved_pct'],0)
        self.assertLess(x['proposed']['annual_kwh'],x['base']['annual_kwh'])
    def test_downstream_only(self):
        old=self.f.run(1.0)
        new=self.f.run(1.0,[Bank('N15',300,'fixed')])
        oldlines={x['section_id']:x for x in old['lines']}
        newlines={x['section_id']:x for x in new['lines']}
        # S08 (branch ending N8) is not on capacitor's upstream path; its current is unchanged.
        self.assertAlmostEqual(newlines['S08']['current_a'],oldlines['S08']['current_a'],delta=0.25)
    def test_reject_multi_inbound(self):
        l=self.f.sections.copy()
        l.loc[len(l)] = {'section_id':'extra','from_node':'N12','to_node':'N8','length_km':.1,'r_ohm_per_km':.5,'x_ohm_per_km':.3,'ampacity_a':200}
        with self.assertRaisesRegex(ModelError,'Multiple incoming'):
            Feeder(self.f.nodes,l,'N0')
    def test_one_bank_ranking(self):
        res=candidates(self.f,self.profiles,sizes=(150,300),kind='fixed')
        self.assertTrue(bool(res.feasible.any()))
    def test_switched_off_light_load(self):
        old=self.f.run(.3)
        new=self.f.run(.3,[Bank('N8',600,'switched')],switch_threshold=.6)
        self.assertAlmostEqual(old['loss_kw'],new['loss_kw'],places=9)
    def test_zero_load_no_line_loss(self):
        x=self.f.run(0)
        self.assertAlmostEqual(x['loss_kw'],0,places=6)
if __name__=='__main__':unittest.main()
