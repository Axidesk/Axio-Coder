import { applyLineGutterState, defineDiffTheme, defineEditorTheme, defineLogTheme, enterLogMode, enterLogModeWithLines, enterReadonlyLogMode, exitLogMode, updateLineNumbersButton } from './themes.js';
import { VISTAS_DE_TRABALHO, fecharPreview, getLanguage, loadExplorerOnce, selectEntry, setView } from './explorer.js';
import { agendarReconciliacaoDeAbas, closeActiveTab, closeTrash, createFs, doDeleteTrashPermanent, doPurgeTrash, doRestoreTrash, doTrashSelected, findExplorerRow, loadTrash, openFileInEditor, openFsConfirm, openTrash, renderTabs, revealAndSelectFile, setLimpezaLixeira, startRename, trashPath } from './editor.js';
import { ALTURA_LINHA } from './metricas.js';
import { ensureEditor, initMonaco, updateEditorWatermark } from './monaco.js';
import { aplicarShellAtual, basename, clearLog, connectTermSocket, runCommand } from './terminal.js';
import { cardFinalizar, cardIniciar, cardSaida, escreverNoCardSelecionado, lancarComando, temCardSelecionado } from './terminal_cards.js';
import { ensureTerminal, termFit } from './xterm.js';
import { captureDiffExitScroll, computeLineDiff, enterDiffMode, exitDiffMode, revealDiffExitScroll } from './diff.js';
import { fadeEditorSwap, fadeGutterSwap, revelarLinhaComRolagem, scheduleExplorerReload, smoothRevealLine } from './scroll.js';
import { state } from './state.js';

const DOCK_ANIM_MS = 450;

self.MonacoEnvironment = {
    getWorkerUrl: function (moduleId, label) {
        if (label === 'json') return state.API + '/monaco/vs/language/json/json.worker.js';
        if (label === 'css' || label === 'scss' || label === 'less') return state.API + '/monaco/vs/language/css/css.worker.js';
        if (label === 'html' || label === 'handlebars' || label === 'razor') return state.API + '/monaco/vs/language/html/html.worker.js';
        if (label === 'typescript' || label === 'javascript') return state.API + '/monaco/vs/language/typescript/ts.worker.js';
        return state.API + '/monaco/vs/editor/editor.worker.js';
    }
};

export function handleSSE(data) {
    if (data.type === 'process_started') {
        cardIniciar(data);
    } else if (data.type === 'process_output') {
        cardSaida(data);
    } else if (data.type === 'process_finished') {
        cardFinalizar(data);
    } else if (data.type === 'workspace_activate') {
        state.wsStatus.textContent = 'bootstrap ativo';
    } else if (data.type === 'files_changed') {
        scheduleExplorerReload();
        agendarReconciliacaoDeAbas();
        if (state.trashOpen) loadTrash(true);
        loadVenvName();
    }
}

export function ensureMonacoReady(cb) {
    if (state.monaco) { cb(); return; }
    initMonaco(function () {
        state.monaco = window.monaco;
        cb();
    });
}

export function preloadMonaco() {
    ensureMonacoReady(function () {
        defineEditorTheme();
        defineLogTheme();
        defineDiffTheme();
    });
}

function preloadTerminal() {
    if (state.termSocket) return;
    connectTermSocket();
    ensureTerminal();
}

export function ensureWorkspaceReady() {
    ensureMonacoReady(function () {
        ensureEditor();
        if (state.pendingDiffData) {
            const dd = state.pendingDiffData;
            const ds = state.pendingSnippet;
            state.pendingDiffData = null;
            state.pendingSnippet = null;
            openFileFromLog(state.pendingFile, ds, dd);
            state.pendingFile = null;
            state.pendingLogMode = false;
        } else if (state.pendingFile) {
            const p = state.pendingFile;
            const logOpts = state.pendingLogMode ? { logMode: true, snippet: state.pendingSnippet } : {};
            if (state.pendingLine) logOpts.line = state.pendingLine;
            state.pendingFile = null;
            state.pendingLine = null;
            state.pendingLogMode = false;
            openFileInEditor(p, logOpts);
        }
    });
    loadExplorerOnce();
}

export function activate() {
    ensureWorkspaceReady();
    setActive(true);
    connectTermSocket();
    ensureTerminal();
    termFit();
    state.termInput.focus();
}

