const input = document.querySelector('#markdownInput');
const preview = document.querySelector('#previewContent');
const themeSelect = document.querySelector('#themeSelect');
const convertForm = document.querySelector('#convertForm');
const clearButton = document.querySelector('#clearButton');
const wordCount = document.querySelector('#wordCount');
const lineGutter = document.querySelector('#lineGutter');
const toast = document.querySelector('#toast');
const authModal = document.querySelector('#authModal');
const authActionButton = document.querySelector('#authActionButton');
const signOutButton = document.querySelector('#signOutButton');
const accountStatus = document.querySelector('#accountStatus');
const authMessage = document.querySelector('#authMessage');
const authTitle = document.querySelector('#authTitle');
const authIntro = document.querySelector('#authIntro');
const authTabs = document.querySelector('#authTabs');
const cookieBanner = document.querySelector('#cookieBanner');
const cookiePreferencesButton = document.querySelector('#cookiePreferencesButton');
const essentialCookiesButton = document.querySelector('#essentialCookiesButton');
const optionalCookiesButton = document.querySelector('#optionalCookiesButton');
const accessTokenLifetime = 14 * 60 * 1000;
const STORAGE_KEY = 'markdown2pdf.markdown.v1';
const COOKIE_CONSENT_KEY = 'markdown2pdf.cookie-consent.v1';
const COOKIE_POLICY_VERSION = '2026-10-15';

const starter = `# Your next great document

A quiet place for your ideas to take shape. Write in **Markdown** and see your document come together on the right.

## Made for the details

From a quick note to a polished report, everything stays beautifully readable.

- Thoughtful typography
- Tables, code, and callouts
- One-click PDF export

> Good writing is clear thinking made visible.

### A little code

\`\`\`js
const idea = "made tangible";
console.log(idea);
\`\`\`

| Format | Ready |
| :-- | :--: |
| Headings | ✓ |
| Lists | ✓ |
| Tables | ✓ |

---

Choose a theme above, then export when it feels right.`;

let previewTimer;
let toastTimer;
let accessToken = null;
let accessTokenExpiresAt = 0;
let currentUser = null;
let refreshInFlight = null;
let appInitialized = false;
let passwordResetToken = new URLSearchParams(window.location.search).get('reset');

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('visible');
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove('visible'), 3500);
}

function updateAccountControls() {
  const signedIn = Boolean(currentUser);
  accountStatus.hidden = !signedIn;
  accountStatus.textContent = signedIn ? `@${currentUser.username}` : '';
  authActionButton.hidden = signedIn;
  signOutButton.hidden = !signedIn;
}

function showAuthMessage(message, isError = false) {
  authMessage.textContent = message;
  authMessage.classList.toggle('error', isError);
  authMessage.hidden = !message;
}

function setAuthView(view, message = '') {
  const forms = {
    login: document.querySelector('#loginForm'),
    signup: document.querySelector('#signupForm'),
    forgot: document.querySelector('#forgotForm'),
    reset: document.querySelector('#resetForm'),
  };
  for (const [name, form] of Object.entries(forms)) form.hidden = name !== view;
  const isAccountEntry = view === 'login' || view === 'signup';
  authTabs.hidden = !isAccountEntry;
  for (const tab of authTabs.querySelectorAll('[data-auth-view]')) {
    const active = tab.dataset.authView === view;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  }
  authTitle.textContent = {
    login: 'Welcome',
    signup: 'Create free account',
    forgot: 'Reset your password',
    reset: 'Choose a new password',
  }[view];
  authIntro.textContent = {
    login: 'Sign in to export your document as a PDF.',
    signup: 'A free account is all you need to export and download.',
    forgot: 'Enter your account email and we will send a secure reset link.',
    reset: 'Choose a strong new password for your account.',
  }[view];
  showAuthMessage(message);
  const form = forms[view];
  if (form) {
    const firstInput = form.querySelector('input:not([type="checkbox"])');
    window.setTimeout(() => firstInput?.focus(), 80);
  }
}

