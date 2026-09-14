const API = {
  list: '/api/v1/manager/complaints',
  update: (id) => `/api/v1/manager/complaints/${encodeURIComponent(id)}`,
};

export const fixtureComplaints = [
  {
    complaint_id: 'cmp_01J8N4K2D7Q9', complaint_type: 'delivery_damage', status: 'queued', created_at: '2026-09-12T08:18:00Z',
    complaint_text: 'The dresser arrived this morning with a cracked drawer front. Please report the damage to a manager.',
    consent_source: 'explicit_request', customer_context: 'Dresser delivery; order details remain in the protected runtime context.',
    internal_notes: '', version: 1,
    audit: [
      { at: '2026-09-12T08:18:03Z', text: 'Complaint created from an explicit customer request.' },
      { at: '2026-09-12T08:18:03Z', text: 'Queued for manager review · model mock-1.0 · index idx_demo_001.' },
    ],
  },
  {
    complaint_id: 'cmp_01J8N31B5M6P', complaint_type: 'missing_item_or_part', status: 'acknowledged', created_at: '2026-09-12T07:54:00Z',
    complaint_text: 'The wardrobe package is missing the rail and fittings bag. I confirmed that this should be sent as a complaint.',
    consent_source: 'confirmed', customer_context: 'Missing assembly parts reported after delivery.', internal_notes: 'Check packing manifest before reply.', version: 1,
    audit: [
      { at: '2026-09-12T07:53:42Z', text: 'Customer confirmed the prepared complaint.' },
      { at: '2026-09-12T07:54:00Z', text: 'Complaint queued for manager review.' },
      { at: '2026-09-12T08:02:16Z', text: 'Acknowledged by local-demo-manager.' },
    ],
  },
  {
    complaint_id: 'cmp_01J8MZZ91K4R', complaint_type: 'delivery_delay', status: 'queued', created_at: '2026-09-12T07:36:00Z',
    complaint_text: 'The delivery window ended yesterday and nothing arrived. Please pass this to your support manager.',
    consent_source: 'explicit_request', customer_context: 'Customer reports missed delivery window.', internal_notes: '', version: 1,
    audit: [
      { at: '2026-09-12T07:36:19Z', text: 'Complaint created from an explicit customer request.' },
      { at: '2026-09-12T07:36:19Z', text: 'Queued for manager review.' },
    ],
  },
  {
    complaint_id: 'cmp_01J8MYQ3X2Z8', complaint_type: 'product_quality', status: 'resolved', created_at: '2026-09-11T16:20:00Z',
    complaint_text: 'The cabinet door finish is uneven. Please file this complaint for me.',
    consent_source: 'explicit_request', customer_context: 'Surface finish concern on cabinet door.', internal_notes: 'Resolution recorded outside this demonstration.', version: 1,
    audit: [
      { at: '2026-09-11T16:20:04Z', text: 'Complaint queued for manager review.' },
      { at: '2026-09-11T16:29:12Z', text: 'Acknowledged by local-demo-manager.' },
      { at: '2026-09-12T07:12:31Z', text: 'Marked resolved by local-demo-manager.' },
    ],
  },
];

const state = { complaints: [], selectedId: null, loading: false };
const list = document.querySelector('#complaint-list');
const detail = document.querySelector('#complaint-detail');
const search = document.querySelector('#search');
const statusFilter = document.querySelector('#status-filter');
const subtypeFilter = document.querySelector('#subtype-filter');
const resultCount = document.querySelector('#result-count');
const openCount = document.querySelector('#open-count');
const emptyState = document.querySelector('#empty-state');
const appShell = document.querySelector('#manager-app');
const loginPanel = document.querySelector('#login-panel');
const loginForm = document.querySelector('#login-form');
const loginError = document.querySelector('#login-error');

export function safeText(value) { return typeof value === 'string' ? value : ''; }
export function label(value) { return safeText(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()); }

async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (response.status === 401) throw new Error('session_expired');
  if (!response.ok) throw new Error(`request_failed_${response.status}`);
  return response;
}

function liveMode() {
  return !new URLSearchParams(location.search).has('fixture');
}

function showLogin(message = '') {
  if (appShell) appShell.hidden = true;
  if (loginPanel) loginPanel.hidden = false;
  if (loginError) {
    loginError.textContent = message;
    loginError.hidden = !message;
  }
}

function showLiveError(message) {
  if (!appShell) return;
  appShell.hidden = false;
  const old = appShell.querySelector('.error-banner[data-live-error]');
  if (old) old.remove();
  const banner = document.createElement('div');
  banner.className = 'error-banner';
  banner.dataset.liveError = 'true';
  banner.setAttribute('role', 'alert');
  banner.textContent = message;
  appShell.prepend(banner);
}

