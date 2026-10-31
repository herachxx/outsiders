'use strict';
// Operator console: server-backed, with no localStorage of player requests.
const $=id=>document.getElementById(id);
const labels={
 'complaint.insult':'Оскорбления в чате','complaint.cheat':'Подозрение на читы','complaint.dm':'Нарушение игровых правил',
 'complaint.scam':'Мошенничество','complaint.rmt_ads':'Продажа игровой валюты','complaint.admin':'Жалоба на администратора',
 'complaint.other':'Другая жалоба','complaint.invalid':'Недостаточно данных','report.question':'Вопрос об игре',
 'report.help':'Помощь по игре','report.complaint':'Обращение','report.account':'Аккаунт и безопасность',
 'report.payment':'Платёж и покупки','report.offtopic':'Другой вопрос','unclassified':'Ручная классификация'
};
const statuses={new:'Новое',in_review:'В работе',needs_info:'Нужны сведения',escalated:'На проверке',resolved:'Решено',closed:'Закрыто'};
const reasonLabels={
 history_unavailable:'История недоступна',policy_draft:'Предварительный ответ без решения',
 mandatory_human:'Обязательная проверка оператором',critical_review:'Приоритетная проверка',
 complaint_human_review:'Жалоба требует проверки',evidence_not_verified:'Материалы не проверены',
 no_verified_rule:'Нет подтверждённой цитаты',history_unavailable:'История обращений недоступна',
 language_uncertain:'Язык требует уточнения',language_mixed:'Смешанные языки',
 classifier_uncalibrated:'Оценка модели не калибрована',classifier_fallback:'Резервная классификация',
 rules_unavailable:'База правил не загружена',manual_triage_required:'Нужна ручная классификация',topic_selected_by_player:'Тема выбрана игроком, ещё не проверена',
 classifier_calibrated:'Калиброванная классификация',rule_ambiguous_or_unknown:'Неоднозначный пункт правил',
 rule_irrelevant_to_category:'Пункт не относится к теме',unverified_rule:'Непроверенный пункт правил',
 sensitive_category_override:'Усиленная проверка чувствительной категории'
};
const P_ORDER=['p0','p1','p2','p3'];
let queue=[],current=null,csrf='',activeFilter='all',query='',approvedText=null,loading=false,totalCount=0,activeTab='summary';
const PAGE_SIZE=60;
function label(code){return labels[code]||code||'Обращение';}
function notify(value,type='success'){
 if(!value)return;
 const region=$('toast-region');const card=document.createElement('div');card.className='toast '+(type==='error'?'error':'success');card.setAttribute('role',type==='error'?'alert':'status');
 const message=text('span',value,'toast-message');const dismiss=document.createElement('button');dismiss.type='button';dismiss.setAttribute('aria-label','Закрыть уведомление');const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-close');icon.append(use);dismiss.append(icon);dismiss.addEventListener('click',()=>{clearTimeout(timer);card.remove()});card.append(message,dismiss);region.append(card);
 while(region.children.length>3)region.firstElementChild.remove();const timer=setTimeout(()=>card.remove(),5200);
}
function text(tag,value,cls){const el=document.createElement(tag);el.textContent=String(value??'');if(cls)el.className=cls;return el;}
function when(iso){if(!iso)return '—';const d=new Date(iso);return Number.isNaN(d.getTime())?'—':d.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});}
async function http(path,{method='GET',body}={}){
 const headers={'Accept':'application/json'};
 if(body!==undefined)headers['Content-Type']='application/json';
 if(method!=='GET')headers['X-CSRF-Token']=csrf;
 let response;
 try{response=await fetch(path,{method,headers,credentials:'same-origin',body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});}catch{throw Error('Сеть недоступна. Проверьте подключение к серверу.');}
 if(response.status===401){location.replace('/admin/login');throw Error('Сессия завершена. Войдите снова.');}
 if(!response.ok){let details;try{details=(await response.json()).detail;}catch{}throw Error(typeof details==='string'?details:`Ошибка сервера: ${response.status}`);}
 return response.json();
}
function filtered(){return queue.filter(item=>{
 const r=item.result||{};
 if(activeFilter==='human'&&!r.needs_human&&item.status!=='escalated')return false;
 if(activeFilter==='p0'&&!['p0','p1'].includes(r.priority))return false;
 if(query&&!`${item.id} ${JSON.stringify(item.request||{})} ${label(r.category)}`.toLowerCase().includes(query))return false;
 return true;
 }).sort((a,b)=>(P_ORDER.indexOf(a.result.priority)+4)%4-(P_ORDER.indexOf(b.result.priority)+4)%4);}