function openAuthModal(view = 'login', message = '') {
  authModal.hidden = false;
  setAuthView(view, message);
}

function closeAuthModal() {
  authModal.hidden = true;
}

function acceptSession(result) {
  accessToken = result.access_token;
  accessTokenExpiresAt = Date.now() + accessTokenLifetime;
  currentUser = result.user;
  updateAccountControls();
}

async function refreshSession() {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const response = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' });
      if (response.status === 204) {
        accessToken = null;
        accessTokenExpiresAt = 0;
        currentUser = null;
        updateAccountControls();
        return false;
      }
      if (!response.ok) {
        accessToken = null;
        accessTokenExpiresAt = 0;
        currentUser = null;
        updateAccountControls();
        return false;
      }
      acceptSession(await response.json());
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function authenticatedFetch(url, options = {}) {
  if (!accessToken || Date.now() >= accessTokenExpiresAt) {
    if (!await refreshSession()) return null;
  }
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${accessToken}`);
  let response = await fetch(url, { ...options, headers, credentials: 'same-origin' });
  if (response.status === 401 && await refreshSession()) {
    headers.set('Authorization', `Bearer ${accessToken}`);
    response = await fetch(url, { ...options, headers, credentials: 'same-origin' });
  }
  return response;
}

async function responseError(response) {
  try {
    const body = await response.json();
    if (Array.isArray(body.detail)) return body.detail.map((issue) => issue.msg).join(' ');
    return body.detail || body.message || 'Something went wrong. Please try again.';
  } catch {
    return 'Something went wrong. Please try again.';
  }
}

async function handleAccountForm(form, endpoint, buildPayload, onSuccess) {
  const submitButton = form.querySelector('.auth-submit');
  submitButton.disabled = true;
  showAuthMessage('Working securely…');
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload(new FormData(form))),
      credentials: 'same-origin',
    });
    const result = await response.json();
    if (!response.ok) throw new Error(Array.isArray(result.detail)
      ? result.detail.map((issue) => issue.msg).join(' ')
      : result.detail || 'Something went wrong. Please try again.');
    await onSuccess(result);
  } catch (error) {
    showAuthMessage(error.message || 'Could not reach the service. Try again.', true);
  } finally {
    submitButton.disabled = false;
  }
}

function hasCurrentCookieChoice() {
  try {
    const saved = JSON.parse(localStorage.getItem(COOKIE_CONSENT_KEY) || 'null');
    return saved?.version === COOKIE_POLICY_VERSION && saved?.essential === true;
  } catch {
    return false;
  }
}

async function saveCookieChoice(analytics, advertising) {
  const choice = {
    essential: true,
    analytics,
    advertising,
    version: COOKIE_POLICY_VERSION,
    savedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(COOKIE_CONSENT_KEY, JSON.stringify(choice));
  } catch {
    showToast('Your browser could not save this choice. Please allow site storage to continue.', true);
    return;
  }
  cookieBanner.hidden = true;
  cookieBanner.classList.remove('is-initial');
  initializeServiceAfterCookieChoice();
  try {
    const response = await fetch('/api/auth/cookie-consent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ essential: true, analytics, advertising }),
      credentials: 'same-origin',
    });
    if (!response.ok) throw new Error('Preference receipt was not recorded');
  } catch {
    showToast('Your preference is saved in this browser. The consent receipt could not be synchronized.', true);
  }
}

function syncEditorDetails() {
  const source = input.value;
  const words = source.trim() ? source.trim().split(/\s+/u).length : 0;
  wordCount.textContent = `${words} ${words === 1 ? 'word' : 'words'}`;
  lineGutter.textContent = Array.from({ length: Math.max(1, source.split('\n').length) }, (_, index) => index + 1).join('\n');
  if (hasCurrentCookieChoice()) localStorage.setItem(STORAGE_KEY, source);
}

function initializeServiceAfterCookieChoice() {
  if (appInitialized || !hasCurrentCookieChoice()) return;
  appInitialized = true;
  syncEditorDetails();
  loadThemes();
  renderPreview();
  refreshSession();
}

function applyPreviewTheme() {
  preview.dataset.theme = themeSelect.value || 'default';
  preview.parentElement.dataset.theme = themeSelect.value || 'default';
}

async function renderPreview() {
  try {
    const response = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown: input.value }),
    });
    if (!response.ok) throw new Error('Preview unavailable');
    const result = await response.json();
    preview.innerHTML = result.html || '<p class="empty-preview">Your preview will appear here.</p>';
  } catch {
    showToast('Could not update the preview. Check your connection and try again.', true);
  }
}

function schedulePreview() {
  syncEditorDetails();
  window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(renderPreview, 160);
}

async function loadThemes() {
  try {
    const response = await fetch('/api/themes');
    if (!response.ok) return;
    const { themes } = await response.json();
    if (!Array.isArray(themes) || themes.length === 0) return;
    const selected = themeSelect.value;
    const labels = {
      default: 'Paper',
      github: 'GitHub',
      dark: 'Midnight',
      academic: 'Academic',
      minimal: 'Minimal',
      nord: 'Nord',
      solarized: 'Solarized',
      warm: 'Warm',
      dracula: 'Dracula',
      monokai: 'Monokai',
      ocean: 'Ocean',
      forest: 'Forest',
      rose: 'Rose',
      sepia: 'Sepia',
      contrast: 'High Contrast',
      corporate: 'Corporate',
    };
    const availableThemes = new Map(
      [...themeSelect.options].map((option) => [option.value, option.textContent]),
    );
    for (const { id, label } of themes) {
      availableThemes.set(id, labels[id] || label || id.replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()));
    }
    themeSelect.replaceChildren(...[...availableThemes].map(([id, label]) => {
      const option = document.createElement('option');
      option.value = id;
      option.textContent = label;
      return option;
    }));
    const fallback = themes.find((theme) => theme.id === 'default') || themes[0];
    themeSelect.value = themes.some((theme) => theme.id === selected) ? selected : fallback.id;
    applyPreviewTheme();
  } catch {
    // The built-in theme options remain available if theme discovery fails.
  }
}

async function submitConversion(event) {
  event.preventDefault();
  if (!input.value.trim()) {
    showToast('Add some Markdown before exporting.', true);
    input.focus();
    return;
  }
  const button = document.querySelector('#convertButton');
  button.disabled = true;
  button.querySelector('span:last-child').textContent = 'Preparing PDF…';
  try {
    const response = await authenticatedFetch('/convert', {
      method: 'POST',
      body: new FormData(convertForm),
    });
    if (!response) {
      openAuthModal('signup', 'Create an account or sign in to export your PDF.');
      return;
    }
    if (!response.ok) {
      if (response.status === 401) {
        openAuthModal('login', 'Please sign in to export your PDF.');
        return;
      }
      throw new Error(await responseError(response));
    }
    const file = URL.createObjectURL(await response.blob());
    const downloadLink = document.createElement('a');
    downloadLink.href = file;
    downloadLink.download = 'markdown2pdf-document.pdf';
    document.body.append(downloadLink);
    downloadLink.click();
    downloadLink.remove();
    URL.revokeObjectURL(file);
    showToast('Your PDF is ready to download.');
  } catch (error) {
    showToast(error.message || 'Could not export your PDF. Please try again.', true);
  } finally {
    button.disabled = false;
    button.querySelector('span:last-child').textContent = 'Export PDF';
  }
}

input.addEventListener('input', schedulePreview);
input.addEventListener('scroll', () => { lineGutter.scrollTop = input.scrollTop; });
convertForm.addEventListener('submit', submitConversion);
authActionButton.addEventListener('click', () => openAuthModal('login'));
signOutButton.addEventListener('click', async () => {
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  } finally {
    accessToken = null;
    accessTokenExpiresAt = 0;
    currentUser = null;
    updateAccountControls();
    showToast('You have been signed out.');
  }
});
for (const button of authModal.querySelectorAll('[data-auth-view]')) {
  button.addEventListener('click', () => setAuthView(button.dataset.authView));
}
for (const button of authModal.querySelectorAll('[data-auth-close]')) {
  button.addEventListener('click', closeAuthModal);
}
essentialCookiesButton.addEventListener('click', () => saveCookieChoice(false, false));
optionalCookiesButton.addEventListener('click', () => saveCookieChoice(true, true));
cookiePreferencesButton.addEventListener('click', () => {
  cookieBanner.hidden = false;
  cookieBanner.scrollIntoView({ behavior: 'smooth', block: 'end' });
  essentialCookiesButton.focus();
});
document.querySelector('#loginForm').addEventListener('submit', (event) => {
  event.preventDefault();
  handleAccountForm(event.currentTarget, '/api/auth/login', (data) => ({
    username: data.get('username'),
    password: data.get('password'),
  }), async (result) => {
    acceptSession(result);
    closeAuthModal();
    showToast(`Welcome, ${currentUser.first_name}.`);
  });
});
document.querySelector('#signupForm').addEventListener('submit', (event) => {
  event.preventDefault();
  handleAccountForm(event.currentTarget, '/api/auth/signup', (data) => ({
    first_name: data.get('first_name'),
    last_name: data.get('last_name'),
    username: data.get('username'),
    email: data.get('email'),
    password: data.get('password'),
    accept_terms: data.get('accept_terms') === 'on',
    acknowledge_privacy: data.get('accept_terms') === 'on',
    acknowledge_cookies: data.get('accept_terms') === 'on',
  }), async (result) => {
    acceptSession(result);
    closeAuthModal();
    showToast(`Your account is ready, ${currentUser.first_name}.`);
  });
});
document.querySelector('#forgotForm').addEventListener('submit', (event) => {
  event.preventDefault();
  handleAccountForm(event.currentTarget, '/api/auth/forgot-password', (data) => ({
    email: data.get('email'),
  }), async (result) => {
    showAuthMessage(result.message);
    event.currentTarget.reset();
  });
});
document.querySelector('#resetForm').addEventListener('submit', (event) => {
  event.preventDefault();
  handleAccountForm(event.currentTarget, '/api/auth/reset-password', (data) => ({
    token: passwordResetToken,
    password: data.get('password'),
  }), async (result) => {
    passwordResetToken = null;
    window.history.replaceState({}, '', window.location.pathname);
    event.currentTarget.reset();
    setAuthView('login', result.message);
  });
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !authModal.hidden) closeAuthModal();
});
clearButton.addEventListener('click', () => {
  if (!input.value || window.confirm('Clear this document?')) {
    input.value = '';
    schedulePreview();
    input.focus();
  }
});
document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    convertForm.requestSubmit();
  }
});

themeSelect.addEventListener('change', () => {
  localStorage.setItem('markdown2pdf.theme.v1', themeSelect.value);
  applyPreviewTheme();
});

const hasCookieChoice = hasCurrentCookieChoice();
input.value = hasCookieChoice
  ? localStorage.getItem(STORAGE_KEY)
    ?? localStorage.getItem('paperplane.markdown.v1')
    ?? starter
  : starter;
themeSelect.value = hasCookieChoice
  ? localStorage.getItem('markdown2pdf.theme.v1')
    || localStorage.getItem('paperplane.theme.v1')
    || 'default'
  : 'default';
if (![...themeSelect.options].some((option) => option.value === themeSelect.value)) {
  themeSelect.value = 'default';
}
applyPreviewTheme();
updateAccountControls();
if (passwordResetToken) openAuthModal('reset', '');
if (!hasCurrentCookieChoice() || window.location.hash === '#cookie-preferences') {
  cookieBanner.hidden = false;
  if (!hasCurrentCookieChoice()) cookieBanner.classList.add('is-initial');
}
initializeServiceAfterCookieChoice();
