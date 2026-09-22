import { state } from './state.js';
import * as dom from './dom.js';
import { vistaDe } from './colunas.js';
import { collapseHistorySearchInline } from './historico/busca.js';
import { recolherContextPopup, syncMenuIcons, syncWorkspaceTopBar } from './ui.js';

const { aiSubmenu, btnCopyTools, btnCopyToolsHistory, btnDockCode, btnDockFiles, btnDockLogSession, btnEyeDiff, btnGitRestoreHistory, btnHistorySearch, btnRedo, btnShowQuestion, btnShowThoughts, btnShowTools, btnUndo, col3Header, col3Title, lblRedoCount, lblUndoCount, logDock, modeSubmenu, panelCol2, panelCol3, panelLogSession, plusMenu, slidingPanelContainer } = dom;


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
        syncCopyButtons();
        if (btnUndo) btnUndo.classList.remove('hidden');
        if (btnRedo) btnRedo.classList.remove('hidden');
        if (btnEyeDiff) {
            if (isDiff) btnEyeDiff.classList.remove('hidden');
            else btnEyeDiff.classList.add('hidden');
        }
        if (lblUndoCount) lblUndoCount.classList.remove('hidden');
        if (lblRedoCount) lblRedoCount.classList.remove('hidden');
        
        col3Title.textContent = fileName;
        col3Title.title = 'Mostrar na arvore de ficheiros';
        col3Title.classList.remove('text-[var(--text)]', 'text-[var(--text-branco)]');
        col3Title.classList.add('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
        col3Title.ondblclick = null;

        syncDocTopBar();
    }
    function resetCol3State(vista) {
        state.isShowingTools = false;
        state.isShowingThoughts = false;
        state.isShowingQuestions = false;
        state.currentActiveFileBalloonHtml = "";
        state.currentUndoFile = null;
        state.currentFileDataRef = null;
        document.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
        document.querySelectorAll('.file-card-selected').forEach(el => el.classList.remove('file-card-selected'));
        resetToolButtonsState();
        if (btnHistorySearch) {
            btnHistorySearch.classList.remove('text-[var(--oliva)]');
            btnHistorySearch.classList.add('text-[var(--text-mutado)]');
        }
        syncCopyButtons();
        if (btnUndo) btnUndo.classList.add('hidden');
        if (btnRedo) btnRedo.classList.add('hidden');
        if (btnEyeDiff) btnEyeDiff.classList.add('hidden');
        if (lblUndoCount) lblUndoCount.classList.add('hidden');
        if (lblRedoCount) lblRedoCount.classList.add('hidden');
        state.currentOpenedDiff = null;
        const alvo = vista || vistaDe('dock');
        if (alvo && alvo.titulo) {
            alvo.titulo.textContent = 'Codigo';
            alvo.titulo.onclick = null;
            alvo.titulo.ondblclick = null;
            alvo.titulo.title = "";
            alvo.titulo.classList.remove('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
            alvo.titulo.classList.add('text-[var(--text)]');
        }
        if (alvo && alvo.codigo) {
            alvo.codigo.style.display = '';
            alvo.codigo.style.flexDirection = '';
            alvo.codigo.style.padding = '';
        }

        syncDocTopBar();
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
    function camadaCol3Aberta() {
        return !!panelCol3 && !panelCol3.classList.contains('panel-col-closed');
    }


    function camadaNotasAberta() {
        const notas = vistaDe('notas');
        return !!(notas && notas.col3Aberta());
    }

    function vistaPreviewAtiva() {
        return state.vistaDocAtual === 'preview';
    }

    function syncDocTopBar() {
        const historico = vistaDe('historico');
        const historicoNoEditor = state.codigoDoHistoricoNoEditor && !(historico && historico.col3Aberta());
        const preview = vistaPreviewAtiva();
        const camadaDoDock = camadaCol3Aberta();
        const esconder = preview || camadaNotasAberta() || camadaDoDock || (isHistoryOpen() && !historicoNoEditor);
        syncWorkspaceTopBar(esconder, preview);

        if (col3Header) col3Header.style.display = camadaDoDock ? '' : 'none';
    }

    function syncCopyButtons(vista, ativo) {
        const alvo = vista || vistaDe('dock');
        const ferramentas = ativo === 'tools' && !!alvo;
        if (btnCopyTools) btnCopyTools.classList.toggle('hidden', !(ferramentas && alvo.id === 'dock'));
        if (btnCopyToolsHistory) btnCopyToolsHistory.classList.toggle('hidden', !(ferramentas && alvo.id === 'historico'));
        if (btnGitRestoreHistory && ativo !== 'git') btnGitRestoreHistory.classList.add('hidden');
    }
    function openPanelCol(panel) {
        if (!panel) return;
        panel.classList.remove('panel-col-closed');
        syncDockButtons();
        syncDocTopBar();
    }
    function closePanelCol(panel) {
        if (!panel) return;
        panel.classList.add('panel-col-closed');
        syncDockButtons();
        syncDocTopBar();
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
    function openCol3Panel() {
   
        if (window.WorkspaceView && typeof window.WorkspaceView.showEditor === 'function') {
            window.WorkspaceView.showEditor();
        }
        openPanelCol(panelCol3);
    }
    function closeCol3() {
        closePanelCol(panelCol3);
        resetCol3State();
    }
    function isLogDockOpen() {
        return panelLogSession && !panelLogSession.classList.contains('panel-col-closed');
    }
    function openLogDock() {
        if (!logDock) return;
        logDock.classList.remove('dock-closed');
        if (panelLogSession) panelLogSession.classList.remove('panel-col-closed');
        syncDockButtons();
    }
    function closeLogDock() {
        if (panelLogSession) panelLogSession.classList.add('panel-col-closed');
        if (panelCol2) panelCol2.classList.add('panel-col-closed');
        if (panelCol3) panelCol3.classList.add('panel-col-closed');
        syncDockButtons();
    }
    function isHistoryOpen() {
        return !slidingPanelContainer.classList.contains('dock-closed');
    }
    function openHistory() {
        recolherContextPopup();
        slidingPanelContainer.classList.remove('dock-closed');
        syncDocTopBar();
    }
    function closeHistory() {

        state.codigoDoHistoricoNoEditor = false;
        const vistaHistorico = vistaDe('historico');
        if (vistaHistorico) vistaHistorico.fecharCol3();
        slidingPanelContainer.classList.add('dock-closed');

        state.isShowingSessionHistory = false;
        if (state.historySearchInlineActive) {
            collapseHistorySearchInline();
        }
        syncDocTopBar();
    }
    function closeHistoryPanel() {
        closeHistory();
        if (window.WorkspaceView && typeof window.WorkspaceView.setFocusMode === 'function') {
            window.WorkspaceView.setFocusMode(false);
        }
        syncMenuIcons();
        syncDocTopBar();
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
    syncCopyButtons,
    openPanelCol,
    closePanelCol,
    toggleLogColumn,
    openCol3Panel,
    closeCol3,
    isLogDockOpen,
    openLogDock,
    closeLogDock,
    isHistoryOpen,
    openHistory,
    closeHistory,
    closeHistoryPanel,
    openLogDockInWorkspace,
    syncDocTopBar
};