export function showEditor() {
    abrirDoc('editor');
}

export function abrirDoc(vista) {
    ensureWorkspaceReady();
    setActive(true);
    setView(vista || state.vistaDeTrabalho);
}

export function setActive(active) {
    state.workspaceActive = !!active;
    if (!active) collapseVenv();
    const documentoAberto = emVistaDeTrabalho();
    const barVisible = state.workspaceActive || documentoAberto;
    if (state.wsTopBar) {
        if (barVisible) {
            state.wsTopBar.classList.remove('hidden');
            state.wsTopBar.style.opacity = '0';
            void state.wsTopBar.offsetWidth;
            state.wsTopBar.style.opacity = '1';
        } else {
            state.wsTopBar.style.opacity = '0';
            window.setTimeout(() => {
                state.wsTopBar.classList.add('hidden');
                state.wsTopBar.style.opacity = '1';
            }, 300);
        }
    }
    if (!active && !documentoAberto) {
        setView('chat');
    }
    applyTopBarVisibility();
    applyTabsVisibility();
}

function emVistaDeTrabalho() {
    return VISTAS_DE_TRABALHO.includes(state.currentView);
}

export function applyTopBarVisibility() {
    if (!state.workspaceActive && !emVistaDeTrabalho()) return;
    if (state.wsTopBar) state.wsTopBar.classList.toggle('ws-top-bar-collapsed', state.topBarHidden);
    if (state.termTopBar) state.termTopBar.classList.toggle('term-top-bar-collapsed', state.topBarHidden);
}

export function applyTabsVisibility() {
    if (!state.editorTabs) return;
    const show = state.currentView === 'editor';
    state.editorTabs.classList.toggle('editor-tabs-visible', show);
}

export function setTopBarHidden(hidden) {
    state.topBarHidden = !!hidden;
    applyTopBarVisibility();
}

export function alinharComLinha(linha) {

    if (!state.monaco) return false;
    const ed = (state.diffMode && state.diffModifiedEditor) ? state.diffModifiedEditor : state.editor;
    const modelo = ed && ed.getModel();
    if (!modelo) return false;
    const n = Number(linha);
    if (!isFinite(n)) return false;
    const total = modelo.getLineCount();

    const ref = Math.max(1, Math.min(total, Math.floor(n)));
    const topo = ed.getTopForLineNumber(ref) + (n - ref) * ALTURA_LINHA;
    ed.setScrollTop(Math.max(0, Math.round(topo)), state.monaco.editor.ScrollType.Immediate);
    return true;
}

export async function transferirDaCamada(path, linha, arquivoOriginal) {

    if (!state.monaco) return false;

    const alvo = path || arquivoOriginal;
    if (!alvo) return false;

    const recarregar = state.diffMode || state.logModeNeedsReload || state.currentFile !== alvo;
    if (state.logMode || state.diffMode) exitLogMode(true);
    if (recarregar) await openFileInEditor(alvo, { semFade: true, recarregar: true });
    if (!path) revealAndSelectFile(alvo);
    if (linha == null) return true;
    return alinharComLinha(linha);
}

export function layoutAllEditors() {
    if (state.editor) state.editor.layout();
    if (state.diffOriginalEditor) state.diffOriginalEditor.layout();
    if (state.diffModifiedEditor) state.diffModifiedEditor.layout();
}

export function applyExplorerSize(diferirLayout) {
    const row = document.getElementById('dock-bottom-row');
    const right = state.dockSide === 'right';
    if (row) {
        const eixo = right ? 'width' : 'height';
        const outro = right ? 'height' : 'width';
        const valor = state.dockCollapsedForFocus ? '0px' : (state.explorerSize + 'px');
        if (row.style[eixo] !== valor) row.style[eixo] = valor;
        if (row.style[outro]) row.style[outro] = '';
    }
    const view = state.explorerView;
    if (view) {
        if (right) {
            if (view.style.height) view.style.height = '';
            if (view.style.width) view.style.width = '';
        } else {
            if (view.style.height !== '100%') view.style.height = '100%';
            if (view.style.width !== 'auto') view.style.width = 'auto';
        }
    }
    if (diferirLayout) scheduleEditorLayout();
    else layoutAllEditors();
}

