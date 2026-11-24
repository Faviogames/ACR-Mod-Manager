'use strict';
const normalise = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
function filterStages(stages, filter, query) {
  const search = normalise(query).trim();
  return stages.filter(s => (filter === 'all' || (filter === 'active' ? s.active : !s.active)) &&
    normalise(`${s.name} ${s.country}`).includes(search));
}
function isInGame(stage, scanned) {
  return Boolean(scanned && stage.active && stage.valid && stage.compatible && stage.menu_ready);
}
if (typeof module !== 'undefined') module.exports = {filterStages, normalise, isInGame};
if (typeof document !== 'undefined') boot();

async function boot() {
  const $ = id => document.getElementById(id);
  const dictionary = await (await fetch('/translations.json')).json();
  let language = 'en';
  const t = (source, values={}) => (language==='en' ? dictionary.text[source] || source : source).replace(/\{(\w+)\}/g, (match,key)=>values[key] ?? match);
  const message = value => {
    value=String(value || '');
    if(language==='es') return value;
    if(dictionary.text[value]) return dictionary.text[value];
    for(const [source,en] of Object.entries(dictionary.prefixes)) if(value.startsWith(source)) return en+value.slice(source.length);
    return value.replace(/^Generando tablas para (\d+) tramos activos…$/, 'Generating tables for $1 enabled stages…')
      .replace(/^Comprobando integridad de (.+)…$/, 'Checking integrity of $1…')
      .replace(/^Recuperando registros e imágenes de (.+)…$/, 'Recovering registrations and images from $1…')
      .replace(/^Reconociendo (\d+) tramos oficiales; creando la base de datos local…$/, 'Recognising $1 official stages; creating the local database…');
  };
  const staticText=[], staticAttributes=[];
  const reverse=new Map();
  for(const [es,en] of Object.entries(dictionary.text)) if(!reverse.has(en)) reverse.set(en,es);
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()) {
    const node=walker.currentNode, en=node.textContent.trim(), es=reverse.get(en);
    if(es) staticText.push({node,en,es,prefix:node.textContent.match(/^\s*/)[0],suffix:node.textContent.match(/\s*$/)[0]});
  }
  for(const node of document.querySelectorAll('[title],[placeholder],[aria-label]')) for(const attribute of ['title','placeholder','aria-label']) {
    const en=node.getAttribute(attribute),es=reverse.get(en);
    if(es) staticAttributes.push({node,attribute,en,es});
  }
  function applyLanguage(value) {
    language=value==='es'?'es':'en';document.documentElement.lang=language;$('language').value=language;
    for(const item of staticText) if(item.node.isConnected) item.node.textContent=item.prefix+item[language]+item.suffix;
    for(const item of staticAttributes) item.node.setAttribute(item.attribute,item[language]);
    lastRows='';$('toast').textContent='';$('toast').classList.remove('visible');
  }
  const countryName = value => {
    const pairs={España:['Spain','España'],Spain:['Spain','España'],Kenia:['Kenya','Kenia'],Kenya:['Kenya','Kenia'],Grecia:['Greece','Grecia'],Greece:['Greece','Grecia'],Belgium:['Belgium','Bélgica'],France:['France','Francia'],Italy:['Italy','Italia'],Mexico:['Mexico','México'],Germany:['Germany','Alemania'],Portugal:['Portugal','Portugal'],Sweden:['Sweden','Suecia'],Monaco:['Monaco','Mónaco'],Croatia:['Croatia','Croacia'],Estonia:['Estonia','Estonia'],Finland:['Finland','Finlandia'],NewZealand:['New Zealand','Nueva Zelanda'],Japan:['Japan','Japón'],Argentina:['Argentina','Argentina'],Chile:['Chile','Chile'],Turkey:['Turkey','Turquía'],Wales:['Wales','Gales']};
    return pairs[value]?.[language==='es'?1:0] || value;
  };
  const token = location.hash.slice(1) || sessionStorage.getItem('content-token') || '';
  sessionStorage.setItem('content-token', token);
  history.replaceState(null, '', '/');
  let state = null, selected = null, filter = 'all', lastRows = '', toastTimer;
  const images = new Map();
  const icon = name => { const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const use = document.createElementNS(svg.namespaceURI, 'use'); use.setAttribute('href', `#i-${name}`); svg.append(use); return svg; };
  const el = (tag, cls, text) => {const node = document.createElement(tag); if(cls) node.className=cls; if(text!=null) node.textContent=text; return node;};
  const size = bytes => `${(bytes / 1024 ** 3).toLocaleString(language, {maximumFractionDigits: 2})} GB`;
  const status = s => message(s.reason) || (!s.valid ? t('Requiere revisión') : !s.compatible ? t('Build no compatible') : s.active ? (state?.scanned===false ? t('Pendiente de escanear') : s.menu_ready ? t('En el juego') : t('Pendiente de menú')) : t('Desactivado'));
  async function api(path, body) {
    const response = await fetch(path, {method:body ? 'POST' : 'GET', headers:{'X-App-Token':token, ...(body ? {'Content-Type':'application/json'} : {})}, ...(body ? {body:JSON.stringify(body)} : {})});
    const data = await response.json(); if(!response.ok) throw new Error(message(data.error) || t('No se pudo completar la operación')); return data;
  }
  function toast(message) { $('toast').textContent=message; $('toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),4500); }
  async function imageFor(stage) {
    if (!stage.has_preview) return null;
    const key=stage.id+':'+stage.preview_hash;
    if (!images.has(key)) images.set(key, fetch(`/api/preview?id=${encodeURIComponent(stage.id)}`, {headers:{'X-App-Token':token}})
      .then(r => {if(!r.ok) throw new Error(); return r.blob();}).then(blob => URL.createObjectURL(blob)).catch(()=>null));
    return images.get(key);
  }
  function renderList(force=false) {
    if(!state) return;
    const rows = filterStages(state.stages.map(row=>({...row,country:countryName(row.country)})), filter, $('search').value);
    const key = JSON.stringify([rows, filter, selected]);
    if (!force && key===lastRows) return;
    if (!rows.some(r=>r.id===selected)) selected=rows[0]?.id || null;
    lastRows=JSON.stringify([rows, filter, selected]);
    $('stage-list').replaceChildren(); $('empty-list').hidden=rows.length>0;
    $('stage-list').hidden=rows.length===0;
    for(const row of rows) {
      const button=el('button',`stage-card${row.id===selected?' selected':''}${!row.active?' inactive':''}${!row.compatible?' warning':''}`);
      button.setAttribute('role','listitem'); button.setAttribute('aria-pressed',String(row.id===selected)); button.setAttribute('aria-label',`${row.name}, ${status(row)}`);
      const thumb=el('span','thumb'); thumb.append(icon('flag')); imageFor(row).then(url=>{if(url && button.isConnected){const img=el('img');img.src=url;img.alt='';thumb.replaceChildren(img);}});
      const info=el('span','stage-card-text');info.append(el('strong','',row.name),el('small','',row.country || t('Tramo de la comunidad')));
      const badge=el('span','card-status');badge.append(el('i','dot'),document.createTextNode(status(row)));info.append(badge);
      const arrow=icon('arrow');arrow.classList.add('card-chevron');button.append(thumb,info,arrow);
      button.addEventListener('click',()=>{selected=row.id;renderList(true);renderDetail();}); $('stage-list').append(button);
    }
    $('visible-count').textContent=`${rows.length} ${rows.length===1?t('tramo'):t('tramos')}`;
    document.querySelectorAll('[data-filter]').forEach(b=>{const active=b.dataset.filter===filter;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});
    renderDetail();
  }
  function renderDetail() {
    const row=state?.stages.find(r=>r.id===selected);
    $('empty-detail').hidden=!!row; $('stage-detail').hidden=!row; if(!row)return;
    $('hero-name').textContent=row.name; $('hero-country').textContent=countryName(row.country).toUpperCase() || t('TRAMO DE LA COMUNIDAD');
    document.querySelector('.hero-caption').textContent=row.preview_scope==='location'?t('IMAGEN DE LA UBICACIÓN'):t('TRAMO DE LA COMUNIDAD');
    $('hero-status').textContent=status(row);$('hero-status').className=`badge${!row.compatible?' warning':!row.active?' inactive':''}`;
    const ready=isInGame(row,state.scanned);
    $('hero-active-badge').hidden=!ready; $('hero-status').hidden=ready;
    $('hero-active-badge').alt=t('Mod activo: en el juego');
    $('hero-active-badge').title=t('Mod activo: en el juego');
    $('hero-source').textContent=(row.external || row.source_kind==='external')?t('MOD EXTERNO'):'WRC GENERATIONS → ACR';
    $('stage-version').textContent=message(row.version); $('stage-version').title=row.version;
    $('stage-size').textContent=size(row.size);$('stage-author').textContent=(row.author==='Comunidad' ? t('Comunidad') : message(row.author)) || t('Comunidad');
    $('description').textContent=(row.registration_required?message(row.description):row.description) || t('Este tramo aún no incluye una descripción.');
    $('compat-title').textContent=row.registration_required?t('Pendiente de registrar en el gestor'):row.compatible?t('Compatibilidad declarada con tu versión de ACR'):t('Revisa la compatibilidad antes de correr');
    $('compat-description').textContent=row.registration_required?t('Esta versión no está en el catálogo interno; actualiza el gestor.'):row.compatible?t('El menú se genera a partir de tu juego instalado.'):t('Construido para {build}.',{build:row.build});
    if(row.external) {
      $('compat-title').textContent=t('Mod externo no soportado');
      $('compat-description').textContent=t('Detectado en la carpeta, pero todavía no integrado en el gestor. Esto no confirma que esté averiado.');
    }
    if(row.compatibility_scope==='menu') {
      $('compat-title').textContent=t('Registro recuperado del catálogo oficial');
      $('compat-description').textContent=t('Menú compatible. La build original del nivel no está declarada; falta comprobarlo en el juego.');
    }
    $('compat-title').closest('.compatibility').classList.toggle('warning',!row.compatible);
    const button=$('toggle');button.querySelector('span').textContent=!state.scanned?t('Escanea primero'):!row.valid?message(row.reason):row.active?(row.menu_ready?t('Desactivar tramo'):t('Preparar menú')):t('Activar tramo');button.classList.toggle('activate',!row.active);
    button.disabled=state.busy || !state.scanned || !row.valid || (!row.active && !row.compatible);
    $('toggle-note').textContent=row.registration_required?t('Este mod no se modifica automáticamente. Requiere una integración específica.'):!state.scanned?t('Pulsa Escanear para comprobar el paquete antes de activarlo o desactivarlo.'):row.active?(row.menu_ready?t('Al desactivar, el tramo se guarda fuera de mods y el menú se actualiza automáticamente.'):t('El nivel está en mods; falta generar o actualizar su entrada de menú.')):t('Al activar, el tramo vuelve a mods y el menú se actualiza automáticamente.');
    const imageKey=row.id+':'+row.preview_hash;
    if($('hero-image').dataset.stage!==imageKey) {
      $('hero-image').dataset.stage=imageKey;$('hero-image').removeAttribute('src');$('hero-image').alt=t('Imagen de {name}',{name:row.name});
      imageFor(row).then(url=>{if(url && selected===row.id && $('hero-image').dataset.stage===imageKey) $('hero-image').src=url;});
    }
  }
  function render(next) {
    const wasBusy=state?.busy; state=next;
    if(next.language && next.language!==language) applyLanguage(next.language);
    $('total-count').textContent=state.stages.length;
    const count=state.stages.filter(s=>s.active).length;
    const countries=new Set(state.stages.map(s=>s.country).filter(Boolean)).size;
    $('countries-count').textContent=`${countries} ${countries===1?t('país'):t('países')}`;
    for(const id of ['scan','install','restore','sync']) $(id).disabled=state.busy;
    const pending=state.stages.filter(s=>s.registration_required).length;
    $('sync').disabled=state.busy || !state.scanned;
    
    document.body.classList.toggle('working',state.busy);
    $('sync-title').textContent=state.busy?message(state.message):state.error?t('El menú necesita atención'):!state.scanned?t('Pulsa Escanear para revisar tus mods'):pending?t('Hay mods no soportados'):state.synced?t('MODS FUNCIONANDO'):t('Biblioteca cargada');
    $('sync-description').textContent=state.busy?t('Espera a que termine antes de cerrar el gestor.'):t('{ready} en el juego · {count} en mods · {status}',{ready:state.menu_ready_count || 0,count,status:state.synced?t('Sin cambios pendientes.'):t('Pendientes de sincronizar.')});
    if(!state.scanned && !state.busy)$('sync-description').textContent=t('Escaneo manual: pulsa Escanear cuando añadas o cambies un mod.');
    if(pending && !state.busy)$('sync-description').textContent=t('{pending} paquetes requieren revisión; consulta su ficha. Se conserva el menú anterior.',{pending});
    $('sync-title').closest('.sync-panel').querySelector('.sync-icon use').setAttribute('href',state.busy?'#i-refresh':'#i-check');
    $('error').hidden=!state.error;$('error').textContent=message(state.error);
    const progress=state.progress;$('progress-panel').hidden=!state.busy;
    if(progress) {const percent=Math.min(100,progress.done/Math.max(progress.total,1)*100);$('progress').value=percent;$('progress-name').textContent=progress.name;$('progress-text').textContent=`${size(progress.done)} / ${size(progress.total)} · ${Math.round(percent)} %`;}
    else {$('progress').removeAttribute('value');$('progress-name').textContent=message(state.message);$('progress-text').textContent='';}
    $('log').textContent=state.logs.map(message).join('\n');$('activity-summary').textContent=state.error?t('Revisar detalles'):state.busy?t('Operación en curso'):t('Todo bajo control');
    $('game-path').textContent=state.game || t('Detectando…');$('mods-path').textContent=state.mods || t('Detectando…');$('backups-path').textContent=state.backups || t('Detectando…');
    const update=state.updates || {status:'idle'};
    $('updates').classList.toggle('update-available',update.status==='available');
    $('update-badge').hidden=update.status!=='available';
    $('updates').title=update.status==='available'?t('Nueva versión disponible: {version}',{version:update.version}):t('Buscar actualizaciones');
    $('installed-version').textContent=t('Versión instalada: {version}',{version:state.release?.version || '0.1.0'});
    const updateText={idle:'Pulsa Comprobar para consultar GitHub.',checking:'Buscando actualizaciones en GitHub…',available:'Hay una nueva versión: {version}',current:'Tienes la versión más reciente.',unpublished:'Todavía no hay una versión pública en GitHub.',preparing:'La nueva versión aún no tiene un paquete descargable.',unreachable:'No se pudo consultar GitHub. Comprueba tu conexión e inténtalo de nuevo.'};
    $('update-status').textContent=t(updateText[update.status] || updateText.unreachable,{version:update.version || ''});
    $('check-updates').disabled=update.status==='checking';
    $('open-release').disabled=!['available','current'].includes(update.status);
    renderList();renderDetail(); if(wasBusy && !state.busy && !state.error)toast(state.synced?t('Tu biblioteca está al día.'):state.scanned?t('Biblioteca cargada.'):t('Pulsa Escanear para revisar tus mods'));
  }
  async function action(body) {try {await api('/api/action',body);await poll();}catch(error){toast(error.message);}}
  async function poll(){try{const next=await api('/api/state');if(!state || next.revision!==state.revision)render(next);}catch(error){$('sync-title').textContent=t('Sin conexión con el gestor');$('sync-description').textContent=error.message;}}
  function nativeAction(action) {if(window.chrome?.webview) window.chrome.webview.postMessage({action}); else toast(t('Esta acción está disponible en la ventana del gestor.'));}
  document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{filter=button.dataset.filter;renderList(true);}));
  $('search').addEventListener('input',()=>renderList(true));
  $('clear-search').addEventListener('click',()=>{$('search').value='';filter='all';renderList(true);});
  $('scan').addEventListener('click',()=>action({action:'sync'}));
  $('sync').addEventListener('click',()=>action({action:'sync'}));
  $('toggle').addEventListener('click',()=>{const row=state.stages.find(r=>r.id===selected);if(row)action({action:row.active?(row.menu_ready?'disable':'sync'):'enable',id:row.id});});
  $('install').addEventListener('click',()=>nativeAction('install'));$('restore').addEventListener('click',()=>nativeAction('restore'));
  $('settings').addEventListener('click',()=>$('settings-dialog').showModal());document.querySelector('.dialog-close').addEventListener('click',()=>$('settings-dialog').close());
  window.chrome?.webview?.addEventListener('message',event=>{if(event.data?.error)toast(message(event.data.error));else if(event.data?.copied)toast(t('Plantilla copiada. Pégala en tu mensaje de Discord.'));else poll();});
  $('records').addEventListener('click',()=>nativeAction('records'));
  $('updates').addEventListener('click',()=>{$('updates-dialog').showModal();checkUpdates();});
  async function checkUpdates(){try{await api('/api/updates',{});await poll();}catch(error){toast(message(error.message));}}
  $('check-updates').addEventListener('click',checkUpdates);
  $('open-release').addEventListener('click',()=>nativeAction('release'));
  $('mod-support').addEventListener('click',()=>$('mod-support-dialog').showModal());
  $('open-contact').addEventListener('click',()=>nativeAction('contact'));
  $('copy-support').addEventListener('click',()=>{
    const text=t('Nombre del mod:')+'\n'+t('Autor:')+'\n'+t('Versión del mod:')+'\n'+t('Enlace de descarga (.pak/.utoc/.ucas):')+'\n'+t('Build de ACR:')+'\n'+t('Dependencias:')+'\n'+t('¿Funciona por sí solo?:')+'\n'+t('Tablas que modifica:')+'\n'+t('¿Permites adaptar el paquete para compatibilidad?:');
    window.chrome?.webview?.postMessage({action:'copy-support',text});
  });
  document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>$(button.dataset.close).close()));
  $('language').addEventListener('change',async()=>{
    try {
      const result=await api('/api/language',{language:$('language').value});
      window.chrome?.webview?.postMessage({action:'language',language:result.language});
      await poll();
    } catch(error) {$('language').value=language;toast(message(error.message));}
  });
  poll();setInterval(poll,800);
}
