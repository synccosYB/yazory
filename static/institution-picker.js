(()=>{'use strict';
let shulRabbis={},shulGabbais={};const shulPickers=[];

function phoneList(container,fieldName,phones=[]){
  const wrap=document.createElement('div');wrap.className='contact-phone-list';
  const rows=document.createElement('div');wrap.appendChild(rows);
  const add=document.createElement('button');add.type='button';add.className='small secondary';add.textContent='+ Add phone';wrap.appendChild(add);
  function addPhone(value=''){
    const row=document.createElement('div');row.className='contact-phone-row';
    const input=document.createElement('input');input.maxLength=80;input.value=value||'';if(fieldName)input.name=fieldName;
    const remove=document.createElement('button');remove.type='button';remove.className='small danger';remove.textContent='Remove';
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
  const title=document.createElement('strong');title.textContent="Rabbi's assistant / gabbai";
  const add=document.createElement('button');add.type='button';add.className='small secondary';add.textContent='+ Add rabbi assistant';
  heading.append(title,add);const rows=document.createElement('div');wrap.append(heading,rows);root.appendChild(wrap);
  function addRow(data={}){
    const row=document.createElement('div');row.className='form-grid rabbi-assistant-row';
    const nameLabel=document.createElement('label');nameLabel.textContent="Rabbi assistant / gabbai";
    const name=document.createElement('input');name.name=key+'_rabbi_assistant_name';name.maxLength=160;name.value=data.name||'';nameLabel.appendChild(name);
    const phoneLabel=document.createElement('label');phoneLabel.textContent='Assistant phone';
    const phoneHost=document.createElement('div');phoneLabel.appendChild(phoneHost);
    const hidden=document.createElement('input');hidden.type='hidden';hidden.name=key+'_rabbi_assistant_phones';
    const phones=phoneList(phoneHost,'',data.phones||(data.phone?[data.phone]:[]));
    const sync=()=>hidden.value=JSON.stringify(phones.values());phoneHost.addEventListener('input',sync);phoneHost.addEventListener('click',()=>setTimeout(sync,0));sync();
    const remove=document.createElement('button');remove.type='button';remove.className='small danger';remove.textContent='Remove assistant';remove.addEventListener('click',()=>row.remove());
    row.append(nameLabel,phoneLabel,hidden,remove);rows.appendChild(row);
  }
  add.addEventListener('click',()=>addRow());
  return {rows,addRow};
}

function rabbiFields(root,select){
  const key=select.name;if(!key.endsWith('_shul'))return null;
  const box=document.createElement('div');box.className='shul-rabbi-fields form-grid';
  const rabbiLabel=document.createElement('label');rabbiLabel.textContent='Rabbi for this shul';
  const rabbi=document.createElement('input');rabbi.name=key+'_rabbi';rabbi.maxLength=160;rabbiLabel.appendChild(rabbi);
  const phoneLabel=document.createElement('label');phoneLabel.textContent='Rabbi phone';
  const phoneHost=document.createElement('div');phoneLabel.appendChild(phoneHost);
  box.append(rabbiLabel,phoneLabel);root.appendChild(box);
  let phoneFields=phoneList(phoneHost,key+'_rabbi_phone',[]);
  return{rabbi,phoneHost,get phones(){return phoneFields;},setPhones(values){phoneHost.replaceChildren();phoneFields=phoneList(phoneHost,key+'_rabbi_phone',values||[]);}};
}

function gabbaiFields(root,select){
  const key=select.name;if(!key.endsWith('_shul'))return null;
  const wrap=document.createElement('div');wrap.className='shul-gabbai-fields';
  const heading=document.createElement('div');heading.className='section-heading';
  const title=document.createElement('strong');title.textContent='Gabbaim for this shul';
  const add=document.createElement('button');add.type='button';add.className='small secondary';add.textContent='+ Add shul gabbai';
  heading.append(title,add);const rows=document.createElement('div');wrap.append(heading,rows);root.appendChild(wrap);
  function addRow(data={}){
    const row=document.createElement('div');row.className='form-grid shul-gabbai-row';
    const nameLabel=document.createElement('label');nameLabel.textContent='Shul gabbai';
    const name=document.createElement('input');name.name=key+'_gabbai_name';name.maxLength=160;name.value=data.name||'';nameLabel.appendChild(name);
    const phoneLabel=document.createElement('label');phoneLabel.textContent='Gabbai phone';
    const phoneHost=document.createElement('div');phoneLabel.appendChild(phoneHost);
    const hidden=document.createElement('input');hidden.type='hidden';hidden.name=key+'_gabbai_phones';
    const phones=phoneList(phoneHost,'',data.phones||(data.phone?[data.phone]:[]));
    const sync=()=>hidden.value=JSON.stringify(phones.values());phoneHost.addEventListener('input',sync);phoneHost.addEventListener('click',()=>setTimeout(sync,0));sync();
    const remove=document.createElement('button');remove.type='button';remove.className='small danger';remove.textContent='Remove shul gabbai';remove.addEventListener('click',()=>row.remove());
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
  rabbi=rabbiFields(root,select),assistants=assistantFields(root,select),gabbais=gabbaiFields(root,select);
  function update(){
    const adding=select.value==='__new__';newField.hidden=!adding;input.disabled=!adding;input.required=adding;
    if(adding&&!input.value)input.focus();fillRabbi(select,rabbi,assistants);fillGabbais(select,gabbais);
  }
  select.addEventListener('change',update);update();if(rabbi||gabbais)shulPickers.push({select,rabbi,assistants,gabbais,update});
});
if(shulPickers.length){
  Promise.all([
    fetch('/api/shul-rabbis',{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():{}),
    fetch('/api/shul-gabbais',{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():{})
  ]).then(([rabbis,gabbais])=>{shulRabbis=rabbis||{};shulGabbais=gabbais||{};shulPickers.forEach(item=>item.update());}).catch(()=>{});
}
})();