export function collapseDockForFocus() {
    if (state.dockCollapsedForFocus) return;
    const row = document.getElementById('dock-bottom-row');
    if (!row) return;
    state.dockCollapsedSavedSize = state.explorerSize > 0 ? state.explorerSize : 240;
    state.dockCollapsedForFocus = true;
    applyExplorerSize();
    row.style.borderTopWidth = '0px';
    row.style.borderLeftWidth = '0px';
    row.style.opacity = '0';
    setTimeout(layoutAllEditors, DOCK_ANIM_MS);
}

export function expandDockForFocus() {
    if (!state.dockCollapsedForFocus) return;
    const row = document.getElementById('dock-bottom-row');
    if (!row) return;
    state.dockCollapsedForFocus = false;
    state.explorerSize = state.dockCollapsedSavedSize || 240;
    row.style.borderTopWidth = '';
    row.style.borderLeftWidth = '';
    row.style.opacity = '';
    applyExplorerSize();
    setTimeout(layoutAllEditors, DOCK_ANIM_MS);
}

export function isDockCollapsedForFocus() {
    return state.dockCollapsedForFocus;
}

export function applyDockLayout() {
    const isRight = state.dockSide === 'right';
    const panel = document.getElementById('editor-panel');
    if (panel) {
        panel.classList.toggle('dock-right', isRight);
        panel.classList.toggle('dock-bottom', !isRight);
    }
    applyFilesLayout();
    applyExplorerSize(true);
    if (state.btnDockRight) {
        state.btnDockRight.classList.toggle('text-[var(--oliva)]', isRight);
        state.btnDockRight.classList.toggle('text-[var(--text-suave)]', !isRight);
    }
    setTimeout(layoutAllEditors, DOCK_ANIM_MS);
}

export function applyFilesLayout() {
    if (!state.explorerTree) return;
    state.explorerTree.classList.toggle('files-vertical', state.dockSide !== 'right');
}

export function animateDock(dir) {
    if (!state.explorerView) return;
    state.explorerView.classList.remove('dock-anim-right', 'dock-anim-bottom');
    void state.explorerView.offsetWidth;
    state.explorerView.classList.add(dir === 'right' ? 'dock-anim-right' : 'dock-anim-bottom');
}

export function initExplorerResizer() {
    if (!state.explorerResizer) return;
    state.explorerResizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const dockRow = document.getElementById('dock-bottom-row');
        const right = state.dockSide === 'right';
        const startPos = right ? e.clientX : e.clientY;
        const startSize = state.explorerSize;
        let rafId = null;
        let pendingSize = null;
        if (dockRow) dockRow.classList.add('resizing');

        function flush() {
            rafId = null;
            if (pendingSize === null) return;
            state.explorerSize = pendingSize;
            pendingSize = null;
            applyExplorerSize(true);
        }

        function onMove(ev) {
            const delta = (right ? ev.clientX : ev.clientY) - startPos;
            let newSize = startSize - delta;
            newSize = Math.max(80, Math.min(700, newSize));
            pendingSize = newSize;
            if (rafId === null) rafId = requestAnimationFrame(flush);
        }

        function onUp() {
            if (rafId !== null) {
                cancelAnimationFrame(rafId);
                rafId = null;
            }
            if (pendingSize !== null) {
                state.explorerSize = pendingSize;
                pendingSize = null;
            }
            applyExplorerSize();
            persistDockPrefs();
            if (dockRow) dockRow.classList.remove('resizing');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        }

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });
}

