"""Import the supplied Mansoorabad study, audit GIS, and screen single-bank cases.

Installed kVA allocates an ASSUMED coincident demand, not measured node loads.
No input workbook is modified. GIS is read as EPSG:4326 GeoJSON exported by GDAL.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import openpyxl
import pandas as pd
from engine import Feeder, Bank, ModelError, annual, candidates, compare, validate_profile


REQUIRED = ['SectionID','FromNode','ToNode','Len_KM','NodeKVA','CummLoad',
            'capacity','resistance','reactance','conductor']


def build_model(records, current_a, voltage_kv, pf):
    """Reconstruct topology; allocate demand proportional to installed node kVA."""
    if not all(math.isfinite(float(v)) for v in [current_a,voltage_kv,pf]):
        raise ModelError('Non-finite source input')
    if current_a <= 0 or not 0 < pf <= 1:
        raise ModelError('Source current must be positive and PF in (0,1]')
    rows=pd.DataFrame(records)
    if set(REQUIRED)-set(rows):raise ModelError('Workbook columns do not match the Mansoorabad layout')
    for c in ['FromNode','ToNode']:
        rows[c]=rows[c].map(lambda v: str(int(v)) if isinstance(v,(int,float)) and math.isfinite(v) and int(v)==v else str(v).strip())
    for c in ['Len_KM','NodeKVA','CummLoad','capacity','resistance','reactance']:
        rows[c]=pd.to_numeric(rows[c],errors='coerce')
        if not rows[c].map(math.isfinite).all():raise ModelError(f'Invalid workbook {c}')
    if (rows.NodeKVA<0).any() or rows.NodeKVA.sum()<=0:raise ModelError('Invalid installed kVA')
    roots=set(rows.FromNode)-set(rows.ToNode)
    if len(roots)!=1:raise ModelError('Expected one source node')
    root=next(iter(roots))
    scale=math.sqrt(3)*voltage_kv*current_a/rows.NodeKVA.sum()
    loads=dict(zip(rows.ToNode,rows.NodeKVA*scale*pf))
    nodes=pd.DataFrame([{'node_id':n,'peak_kw':loads.get(n,0.),'pf':pf}
                        for n in sorted(set(rows.FromNode)|set(rows.ToNode))])
    sections=rows.rename(columns={'SectionID':'section_id','FromNode':'from_node',
        'ToNode':'to_node','Len_KM':'length_km','resistance':'r_ohm_per_km',
        'reactance':'x_ohm_per_km','capacity':'ampacity_a'})
    feeder=Feeder(nodes,sections,root,voltage_kv)
    # Independently check that the study cumulative kVA agrees with the tree.
    cumulative={n:float(rows.loc[rows.ToNode==n,'NodeKVA'].sum()) for n in feeder.order}
    for n in feeder.order[:0:-1]:
        cumulative[feeder.lines_by_child[n]['from_node']]+=cumulative[n]
    for r in rows.to_dict('records'):
        if abs(cumulative[r['ToNode']]-r['CummLoad'])>0.01:
            raise ModelError(f"Cumulative kVA disagrees with topology at {r['SectionID']}")
    return feeder,rows


def read_study(path,sheet):
    book=openpyxl.load_workbook(path,data_only=True,read_only=True)
    try:
        ws=book[sheet]
        headers=list(next(ws.values))
        records=[dict(zip(headers,r)) for r in list(ws.values)[1:] if r[1] is not None]
        params={c:ws[c].value for c in ['W6','X6','Y6','Z6','W15','Y12','AA15']}
    finally:book.close()
    if any(params[c] is None for c in ['W6','X6','Y6','Z6']):
        raise ModelError('Required source parameter has no cached numeric value')
    feeder,rows=build_model(records,params['W6'],params['X6'],params['Y6'])
    return feeder,rows,params


def normal_conductor(value):
    return str(value).upper().replace(' ','')


def audit_gis(rows,geojson):
    features=json.loads(Path(geojson).read_text())['features']
    groups={}
    for f in features:
        prop=f['properties'];sid=str(prop.get('SectionID',''))
        if not sid:raise ModelError('GIS feature missing SectionID')
        groups.setdefault(sid,[]).append(prop)
    output=[];study_ids=set()
    for r in rows.to_dict('records'):
        sid=str(r['SectionID']);study_ids.add(sid);matches=groups.get(sid,[])
        reasons=[];gis_length=None;conductor=None
        if not matches:reasons.append('missing GIS section')
        elif len(matches)!=1:reasons.append('duplicate/multipart GIS ID needs review')
        else:
            g=matches[0];gis_length=g.get('LengthKM');conductor=g.get('ConductorN')
            if not isinstance(gis_length,(int,float)) or not math.isfinite(gis_length):
                reasons.append('invalid GIS length')
            elif abs(gis_length-r['Len_KM'])>0.001000001:reasons.append('length differs by more than 1 m')
            if normal_conductor(conductor)!=normal_conductor(r['conductor']):reasons.append('conductor differs')
        output.append({'section_id':sid,'study_km':r['Len_KM'],'gis_km':gis_length,
            'study_conductor':r['conductor'],'gis_conductor':conductor,
            'status':'review' if reasons else 'attribute match only','reason':'; '.join(reasons)})
    for sid in sorted(set(groups)-study_ids):
        output.append({'section_id':sid,'status':'review','reason':'GIS section missing in study'})
    return pd.DataFrame(output)


def study_report(feeder,rows,params):
    df=math.sqrt(3)*feeder.voltage_kv*params['W6']/rows.NodeKVA.sum()
    legacy_line=sum(3*(df*r['CummLoad']/(math.sqrt(3)*feeder.voltage_kv))**2 *r['resistance']*r['Len_KM']/1000 for r in rows.to_dict('records'))
    core=float(pd.to_numeric(rows.get('CORE LOSS',pd.Series(dtype=float)),errors='coerce').fillna(0).sum())
    copper=float(pd.to_numeric(rows.get('COPPER LOSS',pd.Series(dtype=float)),errors='coerce').fillna(0).sum())*df**2
    lf=params['Z6'];loss_factor=.3*lf+.7*lf**2
    physical=feeder.run()
    return {'study_sections':len(rows),'study_length_km':float(rows.Len_KM.sum()),
        'installed_kva':float(rows.NodeKVA.sum()),'source_node':feeder.root,
        'source_current_input_a':params['W6'],'legacy_ht_loss_kw':legacy_line,
        'legacy_transformer_core_kw':core,'legacy_transformer_copper_kw':copper,
        'legacy_annual_total_loss_kwh':(legacy_line+core+copper)*loss_factor*8760,
        'corrected_legacy_annual_total_loss_kwh':(legacy_line+copper)*loss_factor*8760+core*8760,
        'core_loss_hours_assumed':8760,'physical_ht_loss_kw':physical['loss_kw'],
        'physical_source_current_a':physical['grid_current_a'],
        'physical_source_pf':physical['source_pf'],'physical_min_pu':physical['min_pu'],
        'calibration_status':'NOT CALIBRATED: nameplate-proportional loads and workbook PF; source current excludes line losses in allocation',
        'location_status':'UNVERIFIED: study/GIS versions and electrical-node-to-pole mapping need reconciliation'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workbook',required=True);p.add_argument('--sheet',default='JULY')
    p.add_argument('--profiles',required=True,help='Explicit assumed or measured annual hours/load fractions')
    p.add_argument('--profile-basis',required=True,choices=['assumed','measured'])
    p.add_argument('--gis',help='HT lines EPSG:4326 GeoJSON (SectionID, LengthKM, ConductorN)')
    p.add_argument('--sites',help='Optional CSV of eligible electrical node_id, not geographic approval')
    p.add_argument('--sizes',default='150,300,450,600,900')
    p.add_argument('--kind',default='fixed',choices=['fixed','switched'])
    p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    feeder,rows,params=read_study(a.workbook,a.sheet)
    profiles=validate_profile(pd.read_csv(a.profiles))
    sizes=[float(s) for s in a.sizes.split(',')]
    sites=pd.read_csv(a.sites,dtype=str).node_id.tolist() if a.sites else None
    report=study_report(feeder,rows,params)
    report.update(profile_basis=a.profile_basis,workbook_sheet=a.sheet,
        workbook_sha256=hashlib.sha256(Path(a.workbook).read_bytes()).hexdigest(),
        profile_sha256=hashlib.sha256(Path(a.profiles).read_bytes()).hexdigest(),
        method='balanced radial constant-PQ, voltage-sensitive bank; HT conductor savings only',
        switching='fixed or simple 0.6 load-fraction threshold; no hardware controller model')
    if a.gis:
        qa=audit_gis(rows,a.gis);qa.to_csv(out/'gis_reconciliation.csv',index=False)
        report['gis_review_rows']=int((qa.status=='review').sum())
        report['gis_sha256']=hashlib.sha256(Path(a.gis).read_bytes()).hexdigest()
    base=annual(feeder,profiles)
    rank=candidates(feeder,profiles,sizes=sizes,kind=a.kind,limit=100000,candidate_nodes=sites)
    rank['location_status']='electrical node estimate; geographic placement unverified'
    rank.to_csv(out/'candidate_ranking.csv',index=False)
    eligible=rank[rank.feasible] if len(rank) else rank
    banks=[]
    if len(eligible):
        best=eligible.iloc[0];banks=[Bank(str(best.node_id),float(best.kvar),a.kind)]
    result=compare(feeder,profiles,banks,base)
    report.update(screened_bank=[b.__dict__ for b in banks],baseline_ht_kwh=base['annual_kwh'],
        after_ht_kwh=result['proposed']['annual_kwh'],estimated_ht_saved_kwh=result['saved_kwh'],
        estimated_ht_saved_pct=result['saved_pct'],
        recommendation_status='preliminary electrical screen only' if banks else 'no feasible candidate')
    b=base['periods'];q=result['proposed']['periods']
    b.merge(q,on=['period','hours','load_fraction'],suffixes=('_before','_after')).to_csv(out/'period_comparison.csv',index=False)
    # Export every period and every electrical section, retaining the actual scenario key.
    details=[]
    for period in profiles.to_dict('records'):
        old=pd.DataFrame(feeder.run(period['load_fraction'])['lines'])
        new=pd.DataFrame(feeder.run(period['load_fraction'],banks)['lines'])
        merged=old.merge(new,on=['section_id','from_node','to_node','ampacity_a'],suffixes=('_before','_after'))
        merged['period']=period['period'];merged['hours']=period['hours']
        merged['saved_kw']=merged.loss_kw_before-merged.loss_kw_after
        merged['saved_kwh']=merged.saved_kw*period['hours'];details.append(merged)
    pd.concat(details).to_csv(out/'section_comparison.csv',index=False)
    feeder.nodes.to_csv(out/'nodes.csv',index=False)
    feeder.sections[['section_id','from_node','to_node','length_km','r_ohm_per_km','x_ohm_per_km','ampacity_a']].to_csv(out/'sections.csv',index=False)
    profiles.to_csv(out/'profiles.csv',index=False)
    (out/'study_summary.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__':main()
