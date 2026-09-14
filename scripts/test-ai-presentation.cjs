const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ts=require('../apps/desktop/node_modules/typescript');
function load(name){
  const source=fs.readFileSync(path.join(__dirname,'../apps/desktop/src/web-ai/utils/'+name+'.ts'),'utf8');
  const result={exports:{}};
  new Function('exports','module',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(result.exports,result);
  return result.exports;
}
const presentation=load('actionPresentation');
assert.deepEqual(presentation.agentActionCountItems({preview:{counts:{create:2,skip:1}}}),[{label:'新增',value:2},{label:'跳过',value:1}]);
assert.equal(presentation.agentActionOperationLabel({operation:'change_set'}),'整批执行');
assert.equal(presentation.agentActionStatusLabel('stale'),'数据已变化');
assert.equal(presentation.agentActionFailures({preview:{failures:[{message:'数据过期'}]}})[0],'数据过期');
assert.ok(presentation.agentActionDetailTables({preview:{counts:{create:1}}}).length);
const {sameExpectedTimes}=load('expectedPolicy');
const rule={template_id:'t',period_keys:[1,2],week_bits:'11',day_bits:'1100000',effect:'preferred',penalty:10,required:true};
const config=rules=>({schema_version:2,default_policy:'restricted',rules});
assert.ok(sameExpectedTimes(config([rule]),config([{...rule,period_keys:[2,1]}])));
assert.ok(sameExpectedTimes(config([rule]),config([{...rule,day_bits:'1000000'},{...rule,day_bits:'0100000'}])));
assert.ok(!sameExpectedTimes(config([rule]),config([{...rule,penalty:30}])));
console.log('AI review and expected-time policy: 8 checks passed.');
