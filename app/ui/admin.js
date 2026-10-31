'use strict';
/* Operator panel. No frameworks; user text is only ever inserted with textContent. */
const NS = 'http://www.w3.org/2000/svg';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? '' : value);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function icon(name) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(NS, 'use'); use.setAttribute('href', '#i-' + name); svg.append(use);
  return svg;
}

const CATEGORY = {
  'complaint.insult': 'Оскорбления и токсичность', 'complaint.cheat': 'Читы и сторонние программы', 'complaint.dm': 'Убийство и урон без повода',
  'complaint.scam': 'Обман и мошенничество', 'complaint.rmt_ads': 'Реклама и продажа за реальные деньги', 'complaint.admin': 'Жалоба на администратора или апелляция',
  'unclassified': 'Не определено (нужен ручной разбор)', 'complaint.other': 'Другое нарушение', 'complaint.invalid': 'Не жалоба или нет описания', 'report.question': 'Вопрос по игре',
  'report.help': 'Просьба о помощи (застрял, баг)', 'report.complaint': 'Жалоба на игрока из игры', 'report.account': 'Аккаунт и доступ',
  'report.payment': 'Платёж и донат', 'report.offtopic': 'Оффтоп или пустое сообщение',
};
const PRIORITY = {
  p0: { label: 'Критично', tone: 'crit', hint: 'платёж, доступ к аккаунту или угроза' }, p1: { label: 'Высокий', tone: 'high', hint: 'читы, обман, реклама' },
  p2: { label: 'Обычный', tone: 'norm', hint: 'оскорбления, DM, остальные жалобы' }, p3: { label: 'Низкий', tone: 'low', hint: 'вопросы и оффтоп' },
};
const STATUS = {
  new: { label: 'Новое', tone: 'norm' }, in_review: { label: 'В работе', tone: 'warn' }, needs_info: { label: 'Ждём уточнений', tone: 'warn' },
  escalated: { label: 'У старшего', tone: 'high' }, resolved: { label: 'Решено', tone: 'ok' }, closed: { label: 'Закрыто', tone: 'low' },
};
const TRANSITIONS = {
  new: ['in_review', 'needs_info', 'escalated'], in_review: ['needs_info', 'escalated', 'resolved'], needs_info: ['in_review', 'escalated'],
  escalated: ['in_review', 'resolved'], resolved: ['closed', 'in_review'], closed: ['in_review'],
};
const ACTION_LABEL = {
  in_review: ['Взять в работу', 'check'], needs_info: ['Нужны уточнения от игрока', 'help'], escalated: ['Передать старшему', 'flag'],
  closed: ['Закрыть', 'close'], resolved: ['Отметить решённым без ответа', 'check'],
};
const LANG = { ru: 'Русский', kk: 'Казахский', uz: 'Узбекский', en: 'Английский', lat: 'Латиница (язык не определён)', und: 'Не определён', es: 'Испанский', pt: 'Португальский' };
const REASONS = {
  'решение о наказании подтверждает администратор': ['Игрок просит наказать другого игрока. Решение о наказании принимает только оператор.', 'warn'],
  critical_review: ['Критичная тема: платёж, доступ к аккаунту или угроза.', 'warn'], mandatory_human: ['Такие обращения всегда проверяет человек.', 'warn'],
  appeal_requires_human: ['Игрок просит снять наказание или подаёт апелляцию.', 'warn'],
  sanction_or_refund_requested: ['Игрок просит наказать, вернуть деньги или снять бан. Обещать это в ответе нельзя.', 'warn'],
  evidence_not_verified: ['Вложения помощник не видит. Проверьте их сами.', 'warn'],
  language_uncertain: ['Язык определён неуверенно (короткий или смешанный текст).', 'warn'], language_mixed: ['В тексте смешаны языки.', 'warn'],
  citation_from_category: ['Игрок не указал пункт, поэтому помощник выбрал подходящий по теме.', 'ok'],
  rule_ambiguous_or_unknown: ['Пункт из обращения не найден или подходит к нескольким разделам: он не цитируется.', 'warn'],
  rule_irrelevant_to_category: ['Пункт из обращения не подходит к теме жалобы: он не цитируется.', 'warn'],
  rule_unparsed: ['Пункт правил в обращении не удалось распознать.', 'warn'],
  duplicate_same_problem: ['Похоже на повтор: игрок уже писал об этом за последний час.', 'warn'],
  five_tickets_within_hour: ['Пять и более обращений за час: возможен спам.', 'warn'],
  sensitive_category_override: ['Чувствительную тему определили правила, а не обученная модель.', 'ok'],
  rules_unavailable: ['Правила не загружены: обращение разобрано вручную.', 'warn'], manual_triage_required: ['Нужен ручной разбор.', 'warn'],
  topic_selected_by_player: ['Тему выбрал сам игрок.', 'ok'],
  handling_auto: ['Безопасное обращение: на него можно отвечать без проверки.', 'ok'], handling_review: ['Ответ перед отправкой проверяет оператор.', 'ok'],
  handling_escalate: ['Нужно решение оператора до ответа.', 'warn'],
  classifier_calibrated: ['Использована обученная модель.', 'ok'], classifier_uncalibrated: ['Использована обученная модель.', 'ok'],
};
const HIDDEN_REASONS = new Set(['history_unavailable', 'policy_draft', 'confidence_empirical', 'history_same_problem_within_hour', 'classifier_fallback']);
const AUDIT_LABEL = { created: 'Обращение создано', draft_edited: 'Ответ изменён', draft_verified: 'Ответ проверен', attachment_added: 'Добавлено вложение', auto_closed_verified_faq: 'Закрыто автоматически (справочный ответ)' };

