const input = document.querySelector('#markdownInput');
const preview = document.querySelector('#previewContent');
const themeSelect = document.querySelector('#themeSelect');
const convertButton = document.querySelector('#convertButton');
const clearButton = document.querySelector('#clearButton');
const wordCount = document.querySelector('#wordCount');
const lineGutter = document.querySelector('#lineGutter');
const toast = document.querySelector('#toast');
const STORAGE_KEY = 'markdown2pdf.markdown.v1';

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

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('visible');
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove('visible'), 3500);
}

function syncEditorDetails() {
  const source = input.value;
  const words = source.trim() ? source.trim().split(/\s+/u).length : 0;
  wordCount.textContent = `${words} ${words === 1 ? 'word' : 'words'}`;
  lineGutter.textContent = Array.from({ length: Math.max(1, source.split('\n').length) }, (_, index) => index + 1).join('\n');
  localStorage.setItem(STORAGE_KEY, source);
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

async function exportPdf() {
  if (!input.value.trim()) {
    showToast('Add some Markdown before exporting.', true);
    input.focus();
    return;
  }

  convertButton.disabled = true;
  convertButton.lastElementChild.textContent = 'Preparing…';
  try {
    const response = await fetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markdown: input.value, theme: themeSelect.value }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'PDF export failed. Please try again.');
    }
    const pdf = await response.blob();
    const url = URL.createObjectURL(pdf);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'markdown2pdf-document.pdf';
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast('Your PDF is ready — happy sharing!');
  } catch (error) {
    showToast(error.message || 'PDF export failed. Please try again.', true);
  } finally {
    convertButton.disabled = false;
    convertButton.lastElementChild.textContent = 'Export PDF';
  }
}

input.addEventListener('input', schedulePreview);
input.addEventListener('scroll', () => { lineGutter.scrollTop = input.scrollTop; });
convertButton.addEventListener('click', exportPdf);
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
    exportPdf();
  }
});

themeSelect.addEventListener('change', () => {
  localStorage.setItem('markdown2pdf.theme.v1', themeSelect.value);
  applyPreviewTheme();
});

input.value = localStorage.getItem(STORAGE_KEY)
  ?? localStorage.getItem('paperplane.markdown.v1')
  ?? starter;
themeSelect.value = localStorage.getItem('markdown2pdf.theme.v1')
  || localStorage.getItem('paperplane.theme.v1')
  || 'default';
if (![...themeSelect.options].some((option) => option.value === themeSelect.value)) {
  themeSelect.value = 'default';
}
applyPreviewTheme();
syncEditorDetails();
loadThemes();
renderPreview();
