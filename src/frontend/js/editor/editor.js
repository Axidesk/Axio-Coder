import { ordenarPorChaves, tornarAbasArrastaveis } from './arrastar_abas.js';
import { currentDir, deselectEntry, getLanguage, highlightSelection, loadDirChildren, loadExplorer, reloadExplorer, selectEntry, setView } from './explorer.js';
import { ensureEditor, updateEditorWatermark } from './monaco.js';
import { fadeEditorIn, fadeEditorSwap, smoothRevealLine } from './scroll.js';
import { enterLogMode, enterReadonlyLogMode, exitLogMode } from './themes.js';
import { appendLine, basename, enterDir } from './terminal.js';
import { clearHoverLine } from './highlight.js';
import { openFsContextMenu } from './workspace.js';
import { state } from './state.js';

export function loadFileIntoEditor(path, opts) {
    opts = opts || {};
    if (tabsApagadas.has(path)) {
        const modelo = state.editorModels[path];
        if (modelo) return Promise.resolve(_abrirAbaApagada(path, modelo.getValue(), opts));
    }
    return fetch(state.API + '/api/file_content?caminho=' + encodeURIComponent(path))
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                appendLine('[editor] ' + data.error, 'term-err');
                state.wsStatus.textContent = 'editor: erro';
                return false;
            }
            if (!opts.manterVista) setView('editor');
            ensureEditor();
            const applyContent = function () {
                state.suppressAutoSave = true;
                clearHoverLine();
                if (state.currentFile && state.editor && !state.currentFileIsImage && !state.logMode && !state.diffMode) {
                    state.editorViewStates[state.currentFile] = state.editor.saveViewState();
                }
                state.currentFile = path;
                state.abaAtiva = path;
                if (data.tipo === 'imagem') {
                    showEditorImage(data);
                } else if (data.tipo === 'binario') {
                    showEditorBinary(data.mensagem || 'Arquivo binário (não textual).');
                } else {
                    hideEditorImage();
                    let model = state.editorModels[path];
                    if (!model) {
                        model = state.monaco.editor.createModel(data.conteudo || '', getLanguage(path));
                        state.editorModels[path] = model;
                    } else {
                        if (model.getValue() !== (data.conteudo || '')) {
                            model.setValue(data.conteudo || '');
                        }
                    }
                    state.editor.setModel(model);
                    if (state.editorViewStates[path]) {
                        state.editor.restoreViewState(state.editorViewStates[path]);
                    }
                    state.editor.layout();
                    updateEditorWatermark();
                    if (opts.logMode) {
                        enterLogMode(opts.snippet, data.conteudo || '');
                    } else if (opts.readonlyLog) {
                        enterReadonlyLogMode();
                    } else {
                        exitLogMode();
                    }
                    if (opts.line) {
                        const targetLine = parseInt(opts.line, 10) || 1;
                        requestAnimationFrame(() => {
                            if (!state.editor) return;
                            state.editor.setPosition({ lineNumber: targetLine, column: 1 });
                            smoothRevealLine(state.editor, targetLine);
                        });
                    }
                }
                state.suppressAutoSave = false;
                updateTabsActive();
                state.wsStatus.textContent = 'editor: ' + path;
                if (opts.rename) {
                    state.pendingTabRename = path;
                    renderTabs();
                }
            };

            if (opts.semFade || opts.manterVista) {
                applyContent();
            } else if (state.currentFile) {
                fadeEditorSwap(applyContent);
            } else {
                applyContent();
                fadeEditorIn();
            }
            return true;
        })
        .catch(e => {
            appendLine('[editor] erro: ' + e.message, 'term-err');
            state.wsStatus.textContent = 'editor: erro';
            return false;
        });
}
function _abrirAbaApagada(path, conteudo, opts) {
    if (!opts.manterVista) setView('editor');
    ensureEditor();
    const aplicar = function () {
        state.suppressAutoSave = true;
        clearHoverLine();
        if (state.currentFile && state.editor && !state.currentFileIsImage && !state.logMode && !state.diffMode) {
            state.editorViewStates[state.currentFile] = state.editor.saveViewState();
        }
        state.currentFile = path;
        state.abaAtiva = path;
        hideEditorImage();
        let model = state.editorModels[path];
        if (!model) {
            model = state.monaco.editor.createModel(conteudo || '', getLanguage(path));
            state.editorModels[path] = model;
        }
        state.editor.setModel(model);
        if (state.editorViewStates[path]) {
            state.editor.restoreViewState(state.editorViewStates[path]);
        }
        state.editor.layout();
        updateEditorWatermark();
        enterReadonlyLogMode();
        state.suppressAutoSave = false;
        updateTabsActive();
        state.wsStatus.textContent = 'editor: ' + path + ' (apagado, so leitura)';
    };
    if (opts.semFade || opts.manterVista || !state.currentFile) {
        aplicar();
    } else {
        fadeEditorSwap(aplicar);
    }
    return true;
}
function prepareImageHost() {
    if (!state.editorImageHost) return false;
    if (state.diffHost) state.diffHost.classList.add('hidden');
    if (state.editorHost) state.editorHost.classList.add('hidden');
    if (state.editorWatermark) state.editorWatermark.classList.add('hidden');
    state.editorImageHost.innerHTML = '';
    return true;
}
function fadeInImageHost() {
    state.editorImageHost.style.display = 'flex';
    state.editorImageHost.getAnimations().forEach(a => a.cancel());
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        state.editorImageHost.animate(
            [{ opacity: 0 }, { opacity: 1 }],
            { duration: 240, easing: 'ease' }
        );
    }
}
export function showEditorImage(data) {
    state.currentFileIsImage = true;
    if (!prepareImageHost()) return;
    const img = document.createElement('img');
    img.src = 'data:' + (data.mime || 'image/png') + ';base64,' + (data.data || '');
    img.alt = basename(state.currentFile || '');
    img.draggable = false;
    img.className = 'max-w-full max-h-full object-contain';
    img.onerror = () => showEditorBinary('Nao foi possivel desenhar esta imagem.\nO ficheiro pode estar truncado ou num formato que o editor nao le.');
    state.editorImageHost.appendChild(img);
    fadeInImageHost();
}
export function showEditorBinary(msg) {
    state.currentFileIsImage = true;
    if (!prepareImageHost()) return;
    const div = document.createElement('div');
    div.className = 'text-[var(--text-mutado)] text-sm font-mono select-text px-6 text-center';
    div.style.whiteSpace = 'pre-line';
    div.textContent = msg;
    state.editorImageHost.appendChild(div);
    fadeInImageHost();
}
export function hideEditorImage() {
    state.currentFileIsImage = false;
    if (!state.editorImageHost) return;
    state.editorImageHost.style.display = 'none';
    state.editorImageHost.innerHTML = '';
    if (state.editorHost) state.editorHost.classList.remove('hidden');
}
export function updateExplorerToolbar() {
    if (!state.btnTrash) return;
    const temItens = !!state.trashList && !!state.trashList.querySelector(':scope > .trash-node');
    if (state.trashPurgeMode && temItens) {
        state.btnTrash.className = 'trash-purge-btn';
        state.btnTrash.innerHTML = state.ICON_TRASH + '<span>Excluir tudo</span>';
        state.btnTrash.title = 'Excluir tudo da lixeira (vai para a Lixeira do Windows)';
        return;
    }
    state.btnTrash.innerHTML = state.ICON_TRASH;
    if (state.trashOpen) {
        state.btnTrash.className = 'transition-colors text-[var(--oliva)] hover:text-[var(--oliva-hover)]';
        state.btnTrash.title = 'Fechar lixeira';
    } else {
        state.btnTrash.className = 'transition-colors text-[var(--text-mutado)] hover:text-[var(--oliva)]';
        state.btnTrash.title = 'Abrir lixeira';
    }
}
export function findTabElement(path) {
    if (!state.editorTabs) return null;
    const tabs = state.editorTabs.querySelectorAll('.editor-tab');
    for (const t of tabs) {
        if (t.dataset.path === path) return t;
    }
    return null;
}
function pathDaAbaAtiva() {
    return state.abaAtiva || state.currentFile;
}
export function updateTabsActive() {
    if (!state.editorTabs) return;
    state.editorTabs.querySelectorAll('.editor-tab').forEach(t => {
        t.classList.toggle('editor-tab-active', t.dataset.path === pathDaAbaAtiva());
    });
}
export function allTabPaths() {
    const arr = state.openTabs.slice();
    if (state.previewTabPath && !arr.includes(state.previewTabPath)) arr.push(state.previewTabPath);
    return arr;
}
export function addTab(path, preview) {
    if (preview) {
        if (!state.openTabs.includes(path)) state.previewTabPath = path;
    } else {
        if (!state.openTabs.includes(path)) state.openTabs.push(path);
        if (state.previewTabPath === path) state.previewTabPath = null;
    }
}
export function focarAba(path) {
    if (!path) return;
    addTab(path, false);
    state.abaAtiva = path;
    renderTabs();
}
export function pinPreview(path) {
    const target = path || state.previewTabPath || state.currentFile;
    if (!target) return;
    if (!state.openTabs.includes(target)) state.openTabs.push(target);
    if (state.previewTabPath === target) state.previewTabPath = null;
    renderTabs();
}
function rotulosDasAbas(caminhos) {

    const rotulos = new Map();
    const porNome = new Map();
    caminhos.forEach(p => {
        const b = basename(p);
        if (!porNome.has(b)) porNome.set(b, []);
        porNome.get(b).push(p);
    });
    const usados = new Set();
    caminhos.forEach(p => {
        const grupo = porNome.get(basename(p));
        if (grupo.length === 1 || grupo[0] === p) {
            rotulos.set(p, basename(p));
            usados.add(basename(p));
        }
    });
    caminhos.forEach(p => {
        if (rotulos.has(p)) return;
        const partes = String(p).replace(/\\/g, '/').split('/').filter(Boolean);
        for (let n = 2; n <= partes.length; n++) {
            const candidato = partes.slice(-n).join('/');
            if (!usados.has(candidato)) {
                usados.add(candidato);
                rotulos.set(p, candidato);
                return;
            }
        }
        rotulos.set(p, p);
    });
    return rotulos;
}
export function reordenarAbas(ordem) {
    ordenarPorChaves(state.openTabs, ordem, (caminho) => caminho);
    renderTabs();
}
const tabsApagadas = new Set();
const ESPERA_DA_RECONCILIACAO_MS = 300;
let reconciliacaoTimer = null;

