"use strict";
document.getElementById('setup-form').addEventListener('submit', async event => {
  event.preventDefault();
  const password=document.getElementById('password').value;
  const confirm=document.getElementById('confirm').value;
  const error=document.getElementById('error');
  const button=document.getElementById('submit');
  error.textContent='';
  if(password.length<12){error.textContent='Пароль должен содержать не менее 12 символов.';return;}
  if(password!==confirm){error.textContent='Пароли не совпадают.';return;}
  button.disabled=true;
  try {
    const res=await fetch('/admin/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
    if(!res.ok){
      if(res.status===409){location.replace('/admin/login');return;}
      const data=await res.json().catch(()=>({}));
      throw Error(data.detail||'Не получилось сохранить пароль. Попробуйте снова.');
    }
    location.replace('/admin');
  } catch(exc){error.textContent=exc.message;button.disabled=false;}
});