async function ensureManagerSession() {
  try {
    const response = await request('/api/v1/manager/session');
    return response.json();
  } catch (error) {
    if (error.message === 'session_expired' || error.message === 'request_failed_401') {
      showLogin();
    }
    throw error;
  }
}

async function login(event) {
  event.preventDefault();
  const submit = loginForm?.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  if (loginError) loginError.hidden = true;
  try {
    const formData = new FormData(loginForm);
    await request('/api/v1/manager/session', {
      method: 'POST',
      body: JSON.stringify({ email: formData.get('email'), password: formData.get('password') }),
    });
    if (loginPanel) loginPanel.hidden = true;
    if (appShell) appShell.hidden = false;
    await loadComplaints();
  } catch (error) {
    if (loginError) {
      loginError.textContent = error.message === 'session_expired'
        ? 'The email or password was not accepted.'
        : 'The manager service is unavailable. Please retry.';
      loginError.hidden = false;
    }
  } finally {
    if (submit) submit.disabled = false;
  }
}

function filteredComplaints() {
  const term = search.value.trim().toLowerCase();
  return state.complaints.filter((complaint) => {
    const statusMatches = statusFilter.value === 'all' || (statusFilter.value === 'open' ? complaint.status !== 'resolved' : complaint.status === statusFilter.value);
    const subtypeMatches = subtypeFilter.value === 'all' || complaint.complaint_type === subtypeFilter.value;
    const textMatches = !term || `${complaint.complaint_id} ${complaint.complaint_text}`.toLowerCase().includes(term);
    return statusMatches && subtypeMatches && textMatches;
  });
}

export function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown time' : new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(date) + ' UTC';
}

function renderList() {
  const complaints = filteredComplaints();
  list.replaceChildren();
  complaints.forEach((complaint) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'complaint-row';
    button.dataset.id = complaint.complaint_id;
    button.setAttribute('aria-current', String(complaint.complaint_id === state.selectedId));
    const title = document.createElement('strong');
    title.textContent = label(complaint.complaint_type);
    const time = document.createElement('time');
    time.dateTime = complaint.created_at;
    time.textContent = formatTime(complaint.created_at).replace(' UTC', '');
    const excerpt = document.createElement('p');
    excerpt.textContent = complaint.complaint_text;
    const footer = document.createElement('span');
    footer.className = 'row-footer';
    footer.append(statusBadge(complaint.status));
    const reference = document.createElement('span');
    reference.className = 'reference';
    reference.textContent = complaint.complaint_id;
    footer.append(reference);
    button.append(title, time, excerpt, footer);
    button.addEventListener('click', () => selectComplaint(complaint.complaint_id));
    item.append(button);
    list.append(item);
  });
  resultCount.textContent = `${complaints.length} complaint${complaints.length === 1 ? '' : 's'}`;
  openCount.textContent = String(state.complaints.filter((item) => item.status !== 'resolved').length);
  emptyState.hidden = complaints.length > 0;
}

function statusBadge(status) {
  const badge = document.createElement('span');
  badge.className = `status ${status}`;
  badge.textContent = label(status);
  return badge;
}

function selectComplaint(id) {
  state.selectedId = id;
  renderList();
  const complaint = state.complaints.find((item) => item.complaint_id === id);
  if (complaint) renderDetail(complaint);
  if (matchMedia('(max-width: 920px)').matches) detail.scrollIntoView({ block: 'start' });
}

