const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {solveNetwork}=require('./dist/engine.js');const n=JSON.parse(fs.readFileSync('network.json'));const cfg={kv:11,amps:350,pf:.8,sourcePU:1};
const b=solveNetwork(n,cfg,null,0),off=solveNetwork(n,cfg,'180075',0),a=solveNetwork(n,cfg,'180075',1500);
assert.deepEqual(b.v,off.v);assert.equal(b.loss,off.loss);assert.equal(Object.keys(b.v).length,70);assert.equal(Object.keys(b.results).length,69);
assert(Math.abs(b.loss-110.078470897)<1e-6);assert(Math.abs(b.minV-.9641639785)<1e-8);assert(a.loss<b.loss);assert(a.headCurrent<b.headCurrent);assert(a.minV>b.minV);
for(const e of n.edges){if(!a.results[e.id].upstream)assert.equal(a.results[e.id].current,b.results[e.id].current);assert(a.v[e.b]>=b.v[e.b]-1e-10)}
const light=solveNetwork(n,{...cfg,amps:100,pf:.9},'180075',4000);assert(light.headQ<0);
for(const node of Object.keys(n.nodes)){const r=solveNetwork(n,cfg,node,1500);assert(Number.isFinite(r.loss));assert(Object.values(r.v).every(Number.isFinite))}
const children={};for(const e of n.edges)(children[e.a]??=[]).push(e);for(const e of n.edges){const downstream=e.local+(children[e.b]||[]).reduce((s,x)=>s+x.down,0);assert.equal(e.down,downstream,`kVA balance ${e.id}`)}
console.log(JSON.stringify({tests:'passed',sections:69,nodes:70,before:{loss:b.loss,minKV:b.minV*11,headA:b.headCurrent},after:{loss:a.loss,minKV:a.minV*11,headA:a.headCurrent,pf:a.headPF,overloads:a.overloads},lossSaved:b.loss-a.loss},null,2));