export function openFileFromLog(path, snippet, diffData, asReadonly) {
    if (!path) return;
    ensureWorkspaceReady();
    setActive(true);
    setTopBarHidden(false);
    setView('editor');
    if (typeof revealAndSelectFile === 'function') revealAndSelectFile(path);
    if (!state.monaco) {
        state.pendingFile = path;
        state.pendingSnippet = snippet || null;
        state.pendingLogMode = !!snippet;
        state.pendingDiffData = diffData || null;
        setView('editor');
        state.wsStatus.textContent = 'editor: carregando...';
        return;
    }

    const temLinhas = diffData && Array.isArray(diffData.deletedLines) && Array.isArray(diffData.addedLines) &&
                      (diffData.deletedLines.length > 0 || diffData.addedLines.length > 0);
    const hasFullDiff = diffData && diffData.full && diffData.original && diffData.modified && diffData.original !== diffData.modified;
    let diff = null;
    if (temLinhas) {
        diff = {
            deletedLines: diffData.deletedLines.slice(),
            addedLines: diffData.addedLines.slice(),
            origToMod: Array.isArray(diffData.origToMod) ? diffData.origToMod.slice() : [],
            modToOrig: Array.isArray(diffData.modToOrig) ? diffData.modToOrig.slice() : [],
            anchorLine: 0
        };
    } else if (hasFullDiff) {
        diff = computeLineDiff(diffData.original, diffData.modified);
    }
    const hasSubstitution = diff && diff.deletedLines.length && diff.addedLines.length;
    const hasAddition = diff && !diff.deletedLines.length && diff.addedLines.length;
    const hasDeletion = diff && diff.deletedLines.length && !diff.addedLines.length;

    if (hasSubstitution) {
        if (state.currentFile !== path) {
            state.currentFile = path;
            if (!state.openTabs.includes(path)) state.openTabs.push(path);
        }
        updateEditorWatermark();
        renderTabs();
        state.wsStatus.textContent = 'diff: ' + path;
        enterDiffMode(diffData.original, diffData.modified, snippet, path, diff);
        return;
    }
    if (hasAddition) {
        showSingleViewLog(path, diffData.modified, diff.addedLines, 'monaco-diff-added-text', false);
        return;
    }
    if (hasDeletion) {
        showSingleViewLog(path, diffData.original, diff.deletedLines, 'monaco-diff-deleted-text', true);
        return;
    }
    if (state.currentFile === path && state.editor) {
        if (asReadonly) {
            const exitScroll = captureDiffExitScroll();
            exitDiffMode(true);
            enterReadonlyLogMode();
            revealDiffExitScroll(exitScroll);
        } else {
            const applyMode = () => {
                if (snippet) {
                    enterLogMode(snippet, state.editor.getValue());
                } else {
                    exitLogMode();
                }
                const linhas = state.currentLogChangedLines || [];
                revelarLinhaComRolagem(state.editor, linhas[0], 600);
            };
            fadeEditorSwap(applyMode);
        }
        return;
    }
    let opts;
    if (snippet) {
        opts = { logMode: true, snippet: snippet };
    } else if (asReadonly) {
        opts = { readonlyLog: true };
    } else {
        opts = {};
    }
    openFileInEditor(path, opts);
}

export function showSingleViewLog(path, content, changedLines, cls, needsReload) {
    ensureEditor();
    const trocaNoMesmoFicheiro = state.currentFile === path;
    if (state.currentFile && state.currentFile !== path && state.editor && !state.currentFileIsImage && !state.logMode && !state.diffMode) {
        state.editorViewStates[state.currentFile] = state.editor.saveViewState();
    }
    if (state.currentFile !== path) {
        state.currentFile = path;
        if (!state.openTabs.includes(path)) state.openTabs.push(path);
    }
    const sameContent = state.currentFile === path && state.logMode && state.editor && state.editor.getValue() === content;
    if (!sameContent) {
        state.suppressAutoSave = true;
        let model = state.editorModels[path];
        if (!model) {
            model = state.monaco.editor.createModel(content || '', getLanguage(path));
            state.editorModels[path] = model;
        } else {
            if (model.getValue() !== (content || '')) {
                model.setValue(content || '');
            }
        }
        state.editor.setModel(model);
        state.suppressAutoSave = false;
    }
    updateEditorWatermark();
    renderTabs();
    state.wsStatus.textContent = 'log: ' + path;
    enterLogModeWithLines(changedLines, cls, needsReload);
    if (trocaNoMesmoFicheiro) revelarLinhaComRolagem(state.editor, (changedLines || [])[0], 600);
    state.savedDiffScrolls.clear();
}

export function openFileAtLine(path, line) {
    if (!path) return;
    const targetLine = parseInt(line, 10) || 1;
    ensureWorkspaceReady();
    if (state.currentFile === path && state.editor) {
        setView('editor');
        exitLogMode();
        state.editor.setPosition({ lineNumber: targetLine, column: 1 });
        smoothRevealLine(state.editor, targetLine);
        state.editor.focus();
        return;
    }
    if (!state.monaco) {
        state.pendingFile = path;
        state.pendingLine = targetLine;
        state.pendingLogMode = false;
        state.pendingSnippet = null;
        setView('editor');
        return;
    }
    openFileInEditor(path, { line: targetLine });
}

