// ── MODE ─────────────────────────────────────────────────
let currentMode = 'class';

function setMode(mode) {
    currentMode = mode;
    document.getElementById('btn-class').classList.toggle('active', mode === 'class');
    document.getElementById('btn-state').classList.toggle('active', mode === 'state');
    document.getElementById('btn-deps').classList.toggle('active', mode === 'deps');
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

        if (data.truncated) {
            status.textContent = 'ok (tronqué — repo trop grand)';
        } else {
            status.textContent = 'ok';
        }
        status.className = 'ok';
        document.getElementById('btn-svg').style.display = 'inline-block';
        document.getElementById('btn-png').style.display = 'inline-block';
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
        document.getElementById('diagram-wrap').style.display = '';

        if (_zipFile) {
            const form = new FormData();
            form.append('file', _zipFile);
            if (currentMode === 'deps') {
                res = await fetch('/analyze-deps-zip', { method: 'POST', body: form });
            } else {
                res = await fetch('/analyze-zip', { method: 'POST', body: form });
            }
        } else if (currentMode === 'state') {
            res = await fetch('/analyze-state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            });
        } else if (currentMode === 'deps') {
            const filename = document.getElementById('file-name').textContent || 'file.cpp';
            res = await fetch('/analyze-deps', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, filename })
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

       if (currentMode === 'deps') {
            window._lastDeps = data.dep_graph;
            renderDepGraph(data.dep_graph);
            document.getElementById('class-count').textContent = 'dépendances';
            status.textContent = 'ok';
            status.className = 'ok';
            document.getElementById('btn-svg').style.display = 'inline-block';
            document.getElementById('btn-png').style.display = 'inline-block';
            document.getElementById('btn-explain').style.display = 'inline-block';
            btnGen.textContent = '▶ Générer';
            return;
        }

        wrap.innerHTML = '';
        const { svg } = await mermaid.render('mermaid-diagram-' + Date.now(), data.mermaid);
        wrap.innerHTML = svg;

        const count = (data.classes || data.states || data.files || []).length;
        document.getElementById('class-count').textContent =
            currentMode === 'state'
                ? count + ' état' + (count > 1 ? 's' : '')
                : currentMode === 'deps'
                ? 'dépendances'
                : count + ' classe' + (count > 1 ? 's' : '');

        status.textContent = 'ok';
        status.className = 'ok';
        document.getElementById('btn-svg').style.display = 'inline-block';
        document.getElementById('btn-png').style.display = 'inline-block';
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

// ── EXPORT SVG, PNG ───────────────────────────────────────────
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

function exportPNG() {
    const wrap = document.getElementById('diagram-wrap');
    const svgEl = wrap.querySelector('svg');
    if (!svgEl) {
        // fallback Mermaid
        htmlToImage.toPng(wrap, { backgroundColor: '#0f1117', pixelRatio: 2 })
            .then(dataUrl => {
                const a = document.createElement('a');
                a.download = 'diagramme.png';
                a.href = dataUrl;
                a.click();
            });
        return;
    }

    // Pour D3 SVG — capture tout le SVG peu importe le scroll
    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(svgEl);
    const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    const img = new Image();
    img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = svgEl.width.baseVal.value * 2;
        canvas.height = svgEl.height.baseVal.value * 2;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#0f1117';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(2, 2);
        ctx.drawImage(img, 0, 0);
        URL.revokeObjectURL(url);
        const a = document.createElement('a');
        a.download = 'diagramme.png';
        a.href = canvas.toDataURL('image/png');
        a.click();
    };
    img.src = url;
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

function renderDepGraph(depGraph) {
    function nodeId(id) {
        return id.replace('.cpp', '').replace('.h', '');
    }

    const wrap = document.getElementById('diagram-wrap');
    wrap.innerHTML = '';
    wrap.style.display = 'block';
    wrap.style.overflowX = 'auto';
    wrap.style.overflowY = 'auto';
    wrap.style.padding = '0';

    // ── Dagre layout ──
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'TB', ranksep: 120, nodesep: 60, marginx: 40, marginy: 40 });
    g.setDefaultEdgeLabel(() => ({}));

    const nodeSet = new Set();
    const links = [];
    for (const [src, targets] of Object.entries(depGraph)) {
        nodeSet.add(src);
        for (const tgt of targets) {
            nodeSet.add(tgt);
            links.push({ source: src, target: tgt });
        }
    }

    const NODE_W = 140;
    const NODE_H = 28;
    const sourceNodes = new Set(Object.keys(depGraph).map(nodeId));
    window._debugSourceNodes = sourceNodes;

    nodeSet.forEach(id => g.setNode(nodeId(id), { width: NODE_W, height: NODE_H, fullName: id }));
    links.forEach(l => {
        const src = nodeId(l.source);
        const tgt = nodeId(l.target);
        if (src !== tgt) g.setEdge(src, tgt);
    });
    dagre.layout(g);

    // Dimensions calculées par dagre
    const gw = g.graph().width + 80;
    const gh = g.graph().height + 80;

    const svg = d3.select(wrap)
        .append('svg')
        .attr('width', gw)
        .attr('height', gh)
        .style('background', 'transparent')
        .style('min-width', gw + 'px');

    // Flèche
    svg.append('defs').append('marker')
        .attr('id', 'arrow')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 10)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#4ade80')
        .attr('stroke', '#4b5563')
        .attr('stroke-width', 1.5)
        .attr('marker-end', 'url(#arrow)');

    // Liens
    svg.selectAll('path.link')
        .data(links.filter(d => g.node(nodeId(d.source)) && g.node(nodeId(d.target))))
        .enter()
        .append('path')
        .attr('d', d => {
            const s = g.node(nodeId(d.source));
            const t = g.node(nodeId(d.target));
            const x1 = s.x, y1 = s.y + NODE_H / 2;
            const x2 = t.x, y2 = t.y - NODE_H / 2;
            const mx = (y1 + y2) / 2;
            return `M${x1},${y1} C${x1},${mx} ${x2},${mx} ${x2},${y2}`;
        })
        .attr('fill', 'none')
        .attr('stroke', '#4ade80')
        .attr('stroke-width', 1)
        .attr('stroke-opacity', '0.4')
        .attr('marker-end', 'url(#arrow)');

    // Noeuds
    const uniqueNodes = [...new Set([...nodeSet].map(nodeId))];

    const nodeGroup = svg.selectAll('g.node')
        .data(uniqueNodes)
        .enter()
        .append('g')
        .attr('transform', d => {
            const n = g.node(d);
            return `translate(${n.x - NODE_W / 2}, ${n.y - NODE_H / 2})`;
        });

    nodeGroup.append('rect')
        .attr('width', NODE_W)
        .attr('height', NODE_H)
        .attr('rx', 4)
        .attr('fill', '#1a1d27')
        .attr('stroke', d => sourceNodes.has(d) ? '#4ade80' : '#60a5fa')
        .attr('stroke-width', 1);

    nodeGroup.append('text')
        .attr('x', NODE_W / 2)
        .attr('y', NODE_H / 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', d => sourceNodes.has(d) ? '#4ade80' : '#60a5fa')
        .attr('font-family', 'JetBrains Mono, monospace')
        .attr('font-size', '11px')
        .text(d => d);
}

// ── RACCOURCI CLAVIER Ctrl+Entrée ────────────────────────
document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') generate();


});