const state = { tickets: [], current: null, csrf: '', filter: 'human', sort: 'priority', query: '', busy: false, status: null, attachments: [] };

function ago(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return 'только что';
  if (seconds < 3600) return Math.floor(seconds / 60) + ' мин назад';
  if (seconds < 86400) return Math.floor(seconds / 3600) + ' ч назад';
  return Math.floor(seconds / 86400) + ' дн назад';
}
const clock = iso => new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
const isOpen = t => !['resolved', 'closed'].includes(t.status);
const needsHuman = t => isOpen(t) && (t.result.needs_human || t.status === 'escalated');
const isUrgent = t => isOpen(t) && ['p0', 'p1'].includes(t.result.priority);
const title = t => CATEGORY[t.result.category] || t.result.category;

function toast(text, kind = '') {
  const node = h('div', { class: 'toast ' + kind }, h('span', { text }), h('button', { type: 'button', 'aria-label': 'Закрыть уведомление', text: '\u00d7', onclick: () => node.remove() }));
  $('#toasts').append(node);
  setTimeout(() => node.remove(), kind === 'error' ? 9000 : 4500);
}
function badge(text, tone, iconName) { return h('span', { class: 'badge', 'data-tone': tone }, iconName ? icon(iconName) : null, text); }

async function http(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(path, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf }, body: body ? JSON.stringify(body) : undefined });
  } catch { setServiceState('error'); throw new Error('Нет связи с сервисом. Проверьте, что программа запущена, и повторите.'); }
  if (response.status === 401) { location.href = '/admin/login'; throw new Error('Нужно войти заново.'); }
  if (!response.ok) {
    let detail = '';
    try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : ''; } catch { /* no body */ }
    const fallback = { 409: 'Обращение изменилось. Обновите страницу и повторите.', 403: 'Действие запрещено. Войдите заново.', 422: 'Данные не прошли проверку.', 503: 'Сервис не готов.' }[response.status];
    throw new Error(detail || fallback || 'Не удалось выполнить действие (код ' + response.status + ').');
  }
  return response.json();
}

