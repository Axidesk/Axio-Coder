import { findExplorerRow, loadTrash, openFileInEditor, pinPreview, updateExplorerToolbar } from './editor.js';
import { appendLine, basename, enterDir, updateExplorerPath } from './terminal.js';
import { applyTabsVisibility, layoutAllEditors } from './workspace.js';
import { atualizarSugestoes } from './terminal_cards.js';
import { state } from './state.js';
import { abreNoViewer } from './familia_ficheiro.js';

const VALIDADE_DA_LISTA_MS = 6000;
const MAX_PASTAS_LISTADAS = 24;
const INTENCAO_DE_HOVER_MS = 90;
const listasDePastas = new Map();
const listasEmVoo = new Map();
let prefetchTimer = null;
let prefetchAgendado = null;

function listaGuardada(chave) {
    const guardada = listasDePastas.get(chave);
    if (!guardada) return null;
    if (Date.now() - guardada.ts > VALIDADE_DA_LISTA_MS) {
        listasDePastas.delete(chave);
        return null;
    }
    listasDePastas.delete(chave);
    listasDePastas.set(chave, guardada);
    return guardada.dados;
}

function guardarLista(chave, dados) {
    listasDePastas.delete(chave);
    listasDePastas.set(chave, { dados: dados, ts: Date.now() });
    while (listasDePastas.size > MAX_PASTAS_LISTADAS) {
        listasDePastas.delete(listasDePastas.keys().next().value);
    }
}

function pedirLista(chave) {
    const pedido = fetch(state.API + '/api/explorer?path=' + encodeURIComponent(chave))
        .then(r => r.json())
        .then(data => {
            if (!data.sem_raiz && !data.error) guardarLista(chave, data);
            return data;
        });
    listasEmVoo.set(chave, pedido);
    const largar = () => listasEmVoo.delete(chave);
    pedido.then(largar, largar);
    return pedido;
}

export function animateViewTransition(viewName, previousView, targetView, viewport, inClass, outClass, duration) {
    if (state.viewTimers[viewName]) {
        clearTimeout(state.viewTimers[viewName]);
        state.viewTimers[viewName] = null;
    }

    if (previousView === viewName && targetView !== viewName) {
        viewport.classList.remove(inClass);
        viewport.classList.add(outClass);
        state.viewTimers[viewName] = setTimeout(() => {
            viewport.classList.add('hidden');
            viewport.classList.remove('flex');
            viewport.classList.remove(outClass);
            state.viewTimers[viewName] = null;
        }, duration);
    } else {
        viewport.classList.toggle('hidden', targetView !== viewName);
        if (targetView === viewName) {
            viewport.classList.add('flex');
            viewport.classList.remove(outClass);
            viewport.classList.remove(inClass);
            void viewport.offsetWidth;
            viewport.classList.add(inClass);
        } else {
            viewport.classList.remove('flex');
        }
    }
}
export const VISTAS_DE_TRABALHO = ['editor', 'preview'];

export function setView(name) {
    const previousView = state.currentView;
    if (previousView === name) return;
    if (VISTAS_DE_TRABALHO.includes(name)) state.vistaDeTrabalho = name;
    aplicarVista(name, previousView);
}

export function alternarDoc() {
    setView(state.currentView === 'chat' ? state.vistaDeTrabalho : 'chat');
}

export function fecharPreview() {
    setView('editor');
}

function aplicarVista(name, previousView) {
    if (!name || name === state.currentView) return;
    state.currentView = name;

    if (name === 'editor') {
        if (window.axioUnfadeFindWidget) window.axioUnfadeFindWidget();
    } else {
        if (window.axioFadeFindWidget) window.axioFadeFindWidget();
    }

    animateViewTransition('preview', previousView, name, state.previewView, 'preview-fade-in', 'preview-fade-out', 200);

    animateViewTransition('chat', previousView, name, state.chatView, 'chat-fade-in', 'chat-fade-out', 200);

    animateViewTransition('editor', previousView, name, state.editorView, 'editor-slide-up', 'editor-slide-down', 300);

    const blue = 'text-[var(--azul-acao)]';
    const gray = 'text-[var(--text-suave)]';
    if (state.btnEditor) {
        state.btnEditor.classList.toggle('sidebar-active', VISTAS_DE_TRABALHO.includes(name));
    }
    if (state.btnPreview) {
        state.btnPreview.classList.remove(blue, 'text-[var(--text-branco)]', gray);
        state.btnPreview.classList.add(name === 'preview' ? blue : gray);
    }

    applyTabsVisibility();

    if (name === 'editor') layoutAllEditors();

    window.dispatchEvent(new CustomEvent('axio-view-change', { detail: { view: name, anterior: previousView } }));
}

