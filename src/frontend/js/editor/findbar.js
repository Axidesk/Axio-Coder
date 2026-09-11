import { state } from './state.js';
export function wireMonacoFindPush(host) {
    if (!host) return;
    let fw = null;
    let fwRO = null;
    let contentEl = null;
    let findZone = null;
    let findZoneId = null;
    let closeTimer = null;
    let openTimer = null;
    let fadeInTimer = null;
    let closing = false;
    let settledH = 0;
    const DUR = 300;
    const EASE = 'cubic-bezier(0.4, 0, 0.2, 1)';
    const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function getFindWidget() {
        return host.querySelector('.monaco-editor .find-widget');
    }
    function getContentEl() {
        return host.querySelector('.monaco-editor .lines-content');
    }
    function getVScrollbar() {
        return host.querySelector('.monaco-editor .monaco-scrollable-element > .scrollbar.vertical');
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
        return host.querySelector('.monaco-editor .monaco-scrollable-element > .decorationsOverviewRuler');
    }
    function setOverviewRulerOffset(y, animate) {
        const el = getOverviewRuler();
        if (!el) return;
        el.style.transition = animate ? ('transform ' + DUR + 'ms ' + EASE) : 'none';
        el.style.transform = 'translate3d(0px, ' + y + 'px, 0px)';
    }
    function getMarginEl() {
        return host.querySelector('.monaco-editor .margin');
    }
    function setMarginOffset(y, animate) {
        const el = getMarginEl();
        if (!el) return;
        el.style.transition = animate ? ('transform ' + DUR + 'ms ' + EASE) : 'none';
        el.style.transform = 'translate3d(0px, ' + y + 'px, 0px)';
    }
    function syncTabBar(visible) {
        const bar = document.getElementById('ws-top-bar');
        if (bar) bar.classList.toggle('find-open', visible);
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
        if (!state.editor) return;
        if (h <= 0) {
            if (findZoneId !== null) {
                state.editor.changeViewZones(acc => { acc.removeZone(findZoneId); });
                findZoneId = null;
                findZone = null;
            }
            return;
        }
        if (findZoneId === null) {
            findZone = {
                afterLineNumber: 0,
                heightInPx: h,
                domNode: document.createElement('div'),
                suppressMouseDown: true
            };
            state.editor.changeViewZones(acc => { findZoneId = acc.addZone(findZone); });
        } else {
            findZone.heightInPx = h;
            state.editor.changeViewZones(acc => { acc.layoutZone(findZoneId); });
        }
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
        if (state.editor && typeof state.editor.layout === 'function') {
            state.editor.layout();
        }
        settleIntoView(h, h);
    }
    function close() {
        stopCloseTimer();
        if (openTimer !== null) {
            clearTimeout(openTimer);
            openTimer = null;
        }
        contentEl = getContentEl();
        const h = settledH || (findZone ? findZone.heightInPx : 0) || 0;
        settledH = 0;
        if (findZoneId === null || !contentEl) {
            commitZone(0);
            if (contentEl) setContentTransform(0, false);
            setVScrollbarOffset(0, false);
            setOverviewRulerOffset(0, false);
            setMarginOffset(0, false);
            if (state.editor && typeof state.editor.layout === 'function') state.editor.layout();
            closing = false;
            return;
        }
        setContentTransform(0, false);
        setVScrollbarOffset(h, false);
        setOverviewRulerOffset(h, false);
        setMarginOffset(0, false);
        commitZone(0);
        if (state.editor && typeof state.editor.layout === 'function') state.editor.layout();
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
        if (state.editor && typeof state.editor.layout === 'function') {
            state.editor.layout();
        }
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
        syncTabBar(visible);
        const h = visible ? (fw.offsetHeight || 0) : 0;
        if (visible && h > 0) {
            if (closing) return;
            if (findZoneId === null || settledH === 0) {
                if (h !== settledH) open(h);
            } else if (h !== settledH) {
                resize(h);
            }
        } else {
            if (closing) return;
            if (settledH !== 0 || findZoneId !== null) close();
        }
    }
    function ensure() {
        const w = getFindWidget();
        if (w && w !== fw) {
            if (fwRO) fwRO.disconnect();
            fw = w;
            fwRO = new ResizeObserver(() => apply());
            fwRO.observe(fw);
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