export function toggleExplorerSearch(forceClose) {
    if (!state.explorerTree || !state.explorerSearchResults) return;
    if (state.explorerSearchActive || forceClose) {
        state.explorerSearchActive = false;
        if (state.explorerSearchTimer) { clearTimeout(state.explorerSearchTimer); state.explorerSearchTimer = null; }
        state.explorerSearchBox.classList.remove('open');
        if (state.btnExplorerSearch) state.btnExplorerSearch.classList.remove('hide');
        state.explorerSearchInput.value = '';
        const fadeOut = state.explorerSearchResults.animate(
            [{ opacity: 1 }, { opacity: 0 }],
            { duration: 150, easing: 'ease', fill: 'forwards' }
        );
        fadeOut.onfinish = () => {
            fadeOut.cancel();
            state.explorerSearchResults.classList.add('hidden');
            state.explorerSearchResults.innerHTML = '';
            state.explorerTree.classList.remove('hidden');
            state.explorerTree.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease' });
        };
    } else {
        state.explorerSearchActive = true;
        state.explorerSearchBox.classList.add('open');
        if (state.btnExplorerSearch) state.btnExplorerSearch.classList.add('hide');
        const fadeOut = state.explorerTree.animate(
            [{ opacity: 1 }, { opacity: 0 }],
            { duration: 150, easing: 'ease', fill: 'forwards' }
        );
        fadeOut.onfinish = () => {
            fadeOut.cancel();
            state.explorerTree.classList.add('hidden');
            state.explorerSearchResults.classList.remove('hidden');
            state.explorerSearchResults.innerHTML = '<div class="explorer-loading">Digite para buscar no código...</div>';
            state.explorerSearchResults.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease' });
            if (state.explorerSearchInput) state.explorerSearchInput.focus();
        };
    }
}

export function performExplorerSearch(termo) {
    const term = (termo || '').trim();
    if (!state.explorerSearchResults) return;
    if (!term) {
        state.explorerSearchResults.innerHTML = '<div class="explorer-loading">Digite para buscar no código...</div>';
        return;
    }
    const myToken = ++state.explorerSearchPromise;
    state.explorerSearchResults.innerHTML = '<div class="explorer-loading">buscando...</div>';
    fetch(state.API + '/api/search_files?termo=' + encodeURIComponent(term))
        .then(r => r.json())
        .then(data => {
            if (myToken !== state.explorerSearchPromise) return;
            renderExplorerSearchResults(data.results || [], term);
        })
        .catch(e => {
            if (myToken !== state.explorerSearchPromise) return;
            state.explorerSearchResults.innerHTML = '<div class="explorer-loading term-err">' + e.message + '</div>';
        });
}

export function renderExplorerSearchResults(results, termo) {
    if (!state.explorerSearchResults) return;
    state.explorerSearchResults.innerHTML = '';
    if (!results.length) {
        const empty = document.createElement('div');
        empty.className = 'explorer-loading';
        empty.textContent = 'Nenhuma ocorrência encontrada para "' + termo + '".';
        state.explorerSearchResults.appendChild(empty);
        return;
    }
    const termoLower = termo.toLowerCase();
    const muitosArquivos = results.length > 6;
    const frag = document.createDocumentFragment();
    results.forEach(r => {
        const manyHits = r.total > 6;
        frag.appendChild(createSearchResultCard(r, termoLower, muitosArquivos || manyHits));
    });
    state.explorerSearchResults.appendChild(frag);
}

