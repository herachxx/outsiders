'use strict';
const $ = id => document.getElementById(id);
const STORE_KEY = 'grand-support-demo-history-v1';
const categories = {
  question: {kind:'report', label:'Вопрос по игре', placeholder:'Привет! Не могу разобраться, как устроиться на работу механика. Что нужно сделать?'},
  complaint: {kind:'complaint', label:'Жалоба на игрока', placeholder:'Игрок нарушил правила на сервере. Расскажи, что произошло, и укажи никнейм, если помнишь.'},
  technical: {kind:'report', label:'Техническая проблема', placeholder:'Игра вылетает при входе на сервер. Устройство, версия игры и что происходит перед ошибкой…'},
  payment: {kind:'report', label:'Платежи и покупки', placeholder:'Я оплатил Grand Coins, но они не поступили. Укажи время операции без данных банковской карты.'},
  account: {kind:'report', label:'Вопрос об аккаунте', placeholder:'Не могу войти в свой аккаунт. Опиши проблему, но не сообщай пароль и код подтверждения.'},
  idea: {kind:'report', label:'Идея или предложение', placeholder:'Предлагаю добавить новую функцию в игру…'}
};
let selectedCategory = 'question';
let anonymousId='';try{anonymousId=sessionStorage.getItem('grand-player-session')||'';if(!anonymousId){anonymousId=globalThis.crypto?.randomUUID?.()||String(Date.now());sessionStorage.setItem('grand-player-session',anonymousId);}}catch{}
let latestAnswer = '';
let recent = [];
try {const data = JSON.parse(sessionStorage.getItem(STORE_KEY)||'[]');if(Array.isArray(data))recent=data.filter(x => x && typeof x.id === 'string' && typeof x.text === 'string' && typeof x.answer === 'string').slice(-15);} catch {/* optional storage */}
function storeRecent(){try{sessionStorage.setItem(STORE_KEY,JSON.stringify(recent));}catch{/* private mode */}updateNavCount();}
function updateNavCount(){ $('nav-count').textContent=String(recent.length); $('nav-count').hidden=!recent.length; }
function pickCategory(name){
 if(!categories[name])return;
 selectedCategory=name;
 document.querySelectorAll('.category-card').forEach(el=>{const selected=el.dataset.category===name;el.classList.toggle('selected',selected);el.setAttribute('aria-pressed',String(selected));});
 const message=$('ticket-message');
 message.placeholder=window.GrandI18n?.tr(categories[name].placeholder)||categories[name].placeholder;
 $('nick-field').hidden=name!=='complaint';
 $('ticket-server').placeholder='Например, сервер 01';
}
function switchView(name){
 const isHistory=name==='history';
 $('home-view').hidden=isHistory;
 $('history-view').hidden=!isHistory;
 $('breadcrumb-page').textContent=isHistory?'Мои обращения':'Главная';
 document.querySelectorAll('[data-view]').forEach(button=>{const active=button.dataset.view===name;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
 if(isHistory)renderHistory();window.GrandI18n?.apply();
 window.scrollTo({top:0,behavior:'instant'});
}
function makeIcon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-'+name);svg.append(use);return svg;}
function renderHistory(){
 const list=$('history-list');list.replaceChildren();
 if(!recent.length){const empty=document.createElement('div');empty.className='history-empty';empty.append(makeIcon('message'));const title=document.createElement('h2');title.textContent='Пока нет обращений';const description=document.createElement('p');description.textContent='Начни с вопроса — результат появится здесь до закрытия вкладки.';empty.append(title,description);list.append(empty);$('clear-history').hidden=true;return;}
 $('clear-history').hidden=false;
 [...recent].reverse().forEach(item=>{const wrap=document.createElement('article');wrap.className='history-entry';const content=document.createElement('div');const title=document.createElement('strong');title.textContent=item.text.slice(0,125)+(item.text.length>125?'…':'');const detail=document.createElement('small');detail.textContent=item.category+' · '+new Date(item.time).toLocaleString('ru-RU')+' · '+(item.status|| (item.needsHuman?'Нужен специалист':'Предварительный ответ')); content.append(title,detail);const button=document.createElement('button');button.className='subtle-button';button.type='button';button.append(makeIcon('arrow'),'Посмотреть');button.addEventListener('click',()=>{switchView('home');showAnswer(item.result,null,item.categoryKey);$('answer-panel').scrollIntoView({behavior:'smooth',block:'start'});});wrap.append(content,button);
 if(item.accessToken){const statusButton=document.createElement('button');statusButton.className='subtle-button';statusButton.type='button';statusButton.textContent='Проверить статус';
 statusButton.addEventListener('click',async()=>{statusButton.disabled=true;try{const response=await fetch(`/support/tickets/${encodeURIComponent(item.id)}`,{headers:{'X-Ticket-Token':item.accessToken}});
 if(!response.ok)throw Error('Статус недоступен');const info=await response.json();const names={new:'Новое',in_review:'В работе',needs_info:'Нужны сведения',escalated:'На рассмотрении',resolved:'Решено',closed:'Закрыто'};
 item.status=names[info.status]||info.status;detail.textContent=item.category+' · '+item.status;storeRecent();}catch{detail.textContent=item.category+' · Не удалось проверить статус';}finally{statusButton.disabled=false;}});
 wrap.append(statusButton);}list.append(wrap);});
}
function showAnswer(result,elapsedMs,categoryKey=selectedCategory){
 const draft=result?.draft_reply?.text;
 if(typeof draft!=='string')throw new Error('Сервис вернул ответ в неизвестном формате.');
 latestAnswer=draft;
 $('answer-text').textContent=draft.trim()||'Ассистент не смог составить достоверный ответ. Для помощи обратитесь в официальную поддержку Grand Mobile.';
 $('answer-badge').textContent=result.needs_human?'Нужен специалист':'Предварительный ответ';
 $('answer-badge').classList.toggle('human',!!result.needs_human);
 $('human-notice').hidden=!result.needs_human;
 $('idea-notice').hidden=categoryKey!=='idea';
 const citations=$('answer-citations');citations.replaceChildren();
 const refs=Array.isArray(result.draft_reply?.cited)?result.draft_reply.cited:[];
 if(refs.length){const title=document.createElement('strong');title.textContent='Найденные пункты правил';citations.append(title);for(const item of refs){const ref=document.createElement('div');ref.className='citation-item';ref.textContent='Раздел '+item.section_id+', пункт '+item.ref+': '+item.excerpt;citations.append(ref);}citations.hidden=false;}else citations.hidden=true;
 $('answer-latency').textContent=elapsedMs===null?'Результат из истории':'Готово за '+Math.round(elapsedMs)+' мс · обработка + сеть';
 $('answer-panel').hidden=false;window.GrandI18n?.apply();
}
async function submit(event){
 event.preventDefault();
 const raw=$('ticket-message').value.trim();if(!raw){$('ticket-message').focus();return;}
 const button=$('submit-ticket');button.disabled=true;button.classList.add('loading');button.querySelector('span').textContent='Обрабатываем…';
 const status=$('form-status');status.textContent='Проверяем обращение и готовим предварительный ответ…';status.classList.remove('error');
 const cat=categories[selectedCategory];
 const files=Array.from($('screenshot-files').files);if(files.length>4||files.some(f=>f.size>5*1024*1024)){status.textContent='Выберите не более 4 изображений по 5 МБ.';status.classList.add('error');button.disabled=false;button.classList.remove('loading');button.querySelector('span').textContent='Получить ответ';return;}
 const request={kind:cat.kind,messages:[{role:'player',text:raw}],images_count:files.length,region:$('ticket-server').value.trim()||null,reported_nick:selectedCategory==='complaint'?($('ticket-nick').value.trim()||null):null,reporter_hash:anonymousId||null};
 const started=performance.now();
 try{
  const response=await fetch('/support/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request,topic:selectedCategory})});
  if(!response.ok){if(response.status===503)throw new Error('Сервис временно недоступен.');if(response.status===409)throw new Error('Такое обращение уже зарегистрировано за последний час.');if(response.status===422)throw new Error('Проверь длину и содержание сообщения.');throw new Error('Не удалось получить ответ. Попробуй повторить запрос.');}
  const ticket=await response.json();let result=ticket.result;
  showAnswer(result,performance.now()-started,selectedCategory);
  if(ticket.status==='closed'){$('answer-badge').textContent=window.GrandI18n?.tr('Решено')||'Решено';}
  let uploaded=0;let uploadFailed=0;
  for(const file of files){const formData=new FormData();formData.append('file',file);try{const r=await fetch(`/support/tickets/${encodeURIComponent(ticket.id)}/attachments`,{method:'POST',headers:{'X-Ticket-Token':ticket.access_token},body:formData});if(r.ok){const attachment=await r.json();result=attachment.result;uploaded++;}else uploadFailed++;}catch{uploadFailed++;}}
  if(uploaded)showAnswer(result,performance.now()-started,selectedCategory);
  status.textContent=`${window.GrandI18n?.tr('Обращение')||'Обращение'} ${ticket.id} · ${window.GrandI18n?.tr('Сохранено')||'Сохранено'}${uploadFailed?` · ${window.GrandI18n?.tr('Не загружено вложений')||'Не загружено вложений'}: ${uploadFailed}`:''}.`;
  const item={id:ticket.id,accessToken:ticket.access_token,status:ticket.status==='closed'?'Закрыто':'Новое',text:raw,category:cat.label,categoryKey:selectedCategory,time:Date.now(),answer:result.draft_reply.text,needsHuman:!!result.needs_human,result};
  recent.push(item);recent=recent.slice(-15);storeRecent();$('screenshot-files').value='';$('file-count').textContent='Файлы не выбраны';
  window.GrandI18n?.apply();$('answer-panel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(error){status.textContent=window.GrandI18n?.tr(error.message)||error.message;status.classList.add('error');$('answer-panel').hidden=true;}
 finally{button.disabled=false;button.classList.remove('loading');button.querySelector('span').textContent=window.GrandI18n?.tr('Получить ответ')||'Получить ответ';}
}
document.querySelectorAll('.category-card').forEach(el=>el.addEventListener('click',()=>pickCategory(el.dataset.category)));
document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',()=>switchView(el.dataset.view)));
$('ticket-message').addEventListener('input',()=>{$('char-counter').textContent=$('ticket-message').value.length+' / 20000';});
$('ticket-message').addEventListener('keydown',event=>{if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();$('support-form').requestSubmit();}});
$('support-form').addEventListener('submit',submit);
$('copy-answer').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(latestAnswer);$('copy-answer').textContent=window.GrandI18n?.tr('Скопировано ✓')||'Скопировано ✓';setTimeout(()=>{$('copy-answer').replaceChildren(makeIcon('copy'),window.GrandI18n?.tr('Скопировать ответ')||'Скопировать ответ');},1600);}catch{$('form-status').textContent='Не удалось скопировать. Выдели текст ответа вручную.';}});
$('new-ticket').addEventListener('click',()=>{$('answer-panel').hidden=true;$('ticket-message').value='';$('char-counter').textContent='0 / 20000';$('form-status').textContent='';$('ticket-message').focus();$('compose-title').scrollIntoView({behavior:'smooth',block:'start'});});
$('clear-history').addEventListener('click',()=>{if(!confirm(window.GrandI18n?.tr('Очистить историю обращений в этой вкладке?')||'Очистить историю обращений в этой вкладке?'))return;recent=[];storeRecent();renderHistory();});
pickCategory('question');updateNavCount();

const uploadInput=document.getElementById("screenshot-files");if(uploadInput)uploadInput.addEventListener("change",()=>{document.getElementById("file-count").textContent=uploadInput.files.length?`${window.GrandI18n?.tr('Выбрано файлов')||'Выбрано файлов'}: ${uploadInput.files.length}`:(window.GrandI18n?.tr('Файлы не выбраны')||'Файлы не выбраны');});

(async()=>{const box=document.getElementById('assistant-status');if(!box)return;try{const d=await(await fetch('/api/status')).json();box.dataset.state=d.rules_loaded?'ok':'warn';box.textContent=d.rules_loaded?'Помощник работает':'Помощник в ручном режиме: правила не загружены'}catch{box.dataset.state='error';box.textContent='Нет связи с сервисом'}})();
