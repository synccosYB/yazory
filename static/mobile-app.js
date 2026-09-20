(()=>{'use strict';
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/static/service-worker.js',{scope:'/'}).catch(()=>{}));}
let deferredPrompt=null;
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredPrompt=event;document.documentElement.classList.add('app-installable');});
document.addEventListener('click',async event=>{const button=event.target.closest('[data-install-app]');if(!button||!deferredPrompt)return;await deferredPrompt.prompt();deferredPrompt=null;document.documentElement.classList.remove('app-installable');});
})();