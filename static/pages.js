(()=>{'use strict';document.querySelectorAll('[data-print]').forEach(button=>button.addEventListener('click',()=>window.print()));document.querySelectorAll('form[data-stripe-checkout]').forEach(form=>form.addEventListener('submit',()=>{const button=form.querySelector('button[type="submit"]');if(button)button.textContent=button.dataset.loadingText;}));const main=document.querySelector('main');if(!main||document.querySelector('#intake-wizard')||document.body.dataset.printReport)return;const labels=document.body.dataset;
// Profile sections become individually reachable panels, rather than a long page.
const candidates=[...main.children].filter(el=>el.matches('section.card')&&el.querySelector('h2'));
const payoutHeading=[...main.querySelectorAll('h2')].find(heading=>heading.textContent.trim()==='Create applicant check'||heading.closest('section')?.querySelector('form[action$="/payouts/checks"]'));
const payoutForm=payoutHeading?.closest('section')?.querySelector('form[action$="/payouts/checks"]'),payoutFamily=payoutForm?.querySelector('select[name="family_id"]');
if(payoutFamily){const balances=new Map();main.querySelectorAll('table tbody tr').forEach(row=>{const reference=row.querySelector('td:first-child small')?.textContent.trim(),cells=row.querySelectorAll('td');if(reference?.startsWith('YZ-')&&cells.length===4)balances.set(reference,cells[3].textContent.trim());});const display=document.createElement('span'),caption=document.createElement('small'),value=document.createElement('strong');display.className='selected-family-funds';display.hidden=true;display.setAttribute('aria-live','polite');caption.textContent=[...main.querySelectorAll('th')].find(th=>th.textContent.trim()&&th.cellIndex===3)?.textContent.trim()||'Available to give out';display.append(caption,value);payoutFamily.after(display);const update=()=>{const reference=payoutFamily.selectedOptions[0]?.textContent.match(/YZ-\d+/)?.[0],available=balances.get(reference);value.textContent=available||'';display.hidden=!available;};payoutFamily.addEventListener('change',update);update();}
const supporterFamily=document.getElementById('supporter-family'),supporterParent=document.getElementById('new-parent-contact');
document.querySelectorAll('form[data-auto-submit-filters]').forEach(form=>form.querySelectorAll('select').forEach(select=>select.addEventListener('change',()=>form.requestSubmit())));
if(supporterFamily&&supporterParent){const filterParents=()=>{supporterFamily.form.action=`/families/${supporterFamily.value}/contacts`;for(const option of supporterParent.options){if(option.dataset.familyId)option.hidden=option.dataset.familyId!==supporterFamily.value}if(supporterParent.selectedOptions[0]?.hidden)supporterParent.value='';};supporterFamily.addEventListener('change',filterParents);filterParents();}
document.querySelectorAll('[data-select-filter]').forEach(search=>{const select=document.getElementById(search.dataset.selectFilter);if(!select)return;const results=document.createElement('div');results.className='select-search-results';results.hidden=true;search.after(results);select.classList.add('select-search-source');search.setAttribute('role','combobox');search.setAttribute('aria-autocomplete','list');search.setAttribute('aria-expanded','false');const matchingOptions=()=>{const query=search.value.trim().toLocaleLowerCase();return [...select.options].filter(option=>{const wrongFamily=supporterFamily&&select===supporterParent&&option.dataset.familyId&&option.dataset.familyId!==supporterFamily.value;return !wrongFamily&&(!query||option.textContent.toLocaleLowerCase().includes(query));});};const close=()=>{results.hidden=true;search.setAttribute('aria-expanded','false');};const render=()=>{const options=matchingOptions();results.replaceChildren(...options.map(option=>{const button=document.createElement('button');button.type='button';button.textContent=option.textContent.trim();button.className=option.value===select.value?'selected':'';button.addEventListener('mousedown',event=>event.preventDefault());button.addEventListener('click',()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));search.value=option.value?option.textContent.trim():'';close();});return button;}));results.hidden=false;search.setAttribute('aria-expanded','true');};search.addEventListener('focus',render);search.addEventListener('input',()=>{select.value='';render();});search.addEventListener('keydown',event=>{if(event.key==='Escape')close();});search.addEventListener('blur',()=>setTimeout(close,120));supporterFamily?.addEventListener('change',()=>{search.value='';select.value='';close();});});
if(candidates.length>1){document.body.dataset.pageTabs='true';const nav=document.createElement('nav');nav.className='page-panels';nav.setAttribute('aria-label',labels.sections);const controls=candidates.map((section,i)=>{const directUrl=section.dataset.panelHref;if(directUrl){const a=document.createElement('a');a.href=directUrl;a.textContent=section.querySelector('h2').textContent;nav.append(a);return a;}const b=document.createElement('button');b.type='button';b.textContent=section.querySelector('h2').textContent;b.onclick=()=>{candidates.forEach((p,n)=>p.hidden=n!==i);controls.forEach((p,n)=>{p.classList.toggle('selected',n===i);if(p.tagName==='BUTTON')p.setAttribute('aria-pressed',String(n===i));});window.dispatchEvent(new Event('resize'));};nav.append(b);return b;});candidates[0].before(nav);const requestedPanel=Number(new URLSearchParams(location.search).get('panel'));const firstPanel=controls[candidates.findIndex(s=>s.dataset.initialPanel==='true')]||(requestedPanel>0?controls[requestedPanel-1]:null)||controls.find(control=>control.tagName==='BUTTON');if(firstPanel)firstPanel.click();}
// Choose a page size from the actual viewport, leaving room for pager and footer.
main.querySelectorAll('table:not([data-server-paged])').forEach(table=>{const body=table.tBodies[0];if(!body)return;const rows=[...body.rows];if(rows.length<2)return;let page=0,size=6;const pager=document.createElement('div');pager.className='table-pager';const prev=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span');prev.type=next.type='button';prev.textContent=labels.previous;next.textContent=labels.next;count.setAttribute('aria-live','polite');pager.append(prev,count,next);(table.parentElement.classList.contains('table-wrap')?table.parentElement:table).after(pager);
function draw(){if(!table.getClientRects().length)return;rows.forEach(r=>r.hidden=false);const top=body.getBoundingClientRect().top;const overview=table.closest('.overview-grid');const reserve=overview&&overview.nextElementSibling?overview.nextElementSibling.getBoundingClientRect().height+20:0;const height=Math.max(...rows.map(r=>r.getBoundingClientRect().height),40);size=Math.max(1,Math.min(12,Math.floor((window.innerHeight-top-100-reserve)/height)));const pages=Math.ceil(rows.length/size);page=Math.min(page,pages-1);rows.forEach((r,i)=>r.hidden=i<page*size||i>=(page+1)*size);pager.hidden=pages<=1;prev.disabled=page===0;next.disabled=page===pages-1;count.textContent=`${page+1} / ${pages} · ${rows.length}`;}
prev.onclick=()=>{page--;draw();};next.onclick=()=>{page++;draw();};window.addEventListener('resize',draw);table.closest('details')?.addEventListener('toggle',draw);draw();});
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
if(supporterEmailBody&&supporterEmailSubject&&supporterEmailPreviewBody&&supporterEmailPreviewSubject){
  const updateSupporterEmailPreview=()=>{
    supporterEmailPreviewSubject.textContent=supporterEmailSubject.value||'—';
    supporterEmailPreviewBody.replaceChildren(...supporterEmailBody.value.split(/\n\s*\n/).filter(Boolean).map(text=>{
      const paragraph=document.createElement('p');
      paragraph.textContent=text;
      return paragraph;
    }));
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