export function renderTabs() {
    if (!state.editorTabs) return;
    tornarAbasArrastaveis(state.editorTabs, reordenarAbas);
    const caminhos = allTabPaths();
    const rotulos = rotulosDasAbas(caminhos);
    state.editorTabs.innerHTML = '';
    caminhos.forEach(path => {
        const tab = document.createElement('div');
        tab.className = 'editor-tab' + (path === pathDaAbaAtiva() ? ' editor-tab-active' : '') + (path === state.previewTabPath ? ' editor-tab-preview' : '') + (tabsApagadas.has(path) ? ' editor-tab-apagado' : '');
        tab.dataset.path = path;
        tab.title = path;
        const nameSpan = document.createElement('span');
        nameSpan.className = 'editor-tab-name';
        nameSpan.textContent = rotulos.get(path) || basename(path);
        const closeBtn = document.createElement('button');
        closeBtn.className = 'editor-tab-close';
        closeBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        closeBtn.title = 'Fechar';
        tab.appendChild(nameSpan);
        tab.appendChild(closeBtn);
        tab.addEventListener('click', (e) => {
            if (e.target.closest('.editor-tab-close')) return;
            if (path === state.currentFile) { setView('editor'); return; }
            loadFileIntoEditor(path).then(ok => { if (ok) updateTabsActive(); });
        });
        tab.addEventListener('dblclick', () => {
            startTabRename(path, tab, nameSpan);
        });
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeTab(path);
        });
        state.editorTabs.appendChild(tab);
    });
    if (state.pendingTabRename) {
        const target = state.pendingTabRename;
        const tab = findTabElement(target);
        if (tab) {
            state.pendingTabRename = null;
            startTabRename(target, tab, tab.querySelector('.editor-tab-name'));
        }
    }
}
export function marcarAbaApagada(path) {
    if (_marcarAbaApagada(path)) renderTabs();
}

