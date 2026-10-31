"use strict";
async function updateAssistantStatus(){
 const root=document.getElementById('assistant-status');if(!root)return;
 try{
  const response=await fetch('/support/status',{cache:'no-store'});if(!response.ok)throw Error();
  const status=await response.json();root.dataset.state=status.ready?'ready':'manual';
  document.getElementById('assistant-status-title').textContent=status.message;
  document.getElementById('assistant-status-detail').textContent=status.ready
   ?`${status.classification==='model'?'Обученная модель':'Классификация по правилам'} · ответы по шаблонам. Решение подтверждает оператор.`
   :'Обращения сохраняются в очередь. Для автоматического разбора подключите правила и перезапустите сервис.';
 }catch{root.dataset.state='offline';document.getElementById('assistant-status-title').textContent='Нет связи с помощником';document.getElementById('assistant-status-detail').textContent='Проверьте, что окно сервера открыто, и повторите проверку.';}
 window.GrandI18n?.apply();
}
document.getElementById('assistant-status-refresh')?.addEventListener('click',updateAssistantStatus);
void updateAssistantStatus();
