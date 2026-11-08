const C=require('../web/editor/edit_core.js');
let input='';process.stdin.on('data',x=>input+=x);process.stdin.on('end',()=>{
  const result=JSON.parse(input).map(x=>{try{return {plan:C.previewFillet(x.base,x.op,x.region,x.vertical),targets:C.replay(x.base,[x.op],x.region,x.vertical)}}catch(e){return {error:e.message}}});
  process.stdout.write(JSON.stringify(result));
});
