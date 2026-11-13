import unittest
import json
import tempfile
from pathlib import Path
import pandas as pd
from engine import Bank, Feeder, ModelError, annual, candidates
from study import build_model, audit_gis, study_report


def records():
    return [dict(SectionID='S1',FromNode=0,ToNode=1,Len_KM=.5,NodeKVA=100,
                 CummLoad=200,capacity=200,resistance=.3,reactance=.4,conductor='DOG',
                 **{'CORE LOSS':.5,'COPPER LOSS':2}),
            dict(SectionID='S2',FromNode=1,ToNode=2,Len_KM=.5,NodeKVA=100,
                 CummLoad=100,capacity=200,resistance=.3,reactance=.4,conductor='DOG',
                 **{'CORE LOSS':.5,'COPPER LOSS':2})]


class StudyChecks(unittest.TestCase):
    def setUp(self):
        self.f,self.rows=build_model(records(),10,11,.9)
        self.profile=pd.DataFrame([dict(period='all',hours=8760,load_fraction=1)])

    def test_demand_allocation(self):
        self.assertAlmostEqual(self.f.nodes.peak_kw.sum(),3**.5*11*10*.9)

    def test_cumulative_load_must_match_topology(self):
        r=records();r[0]['CummLoad']=100
        with self.assertRaisesRegex(ModelError,'Cumulative'):build_model(r,10,11,.9)

    def test_duplicate_topology_rejected(self):
        r=records();r[1]['ToNode']=1
        with self.assertRaises(ModelError):build_model(r,10,11,.9)

    def test_nonfinite_inputs_rejected(self):
        r=records();r[0]['resistance']=float('inf')
        with self.assertRaises(ModelError):build_model(r,10,11,.9)
        with self.assertRaises(ModelError):self.f.run(banks=[Bank('1',float('nan'))])
        with self.assertRaises(ModelError):annual(self.f,pd.DataFrame([dict(period='bad',hours=float('inf'),load_fraction=1)]))

    def test_core_is_not_multiplied_by_loss_factor(self):
        report=study_report(self.f,self.rows,{'W6':10,'Z6':.6})
        self.assertAlmostEqual(report['corrected_legacy_annual_total_loss_kwh']-report['legacy_annual_total_loss_kwh'],8760*(1-.432))

    def test_eligible_sites_and_empty_selection(self):
        rank=candidates(self.f,self.profile,sizes=(10,),candidate_nodes=['2'])
        self.assertEqual(rank.node_id.tolist(),['2'])
        self.assertTrue(candidates(self.f,self.profile,candidate_nodes=[]).empty)
        with self.assertRaises(ModelError):candidates(self.f,self.profile,candidate_nodes=['missing'])

    def test_gis_missing_duplicate_length_and_conductor(self):
        features=[{'properties':{'SectionID':'S1','LengthKM':.6,'ConductorN':'RABBIT'}},
                  {'properties':{'SectionID':'extra','LengthKM':.1,'ConductorN':'DOG'}}]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'gis.json';p.write_text(json.dumps({'features':features}))
            qa=audit_gis(self.rows,p).set_index('section_id')
            self.assertIn('length differs',qa.loc['S1','reason'])
            self.assertIn('conductor differs',qa.loc['S1','reason'])
            self.assertEqual(qa.loc['S2','reason'],'missing GIS section')
            self.assertEqual(qa.loc['extra','reason'],'GIS section missing in study')
            features.append(features[0]);p.write_text(json.dumps({'features':features}))
            self.assertIn('duplicate',audit_gis(self.rows,p).iloc[0]['reason'])

    def test_no_bank_identity(self):
        self.assertAlmostEqual(self.f.run()['loss_kw'],self.f.run(banks=[])['loss_kw'],places=10)

    def test_only_upstream_reactive_compensation(self):
        # An ideal source isolates the unrelated lateral from voltage interactions.
        nodes=pd.DataFrame([dict(node_id='0',peak_kw=0,pf=1),dict(node_id='1',peak_kw=100,pf=.8),dict(node_id='2',peak_kw=100,pf=.8)])
        lines=pd.DataFrame([dict(section_id='A',from_node='0',to_node='1',length_km=1,r_ohm_per_km=.3,x_ohm_per_km=.4,ampacity_a=200),dict(section_id='B',from_node='0',to_node='2',length_km=1,r_ohm_per_km=.3,x_ohm_per_km=.4,ampacity_a=200)])
        f=Feeder(nodes,lines,'0');old={r['section_id']:r for r in f.run()['lines']};new={r['section_id']:r for r in f.run(banks=[Bank('1',50)])['lines']}
        self.assertLess(new['A']['loss_kw'],old['A']['loss_kw'])
        self.assertAlmostEqual(new['B']['loss_kw'],old['B']['loss_kw'],places=9)


if __name__=='__main__':unittest.main()