export function limparAbaApagada(path) {
    if (_limparAbaApagada(path)) renderTabs();
}

function _marcarAbaApagada(path) {
    if (!path || tabsApagadas.has(path)) return false;
    tabsApagadas.add(path);
    return true;
}

function _limparAbaApagada(path) {
    return tabsApagadas.delete(path);
}

export function agendarReconciliacaoDeAbas() {
    if (reconciliacaoTimer) clearTimeout(reconciliacaoTimer);
    reconciliacaoTimer = setTimeout(() => {
        reconciliacaoTimer = null;
        reconciliarAbas();
    }, ESPERA_DA_RECONCILIACAO_MS);
}

export async function reconciliarAbas() {
    const caminhos = allTabPaths();
    if (!caminhos.length) return;
    let ausentes;
    try {
        const resp = await fetch(state.API + '/api/fs_existem', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminhos: caminhos })
        });
        const data = await resp.json();
        ausentes = new Set(data && data.ausentes);
    } catch (erro) {
        return;
    }
    let mudou = false;
    for (const caminho of caminhos) {
        if (ausentes.has(caminho)) mudou = _marcarAbaApagada(caminho) || mudou;
        else mudou = _limparAbaApagada(caminho) || mudou;
    }
    if (mudou) renderTabs();
}

