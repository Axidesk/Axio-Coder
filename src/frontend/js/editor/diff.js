import { getLanguage } from './explorer.js';
import { fadeEditorIn, smoothScrollEditor } from './scroll.js';
import { clearHoverLineFor, installHoverHighlightFor } from './highlight.js';
import { opcoesBase, RECUO_COLUNA_DIREITA, RECUO_LATERAL } from './metricas.js';
import { defineDiffTheme } from './themes.js';
import { state } from './state.js';

export function computeLineDiff(originalText, modifiedText) {
    const a = String(originalText || '').split('\n');
    const b = String(modifiedText || '').split('\n');
    const deletedLines = [];
    const addedLines = [];
    const N = a.length;
    const M = b.length;
    const origToMod = new Array(N + 1).fill(null);
    const modToOrig = new Array(M + 1).fill(null);
    let prefix = 0;
    while (prefix < N && prefix < M && a[prefix] === b[prefix]) prefix++;
    const MAX_CELLS = 3000000;
    if (N * M > MAX_CELLS) {
        let endA = N;
        let endB = M;
        while (endA > prefix && endB > prefix && a[endA - 1] === b[endB - 1]) {
            endA--;
            endB--;
        }
        for (let i = prefix + 1; i <= endA; i++) deletedLines.push(i);
        for (let i = prefix + 1; i <= endB; i++) addedLines.push(i);
        for (let k = 1; k <= prefix; k++) { origToMod[k] = k; modToOrig[k] = k; }
        for (let k = 0; k < N - endA; k++) {
            origToMod[endA + 1 + k] = endB + 1 + k;
            modToOrig[endB + 1 + k] = endA + 1 + k;
        }
        return { deletedLines, addedLines, origToMod, modToOrig, anchorLine: prefix };
    }
    const dp = new Array(N + 1);
    for (let i = 0; i <= N; i++) dp[i] = new Uint32Array(M + 1);
    for (let i = N - 1; i >= 0; i--) {
        const row = dp[i];
        const nextRow = dp[i + 1];
        const ai = a[i];
        for (let j = M - 1; j >= 0; j--) {
            row[j] = (ai === b[j]) ? nextRow[j + 1] + 1 : (nextRow[j] >= row[j + 1] ? nextRow[j] : row[j + 1]);
        }
    }
    let i = 0;
    let j = 0;
    while (i < N && j < M) {
        if (a[i] === b[j]) {
            origToMod[i + 1] = j + 1;
            modToOrig[j + 1] = i + 1;
            i++;
            j++;
        } else if (dp[i + 1][j] >= dp[i][j + 1]) {
            deletedLines.push(i + 1);
            i++;
        } else {
            addedLines.push(j + 1);
            j++;
        }
    }
    while (i < N) {
        deletedLines.push(i + 1);
        i++;
    }
    while (j < M) {
        addedLines.push(j + 1);
        j++;
    }
    return { deletedLines, addedLines, origToMod, modToOrig, anchorLine: prefix };
}
export function syncDiffScrollFrom(source, target) {

    if (state.diffScrollSyncing || !source || !target) return;
    const esquerda = source.getScrollLeft();
    const topo = source.getScrollTop();
    const moverX = Math.abs(target.getScrollLeft() - esquerda) >= 0.5;
    const moverY = Math.abs(target.getScrollTop() - topo) >= 0.5;
    if (!moverX && !moverY) return;
    state.diffScrollSyncing = true;
    try {
        if (moverX) target.setScrollLeft(esquerda, state.monaco.editor.ScrollType.Immediate);
        if (moverY) target.setScrollTop(topo, state.monaco.editor.ScrollType.Immediate);
    } finally {
        state.diffScrollSyncing = false;
    }
}
export function installDiffScrollSync() {
    disposeDiffScrollSync();
    if (!state.diffOriginalEditor || !state.diffModifiedEditor) return;
    state.diffScrollDisposables.push(state.diffOriginalEditor.onDidScrollChange(() => {
        syncDiffScrollFrom(state.diffOriginalEditor, state.diffModifiedEditor);
    }));
    state.diffScrollDisposables.push(state.diffModifiedEditor.onDidScrollChange(() => {
        syncDiffScrollFrom(state.diffModifiedEditor, state.diffOriginalEditor);
    }));
}
export function disposeDiffScrollSync() {
    state.diffScrollDisposables.forEach(d => { try { d.dispose(); } catch (e) {} });
    state.diffScrollDisposables = [];
}
export function decorateDiffSide(ed, changedLines, highlightCls) {
    if (!ed) return [];
    const model = ed.getModel();
    if (!model) return [];
    const total = model.getLineCount();
    const dim = 'monaco-dim-text';
    const decos = [];
    if (total === 0) return [];
    if (!changedLines || changedLines.length === 0) {
        decos.push({ range: new state.monaco.Range(1, 1, total, model.getLineMaxColumn(total)), options: { inlineClassName: dim } });
        return decos;
    }
    const changed = new Set(changedLines);
    let segStart = 1;
    for (let line = 1; line <= total; line++) {
        if (changed.has(line)) {
            if (segStart < line) {
                decos.push({ range: new state.monaco.Range(segStart, 1, line - 1, model.getLineMaxColumn(line - 1)), options: { inlineClassName: dim } });
            }
            segStart = line + 1;
        }
    }
    if (segStart <= total) {
        decos.push({ range: new state.monaco.Range(segStart, 1, total, model.getLineMaxColumn(total)), options: { inlineClassName: dim } });
    }
    changed.forEach(line => {
        if (line >= 1 && line <= total) {
            decos.push({ range: new state.monaco.Range(line, 1, line, model.getLineMaxColumn(line)), options: { inlineClassName: highlightCls } });
        }
    });
    return decos;
}
export function applyDiffLineDecorations(originalText, modifiedText, precomputedDiff) {
    if (!state.diffOriginalEditor || !state.diffModifiedEditor) return null;
    const diff = precomputedDiff || computeLineDiff(originalText, modifiedText);
    state.diffOriginalDecorations = state.diffOriginalEditor.deltaDecorations(state.diffOriginalDecorations, decorateDiffSide(state.diffOriginalEditor, diff.deletedLines, 'monaco-diff-deleted-text'));
    state.diffModifiedDecorations = state.diffModifiedEditor.deltaDecorations(state.diffModifiedDecorations, decorateDiffSide(state.diffModifiedEditor, diff.addedLines, 'monaco-diff-added-text'));
    return diff;
}
export function computeHiddenRanges(totalLines, changedLines, model) {
    if (!totalLines || totalLines <= 0) return [];
    const changed = new Set(changedLines || []);
    if (changed.size === 0) return [];
    const ranges = [];
    let start = -1;
    for (let line = 1; line <= totalLines; line++) {
        if (!changed.has(line)) {
            if (start === -1) start = line;
        } else if (start !== -1) {
            ranges.push(new state.monaco.Range(start, 1, line - 1, model ? model.getLineMaxColumn(line - 1) : 1));
            start = -1;
        }
    }
    if (start !== -1) {
        ranges.push(new state.monaco.Range(start, 1, totalLines, model ? model.getLineMaxColumn(totalLines) : 1));
    }
    return ranges;
}
export function applyFocusMode() {
    if (!state.monaco) return;
    if (state.diffMode && state.diffOriginalEditor && state.diffModifiedEditor) {
        const diff = state.currentDiffForFocus || computeLineDiff(state.currentDiffOriginal || '', state.currentDiffModified || '');
        const origModel = state.diffOriginalEditor.getModel();
        const modModel = state.diffModifiedEditor.getModel();
        if (origModel && modModel) {
            if (state.focusMode) {
                state.diffOriginalEditor.setHiddenAreas(computeHiddenRanges(origModel.getLineCount(), diff.deletedLines, origModel));
                state.diffModifiedEditor.setHiddenAreas(computeHiddenRanges(modModel.getLineCount(), diff.addedLines, modModel));
            } else {
                state.diffOriginalEditor.setHiddenAreas([]);
                state.diffModifiedEditor.setHiddenAreas([]);
            }
            state.diffOriginalEditor.layout();
            state.diffModifiedEditor.layout();
        }
    } else if (state.logMode && state.editor) {
        const model = state.editor.getModel();
        if (model) {
            if (state.focusMode && state.currentLogChangedLines && state.currentLogChangedLines.length) {
                state.editor.setHiddenAreas(computeHiddenRanges(model.getLineCount(), state.currentLogChangedLines, model));
            } else {
                state.editor.setHiddenAreas([]);
            }
            state.editor.layout();
        }
    }
}
export function setFocusMode(enabled) {
    state.focusMode = !!enabled;
    applyFocusMode();
}
function ajustarRecuoLateral() {

    if (state.diffOriginalEditor) {
        state.diffOriginalEditor.updateOptions({ glyphMargin: false, lineDecorationsWidth: RECUO_LATERAL });
    }
    if (state.diffModifiedEditor) {
        state.diffModifiedEditor.updateOptions({ glyphMargin: false, lineDecorationsWidth: RECUO_COLUNA_DIREITA });
    }
}
export function enterDiffMode(originalText, modifiedText, snippet, path, precomputedDiff) {
    if (state.diffMode && path === state.currentDiffPath && originalText === state.currentDiffOriginal && modifiedText === state.currentDiffModified) {
        return;
    }
    state.currentDiffPath = path;
    state.currentDiffOriginal = originalText;
    state.currentDiffModified = modifiedText;
    state.diffMode = true;
    state.logMode = true;
    clearHoverLineFor(state.editor);
    state.logSnippet = snippet || null;
    defineDiffTheme();
    state.monaco.editor.setTheme('axio-diff');
    state.editorHost.classList.add('hidden');
    state.diffHost.classList.remove('hidden');
    if (state.editorImageHost) state.editorImageHost.style.display = 'none';

    if (!state.diffOriginalHost) state.diffOriginalHost = document.getElementById('diff-original-host');
    if (!state.diffModifiedHost) state.diffModifiedHost = document.getElementById('diff-modified-host');

    const sharedOptions = Object.assign(opcoesBase(), {
        readOnly: true,
        automaticLayout: false,
        lineNumbers: 'off',
        lineNumbersMinChars: 0,
        glyphMargin: false,
        folding: false,
        renderIndentGuides: false,
        renderOverviewRuler: false,
        lineDecorationsWidth: RECUO_LATERAL,
        overviewRulerLanes: 0,
        hideCursorInOverviewRuler: true,
        overviewRulerBorder: false,
        theme: 'axio-diff',
        scrollbar: {
            verticalScrollbarSize: 6,
            horizontalScrollbarSize: 6,
            verticalSliderSize: 40,
            horizontalSliderSize: 40,
            arrowSize: 0,
            useShadows: false,
            verticalHasArrows: false,
            horizontalHasArrows: false
        }
    });

    if (!state.diffOriginalEditor) {
        state.diffOriginalEditor = state.monaco.editor.create(state.diffOriginalHost, sharedOptions);
    }
    if (!state.diffModifiedEditor) {

        state.diffModifiedEditor = state.monaco.editor.create(
            state.diffModifiedHost,
            Object.assign({}, sharedOptions, { lineDecorationsWidth: RECUO_COLUNA_DIREITA })
        );
    }
    installHoverHighlightFor(state.diffOriginalEditor);
    installHoverHighlightFor(state.diffModifiedEditor);

    const savedDiff = state.savedDiffScrolls.get(path);
    const validSavedDiff = (savedDiff && savedDiff.original === originalText && savedDiff.modified === modifiedText) ? savedDiff : null;

    const originalModel = state.monaco.editor.createModel(originalText || '', getLanguage(path));
    const modifiedModel = state.monaco.editor.createModel(modifiedText || '', getLanguage(path));
    if (state.currentDiffModels) {
        state.currentDiffModels.original.dispose();
        state.currentDiffModels.modified.dispose();
    }
    state.currentDiffModels = { original: originalModel, modified: modifiedModel };
    state.diffOriginalEditor.setModel(originalModel);
    state.diffModifiedEditor.setModel(modifiedModel);
    state.diffOriginalDecorations = [];
    state.diffModifiedDecorations = [];
    const diffForReveal = applyDiffLineDecorations(originalText, modifiedText, precomputedDiff);
    state.currentDiffForFocus = diffForReveal;

    const topoInicial = validSavedDiff ? validSavedDiff.top : state.diffOriginalEditor.getScrollTop();
    const esquerdaInicial = validSavedDiff ? validSavedDiff.left : state.diffOriginalEditor.getScrollLeft();
    state.diffOriginalEditor.setScrollTop(topoInicial);
    state.diffOriginalEditor.setScrollLeft(esquerdaInicial);
    state.diffModifiedEditor.setScrollTop(topoInicial);
    state.diffModifiedEditor.setScrollLeft(esquerdaInicial);
    ajustarRecuoLateral();
    requestAnimationFrame(() => {
        state.diffOriginalEditor.layout();
        state.diffModifiedEditor.layout();
    });
    installDiffScrollSync();
    applyFocusMode();
}
export function exitDiffMode(suppressFade) {
    if (!state.diffMode && !state.diffOriginalEditor) return;
    const editorWasHidden = state.editorHost.classList.contains('hidden');
    if (state.diffMode && state.diffOriginalEditor && state.diffModifiedEditor && state.currentDiffPath) {
        state.savedDiffScrolls.set(state.currentDiffPath, {
            original: state.currentDiffOriginal,
            modified: state.currentDiffModified,
            top: state.diffOriginalEditor.getScrollTop(),
            left: state.diffOriginalEditor.getScrollLeft()
        });
    }
    state.diffMode = false;
    state.currentDiffPath = null;
    state.currentDiffOriginal = null;
    state.currentDiffModified = null;
    state.currentDiffForFocus = null;
    disposeDiffScrollSync();
    clearHoverLineFor(state.diffOriginalEditor);
    clearHoverLineFor(state.diffModifiedEditor);
    if (state.diffOriginalEditor) {
        state.diffOriginalDecorations = state.diffOriginalEditor.deltaDecorations(state.diffOriginalDecorations, []);
        state.diffOriginalEditor.setHiddenAreas([]);
        state.diffOriginalEditor.setModel(null);
    }
    if (state.diffModifiedEditor) {
        state.diffModifiedDecorations = state.diffModifiedEditor.deltaDecorations(state.diffModifiedDecorations, []);
        state.diffModifiedEditor.setHiddenAreas([]);
        state.diffModifiedEditor.setModel(null);
    }
    state.diffHost.classList.add('hidden');
    if (state.currentDiffModels) {
        state.currentDiffModels.original.dispose();
        state.currentDiffModels.modified.dispose();
        state.currentDiffModels = null;
    }
    state.editorHost.classList.remove('hidden');
    if (state.editorImageHost) state.editorImageHost.style.display = 'none';
    if (state.editor) {
        state.monaco.editor.setTheme('axio-editor');
        state.editor.layout();
    }
    if (editorWasHidden && !suppressFade) {
        fadeEditorIn();
    }
}
export function captureDiffExitScroll() {
    if (!state.diffMode || !state.diffModifiedEditor) return null;
    const model = state.diffModifiedEditor.getModel();
    if (!model) return null;
    const ranges = state.diffModifiedEditor.getVisibleRanges();
    const line = (ranges && ranges.length) ? ranges[0].startLineNumber : 1;
    return {
        line: line,
        top: state.diffModifiedEditor.getScrollTop(),
        left: state.diffModifiedEditor.getScrollLeft()
    };
}
export function revealDiffExitScroll(exitScroll) {
    if (!exitScroll || !state.editor) return;
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (!state.editor) return;
            state.editor.layout();
            state.editor.setPosition({ lineNumber: exitScroll.line, column: 1 });
            smoothScrollEditor(state.editor, exitScroll.top, 600);
            if (exitScroll.left) {
                state.editor.setScrollLeft(exitScroll.left, state.monaco.editor.ScrollType.Smooth);
            }
        });
    });
}