export function loadExplorerOnce() {
    if (!state.explorerLoaded) {
        state.explorerLoaded = true;
        state.explorerReadyPromise = loadExplorer();
        loadTrash();
    }
}
export function reloadExplorer() {
    state.explorerLoaded = true;
    listasDePastas.clear();
    return loadExplorer();
}
export function prefetchPasta(chave) {
    if (chave === undefined || chave === null) return;
    if (listaGuardada(chave) || listasEmVoo.has(chave)) return;
    pedirLista(chave).catch(() => {});
}
export function ligarPrefetchDePastas() {
    const arvore = state.explorerTree;
    if (!arvore || arvore.dataset.prefetch === '1') return;
    arvore.dataset.prefetch = '1';
    arvore.addEventListener('mouseover', (e) => {
        const row = e.target && e.target.closest ? e.target.closest('.explorer-row') : null;
        if (row && row.dataset.tipo === 'dir') agendarPrefetch(row.dataset.path);
        else cancelarPrefetch();
    });
    arvore.addEventListener('mouseleave', cancelarPrefetch);
}
function agendarPrefetch(chave) {
    if (prefetchTimer && prefetchAgendado === chave) return;
    cancelarPrefetch();
    prefetchAgendado = chave;
    prefetchTimer = setTimeout(() => {
        prefetchTimer = null;
        prefetchPasta(chave);
    }, INTENCAO_DE_HOVER_MS);
}
function cancelarPrefetch() {
    if (!prefetchTimer) return;
    clearTimeout(prefetchTimer);
    prefetchTimer = null;
    prefetchAgendado = null;
}
export async function loadExplorer(path) {
    const queryPath = path !== undefined ? path : (state.currentCwdRel || '');
    const guardada = listaGuardada(queryPath);
    if (guardada) {
        renderExplorer(guardada);
        return;
    }
    state.wsStatus.textContent = 'explorador: carregando...';
    try {
        const data = await pedirLista(queryPath);
        if (data.sem_raiz) {
            renderEmptyExplorer();
            return;
        }
        if (data.error) {
            appendLine('[explorer] ' + data.error, 'term-err');
            state.wsStatus.textContent = 'explorador: erro';
            return;
        }
        renderExplorer(data);
    } catch (e) {
        appendLine('[explorer] erro: ' + e.message, 'term-err');
        state.wsStatus.textContent = 'explorador: erro';
    }
}
export function renderExplorer(data) {
    state.rootPath = data.root || '';
    state.currentCwd = data.cwd || '';
    state.currentCwdRel = data.path || '';
    state.wsStatus.textContent = 'explorador: ' + (basename(data.root) || 'raiz');
    updateExplorerPath(data);

    const caminho = data.path || '';
    const trocouPasta = state.explorerRenderPath !== caminho;
    state.explorerRenderPath = caminho;

    let ul = state.explorerTree.querySelector(':scope > ul');
    if (trocouPasta || !ul) {
        state.explorerTree.innerHTML = '';
        ul = document.createElement('ul');
        state.explorerTree.appendChild(ul);
    }

    const anteriores = new Map();
    Array.from(ul.children).forEach(li => {
        const row = li.querySelector('.explorer-row');
        if (row) anteriores.set(row.dataset.path, li);
    });

    const novos = [];
    data.entries.forEach(entry => {
        const existente = anteriores.get(entry.path);
        if (existente) {
            anteriores.delete(entry.path);
            existente.classList.add('explorer-item-estatico');
            ul.appendChild(existente);
        } else {
            const li = renderEntry(entry);
            ul.appendChild(li);
            novos.push(li);
        }
    });
    anteriores.forEach(li => li.remove());

    if (trocouPasta) staggerExplorerItems(ul);
    else staggerExplorerItems(novos);

    highlightSelection();
    applyErrorMarkers();
    atualizarSugestoes(caminho);
}
export function renderEmptyExplorer() {
    state.explorerTree.innerHTML = '';
    state.explorerRenderPath = null;
    if (state.explorerPath) state.explorerPath.textContent = 'nenhuma pasta selecionada';
    state.wsStatus.textContent = 'explorador: nenhuma pasta selecionada';
}
export function renderEntry(entry) {
    const li = document.createElement('li');
    li.className = 'explorer-item';
    const row = document.createElement('div');
    row.className = 'explorer-row';
    row.title = entry.path;
    row.dataset.path = entry.path;
    row.dataset.tipo = entry.tipo;
    if (entry.tipo === 'grupo') {
        return renderGrupo(entry, li, row);
    }
    if (entry.tipo === 'dir') {
        row.innerHTML = state.ICON_FOLDER + '<span>' + entry.nome + '</span>';
        row.classList.add('explorer-dir');
        li.appendChild(row);
        const childContainer = document.createElement('div');
        childContainer.className = 'explorer-children hidden';
        li.appendChild(childContainer);
        row.addEventListener('click', () => {
            selectEntry(entry.path, 'dir');
            enterDir(entry.path);
        });
    } else {
        row.innerHTML = state.ICON_FILE + '<span>' + entry.nome + '</span>';
        row.classList.add('explorer-file');
        row.addEventListener('click', () => openFile(entry.path, row));
        row.addEventListener('dblclick', () => {
            selectEntry(entry.path, 'file');
            pinPreview(entry.path);
        });
        li.appendChild(row);
    }
    return li;
}
function iconeDoNivel(nivel) {
    return nivel === 'pasta' ? state.ICON_FOLDER : state.ICON_GRUPO;
}
function renderGrupo(entry, li, row) {
    const nivel = entry.nivel || 'grupo';
    row.innerHTML = iconeDoNivel(nivel) + '<span>' + entry.nome + '</span>';
    row.classList.add('explorer-dir', 'explorer-grupo', 'explorer-' + nivel);
    row.title = entry.detalhe ? entry.nome + ' - ' + entry.detalhe : entry.nome;
    li.appendChild(row);
    const childContainer = document.createElement('div');
    childContainer.className = 'explorer-children hidden';
    li.appendChild(childContainer);
    row.addEventListener('click', () => alternarGrupo(entry.path, row, childContainer));
    return li;
}

