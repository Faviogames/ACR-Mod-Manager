const test=require('node:test');const assert=require('node:assert/strict');
const {filterStages}=require('./ui/app.js');
test('controls have unique identifiers and icon links resolve',()=>{const html=require('node:fs').readFileSync(require('node:path').join(__dirname,'ui/index.html'),'utf8');const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(ids).size,ids.length);for(const m of html.matchAll(/href="#([^"]+)"/g))assert.ok(ids.includes(m[1]),m[1]);});
const stages=[{name:'Riudecanyes',country:'España',active:true},{name:'Savalla',country:'España',active:false},{name:'Ntulele',country:'Kenia',active:true}];
test('search ignores case and accents and includes country',()=>{assert.equal(filterStages(stages,'all','ESPANA').length,2);assert.equal(filterStages(stages,'all','tule')[0].name,'Ntulele');});
test('active and disabled filters compose with search',()=>{assert.equal(filterStages(stages,'active','').length,2);assert.deepEqual(filterStages(stages,'disabled','Espana').map(x=>x.name),['Savalla']);assert.equal(filterStages(stages,'disabled','Kenia').length,0);});
