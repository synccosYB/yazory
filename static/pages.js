(()=>{'use strict';document.querySelectorAll('[data-print]').forEach(button=>button.addEventListener('click',()=>window.print()));document.querySelectorAll('form[data-stripe-checkout]').forEach(form=>form.addEventListener('submit',()=>{const button=form.querySelector('button[type="submit"]');if(button)button.textContent=button.dataset.loadingText;}));const main=document.querySelector('main');if(!main||document.querySelector('#intake-wizard')||document.body.dataset.printReport)return;const labels=document.body.dataset;
// Profile sections become individually reachable panels, rather than a long page.
const candidates=[...main.children].filter(el=>el.matches('section.card')&&el.querySelector('h2'));
const profileStatus=document.querySelector('.profile-status-control select[name="status"]');
const profileDenialReason=document.querySelector('.profile-status-control textarea[name="denial_reason"]')?.closest('label');
if(profileStatus&&profileDenialReason){const updateDenialReason=()=>{profileDenialReason.hidden=profileStatus.value!=='Declined';};profileStatus.addEventListener('change',updateDenialReason);updateDenialReason();}
const payoutHeading=[...main.querySelectorAll('h2')].find(heading=>heading.textContent.trim()==='Create applicant check'||heading.closest('section')?.querySelector('form[action$="/payouts/checks"]'));
const payoutForm=payoutHeading?.closest('section')?.querySelector('form[action$="/payouts/checks"]'),payoutFamily=payoutForm?.querySelector('select[name="family_id"]');
if(payoutFamily){const balances=new Map();main.querySelectorAll('table tbody tr').forEach(row=>{const reference=row.querySelector('td:first-child small')?.textContent.trim(),cells=row.querySelectorAll('td');if(reference?.startsWith('YZ-')&&cells.length===4)balances.set(reference,cells[3].textContent.trim());});const display=document.createElement('span'),caption=document.createElement('small'),value=document.createElement('strong');display.className='selected-family-funds';display.hidden=true;display.setAttribute('aria-live','polite');caption.textContent=[...main.querySelectorAll('th')].find(th=>th.textContent.trim()&&th.cellIndex===3)?.textContent.trim()||'Available to give out';display.append(caption,value);payoutFamily.after(display);const update=()=>{const reference=payoutFamily.selectedOptions[0]?.textContent.match(/YZ-\d+/)?.[0],available=balances.get(reference);value.textContent=available||'';display.hidden=!available;};payoutFamily.addEventListener('change',update);update();}
const supporterFamily=document.getElementById('supporter-family'),supporterParent=document.getElementById('new-parent-contact');
document.querySelectorAll('form[data-auto-submit-filters]').forEach(form=>form.querySelectorAll('select').forEach(select=>select.addEventListener('change',()=>form.requestSubmit())));
if(supporterFamily&&supporterParent){const filterParents=()=>{supporterFamily.form.action=`/families/${supporterFamily.value}/contacts`;for(const option of supporterParent.options){if(option.dataset.familyId)option.hidden=option.dataset.familyId!==supporterFamily.value}if(supporterParent.selectedOptions[0]?.hidden)supporterParent.value='';};supporterFamily.addEventListener('change',filterParents);filterParents();}
const connectSupporterFamily=document.getElementById('connect-supporter-family'),connectSupporterParent=document.getElementById('connect-supporter-parent'),connectSupporterInstitution=document.getElementById('connect-supporter-institution');
if(connectSupporterFamily){const filterConnectOptions=()=>{for(const select of [connectSupporterParent,connectSupporterInstitution]){if(!select)continue;for(const option of select.options){if(option.dataset.familyId)option.hidden=option.dataset.familyId!==connectSupporterFamily.value}if(select.selectedOptions[0]?.hidden)select.value='';}};connectSupporterFamily.addEventListener('change',filterConnectOptions);filterConnectOptions();}
document.querySelectorAll('[data-select-filter]').forEach(search=>{const select=document.getElementById(search.dataset.selectFilter);if(!select)return;const results=document.createElement('div');results.className='select-search-results';results.hidden=true;search.after(results);select.classList.add('select-search-source');search.setAttribute('role','combobox');search.setAttribute('aria-autocomplete','list');search.setAttribute('aria-expanded','false');const matchingOptions=()=>{const query=search.value.trim().toLocaleLowerCase();return [...select.options].filter(option=>{const wrongFamily=supporterFamily&&select===supporterParent&&option.dataset.familyId&&option.dataset.familyId!==supporterFamily.value;const wrongConnectFamily=connectSupporterFamily&&select===connectSupporterParent&&option.dataset.familyId&&option.dataset.familyId!==connectSupporterFamily.value;return !wrongFamily&&!wrongConnectFamily&&(!query||option.textContent.toLocaleLowerCase().includes(query));});};const close=()=>{results.hidden=true;search.setAttribute('aria-expanded','false');};const render=()=>{const options=matchingOptions();results.replaceChildren(...options.map(option=>{const button=document.createElement('button');button.type='button';button.textContent=option.textContent.trim();button.className=option.value===select.value?'selected':'';button.addEventListener('mousedown',event=>event.preventDefault());button.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));search.value=option.value?option.textContent.trim():'';close();});return button;}));results.hidden=false;search.setAttribute('aria-expanded','true');};search.addEventListener('focus',render);search.addEventListener('input',()=>{select.value='';render();});search.addEventListener('keydown',event=>{if(event.key==='Escape')close();});search.addEventListener('blur',()=>setTimeout(close,120));supporterFamily?.addEventListener('change',()=>{search.value='';select.value='';close();});connectSupporterFamily?.addEventListener('change',()=>{if(select===connectSupporterParent){search.value='';select.value='';close();}});});

