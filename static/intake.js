(()=>{'use strict';const form=document.getElementById('intake-wizard');if(!form)return;
const initial=JSON.parse(form.dataset.budget),pages=[...form.querySelectorAll('[data-intake-page]')],tabs=[...form.querySelectorAll('[data-step]')];let step=0;
const repeaters=[];
form.querySelectorAll('[data-group]').forEach(root=>{const group=root.dataset.group;let rows=Array.isArray(initial[group])?initial[group].map(r=>({...r})):[],index=0;const fields=[...root.querySelectorAll('[data-entry]')],hidden=root.querySelector('input[type=hidden]');
function sync(){if(rows[index])fields.forEach(f=>rows[index][f.dataset.entry]=f.value);hidden.value=JSON.stringify(rows);}
function draw(){root.querySelector('[data-editor]').hidden=!rows.length;root.querySelector('[data-empty]').hidden=!!rows.length;fields.forEach(f=>{f.value=rows[index]?.[f.dataset.entry]??'';f.required=!!rows.length&&(['kind','provider','amount'].includes(f.dataset.entry)||(group==='children'&&['age','married'].includes(f.dataset.entry)));f.disabled=!rows.length;});root.querySelector('[data-count]').textContent=rows.length?`${index+1} / ${rows.length}`:'';root.querySelector('[data-prev]').disabled=index===0;root.querySelector('[data-next]').disabled=index>=rows.length-1;root.querySelector('[data-add]').disabled=rows.length>=100;hidden.value=JSON.stringify(rows);}
function valid(){return fields.every(f=>f.reportValidity());}
root.querySelector('[data-add]').onclick=()=>{sync();if(rows.length&&!valid())return;rows.push({});index=rows.length-1;draw();fields[0].focus();};
root.querySelector('[data-prev]').onclick=()=>{sync();if(valid()){index--;draw();}};root.querySelector('[data-next]').onclick=()=>{sync();if(valid()){index++;draw();}};
root.querySelector('[data-remove]').onclick=()=>{rows.splice(index,1);index=Math.max(0,Math.min(index,rows.length-1));draw();};fields.forEach(f=>f.addEventListener('input',sync));repeaters.push({sync,count:()=>rows.length});draw();});
const stamps=form.elements.foodstamps,stampBox=document.getElementById('foodstamps-amount');function conditional(){const yes=stamps.value==='yes';stampBox.hidden=!yes;form.elements.foodstamps_amount.required=yes;form.elements.foodstamps_amount.disabled=!yes;}stamps.addEventListener('change',conditional);conditional();
const other=form.elements.other_assistance,otherBox=document.getElementById('other-assistance-entries');function otherConditional(){const yes=other.value==='yes';otherBox.hidden=!yes;otherBox.querySelectorAll('[data-entry]').forEach(f=>f.disabled=!yes||f.closest('[data-editor]').hidden);}other.addEventListener('change',otherConditional);otherConditional();
function validPage(i){return [...pages[i].querySelectorAll('input,select,textarea')].every(f=>f.disabled||f.reportValidity());}
function review(){repeaters.forEach(r=>r.sync());const root=document.getElementById('intake-review');root.replaceChildren();const entries=[['children',String(repeaters[0].count())],['rent',form.elements.rent.value],['food',form.elements.food.value],['income',[form.elements.his_income.value,form.elements.her_income.value,form.elements.other_income.value].filter(Boolean).join(' + ')],['assistance',String(repeaters[1].count())],['accounts',String(repeaters[2].count())]];entries.forEach(([key,value])=>{const line=document.createElement('div'),label=document.createElement('span'),v=document.createElement('strong');label.textContent=root.dataset[key];v.textContent=value||root.dataset.blank;line.append(label,v);root.append(line);});const missing=[];if(!form.elements.name_en.value.trim())missing.push('English name');if(!form.elements.name_yi.value.trim())missing.push('Yiddish name');if(!form.elements.address.value.trim()||!form.elements.city.value.trim()||!form.elements.state.value.trim()||!form.elements.zip_code.value.trim())missing.push('Complete address');if(!repeaters[0].count())missing.push('Children');if(!form.elements.rent.value)missing.push('Rent or mortgage');if(!form.elements.food.value)missing.push('Food costs');const list=document.getElementById('readiness-list');list.replaceChildren();(missing.length?missing:['Ready to submit for review']).forEach(item=>{const li=document.createElement('li');li.textContent=item;list.append(li);});}
function show(i){step=i;pages.forEach((p,n)=>p.hidden=n!==i);tabs.forEach((t,n)=>{t.classList.toggle('selected',n===i);t.setAttribute('aria-current',n===i?'step':'false');});document.getElementById('intake-back').disabled=i===0;document.getElementById('intake-next').hidden=i===pages.length-1;document.getElementById('intake-save').hidden=i!==pages.length-1;document.getElementById('intake-progress').textContent=`${i+1} / ${pages.length}`;if(i===pages.length-1)review();}
function move(i){if(i>step&&!validPage(step))return;show(i);}
tabs.forEach(t=>t.onclick=()=>move(Number(t.dataset.step)));document.getElementById('intake-next').onclick=()=>move(step+1);document.getElementById('intake-back').onclick=()=>move(step-1);
form.noValidate=true;form.addEventListener('submit',e=>{repeaters.forEach(r=>r.sync());for(let i=0;i<pages.length;i++){const invalid=[...pages[i].querySelectorAll('input,select,textarea')].find(f=>!f.disabled&&!f.checkValidity());if(invalid){e.preventDefault();show(i);invalid.reportValidity();return;}}});
form.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.tagName==='INPUT'&&step<pages.length-1){e.preventDefault();move(step+1);}});show(0);
const totals=document.getElementById('intake-totals');
if(totals){
 const status=document.getElementById('profile-save-status');
 const money=new Intl.NumberFormat(document.documentElement.lang||'en',{style:'currency',currency:'USD'});
 const cents=v=>v!==''&&v!=null&&Number.isFinite(Number(v))&&Number(v)>=0?Math.round(Number(v)*100):null;
 const sum=values=>{const known=values.filter(v=>v!==null);return known.length?known.reduce((a,b)=>a+b,0):null;};
 function updateTotals(dirty=false){
  repeaters.forEach(r=>r.sync());
  const val=key=>form.elements[key].value;
  const accounts=JSON.parse(form.elements.accounts_json.value||'[]');
  const bills=sum(accounts.map(r=>cents(r.monthly_bill)));
  document.getElementById('provider-bills-total').textContent=bills===null?totals.dataset.blank:money.format(bills/100);
  const costs=sum([...['rent','food'].map(k=>cents(val(k))),...accounts.filter(r=>r.budget_treatment==='additional').map(r=>cents(r.monthly_bill))]);
  const income=sum(['his_income','her_income','other_income'].map(k=>cents(val(k))));
  const assistance=JSON.parse(form.elements.assistance_json.value||'[]');
  const help=sum([val('foodstamps')==='yes'?cents(val('foodstamps_amount')):val('foodstamps')==='no'?0:null,...(val('other_assistance')!=='no'?assistance.map(r=>cents(r.amount)):val('other_assistance')==='no'?[0]:[])]);
  const foodCosts=(cents(val('food'))??0)+accounts.filter(r=>r.kind==='grocery'&&r.budget_treatment==='additional').reduce((n,r)=>n+(cents(r.monthly_bill)??0),0);
  const stamps=val('foodstamps')==='yes'?(cents(val('foodstamps_amount'))??0):0;
  const usableHelp=(help??0)-stamps+Math.min(stamps,foodCosts);
  const values={children:repeaters[0].count()||totals.dataset.blank,costs,income,help,gap:costs===null?null:Math.max(0,costs-(income??0)-usableHelp),accounts:JSON.parse(form.elements.accounts_json.value||'[]').length};
  totals.querySelectorAll('[data-total]').forEach(el=>{const key=el.dataset.total,v=values[key];el.textContent=['children','accounts'].includes(key)?v:v===null?totals.dataset.blank:money.format(v/100);});
  if(dirty)totals.dataset.dirty='yes';
  status.textContent=totals.dataset.dirty==='yes'?totals.dataset.unsaved:totals.dataset.existing==='yes'?totals.dataset.saved:totals.dataset.new;
 }
 form.addEventListener('input',()=>updateTotals(true));
 form.addEventListener('change',()=>updateTotals(true));
 form.addEventListener('click',e=>{if(e.target.closest('[data-add],[data-remove]'))updateTotals(true);});
 updateTotals();
}
})();
