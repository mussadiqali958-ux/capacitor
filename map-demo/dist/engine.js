/* Balanced linear feeder estimate. Units: three-phase kW/kvar, line-line kV, ohms/km. */
function solveNetwork(net, cfg, bankNode, bankKvar) {
  const {kv,amps,pf,sourcePU}=cfg;
  if (!(kv>0&&amps>=0&&pf>0&&pf<=1&&sourcePU>0&&bankKvar>=0)) throw Error('Invalid scenario inputs');
  if (bankNode && !net.nodes[bankNode]) throw Error('Unknown bank node');
  const incoming={}, children={};
  net.edges.forEach(e=>{if(incoming[e.b])throw Error('Multiple parents');incoming[e.b]=e;(children[e.a]??=[]).push(e)});
  const ordered=[], seen=new Set([net.source]), queue=[net.source];
  while(queue.length){const n=queue.shift();for(const e of children[n]||[]){if(seen.has(e.b))throw Error('Cycle');seen.add(e.b);ordered.push(e);queue.push(e.b)}}
  if(ordered.length!==net.edges.length)throw Error('Disconnected topology');
  const path=new Set();let cursor=bankNode;
  while(cursor&&cursor!==net.source){const e=incoming[cursor];if(!e)throw Error('Unreachable bank node');path.add(e.id);cursor=e.a}
  const total=net.edges.reduce((s,e)=>s+e.local,0), pHead=Math.sqrt(3)*kv*amps*pf, qHead=Math.sqrt(3)*kv*amps*Math.sqrt(1-pf*pf);
  const v={[net.source]:sourcePU}, distance={[net.source]:0}, results={};let loss=0;
  for(const e of ordered){
    const p=pHead*e.down/total, q=qHead*e.down/total-(path.has(e.id)?bankKvar:0);
    const current=Math.hypot(p,q)/(Math.sqrt(3)*kv), kwLoss=3*current*current*e.r*e.length/1000;
    v[e.b]=v[e.a]-(p*e.r+q*e.x)*e.length/(1000*kv*kv);distance[e.b]=distance[e.a]+e.length;
    results[e.id]={p,q,current,loss:kwLoss,loading:current/e.rating,voltage:v[e.b],upstream:path.has(e.id)};loss+=kwLoss;
  }
  const q=qHead-bankKvar, headCurrent=Math.hypot(pHead,q)/(Math.sqrt(3)*kv), headPF=(pHead===0&&q===0)?1:pHead/Math.hypot(pHead,q);
  return {v,distance,results,loss,headCurrent,headPF,headQ:q,minV:Math.min(...Object.values(v)),maxV:Math.max(...Object.values(v)),overloads:Object.values(results).filter(r=>r.loading>1).length,incoming};
}
if(typeof module!=='undefined')module.exports={solveNetwork};
