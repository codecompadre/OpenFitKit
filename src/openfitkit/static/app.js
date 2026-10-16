// Keep this client small: the server owns persistence, provider settings, and context.
const $ = (selector) => document.querySelector(selector);
const token = $('meta[name="openfitkit-token"]').content;
let state = null;
let conversation = null;
let busy = false;
let unsaved = false;
const profileDialog = $('#profile-dialog');
const memoryDialog = $('#memory-dialog');

async function api(path, method = 'GET', body) {
  const response = await fetch(`/api${path}`, {
    method, headers: { 'X-OpenFitKit-Token': token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request failed. Please try again.');
  return result;
}

function compatible() {
  return !conversation || (conversation.provider === state?.provider.provider && conversation.model === state?.provider.model);
}

function controls() {
  document.querySelectorAll('button, input, select, textarea').forEach((element) => { element.disabled = busy; });
  const length = $('#message').value.length;
  const limit = state?.context_limits.max_message_chars || 8000;
  ['#new-chat', '#profile-button', '#memory-button'].forEach((selector) => { $(selector).disabled = busy || !state; });
  $('#message').disabled = busy || !state || unsaved || !compatible();
  $('#send').disabled = busy || !state || unsaved || !compatible() || !$('#message').value.trim() || length > limit || !state.provider.configured;
  $('#reset').disabled = busy || $('#reset-confirmation').value !== 'RESET';
  let note = 'Enter to send · Shift+Enter for a new line';
  if (length > limit) note = `Message is too long (${length.toLocaleString()} / ${limit.toLocaleString()} characters). Shorten it to send.`;
  if (!compatible()) note = 'Read-only: this conversation uses a different provider or model. Start a new conversation.';
  if (unsaved) note = 'Read-only: this reply was not saved. Copy any text you need, then start a new conversation or reopen a saved conversation.';
  $('#input-note').textContent = note;
}

function showError(error) {
  const dialog = document.querySelector('dialog[open]');
  (dialog ? dialog.querySelector('.dialog-error') : $('#error')).textContent = error.message || String(error);
}

async function run(action) {
  if (busy) return;
  busy = true;
  $('#error').textContent = '';
  document.querySelectorAll('.dialog-error').forEach((element) => { element.textContent = ''; });
  controls();
  try { await action(); } catch (error) { showError(error); }
  finally { busy = false; controls(); }
}

function renderHistory() {
  $('#history').replaceChildren();
  for (const item of state.conversations) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = item.title;
    button.title = `${item.provider} · ${item.model}`;
    if (conversation?.id === item.id) button.setAttribute('aria-current', 'true');
    button.addEventListener('click', () => run(async () => {
      conversation = (await api(`/conversations/${item.id}`)).conversation;
      unsaved = false;
      $('#message').value = '';
      $('#status').textContent = '';
      renderConversation();
      renderHistory();
    }));
    $('#history').append(button);
  }
  if (!state.conversations.length) $('#history').textContent = 'No saved conversations yet.';
}

function renderConversation() {
  $('#conversation-title').textContent = conversation?.title || 'New conversation';
  $('#welcome').hidden = Boolean(conversation?.messages.length);
  $('#messages').querySelectorAll('.message').forEach((element) => element.remove());
  for (const message of conversation?.messages || []) {
    const block = document.createElement('section');
    block.className = `message ${message.role === 'user' ? 'user' : 'assistant'}`;
    const label = document.createElement('h2');
    label.textContent = message.role === 'user' ? 'You' : 'Fitness guide';
    const text = document.createElement('p');
    text.textContent = message.content;
    block.append(label, text);
    $('#messages').append(block);
  }
  $('#messages').scrollTop = $('#messages').scrollHeight;
  controls();
}

async function loadState() {
  state = await api('/state');
  $('#mode').textContent = state.provider.demo ? 'Demo · simulated replies' : `${state.provider.provider} · ${state.provider.model}`;
  $('#connection-note').textContent = state.provider.demo ? 'Demo mode does not call an AI service. Replies are examples, not personalized coaching.' : state.provider.configured ? 'Live mode · messages and profile are sent to your configured AI provider. Usage may incur charges.' : 'Live mode is not configured. Set the provider API key in the server environment, then restart the app.';
  renderHistory();
  controls();
}

function newChat() {
  conversation = null;
  unsaved = false;
  $('#message').value = '';
  $('#error').textContent = '';
  $('#status').textContent = '';
  renderConversation();
  renderHistory();
  $('#message').focus();
}

$('#new-chat').addEventListener('click', newChat);
$('#message').addEventListener('input', controls);
$('#message').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$('#send').disabled) $('#composer').requestSubmit();
  }
});
document.querySelectorAll('[data-suggestion]').forEach((button) => button.addEventListener('click', () => {
  $('#message').value = button.dataset.suggestion;
  controls();
  $('#message').focus();
}));
$('#composer').addEventListener('submit', (event) => {
  event.preventDefault();
  if ($('#send').disabled) return;
  run(async () => {
    $('#status').textContent = 'Preparing a reply…';
    let result;
    try { result = await api('/chat', 'POST', { conversation_id: conversation?.id || null, message: $('#message').value }); }
    finally { $('#status').textContent = ''; }
    conversation = result.conversation;
    unsaved = result.saved === false;
    $('#message').value = '';
    renderConversation();
    const notices = Array.isArray(result.warnings) ? [...result.warnings] : [];
    if (unsaved) notices.push('This reply is visible but not saved. Select and copy the text before leaving. Start a new conversation or reopen a saved one to continue.');
    else if (result.context.trimmed) notices.push('Earlier messages remain saved. This reply used a recent portion of this conversation and your profile.');
    $('#status').textContent = notices.join(' ');
    await loadState();
  }).then(() => $('#message').focus());
});

$('#profile-button').addEventListener('click', () => {
  for (const [key, value] of Object.entries(state.profile)) {
    const field = $('#profile-form').elements.namedItem(key);
    if (field) field.value = value ?? '';
  }
  profileDialog.querySelector('.dialog-error').textContent = '';
  profileDialog.showModal();
});
$('#profile-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const profile = Object.fromEntries(new FormData(event.target));
  for (const key of ['days_per_week', 'minutes_per_session']) profile[key] = profile[key] === '' ? null : Number(profile[key]);
  run(async () => {
    state.profile = (await api('/profile', 'PUT', profile)).profile;
    profileDialog.close();
    $('#status').textContent = 'Profile saved. It will be used with your next message.';
  });
});
$('#memory-button').addEventListener('click', () => {
  $('#memory-count').textContent = `${state.memory.conversations} saved conversations · ${state.memory.messages} messages`;
  $('#reset-confirmation').value = '';
  memoryDialog.querySelector('.dialog-error').textContent = '';
  memoryDialog.showModal();
  controls();
});
$('#memory-new-chat').addEventListener('click', () => { memoryDialog.close(); newChat(); });
$('#reset-confirmation').addEventListener('input', controls);
$('#memory-form').addEventListener('submit', (event) => {
  event.preventDefault();
  if ($('#reset').disabled) return;
  const scope = new FormData(event.target).get('scope');
  const confirmation = $('#reset-confirmation').value;
  run(async () => {
    await api('/memory/reset', 'POST', { scope, confirmation });
    conversation = null;
    unsaved = false;
    $('#message').value = '';
    renderConversation();
    await loadState();
    memoryDialog.close();
    $('#status').textContent = scope === 'all' ? 'Local conversations and profile cleared.' : 'Local conversations cleared. Your profile is unchanged.';
  });
});
document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach((dialog) => dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); }));
run(loadState);
