import { revealSnippet, smoothRevealLine } from './scroll.js';
import { applyFocusMode, decorateDiffSide, exitDiffMode, updateLogToggle } from './diff.js';
import { state } from './state.js';

export function defineEditorTheme() {
    if (state.editorThemeDefined) return;
    state.editorThemeDefined = true;
    state.monaco.editor.defineTheme('axio-editor', {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '8b8b8b', fontStyle: 'italic' },
            { token: 'comment.line', foreground: '8b8b8b', fontStyle: 'italic' },
            { token: 'comment.block', foreground: '8b8b8b', fontStyle: 'italic' },
            { token: 'comment.doc', foreground: '8b8b8b', fontStyle: 'italic' }
        ],
        colors: {
            'editor.background': '#1e1e1e',
            'editor.foreground': '#d4d4d4',
            'editor.lineHighlightBackground': '#2a2a2a',
            'editor.lineHighlightBorder': '#00000000',
            'editor.selectionBackground': '#4a4a4a',
            'editor.inactiveSelectionBackground': '#3a3d41',
            'editor.selectionHighlightBorder': '#00000000',
            'editor.foldBackground': '#00000000',
            'editorCursor.foreground': '#d4d4d4',
            'editorBracketMatch.background': '#00000000',
            'editorBracketMatch.border': '#00000000',
            'editorIndentGuide.background': '#2a2a2a',
            'editorIndentGuide.activeBackground': '#2a2a2a'
        }
    });
}
export function defineLogTheme() {
    if (state.logThemeDefined) return;
    state.logThemeDefined = true;
    state.monaco.editor.defineTheme('axio-log', {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: '', foreground: '6b7280' }
        ],
        colors: {
            'editor.background': '#00000000',
            'editorLineNumber.foreground': '#6b7280',
            'editorLineNumber.activeForeground': '#6b7280',
            'editor.lineHighlightBackground': '#00000000',
            'editor.lineHighlightBorder': '#00000000',
            'editor.selectionBackground': '#00000000',
            'editorCursor.foreground': '#6b7280',
            'editorIndentGuide.background': '#00000000',
            'editorIndentGuide.activeBackground': '#00000000'
        }
    });
}
export function applyLogDecorations(content, snippet) {
    if (!state.editor) return { startLine: -1, endLine: -1 };
    const model = state.editor.getModel();
    if (!model) return { startLine: -1, endLine: -1 };
    const totalLines = model.getLineCount();
    if (totalLines === 0) {
        state.logDecorations = state.editor.deltaDecorations(state.logDecorations, []);
        return { startLine: -1, endLine: -1 };
    }

    let startLine = -1;
    let endLine = -1;
    if (snippet) {
        const firstLine = snippet.split('\n').find(l => l.trim().length > 0);
        if (firstLine) {
            const needle = firstLine.trim();
            const lines = content.split('\n');
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].indexOf(needle) !== -1) {
                    if (startLine === -1) startLine = i + 1;
                    endLine = i + 1;
                }
            }
        }
    }

    const decos = [];
    const dim = 'monaco-dim-text';
    const hit = 'monaco-snippet-text';
    const lastCol = model.getLineMaxColumn(totalLines);

    if (startLine === -1) {
        decos.push({
            range: new state.monaco.Range(1, 1, totalLines, lastCol),
            options: { inlineClassName: dim }
        });
    } else {
        if (startLine > 1) {
            decos.push({
                range: new state.monaco.Range(1, 1, startLine - 1, model.getLineMaxColumn(startLine - 1)),
                options: { inlineClassName: dim }
            });
        }
        decos.push({
            range: new state.monaco.Range(startLine, 1, endLine, model.getLineMaxColumn(endLine)),
            options: { inlineClassName: hit }
        });
        if (endLine < totalLines) {
            decos.push({
                range: new state.monaco.Range(endLine + 1, 1, totalLines, lastCol),
                options: { inlineClassName: dim }
            });
        }
    }

    state.logDecorations = state.editor.deltaDecorations(state.logDecorations, decos);
    return { startLine: startLine, endLine: endLine };
}
export function applyLineGutterState() {
    if (!state.editor) return;
    state.editor.updateOptions({
        lineNumbers: state.showLineNumbers ? 'on' : 'off',
        lineNumbersMinChars: state.showLineNumbers ? 3 : 0,
        glyphMargin: false,
        lineDecorationsWidth: state.showLineNumbers ? 0 : 10,
        folding: true,
        renderIndentGuides: state.showLineNumbers
    });
}
export function updateLineNumbersButton() {
    if (!state.btnLineNumbers) return;
    if (state.showLineNumbers) {
        state.btnLineNumbers.className = 'transition-colors text-[var(--oliva)] hover:text-[var(--oliva-hover)]';
        state.btnLineNumbers.title = 'Ocultar numeração e linhas de identação';
    } else {
        state.btnLineNumbers.className = 'transition-colors text-[var(--text-mutado)] hover:text-[var(--oliva)]';
        state.btnLineNumbers.title = 'Exibir numeração e linhas de identação';
    }
}
export function applyLogEditorOptions() {
    state.editor.updateOptions({
        readOnly: true,
        lineNumbers: state.showLineNumbers ? 'on' : 'off',
        lineNumbersMinChars: state.showLineNumbers ? 3 : 0,
        glyphMargin: false,
        lineDecorationsWidth: state.showLineNumbers ? 0 : 10,
        folding: true,
        renderIndentGuides: state.showLineNumbers,
        renderLineHighlight: 'none',
        minimap: { enabled: false },
        fontSize: 14,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
        scrollBeyondLastLine: false,
        overviewRulerLanes: 0,
        hideCursorInOverviewRuler: true,
        overviewRulerBorder: false,
        renderLineHighlightOnlyWhenFocus: true,
        smoothScrolling: true,
        mouseWheelScrollSensitivity: 1
    });
}
export function enterLogMode(snippet, content) {
    state.logMode = true;
    state.logSnippet = snippet || null;
    exitDiffMode();
    if (!state.editor) return;
    applyLogEditorOptions();
    state.monaco.editor.setTheme('axio-log');
    const range = applyLogDecorations(content || '', snippet);
    const changed = [];
    if (range && range.startLine !== -1) {
        for (let i = range.startLine; i <= range.endLine; i++) changed.push(i);
    }
    state.currentLogChangedLines = changed;
    state.currentLogFocusCls = '';
    applyFocusMode();
    if (snippet && content) {
        requestAnimationFrame(() => revealSnippet(snippet, content));
    }
    updateLogToggle();
}
export function enterLogModeWithLines(changedLines, cls, needsReload) {
    state.logMode = true;
    state.logSnippet = null;
    exitDiffMode();
    if (!state.editor) return;
    applyLogEditorOptions();
    state.monaco.editor.setTheme('axio-log');
    state.logDecorations = state.editor.deltaDecorations(state.logDecorations, decorateDiffSide(state.editor, changedLines, cls));
    state.logModeNeedsReload = !!needsReload;
    state.currentLogChangedLines = changedLines || [];
    state.currentLogFocusCls = cls || '';
    applyFocusMode();
    const firstChanged = (changedLines && changedLines.length) ? changedLines[0] : 1;
    requestAnimationFrame(() => {
        if (state.editor) {
            state.editor.setPosition({ lineNumber: firstChanged, column: 1 });
            smoothRevealLine(state.editor, firstChanged);
        }
    });
    updateLogToggle();
}
export function exitLogMode() {
    state.logMode = false;
    state.logSnippet = null;
    state.currentLogChangedLines = [];
    state.currentLogFocusCls = '';
    state.logModeNeedsReload = false;
    exitDiffMode();
    if (state.editor) {
        state.logDecorations = state.editor.deltaDecorations(state.logDecorations, []);
        state.editor.setHiddenAreas([]);
        state.editor.updateOptions({
            readOnly: false,
            lineNumbers: state.showLineNumbers ? 'on' : 'off',
            lineNumbersMinChars: state.showLineNumbers ? 3 : 0,
            glyphMargin: false,
            lineDecorationsWidth: state.showLineNumbers ? 0 : 10,
            folding: true,
            renderIndentGuides: state.showLineNumbers,
            renderLineHighlight: 'none',
            bracketPairColorization: { enabled: false },
            highlightActiveIndentGuide: false,
            minimap: { enabled: false },
            fontSize: 14,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
            scrollBeyondLastLine: false,
            overviewRulerLanes: 3,
            hideCursorInOverviewRuler: true,
            overviewRulerBorder: false,
            renderLineHighlightOnlyWhenFocus: false
        });
        state.monaco.editor.setTheme('axio-editor');
    }
    updateLogToggle();
}
export function enterReadonlyLogMode() {
    state.logMode = true;
    state.logSnippet = null;
    exitDiffMode();
    if (!state.editor) return;
    applyLogEditorOptions();
    state.monaco.editor.setTheme('axio-editor');
    state.logDecorations = state.editor.deltaDecorations(state.logDecorations, []);
    state.currentLogChangedLines = [];
    state.currentLogFocusCls = '';
    state.logModeNeedsReload = false;
    applyFocusMode();
    updateLogToggle();
}
export function defineDiffTheme() {
    if (state.diffThemeDefined) return;
    state.diffThemeDefined = true;
    state.monaco.editor.defineTheme('axio-diff', {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: '', foreground: '6b7280' }
        ],
        colors: {
            'editor.background': '#00000000',
            'editorGutter.background': '#00000000',
            'editor.foreground': '#6b7280',
            'editorLineNumber.foreground': '#6b7280',
            'editorLineNumber.activeForeground': '#6b7280',
            'editor.lineHighlightBackground': '#00000000',
            'editor.lineHighlightBorder': '#00000000',
            'editor.selectionBackground': '#00000000',
            'editorCursor.foreground': '#6b7280',
            'editorIndentGuide.background': '#00000000',
            'editorIndentGuide.activeBackground': '#00000000',
            'diffEditor.insertedTextBackground': '#00000000',
            'diffEditor.removedTextBackground': '#00000000',
            'diffEditor.insertedLineBackground': '#00000000',
            'diffEditor.removedLineBackground': '#00000000',
            'diffEditor.insertedTextBorder': '#00000000',
            'diffEditor.removedTextBorder': '#00000000',
            'diffEditor.diagonalFill': '#00000000'
        }
    });
}