function renderQueue(){
 $('count').textContent=totalCount;$('all-count').textContent=totalCount;
 const list=$('queue');list.replaceChildren();
 for(const item of filtered()){
 const button=document.createElement('button');button.type='button';button.className='queue-item'+(item.id===current?.id?' active':'');
 button.setAttribute('aria-current',item.id===current?.id?'true':'false');
 const head=text('div','','queue-top');head.append(text('span','#'+item.id,'queue-id'),text('span',when(item.created_at),'queue-time'));button.append(head);
 button.append(text('span',label(item.result.category),'queue-name'));
 const bottom=text('div','','queue-bottom');bottom.append(text('span',`${item.request.region||'Сервер не указан'} · ${statuses[item.status]||'—'}`,'queue-info'));
 bottom.append(text('span',(item.result.priority||'p2').toUpperCase(),'tag '+(item.result.priority||'p2')));button.append(bottom);
 button.addEventListener('click',()=>{if(current&&$('draft').value!==current.draft_text){notify('Сохраните изменения черновика перед переходом.','error');switchTab('reply');return;}const different=current?.id!==item.id;select(item);if(different)switchTab('summary');document.querySelector('.app-layout').classList.add('show-case');});list.append(button);
 }
 if(!list.children.length)list.append(text('p','Нет обращений по выбранным условиям.','list-empty'));
 $('load-more').hidden=queue.length>=totalCount;
}
async function reload(keep=true,append=false){
 if(current && $('draft').value!==current.draft_text)throw Error('Сохраните черновик перед обновлением очереди.');
 const selected=keep?current?.id:null;
 const params=new URLSearchParams({limit:String(PAGE_SIZE),offset:String(append?queue.length:0)});
 if(query)params.set('q',query);
 if(activeFilter==='human')params.set('human','true');
 if(activeFilter==='p0')params.set('priority','urgent');
 const data=await http('/admin/api/tickets?'+params.toString());
 totalCount=data.total;queue=append?queue.concat(data.items):data.items;
 if(selected)current=queue.find(x=>x.id===selected)||queue[0]||null;
 else current=queue[0]||null;
 if(current)select(current);else{renderQueue();$('empty').hidden=false;$('ticket').hidden=true;$('decision-content').hidden=true;$('decision-empty').hidden=false;}

}
async function loadAttachments(id){
 const wrap=$('attachment-section'),list=$('attachment-list');wrap.hidden=true;list.replaceChildren();
 try{
  const data=await http(`/admin/api/tickets/${encodeURIComponent(id)}/attachments`);
  if(current?.id!==id)return;
  if(!data.items.length){wrap.hidden=true;return;}
  wrap.hidden=false;
  for(const attachment of data.items){
    const a=document.createElement('a');a.className='attachment-link';
    a.href=`/admin/api/tickets/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachment.id)}`;
    a.target='_blank';a.rel='noopener noreferrer';a.setAttribute('download',attachment.filename);
    a.append(text('span','Снимок экрана · '+Math.ceil(attachment.size/1024)+' КБ'),text('span','Скачать для проверки'));
    list.append(a);
  }
 }catch(error){if(current?.id===id)notify('Не удалось получить вложения: '+error.message);}
}
async function loadAudit(){
 if(!current)return;const id=current.id,root=$('audit-events');
 try{const response=await http(`/admin/api/tickets/${encodeURIComponent(id)}/audit`);if(current?.id!==id)return;
 root.replaceChildren();for(const ev of response.events){const actionName={created:'Создано обращение',status_changed:'Изменён статус',draft_updated:'Изменён черновик',draft_verified:'Проверен ответ',attachment_added:'Добавлено вложение',escalated:'Передано на проверку'}[ev.action]||ev.action;const actorName={player:'Игрок',operator:'Оператор'}[ev.actor]||ev.actor;const line=text('div',`${when(ev.occurred_at)} · ${actionName} · ${actorName}`,'audit-line');root.append(line);}
 if(!response.events.length)root.textContent='Нет изменений';
 }catch(error){root.textContent=error.message;}
}
function select(item){
 current=item;approvedText=item.draft_approved?item.draft_text:null;
 $('empty').hidden=true;$('ticket').hidden=false;$('decision-empty').hidden=true;$('decision-content').hidden=false;
 const title=label(item.result.category);$('ticket-id').textContent=item.id;$('case-title').textContent=title;
 $('case-subtitle').textContent=`${statuses[item.status]||'—'} · ${when(item.created_at)}`;
 $('priority').textContent=(item.result.priority||'p2').toUpperCase();$('priority').dataset.level=item.result.priority;
 $('category').textContent=title;$('meta-server').textContent=item.request.region||'Не указан';
 $('meta-lang').textContent=(item.result.lang||'—').toUpperCase();$('meta-attachments').textContent=String(item.request.images_count||0);
 // Preserve all player messages; never show historical admin verdicts as player facts.
 $('original').textContent=(item.request.messages||[]).filter(x=>x.role==='player').map(x=>x.text).join('\n\n');
 $('reported-line').hidden=!item.request.reported_nick;
 $('reported-line').textContent=item.request.reported_nick?'Указанный игрок: '+item.request.reported_nick:'';
 const facts=item.result.extracted?.claims||[];$('claims-count').textContent=facts.length+' пунктов';
 $('claims').replaceChildren();for(const fact of facts)$('claims').append(text('li',fact));
 const refs=item.result.draft_reply?.cited||[];$('citations').replaceChildren();
 if(!refs.length)$('citations').append(text('p','Проверенных цитат правил нет.','empty-cites'));
 for(const cite of refs){const box=text('div','','citation');box.append(text('span','Пункт '+cite.ref,'citation-ref'),text('span',cite.excerpt||'—'));
 box.append(text('small',`Раздел ${cite.section_id} · хеш ${String(cite.rules_hash||'').slice(0,12)}…`));$('citations').append(box);}
 $('reasons').replaceChildren();for(const reason of item.result.reasons||[])$('reasons').append(text('li',reasonLabels[reason]||reason.replaceAll('_',' ')));
 $('human-state').textContent=item.result.needs_human?'Требуется человек':'Предварительная обработка';
 $('human-details').textContent=item.result.needs_human?'Решение принимает оператор':'Проверьте черновик перед использованием';
 $('decision-category').textContent=title;$('decision-priority').textContent=(item.result.priority||'p2').toUpperCase();
 $('ticket-status').value=item.status;$('status-note').value='';
 $('draft').value=item.draft_text||'';$('draft').disabled=['resolved','closed'].includes(item.status);
 $('copy').disabled=!approvedText;$('check').disabled=['resolved','closed'].includes(item.status);
 $('save').disabled=['resolved','closed'].includes(item.status);
 $('draft-state').textContent=item.draft_approved?'Проверен на сервере':'Требуется проверка';
 $('draft-length').textContent=$('draft').value.length+' символов';
 $('attachment-tab-count').textContent=(item.request.images_count||0)?'('+item.request.images_count+')':'';
 $('facts-section').hidden=!facts.length;
 renderQueue();void loadAttachments(item.id);if($('audit-details').open)void loadAudit();
}
function changed(){approvedText=null;$('copy').disabled=true;$('draft-state').textContent='Есть несохранённые изменения';
 $('draft-length').textContent=$('draft').value.length+' символов';}
