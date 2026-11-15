const $ = selector => document.querySelector(selector);
const PAGE_SIZE = 50;
let query = '', offset = 0, selectedId = null, demo = false, listVersion = 0, detailVersion = 0;
let searchTimer;
const fullDate = new Intl.DateTimeFormat('ru-RU', {dateStyle: 'medium', timeStyle: 'short'});
const shortDate = new Intl.DateTimeFormat('ru-RU', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
const formatDate = (value, format = fullDate) => format.format(new Date(value));

async function get(path) {
  const response = await fetch(path);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Не удалось загрузить данные');
  return data;
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function showError(error) {
  $('#manager-error').textContent = error.message;
  $('#manager-error').hidden = false;
}
function selectRow() {
  document.querySelectorAll('.lead-row').forEach(row => {
    const selected = row.dataset.id === selectedId;
    row.classList.toggle('active', selected);
    if (selected) row.setAttribute('aria-current', 'true');
    else row.removeAttribute('aria-current');
  });
}
async function loadList() {
  const version = ++listVersion;
  const params = new URLSearchParams({q: query, offset: String(offset), limit: String(PAGE_SIZE)});
  const data = await get('/api/leads?' + params);
  if (version !== listVersion) return;
  $('#manager-error').hidden = true;
  $('#total-count').textContent = data.total;
  $('#list-status').textContent = query ? `Найдено: ${data.filtered}` : `Всего заявок: ${data.total}`;
  const focusedRow = document.activeElement.closest('.lead-row')?.dataset.id;
  const list = $('#lead-list');
  const scrollTop = list.scrollTop;
  list.replaceChildren();
  for (const lead of data.items) {
    const button = element('button', 'lead-row'); button.type = 'button'; button.dataset.id = lead.id;
    const top = element('div', 'row-top');
    const date = element('time', '', formatDate(lead.created_at, shortDate)); date.dateTime = lead.created_at;
    top.append(element('strong', '', lead.company), date);
    button.append(top, element('span', 'row-contact', `${lead.name} · ${lead.phone}`),
      element('span', 'row-title', lead.session_title === 'Новый диалог' ? 'Заявка без предварительного диалога' : lead.session_title));
    button.onclick = () => openLead(lead.id);
    list.append(button);
  }
  selectRow();
  if (focusedRow) [...list.children].find(row => row.dataset.id === focusedRow)?.focus({preventScroll: true});
  list.scrollTop = scrollTop;
  $('#list-empty').hidden = data.filtered !== 0;
  $('#list-empty h3').textContent = query ? 'Ничего не найдено' : 'Пока нет заявок';
  $('#list-empty p').textContent = query ? 'Попробуйте другую компанию, имя или телефон.' : 'Оставьте тестовую заявку в чате — она появится здесь автоматически.';
  $('#pagination').hidden = data.filtered <= PAGE_SIZE;
  $('#previous').disabled = offset === 0;
  $('#next').disabled = offset + PAGE_SIZE >= data.filtered;
  $('#page-label').textContent = `${Math.floor(offset / PAGE_SIZE) + 1} / ${Math.max(1, Math.ceil(data.filtered / PAGE_SIZE))}`;
}
function renderMessages(messages) {
  const list = $('#lead-messages'); list.replaceChildren();
  if (!messages.length) list.append(element('p', 'empty-transcript', 'Клиент оставил заявку без сообщений в чате.'));
  for (const message of messages) {
    const article = element('article', 'transcript-message ' + message.role);
    const author = message.role === 'user' ? 'КЛИЕНТ' : demo ? 'ДЕМО-КОНСУЛЬТАНТ' : 'ENERGYTOOL';
    article.append(element('div', 'transcript-label', `${author} · ${formatDate(message.created_at)}`),
      element('div', 'transcript-content', message.content));
    if (message.metadata.sources?.length) {
      const details = element('details', 'transcript-sources');
      details.append(element('summary', '', `Источники ответа · ${message.metadata.sources.length}`));
      const items = element('ul');
      for (const source of message.metadata.sources) items.append(element('li', '', source.title));
      details.append(items); article.append(details);
    }
    list.append(article);
  }
}
async function openLead(id, moveFocus = true) {
  const version = ++detailVersion;
  selectedId = id; selectRow();
  $('#detail-error').hidden = true;
  $('#selection-empty').hidden = true;
  $('#lead-detail').hidden = true;
  $('.lead-panel').setAttribute('aria-busy', 'true');
  try {
    const data = await get('/api/leads/' + encodeURIComponent(id));
    if (version !== detailVersion) return;
    const {lead, messages, session} = data;
    $('#company').textContent = lead.company;
    $('#lead-date').textContent = `Создана ${formatDate(lead.created_at)} · № ${lead.id.slice(0, 8)}`;
    $('#contact-name').textContent = lead.name;
    $('#contact-phone').textContent = lead.phone;
    $('#lead-summary').textContent = lead.summary;
    $('#message-count').textContent = `(${messages.length})`;
    $('#session-state').textContent = session.closed ? 'Сессия завершена' : 'Сессия открыта';
    renderMessages(messages);
    $('#lead-detail').hidden = false;
    history.replaceState(null, '', '/manager?id=' + encodeURIComponent(id));
    if (moveFocus) {
      $('#company').tabIndex = -1; $('#company').focus({preventScroll: true});
      if (window.matchMedia('(max-width: 720px)').matches) $('#lead-detail').scrollIntoView({behavior:'smooth', block:'start'});
      else $('.lead-panel').scrollTop = 0;
    }
  } catch (error) {
    if (version !== detailVersion) return;
    $('#detail-error').textContent = error.message;
    $('#detail-error').hidden = false;
  } finally {
    if (version === detailVersion) $('.lead-panel').setAttribute('aria-busy', 'false');
  }
}
$('#lead-search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  // Invalidate pending list requests before the debounce interval expires.
  listVersion++;
  searchTimer = setTimeout(() => {query = $('#lead-search').value.trim(); offset = 0; loadList().catch(showError);}, 250);
});
$('#refresh').onclick = async () => {
  $('#refresh').disabled = true;
  try {await loadList(); if (selectedId) await openLead(selectedId, false);}
  catch (error) {showError(error);}
  finally {$('#refresh').disabled = false;}
};
$('#previous').onclick = () => {offset = Math.max(0, offset - PAGE_SIZE); loadList().catch(showError);};
$('#next').onclick = () => {offset += PAGE_SIZE; loadList().catch(showError);};
(async () => {
  const status = await get('/api/status'); demo = status.demo;
  if (demo) {
    $('#manager-mode').textContent = 'Демо «СкладЛаб» · Только тестовые заявки. Отправки в CRM или реальному оператору нет.';
    $('#manager-mode').classList.add('demo');
  }
  await loadList();
  const initial = new URLSearchParams(location.search).get('id');
  if (initial) await openLead(initial, false);
  setInterval(() => {if (!document.hidden) loadList().catch(showError);}, 15000);
})().catch(showError);
