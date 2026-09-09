(()=>{'use strict';
let shulRabbis={},shulGabbais={};const shulPickers=[];
const form=document.querySelector('#intake-wizard');
const mode=form&&form.querySelector('[data-rabbi-mode]');
const person=form&&form.querySelector('[data-rabbi-person]');
const familyRabbi=form&&form.querySelector('input[name="rabbi"]');
const familyRabbiPhone=form&&form.querySelector('input[name="rabbi_phone"]');
const selectedShuls={};
const labels=form?{
  rabbi:form.dataset.rabbiLabel,rabbiPhone:form.dataset.rabbiPhoneLabel,
  gabbais:form.dataset.gabbaisLabel,addGabbai:form.dataset.addGabbaiLabel,
  gabbai:form.dataset.gabbaiLabel,gabbaiPhone:form.dataset.gabbaiPhoneLabel,
  remove:form.dataset.removeLabel,addPhone:form.dataset.addPhoneLabel,
  assistants:form.dataset.rabbiAssistantsLabel,
  addAssistant:form.dataset.addRabbiAssistantLabel,
  assistant:form.dataset.rabbiAssistantLabel,
  assistantPhone:form.dataset.assistantPhoneLabel
}:{};

function suggestedRabbi(){
  const weekday=selectedShuls.weekday_shul&&shulRabbis[selectedShuls.weekday_shul.value];
  const shabbos=selectedShuls.shabbos_shul&&shulRabbis[selectedShuls.shabbos_shul.value];
  return(weekday&&weekday.name&&weekday)||(shabbos&&shabbos.name&&shabbos)||null;
}
function applySuggestion(){
  if(!mode||mode.value!=='automatic'||!familyRabbi||!familyRabbiPhone)return;
  const rabbi=suggestedRabbi();familyRabbi.value=rabbi?rabbi.name:'';familyRabbiPhone.value=rabbi?(rabbi.phone||''):'';
  if(person)person.value='';
}
function applyCanonical(){
  if(!person||!person.value||!familyRabbi||!familyRabbiPhone)return;
  const option=person.selectedOptions[0];familyRabbi.value=option.textContent.trim();familyRabbiPhone.value=option.dataset.phone||'';
}
function applyMode(){
  const canonical=mode&&mode.value==='canonical';
  if(person){person.closest('label').hidden=!canonical;person.disabled=!canonical;}
  if(mode&&mode.value==='automatic')applySuggestion();
  if(canonical)applyCanonical();
}
function markManual(){
  if(!mode||mode.value!=='automatic')return;mode.value='manual';if(person)person.value='';applyMode();
}

function phoneList(container,fieldName,phones=[]){
  const wrap=document.createElement('div');wrap.className='contact-phone-list';
  const rows=document.createElement('div');wrap.appendChild(rows);
  const add=document.createElement('button');add.type='button';add.className='small secondary';add.textContent=labels.addPhone||'+ Add phone';wrap.appendChild(add);
  function addPhone(value=''){
    const row=document.createElement('div');row.className='contact-phone-row';
    const input=document.createElement('input');input.maxLength=80;input.value=value||'';if(fieldName)input.name=fieldName;
    const remove=document.createElement('button');remove.type='button';remove.className='small danger';remove.textContent=labels.remove||'Remove';
    remove.addEventListener('click',()=>row.remove());
    row.append(input,remove);rows.appendChild(row);
  }
  add.addEventListener('click',()=>addPhone(''));
  (phones&&phones.length?phones:['']).forEach(addPhone);
  container.appendChild(wrap);
  return {wrap,rows,addPhone,values:()=>Array.from(rows.querySelectorAll('input')).map(i=>i.value.trim()).filter(Boolean)};
}

function assistantFields(root,select){
  const key=select.name;if(!key.endsWith('_shul'))return null;
  const wrap=document.createElement('div');wrap.className='shul-rabbi-assistant-fields';
  const heading=document.createElement('div');heading.className='section-heading';
  const title=document.createElement('strong');title.textContent=labels.assistants||"Rabbi assistants / gabbaim";
  const add=document.createElement('button');add.type='button';add.className='small secondary';add.textContent=labels.addAssistant||'+ Add rabbi assistant';
  heading.append(title,add);const rows=document.createElement('div');wrap.append(heading,rows);root.appendChild(wrap);
  function addRow(data={}){
    const row=document.createElement('div');row.className='form-grid rabbi-assistant-row';
    const nameLabel=document.createElement('label');nameLabel.textContent=labels.assistant||"Rabbi assistant / gabbai";
    const name=document.createElement('input');name.name=key+'_rabbi_assistant_name';name.maxLength=160;name.value=data.name||'';nameLabel.appendChild(name);
    const phoneLabel=document.createElement('label');phoneLabel.textContent=labels.assistantPhone||'Assistant phone';
    const phoneHost=document.createElement('div');phoneLabel.appendChild(phoneHost);
    const hidden=document.createElement('input');hidden.type='hidden';hidden.name=key+'_rabbi_assistant_phones';
    const phones=phoneList(phoneHost,'',data.phones||(data.phone?[data.phone]:[]));
    const sync=()=>hidden.value=JSON.stringify(phones.values());phoneHost.addEventListener('input',sync);phoneHost.addEventListener('click',()=>setTimeout(sync,0));sync();
    const remove=document.createElement('button');remove.type='button';remove.className='small danger';remove.textContent=labels.remove||'Remove';remove.addEventListener('click',()=>row.remove());
    row.append(nameLabel,phoneLabel,hidden,remove);rows.appendChild(row);
  }
  add.addEventListener('click',()=>addRow());
  return {rows,addRow};
}

function rabbiFields(root,select){
  const key=select.name;if(!key.endsWith('_shul'))return null;
  const box=document.createElement('div');box.className='shul-rabbi-fields form-grid';
  const rabbiLabel=document.createElement('label');rabbiLabel.textContent=labels.rabbi||'Rabbi for this shul';
  const rabbi=document.createElement('input');rabbi.name=key+'_rabbi';rabbi.maxLength=160;rabbiLabel.appendChild(rabbi);
  const phoneLabel=document.createElement('label');phoneLabel.textContent=labels.rabbiPhone||'Rabbi phone';
  const phoneHost=document.createElement('div');phoneLabel.appendChild(phoneHost);
  box.append(rabbiLabel,phoneLabel);root.appendChild(box);
  let phoneFields=phoneList(phoneHost,key+'_rabbi_phone',[]);
  return{rabbi,phoneHost,get phones(){return phoneFields;},setPhones(values){phoneHost.replaceChildren();phoneFields=phoneList(phoneHost,key+'_rabbi_phone',values||[]);}};
}

function gabbaiFields(root,select){
  const key=select.name;if(!key.endsWith('_shul'))return null;
  const wrap=document.createElement('div');wrap.className='shul-gabbai-fields';
  const heading=document.createElement('div');heading.className='section-heading';
  const title=document.createElement('strong');title.textContent=labels.gabbais||'Gabbaim for this shul';
  const add=document.createElement('button');add.type='button';add.className='small secondary';add.textContent=labels.addGabbai||'+ Add gabbai';
  heading.append(title,add);const rows=document.createElement('div');wrap.append(heading,rows);root.appendChild(wrap);
  function addRow(data={}){
    const row=document.createElement('div');row.className='form-grid shul-gabbai-row';
    const nameLabel=document.createElement('label');nameLabel.textContent=labels.gabbai||'Gabbai';
    const name=document.createElement('input');name.name=key+'_gabbai_name';name.maxLength=160;name.value=data.name||'';nameLabel.appendChild(name);
    const phoneLabel=document.createElement('label');phoneLabel.textContent=labels.gabbaiPhone||'Gabbai phone';
    const phoneHost=document.createElement('div');phoneLabel.appendChild(phoneHost);
    const hidden=document.createElement('input');hidden.type='hidden';hidden.name=key+'_gabbai_phones';
    const phones=phoneList(phoneHost,'',data.phones||(data.phone?[data.phone]:[]));
    const sync=()=>hidden.value=JSON.stringify(phones.values());phoneHost.addEventListener('input',sync);phoneHost.addEventListener('click',()=>setTimeout(sync,0));sync();
    const remove=document.createElement('button');remove.type='button';remove.className='small danger';remove.textContent=labels.remove||'Remove';remove.addEventListener('click',()=>row.remove());
    row.append(nameLabel,phoneLabel,hidden,remove);rows.appendChild(row);
  }
  add.addEventListener('click',()=>addRow());return{rows,addRow};
}

function fillRabbi(select,fields,assistants){
  if(!fields)return;const adding=select.value==='__new__';
  const row=adding?{}:(shulRabbis[select.value]||{});
  fields.rabbi.value=row.name||'';fields.setPhones(row.phones||(row.phone?[row.phone]:[]));
  if(assistants){assistants.rows.replaceChildren();(row.assistants||[]).forEach(assistants.addRow);}
}
function fillGabbais(select,fields){
  if(!fields)return;fields.rows.replaceChildren();
  if(select.value==='__new__'){fields.addRow();return;}
  const rows=shulGabbais[select.value]||[];if(rows.length){rows.forEach(fields.addRow);}else{fields.addRow();}
}
document.querySelectorAll('[data-institution-picker]').forEach(root=>{
  const select=root.querySelector('[data-institution-select]'),newField=root.querySelector('[data-new-institution]'),input=newField.querySelector('input'),
  advanced=document.createElement('details'),advancedTitle=document.createElement('summary');
  advanced.className='shul-contact-editor';advancedTitle.textContent=form.dataset.shulContactsLabel||'Shul contacts';advanced.appendChild(advancedTitle);root.appendChild(advanced);
  const rabbi=rabbiFields(advanced,select),assistants=assistantFields(advanced,select),gabbais=gabbaiFields(advanced,select);
  if(select.name==='weekday_shul'||select.name==='shabbos_shul')selectedShuls[select.name]=select;
  function update(){
    const adding=select.value==='__new__';newField.hidden=!adding;input.disabled=!adding;input.required=false;advanced.open=adding;
    root.classList.toggle('has-institution',Boolean(select.value));
    if(adding&&!input.value)input.focus();fillRabbi(select,rabbi,assistants);fillGabbais(select,gabbais);applySuggestion();
  }
  select.addEventListener('change',update);update();if(rabbi||gabbais)shulPickers.push({select,rabbi,assistants,gabbais,update});
});
if(shulPickers.length){
  Promise.all([
    fetch('/api/shul-rabbis',{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():{}),
    fetch('/api/shul-gabbais',{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():{})
  ]).then(([rabbis,gabbais])=>{shulRabbis=rabbis||{};shulGabbais=gabbais||{};shulPickers.forEach(item=>item.update());applyMode();}).catch(()=>{});
}
if(mode)mode.addEventListener('change',applyMode);
if(person)person.addEventListener('change',applyCanonical);
if(familyRabbi)familyRabbi.addEventListener('input',markManual);
if(familyRabbiPhone)familyRabbiPhone.addEventListener('input',markManual);
applyMode();
})();
