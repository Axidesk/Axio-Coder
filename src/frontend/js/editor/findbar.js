import { state } from './state.js';
export function wireMonacoFindPush(host) {
    if (!host) return;
    let fw = null;
    let fwRO = null;
    let contentEl = null;
    const zonas = new Map();
    let ultimaAltura = 0;
    let closeTimer = null;
    let openTimer = null;
    let fadeInTimer = null;
    let closing = false;
    let settledH = 0;
    const DUR = 300;
    const EASE = 'cubic-bezier(0.4, 0, 0.2, 1)';
    const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const FIND_TOGGLES = { matchCase: 'codicon-case-sensitive', wholeWord: 'codicon-whole-word', regex: 'codicon-regex' };
    const WORD_SEPARATORS = '`~!@#$%^&*()-=+[{]}\\|;:\'",.<>/?';
    const DIM_CLASS = 'monaco-dim-text';
    const DIM_WAIT = 170;
    const DIM_MIN = 1;
    const DIM_LIMIT = 10000;
    const dimStates = new Map();
    const dimWatched = new Set();
    let dimTimer = null;
    let dimWidget = null;
    let widgetWasVisible = false;

    function getFindWidget() {
        const todos = host.querySelectorAll('.monaco-editor .find-widget');
        for (let i = 0; i < todos.length; i++) {
            if (todos[i].classList.contains('visible')) return todos[i];
        }
        for (let i = 0; i < todos.length; i++) {
            if (todos[i] === fw) return fw;
        }
        return todos[0] || null;
    }
    function editorDoFind() {
        const fwEl = getFindWidget();
        const eds = (state.monaco && state.monaco.editor && typeof state.monaco.editor.getEditors === 'function')
            ? state.monaco.editor.getEditors()
            : [];
        if (fwEl) {
            for (let i = 0; i < eds.length; i++) {
                const dom = eds[i].getDomNode();
                if (dom && dom.contains(fwEl)) return eds[i];
            }
        }
        return state.editor || null;
    }
    function domDoFind() {
        const ed = editorDoFind();
        if (ed && typeof ed.getDomNode === 'function') {
            const dom = ed.getDomNode();
            if (dom) return dom;
        }
        return host;
    }
    function getContentEl() {
        return domDoFind().querySelector('.lines-content');
    }
    function getVScrollbar() {
        return domDoFind().querySelector('.monaco-scrollable-element > .scrollbar.vertical');
    }
    function setVScrollbarOffset(y, animate) {
        const el = getVScrollbar();
        if (!el) return;
        el.style.transition = animate
            ? ('transform ' + DUR + 'ms ' + EASE + ', opacity 100ms linear')
            : 'opacity 100ms linear';
        el.style.transform = y ? ('translateY(' + y + 'px)') : '';
    }
    function getOverviewRuler() {
        return domDoFind().querySelector('.monaco-scrollable-element > .decorationsOverviewRuler');
    }
    function setOverviewRulerOffset(y, animate) {
        const el = getOverviewRuler();
        if (!el) return;
        el.style.transition = animate ? ('transform ' + DUR + 'ms ' + EASE) : 'none';
        el.style.transform = 'translate3d(0px, ' + y + 'px, 0px)';
    }
    function getMarginEl() {
        return domDoFind().querySelector('.margin');
    }
    function setMarginOffset(y, animate) {
        const el = getMarginEl();
        if (!el) return;
        el.style.transition = animate ? ('transform ' + DUR + 'ms ' + EASE) : 'none';
        el.style.transform = 'translate3d(0px, ' + y + 'px, 0px)';
    }
    function syncTabBar() {
        const bar = document.getElementById('ws-top-bar');
        if (!bar) return;
        const wrap = document.getElementById('editor-host-wrap');
        const onde = wrap || document;
        bar.classList.toggle('find-open', !!onde.querySelector('.monaco-editor .find-widget.visible'));
    }
    function relocateFindTooltip() {
        const fwEl = getFindWidget();
        if (!fwEl || !fwEl.classList.contains('visible')) return;
        const cv = host.querySelector('.context-view') || document.querySelector('.context-view');
        if (!cv || !cv.querySelector('.monaco-hover.workbench-hover')) return;
        const fwRect = fwEl.getBoundingClientRect();
        const cvRect = cv.getBoundingClientRect();
        const gap = 4;
        if (cvRect.top < fwRect.bottom + gap) {
            const delta = (fwRect.bottom + gap) - cvRect.top;
            const currentTop = parseFloat(cv.style.top) || 0;
            cv.style.top = (currentTop + delta) + 'px';
            const pointer = cv.querySelector('.workbench-hover-pointer');
            if (pointer) {
                pointer.classList.remove('bottom');
                pointer.classList.add('top');
            }
            cv.classList.remove('top');
            cv.classList.add('bottom');
        }
    }
    function stopCloseTimer() {
        if (closeTimer !== null) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
    }
    function commitZone(h) {
        const ed = editorDoFind();
        if (!ed) return;
        const reg = zonas.get(ed);
        if (h <= 0) {
            if (reg) {
                ed.changeViewZones(acc => { acc.removeZone(reg.id); });
                zonas.delete(ed);
            }
            return;
        }
        ultimaAltura = h;
        if (!reg) {
            const zone = {
                afterLineNumber: 0,
                heightInPx: h,
                domNode: document.createElement('div'),
                suppressMouseDown: true
            };
            ed.changeViewZones(acc => { zonas.set(ed, { id: acc.addZone(zone), zone: zone }); });
            return;
        }
        reg.zone.heightInPx = h;
        ed.changeViewZones(acc => { acc.layoutZone(reg.id); });
    }
    function setContentTransform(y, animate) {
        if (!contentEl) return;
        contentEl.style.transition = animate ? ('transform ' + DUR + 'ms ' + EASE) : 'none';
        contentEl.style.transform = 'translateY(' + y + 'px)';
    }
    function settleIntoView(offset, h) {
        setContentTransform(-offset, false);
        setMarginOffset(-offset, false);
        void contentEl.offsetHeight;
        if (REDUCED) {
            setContentTransform(0, false);
            setVScrollbarOffset(h, false);
            setOverviewRulerOffset(h, false);
            setMarginOffset(0, false);
        } else {
            setContentTransform(0, true);
            setVScrollbarOffset(h, true);
            setOverviewRulerOffset(h, true);
            setMarginOffset(0, true);
            openTimer = setTimeout(function () {
                openTimer = null;
                setContentTransform(0, false);
                setVScrollbarOffset(h, false);
                setOverviewRulerOffset(h, false);
                setMarginOffset(0, false);
            }, DUR);
        }
        settledH = h;
    }
    function open(h) {
        contentEl = getContentEl();
        stopCloseTimer();
        if (openTimer !== null) {
            clearTimeout(openTimer);
            openTimer = null;
        }
        closing = false;
        if (!contentEl) {
            commitZone(h);
            setVScrollbarOffset(h, false);
            setOverviewRulerOffset(h, false);
            setMarginOffset(0, false);
            settledH = h;
            return;
        }
        setContentTransform(0, false);
        setVScrollbarOffset(0, false);
        setOverviewRulerOffset(0, false);
        setMarginOffset(0, false);
        commitZone(h);
        const ed = editorDoFind();
        if (ed && typeof ed.layout === 'function') ed.layout();
        settleIntoView(h, h);
    }
    function close() {
        stopCloseTimer();
        if (openTimer !== null) {
            clearTimeout(openTimer);
            openTimer = null;
        }
        contentEl = getContentEl();
        const ed = editorDoFind();
        const h = settledH || ultimaAltura || 0;
        settledH = 0;
        if (!zonas.get(ed) || !contentEl) {
            commitZone(0);
            if (contentEl) setContentTransform(0, false);
            setVScrollbarOffset(0, false);
            setOverviewRulerOffset(0, false);
            setMarginOffset(0, false);
            if (ed && typeof ed.layout === 'function') ed.layout();
            closing = false;
            return;
        }
        setContentTransform(0, false);
        setVScrollbarOffset(h, false);
        setOverviewRulerOffset(h, false);
        setMarginOffset(0, false);
        commitZone(0);
        if (ed && typeof ed.layout === 'function') ed.layout();
        setContentTransform(h, false);
        setMarginOffset(h, false);
        void contentEl.offsetHeight;
        if (REDUCED) {
            setContentTransform(0, false);
            setVScrollbarOffset(0, false);
            setOverviewRulerOffset(0, false);
            setMarginOffset(0, false);
            closing = false;
        } else {
            closing = true;
            setContentTransform(0, true);
            setVScrollbarOffset(0, true);
            setOverviewRulerOffset(0, true);
            setMarginOffset(0, true);
            closeTimer = setTimeout(() => {
                closeTimer = null;
                setContentTransform(0, false);
                setVScrollbarOffset(0, false);
                setOverviewRulerOffset(0, false);
                setMarginOffset(0, false);
                closing = false;
            }, DUR);
        }
    }
    function resize(h) {
        const oldH = settledH;
        const delta = h - oldH;
        if (delta === 0) {
            settledH = h;
            return;
        }
        contentEl = getContentEl();
        if (!contentEl) {
            commitZone(h);
            setVScrollbarOffset(h, false);
            setOverviewRulerOffset(h, false);
            setMarginOffset(0, false);
            settledH = h;
            return;
        }
        stopCloseTimer();
        if (openTimer !== null) {
            clearTimeout(openTimer);
            openTimer = null;
        }
        closing = false;
        setContentTransform(0, false);
        setVScrollbarOffset(oldH, false);
        setOverviewRulerOffset(oldH, false);
        setMarginOffset(0, false);
        commitZone(h);
        const ed = editorDoFind();
        if (ed && typeof ed.layout === 'function') ed.layout();
        settleIntoView(delta, h);
    }
    function updateMatchesCountVisibility() {
        if (!fw) return;
        const count = fw.querySelector('.matchesCount');
        if (!count) return;
        const controls = fw.querySelector('.find-part .monaco-findInput > .controls');
        if (controls && count.parentElement !== controls) {
            const firstToggle = controls.firstElementChild;
            if (firstToggle) {
                controls.insertBefore(count, firstToggle);
            } else {
                controls.appendChild(count);
            }
        }
        const input = fw.querySelector('.find-part .monaco-inputbox .input');
        const hasQuery = input ? String(input.value || '').length > 0 : true;
        count.style.display = hasQuery ? '' : 'none';
        fw.classList.toggle('axio-find-count', hasQuery);
        const inputBox = fw.querySelector('.find-part .monaco-inputbox');
        const expanded = inputBox ? inputBox.offsetHeight > 32 : false;
        fw.classList.toggle('axio-find-expanded', expanded);
    }
    function apply() {
        if (!fw) return;
        updateMatchesCountVisibility();
        const visible = fw.classList.contains('visible');
        if (visible !== widgetWasVisible) {
            widgetWasVisible = visible;
            if (visible) scheduleDimming();
            else clearAllDimming();
        }
        syncTabBar();
        const h = visible ? (fw.offsetHeight || 0) : 0;
        if (visible && h > 0) {
            if (closing) return;
            if (!zonas.get(editorDoFind()) || settledH === 0) {
                if (h !== settledH) open(h);
            } else if (h !== settledH) {
                resize(h);
            }
        } else {
            if (closing) return;
            if (settledH !== 0 || zonas.size > 0) close();
        }
    }
    function ensure() {
        const w = getFindWidget();
        if (w && w !== fw) {
            if (fwRO) fwRO.disconnect();
            fw = w;
            fwRO = new ResizeObserver(() => apply());
            fwRO.observe(fw);
            watchFindWidget(w);
        }
        apply();
        requestAnimationFrame(relocateFindTooltip);
    }
    function fadeFindWidget() {
        if (fadeInTimer !== null) {
            clearTimeout(fadeInTimer);
            fadeInTimer = null;
        }
        const fwEl = getFindWidget();
        if (fwEl && fwEl.classList.contains('visible')) {
            fwEl.classList.remove('axio-find-fade-in');
            fwEl.classList.add('axio-find-fade');
        }
    }
    function unfadeFindWidget() {
        const fwEl = getFindWidget();
        if (!fwEl) return;
        fwEl.classList.remove('axio-find-fade');
        if (!fwEl.classList.contains('visible')) {
            fwEl.style.transition = 'none';
            fwEl.style.transform = '';
            void fwEl.offsetWidth;
            fwEl.style.transition = '';
            fwEl.style.transform = '';
            return;
        }
        fwEl.classList.add('axio-find-fade-in');
        if (fadeInTimer !== null) clearTimeout(fadeInTimer);
        fadeInTimer = setTimeout(() => {
            fadeInTimer = null;
            fwEl.classList.remove('axio-find-fade-in');
        }, DUR);
    }
    function gapsWithoutMatches(occurrences, totalLines, lastColumn) {
        const gaps = [];
        let line = 1;
        let column = 1;
        function pushGap(atLine, atColumn) {
            if (atLine > line || (atLine === line && atColumn > column)) {
                gaps.push({ startLine: line, startColumn: column, endLine: atLine, endColumn: atColumn });
            }
        }
        for (let i = 0; i < occurrences.length; i++) {
            const o = occurrences[i];
            const coversCursor = o.startLine < line || (o.startLine === line && o.startColumn <= column);
            if (coversCursor) {
                if (o.endLine > line || (o.endLine === line && o.endColumn > column)) {
                    line = o.endLine;
                    column = o.endColumn;
                }
                continue;
            }
            pushGap(o.startLine, o.startColumn);
            line = o.endLine;
            column = o.endColumn;
        }
        pushGap(totalLines, lastColumn);
        return gaps;
    }
    function findToggleOptions(fwEl) {
        function isOn(icon) {
            const btn = fwEl.querySelector('.monaco-custom-toggle.' + icon);
            return !!(btn && btn.classList.contains('checked'));
        }
        return {
            isRegex: isOn(FIND_TOGGLES.regex),
            matchCase: isOn(FIND_TOGGLES.matchCase),
            wordSeparators: isOn(FIND_TOGGLES.wholeWord) ? WORD_SEPARATORS : null
        };
    }
    function searchMatches(model, term, options) {
        try {
            return model.findMatches(term, false, options.isRegex, options.matchCase, options.wordSeparators, false, DIM_LIMIT + 1);
        } catch (e) {
            return null;
        }
    }
    function clearDimming(ed) {
        const st = dimStates.get(ed);
        if (!st) return;
        dimStates.delete(ed);
        if (st.ids.length && ed.getModel() === st.model) ed.deltaDecorations(st.ids, []);
    }
    function clearAllDimming() {
        if (dimTimer !== null) {
            clearTimeout(dimTimer);
            dimTimer = null;
        }
        Array.from(dimStates.keys()).forEach((ed) => clearDimming(ed));
    }
    function watchModelChanges(ed) {
        if (dimWatched.has(ed)) return;
        dimWatched.add(ed);
        ed.onDidChangeModel(() => {
            clearDimming(ed);
            scheduleDimming();
        });
    }
    function paintDimming(ed, term, options, key) {
        const model = ed.getModel();
        if (!model) {
            clearDimming(ed);
            return;
        }
        const before = dimStates.get(ed);
        const previousIds = before && before.model === model ? before.ids : [];
        const found = searchMatches(model, term, options);
        if (found === null || found.length > DIM_LIMIT) {
            if (previousIds.length) ed.deltaDecorations(previousIds, []);
            dimStates.delete(ed);
            return;
        }
        const occurrences = found.map((a) => ({
            startLine: a.range.startLineNumber,
            startColumn: a.range.startColumn,
            endLine: a.range.endLineNumber,
            endColumn: a.range.endColumn
        }));
        const totalLines = model.getLineCount();
        const gaps = gapsWithoutMatches(occurrences, totalLines, model.getLineMaxColumn(totalLines));
        const decorations = gaps.map((g) => ({
            range: new state.monaco.Range(g.startLine, g.startColumn, g.endLine, g.endColumn),
            options: { inlineClassName: DIM_CLASS }
        }));
        const ids = ed.deltaDecorations(previousIds, decorations);
        if (ids.length) {
            dimStates.set(ed, { model: model, ids: ids, key: key });
            watchModelChanges(ed);
        } else {
            dimStates.delete(ed);
        }
    }
    function applyDimming() {
        const fwEl = getFindWidget();
        const ed = editorDoFind();
        if (!fwEl || !ed || !fwEl.classList.contains('visible')) {
            clearAllDimming();
            return;
        }
        const input = fwEl.querySelector('.find-part .monaco-inputbox .input');
        const term = input ? String(input.value || '') : '';
        if (term.length < DIM_MIN) {
            clearAllDimming();
            return;
        }
        const options = findToggleOptions(fwEl);
        const key = term + '|' + (options.isRegex ? 'r' : '') + (options.matchCase ? 'c' : '') + (options.wordSeparators ? 'w' : '');
        const current = dimStates.get(ed);
        if (current && current.model === ed.getModel() && current.key === key) return;
        paintDimming(ed, term, options, key);
    }
    function scheduleDimming() {
        if (dimTimer !== null) clearTimeout(dimTimer);
        dimTimer = setTimeout(() => {
            dimTimer = null;
            applyDimming();
        }, DIM_WAIT);
    }
    function watchFindWidget(w) {
        if (!w || w === dimWidget) return;
        dimWidget = w;
        w.addEventListener('input', scheduleDimming);
        w.addEventListener('click', scheduleDimming);
        w.addEventListener('keyup', scheduleDimming);
    }
    window.axioFadeFindWidget = fadeFindWidget;
    window.axioUnfadeFindWidget = unfadeFindWidget;

    const mo = new MutationObserver(() => ensure());
    mo.observe(host, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
    ensure();
}
export function installFindToggle() {
    if (!state.editor) return;
    const isOpen = function () {
        const fw = state.editorHost.querySelector('.monaco-editor .find-widget');
        return !!(fw && fw.classList.contains('visible'));
    };
    state.editor.addAction({
        id: 'axio-toggle-find',
        label: 'Alternar busca',
        keybindings: [state.monaco.KeyMod.CtrlCmd | state.monaco.KeyCode.KeyF],
        run: function () {
            if (isOpen()) {
                state.editor.trigger('keyboard', 'closeFindWidget', null);
            } else {
                state.editor.trigger('keyboard', 'actions.find', null);
            }
        }
    });
}
