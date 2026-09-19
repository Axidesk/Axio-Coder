import { abrirDoc, activate, collapseDockForFocus, expandDockForFocus, getView, handleSSE, isDockCollapsedForFocus, loadVenvName, openFileAtLine, openFileFromLog, preloadMonaco, setActive, setTopBarHidden, showEditor, transferirDaCamada } from './workspace.js';
import { focarAba, renderTabs, revealAndSelectFile, revealPath, updateExplorerToolbar } from './editor.js';
import { alternarDoc, currentDir, fecharPreview, reloadExplorer, selectEntry, setView } from './explorer.js';
import { appendLine } from './terminal.js';
import { ensureTerminal, termFit } from './xterm.js';
import { updateEditorWatermark } from './monaco.js';
import { setFocusMode } from './diff.js';
import { state } from './state.js';

const RECUO_DA_NAVEGACAO_MS = 1200;

export function fadeEditorSwap(apply) {
    if (!state.editorHost) { apply(); return; }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        apply();
        return;
    }
    state.editorHost.getAnimations().forEach(a => a.cancel());
    const out = state.editorHost.animate(
        [{ opacity: 1 }, { opacity: 0 }],
        { duration: 140, easing: 'ease', fill: 'forwards' }
    );
    out.onfinish = function () {
        out.cancel();
        apply();
        state.editorHost.animate(
            [{ opacity: 0 }, { opacity: 1 }],
            { duration: 220, easing: 'ease' }
        );
    };
}
export function fadeEditorIn() {
    if (!state.editorHost) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    state.editorHost.getAnimations().forEach(a => a.cancel());
    state.editorHost.animate(
        [{ opacity: 0 }, { opacity: 1 }],
        { duration: 220, easing: 'ease' }
    );
}
export function getEditorMargin() {
    if (!state.editor) return null;
    const dom = state.editor.getDomNode();
    return dom ? dom.querySelector('.margin') : null;
}
export function getScrollableElement() {
    if (!state.editor) return null;
    const dom = state.editor.getDomNode();
    return dom ? dom.querySelector('.monaco-scrollable-element') : null;
}
export function fadeGutterSwap(apply) {
    if (!state.editor) { apply(); return; }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        apply();
        return;
    }
    const margin = getEditorMargin();
    const scrollable = getScrollableElement();
    if (!margin || !scrollable) {
        apply();
        return;
    }

    margin.getAnimations().forEach(a => a.cancel());
    scrollable.getAnimations().forEach(a => a.cancel());
    margin.style.opacity = '';
    scrollable.style.transform = '';

    const beforeLeft = scrollable.getBoundingClientRect().left;
    const out = margin.animate(
        [{ opacity: 1 }, { opacity: 0 }],
        { duration: 100, easing: 'ease', fill: 'forwards' }
    );
    out.onfinish = function () {
        out.cancel();
        margin.style.opacity = '0';
        apply();
        if (state.editor) state.editor.layout();
        const afterLeft = scrollable.getBoundingClientRect().left;
        const delta = afterLeft - beforeLeft;

        if (Math.abs(delta) >= 0.5) {
            scrollable.style.transform = 'translateX(' + (-delta) + 'px)';
            void scrollable.offsetWidth;
            const slide = scrollable.animate(
                [{ transform: 'translateX(' + (-delta) + 'px)' }, { transform: 'translateX(0px)' }],
                { duration: 180, easing: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)', fill: 'forwards' }
            );
            slide.onfinish = function () {
                slide.cancel();
                scrollable.style.transform = '';
                fadeGutterIn();
            };
        } else {
            fadeGutterIn();
        }
    };

    function fadeGutterIn() {
        margin.getAnimations().forEach(a => a.cancel());
        margin.style.opacity = '0';
        const inn = margin.animate(
            [{ opacity: 0 }, { opacity: 1 }],
            { duration: 160, easing: 'ease', fill: 'forwards' }
        );
        inn.onfinish = function () {
            inn.cancel();
            margin.style.opacity = '';
        };
    }
}
export function smoothScrollEditor(ed, targetTop, duration) {
    if (!ed) return;
    const token = ++state.scrollAnimToken;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        ed.setScrollTop(targetTop, state.monaco.editor.ScrollType.Immediate);
        return;
    }
    const startTop = ed.getScrollTop();
    const delta = targetTop - startTop;
    if (Math.abs(delta) < 2) return;
    const dur = duration || 600;
    const start = performance.now();
    function frame(now) {
        if (token !== state.scrollAnimToken) return;
        const t = Math.min(1, (now - start) / dur);
        const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        ed.setScrollTop(startTop + delta * eased, state.monaco.editor.ScrollType.Immediate);
        if (t < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
}
export function isEditorLineVisible(ed, targetLine) {
    if (!ed || !targetLine || targetLine < 1) return true;
    const layout = ed.getLayoutInfo();
    const scrollTop = ed.getScrollTop();
    const MARGEM = 40;
    const lineTop = ed.getTopForLineNumber(targetLine);
    const lineBottom = ed.getTopForLineNumber(targetLine + 1);
    return lineTop >= scrollTop + MARGEM && lineBottom <= scrollTop + layout.height - MARGEM;
}
export function smoothRevealLine(ed, targetLine, duration) {
    if (!ed) return;
    if (isEditorLineVisible(ed, targetLine)) return;
    const layout = ed.getLayoutInfo();
    const targetTop = ed.getTopForLineNumber(targetLine) - (layout.height / 2);
    smoothScrollEditor(ed, targetTop, duration);
}
export function revelarLinhaComRolagem(ed, linha, duration) {
    if (!ed || !linha) return;
    requestAnimationFrame(function () {
        requestAnimationFrame(function () {
            if (!ed) return;
            ed.layout();
            const layout = ed.getLayoutInfo();
            const top = ed.getTopForLineNumber(linha) - (layout.height / 2);
            if (!isFinite(top)) return;
            smoothScrollEditor(ed, Math.max(0, top), duration || 600);
        });
    });
}
export function saveFile() {
    if (!state.editor || !state.currentFile || state.currentFileIsImage) return;
    fetch(state.API + '/api/file_save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caminho: state.currentFile, conteudo: state.editor.getValue() })
    })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                appendLine('[editor] ' + data.error, 'term-err');
                state.wsStatus.textContent = 'editor: erro ao salvar';
                return;
            }
            state.wsStatus.textContent = 'salvo: ' + state.currentFile;
        })
        .catch(e => {
            appendLine('[editor] erro: ' + e.message, 'term-err');
        });
}
export function scheduleAutoSave() {
    if (state.suppressAutoSave || !state.currentFile || state.currentFileIsImage) return;
    if (state.autoSaveTimer) clearTimeout(state.autoSaveTimer);
    state.autoSaveTimer = setTimeout(() => {
        state.autoSaveTimer = null;
        saveFile();
    }, 600);
}

