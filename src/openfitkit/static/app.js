// The server owns persistence, provider settings and context. No keys enter this client.
const $ = (selector) => document.querySelector(selector);
const token = $('meta[name="openfitkit-token"]').content;
const focuses = {
  general: ['Your fitness goal', ''],
  movement: ['Move more', 'Help me find a manageable way to add more movement to my day.'],
  strength: ['Build strength', 'Help me start a manageable strength routine with the equipment I have.'],
  fueling: ['Fuel your day', 'Help me choose a practical food or hydration habit that supports my activity.'],
  recovery: ['Recover well', 'Help me plan a manageable recovery or mobility routine.'],
  habits: ['Build consistency', 'Help me choose one small fitness habit I can stick with this week.'],
};
let state = null;
let conversation = null;
let focus = 'general';
let suggestedDraft = '';
let busy = false;
let unsaved = false;

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

function requestMessage() {
  const minutes = $('#available-time').value;
  return $('#message').value + (minutes ? `\n\nTime available today: ${minutes} minutes.` : '');
}

function controls() {
  document.querySelectorAll('button, input, select, textarea').forEach((element) => { element.disabled = busy || !state; });
  document.querySelectorAll('[data-close]').forEach((button) => { button.disabled = busy; });
  const length = requestMessage().length;
  const limit = state?.context_limits.max_message_chars || 8000;
  const readonly = !state || unsaved || !compatible();
  ['#new-chat', '#profile-button', '#summary-profile-button', '#history-button', '#memory-button'].forEach((selector) => { $(selector).disabled = busy || !state; });
  $('#message').disabled = busy || readonly;
  $('#available-time').disabled = busy || readonly;
  document.querySelectorAll('[data-focus]').forEach((button) => { button.disabled = busy || readonly; });
  $('#send').disabled = busy || readonly || !$('#message').value.trim() || length > limit || !state?.provider.configured;
  $('#reset').disabled = busy || !state || $('#reset-confirmation').value !== 'RESET';
  let note = 'Enter to send · Shift+Enter for a new line';
  if (length > limit) note = `Too long (${length.toLocaleString()} / ${limit.toLocaleString()} characters). Shorten your request to send.`;
  if (state && !compatible()) note = 'Read-only: this conversation uses a different provider or model. Start fresh to continue.';
  if (unsaved) note = 'Read-only: saving could not be confirmed. Copy this guidance, then start fresh or reopen saved guidance.';
  $('#input-note').textContent = note;
  $('.guidance-panel').setAttribute('aria-busy', String(busy));
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

function chooseFocus(value, fillDraft = false) {
  focus = value;
  $('#focus-label').textContent = focuses[focus][0];
  document.querySelectorAll('[data-focus]').forEach((button) => { button.setAttribute('aria-pressed', String(button.dataset.focus === focus)); });
  if (fillDraft && (!$('#message').value.trim() || $('#message').value === suggestedDraft)) {
    suggestedDraft = focuses[focus][1];
    $('#message').value = suggestedDraft;
  }
  controls();
}

function renderProfile() {
  const profile = state.profile;
  const details = [];
  if (profile.goals.trim()) details.push(profile.goals.trim());
  if (profile.days_per_week) details.push(`${profile.days_per_week} days per week${profile.minutes_per_session ? ` · ${profile.minutes_per_session} minutes per session` : ''}`);
  else if (profile.minutes_per_session) details.push(`${profile.minutes_per_session} minutes per session`);
  $('#profile-summary').textContent = details.join('\n') || 'Add your goals, available time and equipment to help shape your guidance.';
  $('#summary-profile-button').textContent = details.length ? 'Adjust your profile →' : 'Personalize your profile →';
}

function renderHistory() {
  $('#history').replaceChildren();
  for (const item of state.conversations) {
    const button = document.createElement('button');
    button.type = 'button';
    const title = document.createElement('span');
    title.textContent = item.title;
    const date = document.createElement('small');
    const updated = new Date(item.updated_at || item.created_at);
    date.textContent = Number.isNaN(updated.getTime()) ? 'Saved guidance' : updated.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    button.append(title, date);
    if (conversation?.id === item.id) button.setAttribute('aria-current', 'true');
    button.addEventListener('click', () => run(async () => {
      conversation = (await api(`/conversations/${item.id}`)).conversation;
      unsaved = false;
      $('#message').value = '';
      $('#available-time').value = '';
      $('#status').textContent = '';
      chooseFocus('general');
      renderConversation();
      renderHistory();
      $('#history-dialog').close();
    }));
    $('#history').append(button);
  }
  if (!state.conversations.length) $('#history').textContent = 'Your guidance will be saved here after your first request.';
}

function messageBlock(message) {
  const block = document.createElement('section');
  block.className = `message ${message.role === 'user' ? 'user' : 'assistant'}`;
  const label = document.createElement('h3');
  label.textContent = message.role === 'user' ? 'Your brief' : 'Fitness guidance';
  const text = document.createElement('p');
  text.textContent = message.content;
  block.append(label, text);
  return block;
}

function renderConversation() {
  const messages = conversation?.messages || [];
  $('#conversation-title').textContent = conversation?.title || 'A practical place to begin';
  $('#welcome').hidden = Boolean(messages.length);
  $('#messages').querySelectorAll('.message').forEach((element) => element.remove());
  $('#earlier-messages').replaceChildren();
  messages.slice(-2).forEach((message) => $('#messages').append(messageBlock(message)));
  messages.slice(0, -2).forEach((message) => $('#earlier-messages').append(messageBlock(message)));
  $('#previous-guidance').hidden = messages.length <= 2;
  $('#previous-guidance').open = false;
  $('#brief-title').textContent = messages.length ? 'Refine your next step' : 'Plan a small next step';
  $('#brief-help').textContent = messages.length ? 'Ask a follow-up, share what worked, or adjust the guidance to fit your day.' : 'Share what you want to work on. Include anything that would make it easier to get started.';
  $('#message-label').textContent = messages.length ? 'What would you like to adjust?' : 'What would you like help with?';
  $('#message').placeholder = messages.length ? 'Could we make this shorter or adapt it to my equipment?' : "I'd like to feel stronger, but I'm not sure where to start…";
  $('#send').firstChild.textContent = messages.length ? 'Refine guidance ' : 'Get guidance ';
  controls();
}

async function loadState() {
  try { state = await api('/state'); }
  catch (error) {
    state = null;
    $('#mode').textContent = 'Setup unavailable';
    $('#connection-note').textContent = 'Unable to refresh your local setup. Reload the page before continuing. Any visible guidance can still be copied.';
    throw error;
  }
  $('#mode').textContent = state.provider.demo ? 'Demo · simulated guidance' : state.provider.provider === 'openrouter' ? 'Fitness guidance · OpenRouter' : 'Fitness guidance · custom provider';
  $('#connection-note').textContent = state.provider.demo ? 'Offline demo: replies are fixed examples, not personalized guidance. No AI service is called.' : state.provider.configured ? 'Live guidance sends your request, profile and recent conversation to your configured provider. Usage may incur charges.' : 'Live guidance is not configured. Add OPENROUTER_API_KEY in the server environment, then restart the app.';
  renderProfile();
  renderHistory();
  controls();
}

function newChat() {
  conversation = null;
  unsaved = false;
  suggestedDraft = '';
  $('#message').value = '';
  $('#available-time').value = '';
  $('#error').textContent = '';
  $('#status').textContent = 'A fresh start uses your current profile. Previous guidance remains saved.';
  chooseFocus('general');
  renderConversation();
  renderHistory();
  $('#message').focus();
}

$('#new-chat').addEventListener('click', newChat);
$('#message').addEventListener('input', controls);
$('#available-time').addEventListener('change', controls);
$('#message').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$('#send').disabled) $('#composer').requestSubmit();
  }
});
document.querySelectorAll('[data-focus]').forEach((button) => button.addEventListener('click', () => {
  chooseFocus(button.dataset.focus, true);
  $('#message').focus();
}));
$('#composer').addEventListener('submit', (event) => {
  event.preventDefault();
  if ($('#send').disabled) return;
  let generated = false;
  run(async () => {
    $('#status').textContent = 'Finding a practical next step…';
    let result;
    try { result = await api('/chat', 'POST', { conversation_id: conversation?.id || null, message: requestMessage(), focus }); }
    finally { $('#status').textContent = ''; }
    conversation = result.conversation;
    const notices = Array.isArray(result.warnings) ? [...result.warnings] : [];
    unsaved = result.saved === false || notices.length > 0;
    $('#message').value = '';
    renderConversation();
    generated = true;
    if (unsaved) notices.push('Copy the guidance before leaving. Start fresh or reopen a saved conversation to continue.');
    else if (result.context?.trimmed) notices.push('Earlier steps remain saved. This reply used your profile and a recent portion of this conversation.');
    $('#status').textContent = notices.join(' ');
    await loadState();
  }).then(() => {
    if (generated && window.matchMedia('(max-width: 620px)').matches) $('.guidance-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    else if (!$('#message').disabled) $('#message').focus();
  });
});

function openProfile() {
  for (const [key, value] of Object.entries(state.profile)) {
    const field = $('#profile-form').elements.namedItem(key);
    if (field) field.value = value ?? '';
  }
  $('#profile-dialog .dialog-error').textContent = '';
  $('#profile-dialog').showModal();
}
$('#profile-button').addEventListener('click', openProfile);
$('#summary-profile-button').addEventListener('click', openProfile);
$('#history-button').addEventListener('click', () => $('#history-dialog').showModal());
$('#profile-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const profile = Object.fromEntries(new FormData(event.target));
  for (const key of ['days_per_week', 'minutes_per_session']) profile[key] = profile[key] === '' ? null : Number(profile[key]);
  run(async () => {
    state.profile = (await api('/profile', 'PUT', profile)).profile;
    renderProfile();
    $('#profile-dialog').close();
    $('#status').textContent = 'Profile saved. Your next request will use these details.';
  });
});
$('#memory-button').addEventListener('click', () => {
  $('#memory-count').textContent = `${state.memory.conversations} saved conversations · ${state.memory.messages} messages`;
  $('#provider-detail').textContent = state.provider.demo ? 'Connection: offline demo. No API key is needed.' : `Connection: ${state.provider.provider} · ${state.provider.model}. API key ${state.provider.configured ? 'configured' : 'not configured'} on the server.`;
  $('#reset-confirmation').value = '';
  $('#memory-dialog .dialog-error').textContent = '';
  $('#memory-dialog').showModal();
  controls();
});
$('#memory-new-chat').addEventListener('click', () => { $('#memory-dialog').close(); newChat(); });
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
    suggestedDraft = '';
    $('#message').value = '';
    $('#available-time').value = '';
    chooseFocus('general');
    renderConversation();
    await loadState();
    $('#memory-dialog').close();
    $('#status').textContent = scope === 'all' ? 'Local guidance and profile cleared. You can choose a new starting point.' : 'Local guidance cleared. Your profile is unchanged.';
  });
});
document.querySelectorAll('[data-close]').forEach((button) => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach((dialog) => dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); }));
run(loadState);