/* ---------- assistant status ---------- */
const MODE = { demo: 'демо на условных правилах', rules: 'правила и шаблоны', 'rules+model': 'правила, шаблоны и обученная модель', manual: 'ручной режим' };
function setServiceState(kind, text) {
  const chip = $('#status-chip'); chip.dataset.state = kind;
  $('#status-text').textContent = text || { ok: 'Помощник работает', warn: 'Помощник в ручном режиме', error: 'Нет связи с сервисом', loading: 'Проверяем помощника' }[kind];
  const banner = $('#banner');
  if (kind === 'warn') { banner.hidden = false; banner.className = 'banner'; banner.replaceChildren(h('span', { text: 'Правила игры не загружены, поэтому помощник не разбирает обращения. ' }), h('button', { type: 'button', class: 'link-btn', text: 'Загрузить rules.json', onclick: openHelp })); }
  else if (kind === 'error') { banner.hidden = false; banner.className = 'banner error'; banner.textContent = 'Нет связи с сервисом. Данные на экране могут быть устаревшими.'; }
  else banner.hidden = true;
}
async function refreshStatus() {
  try {
    const data = await (await fetch('/api/status', { credentials: 'same-origin' })).json();
    state.status = data;
    $('#rules-box').hidden = data.rules_loaded && !data.demo;
    if (!data.rules_loaded) setServiceState('warn');
    else setServiceState('ok', data.demo ? 'Помощник работает' : 'Помощник работает · ' + MODE[data.mode]);
    renderLive();
  } catch { setServiceState('error'); }
}
function renderLive() {
  const data = state.status; const list = $('#live'); list.replaceChildren();
  if (!data) return;
  const row = (name, value) => h('li', {}, h('span', { text: name }), h('strong', { text: value }));
  list.append(row('Правила игры', data.rules_loaded ? 'загружены, пунктов: ' + data.rules_count : 'не загружены'),
    row('Режим разбора', MODE[data.mode] || data.mode), row('Версия правил', data.rules_version || 'нет'),
    row('Обученная модель', data.model_loaded ? 'подключена' : 'не подключена (не требуется)'),
    row('Внешние сервисы', 'не используются'));
}
async function runSelftest() {
  const button = $('#selftest'); const out = $('#selftest-result'); button.setAttribute('aria-busy', 'true'); button.disabled = true; out.replaceChildren(h('p', { class: 'muted', text: 'Проверяем…' }));
  try {
    const data = await http('/admin/api/selftest', { method: 'POST', body: {} });
    out.replaceChildren();
    if (data.error) { out.append(h('p', { class: 'check-result bad', text: data.error })); return; }
    out.append(h('p', { class: 'check-result', text: 'Помощник ответил на все ' + data.results.length + ' тестовых обращения. Они нигде не сохранены.' }));
    for (const r of data.results) {
      out.append(h('div', { class: 'result' }, h('strong', { text: CATEGORY[r.category] + ' · ' + PRIORITY[r.priority].label }),
        h('p', { text: r.text }), h('p', { text: 'Нужен человек: ' + (r.needs_human ? 'да' : 'нет') + ' · пункты правил: ' + (r.cited.length ? r.cited.join(', ') : 'не требуются') + ' · ' + String(r.ms).replace('.', ',') + ' мс' })));
    }
  } catch (error) { out.replaceChildren(h('p', { class: 'check-result bad', text: error.message })); }
  finally { button.removeAttribute('aria-busy'); button.disabled = false; }
}

