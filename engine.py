"""11 kV radial balanced 3-phase HT feeder capacitor screening engine.
Engineering screening only; not unbalanced harmonic/protection or certified design.
Units: nodes peak_kw (kW), sections ohm/km & km, capacitors kVAr (three phase).
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict, deque
from typing import Optional
import math
import pandas as pd


class ModelError(ValueError):
    pass


@dataclass(frozen=True)
class Bank:
    node_id: str
    kvar: float
    kind: str = "fixed"  # fixed | switched


class Feeder:
    def __init__(self, nodes: pd.DataFrame, sections: pd.DataFrame, root: str, voltage_kv: float = 11.0):
        self.nodes = nodes.copy()
        self.sections = sections.copy()
        self.root = str(root).strip()
        self.voltage_kv = float(voltage_kv)
        if not 1 < self.voltage_kv < 36:
            raise ModelError("Nominal line-line voltage must be between 1 and 36 kV for this HT model.")
        self._validate()

    def _validate(self):
        ncols = {'node_id','peak_kw','pf'}
        lcols = {'section_id','from_node','to_node','length_km','r_ohm_per_km','x_ohm_per_km','ampacity_a'}
        if ncols - set(self.nodes.columns): raise ModelError(f"nodes.csv missing {sorted(ncols - set(self.nodes.columns))}")
        if lcols - set(self.sections.columns): raise ModelError(f"sections.csv missing {sorted(lcols - set(self.sections.columns))}")
        for d,cols in [(self.nodes,['node_id']), (self.sections,['section_id','from_node','to_node'])]:
            for col in cols:
                d[col] = d[col].astype(str).str.strip()
        if self.nodes.node_id.duplicated().any(): raise ModelError("Duplicate node_id. Resolve unique electrical connectivity.")
        if self.sections.section_id.duplicated().any(): raise ModelError("Duplicate section_id. Merge GIS geometry pieces before load flow.")
        if self.sections.to_node.duplicated().any():
            ids = self.sections.loc[self.sections.to_node.duplicated(False),'to_node'].unique()
            raise ModelError(f"Multiple incoming energized sections at nodes {list(ids)[:10]}. Validate switch state and source paths.")
        if self.root not in set(self.nodes.node_id): raise ModelError("Root feeder node does not exist in nodes.csv")
        for col in ['peak_kw','pf']:
            self.nodes[col] = pd.to_numeric(self.nodes[col],errors='coerce')
            if not self.nodes[col].map(math.isfinite).all(): raise ModelError(f"Invalid numeric node {col}")
        for col in ['length_km','r_ohm_per_km','x_ohm_per_km','ampacity_a']:
            self.sections[col] = pd.to_numeric(self.sections[col],errors='coerce')
            if not self.sections[col].map(math.isfinite).all(): raise ModelError(f"Invalid numeric section {col}")
        if (self.nodes.peak_kw < 0).any() or (self.nodes.pf <= 0).any() or (self.nodes.pf > 1).any():
            raise ModelError("Node loads must be >=0 and pf must lie in (0,1].")
        if (self.sections.length_km <= 0).any() or (self.sections.r_ohm_per_km < 0).any() or (self.sections.x_ohm_per_km < 0).any() or (self.sections.ampacity_a <= 0).any():
            raise ModelError("Invalid section length, R/X, or ampacity; zero or negative lengths are not allowed.")
        nodeids=set(self.nodes.node_id)
        unknown=(set(self.sections.from_node)|set(self.sections.to_node))-nodeids
        if unknown: raise ModelError(f"Unknown bus(es) in sections: {sorted(unknown)[:10]}")
        if self.root in set(self.sections.to_node):raise ModelError("Feeder source has an incoming line: incorrect root or closed tie.")
        self.children=defaultdict(list)
        self.lines_by_child={}
        for row in self.sections.to_dict('records'):
            a,b=row['from_node'],row['to_node']
            self.children[a].append(b)
            self.lines_by_child[b]=row
        self.order=[]
        visited={self.root}
        q=deque([self.root])
        while q:
            a=q.popleft();self.order.append(a)
            for b in self.children[a]:
                if b in visited: raise ModelError("Closed-loop/cycle detected; resolve open point before radial calculation.")
                visited.add(b);q.append(b)
        if visited!=nodeids or len(self.sections)!=len(self.nodes)-1:
            raise ModelError(f"Feeder not a single connected radial tree: reached {len(visited)}/{len(nodeids)} buses. Validate switches/disconnected objects.")
        self.node_data=self.nodes.set_index('node_id').to_dict('index')
        self.v_phase=self.voltage_kv*1000/math.sqrt(3)

    def run(self, load_fraction: float = 1.0, banks: list[Bank] | None = None,
            switch_threshold: float = 0.60, tol_v: float = 1e-5, maxiter: int = 250):
        if not 0 <= load_fraction <= 2.0: raise ModelError("load_fraction must be between 0 and 2.")
        if not math.isfinite(switch_threshold) or not 0 <= switch_threshold <= 2:
            raise ModelError("switch_threshold must lie in [0,2].")
        banks = banks or []
        caps = defaultdict(float)
        for b in banks:
            if b.node_id not in self.node_data: raise ModelError(f"Bank location {b.node_id} not in feeder")
            if not math.isfinite(b.kvar) or b.kvar <= 0 or b.kind not in ('fixed','switched'):
                raise ModelError("Bank kVAr must be positive and kind must be fixed or switched")
            if b.kind=='fixed' or load_fraction >= switch_threshold:
                caps[b.node_id]+=b.kvar
        v={node:complex(self.v_phase) for node in self.order}
        branch={}
        for k in range(maxiter):
            inj={}
            for node in self.order:
                record=self.node_data[node]
                p=float(record['peak_kw'])*load_fraction
                q=p*math.tan(math.acos(float(record['pf'])))
                # Physical shunt bank kVAr changes with the square of the local voltage.
                q-=caps[node]*(abs(v[node])/self.v_phase)**2
                inj[node]=((complex(p,q)*1000/3)/v[node]).conjugate()
            for node in self.order[:0:-1]:
                down=inj[node]+sum(branch[kid] for kid in self.children[node])
                branch[node]=down
            newv={self.root:complex(self.v_phase)}
            for a in self.order:
                for b in self.children[a]:
                    line=self.lines_by_child[b]
                    z=complex(line['r_ohm_per_km'], line['x_ohm_per_km'])*line['length_km']
                    newv[b]=newv[a]-z*branch[b]
            change=max(abs(newv[n]-v[n]) for n in self.order)
            v=newv
            if min(abs(voltage) for voltage in v.values()) < self.v_phase*0.55:
                raise ModelError("Voltage collapsed; check load, R/X data, source voltage or topology")
            if change < tol_v:break
        else: raise ModelError("Backward-forward sweep did not converge: inspect large R/X or load entries")
        line_results=[]
        for b,I in branch.items():
            li=self.lines_by_child[b]
            z=complex(li['r_ohm_per_km'], li['x_ohm_per_km'])*li['length_km']
            loss_kw=(3*abs(I)**2*z.real)/1000
            line_results.append({'section_id':li['section_id'],'from_node':li['from_node'],
                'to_node':b,'current_a':abs(I),'loss_kw':loss_kw,'reactive_loss_kvar':3*abs(I)**2*z.imag/1000,
                'ampacity_a':li['ampacity_a'],'loading_pct':abs(I)/li['ampacity_a']*100,
                'end_voltage_pu':abs(v[b])/self.v_phase})
        total_current=sum(branch[k] for k in self.children[self.root]) + inj[self.root]
        source_power=3*complex(self.v_phase)*total_current.conjugate()/1000
        power_kw=source_power.real; reactive_kvar=source_power.imag
        min_voltage=min(abs(t) for t in v.values())/self.v_phase
        max_voltage=max(abs(t) for t in v.values())/self.v_phase
        return {'loss_kw':sum(r['loss_kw'] for r in line_results), 'source_kw':power_kw,
                'source_kvar':reactive_kvar, 'source_pf':abs(power_kw)/abs(source_power) if abs(source_power)>1e-10 else 1,
                'leading':reactive_kvar < -1e-6, 'grid_current_a':abs(total_current),
                'min_pu':min_voltage, 'max_pu':max_voltage,
                'max_line_loading_pct':max([r['loading_pct'] for r in line_results],default=0),
                'voltages':{n:abs(t)/self.v_phase for n,t in v.items()},
                'lines':line_results,'iterations':k+1}


def validate_profile(profiles: pd.DataFrame):
    for c in ['period','hours','load_fraction']:
        if c not in profiles:raise ModelError(f"profiles.csv needs column {c}")
    p=profiles.copy()
    p['hours']=pd.to_numeric(p['hours'],errors='coerce')
    p['load_fraction']=pd.to_numeric(p['load_fraction'],errors='coerce')
    if not all(p[c].map(math.isfinite).all() for c in ['hours','load_fraction']) or (p.hours<0).any() or (p.load_fraction<0).any() or (p.load_fraction>2).any():
        raise ModelError("Invalid period hours or load multipliers")
    if abs(p.hours.sum()-8760)>1:
        raise ModelError(f"Period hours sum {p.hours.sum():.0f}, expected 8760 for non-leap year. Adjust profile.")
    if p.period.duplicated().any():raise ModelError("Duplicate period name")
    return p


def annual(feeder:Feeder,profiles:pd.DataFrame,banks=None,threshold=.60):
    profiles=validate_profile(profiles)
    summaries=[]; detail=[]
    for r in profiles.to_dict('records'):
        run=feeder.run(float(r['load_fraction']),banks or [],threshold)
        summaries.append({'period':r['period'],'hours':r['hours'],'load_fraction':r['load_fraction'],
            'loss_kw':run['loss_kw'],'loss_kwh':run['loss_kw']*r['hours'],
            'source_kw':run['source_kw'],'source_kvar':run['source_kvar'],
            'source_pf':run['source_pf'],'leading':run['leading'],
            'min_pu':run['min_pu'],'max_pu':run['max_pu'],
            'max_line_loading_pct':run['max_line_loading_pct'], 'grid_current_a':run['grid_current_a']})
        if r['load_fraction']==max(profiles.load_fraction):detail=run['lines']
    results=pd.DataFrame(summaries)
    return {'annual_kwh':float(results.loss_kwh.sum()),
            'modelled_grid_kwh':float((results.source_kw*results.hours).sum()),
            'modelled_load_kwh':float((profiles.load_fraction*profiles.hours).sum()*feeder.nodes.peak_kw.sum()),
            'periods':results,
            'peak_lines':pd.DataFrame(detail),
            'min_pu':float(results.min_pu.min()),'max_pu':float(results.max_pu.max()),
            'max_loading_pct':float(results.max_line_loading_pct.max()),
            'any_leading':bool(results.leading.any())}


def compare(feeder,profiles,banks=None,base=None,threshold=.60):
    b=base or annual(feeder,profiles,[])
    proposed=annual(feeder,profiles,banks or [],threshold)
    saved=b['annual_kwh']-proposed['annual_kwh']
    return {'base':b,'proposed':proposed,'saved_kwh':saved,
            'saved_pct':saved/b['annual_kwh']*100 if b['annual_kwh']>0 else 0}


def candidates(feeder,profiles,sizes=(150,300,450,600,900),kind='fixed',vmin=.95,vmax=1.05,
               cap_cost_per_kvar=None,energy_value_per_kwh=None,cap_life_years=15,
               threshold=.6,existing=None,limit=100,candidate_nodes=None):
    # Exhaustive single-bank candidates and greedy iterative extension via existing banks.
    existing=list(existing or [])
    sites=set(feeder.order if candidate_nodes is None else map(str,candidate_nodes))
    if sites-set(feeder.order):raise ModelError("Candidate site does not exist in feeder")
    if not sizes or any(not math.isfinite(float(s)) or float(s)<=0 for s in sizes):
        raise ModelError("Candidate sizes must be finite and positive")
    base=annual(feeder,profiles,existing,threshold)
    allrows=[]
    for node in feeder.order:
        if node==feeder.root or node not in sites:continue
        for size in sizes:
            if float(size)<=0:continue
            bank=Bank(node,float(size),kind)
            try:
                case=annual(feeder,profiles,existing+[bank],threshold)
            except ModelError as e:
                allrows.append({'node_id':node,'kvar':size,'kind':kind,'feasible':False,'reason':str(e),'saved_kwh':None});continue
            violated=[]
            if case['min_pu']<vmin-1e-8:violated.append('undervoltage')
            if case['max_pu']>vmax+1e-8:violated.append('overvoltage')
            if case['max_loading_pct']>100+1e-8:violated.append('ampacity')
            if case['any_leading']:violated.append('leading grid PF')
            saved=base['annual_kwh']-case['annual_kwh']
            if saved<=0:violated.append('no annual saving')
            row={'node_id':node,'kvar':float(size),'kind':kind,'feasible':not violated,
                'reason':', '.join(violated),'saved_kwh':saved,
                'saved_pct':saved/base['annual_kwh']*100 if base['annual_kwh']>0 else 0,
                'post_loss_kwh':case['annual_kwh'],'v_min_pu':case['min_pu'],
                'v_max_pu':case['max_pu'],'max_loading_pct':case['max_loading_pct'],
                'capex':float(size)*cap_cost_per_kvar if cap_cost_per_kvar is not None else None}
            if cap_cost_per_kvar is not None and energy_value_per_kwh is not None:
                annual_benefit=saved*energy_value_per_kwh
                row.update(annual_benefit=annual_benefit,payback_years=row['capex']/annual_benefit if annual_benefit>0 else None,
                           annual_net_value=annual_benefit-row['capex']/cap_life_years)
            allrows.append(row)
    rows=pd.DataFrame(allrows) if allrows else pd.DataFrame(columns=['node_id','kvar','kind','feasible','reason','saved_kwh'])
    if len(rows):
        rankby='annual_net_value' if 'annual_net_value' in rows.columns else 'saved_kwh'
        rows=rows.sort_values(['feasible',rankby],ascending=[False,False],na_position='last')
    return rows.head(limit).reset_index(drop=True)


def greedy_banks(feeder,profiles,n_banks=2,sizes=(150,300,450,600,900),kind='fixed',**kwargs):
    installed=[]; history=[]
    for step in range(n_banks):
        c=candidates(feeder,profiles,sizes=sizes,kind=kind,existing=installed,limit=len(feeder.order)*len(sizes),**kwargs)
        used={x.node_id for x in installed}
        eligible=c[(c.feasible)&(~c.node_id.isin(used))]
        if eligible.empty:break
        best=eligible.iloc[0]
        installed.append(Bank(str(best.node_id),float(best.kvar),kind))
        history.append(best.to_dict())
    return installed,pd.DataFrame(history)