function renderDetail(complaint) {
  detail.replaceChildren();
  const top = document.createElement('div'); top.className = 'detail-top';
  const headingGroup = document.createElement('div');
  const heading = document.createElement('h2'); heading.textContent = label(complaint.complaint_type);
  const meta = document.createElement('p'); meta.textContent = `${complaint.complaint_id} · ${formatTime(complaint.created_at)}`;
  headingGroup.append(heading, meta);
  const actions = document.createElement('div'); actions.className = 'detail-actions';
  if (complaint.status === 'queued') actions.append(actionButton('Acknowledge', 'primary', () => updateComplaint(complaint, { status: 'acknowledged' })));
  if (complaint.status !== 'resolved') actions.append(actionButton('Mark resolved', 'secondary', () => updateComplaint(complaint, { status: 'resolved' })));
  top.append(headingGroup, actions);

  const data = document.createElement('dl'); data.className = 'detail-grid';
  addFact(data, 'Status', label(complaint.status));
  addFact(data, 'Subtype', label(complaint.complaint_type));
  addFact(data, 'Consent source', complaint.consent_source === 'confirmed' ? 'Customer confirmation' : 'Explicit request');
  addFact(data, 'Created', formatTime(complaint.created_at));
  addFact(data, 'Customer context', complaint.customer_context || 'No additional context');

  const excerpt = document.createElement('section'); excerpt.className = 'excerpt';
  const excerptHeading = document.createElement('h3'); excerptHeading.textContent = 'Conversation excerpt';
  const quote = document.createElement('blockquote'); quote.textContent = complaint.complaint_text;
  excerpt.append(excerptHeading, quote);

  const notes = document.createElement('section'); notes.className = 'notes';
  const notesHeading = document.createElement('h3'); notesHeading.textContent = 'Internal note';
  const noteLabel = document.createElement('label'); noteLabel.htmlFor = 'internal-note'; noteLabel.textContent = 'Visible to managers only';
  const textarea = document.createElement('textarea'); textarea.id = 'internal-note'; textarea.maxLength = 2000; textarea.placeholder = 'Add concise review context'; textarea.value = complaint.internal_notes || '';
  const save = actionButton('Save note', 'primary', () => updateComplaint(complaint, { internal_notes: textarea.value }));
  const saveStatus = document.createElement('span'); saveStatus.className = 'save-status'; saveStatus.setAttribute('role', 'status');
  save.addEventListener('manager:saved', () => { saveStatus.textContent = 'Saved'; });
  notes.append(notesHeading, noteLabel, textarea, save, saveStatus);

  const audit = document.createElement('section'); audit.className = 'audit';
  const auditHeading = document.createElement('h3'); auditHeading.textContent = 'Audit history';
  const timeline = document.createElement('ol');
  complaint.audit.forEach((event) => {
    const item = document.createElement('li');
    const time = document.createElement('time'); time.dateTime = event.at; time.textContent = formatTime(event.at).replace(' UTC', '');
    const text = document.createElement('p'); text.textContent = event.text;
    item.append(time, text); timeline.append(item);
  });
  audit.append(auditHeading, timeline);
  detail.append(top, data, excerpt, notes, audit);
  detail.focus({ preventScroll: true });
}

function addFact(listElement, term, description) {
  const wrapper = document.createElement('div');
  const dt = document.createElement('dt'); dt.textContent = term;
  const dd = document.createElement('dd'); dd.textContent = safeText(description);
  wrapper.append(dt, dd); listElement.append(wrapper);
}

function actionButton(text, style, handler) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = `button ${style}`; button.textContent = text;
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { await handler(); button.dispatchEvent(new CustomEvent('manager:saved')); }
    finally { if (button.isConnected) button.disabled = false; }
  });
  return button;
}

async function updateComplaint(complaint, patch) {
  try {
    const response = await request(API.update(complaint.complaint_id), { method: 'PATCH', body: JSON.stringify({ ...patch, version: complaint.version }) });
    const updated = await response.json();
    Object.assign(complaint, updated);
  } catch (error) {
    if (!new URLSearchParams(location.search).has('fixture')) {
      if (error.message === 'session_expired') showLogin('Manager session expired. Sign in again to continue.');
      const banner = document.createElement('div'); banner.className = 'error-banner'; banner.setAttribute('role', 'alert');
      banner.textContent = error.message === 'session_expired' ? 'Manager session expired. Sign in again to continue.' : 'The update was not saved. Retry when the runtime is available.';
      detail.prepend(banner);
      return;
    }
    Object.assign(complaint, patch);
    complaint.audit.push({ at: new Date().toISOString(), text: patch.status ? `${label(patch.status)} by local-demo-manager.` : 'Internal note updated by local-demo-manager.' });
  }
  renderList();
  if (!Object.hasOwn(patch, 'internal_notes')) renderDetail(complaint);
}

async function loadComplaints() {
  if (!liveMode()) {
    state.complaints = structuredClone(fixtureComplaints);
  } else {
    try {
      await ensureManagerSession();
      const response = await request(API.list);
      const payload = await response.json();
      const records = Array.isArray(payload) ? payload : payload.complaints || [];
      state.complaints = records;
      if (appShell) appShell.hidden = false;
    } catch (error) {
      state.complaints = [];
      if (error.message !== 'request_failed_401' && error.message !== 'session_expired') {
        showLiveError('The live manager queue is unavailable. No fixture records were loaded.');
      }
      renderList();
      return;
    }
  }
  renderList();
  const first = filteredComplaints()[0];
  if (first) selectComplaint(first.complaint_id);
}

if (list) {
  [search, statusFilter, subtypeFilter].forEach((control) => control.addEventListener('input', renderList));
  if (loginForm) loginForm.addEventListener('submit', login);
  if (liveMode()) {
    if (appShell) appShell.hidden = true;
    showLogin();
  }
  loadComplaints();
}