/* ---------- queue ---------- */
function visible() {
  const q = state.query.toLowerCase();
  const filter = { human: needsHuman, urgent: isUrgent, open: isOpen, all: () => true }[state.filter];
  const list = state.tickets.filter(filter).filter(t => !q || t.id.toLowerCase().includes(q) || (t.request.messages[0]?.text || '').toLowerCase().includes(q) || title(t).toLowerCase().includes(q) || (t.request.reported_nick || '').toLowerCase().includes(q));
  const rank = t => ({ p0: 0, p1: 1, p2: 2, p3: 3 }[t.result.priority] ?? 3);
  const byTime = (a, b) => new Date(a.created_at) - new Date(b.created_at);
  list.sort(state.sort === 'priority' ? (a, b) => rank(a) - rank(b) || byTime(a, b) : state.sort === 'new' ? (a, b) => byTime(b, a) : byTime);
  return list;
}
function renderQueue() {
  const t = state.tickets;
  $('#count').textContent = t.length; $('#n-human').textContent = t.filter(needsHuman).length; $('#n-urgent').textContent = t.filter(isUrgent).length;
  $('#n-open').textContent = t.filter(isOpen).length; $('#n-all').textContent = t.length;
  $$('.chip').forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.filter === state.filter)));
  const list = visible(); const ul = $('#queue'); ul.replaceChildren();
  for (const item of list) {
    const p = PRIORITY[item.result.priority] || PRIORITY.p3; const s = STATUS[item.status];
    const button = h('button', { type: 'button', class: 'q-item', 'data-p': item.result.priority, 'aria-current': String(state.current?.id === item.id), onclick: () => openTicket(item.id, true) },
      h('div', { class: 'q-top' }, h('span', { text: item.id }), h('span', { text: ago(item.created_at) })),
      h('div', { class: 'q-title', text: title(item) }), h('div', { class: 'q-text', text: item.request.messages[0]?.text || '' }),
      h('div', { class: 'q-meta' }, badge(p.label, p.tone), badge(s.label, s.tone), needsHuman(item) ? badge('Нужен человек', 'warn', 'user') : null));
    ul.append(h('li', {}, button));
  }
  const empty = $('#queue-empty'); empty.hidden = list.length > 0;
  if (!list.length) {
    const total = state.tickets.length;
    $('#queue-empty-title').textContent = total ? 'В этом разделе пусто' : 'Обращений пока нет';
    $('#queue-empty-text').textContent = total ? 'Выберите другой раздел фильтра, например «Все».' : 'Игроки создают обращения на странице поддержки. Чтобы посмотреть, как работает помощник, создайте тестовое обращение.';
  }
}
async function loadQueue(keepSelection = true) {
  const data = await http('/admin/api/tickets?limit=200');
  state.tickets = data.items;
  if (state.current) { const fresh = state.tickets.find(t => t.id === state.current.id); if (fresh && keepSelection) state.current = fresh; }
  renderQueue();
}

/* ---------- tabs ---------- */
const TABS = ['case', 'reply', 'files', 'history'];
function selectTab(name, focus = false) {
  for (const key of TABS) {
    const on = key === name; const tab = $('#tab-' + key);
    tab.setAttribute('aria-selected', String(on)); tab.tabIndex = on ? 0 : -1; $('#panel-' + key).hidden = !on;
    if (on && focus) tab.focus();
  }
  if (name === 'history') loadAudit();
}
$$('.tab').forEach(tab => {
  tab.addEventListener('click', () => selectTab(tab.id.slice(4)));
  tab.addEventListener('keydown', event => {
    const i = TABS.indexOf(tab.id.slice(4)); let n = null;
    if (event.key === 'ArrowRight') n = (i + 1) % TABS.length; else if (event.key === 'ArrowLeft') n = (i + TABS.length - 1) % TABS.length;
    else if (event.key === 'Home') n = 0; else if (event.key === 'End') n = TABS.length - 1;
    if (n !== null) { event.preventDefault(); selectTab(TABS[n], true); }
  });
});

