import { state } from './state.js';
import * as dom from './dom.js';
import { collapseHistorySearchInline, moveColsToDock, moveColsToHistory } from './history.js';
import { recolherContextPopup, syncMenuIcons, syncWorkspaceTopBar } from './ui.js';

const { aiSubmenu, btnCopyTools, btnDockCode, btnDockFiles, btnDockLogSession, btnEyeDiff, btnHistorySearch, btnRedo, btnShowQuestion, btnShowThoughts, btnShowTools, btnUndo, codeViewContainer, col3Title, lblRedoCount, lblUndoCount, logDock, modeSubmenu, panelCol1, panelCol2, panelCol3, panelLogSession, plusMenu, slidingPanelContainer, wrap } = dom;


    function closePlusMenus() {
        if (plusMenu) plusMenu.classList.remove('menu-open');
        if (modeSubmenu) modeSubmenu.classList.remove('menu-open');
        if (aiSubmenu) aiSubmenu.classList.remove('menu-open');
    }
    function resetToolButtonsState() {
        if (btnShowTools) {
            btnShowTools.classList.remove('text-[var(--oliva)]');
            btnShowTools.classList.add('text-[var(--text-mutado)]');
        }
        if (btnShowThoughts) {
            btnShowThoughts.classList.remove('text-[var(--oliva)]');
            btnShowThoughts.classList.add('text-[var(--text-mutado)]');
        }
        if (btnShowQuestion) {
            btnShowQuestion.classList.remove('text-[var(--oliva)]');
            btnShowQuestion.classList.add('text-[var(--text-mutado)]');
        }
    }
    function setupCol3ForFileView(fileName, isDiff) {
        state.isShowingTools = false;
        state.isShowingThoughts = false;
        state.isShowingQuestions = false;
        resetToolButtonsState();
        if (btnCopyTools) btnCopyTools.classList.add('hidden');
        if (btnUndo) btnUndo.classList.remove('hidden');
        if (btnRedo) btnRedo.classList.remove('hidden');
        if (btnEyeDiff) {
            if (isDiff) btnEyeDiff.classList.remove('hidden');
            else btnEyeDiff.classList.add('hidden');
        }
        if (lblUndoCount) lblUndoCount.classList.remove('hidden');
        if (lblRedoCount) lblRedoCount.classList.remove('hidden');
        
        col3Title.textContent = fileName;
        col3Title.title = 'Abrir no editor';
        col3Title.classList.remove('text-[var(--text)]', 'text-[var(--text-branco)]');
        col3Title.classList.add('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
        col3Title.ondblclick = null;
    }
    function resetCol3State() {
        state.isShowingTools = false;
        state.isShowingThoughts = false;
        state.isShowingQuestions = false;
        state.currentActiveFileBalloonHtml = "";
        state.currentUndoFile = null;
        state.currentFileDataRef = null;
        // Limpa o destaque de seleção da pilha de edições
        document.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
        document.querySelectorAll('.file-card-selected').forEach(el => el.classList.remove('file-card-selected'));
        resetToolButtonsState();
        if (btnHistorySearch) {
            btnHistorySearch.classList.remove('text-[var(--oliva)]');
            btnHistorySearch.classList.add('text-[var(--text-mutado)]');
        }
        if (btnCopyTools) btnCopyTools.classList.add('hidden');
        if (btnUndo) btnUndo.classList.add('hidden');
        if (btnRedo) btnRedo.classList.add('hidden');
        if (btnEyeDiff) btnEyeDiff.classList.add('hidden');
        if (lblUndoCount) lblUndoCount.classList.add('hidden');
        if (lblRedoCount) lblRedoCount.classList.add('hidden');
        state.currentOpenedDiff = null;
        col3Title.textContent = 'Codigo';
        col3Title.onclick = null;
        col3Title.ondblclick = null;
        col3Title.title = "";
        col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
        col3Title.classList.add('text-[var(--text)]');
        // Restaura o layout padrão da Col 3 (usado pelo modo de busca).
        codeViewContainer.style.display = '';
        codeViewContainer.style.flexDirection = '';
        codeViewContainer.style.padding = '';
    }
    function syncDockButtons() {
        if (btnDockLogSession) {
            const open = panelLogSession && !panelLogSession.classList.contains('panel-col-closed');
            btnDockLogSession.classList.toggle('hidden', open);
            btnDockLogSession.classList.toggle('text-[var(--oliva)]', open);
            btnDockLogSession.classList.toggle('text-[var(--text-mutado)]', !open);
        }
        if (btnDockFiles) btnDockFiles.classList.add('hidden');
        if (btnDockCode) btnDockCode.classList.add('hidden');
    }
    function syncLogDockFlex() {
        if (!logDock) return;
        const col3InDock = panelCol3 && panelCol3.parentNode === logDock;
        const col3Open = col3InDock && !panelCol3.classList.contains('panel-col-closed');
        logDock.classList.toggle('has-code', col3Open);
    }
    function syncHistoryContainerWidth() {
        if (!slidingPanelContainer) return;
        const col3InHistory = panelCol3 && panelCol3.parentNode === slidingPanelContainer;
        if (!col3InHistory || slidingPanelContainer.classList.contains('history-search-expanded')) {
            slidingPanelContainer.style.width = '';
            return;
        }
        if (!panelCol3.classList.contains('panel-col-closed')) {
            slidingPanelContainer.style.width = '100vw';
            return;
        }
        let openCount = 0;
        if (panelCol1 && !panelCol1.classList.contains('panel-col-closed')) openCount++;
        if (panelCol2 && !panelCol2.classList.contains('panel-col-closed')) openCount++;
        const colWidth = panelCol1 ? panelCol1.offsetWidth : 0;
        let w = openCount * colWidth;
        const cs = window.getComputedStyle(slidingPanelContainer);
        w += parseFloat(cs.paddingLeft) || 0;
        w += parseFloat(cs.paddingRight) || 0;
        slidingPanelContainer.style.width = Math.round(w) + 'px';
    }
    function openPanelCol(panel) {
        if (!panel) return;
        panel.classList.remove('panel-col-closed');
        syncDockButtons();
        if (panel === panelCol3) syncLogDockFlex();
        syncHistoryContainerWidth();
    }
    function closePanelCol(panel) {
        if (!panel) return;
        panel.classList.add('panel-col-closed');
        syncDockButtons();
        if (panel === panelCol3) syncLogDockFlex();
        syncHistoryContainerWidth();
    }
    function toggleLogColumn(panel) {
        if (!panel) return;
        const isOpen = !panel.classList.contains('panel-col-closed');
        if (isOpen) {
            closePanelCol(panel);
        } else {
            openLogDock();
            openPanelCol(panel);
        }
        syncDockButtons();
    }
    function col3IsOverlay() {
        return panelCol3 && panelCol3.classList.contains('col3-overlay');
    }
    function moveCol3ToOverlay() {
        if (!wrap || !panelCol3) return;
        clearTimeout(state.col3OverlayCloseTimer);
        state.col3OverlayCloseTimer = null;
        if (panelCol3.parentNode !== wrap) {
            panelCol3.classList.add('col3-overlay');
            wrap.appendChild(panelCol3);
            void panelCol3.offsetWidth;
        }
    }
    function openCol3Overlay() {
        if (window.WorkspaceView && typeof window.WorkspaceView.showEditor === 'function') {
            window.WorkspaceView.showEditor();
        }
        moveCol3ToOverlay();
        panelCol3.classList.add('col3-overlay');
        panelCol3.classList.remove('panel-col-closed');
        panelCol3.classList.add('col3-overlay-open');
        syncDockButtons();
        syncLogDockFlex();
        syncHistoryContainerWidth();
    }
    function clearCol3Overlay() {
        clearTimeout(state.col3OverlayCloseTimer);
        state.col3OverlayCloseTimer = null;
        if (panelCol3) {
            panelCol3.classList.remove('col3-overlay', 'col3-overlay-open');
        }
    }
    function closeCol3Overlay() {
        if (!col3IsOverlay()) return;
        panelCol3.classList.remove('col3-overlay-open');
        panelCol3.classList.add('panel-col-closed');
        clearTimeout(state.col3OverlayCloseTimer);
        state.col3OverlayCloseTimer = window.setTimeout(() => {
            state.col3OverlayCloseTimer = null;
            if (!col3IsOverlay()) return;
            clearCol3Overlay();
            moveColsToHistory();
            syncHistoryContainerWidth();
        }, 320);
    }
    function openCol3Panel() {
        if (isHistoryOpen()) {
            openCol3Overlay();
        } else {
            openPanelCol(panelCol3);
        }
    }
    function closeCol3() {
        if (col3IsOverlay()) {
            closeCol3Overlay();
        } else {
            closePanelCol(panelCol3);
        }
        resetCol3State();
    }
    function isLogDockOpen() {
        return panelLogSession && !panelLogSession.classList.contains('panel-col-closed');
    }
    function isCol3Open() {
        return panelCol3 && !panelCol3.classList.contains('panel-col-closed');
    }
    function openLogDock() {
        if (!logDock) return;
        logDock.classList.remove('dock-closed');
        if (panelLogSession) panelLogSession.classList.remove('panel-col-closed');
        syncDockButtons();
        syncLogDockFlex();
    }
    function closeLogDock() {
        if (panelLogSession) panelLogSession.classList.add('panel-col-closed');
        if (panelCol2) panelCol2.classList.add('panel-col-closed');
        if (panelCol3) panelCol3.classList.add('panel-col-closed');
        syncDockButtons();
        syncLogDockFlex();
    }
    function isHistoryOpen() {
        return !slidingPanelContainer.classList.contains('dock-closed');
    }
    function openHistory() {
        recolherContextPopup();
        slidingPanelContainer.classList.remove('dock-closed');
    }
    function closeHistory() {
        slidingPanelContainer.classList.add('dock-closed');
        if (state.historySearchInlineActive) {
            collapseHistorySearchInline();
        }
    }
    function closeHistoryAndResetDock() {
        closeHistory();
        closePanelCol(panelCol2);
        closeCol3();
        if (window.WorkspaceView && typeof window.WorkspaceView.setFocusMode === 'function') {
            window.WorkspaceView.setFocusMode(false);
        }
        moveColsToDock();
        syncLogDockFlex();
        syncMenuIcons();
        syncWorkspaceTopBar(false);
        if (window.WorkspaceView && typeof window.WorkspaceView.expandDockForFocus === 'function') {
            window.WorkspaceView.expandDockForFocus();
        }
    }
    function openLogDockInWorkspace() {
        if (window.WorkspaceView && typeof window.WorkspaceView.showEditor === 'function') {
            window.WorkspaceView.showEditor();
        }
        openLogDock();
    }

export {
    closePlusMenus,
    setupCol3ForFileView,
    resetCol3State,
    syncDockButtons,
    syncLogDockFlex,
    syncHistoryContainerWidth,
    openPanelCol,
    closePanelCol,
    toggleLogColumn,
    col3IsOverlay,
    moveCol3ToOverlay,
    openCol3Overlay,
    clearCol3Overlay,
    closeCol3Overlay,
    openCol3Panel,
    closeCol3,
    isLogDockOpen,
    isCol3Open,
    openLogDock,
    closeLogDock,
    isHistoryOpen,
    openHistory,
    closeHistory,
    closeHistoryAndResetDock,
    openLogDockInWorkspace
};