import { state } from '../state.js';
import * as dom from '../dom.js';
import { adicionarFileNaLista } from '../files.js';
import { vistaDe } from '../colunas.js';
import { isHistoryOpen } from '../layout.js';

const { btnHistorySearch, btnShowQuestion, btnShowThoughts, btnShowTools } = dom;

let repinturaCol3 = null;
let sincronizacaoDeRestauro = null;

    function openFilesPanel(group, vista) {
        const alvo = vista || vistaDe('dock');
        alvo.abrirCol2();
        window.currentActiveLogGroup = group;
        state.currentViewingTools = group.tools || [];
        state.currentViewingThoughts = group.thoughts || [];
        state.currentViewingQuestions = group.questions || [];
        state.thoughtsExpanded = false;
        state.currentViewingAiResponse = group.aiResponse || '';
        updateActionButtons();
        const repintar = alvo.col3Aberta() && !!repinturaCol3;
        if (!repintar) alvo.fecharCol3();
        alvo.lista.innerHTML = '';
        if ((group.files || []).length === 0) {
            alvo.lista.innerHTML = '<div class="panel-empty">Nenhum arquivo modificado neste turno.</div>';
        }
        (group.files || []).forEach(fileData => adicionarFileNaLista(fileData, alvo));
        alvo.aoAbrirGrupo(group);
        if (repintar) repinturaCol3(alvo, group);
    }
    function registrarRepinturaCol3(fn) {
        repinturaCol3 = fn;
    }
    function registrarSincronizacaoDeRestauro(fn) {
        sincronizacaoDeRestauro = fn;
    }
    function updateActionButtons() {
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
        if (sincronizacaoDeRestauro) sincronizacaoDeRestauro();
    }
    function setHistoryActionButtonsVisible(show) {
        if (btnHistorySearch) btnHistorySearch.classList.toggle('hidden', !show);
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
    registrarRepinturaCol3,
    registrarSincronizacaoDeRestauro,
    updateActionButtons,
    setHistoryActionButtonsVisible,
    selectHistoryTask
};