/* ---------- ticket ---------- */
function nextStep(t) {
  const hint = {
    new: 'Прочитайте обращение и разбор помощника, поправьте текст ответа при необходимости и нажмите «Отправить ответ».',
    in_review: 'Обращение в работе. Проверьте текст ответа и нажмите «Отправить ответ» либо передайте старшему.',
    needs_info: 'Ждём уточнений от игрока. Когда ответ получен, верните обращение в работу.',
    escalated: 'Обращение у старшего. Когда решение принято, верните его в работу и отправьте ответ.',
    resolved: 'Ответ отмечен как отправленный. В игру он автоматически не уходит: скопируйте текст и отправьте вручную, если ещё не сделали.',
    closed: 'Обращение закрыто. Вернуть его в работу можно кнопкой ниже.',
  }[t.status];
  return hint;
}
function renderTicket(t, keepTab) {
  state.current = t;
  const p = PRIORITY[t.result.priority] || PRIORITY.p3; const s = STATUS[t.status]; const r = t.result;
  $('#ws-empty').hidden = true; $('#ticket').hidden = false;
  $('#t-id').textContent = t.id; $('#t-title').textContent = title(t); $('#t-sub').textContent = 'Создано ' + clock(t.created_at) + ' (' + ago(t.created_at) + ')';
  const pr = $('#t-priority'); pr.textContent = p.label; pr.dataset.tone = p.tone; const st = $('#t-status'); st.textContent = s.label; st.dataset.tone = s.tone;
  $('#next-step').textContent = nextStep(t);
  $('#t-text').textContent = t.request.messages[0]?.text || '';
  const x = r.extracted || {}; const facts = $('#t-facts'); facts.replaceChildren();
  const fact = (name, value) => facts.append(h('div', {}, h('dt', { text: name }), h('dd', { text: value })));
  fact('Ник обвиняемого', t.request.reported_nick || x.nickname || 'не указан'); fact('Сервер', t.request.region || x.server || 'не указан');
  fact('Вложений', String(t.request.images_count || 0)); fact('Пункты от игрока', (x.rule_refs || []).join(', ') || 'не указаны');
  $('#a-meta').textContent = r.meta ? 'Разобрано за ' + String(r.meta.ms).replace('.', ',') + ' мс · режим: ' + (MODE[r.meta.mode] || r.meta.mode) + (r.meta.rules_version ? ' · версия правил ' + r.meta.rules_version : '') : 'Разбор сохранён без технических данных.';
  $('#a-category').textContent = CATEGORY[r.category] || r.category;
  $('#a-priority').textContent = p.label + ' (' + p.hint + ')';
  $('#a-lang').textContent = LANG[r.lang] || r.lang;
  $('#a-human').textContent = needsHuman(t) ? 'Оператор (нужна проверка)' : 'Можно отвечать по шаблону';
  const percent = Math.round((r.confidence || 0) * 100);
  $('#a-conf-value').textContent = percent ? percent + '%' : 'не оценена'; $('#a-conf').setAttribute('aria-valuenow', String(percent)); $('#a-conf-bar').style.width = percent + '%';
  const reasons = $('#a-reasons'); reasons.replaceChildren(); const technical = [];
  for (const code of r.reasons || []) {
    if (HIDDEN_REASONS.has(code)) continue;
    const known = REASONS[code];
    if (known) reasons.append(h('li', { 'data-tone': known[1] }, icon(known[1] === 'ok' ? 'check' : 'alert'), h('span', { text: known[0] })));
    else if (code.startsWith('safety_')) reasons.append(h('li', { 'data-tone': 'warn' }, icon('alert'), h('span', { text: 'Проверка безопасности заменила текст ответа на нейтральный.' })));
    else technical.push(code);
  }
  if (!reasons.children.length) reasons.append(h('li', {}, icon('check'), h('span', { text: 'Особых причин для проверки нет.' })));
  $('#a-tech').textContent = technical.length ? technical.join(', ') : 'нет';
  const rules = $('#a-rules'); rules.replaceChildren();
  const cited = r.draft_reply?.cited || [];
  if (!cited.length) rules.append(h('p', { class: 'muted small', text: 'Пункты правил к этому обращению не подходят или не нужны.' }));
  for (const c of cited) rules.append(h('div', { class: 'rule' }, h('b', { text: 'Пункт ' + c.ref + ' (раздел ' + c.section_id + ')' }), h('p', { text: c.excerpt })));
  const draft = $('#draft'); draft.value = t.draft_text; updateDraftState();
  $('#check-result').hidden = true;
  renderStatusActions(t);
  $$('#ticket .btn[aria-busy]').forEach(b => b.removeAttribute('aria-busy'));
  const closedTicket = !isOpen(t);
  $('#escalate').disabled = closedTicket || !(TRANSITIONS[t.status] || []).includes('escalated');
  ['send', 'check', 'save'].forEach(id => { $('#' + id).disabled = closedTicket; }); draft.readOnly = closedTicket;
  $('#audit').replaceChildren(); $('#draft-count').dataset.note = ''; updateDraftState(); selectTab(keepTab || 'case');
}
function updateDraftState() {
  const t = state.current; if (!t) return; const text = $('#draft').value; const dirty = text !== t.draft_text; const badgeEl = $('#draft-state');
  const [label, tone] = dirty ? ['Есть несохранённые изменения', 'warn'] : t.draft_approved ? ['Проверен', 'ok'] : ['Не проверен', 'low'];
  badgeEl.textContent = label; badgeEl.dataset.tone = tone; const note = $('#draft-count').dataset.note; $('#draft-count').textContent = text.length + ' из 20 000 символов' + (note && !dirty ? ' · ' + note : '');
}
function renderStatusActions(t) {
  const box = $('#status-actions'); box.replaceChildren();
  for (const target of TRANSITIONS[t.status] || []) {
    if (target === 'escalated' || (target === 'resolved' && t.status === 'in_review')) continue; // sending the reply is the normal way to resolve
    const [label, iconName] = ACTION_LABEL[target];
    box.append(h('button', { type: 'button', class: 'btn' + (target === 'escalated' ? ' btn-danger' : ''), onclick: () => run(async () => { await changeStatus(target); toast('Статус: ' + STATUS[target].label, 'ok'); }) }, icon(iconName), h('span', { text: label })));
  }
}
async function openTicket(id, push) {
  if (isDirty() && state.current?.id !== id) { try { await saveDraft(); } catch (error) { toast('Черновик не сохранён: ' + error.message, 'error'); return; } }
  let ticket = state.tickets.find(t => t.id === id);
  try { ticket = await http('/admin/api/tickets/' + encodeURIComponent(id)); } catch (error) { toast(error.message, 'error'); return; }
  renderTicket(ticket); renderQueue();
  $('#layout').dataset.view = 'ticket';
  if (push && location.hash !== '#' + id) history.pushState(null, '', '#' + id);
  $('#workspace').scrollTo({ top: 0 }); $('#workspace').focus({ preventScroll: true });
  loadAttachments(id);
}
async function loadAttachments(id) {
  const box = $('#t-files'); box.replaceChildren(); $('#files-empty').hidden = false; $('#files-count').hidden = true;
  $('#files-note').hidden = !(state.current?.request.images_count);
  try {
    const data = await http('/admin/api/tickets/' + encodeURIComponent(id) + '/attachments');
    if (state.current?.id !== id || !data.items.length) return;
    $('#files-empty').hidden = true; $('#files-count').hidden = false; $('#files-count').textContent = data.items.length;
    for (const item of data.items) box.append(h('a', { href: '/admin/api/tickets/' + encodeURIComponent(id) + '/attachments/' + encodeURIComponent(item.id), download: '' }, icon('file'), item.filename + ' (' + Math.max(1, Math.round(item.size / 1024)) + ' КБ)'));
  } catch { /* attachments are optional */ }
}
async function loadAudit() {
  const t = state.current; if (!t) return;
  try {
    const data = await http('/admin/api/tickets/' + encodeURIComponent(t.id) + '/audit'); const list = $('#audit'); list.replaceChildren();
    for (const event of data.events) {
      let text = AUDIT_LABEL[event.action] || event.action;
      if (event.action === 'status_changed') text = 'Статус: ' + (STATUS[event.detail.from]?.label || event.detail.from) + ' → ' + (STATUS[event.detail.to]?.label || event.detail.to) + (event.detail.note ? '. Комментарий: ' + event.detail.note : '');
      list.append(h('li', {}, h('time', { text: clock(event.occurred_at) + ' · ' + (event.actor === 'operator' ? 'оператор' : event.actor) }), text));
    }
  } catch (error) { toast(error.message, 'error'); }
}
function setBusy(on) { state.busy = on; $$('#ticket .btn, #ticket textarea, #ticket input').forEach(el => { if (on) el.setAttribute('aria-busy', 'true'); else el.removeAttribute('aria-busy'); }); }
async function run(task) {
  if (state.busy) return; setBusy(true);
  try { await task(); } catch (error) { toast(error.message, 'error'); if (/изменил|Обновите/.test(error.message)) await loadQueue().catch(() => {}); }
  finally { setBusy(false); }
}
function currentTab() { return TABS.find(k => $('#tab-' + k).getAttribute('aria-selected') === 'true'); }
function applyTicket(ticket) { state.tickets = state.tickets.map(t => t.id === ticket.id ? ticket : t); renderTicket(ticket, currentTab()); renderQueue(); }
async function saveDraft() {
  const t = state.current; const text = $('#draft').value;
  if (!text.trim()) throw new Error('Ответ пустой. Напишите текст или верните текст помощника.');
  if (text === t.draft_text) return t;
  const updated = await http('/admin/api/tickets/' + encodeURIComponent(t.id) + '/draft', { method: 'PUT', body: { version: t.version, text } });
  applyTicket(updated); return updated;
}
async function verify() {
  const t = await saveDraft(); const result = await http('/admin/api/tickets/' + encodeURIComponent(t.id) + '/verify', { method: 'POST', body: { version: t.version } });
  if (result.approved) applyTicket(result.ticket);
  const box = $('#check-result'); box.hidden = false; box.className = 'check-result' + (result.approved ? '' : ' bad');
  box.textContent = result.approved ? 'Проверка пройдена: цитаты существуют, обещаний наказания, разбана или возврата денег нет.' : 'Проверка не пройдена: ' + (result.reasons || []).map(code => (REASONS[code]?.[0] || code)).join(' ') + ' Исправьте текст или верните текст помощника.';
  return result;
}
async function changeStatus(target, note = $('#note').value.trim()) {
  const t = state.current; const updated = await http('/admin/api/tickets/' + encodeURIComponent(t.id) + '/status', { method: 'POST', body: { version: t.version, status: target, note } });
  $('#note').value = ''; applyTicket(updated); return updated;
}
async function sendReply() {
  const result = await verify(); if (!result.approved) throw new Error('Ответ не отправлен: он не прошёл проверку.');
  let t = state.current;
  if (['new', 'needs_info'].includes(t.status)) t = await changeStatus('in_review', '');
  await changeStatus('resolved', $('#note').value.trim() || 'Ответ проверен и отмечен как отправленный');
  selectTab('reply');
  try { await navigator.clipboard.writeText(state.current.draft_text); toast('Ответ отмечен как отправленный и скопирован. Отправьте его игроку в игре.', 'ok'); }
  catch { toast('Ответ отмечен как отправленный. Скопируйте текст кнопкой «Скопировать» и отправьте игроку.', 'ok'); }
}

