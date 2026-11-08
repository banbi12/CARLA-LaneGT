'use strict';
const data=window.COMPARISON,rows=data.frames,$=id=>document.getElementById(id),classes=['divider','ped_crossing','boundary','centerline'];
let filtered=[],index=0;
const focus='062dd1c38f2a45d8bd34bfd6395741df';
const endpoint=r=>r.unmatched_interior_boundary_endpoints;
function match(r,v){return v==='all'||v==='junction'&&r.near_junction||v==='slope'&&r.terrain==='slope'||v==='elevated'&&r.terrain==='elevated'||v==='improved'&&endpoint(r)[1]<endpoint(r)[0]||v==='remaining'&&endpoint(r)[1]>0||v==='worsened'&&endpoint(r)[1]>endpoint(r)[0]||v==='divider'&&r.changed.divider;}
function show(){
  if(!filtered.length){$('details').textContent='当前筛选无帧';$('frame').innerHTML='';$('counts').innerHTML='';$('oldImage').removeAttribute('src');$('newImage').removeAttribute('src');return;}
  index=(index+filtered.length)%filtered.length;const r=filtered[index],v=$('view').value;
  $('frame').value=r.token;document.body.className=v;
  $('details').textContent=`${index+1}/${filtered.length} · ${r.scene} frame ${r.frame_idx} · ${r.terrain} · boundary孤立内部端点 ${endpoint(r)[0]} → ${endpoint(r)[1]} · boundary落在旧线20cm外的采样比例 ${(100*(1-r.coverage_20cm.boundary.new_covered_by_old)).toFixed(1)}%（含边界位置变化）`;
  $('counts').innerHTML='<table><tr><th>实例数</th>'+classes.map(c=>'<th>'+c+'</th>').join('')+'<th>合计</th></tr>'+['原版','V4.1'].map((label,s)=>'<tr><td>'+label+'</td>'+classes.map(c=>'<td>'+r.counts[s][c]+'</td>').join('')+'<td>'+r.instances[s]+'</td></tr>').join('')+'</table>';
  ['old','new'].forEach((key,s)=>{$(key+'Image').src=r.images[s][v];$(key+'Link').href=r.review_links[s];});
  history.replaceState(null,'','#'+r.token);
}
function filter(token){filtered=rows.filter(r=>match(r,$('filter').value));$('frame').innerHTML=filtered.map(r=>'<option value="'+r.token+'">'+r.scene+' · frame '+r.frame_idx+'</option>').join('');index=Math.max(0,filtered.findIndex(r=>r.token===token));show();}
$('filter').onchange=()=>filter($('frame').value);$('frame').onchange=()=>{index=filtered.findIndex(r=>r.token===$('frame').value);show();};
$('prev').onclick=()=>{index--;show();};$('next').onclick=()=>{index++;show();};$('view').onchange=show;
$('focus').onclick=()=>{$('filter').value='all';filter(focus);};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT'].includes(e.target.tagName))return;if(e.key==='ArrowLeft')$('prev').onclick();if(e.key==='ArrowRight')$('next').onclick();});
const a=data.report;$('summary').textContent=`同一组 ${a.frames} 帧、相同相机/位姿/BEV/高程范围。boundary实例 ${a.counts[0].boundary} → ${a.counts[1].boundary}；divider ${a.counts[0].divider} → ${a.counts[1].divider}。crosswalk和centerline几何逐帧一致。`;
filter(location.hash.slice(1)||focus);
