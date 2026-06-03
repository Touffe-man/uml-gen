// ── MODE ─────────────────────────────────────────────────
let currentMode = 'class';

function setMode(mode) {
    currentMode = mode;
    document.getElementById('btn-class').classList.toggle('active', mode === 'class');
    document.getElementById('btn-state').classList.toggle('active', mode === 'state');
}

// ── MERMAID ──────────────────────────────────────────────
mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
        background: '#0f1117',
        primaryColor: '#1a1d27',
        primaryTextColor: '#e2e8f0',
        primaryBorderColor: '#4ade80',
        lineColor: '#6b7280',
        secondaryColor: '#12141f',
        tertiaryColor: '#1e2130',
    }
});

// ── CODEMIRROR ───────────────────────────────────────────
const editor = CodeMirror.fromTextArea(document.getElementById('code-area'), {
    mode: 'text/x-c++src',
    theme: 'dracula',
    lineNumbers: true,
    gutters: ["CodeMirror-linenumbers"],
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    autoCloseBrackets: true,
    matchBrackets: true,
    lineWrapping: false,
});

// ── UPLOAD FICHIER ───────────────────────────────────────
let _zipFile = null;

function loadFile() {
    const file = document.getElementById('file-input').files[0];
    if (!file) return;
    document.getElementById('file-name').textContent = file.name;

    if (file.name.endsWith('.zip')) {
        _zipFile = file;
        editor.setValue('// Projet ZIP chargé : ' + file.name + '\n// Lance la génération pour analyser tous les fichiers .cpp/.h');
    } else {
        _zipFile = null;
        const reader = new FileReader();
        reader.onload = e => editor.setValue(e.target.result);
        reader.readAsText(file);
    }
}

// ── GITHUB ───────────────────────────────────────────────
async function analyzeGithub() {
    const url = document.getElementById('github-url').value.trim();
    const status = document.getElementById('status');
    const wrap = document.getElementById('diagram-wrap');
    const btn = document.getElementById('btn-github');

    if (!url) {
        status.textContent = 'URL manquante';
        status.className = 'err';
        return;
    }

    status.textContent = 'téléchargement...';
    status.className = '';
    btn.textContent = '⏳ ...';

    try {
        const res = await fetch('/analyze-github', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await res.json();

        if (data.error) {
            status.textContent = data.error;
            status.className = 'err';
            return;
        }

        wrap.innerHTML = '';
        const { svg } = await mermaid.render('mermaid-diagram-' + Date.now(), data.mermaid);
        wrap.innerHTML = svg;

        const count = (data.classes || []).length;
        document.getElementById('class-count').textContent =
            count + ' classe' + (count > 1 ? 's' : '') +
            ' · ' + data.files_analyzed + ' fichier' + (data.files_analyzed > 1 ? 's' : '');

        status.textContent = 'ok';
        status.className = 'ok';
        document.getElementById('btn-svg').style.display = 'inline-block';
        document.getElementById('btn-explain').style.display = 'inline-block';
        window._lastMermaid = data.mermaid;
        window._lastReadme = data.readme || "";

    } catch (e) {
        status.textContent = 'erreur : ' + e.message;
        status.className = 'err';
    } finally {
        btn.textContent = '↓ Analyser';
    }
}

// ── GÉNÉRER ──────────────────────────────────────────────
async function generate() {
    const code = editor.getValue().trim();
    const status = document.getElementById('status');
    const wrap = document.getElementById('diagram-wrap');
    const btnGen = document.getElementById('btn-gen');

    if (!code) {
        status.textContent = 'aucun code';
        status.className = 'err';
        return;
    }

    status.textContent = 'analyse...';
    status.className = '';
    btnGen.textContent = '⏳ ...';

    try {
        let res;

        if (_zipFile) {
            const form = new FormData();
            form.append('file', _zipFile);
            res = await fetch('/analyze-zip', { method: 'POST', body: form });
        } else if (currentMode === 'state') {
            res = await fetch('/analyze-state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            });
        } else {
            res = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            });
        }

        const data = await res.json();

        if (data.error) {
            status.textContent = data.error;
            status.className = 'err';
            return;
        }

        wrap.innerHTML = '';
        const { svg } = await mermaid.render('mermaid-diagram-' + Date.now(), data.mermaid);
        wrap.innerHTML = svg;

        const count = (data.classes || data.states || []).length;
        document.getElementById('class-count').textContent =
            currentMode === 'state'
                ? count + ' état' + (count > 1 ? 's' : '')
                : count + ' classe' + (count > 1 ? 's' : '');

        status.textContent = 'ok';
        status.className = 'ok';
        document.getElementById('btn-svg').style.display = 'inline-block';
        document.getElementById('btn-explain').style.display = 'inline-block';
        window._lastMermaid = data.mermaid;
        window._lastReadme = data.readme || "";
        
    } catch (e) {
        status.textContent = 'erreur : ' + e.message;
        status.className = 'err';
    } finally {
        btnGen.textContent = '▶ Générer';
    }
}

// ── EXPORT SVG ───────────────────────────────────────────
function exportSVG() {
    const svg = document.querySelector('#diagram-wrap svg');
    if (!svg) return;
    const box = svg.getBoundingClientRect();
    svg.setAttribute('width', box.width);
    svg.setAttribute('height', box.height);
    const blob = new Blob([new XMLSerializer().serializeToString(svg)],
        { type: 'image/svg+xml;charset=utf-8' });
    const a = document.createElement('a');
    a.download = 'diagramme.svg';
    a.href = URL.createObjectURL(blob);
    a.click();
    URL.revokeObjectURL(a.href);
}

// ── EXPLIQUER ────────────────────────────────────────────
async function explain() {
    const btn = document.getElementById('btn-explain');
    const panel = document.getElementById('explain-panel');
    const content = document.getElementById('explain-content');

    if (!window._lastMermaid) return;

    btn.textContent = '⏳ ...';
    panel.style.display = 'block';
    content.innerHTML = '<span class="explain-loading">analyse en cours...</span>';

    try {
        const res = await fetch('/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mermaid: window._lastMermaid, readme: window._lastReadme || "" })
        });
        const data = await res.json();
        if (data.error) {
            content.innerHTML = `<span class="explain-error">${data.error}</span>`;
        } else {
            content.innerHTML = marked.parse(data.explanation);
        }
    } catch (e) {
        content.innerHTML = `<span class="explain-error">Erreur : ${e.message}</span>`;
    } finally {
        btn.textContent = '✦ Expliquer';
    }
}

function toggleExplain() {
    const content = document.getElementById('explain-content');
    const btn = document.getElementById('btn-collapse');
    const visible = content.style.display !== 'none';
    content.style.display = visible ? 'none' : 'block';
    btn.textContent = visible ? '↑' : '↓';
}

// ── RACCOURCI CLAVIER Ctrl+Entrée ────────────────────────
document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') generate();


});