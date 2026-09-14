const API = {
  conversations: '/api/v1/conversations',
  events: (conversationId) => `/api/v1/conversations/${encodeURIComponent(conversationId)}/events`,
  messages: (conversationId) => `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
  confirm: (conversationId, draftId) => `/api/v1/conversations/${encodeURIComponent(conversationId)}/complaints/${encodeURIComponent(draftId)}/confirm`,
  discard: (conversationId, draftId) => `/api/v1/conversations/${encodeURIComponent(conversationId)}/complaints/${encodeURIComponent(draftId)}`,
};

export const fixtures = {
  catalog: {
    customer: 'Is the Alder dining table solid wood, and how should I care for it?',
    assistant: 'The Alder dining table uses a solid oak top with an oak-veneered support panel. Wipe spills promptly with a soft, damp cloth and avoid abrasive cleaners or placing hot cookware directly on the surface.',
    citations: [
      { id: 'S1', title: 'Alder dining table', detail: 'Materials · Solid oak top; oak-veneered support panel · Updated 12 Sep 2026' },
      { id: 'S2', title: 'Wood furniture care', detail: 'Care guide · Cleaning and heat protection · Updated 08 Sep 2026' },
    ],
  },
  abstention: {
    customer: 'Will the Alder table be available in walnut next spring?',
    assistant: 'I cannot verify a future walnut option from the current company information. A manager can help with upcoming range questions, but availability should not be assumed until it is published.',
    state: { kind: 'warning', title: 'Information not verified', text: 'No current source supports this product option or future availability.' },
  },
  confirmation: {
    customer: 'The dresser arrived with a cracked drawer front and I am disappointed.',
    assistant: 'I can prepare this as a product-quality complaint for the manager queue. Please confirm before I submit it.',
    state: { kind: 'warning confirmation', title: 'Submit this complaint?', text: 'Cracked drawer front on delivered dresser · Product quality', draftId: 'draft_demo_01' },
  },
  submitted: {
    customer: 'Please report the damaged dresser to a manager.',
    assistant: 'Your complaint has been submitted to the manager queue. Keep the reference below if you need to follow up.',
    state: { kind: 'success', title: 'Complaint queued', text: 'A manager can now review the complaint and conversation context.', complaintId: 'cmp_01J8N4K2D7Q9' },
  },
  degraded: {
    customer: 'What is the delivery charge to North District?',
    assistant: 'Company information is temporarily unavailable, so I cannot verify the delivery charge. Please retry; no answer has been inferred from memory.',
    state: { kind: 'error', title: 'Company information unavailable', text: 'The knowledge service did not respond. Your message was not changed or submitted.', retry: true },
  },
};

const state = { conversationId: null, draftId: null, lastMessage: '', busy: false };
const messages = document.querySelector('#messages');
const form = document.querySelector('#message-form');
const input = document.querySelector('#message-input');
const runtimeStatus = document.querySelector('#runtime-status');
const fixtureSelect = document.querySelector('#fixture-select');

export function safeText(value) { return typeof value === 'string' ? value : ''; }

function formatTime(value) {
  return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(value);
}

function messageItem(role, body, timestamp = new Date()) {
  const item = document.createElement('li');
  item.className = `message ${role}`;
  const meta = document.createElement('p');
  meta.className = 'message-meta';
  meta.textContent = role === 'customer' ? 'You' : 'Support assistant';
  const content = document.createElement('div');
  content.className = 'message-body';
  const paragraph = document.createElement('p');
  paragraph.textContent = safeText(body);
  content.append(paragraph);
  const time = document.createElement('time');
  time.className = 'message-time';
  time.dateTime = timestamp.toISOString();
  time.textContent = formatTime(timestamp);
  item.append(meta, content, time);
  return { item, content, paragraph };
}

function addCitations(container, citations = []) {
  if (!citations.length) return;
  const list = document.createElement('ul');
  list.className = 'citations';
  list.setAttribute('aria-label', 'Sources');
  citations.forEach((citation) => {
    const fragment = document.querySelector('#citation-template').content.cloneNode(true);
    const button = fragment.querySelector('button');
    const detail = fragment.querySelector('.citation-detail');
    button.textContent = `${safeText(citation.id || citation.citation_id)} · ${safeText(citation.title)}`;
    detail.textContent = safeText(citation.detail || citation.content || 'Source details unavailable.');
    button.addEventListener('click', () => {
      const expanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', String(!expanded));
      detail.hidden = expanded;
    });
    list.append(fragment);
  });
  container.append(list);
}

function addStatePanel(container, panel) {
  if (!panel) return;
  const section = document.createElement('section');
  section.className = `state-panel ${panel.kind || ''}`;
  const heading = document.createElement('h2');
  heading.textContent = safeText(panel.title);
  const text = document.createElement('p');
  text.textContent = safeText(panel.text);
  section.append(heading, text);
  if (panel.complaintId) {
    const id = document.createElement('span');
    id.className = 'complaint-id';
    id.textContent = safeText(panel.complaintId);
    section.append(id);
  }
  const actions = document.createElement('div');
  actions.className = 'action-row';
  if (panel.draftId) {
    state.draftId = panel.draftId;
    actions.append(makeButton('Confirm and submit', 'primary', confirmComplaint), makeButton('Not now', 'secondary', discardComplaint));
  }
  if (panel.retry) actions.append(makeButton('Retry', 'primary', retryLastMessage));
  if (actions.childElementCount) section.append(actions);
  container.append(section);
}

function makeButton(label, style, handler) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `button ${style}`;
  button.textContent = label;
  button.addEventListener('click', handler);
  return button;
}

export function renderFixture(name = 'catalog') {
  const fixture = fixtures[name] || fixtures.catalog;
  state.draftId = null;
  messages.replaceChildren();
  const now = new Date();
  const customer = messageItem('customer', fixture.customer, new Date(now.getTime() - 60_000));
  const assistant = messageItem('assistant', fixture.assistant, now);
  messages.append(customer.item, assistant.item);
  addCitations(assistant.content, fixture.citations);
  addStatePanel(assistant.content, fixture.state);
  state.lastMessage = fixture.customer;
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...options.headers },
  });
  if (response.status === 401) throw new Error('session_expired');
  if (!response.ok) throw new Error(`request_failed_${response.status}`);
  return response;
}

async function ensureConversation() {
  if (state.conversationId) return state.conversationId;
  const response = await request(API.conversations, { method: 'POST', body: '{}' });
  const payload = await response.json();
  state.conversationId = payload.conversation_id;
  if (!state.conversationId) throw new Error('invalid_conversation_response');
  return state.conversationId;
}

function setBusy(busy, label = 'checking company information') {
  state.busy = busy;
  runtimeStatus.hidden = !busy;
  runtimeStatus.querySelector('span:last-child').textContent = label;
  form.querySelector('button').disabled = busy;
  input.setAttribute('aria-busy', String(busy));
}

async function submitMessage(event) {
  event?.preventDefault();
  if (state.busy) return;
  const text = input.value.trim();
  if (!text) return;
  state.lastMessage = text;
  messages.append(messageItem('customer', text).item);
  input.value = '';
  setBusy(true);
  const assistant = messageItem('assistant', '');
  assistant.item.hidden = true;
  messages.append(assistant.item);
  try {
    const conversationId = await ensureConversation();
    const response = await request(API.messages(conversationId), { method: 'POST', headers: { Accept: 'text/event-stream, application/json' }, body: JSON.stringify({ message: text }) });
    if (!(response.headers.get('content-type') || '').includes('text/event-stream')) throw new Error('invalid_runtime_response');
    assistant.item.hidden = false;
    await consumeStream(response, assistant);
  } catch (error) {
    assistant.item.hidden = false;
    const fixtureMode = new URLSearchParams(location.search).has('fixture');
    const sessionExpired = error.message === 'session_expired';
    assistant.paragraph.textContent = sessionExpired
      ? 'Your anonymous session has expired. Refresh the page to start a new conversation.'
      : fixtureMode
        ? fixtures.degraded.assistant
        : 'Support is temporarily unavailable. Please retry in a moment.';
    addStatePanel(assistant.content, sessionExpired
      ? { kind: 'error', title: 'Session expired', text: 'Refresh the page; the previous anonymous session cannot be resumed.' }
      : fixtureMode
        ? fixtures.degraded.state
        : { kind: 'error', title: 'Request not completed', text: 'The live support service did not respond. Your message was not submitted.', retry: true });
  } finally {
    setBusy(false);
    assistant.item.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }
}

async function consumeStream(response, assistant) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    events.forEach((raw) => applyEvent(parseEvent(raw), assistant));
  }
  buffer += decoder.decode();
  if (buffer.trim()) applyEvent(parseEvent(buffer), assistant);
}

export function parseEvent(raw) {
  const event = { type: 'message', data: null };
  raw.split(/\r?\n/).forEach((line) => {
    if (line.startsWith('event:')) event.type = line.slice(6).trim();
    if (line.startsWith('data:')) {
      const value = line.slice(5).trim();
      try { event.data = JSON.parse(value); } catch { event.type = 'error'; event.data = { message: 'The response stream was invalid.', retryable: true }; }
    }
  });
  // Runtime SSE data is the full event envelope so replay consumers retain
  // request_id and sequence.  Normalize it here for the presentation layer.
  if (event.data && typeof event.data === 'object' && event.data.data && typeof event.data.data === 'object') {
    event.request_id = event.data.request_id;
    event.sequence = event.data.sequence;
    event.data = event.data.data;
  }
  return event;
}

function applyEvent(event, assistant) {
  const data = event.data || {};
  if (event.type === 'status') setBusy(true, safeText(data.state).replaceAll('_', ' ') || 'checking company information');
  if (event.type === 'token') assistant.paragraph.textContent += safeText(data.text);
  if (event.type === 'citation') addCitations(assistant.content, [data]);
  if (event.type === 'complaint.confirmation_required') addStatePanel(assistant.content, { kind: 'warning', title: 'Submit this complaint?', text: `${safeText(data.complaint_text)} · ${safeText(data.complaint_type).replaceAll('_', ' ')}`, draftId: data.draft_id });
  if (event.type === 'complaint.submitted') addStatePanel(assistant.content, { kind: 'success', title: 'Complaint queued', text: 'A manager can now review it.', complaintId: data.complaint_id });
  if (event.type === 'error') addStatePanel(assistant.content, { kind: 'error', title: 'Request not completed', text: data.message || 'Please retry.', retry: data.retryable !== false });
}

async function confirmComplaint(event) {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await request(API.confirm(state.conversationId || 'demo', state.draftId), { method: 'POST', body: '{}' });
    const result = await response.json();
    renderFixture('submitted');
    const id = document.querySelector('.complaint-id');
    if (id && result.complaint_id) id.textContent = result.complaint_id;
  } catch {
    addStatePanel(button.closest('.message-body'), { kind: 'error', title: 'Complaint not submitted', text: 'The confirmed draft was preserved. Retry when the service is available.', retry: true });
  }
}

async function discardComplaint(event) {
  event.currentTarget.disabled = true;
  try { await request(API.discard(state.conversationId || 'demo', state.draftId), { method: 'DELETE' }); } catch { /* presentation remains safe */ }
  renderFixture('catalog');
}

function retryLastMessage() {
  input.value = state.lastMessage;
  input.focus();
}

if (form) {
  form.addEventListener('submit', submitMessage);
  fixtureSelect.addEventListener('change', () => renderFixture(fixtureSelect.value));
  const requestedFixture = new URLSearchParams(location.search).get('fixture');
  if (requestedFixture && fixtures[requestedFixture]) fixtureSelect.value = requestedFixture;
  renderFixture(fixtureSelect.value);
}
