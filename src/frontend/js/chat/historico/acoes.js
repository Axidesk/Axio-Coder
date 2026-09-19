import { state } from '../state.js';
import * as dom from '../dom.js';
import { adicionarFileNaLista } from '../files.js';
import { vistaDe } from '../colunas.js';
import { isHistoryOpen } from '../layout.js';

const { btnDeleteTask, btnHistorySearch, btnRestoreTask, btnSaveTask, btnSaveTaskIcon, btnShowQuestion, btnShowThoughts, btnShowTools } = dom;

    function openFilesPanel(group, vista) {
        const alvo = vista || vistaDe('dock');
        alvo.abrirCol2();
        window.currentActiveLogGroup = group;
        state.currentViewingTools = group.tools || [];
        state.currentViewingThoughts = group.thoughts || [];
        state.currentViewingQuestions = group.questions || [];
        state.thoughtsExpanded = false;
        state.currentViewingAiResponse = group.aiResponse || '';
        updateShowButtonsState();
        alvo.fecharCol3();
        alvo.lista.innerHTML = '';
        if ((group.files || []).length === 0) {
            alvo.lista.innerHTML = '<div class="panel-empty">Nenhum arquivo modificado neste turno.</div>';
        }
        (group.files || []).forEach(fileData => adicionarFileNaLista(fileData, alvo));
        alvo.aoAbrirGrupo(group);
    }
    function updateActionButtons() {
        const enabled = !!state.currentSelectedHistoryGroup;
        [btnRestoreTask, btnSaveTask, btnDeleteTask].forEach(btn => {
            if (!btn) return;
            btn.disabled = !enabled;
            btn.classList.toggle('opacity-40', !enabled);
            btn.classList.toggle('cursor-default', !enabled);
        });
        if (btnSaveTask) {
            const isSaved = enabled && !!state.currentSelectedHistoryGroup.salvo;
            btnSaveTask.classList.toggle('text-[var(--oliva)]', isSaved);
            btnSaveTask.classList.toggle('text-[var(--text-mutado)]', !isSaved);
            if (btnSaveTaskIcon) {
                btnSaveTaskIcon.setAttribute('fill', isSaved ? 'currentColor' : 'none');
            }
        }
        updateShowButtonsState();
    }
    function updateShowButtonsState() {
        const enabled = isHistoryOpen()
            ? !!state.currentSelectedHistoryGroup
            : !!window.currentActiveLogGroup;
        [btnShowQuestion, btnShowThoughts, btnShowTools].forEach(btn => {
            if (!btn) return;
            btn.disabled = !enabled;
            btn.classList.toggle('opacity-40', !enabled);
            btn.classList.toggle('cursor-default', !enabled);
            if (!enabled) {
                btn.classList.remove('text-[var(--oliva)]');
                btn.classList.add('text-[var(--text-mutado)]');
            }
        });
    }
    function setHistoryActionButtonsVisible(show) {
        if (btnHistorySearch) btnHistorySearch.classList.toggle('hidden', !show);
        if (btnRestoreTask) btnRestoreTask.classList.toggle('hidden', !show);
        if (btnSaveTask) btnSaveTask.classList.toggle('hidden', !show);
        if (btnDeleteTask) btnDeleteTask.classList.toggle('hidden', !show);
    }
    function selectHistoryTask(group, el) {
        document.querySelectorAll('.history-round-card').forEach(c => c.classList.remove('history-round-selected'));
        el.classList.add('history-round-selected');
        state.currentSelectedHistoryGroup = group;
        state.currentSelectedHistoryEl = el;
        updateActionButtons();
    }


export {
    openFilesPanel,
    updateActionButtons,
    setHistoryActionButtonsVisible,
    selectHistoryTask
};