export function createSearchResultCard(r, termoLower, collapsedByDefault) {
    const card = document.createElement('div');
    card.className = 'esc-card';

    const header = document.createElement('div');
    header.className = 'esc-file';

    const chevron = document.createElement('span');
    chevron.className = 'esc-chevron';

    const name = document.createElement('span');
    name.className = 'esc-file-name';
    name.textContent = r.arquivo;
    name.title = r.arquivo;

    const count = document.createElement('span');
    count.className = 'esc-file-count';
    count.textContent = r.total + (r.total === 1 ? ' ocorrência' : ' ocorrências');

    header.appendChild(chevron);
    header.appendChild(name);
    header.appendChild(count);

    const hits = document.createElement('div');
    hits.className = 'esc-hits';

    r.ocorrencias.forEach(o => {
        const hit = document.createElement('div');
        hit.className = 'esc-hit';
        const line = document.createElement('span');
        line.className = 'esc-hit-line';
        line.textContent = o.linha;
        const txt = document.createElement('span');
        txt.className = 'esc-hit-text';
        appendSearchHighlight(txt, o.trecho, o.destaque || termoLower);
        hit.appendChild(line);
        hit.appendChild(txt);
        hit.title = 'Abrir ' + r.arquivo + ' na linha ' + o.linha;
        hit.addEventListener('click', () => {
            openFileAtLine(r.arquivo, o.linha);
        });
        hits.appendChild(hit);
    });

    let collapsed = !!collapsedByDefault;
    function applyState() {
        hits.style.display = collapsed ? 'none' : '';
        chevron.textContent = collapsed ? '+' : '−';
    }
    header.addEventListener('click', () => {
        collapsed = !collapsed;
        applyState();
    });

    card.appendChild(header);
    card.appendChild(hits);
    applyState();
    return card;
}

export function appendSearchHighlight(container, text, alvo) {
    const termo = String(alvo || '').toLowerCase();
    const idx = termo ? String(text).toLowerCase().indexOf(termo) : -1;
    if (idx === -1) {
        container.textContent = text;
        return;
    }
    container.appendChild(document.createTextNode(text.slice(0, idx)));
    const match = document.createElement('span');
    match.className = 'esc-match';
    match.textContent = text.slice(idx, idx + termo.length);
    container.appendChild(match);
    container.appendChild(document.createTextNode(text.slice(idx + termo.length)));
}

if ('requestIdleCallback' in window) {
    requestIdleCallback(preloadMonaco, { timeout: 3000 });
    requestIdleCallback(preloadTerminal, { timeout: 4000 });
} else {
    setTimeout(preloadMonaco, 1200);
    setTimeout(preloadTerminal, 1500);
}

export function getView() {
    return state.currentView;
}

state.btnPreview.addEventListener('click', () => {
    if (state.currentView === 'preview') {
        fecharPreview();
    } else {
        setView('preview');
    }
});
state.termInput.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const cmd = state.termInput.value.trim();
    if (!cmd) return;
    state.termInput.value = '';
    if (cmd === 'clear' || cmd === 'cls') {
        clearLog();
        return;
    }
    if (state.shellAtivo || /^cd\b/i.test(cmd)) {
        runCommand(cmd);
        return;
    }
    if (temCardSelecionado()) {
        escreverNoCardSelecionado(cmd);
        return;
    }
    lancarComando(cmd);
});

export function loadVenvName() {
    fetch(state.API + '/api/env_info')
        .then(r => r.json())
        .then(data => {
            state.venvDetected = !!(data && data.venv_name);
            if (state.termVenvName) state.termVenvName.textContent = (data && data.venv_name) || '';
            if (data && data.shell) aplicarShellAtual(data.shell);
        })
        .catch(() => {});
}
export function showVenvPopup() {
    const popup = document.getElementById('term-venv-popup');
    if (!popup) return;
    popup.classList.add('visible');
    if (state.venvPopupTimer) clearTimeout(state.venvPopupTimer);
    state.venvPopupTimer = setTimeout(() => popup.classList.remove('visible'), 2600);
}
export function toggleVenv() {
    if (!state.venvDetected) {
        collapseVenv();
        showVenvPopup();
        return;
    }
    state.venvExpanded = !state.venvExpanded;
    if (state.termVenvName) state.termVenvName.classList.toggle('expanded', state.venvExpanded);
    if (state.termPromptArrow) state.termPromptArrow.textContent = state.venvExpanded ? '<' : '>';
}
export function collapseVenv() {
    if (!state.venvExpanded) return;
    state.venvExpanded = false;
    if (state.termVenvName) state.termVenvName.classList.remove('expanded');
    if (state.termPromptArrow) state.termPromptArrow.textContent = '>';
}

if (state.termPromptArrow) {
    state.termPromptArrow.addEventListener('click', toggleVenv);
}
if (state.termVenvName) {
    state.termVenvName.style.cursor = 'pointer';
    state.termVenvName.title = 'Ambiente virtual';
    state.termVenvName.addEventListener('click', toggleVenv);
}
loadVenvName();