window.addEventListener('focus', agendarReconciliacaoDeAbas);

export function startTabRename(path, tab, nameSpan) {
    if (!nameSpan) return;
    iniciarRenameInline({
        path: path,
        alvo: nameSpan,
        valor: basename(path),
        nomeOriginal: basename(path),
        classe: 'editor-tab-rename',
        renameTarget: { path: path },
        aoDescartar: () => renderTabs(),
    });
}
export function openFileInEditor(path, opts) {

    opts = opts || {};
    if (state.typingCreatedFile && state.typingCreatedFile !== path) state.typingCreatedFile = null;
    limparAbaApagada(path);
    if (state.currentFile === path && !opts.recarregar) {
        if (!opts.manterVista) setView('editor');
        return Promise.resolve(true);
    }
    if (!state.monaco) {
        state.pendingFile = path;
        if (opts.rename) state.pendingTabRename = path;
        if (!opts.manterVista) setView('editor');
        state.wsStatus.textContent = 'editor: carregando...';
        return Promise.resolve(false);
    }
    if (!opts.manterVista) setView('editor');
    return loadFileIntoEditor(path, opts).then(ok => {
        if (!ok) return false;
        addTab(path, !!opts.preview);
        renderTabs();
        return true;
    });
}
export function closeTab(path) {
    const allBefore = allTabPaths();
    const idx = allBefore.indexOf(path);
    if (state.typingCreatedFile === path) state.typingCreatedFile = null;
    if (state.openTabs.includes(path)) state.openTabs.splice(state.openTabs.indexOf(path), 1);
    if (state.previewTabPath === path) state.previewTabPath = null;
    if (state.abaAtiva === path) state.abaAtiva = null;
    if (state.currentFile === path) {
        if (state.logMode || state.diffMode) {
            exitLogMode();
        }
        state.currentFile = null;
        if (state.editor) {
            state.suppressAutoSave = true;
            state.editor.setModel(null);
            state.suppressAutoSave = false;
        }
        state.currentFileIsImage = false;
        hideEditorImage();
        updateEditorWatermark();
        deselectEntry();
        const next = allTabPaths()[Math.max(0, idx - 1)] || null;
        renderTabs();
        if (next) {
            loadFileIntoEditor(next);
        } else {
            state.wsStatus.textContent = 'editor: fechado';
        }
    } else {
        renderTabs();
    }
}
export function closeActiveTab() {
    if (!state.currentFile) return;
    closeTab(state.currentFile);
}
export async function performRename(path, novoNome) {
    try {
        const resp = await fetch(state.API + '/api/fs_rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminho: path, novo_nome: novoNome })
        });
        const data = await resp.json();
        if (data.error) {
            appendLine('[explorer] ' + data.error, 'term-err');
            return null;
        }
        const newPath = data.caminho || path;
        window.dispatchEvent(new CustomEvent('axio-fs-renamed', { detail: { oldPath: path, newPath: newPath } }));
        if (state.typingCreatedFile === path) state.typingCreatedFile = newPath;
        const idx = state.openTabs.indexOf(path);
        if (idx !== -1) state.openTabs[idx] = newPath;
        if (state.previewTabPath === path) state.previewTabPath = newPath;
        if (state.editorModels[path]) {
            state.editorModels[newPath] = state.editorModels[path];
            delete state.editorModels[path];
            state.monaco.editor.setModelLanguage(state.editorModels[newPath], getLanguage(newPath));
        }
        if (state.editorViewStates[path]) {
            state.editorViewStates[newPath] = state.editorViewStates[path];
            delete state.editorViewStates[path];
        }
        if (state.currentFile === path) {
            state.currentFile = newPath;
        }
        if (state.selectedPath === path) state.selectedPath = newPath;
        reloadExplorer();
        renderTabs();
        return newPath;
    } catch (e) {
        appendLine('[explorer] erro: ' + e.message, 'term-err');
        return null;
    }
}
export async function revealPath(relPath) {
    if (!relPath) return;
    const segments = relPath.split('/');
    let current = '';
    for (let i = 0; i < segments.length - 1; i++) {
        current = current ? current + '/' + segments[i] : segments[i];
        const row = findExplorerRow(current);
        if (!row) continue;
        const li = row.closest('.explorer-item');
        const container = li ? li.querySelector('.explorer-children') : null;
        if (!container) continue;
        if (container.dataset.loaded !== '1') {
            await loadDirChildren(current, container);
        } else {
            container.classList.remove('hidden');
        }
    }
    highlightSelection();
}
export function caminhoRelativoAoProjeto(caminho, separador) {
    const p = String(caminho || '').replace(/\\/g, '/');
    const raiz = String(state.rootPath || state.currentCwd || '').replace(/\\/g, '/').replace(/\/+$/, '');
    const rel = (raiz && p.toLowerCase().startsWith(raiz.toLowerCase() + '/')) ? p.slice(raiz.length + 1) : p;
    return separador ? rel.replace(/\//g, separador) : rel;
}
export async function revealAndSelectFile(path) {
    if (!path) return;
    if (!state.explorerLoaded && typeof loadExplorer === 'function') {
        state.explorerLoaded = true;
        state.explorerReadyPromise = loadExplorer();
        if (typeof loadTrash === 'function') loadTrash();
    }
    if (state.explorerReadyPromise) {
        try { await state.explorerReadyPromise; } catch (e) {}
    }
    const relativo = caminhoRelativoAoProjeto(path);
    const segments = relativo.split('/').filter(Boolean);
    const parent = segments.length > 1 ? segments.slice(0, -1).join('/') : '';
    if (parent !== state.currentCwdRel && typeof enterDir === 'function') {
        await enterDir(parent);
    }
    selectEntry(relativo, 'file');
    const row = findExplorerRow(relativo);
    if (row && typeof row.scrollIntoView === 'function') {
        row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
}
export function findExplorerRow(path) {
    try {
        return state.explorerTree.querySelector('.explorer-row[data-path="' + CSS.escape(path) + '"]');
    } catch (e) {
        return null;
    }
}
export function startRename(path, row) {
    if (!row) row = findExplorerRow(path);
    if (!row) return;
    const span = row.querySelector('span');
    if (!span) return;
    const nome = span.textContent;
    iniciarRenameInline({
        path: path,
        alvo: span,
        valor: nome,
        nomeOriginal: nome,
        classe: 'explorer-rename-input',
        renameTarget: { path: path, row: row },
        aoDescartar: (input) => { if (input.parentNode) input.replaceWith(span); },
    });
}

function iniciarRenameInline(opts) {
    state.renameTarget = opts.renameTarget;
    const input = document.createElement('input');
    input.type = 'text';
    input.value = opts.valor;
    input.className = opts.classe;
    opts.alvo.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const commit = async () => {
        if (done) return;
        done = true;
        state.renameTarget = null;
        const novoNome = input.value.trim();
        if (novoNome && novoNome !== opts.nomeOriginal) {
            await performRename(opts.path, novoNome);
        } else {
            opts.aoDescartar(input);
        }
    };
    input.addEventListener('keydown', ev => {
        if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
        else if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); done = true; state.renameTarget = null; opts.aoDescartar(input); }
    });
    input.addEventListener('blur', commit);
}
export async function createFs(tipo) {
    const dir = currentDir();
    const baseName = tipo === 'dir' ? 'nova_pasta' : 'Novo Ficheiro';
    const caminho = dir ? dir + '/' + baseName : baseName;
    try {
        const resp = await fetch(state.API + '/api/fs_create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminho: caminho, tipo: tipo })
        });
        const data = await resp.json();
        if (data.error) {
            appendLine('[explorer] ' + data.error, 'term-err');
            return;
        }
        await reloadExplorer();
        await revealPath(data.caminho);
        selectEntry(data.caminho, tipo);
        if (tipo === 'dir') {
            const row = findExplorerRow(data.caminho);
            if (row) startRename(data.caminho, row);
        } else {
            openFileInEditor(data.caminho, { rename: true });
        }
    } catch (e) {
        appendLine('[explorer] erro: ' + e.message, 'term-err');
    }
}
export async function loadTrash(silencioso) {
    if (!state.trashList) return;
    if (!silencioso && !state.trashList.querySelector(':scope > .trash-node')) {
        state.trashList.innerHTML = '<div class="explorer-loading">carregando...</div>';
    }
    try {
        const resp = await fetch(state.API + '/api/trash', { cache: 'no-store' });
        const data = await resp.json();
        const visiveis = (data.items || []).filter(item => !state.pendingTrashDelete.has(item.id));
        if (visiveis.length === 0) {
            state.trashList.innerHTML = '<div class="explorer-loading">lixeira vazia</div>';
            return;
        }
        state.trashList.querySelectorAll('.explorer-loading').forEach(el => el.remove());
        const pendentes = new Map();
        state.trashList.querySelectorAll(':scope > .trash-node').forEach(el => {
            if (el.dataset.id) pendentes.set(el.dataset.id, el);
        });
        visiveis.forEach(item => {
            const existente = pendentes.get(item.id);
            if (existente) {
                pendentes.delete(item.id);
                state.trashList.appendChild(existente);
                return;
            }
            state.trashList.appendChild(montarNodeTrash(item));
        });
        pendentes.forEach(el => el.remove());
    } catch (e) {
        state.trashList.innerHTML = '<div class="explorer-loading term-err">' + e.message + '</div>';
    }
}
export function montarNodeTrash(item) {
    const node = document.createElement('div');
    node.className = 'trash-node';
    node.dataset.id = item.id;
    node.dataset.tipo = item.tipo || 'file';

    const div = document.createElement('div');
    div.className = 'trash-item';
    div.title = item.original || item.nome;
    div.innerHTML = (item.tipo === 'dir' ? state.ICON_FOLDER : state.ICON_FILE) +
        '<span>' + item.nome + '</span>' +
        '<button class="trash-restore" title="Restaurar" type="button">' +
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>' +
        '</button>';
    const selectTrashItem = () => {
        state.trashSelectedId = item.id;
        state.trashSelectedName = item.nome;
        state.selectedPath = null;
        state.selectedEntryType = null;
        highlightSelection();
        document.querySelectorAll('.trash-item').forEach(el => el.classList.remove('trash-item-selected'));
        div.classList.add('trash-item-selected');
        updateExplorerToolbar();
    };
    div.addEventListener('click', () => {
        selectTrashItem();
        if (item.tipo === 'dir') alternarFilhosTrash(node, item.id);
    });
    div.addEventListener('contextmenu', (ev) => {
        ev.preventDefault();
        selectTrashItem();
        openFsContextMenu(ev.clientX, ev.clientY, null, item.id);
    });
    const restoreBtn = div.querySelector('.trash-restore');
    restoreBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        state.trashSelectedId = item.id;
        state.trashSelectedName = item.nome;
        doRestoreTrash();
    });

    node.appendChild(div);
    const children = document.createElement('div');
    children.className = 'trash-children hidden';
    node.appendChild(children);
    return node;
}
export async function alternarFilhosTrash(node, id) {
    const children = node.querySelector('.trash-children');
    if (!children) return;
    if (children.dataset.loaded === '1') {
        children.classList.toggle('hidden');
        return;
    }
    children.classList.remove('hidden');
    children.innerHTML = '<div class="explorer-loading">carregando...</div>';
    try {
        const resp = await fetch(state.API + '/api/trash_tree?id=' + encodeURIComponent(id), { cache: 'no-store' });
        const data = await resp.json();
        children.innerHTML = '';
        (data.items || []).forEach(sub => children.appendChild(montarNodeTrash(sub)));
        children.dataset.loaded = '1';
    } catch (e) {
        children.innerHTML = '<div class="explorer-loading term-err">' + e.message + '</div>';
    }
}
export function openTrash() {
    state.trashOpen = true;
    state.trashSelectedId = null;
    state.trashSelectedName = null;
    state.trashPurgeMode = false;
    if (state.trashView) state.trashView.classList.remove('trash-closed');
    updateExplorerToolbar();
    loadTrash();
}
export function closeTrash() {
    state.trashOpen = false;
    state.trashSelectedId = null;
    state.trashSelectedName = null;
    state.trashPurgeMode = false;
    if (state.trashView) state.trashView.classList.add('trash-closed');
    updateExplorerToolbar();
}
export function setLimpezaLixeira(ativo) {
    if (ativo) {
        if (state.trashPurgeMode || !state.trashOpen) return;
        if (!state.trashList || !state.trashList.querySelector(':scope > .trash-node')) return;
    } else if (!state.trashPurgeMode) {
        return;
    }
    state.trashPurgeMode = ativo;
    updateExplorerToolbar();
}
export function openFsConfirm(message, onYes) {
    if (!state.fsConfirmPopup) return;
    state.fsConfirmMessage.textContent = message;
    state.pendingFsConfirm = onYes;
    state.fsConfirmPopup.classList.remove('opacity-0', 'pointer-events-none');
    const content = state.fsConfirmPopup.querySelector('#fs-confirm-content');
    if (content) { content.classList.remove('scale-95'); content.classList.add('scale-100'); }
}
export function closeFsConfirm() {
    state.pendingFsConfirm = null;
    if (state.fsConfirmPopup) {
        state.fsConfirmPopup.classList.add('opacity-0', 'pointer-events-none');
        const content = state.fsConfirmPopup.querySelector('#fs-confirm-content');
        if (content) { content.classList.add('scale-95'); content.classList.remove('scale-100'); }
    }
}
if (state.fsConfirmYes) {
    state.fsConfirmYes.addEventListener('click', () => {
        const fn = state.pendingFsConfirm;
        closeFsConfirm();
        if (fn) fn();
    });
}
if (state.fsConfirmCancel) {
    state.fsConfirmCancel.addEventListener('click', closeFsConfirm);
}
export async function trashPath(path) {
    if (!path) return;
    if (state.autoSaveTimer) {
        clearTimeout(state.autoSaveTimer);
        state.autoSaveTimer = null;
    }
    try {
        const resp = await fetch(state.API + '/api/fs_trash', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminho: path })
        });
        const data = await resp.json();
        if (data.error) {
            appendLine('[explorer] ' + data.error, 'term-err');
            return;
        }
        if (state.typingCreatedFile === (data.caminho || path)) state.typingCreatedFile = null;
        marcarAbaApagada(data.caminho || path);
        window.dispatchEvent(new CustomEvent('axio-fs-deleted', { detail: { path: data.caminho || path } }));
        if (state.selectedPath === path) deselectEntry();
        reloadExplorer();
        await loadTrash(true);
    } catch (e) {
        appendLine('[explorer] erro: ' + e.message, 'term-err');
    }
}
export async function doTrashSelected() {
    await trashPath(state.selectedPath);
}
export async function doDeleteTrashPermanent() {
    const id = state.trashSelectedId;
    if (!id) return;
    state.pendingTrashDelete.add(id);
    try {
        const resp = await fetch(state.API + '/api/trash_delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        const data = await resp.json();
        if (data.error) {
            state.pendingTrashDelete.delete(id);
            appendLine('[lixeira] ' + data.error, 'term-err');
            return;
        }
        state.trashSelectedId = null;
        state.trashSelectedName = null;
        updateExplorerToolbar();
        loadTrash(true);
    } catch (e) {
        state.pendingTrashDelete.delete(id);
        appendLine('[lixeira] erro: ' + e.message, 'term-err');
    }
}
export async function doRestoreTrash() {
    const id = state.trashSelectedId;
    if (!id) return;
    try {
        const resp = await fetch(state.API + '/api/trash_restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        const data = await resp.json();
        if (data.error) {
            appendLine('[lixeira] ' + data.error, 'term-err');
            return;
        }
        if (data.caminho) {
            window.dispatchEvent(new CustomEvent('axio-fs-restored', { detail: { path: data.caminho } }));
        }
        state.trashSelectedId = null;
        updateExplorerToolbar();
        loadTrash(true);
        reloadExplorer();
    } catch (e) {
        appendLine('[lixeira] erro: ' + e.message, 'term-err');
    }
}
export function doPurgeTrash() {
    if (!state.trashList) return;
    const total = state.trashList.querySelectorAll(':scope > .trash-node').length;
    if (!total) return;
    const rotulo = total === 1 ? '1 item' : total + ' itens';
    openFsConfirm('Excluir tudo da lixeira (' + rotulo + ')? Irá para a Lixeira do Windows.', async () => {
        state.trashPurgeMode = false;
        state.trashSelectedId = null;
        state.trashSelectedName = null;
        updateExplorerToolbar();
        state.trashList.innerHTML = '<div class="explorer-loading">excluindo...</div>';
        try {
            const resp = await fetch(state.API + '/api/trash_purge', { method: 'POST' });
            const data = await resp.json();
            if (data.error) appendLine('[lixeira] ' + data.error, 'term-err');
        } catch (e) {
            appendLine('[lixeira] erro: ' + e.message, 'term-err');
        }
        loadTrash(true);
    });
}
