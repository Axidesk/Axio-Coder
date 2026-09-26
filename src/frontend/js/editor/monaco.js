import { opcoesBase } from './metricas.js';
import { defineEditorTheme, defineLogTheme } from './themes.js';
import { installEditorHoverHighlight, installUrlWordSelection } from './highlight.js';
import { installFindToggle, wireMonacoFindPush } from './findbar.js';
import { instalarDestaqueCsv } from './destacar_csv.js';
import { instalarPontosDeParagem } from './pontos_paragem.js';
import { refreshErrorMarkers } from './explorer.js';
import { createFileFromTyping, scheduleAutoSave } from './scroll.js';
import { appendLine } from './terminal.js';
import { trashPath } from './editor.js';
import { state } from './state.js';

export function initMonaco(cb) {
    if (window.monaco) { cb(); return; }
    if (cb) state.monacoInitQueue.push(cb);
    if (state.monacoLoading) return;
    state.monacoLoading = true;
    const nodeRequire = window.require;
    try { self.module = undefined; } catch (e) {}
    try { self.process.browser = true; } catch (e) {}
    const script = document.createElement('script');
    script.src = state.API + '/monaco/vs/loader.js';
    script.onload = function () {
        const amdRequire = window.require;
        window.require = nodeRequire;
        amdRequire.config({ paths: { vs: state.API + '/monaco/vs' }, preferScriptTags: true });
        amdRequire(['vs/editor/editor.main'], function () {
            state.monacoLoading = false;
            flushMonacoQueue();
        }, function (err) {
            appendLine('[editor] falha ao carregar editor.main: ' + (err && err.message ? err.message : err), 'term-err');
            state.monacoLoading = false;
            state.monacoInitQueue.length = 0;
        });
    };
    script.onerror = function () {
        appendLine('[editor] falha ao carregar o Monaco', 'term-err');
        state.monacoLoading = false;
        state.monacoInitQueue.length = 0;
    };
    document.head.appendChild(script);
}
export function flushMonacoQueue() {
    const cbs = state.monacoInitQueue.splice(0);
    cbs.forEach(function (fn) {
        try { fn(); } catch (e) { console.error(e); }
    });
}
export function ensureEditor() {
    if (state.editor) return;
    if (!state.monaco) return;
    defineEditorTheme();
    defineLogTheme();
    state.editor = state.monaco.editor.create(state.editorHost, Object.assign(opcoesBase(), {
        value: '',
        language: 'plaintext',
        theme: 'axio-editor',
        automaticLayout: false,
        lineNumbers: 'off',
        lineNumbersMinChars: 0,
        glyphMargin: false,
        lineDecorationsWidth: 0,
        folding: true,
        bracketPairColorization: { enabled: false },
        highlightActiveIndentGuide: false,
        renderIndentGuides: false,
        overviewRulerLanes: 3,
        overviewRulerBorder: false,
        find: { addExtraSpaceOnTop: false }
    }));
    state.monaco.editor.onDidChangeMarkers(refreshErrorMarkers);
    state.editor.onDidChangeModelContent(() => {
        if (state.suppressAutoSave) return;
        if (!state.currentFile) {
            if (state.editor.getValue().trim() === '') return;
            if (!state.creatingFromTyping) {
                state.creatingFromTyping = true;
                createFileFromTyping().finally(() => { state.creatingFromTyping = false; });
            }
            return;
        }
        scheduleAutoSave();
        if (state.currentFile === state.typingCreatedFile && state.editor.getValue().trim() === '') {
            const p = state.typingCreatedFile;
            state.typingCreatedFile = null;
            trashPath(p);
        }
    });
    installEditorHoverHighlight();
    installUrlWordSelection();
    wireMonacoFindPush(state.editorHost);
    wireMonacoFindPush(state.diffHost);
    installFindToggle();
    instalarDestaqueCsv();
    instalarPontosDeParagem();
    updateEditorWatermark();
}
export function updateEditorWatermark() {
    if (!state.editorWatermark) return;
    const hasFile = !!state.currentFile;
    if (hasFile) {
        state.editorWatermark.classList.add('editor-watermark-hidden');
    } else {
        state.editorWatermark.classList.remove('editor-watermark-hidden');
    }
}
