'use strict';
document.getElementById('login-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=document.getElementById('submit');const error=document.getElementById('error');
  error.textContent='';button.disabled=true;
  try{
    const response=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('password').value})});
    if(!response.ok)throw new Error(response.status===429?'Слишком много попыток. Повторите позже.':response.status===503?'Вход ещё не настроен на сервере.':'Неверный пароль.');
    location.replace('/admin');
  }catch(exc){error.textContent=exc.message;button.disabled=false;}
});