if (state.btnDockRight) {
    state.btnDockRight.addEventListener('click', () => {
        const goingRight = state.dockSide !== 'right';
        state.dockSide = goingRight ? 'right' : 'bottom';
        applyDockLayout();
        animateDock(goingRight ? 'right' : 'bottom');
        persistDockPrefs();
    });
}

if (state.btnTrash) {
    state.btnTrash.addEventListener('click', (e) => {
        e.stopPropagation();
        closeFsContextMenu();
        if (state.trashPurgeMode) { doPurgeTrash(); return; }
        if (state.trashOpen) closeTrash(); else openTrash();
    });
}

if (state.trashView) {
    state.trashView.addEventListener('click', () => setLimpezaLixeira(true));
}

document.addEventListener('click', (e) => {
    if (!state.trashPurgeMode) return;
    if (state.trashView && state.trashView.contains(e.target)) return;
    if (state.btnTrash && state.btnTrash.contains(e.target)) return;
    setLimpezaLixeira(false);
}, true);

if (state.btnLineNumbers) {
    state.btnLineNumbers.addEventListener('click', () => {
        fadeGutterSwap(() => {
            state.showLineNumbers = !state.showLineNumbers;
            applyLineGutterState();
            updateLineNumbersButton();
        });
    });
}

if (state.btnCreateFile) {
    state.btnCreateFile.addEventListener('click', () => {
        createFs('file');
    });
}


if (state.btnExplorerSearch) {
    state.btnExplorerSearch.addEventListener('click', () => {
        toggleExplorerSearch();
    });
}
if (state.explorerSearchLupa) {
    state.explorerSearchLupa.addEventListener('click', () => {
        if (state.explorerSearchActive) toggleExplorerSearch(true);
    });
}
if (state.explorerSearchInput) {
    state.explorerSearchInput.addEventListener('input', () => {
        clearTimeout(state.explorerSearchTimer);
        state.explorerSearchTimer = setTimeout(() => performExplorerSearch(state.explorerSearchInput.value), 250);
    });
    state.explorerSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            toggleExplorerSearch(true);
        }
    });
}

if (state.fsContextMenu) {
    state.fsContextMenu.querySelectorAll('button[data-fs-ctx]').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.dataset.fsCtx;
            const target = state.fsContextTarget;
            const trashId = state.fsContextTrashId;
            closeFsContextMenu();
            if (action === 'file') createFs('file');
            else if (action === 'dir') createFs('dir');
            else if (action === 'rename' && target) startRename(target, findExplorerRow(target));
            else if (action === 'delete' && target) openFsConfirm('Excluir "' + basename(target) + '"? Ele será movido para a lixeira.', () => trashPath(target));
            else if (action === 'restore' && trashId) {
                state.trashSelectedId = trashId;
                state.trashSelectedName = null;
                doRestoreTrash();
            } else if (action === 'purge' && trashId) {
                state.trashSelectedId = trashId;
                state.trashSelectedName = basename(trashId);
                openFsConfirm('Excluir definitivamente "' + basename(trashId) + '"? Irá para a Lixeira do Windows.', doDeleteTrashPermanent);
            }
        });
    });
}

if (state.explorerTree) {
    state.explorerTree.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        const row = e.target.closest('.explorer-row');
        const path = row ? row.dataset.path : null;
        const tipo = row ? row.dataset.tipo : null;
        if (path) selectEntry(path, tipo);
        openFsContextMenu(e.clientX, e.clientY, path);
    });
}

export function openFsContextMenu(x, y, path, trashId) {
    if (!state.fsContextMenu) return;
    state.fsContextTarget = path || null;
    state.fsContextTrashId = trashId || null;
    const isTrash = !!state.fsContextTrashId;
    const hasTarget = !!state.fsContextTarget;
    const renameBtn = state.fsContextMenu.querySelector('#fs-ctx-rename');
    const deleteBtn = state.fsContextMenu.querySelector('#fs-ctx-delete');
    const restoreBtn = state.fsContextMenu.querySelector('#fs-ctx-restore');
    const purgeBtn = state.fsContextMenu.querySelector('#fs-ctx-purge');
    if (renameBtn) renameBtn.classList.toggle('hidden', !hasTarget);
    if (deleteBtn) deleteBtn.classList.toggle('hidden', !hasTarget);
    if (restoreBtn) restoreBtn.classList.toggle('hidden', !isTrash);
    if (purgeBtn) purgeBtn.classList.toggle('hidden', !isTrash);
    state.fsContextMenu.style.left = Math.max(8, Math.min(x, window.innerWidth - 210)) + 'px';
    state.fsContextMenu.style.top = Math.max(8, Math.min(y, window.innerHeight - 220)) + 'px';
    state.fsContextMenu.classList.add('menu-open');
}
export function closeFsContextMenu() {
    if (state.fsContextMenu) state.fsContextMenu.classList.remove('menu-open');
    state.fsContextTarget = null;
}

