import { state } from './state.js';
export function clearHoverLineFor(ed) {
    if (!ed) return;
    const st = state.hoverStates.get(ed);
    if (!st) return;
    st.line = -1;
    st.decorations = ed.deltaDecorations(st.decorations, []);
}
export function clearHoverLine() {
    if (state.editor) clearHoverLineFor(state.editor);
    if (state.diffOriginalEditor) clearHoverLineFor(state.diffOriginalEditor);
    if (state.diffModifiedEditor) clearHoverLineFor(state.diffModifiedEditor);
}
export function hasNonEmptySelection(ed) {
    if (!ed) return false;
    const sel = ed.getSelection();
    return !!(sel && !sel.isEmpty());
}
export function applyHoverLine(ed, line) {
    if (!ed) return;
    const st = state.hoverStates.get(ed);
    if (!st) return;
    if (line === st.line) return;
    st.line = line;
    const model = ed.getModel();
    if (!model || line <= 0) {
        st.decorations = ed.deltaDecorations(st.decorations, []);
        return;
    }
    const maxCol = model.getLineMaxColumn(line);
    st.decorations = ed.deltaDecorations(st.decorations, [{
        range: new state.monaco.Range(line, 1, line, maxCol),
        options: { isWholeLine: true, className: 'monaco-hover-line' }
    }]);
}
export function installHoverHighlightFor(ed) {
    if (!ed || state.hoverInstalled.has(ed)) return;
    state.hoverInstalled.add(ed);
    state.hoverStates.set(ed, { decorations: [], line: -1 });
    ed.onMouseMove(function (e) {
        if (!ed) return;
        if (hasNonEmptySelection(ed)) {
            clearHoverLineFor(ed);
            return;
        }
        if (ed === state.editor) {
            if (state.logMode || state.diffMode || state.currentFileIsImage) {
                clearHoverLineFor(ed);
                return;
            }
            if (ed.getOption(state.monaco.editor.EditorOption.renderLineHighlight) !== 'none') {
                ed.updateOptions({ renderLineHighlight: 'none' });
            }
        }
        const line = e.target && e.target.position ? e.target.position.lineNumber : -1;
        applyHoverLine(ed, line);
    });
    ed.onMouseLeave(function () {
        clearHoverLineFor(ed);
    });
    ed.onDidChangeCursorSelection(function () {
        if (hasNonEmptySelection(ed)) {
            clearHoverLineFor(ed);
        }
    });
}
export function installEditorHoverHighlight() {
    installHoverHighlightFor(state.editor);
}
export function installUrlWordSelection() {
    if (state.urlWordSelectionInstalled || !state.editor) return;
    state.urlWordSelectionInstalled = true;
    const urlRegex = /[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^\s"'<>()]+/g;
    state.editor.onMouseUp(function (e) {
        if (!state.editor) return;
        if (e.event.detail !== 2) return;
        if (state.logMode || state.diffMode) return;
        const pos = e.target && e.target.position;
        if (!pos) return;
        const model = state.editor.getModel();
        if (!model) return;
        const lineText = model.getLineContent(pos.lineNumber);
        urlRegex.lastIndex = 0;
        let m;
        while ((m = urlRegex.exec(lineText)) !== null) {
            const startCol = m.index + 1;
            const endCol = m.index + m[0].length + 1;
            if (pos.column >= startCol && pos.column <= endCol) {
                state.editor.setSelection(new state.monaco.Range(pos.lineNumber, startCol, pos.lineNumber, endCol));
                break;
            }
        }
    });
}