/* ---------- wiring ---------- */
let autosaveTimer = null;
function isDirty() { const t = state.current; return !!t && !$('#draft').readOnly && $('#draft').value !== t.draft_text; }
$('#draft').addEventListener('input', () => {
  updateDraftState(); clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(async () => {
    if (state.busy || !isDirty() || !$('#draft').value.trim()) return;
    setBusy(true);
    try { await saveDraft(); $('#draft-count').dataset.note = 'Сохранено автоматически'; updateDraftState(); }
    catch { $('#draft-count').dataset.note = 'Не удалось сохранить автоматически'; updateDraftState(); }
    finally { setBusy(false); }
  }, 1500);
});
window.addEventListener('beforeunload', event => { if (isDirty()) { event.preventDefault(); event.returnValue = ''; } });
$('#next-ticket').addEventListener('click', () => {
  const list = visible().filter(t => t.id !== state.current?.id && isOpen(t));
  if (list.length) openTicket(list[0].id, true); else { toast('Больше нет обращений в этом разделе.', 'ok'); showQueue(); }
});
$('#restore').addEventListener('click', () => { const t = state.current; if (t) { $('#draft').value = t.result.draft_reply.text; updateDraftState(); } });
$('#save').addEventListener('click', () => run(async () => { await saveDraft(); toast('Ответ сохранён.', 'ok'); }));
$('#check').addEventListener('click', () => run(verify));
$('#send').addEventListener('click', () => run(sendReply));
$('#escalate').addEventListener('click', () => run(async () => { await changeStatus('escalated'); toast('Передано на проверку старшему.', 'ok'); }));
$('#copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#draft').value); toast('Текст скопирован.', 'ok'); } catch { toast('Браузер не разрешил копирование. Выделите текст и скопируйте вручную.', 'error'); } });
$('#back').addEventListener('click', () => { if (location.hash) history.back(); else showQueue(); });
function showQueue() { $('#layout').dataset.view = 'queue'; state.current = null; $('#ticket').hidden = true; $('#ws-empty').hidden = false; renderQueue(); }
window.addEventListener('popstate', () => { const id = location.hash.slice(1); if (id) openTicket(id, false); else showQueue(); });
$$('.chip').forEach(chip => chip.addEventListener('click', () => { state.filter = chip.dataset.filter; renderQueue(); }));
$('#sort').addEventListener('change', event => { state.sort = event.target.value; renderQueue(); });
let timer; $('#search').addEventListener('input', event => { clearTimeout(timer); timer = setTimeout(() => { state.query = event.target.value.trim(); renderQueue(); }, 150); });
$('#refresh').addEventListener('click', async () => { try { await loadQueue(); await refreshStatus(); toast('Очередь обновлена.', 'ok'); } catch (error) { toast(error.message, 'error'); } });
$('#logout').addEventListener('click', async () => { try { await http('/admin/api/logout', { method: 'POST', body: {} }); } catch { /* leave anyway */ } location.href = '/admin/login'; });
document.addEventListener('keydown', event => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '') || document.querySelector('dialog[open]');
  if (event.key === '/' && !typing) { event.preventDefault(); $('#search').focus(); return; }
  if (typing || event.ctrlKey || event.metaKey || event.altKey || !['j', 'k'].includes(event.key.toLowerCase())) return;
  const list = visible(); if (!list.length) return; const i = list.findIndex(t => t.id === state.current?.id);
  const next = list[Math.min(list.length - 1, Math.max(0, i + (event.key.toLowerCase() === 'j' ? 1 : -1)))]; if (next) openTicket(next.id, true);
});
/* dialogs */
$$('dialog [data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$$('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); }));
const openHelp = () => { renderLive(); refreshStatus(); $('#help-dialog').showModal(); };
$('#open-help').addEventListener('click', openHelp); $('#status-chip').addEventListener('click', openHelp); $('#selftest').addEventListener('click', runSelftest);
$('#rules-pick').addEventListener('click', () => $('#rules-file').click());
$('#rules-file').addEventListener('change', async event => {
  const file = event.target.files[0]; event.target.value = ''; if (!file) return;
  try {
    const body = JSON.parse(await file.text());
    await http('/admin/api/rules', { method: 'POST', body });
    await refreshStatus(); toast('Правила загружены. Помощник готов к работе.', 'ok');
  } catch (error) { toast(error instanceof SyntaxError ? 'Файл не похож на JSON. Выберите rules.json.' : error.message, 'error'); }
});
const SAMPLE = 'Игрок Arman_Petrov оскорбил меня и мою семью в чате на 12 сервере, скрины есть, 2.1 ОП';
const openNew = () => { $('#new-form').reset(); $('#new-dialog').showModal(); $('#n-text').focus(); };
$('#new-ticket').addEventListener('click', openNew); $('#empty-new').addEventListener('click', openNew);
$('#n-sample').addEventListener('click', () => { $('#n-kind').value = 'complaint'; $('#n-text').value = SAMPLE; $('#n-files').checked = true; });
$('#new-form').addEventListener('submit', async event => {
  event.preventDefault(); const submit = $('#n-submit'); submit.disabled = true; submit.setAttribute('aria-busy', 'true');
  const request = { kind: $('#n-kind').value, messages: [{ role: 'player', text: $('#n-text').value }], images_count: $('#n-files').checked ? 1 : 0 };
  if ($('#n-nick').value.trim()) request.reported_nick = $('#n-nick').value.trim(); if ($('#n-region').value.trim()) request.region = $('#n-region').value.trim();
  try {
    const ticket = await http('/admin/api/tickets', { method: 'POST', body: { request } });
    $('#new-dialog').close(); await loadQueue(); state.filter = 'all'; renderQueue(); await openTicket(ticket.id, true);
    toast('Обращение создано. Помощник разобрал его' + (ticket.result.meta ? ' за ' + String(ticket.result.meta.ms).replace('.', ',') + ' мс.' : '.'), 'ok');
  } catch (error) { toast(error.message, 'error'); } finally { submit.disabled = false; submit.removeAttribute('aria-busy'); }
});
(async function start() {
  try {
    const session = await http('/admin/api/session'); state.csrf = session.csrf;
    await Promise.all([loadQueue(), refreshStatus()]);
    const id = location.hash.slice(1); if (id) await openTicket(id, false);
    else if (!state.tickets.filter(needsHuman).length && state.tickets.length) { state.filter = 'all'; renderQueue(); }
  } catch (error) { toast(error.message, 'error'); }
  setInterval(() => { refreshStatus(); loadQueue().catch(() => {}); }, 30000);
})();
