'use strict';
const D=window.V42_COMPARE,$=id=>document.getElementById(id),focus='062dd1c38f2a45d8bd34bfd6395741df',classes=['divider','boundary','ped_crossing','centerline'];
let rows=[],index=0;
function match(r,f){return f==='all'||f==='changed'&&r.divider_changed||f==='junction'&&r.near_junction||f==='slope'&&r.terrain==='slope'||f==='elevated'&&r.terrain==='elevated';}
function show(){if(!rows.length){$('details').textContent='当前筛选无帧';$('oldImage').removeAttribute('src');$('newImage').removeAttribute('src');$('counts').innerHTML='';return;}index=(index+rows.length)%rows.length;const r=rows[index],v=$('view').value;document.body.className=v;$('frame').value=r.token;
$('details').textContent=`${index+1}/${rows.length} · ${r.scene} frame ${r.frame_idx} · ${r.terrain} · ${r.divider_changed?'divider连接变化':'GT几何保持原样'} · boundary保持原样`;
$('counts').innerHTML='<table><tr><th>实例</th>'+classes.map(c=>'<th>'+c+'</th>').join('')+'</tr>'+['原版','连接后'].map((label,s)=>'<tr><td>'+label+'</td>'+classes.map(c=>'<td>'+r.counts[s][c]+'</td>').join('')+'</tr>').join('')+'</table>';
['old','new'].forEach((k,s)=>{$(k+'Image').src=r.images[s][v];$(k+'Link').href=r.review_links[s];});history.replaceState(null,'','#'+r.token);}
function filter(token){rows=D.frames.filter(r=>match(r,$('filter').value));$('frame').innerHTML=rows.map(r=>'<option value="'+r.token+'">'+r.scene+' · frame '+r.frame_idx+'</option>').join('');index=Math.max(0,rows.findIndex(r=>r.token===token));show();}
$('filter').onchange=()=>filter($('frame').value);$('frame').onchange=()=>{index=rows.findIndex(r=>r.token===$('frame').value);show();};$('view').onchange=show;$('prev').onclick=()=>{index--;show();};$('next').onclick=()=>{index++;show();};$('focus').onclick=()=>{$('filter').value='all';filter(focus);};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT'].includes(e.target.tagName))return;if(e.key==='ArrowLeft')$('prev').onclick();if(e.key==='ArrowRight')$('next').onclick();});
$('summary').textContent=`同一批 ${D.report.frames} 帧，${D.report.divider_changed_frames} 帧divider有连接变化；原始 ${D.report.native_divider_curves_preserved} 条世界divider完整保留。V4.1代码和输出保持冻结。`;
filter(location.hash.slice(1)||focus);