document.addEventListener('click', (e) => {
    if (state.fsContextMenu && !state.fsContextMenu.contains(e.target)) {
        closeFsContextMenu();
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (state.fsContextMenu && state.fsContextMenu.classList.contains('menu-open')) { closeFsContextMenu(); return; }
        if (state.renameTarget) return;
        if (state.currentView === 'editor') {
            const suggestOpen = document.querySelector('.suggest-widget.visible, .monaco-editor .suggest-widget.visible');
            if (!suggestOpen) {
                if (state.currentFile) closeActiveTab();
            }
        }
    } else if (e.key === 'Delete') {
        const tag = (document.activeElement && document.activeElement.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        if (state.trashSelectedId) {
            openFsConfirm('Excluir definitivamente "' + (state.trashSelectedName || basename(state.trashSelectedId)) + '"? Irá para a Lixeira do Windows.', doDeleteTrashPermanent);
            return;
        }
        if (state.selectedPath) {
            doTrashSelected();
        }
    }
}, true);

const DOCK_PREFS_KEY = 'axio-dock-prefs';

export function persistDockPrefs() {
    try {
        localStorage.setItem(DOCK_PREFS_KEY, JSON.stringify({ side: state.dockSide, size: state.explorerSize }));
    } catch (e) {}
}

export function initDockPrefs() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(DOCK_PREFS_KEY) || 'null'); } catch (e) {}
    if (!saved || typeof saved !== 'object') return;
    if (saved.side === 'right' || saved.side === 'bottom') state.dockSide = saved.side;
    const tamanho = parseInt(saved.size, 10);
    if (!isNaN(tamanho)) state.explorerSize = Math.max(80, Math.min(700, tamanho));
}

export function applyDockTheme(theme) {
    if (theme !== 'espacial') theme = 'dark';
    document.body.classList.toggle('theme-espacial', theme === 'espacial');
    try { localStorage.setItem('axio-dock-theme', theme); } catch (e) {}
}
export function initDockTheme() {
    let saved = null;
    try { saved = localStorage.getItem('axio-dock-theme'); } catch (e) {}
    if (saved === 'espacial' || saved === 'dark') {
        applyDockTheme(saved);
    }
    try {
        const { ipcRenderer } = require('electron');
        ipcRenderer.on('menu:set-tema', (e, tema) => applyDockTheme(tema));
        if (saved) ipcRenderer.send('tema:set', saved);
    } catch (e) {}
}

initDockTheme();
initDockPrefs();

applyDockLayout();
initExplorerResizer();


export function scheduleEditorLayout() {
    if (state.resizeLayoutRaf !== null) return;
    state.resizeLayoutRaf = requestAnimationFrame(() => {
        state.resizeLayoutRaf = null;
        layoutAllEditors();
    });
}
window.addEventListener('resize', scheduleEditorLayout);

if (typeof ResizeObserver !== 'undefined' && state.editorHost) {
    state.editorVigia = new ResizeObserver(scheduleEditorLayout);
    state.editorVigia.observe(state.editorHost);
}

export function mountLogDockIntoWorkspace() {
    const logDock = document.getElementById('log-dock');
    const panelCol2 = document.getElementById('panel-col-2');
    if (!logDock) return;

    if (panelCol2 && panelCol2.parentNode !== logDock) {
        logDock.appendChild(panelCol2);
    }

    const editorHostWrap = document.getElementById('editor-host-wrap');
    ['panel-col-3', 'panel-col-3-history', 'panel-col-3-notes'].forEach((id) => {
        const camada = document.getElementById(id);
        if (camada && editorHostWrap && camada.parentNode !== editorHostWrap) {
            editorHostWrap.appendChild(camada);
        }
    });
}

mountLogDockIntoWorkspace();