function alternarGrupo(path, row, container) {
    if (row.classList.contains('explorer-aberto')) {
        row.classList.remove('explorer-aberto');
        container.classList.add('hidden');
        return;
    }
    row.classList.add('explorer-aberto');
    if (container.dataset.loaded === '1') {
        container.classList.remove('hidden');
        return;
    }
    loadDirChildren(path, container);
}

export function staggerExplorerItems(container) {
    const items = typeof container.querySelectorAll === 'function'
        ? container.querySelectorAll('.explorer-item')
        : container;
    const step = 0.006;
    const max = 0.12;
    for (let i = 0; i < items.length; i++) {
        items[i].style.animationDelay = Math.min(i * step, max) + 's';
    }
}
export async function loadDirChildren(path, container) {
    container.innerHTML = '<div class="explorer-loading">carregando...</div>';
    container.classList.remove('hidden');
    try {
        const resp = await fetch(state.API + '/api/explorer?path=' + encodeURIComponent(path));
        const data = await resp.json();
        if (data.sem_raiz) {
            container.innerHTML = '';
            return false;
        }
        if (data.error) {
            container.innerHTML = '<div class="explorer-loading term-err">' + data.error + '</div>';
            return false;
        }
        container.innerHTML = '';
        const ul = document.createElement('ul');
        data.entries.forEach(e => ul.appendChild(renderEntry(e)));
        container.appendChild(ul);
        staggerExplorerItems(ul);
        container.dataset.loaded = '1';
        highlightSelection();
        applyErrorMarkers();
        return true;
    } catch (e) {
        container.innerHTML = '<div class="explorer-loading term-err">' + e.message + '</div>';
        return false;
    }
}
export function openFile(path, row) {
    if (!row) row = findExplorerRow(path);
    selectEntry(path, 'file');
    if (abreNoViewer(path) || /\.html?$/i.test(path)) {
        pinPreview(path);
        window.dispatchEvent(new CustomEvent('axio-preview-open', { detail: { path: path } }));
        abrirCodigoDoPreview(path);
        return;
    }
    if (!state.monaco) {
        state.pendingFile = path;
        state.pendingLogMode = false;
        state.pendingSnippet = null;
        setView('editor');
        state.wsStatus.textContent = 'editor: carregando...';
        anunciarArquivoAberto(path);
        return;
    }
    openFileInEditor(path, { preview: true }).then(() => anunciarArquivoAberto(path));
}
function anunciarArquivoAberto(path) {
    window.dispatchEvent(new CustomEvent('axio-editor-file-open', { detail: { path: path } }));
}
function abrirCodigoDoPreview(path) {
    openFileInEditor(path, { preview: true, manterVista: true }).then(() => anunciarArquivoAberto(path));
}
export function selectEntry(path, tipo) {
    state.selectedPath = path;
    state.selectedEntryType = tipo || 'file';
    state.trashSelectedId = null;
    state.trashSelectedName = null;
    document.querySelectorAll('.trash-item').forEach(el => el.classList.remove('trash-item-selected'));
    highlightSelection();
    updateExplorerToolbar();
}
export function highlightSelection() {
    document.querySelectorAll('.explorer-file').forEach(r => r.classList.remove('explorer-selected'));
    document.querySelectorAll('.explorer-dir').forEach(r => r.classList.remove('explorer-dir-selected'));
    if (!state.selectedPath) return;
    const row = findExplorerRow(state.selectedPath);
    if (!row) return;
    if (state.selectedEntryType === 'dir') {
        row.classList.add('explorer-dir-selected');
    } else {
        row.classList.add('explorer-selected');
    }
}
export function deselectEntry() {
    state.selectedPath = null;
    state.selectedEntryType = null;
    highlightSelection();
    updateExplorerToolbar();
}
export function currentDir() {
    return state.currentCwdRel || '';
}
export function getLanguage(path) {
    const ext = (path.split('.').pop() || '').toLowerCase();
    const map = {
        py: 'python', js: 'javascript', mjs: 'javascript', cjs: 'javascript',
        ts: 'typescript', tsx: 'typescript', jsx: 'javascript',
        html: 'html', htm: 'html', css: 'css', scss: 'scss', less: 'less',
        json: 'json', md: 'markdown', cpp: 'cpp', cc: 'cpp', h: 'cpp', hpp: 'cpp',
        c: 'c', sh: 'shell', bash: 'shell', sql: 'sql', yaml: 'yaml', yml: 'yaml',
        xml: 'xml', java: 'java', cs: 'csharp', go: 'go', rs: 'rust', php: 'php',
        rb: 'ruby', swift: 'swift', kt: 'kotlin', lua: 'lua', r: 'r'
    };
    return map[ext] || 'plaintext';
}
export const errorMarkerFiles = new Set();

export function refreshErrorMarkers() {
    if (!state.editor || !state.monaco || !state.currentFile) return;
    const model = state.editor.getModel();
    if (!model) return;
    const markers = state.monaco.editor.getModelMarkers({ resource: model.uri });
    const hasError = markers.some(m => m.severity === state.monaco.MarkerSeverity.Error);
    if (hasError) {
        errorMarkerFiles.add(state.currentFile);
    } else {
        errorMarkerFiles.delete(state.currentFile);
    }
    applyErrorMarkers();
}
export function applyErrorMarkers() {
    if (!state.explorerTree || typeof findExplorerRow !== 'function') return;
    state.explorerTree.querySelectorAll('.explorer-error').forEach(el => el.classList.remove('explorer-error'));
    errorMarkerFiles.forEach(path => {
        const row = findExplorerRow(path);
        if (row) row.classList.add('explorer-error');
        const segs = path.split('/');
        segs.pop();
        let acc = '';
        for (let i = 0; i < segs.length; i++) {
            acc = acc ? acc + '/' + segs[i] : segs[i];
            const dirRow = findExplorerRow(acc);
            if (dirRow) dirRow.classList.add('explorer-error');
        }
    });
}

loadExplorerOnce();
ligarPrefetchDePastas();