async function saveDraft(){if(!current)throw Error('Выберите обращение');
 if($('draft').value===current.draft_text)return current;
 const ticket=await http(`/admin/api/tickets/${encodeURIComponent(current.id)}/draft`,{method:'PUT',body:{version:current.version,text:$('draft').value}});
 current=ticket;queue=queue.map(t=>t.id===ticket.id?ticket:t);select(ticket);return ticket;
}
async function action(task){if(loading)return;loading=true;try{await task();}catch(error){notify(error.message);if(/измен|changed|reload/i.test(error.message))await reload();}finally{loading=false;}}
$('save').addEventListener('click',()=>action(async()=>{await saveDraft();notify('Черновик сохранён на сервере.');}));
$('check').addEventListener('click',()=>action(async()=>{
 const item=await saveDraft();const checked=await http(`/admin/api/tickets/${encodeURIComponent(item.id)}/verify`,{method:'POST',body:{version:item.version}});
 if(checked.approved){queue=queue.map(t=>t.id===item.id?checked.ticket:t);select(checked.ticket);notify('Черновик проверен. Можно скопировать ответ.');}
 else{approvedText=null;$('copy').disabled=true;$('draft-state').textContent='Не прошёл проверку';notify('Не пройдена проверка: '+checked.reasons.join(', '));}
}));
$('copy').addEventListener('click',()=>action(async()=>{
 if(!current?.draft_approved||current.draft_text!==$('draft').value)throw Error('Сначала проверьте черновик');
 await navigator.clipboard.writeText(current.draft_text);notify('Проверенный ответ скопирован. В Grand Mobile ничего не отправлено.');
}));
$('restore').addEventListener('click',()=>{if(!current)return;$('draft').value=current.result.draft_reply?.text||'';changed();});
$('draft').addEventListener('input',changed);
async function setStatus(status){
 if(!current)throw Error('Выберите обращение');if($('draft').value!==current.draft_text)throw Error('Сначала сохраните правки черновика.');
 const item=await http(`/admin/api/tickets/${encodeURIComponent(current.id)}/status`,{method:'POST',body:{version:current.version,status,note:$('status-note').value.trim()}});
 queue=queue.map(t=>t.id===item.id?item:t);select(item);await loadAudit();notify('Статус обращения обновлён и записан в журнал.');
}
$('apply-status').addEventListener('click',()=>action(()=>setStatus($('ticket-status').value)));
$('escalate').addEventListener('click',()=>action(()=>setStatus('escalated')));
$('audit-details').addEventListener('toggle',()=>{if($('audit-details').open&&activeTab==='history')void loadAudit();});
$('refresh').addEventListener('click',()=>action(async()=>{if(current&&$('draft').value!==current.draft_text)throw Error('Сначала сохраните изменения черновика.');await reload();notify('Очередь обновлена.');}));
$('load-more').addEventListener('click',()=>action(()=>reload(true,true)));
let searchTimer; $('search').addEventListener('input',event=>{query=event.target.value.toLowerCase().trim();clearTimeout(searchTimer);searchTimer=setTimeout(()=>void action(()=>reload(false)),240);});
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{
 activeFilter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===button));void action(()=>reload(false));
}));
function openDialog(){$('dialog-backdrop').hidden=false;$('message').focus();}
function closeDialog(){$('dialog-backdrop').hidden=true;$('open-new').focus();}
$('open-new').addEventListener('click',openDialog);
$('empty-demo').addEventListener('click',openDialog);$('close-new').addEventListener('click',closeDialog);$('cancel-new').addEventListener('click',closeDialog);
$('dialog-backdrop').addEventListener('click',e=>{if(e.target===$('dialog-backdrop'))closeDialog();});
window.addEventListener('keydown',e=>{
 if(e.key==='Escape'&&!$('dialog-backdrop').hidden)closeDialog();
 if(e.key==='/'&&$('dialog-backdrop').hidden&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){e.preventDefault();$('search').focus();}
});
$('ticket-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
 $('analyze').disabled=true;
 try{
 const request={kind:$('kind').value,messages:[{role:'player',text:$('message').value.trim()}],region:$('region').value.trim()||null,
 reported_nick:$('nickname').value.trim()||null,rule_refs_raw:$('rule-refs').value.trim()||null,images_count:0};
 const item=await http('/admin/api/tickets',{method:'POST',body:{request}});
 await reload(false);closeDialog();select(item);switchTab('summary');document.querySelector('.app-layout').classList.add('show-case');notify('Обращение создано.');
 }finally{$('analyze').disabled=false;}
});});
$('logout').addEventListener('click',()=>action(async()=>{await http('/admin/api/logout',{method:'POST'});location.replace('/admin/login');}));
$('rail-help').addEventListener('click',()=>notify('Выберите обращение слева. Ответ редактируется во вкладке «Ответ и статус».'));
window.addEventListener('beforeunload',event=>{if(current&&$('draft').value!==current.draft_text){event.preventDefault();event.returnValue='';}});

