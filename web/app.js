const $ = (s) => document.querySelector(s);
let activeSession = null, viewedSession = null, busy = false, sources = null, demoMode = false;
let pendingChat = null, pendingLead = null, waitingTimer = null;
let sessionLoadVersion = 0, creatingSession = false;
const request = async (path, data) => {
  const response = await fetch(path, data === undefined ? {} : {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Не удалось выполнить запрос');
  return result;
};
function setBusy(value) {
  busy = value;
  ['#send','#new-chat','#lead-open'].forEach(s => $(s).disabled = value);
  $('#message').disabled = value || viewedSession !== activeSession;
  $('#send').textContent = value ? '…' : '↑';
  clearInterval(waitingTimer);
  $('#reply-status').hidden = !value;
  if (value) {
    const started = Date.now();
    const update = () => {$('#reply-status').textContent = `Консультант готовит ответ · ${Math.floor((Date.now()-started)/1000)} с`;};
    update(); waitingTimer = setInterval(update,1000);
  }
}
function showDebug(metadata) {
  sources = metadata;
  $('#debug').hidden = false;
  $('#debug-toggle').setAttribute('aria-pressed','true');
  const container = $('#debug-content'); container.replaceChildren();
  const status = document.createElement('p');
  status.textContent = `${metadata.elapsed_ms} мс · ${metadata.mode === 'llm' ? 'Ответ LLM' : metadata.mode === 'retrieval' ? 'Поиск без LLM' : 'Ошибка API'}`;
  container.append(status);
  for (const source of metadata.sources || []) {
    const details = document.createElement('details'), title = document.createElement('summary'), text = document.createElement('pre');
    title.textContent = source.title;
    text.textContent = `${source.document}\nBM25: ${source.score}\n\n${source.text}`;
    details.append(title,text); container.append(details);
  }
}
function addMessage(role, content, metadata = {}, leadId = null) {
  $('#welcome').hidden = true;
  const article = document.createElement('article'); article.className = 'message ' + role;
  const label = document.createElement('div'); label.className = 'speaker'; label.textContent = role === 'user' ? 'ВЫ' : role === 'lead' ? 'ЗАЯВКА СОХРАНЕНА В ПРОТОТИПЕ' : demoMode ? 'СКЛАДЛАБ · ДЕМО' : 'ENERGYTOOL';
  const body = document.createElement('div'); body.className = 'body'; body.textContent = content;
  article.append(label,body);
  if (role === 'lead' && leadId) {
    const link = document.createElement('a'); link.className = 'lead-manager-link';
    link.href = '/manager?id=' + encodeURIComponent(leadId);
    link.target = '_blank'; link.rel = 'noopener';
    link.textContent = 'Открыть заявку на экране менеджера ↗';
    article.append(link);
  }
  if (metadata.sources) {
    const controls = document.createElement('div'); controls.className = 'message-tools';
    const button = document.createElement('button'); button.textContent = `Источники · ${metadata.sources.length}`;
    button.onclick = () => showDebug(metadata);
    const time = document.createElement('span'); time.textContent = `${(metadata.elapsed_ms / 1000).toFixed(2)} с`;
    controls.append(button,time); article.append(controls); sources = metadata;
  }
  $('#messages').append(article);
  $('#conversation').scrollTop = $('#conversation').scrollHeight;
  return article;
}
async function refreshHistory() {
  const list = await request('/api/sessions'); $('#history').replaceChildren();
  for (const session of list) {
    const button = document.createElement('button'); button.textContent = session.title; button.title = session.title;
    button.className = session.id === viewedSession ? 'active' : '';
    button.onclick = () => {if (!busy && !creatingSession) openSession(session.id).catch(showError);};
    $('#history').append(button);
  }
}
function showError(error) { $('#error').textContent = error.message; }
async function openSession(id) {
  const version = ++sessionLoadVersion;
  const data = await request('/api/sessions/' + id);
  if (version !== sessionLoadVersion) return;
  viewedSession = id; $('#messages').replaceChildren(); sources = null;
  $('#debug-content').replaceChildren();
  $('#welcome').hidden = data.messages.length > 0;
  for (const message of data.messages) addMessage(message.role,message.content,message.metadata);
  for (const lead of data.leads) addMessage('lead',lead.summary,{},lead.id);
  const archived = id !== activeSession || data.session.closed;
  $('#archive-notice').hidden = !archived;
  $('#composer').hidden = archived; $('#lead-open').hidden = archived;
  $('#session-label').textContent = archived ? 'История консультации' : 'Текущая консультация';
  $('#message').disabled = archived;
  await refreshHistory();
}
async function newSession() {
  if (busy || creatingSession) return;
  creatingSession = true; $('#new-chat').disabled = true;
  try {
    if (activeSession) await request('/api/close',{session_id:activeSession});
    activeSession = (await request('/api/sessions',{})).id;
    pendingChat = null; pendingLead = null;
    $('#message').value = ''; $('#error').textContent = '';
    await openSession(activeSession);
  } finally {creatingSession=false; $('#new-chat').disabled=busy;}
}
async function sendMessage(text) {
  if (busy || creatingSession || !text.trim() || activeSession !== viewedSession) return;
  text = text.trim();
  if (!pendingChat || pendingChat.text !== text) pendingChat = {text, id:crypto.randomUUID()};
  setBusy(true); $('#error').textContent = ''; $('#message').value = '';
  const outgoing = addMessage('user',text);
  try {
    const result = await request('/api/chat',{session_id:activeSession,message:text,request_id:pendingChat.id});
    pendingChat = null;
    addMessage('assistant',result.answer,result);
    if (!$('#debug').hidden) showDebug(result);
    await refreshHistory().catch(showError);
  } catch (error) {outgoing.remove(); showError(error); $('#message').value = text;}
  finally {setBusy(false); $('#message').focus();}
}
$('#composer').onsubmit = e => {e.preventDefault(); sendMessage($('#message').value);};
$('#message').onkeydown = e => {if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {e.preventDefault(); sendMessage(e.target.value);}};
$('#new-chat').onclick = () => newSession().catch(showError);
document.querySelectorAll('[data-question]').forEach(button => button.onclick = () => sendMessage(button.dataset.question));
$('#debug-toggle').onclick = () => {
  const open = $('#debug').hidden; $('#debug').hidden = !open; $('#debug-toggle').setAttribute('aria-pressed',String(open));
  if (open && sources) showDebug(sources);
};
$('#lead-open').onclick = () => {$('#lead-error').textContent = ''; $('#lead-dialog').showModal();};
$('#lead-close').onclick = () => $('#lead-dialog').close();
$('#lead-form').onsubmit = async e => {
  e.preventDefault(); const button = e.target.querySelector('[type=submit]'); button.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(e.target)); data.test_data = data.test_data === 'on'; data.session_id = activeSession;
    const signature = JSON.stringify(data);
    if (!pendingLead || pendingLead.signature!==signature) pendingLead = {signature,id:crypto.randomUUID()};
    data.request_id = pendingLead.id;
    const lead = await request('/api/leads',data); addMessage('lead',`Заявка № ${lead.id.slice(0,8)} сохранена.\n\n`+lead.summary,{},lead.id); pendingLead=null; $('#lead-dialog').close(); e.target.reset();
  } catch(error) {$('#lead-error').textContent = error.message;} finally {button.disabled = false;}
};
window.addEventListener('pagehide', () => {if (activeSession) navigator.sendBeacon('/api/close',new Blob([JSON.stringify({session_id:activeSession})],{type:'application/json'}));});
window.addEventListener('pageshow', event => {if (event.persisted) newSession().catch(showError);});
(async () => {
  const status = await request('/api/status');
  $('#connection').textContent = status.llm ? `Консультант подключён · ${status.documents} документов в базе знаний` : `Режим поиска · ${status.documents} документов. LLM не подключена — показываем выдержки вместо консультации.`;
  $('#connection').classList.toggle('ready',status.llm);
  if (status.external_blocked) $('#connection').textContent = 'Поиск по базе EnergyTool · Отправка материалов в OpenRouter отключена. Для ответов по кейсу подключите API организаторов.';
  if (status.demo) {
    demoMode = true;
    $('#connection').textContent = status.llm
      ? 'Демо с AI · Вымышленная база «СкладЛаб». Материалы EnergyTool не используются. Вводите только тестовые данные.'
      : 'Демо «СкладЛаб» · Модель не подключена. Вводите только тестовые данные.';
    $('h1').textContent = 'Тест AI-консультанта';
    $('.welcome h2').textContent = 'Проверим диалог на примере складов';
    $('.welcome p').textContent = 'Опишите вымышленную ситуацию. Модель уточнит задачу и предложит следующий шаг по учебной базе.';
    $('.welcome .eyebrow').textContent = 'УЧЕБНЫЙ СЦЕНАРИЙ';
    $('.footnote:not(#reply-status)').textContent = 'Учебная база «СкладЛаб» · Это не консультация о реальных услугах EnergyTool.';
    document.querySelectorAll('[data-question]').forEach((button, index) => { if (index > 1) button.hidden = true; });
  }
  await newSession();
})().catch(showError);