const editParent=document.getElementById('parent-contact');
const editParentConnection=document.getElementById('parent-connection');
if(editParent&&editParentConnection){
  const requireParentConnection=()=>{editParentConnection.required=Boolean(editParent.value);};
  editParent.addEventListener('change',requireParentConnection);
  requireParentConnection();
}
if(candidates.length>1){document.body.dataset.pageTabs='true';const nav=document.createElement('nav');nav.className='page-panels';nav.setAttribute('aria-label',labels.sections);const controls=candidates.map((section,i)=>{const directUrl=section.dataset.panelHref;if(directUrl){const a=document.createElement('a');a.href=directUrl;a.textContent=section.querySelector('h2').textContent;nav.append(a);return a;}const b=document.createElement('button');b.type='button';b.textContent=section.querySelector('h2').textContent;b.onclick=()=>{candidates.forEach((p,n)=>p.hidden=n!==i);controls.forEach((p,n)=>{p.classList.toggle('selected',n===i);if(p.tagName==='BUTTON')p.setAttribute('aria-pressed',String(n===i));});window.dispatchEvent(new Event('resize'));};nav.append(b);return b;});candidates[0].before(nav);const requestedPanel=Number(new URLSearchParams(location.search).get('panel'));const firstPanel=controls[candidates.findIndex(s=>s.dataset.initialPanel==='true')]||(requestedPanel>0?controls[requestedPanel-1]:null)||controls.find(control=>control.tagName==='BUTTON');if(firstPanel)firstPanel.click();}
const familySupporterTable=[...main.querySelectorAll('table')].find(table=>table.querySelector('form[action^="/contacts/"]')&&table.closest('section')?.querySelector('.supporter-summary-heading'));
if(familySupporterTable){familySupporterTable.id='family-supporters-table';familySupporterTable.classList.add('family-supporters-table');let compactedActions=false;for(const row of familySupporterTable.tBodies[0]?.rows||[]){const phoneCell=row.cells[2],digits=phoneCell?.textContent.replace(/\D/g,'');if(digits?.length===10){phoneCell.textContent=`(${digits.slice(0,3)}) ${digits.slice(3,6)}-${digits.slice(6)}`;phoneCell.dir='ltr';}const editCell=row.cells[4],editLink=editCell?.querySelector('a'),nameBox=row.cells[0]?.querySelector('.supporter-name');if(editLink&&nameBox){const editLabel=editLink.textContent.trim(),supporterName=nameBox.querySelector('a')?.textContent.trim()||'';editLink.className='supporter-row-edit';editLink.textContent='✎';editLink.title=editLabel;editLink.setAttribute('aria-label',`${editLabel} — ${supporterName}`);nameBox.querySelector('a')?.after(editLink);editCell.remove();compactedActions=true;}}if(compactedActions)familySupporterTable.tHead?.rows[0]?.lastElementChild?.remove();const heading=familySupporterTable.closest('section')?.querySelector('.supporter-summary-heading');if(heading){const search=document.createElement('input'),label=document.documentElement.lang==='yi'?'זוכן העלפער':document.documentElement.lang==='he'?'חיפוש תומכים':'Search supporters',count=heading.lastElementChild;search.type='search';search.placeholder=label;search.setAttribute('aria-label',label);search.autocomplete='off';search.dataset.tableSearch=familySupporterTable.id;count?.classList.add('family-supporter-count');const tools=document.createElement('div');tools.className='family-supporter-tools';heading.append(tools);if(count)tools.append(count);tools.append(search);}}
document.querySelectorAll('[data-table-search]').forEach(search=>{const table=document.getElementById(search.dataset.tableSearch),body=table?.tBodies[0];if(!body)return;const rows=[...body.rows];search.addEventListener('input',()=>{const query=search.value.trim().toLocaleLowerCase();rows.forEach(row=>row.dataset.searchMatch=String(row.dataset.metricMatch!=='false'&&(!query||row.textContent.toLocaleLowerCase().includes(query))));table.dispatchEvent(new Event('table-search'));});});
document.querySelectorAll('[data-accordion-search]').forEach(search=>{const list=document.getElementById(search.dataset.accordionSearch);if(!list)return;const items=[...list.querySelectorAll(':scope > .communication-accordion-item')];search.addEventListener('input',()=>{const query=search.value.trim().toLocaleLowerCase();items.forEach(item=>item.hidden=item.dataset.metricMatch==='false'||Boolean(query&&!item.textContent.toLocaleLowerCase().includes(query)));});});
document.querySelectorAll('[data-list-search]').forEach(search=>{const list=document.getElementById(search.dataset.listSearch);if(!list)return;const items=[...list.querySelectorAll(':scope > [data-list-item]')];search.addEventListener('input',()=>{const query=search.value.trim().toLocaleLowerCase();items.forEach(item=>item.hidden=Boolean(query&&!item.textContent.toLocaleLowerCase().includes(query)));});});
const communicationMetricData=document.getElementById('communication-callbacks'),communicationTable=document.getElementById('communications-supporters-list'),communicationSearch=document.querySelector('[data-accordion-search="communications-supporters-list"]');
const mailboxSearch=document.querySelector('[data-mailbox-search]'),mailboxList=document.querySelector('[data-mailbox-list]'),mailboxListFold=mailboxList?.closest('.mailbox-list-fold');if(mailboxSearch&&mailboxList){mailboxSearch.addEventListener('input',()=>{if(mailboxSearch.value)mailboxListFold.open=true;const query=mailboxSearch.value.trim().toLowerCase();for(const message of mailboxList.querySelectorAll('.mailbox-message'))message.hidden=query&&!message.textContent.toLowerCase().includes(query);});}const composeButton=document.querySelector('[data-mailbox-compose]'),composePanel=document.querySelector('[data-mailbox-compose-panel]'),composeClose=document.querySelector('[data-mailbox-compose-close]');if(composeButton&&composePanel){composeButton.addEventListener('click',()=>{composePanel.hidden=false;composePanel.querySelector('select')?.focus();});composeClose?.addEventListener('click',()=>{composePanel.hidden=true;});}
const mailboxFolders=[...document.querySelectorAll('[data-mailbox-folder]')];if(mailboxFolders.length&&mailboxList){const showFolder=folder=>{mailboxListFold.open=true;mailboxFolders.forEach(link=>link.classList.toggle('selected',link.dataset.mailboxFolder===folder));mailboxSearch.value='';for(const message of mailboxList.querySelectorAll('.mailbox-message')){const category=message.dataset.mailboxCategory||message.id.replace('mailbox-','');message.hidden=folder==='inbox'?category==='sent':category!==folder;}mailboxList.closest('.mailbox-main')?.scrollIntoView({behavior:'smooth',block:'start'});};mailboxFolders.forEach(link=>link.addEventListener('click',event=>{event.preventDefault();showFolder(link.dataset.mailboxFolder);}));if(location.hash==='#mailbox-sent')showFolder('sent');}
const richTextareas=document.querySelectorAll('.mailbox textarea[name="body"],#email-draft textarea[name="body"]');richTextareas.forEach(textarea=>{if(textarea.previousElementSibling?.classList.contains('email-format-toolbar'))return;const toolbar=document.createElement('div');toolbar.className='email-format-toolbar';toolbar.setAttribute('role','toolbar');toolbar.setAttribute('aria-label','Text formatting');const commands=[['B','Bold','**','**'],['I','Italic','*','*'],['U','Underline','[u]','[/u]'],['•','Bulleted list','- ',''],['1.','Numbered list','1. ',''],['🔗','Insert link','[','](https://)']];for(const [label,title,before,after] of commands){const button=document.createElement('button');button.type='button';button.textContent=label;button.title=title;button.setAttribute('aria-label',title);button.addEventListener('click',()=>{const start=textarea.selectionStart,end=textarea.selectionEnd,selected=textarea.value.slice(start,end),lineCommand=title.includes('list'),prefix=lineCommand&&(start>0&&textarea.value[start-1]!=='\n')?'\n':'';textarea.setRangeText(prefix+before+selected+after,start,end,'end');textarea.focus();textarea.dispatchEvent(new Event('input',{bubbles:true}));});toolbar.append(button);}textarea.before(toolbar);});
const revealCommunicationTarget=target=>{if(!target)return;const tools=target.closest('details.communication-tools');if(tools)tools.open=true;if(target.matches('details'))target.open=true;requestAnimationFrame(()=>{target.scrollIntoView({behavior:'smooth',block:'start'});target.focus?.({preventScroll:true});});};
document.querySelector('.mailbox-tools-link')?.addEventListener('click',event=>{const target=document.getElementById('communication-tools');if(!target)return;event.preventDefault();target.open=true;history.replaceState(null,'','#communication-tools');requestAnimationFrame(()=>target.scrollIntoView({behavior:'smooth',block:'start'}));});
if(communicationMetricData&&communicationTable&&communicationSearch){const callbackData=JSON.parse(communicationMetricData.textContent),callbackIds=new Set(callbackData.callbacks),overdueIds=new Set(callbackData.overdue),metricLinks=[...document.querySelectorAll('[data-communication-filter]')];metricLinks.forEach(link=>link.addEventListener('click',event=>{event.preventDefault();const filter=link.dataset.communicationFilter;for(const item of communicationTable.querySelectorAll(':scope > .communication-accordion-item')){const contactId=Number(item.dataset.contactId);item.dataset.metricMatch=String(filter==='all'||filter==='callbacks'&&callbackIds.has(contactId)||filter==='overdue'&&overdueIds.has(contactId));}communicationSearch.value='';communicationSearch.dispatchEvent(new Event('input'));metricLinks.forEach(item=>item.classList.toggle('selected',item===link));const section=document.getElementById('outreach-workflow');history.replaceState(null,'',link.hash);revealCommunicationTarget(section);}));document.querySelector('.communication-metrics>a:last-child')?.addEventListener('click',event=>{event.preventDefault();const section=document.getElementById('communication-history');history.replaceState(null,'',event.currentTarget.hash);revealCommunicationTarget(section);});}
const revealCommunicationHash=()=>{const target=document.getElementById(location.hash.slice(1));if(target?.closest('details.communication-tools'))revealCommunicationTarget(target);};window.addEventListener('hashchange',revealCommunicationHash);if(location.hash)revealCommunicationHash();
// The dashboard preview is already capped at six rows; keep all of them visible.
main.querySelectorAll('.dashboard-overview table').forEach(table=>table.dataset.serverPaged='');
// Choose a page size from the actual viewport, leaving room for pager and footer.
main.querySelectorAll('table:not([data-server-paged])').forEach(table=>{const body=table.tBodies[0];if(!body)return;const rows=[...body.rows];if(rows.length<2)return;let page=0,size=6;const pager=document.createElement('div');pager.className='table-pager';const prev=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span');prev.type=next.type='button';prev.textContent=labels.previous;next.textContent=labels.next;count.setAttribute('aria-live','polite');pager.append(prev,count,next);(table.parentElement.classList.contains('table-wrap')?table.parentElement:table).after(pager);
function draw(){if(!table.getClientRects().length)return;const visibleRows=rows.filter(r=>r.dataset.searchMatch!=='false');rows.forEach(r=>r.hidden=true);visibleRows.forEach(r=>r.hidden=false);const top=body.getBoundingClientRect().top;const overview=table.closest('.overview-grid');const reserve=overview&&overview.nextElementSibling?overview.nextElementSibling.getBoundingClientRect().height+20:0;const height=Math.max(40,...visibleRows.map(r=>r.getBoundingClientRect().height)),familyMinimum=table.classList.contains('family-supporters-table')?Math.min(5,visibleRows.length):1;size=Math.max(familyMinimum,Math.min(12,Math.floor((window.innerHeight-top-100-reserve)/height)));const pages=Math.max(1,Math.ceil(visibleRows.length/size));page=Math.min(page,pages-1);visibleRows.forEach((r,i)=>r.hidden=i<page*size||i>=(page+1)*size);pager.hidden=pages<=1;prev.disabled=page===0;next.disabled=page===pages-1;count.textContent=`${page+1} / ${pages} · ${visibleRows.length}`;}
prev.onclick=()=>{page--;draw();};next.onclick=()=>{page++;draw();};window.addEventListener('resize',draw);table.addEventListener('table-search',()=>{page=0;draw();});table.closest('details')?.addEventListener('toggle',draw);draw();});
main.querySelectorAll('section.card').forEach(section=>{let rows=[...section.children].filter(el=>el.matches('[data-page-item],.activity-row'));if(rows.length<2)return;let page=0;const pager=document.createElement('div');pager.className='table-pager';const prev=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span');prev.type=next.type='button';prev.textContent=labels.previous;next.textContent=labels.next;count.setAttribute('aria-live','polite');pager.append(prev,count,next);section.append(pager);function draw(){if(!section.getClientRects().length)return;rows.forEach(r=>r.hidden=false);const height=Math.max(...rows.map(r=>r.getBoundingClientRect().height+12),40),size=Math.max(1,Math.min(8,Math.floor((innerHeight-rows[0].getBoundingClientRect().top-100)/height))),pages=Math.ceil(rows.length/size);page=Math.min(page,pages-1);rows.forEach((r,i)=>r.hidden=i<page*size||i>=(page+1)*size);pager.hidden=pages<=1;prev.disabled=page===0;next.disabled=page===pages-1;count.textContent=`${page+1} / ${pages}`;}prev.onclick=()=>{page--;draw();};next.onclick=()=>{page++;draw();};window.addEventListener('resize',draw);draw();});
// Long household notes are paged rather than cut off or stretched vertically.
main.querySelectorAll('.preserve').forEach(note=>{const text=note.textContent;if(text.length<=700)return;const chunks=text.match(/[\s\S]{1,650}(?:\s|$)|[\s\S]{1,650}/g)||[text];let i=0;const pager=document.createElement('div');pager.className='table-pager';const back=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span');back.type=next.type='button';back.textContent=labels.previous;next.textContent=labels.next;pager.append(back,count,next);note.after(pager);function draw(){note.textContent=chunks[i];back.disabled=i===0;next.disabled=i===chunks.length-1;count.textContent=`${i+1} / ${chunks.length}`;}back.onclick=()=>{i--;draw();};next.onclick=()=>{i++;draw();};draw();});
})();


const manualDonationSupporter = document.querySelector('#manual-donation-supporter');
const supporterEmailBody=document.querySelector('#supporter-email-body');
const supporterEmailSubject=document.querySelector('#supporter-email-subject');
const supporterEmailPreviewBody=document.querySelector('#supporter-email-preview-body');
const supporterEmailPreviewSubject=document.querySelector('#supporter-email-preview-subject');
document.querySelectorAll('form[data-ai-email-form]').forEach(form=>form.addEventListener('submit',()=>{
  const button=form.querySelector('button[type="submit"]');
  const status=form.querySelector('[data-ai-email-status]');
  if(!button)return;
  button.disabled=true;
  button.textContent=button.dataset.loadingText;
  form.setAttribute('aria-busy','true');
  if(status)status.textContent=button.dataset.loadingText;
}));
const initialEmailDraft=document.querySelector('[data-initial-email-draft]');
if(initialEmailDraft){
  initialEmailDraft.scrollIntoView({block:'start'});
  initialEmailDraft.focus({preventScroll:true});
}

// Shared mobile application shell and table accessibility for every staff page.
(()=>{
  const sidebar=document.querySelector('.sidebar');
  const openButton=document.querySelector('[data-nav-open]');
  const closeButtons=document.querySelectorAll('[data-nav-close]');
  const backdrop=document.querySelector('.mobile-nav-backdrop');
  if(sidebar&&openButton&&backdrop){
    const setOpen=open=>{
      document.body.classList.toggle('mobile-nav-visible',open);
      openButton.setAttribute('aria-expanded',String(open));
      backdrop.hidden=!open;
      if(open)sidebar.querySelector('.mobile-nav-close')?.focus();
      else if(document.activeElement?.matches('[data-nav-close]'))openButton.focus();
    };
    openButton.addEventListener('click',()=>setOpen(true));
    closeButtons.forEach(button=>button.addEventListener('click',()=>setOpen(false)));
    sidebar.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>setOpen(false)));
    document.addEventListener('keydown',event=>{if(event.key==='Escape')setOpen(false);});
    matchMedia('(min-width: 751px)').addEventListener('change',event=>{if(event.matches)setOpen(false);});
  }

  document.querySelectorAll('.table-wrap table').forEach(table=>{
    const headings=[...table.querySelectorAll('thead th')].map(cell=>cell.textContent.trim());
    table.querySelectorAll('tbody tr').forEach(row=>{
      [...row.cells].forEach((cell,index)=>{
        if(!cell.dataset.label&&headings[index])cell.dataset.label=headings[index];
      });
    });
    table.parentElement.setAttribute('tabindex','0');
    table.parentElement.setAttribute('role','region');
  });
})();
if(supporterEmailBody&&supporterEmailSubject&&supporterEmailPreviewBody&&supporterEmailPreviewSubject){
  const formattedEmailFragment=text=>{const template=document.createElement('template'),escape=value=>value.replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),inline=value=>escape(value).replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s<>)]+)\)/g,'<a href="$2">$1</a>').replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>').replace(/\[u\]([^\n]+?)\[\/u\]/g,'<u>$1</u>');const blocks=text.split(/\n\s*\n/).filter(Boolean).map(block=>{const lines=block.split('\n'),unordered=lines.every(line=>line.startsWith('- ')),ordered=lines.every(line=>/^\d+\. /.test(line));if(unordered||ordered){const tag=unordered?'ul':'ol';return `<${tag}>${lines.map(line=>`<li>${inline(line.replace(/^(?:- |\d+\. )/,''))}</li>`).join('')}</${tag}>`;}return `<p>${inline(block).replace(/\n/g,'<br>')}</p>`;}).join('');template.innerHTML=blocks;return template.content;};
  const updateSupporterEmailPreview=()=>{
    supporterEmailPreviewSubject.textContent=supporterEmailSubject.value||'—';
    supporterEmailPreviewBody.replaceChildren(formattedEmailFragment(supporterEmailBody.value));
  };
  supporterEmailBody.addEventListener('input',updateSupporterEmailPreview);
  supporterEmailSubject.addEventListener('input',updateSupporterEmailPreview);
  updateSupporterEmailPreview();
}
const manualNewDonor = document.querySelector('#manual-new-donor');
if (manualDonationSupporter && manualNewDonor) {
  const updateManualDonorFields = () => {
    const isNew = manualDonationSupporter.value === '__new__';
    manualNewDonor.hidden = !isNew;
    manualNewDonor.querySelectorAll('input, select').forEach((field) => {
      field.required = isNew && (field.name === 'donor_name' || field.name === 'family_id');
    });
  };
  manualDonationSupporter.addEventListener('change', updateManualDonorFields);
  updateManualDonorFields();
}
document.querySelectorAll('[data-open-details]').forEach(link=>link.addEventListener('click',()=>{
  const details=document.getElementById(link.dataset.openDetails);
  if(details)details.open=true;
}));

const mailboxRecipientForm=document.querySelector('[data-mailbox-recipient-form]');
if(mailboxRecipientForm){
  mailboxRecipientForm.addEventListener('submit',event=>{
    const contact=mailboxRecipientForm.querySelector('[name="contact_id"]');
    const email=mailboxRecipientForm.querySelector('[name="recipient_email"]');
    email.setCustomValidity('');
    if(!contact.value&&!email.value.trim()){
      event.preventDefault();
      email.setCustomValidity('Choose a person or enter an email address.');
      email.reportValidity();
    }
  });
}