function switchTab(name){
 if(!['summary','reply','details','history'].includes(name))return;
 activeTab=name;
 document.querySelectorAll('[data-tab]').forEach(button=>{const selected=button.dataset.tab===name;button.classList.toggle('active',selected);button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;});
 for(const tab of ['summary','reply','details','history'])$('panel-'+tab).hidden=tab!==name;
 $('case-pane').scrollTop=0;
 if(name==='history'&&current)void loadAudit();
 if(name==='details'&&current)void loadAttachments(current.id);
}
document.querySelectorAll('[data-tab]').forEach(button=>{
 button.addEventListener('click',()=>switchTab(button.dataset.tab));
 button.setAttribute('aria-controls','panel-'+button.dataset.tab);
 button.addEventListener('keydown',event=>{
  const order=['summary','reply','details','history'];const index=order.indexOf(button.dataset.tab);let next;
  if(event.key==='ArrowRight')next=order[(index+1)%order.length];
  if(event.key==='ArrowLeft')next=order[(index+order.length-1)%order.length];
  if(event.key==='Home')next=order[0];
  if(event.key==='End')next=order[order.length-1];
  if(!next)return;event.preventDefault();switchTab(next);$('tab-'+next).focus();
 });
});
$('to-reply').addEventListener('click',()=>switchTab('reply'));
$('to-details').addEventListener('click',()=>switchTab('details'));
$('mobile-back').addEventListener('click',()=>document.querySelector('.app-layout').classList.remove('show-case'));

(async()=>{
 try{
 const session=await http('/admin/api/session');csrf=session.csrf;
 await reload(false);
 }catch(error){notify(error.message,'error');}
})();
