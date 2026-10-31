'use strict';
const $ = id => document.getElementById(id);
const key = 'grand-support-local-v1';
const ruleLabel=document.createElement('label');ruleLabel.textContent='Пункты правил из обращения';const ruleInput=document.createElement('input');ruleInput.id='rule-refs';ruleInput.maxLength=200;ruleInput.placeholder='Например: 2.1';ruleLabel.append(ruleInput);document.querySelector('.fields').append(ruleLabel);
let queue = [], current = null, approvedText = null, checking = false;
try { const saved = JSON.parse(localStorage.getItem(key) || '[]'); if (Array.isArray(saved)) queue = saved.filter(x => x && typeof x.id === 'string' && typeof x.edit === 'string' && typeof x.request?.messages?.[0]?.text === 'string' && typeof x.result?.priority === 'string' && typeof x.result?.category === 'string' && Array.isArray(x.result.reasons) && typeof x.result.draft_reply?.text === 'string' && Array.isArray(x.result.draft_reply?.cited) && Array.isArray(x.result.extracted?.claims)); } catch { $('notice').textContent = 'Не удалось прочитать сохранённую очередь. Можно начать заново.'; }
const notify = text => { $('notice').textContent = text; };
async function api(path, body) {
  let response;
  try { response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); }
  catch { throw new Error('Сервис недоступен. Проверьте, что локальный сервер запущен.'); }
  if (!response.ok) throw new Error(response.status === 503 ? 'Правила или модель недоступны. Проверьте настройки сервера.' : 'Не удалось обработать запрос. Проверьте данные и повторите.');
  return response.json();
}
function list(id, values) { $(id).replaceChildren(...values.map(value => {const li=document.createElement('li');li.textContent=value;return li;})); }
function renderQueue() {
  $('count').textContent = queue.length;
  $('queue').replaceChildren();
  [...queue].sort((a,b)=>a.result.priority.localeCompare(b.result.priority)).forEach(item=>{
    const button=document.createElement('button');button.className='queue-item'+(item.id===current?.id?' active':'');
    button.textContent=item.result.priority.toUpperCase()+' · '+item.request.messages[0].text.slice(0,65);
    const small=document.createElement('small');small.textContent=item.escalated?'Отмечено для старшего':item.result.category;button.append(small);
    button.onclick=()=>select(item);$('queue').append(button);
  });
}
function select(item) {
  if(current) current.edit=$('draft').value;
  current=item;approvedText=null;$('copy').disabled=true;
  $('empty').hidden=true;$('ticket').hidden=false;
  $('category').textContent=item.result.category;
  $('priority').textContent=item.result.priority.toUpperCase();$('priority').dataset.level=item.result.priority;
  $('metadata').textContent='Язык: '+item.result.lang+' · Вложений: '+item.request.images_count+' · '+(item.escalated?'Отмечено для старшего':item.result.needs_human?'Требуется проверка человеком':'Черновик готов к проверке')+' · Полоса: '+({auto:'можно ответить автоматически',review:'проверка администратором',escalate:'решает администратор'}[(item.result.reasons.find(r=>r.startsWith('handling_'))||'').slice(9)]||'проверка администратором');
  $('original').textContent=item.request.messages[0].text;
  list('claims',item.result.extracted.claims);list('reasons',item.result.reasons);
  $('citations').replaceChildren();
  if(!item.result.draft_reply.cited.length) $('citations').textContent='Подтверждённых цитат нет.';
  for(const citation of item.result.draft_reply.cited) {
    const box=document.createElement('div');box.className='citation';box.textContent=citation.section_id+'/'+citation.ref+' — '+citation.excerpt;
    const hash=document.createElement('small');hash.textContent='Версия: '+citation.rules_hash;box.append(hash);$('citations').append(box);
  }
  $('draft').value=item.edit;$('draft-state').textContent='Перед копированием проверьте текст.';renderQueue();
}
$('ticket-form').onsubmit=async event=>{
  event.preventDefault();$('analyze').disabled=true;notify('Разбираем обращение…');
  const request={kind:$('kind').value,messages:[{role:'player',text:$('message').value}],images_count:Number($('images').value),region:$('region').value||null,reported_nick:$('nickname').value||null,rule_refs_raw:$('rule-refs').value||null};
  try {const result=await api('/triage?format=internal',request);const item={id:crypto.randomUUID(),request,result,edit:result.draft_reply.text,escalated:false};queue.push(item);select(item);notify('Разбор готов. Проверьте черновик; он ещё не сохранён на устройстве.');}
  catch(error){notify(error.message);}finally{$('analyze').disabled=false;}
};
$('draft').oninput=()=>{approvedText=null;$('copy').disabled=true;$('draft-state').textContent='Текст изменён. Нужна повторная проверка.';if(current)current.edit=$('draft').value;};
const restore=document.createElement('button');restore.textContent='Восстановить шаблон';restore.className='quiet';restore.onclick=()=>{if(!current)return;$('draft').value=current.result.draft_reply.text;$('draft').dispatchEvent(new Event('input'));};$('save').parentElement.append(restore);
$('check').onclick=async()=>{
  if(!current||checking)return;checking=true;$('check').disabled=true;
  const item=current,text=$('draft').value;
  try {const result=await api('/draft/check',{request:item.request,draft:{...item.result.draft_reply,text}});
    if(current!==item||$('draft').value!==text)return;
    approvedText=result.approved?text:null;$('copy').disabled=!result.approved;
    $('draft-state').textContent=result.approved?'Проверка пройдена. Можно скопировать текст.':'Правка требует проверки человеком. Сохраните её локально или восстановите исходный шаблон.';
  }catch(error){notify(error.message);}finally{checking=false;$('check').disabled=false;}
};
$('copy').onclick=async()=>{if(approvedText!==$('draft').value||!approvedText)return;try{await navigator.clipboard.writeText(approvedText);notify('Проверенный текст скопирован.');}catch{notify('Браузер запретил копирование. Проверьте разрешение буфера обмена.');}};
$('save').onclick=()=>{if(!current)return;current.edit=$('draft').value;try{localStorage.setItem(key,JSON.stringify(queue));notify('Очередь и правка сохранены в браузере этого устройства.');}catch{notify('Не удалось сохранить: хранилище браузера недоступно или заполнено.');}};
$('escalate').onclick=()=>{if(!current)return;current.escalated=true;select(current);notify('Отмечено для старшего локально. Для сохранения нажмите «Сохранить на устройстве».');};
$('clear').onclick=()=>{if(!confirm('Удалить очередь и сохранённые правки на этом устройстве?'))return;try{localStorage.removeItem(key);}catch{notify('Браузер не разрешил очистку сохранённых данных.');return;}queue=[];current=null;approvedText=null;$('ticket').hidden=true;$('empty').hidden=false;renderQueue();notify('Данные устройства очищены.');};
fetch('/health').then(r=>{$('health').textContent=r.ok?'Сервис готов · локальный режим':'Правила не загружены';}).catch(()=>{$('health').textContent='Сервис недоступен';});
renderQueue();