export async function createFileFromTyping() {
    const dir = currentDir();
    const caminho = dir ? dir + '/Novo Ficheiro' : 'Novo Ficheiro';
    try {
        const resp = await fetch(state.API + '/api/fs_create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminho: caminho, tipo: 'file' })
        });
        const data = await resp.json();
        if (data.error) {
            appendLine('[editor] ' + data.error, 'term-err');
            return;
        }
        await reloadExplorer();
        await revealPath(data.caminho);
        selectEntry(data.caminho, 'file');
        state.currentFile = data.caminho;
        state.typingCreatedFile = data.caminho;
        if (!state.openTabs.includes(data.caminho)) state.openTabs.push(data.caminho);
        renderTabs();
        updateEditorWatermark();
        saveFile();
    } catch (e) {
        appendLine('[editor] erro: ' + e.message, 'term-err');
    }
}

export function scheduleExplorerReload() {
    if (state.explorerReloadTimer) clearTimeout(state.explorerReloadTimer);
    state.explorerReloadTimer = setTimeout(() => {
        state.explorerReloadTimer = null;
        if (Date.now() - state.explorerNavigatedAt < RECUO_DA_NAVEGACAO_MS) {
            scheduleExplorerReload();
            return;
        }
        if (typeof reloadExplorer === 'function') reloadExplorer();
    }, 250);
}

window.WorkspaceView = {
    activate: activate,
    ensureTerminal: ensureTerminal,
    fitTerminal: termFit,
    onSSE: handleSSE,
    setActive: setActive,
    setTopBarHidden: setTopBarHidden,
    reloadExplorer: reloadExplorer,
    loadVenvName: loadVenvName,
    openFileFromLog: openFileFromLog,
    openFileAtLine: openFileAtLine,
    revealAndSelectFile: revealAndSelectFile,
    focarAba: focarAba,
    transferirDaCamada: transferirDaCamada,
    setFocusMode: setFocusMode,
    setView: setView,
    fecharPreview: fecharPreview,
    alternarDoc: alternarDoc,
    abrirDoc: abrirDoc,
    showEditor: showEditor,
    getView: getView,
    preloadMonaco: preloadMonaco,
    collapseDockForFocus: collapseDockForFocus,
    expandDockForFocus: expandDockForFocus,
    isDockCollapsedForFocus: isDockCollapsedForFocus
};

updateExplorerToolbar();
setView('chat');
