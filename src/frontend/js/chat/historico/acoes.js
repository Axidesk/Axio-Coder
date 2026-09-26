import { state } from '../state.js';
import * as dom from '../dom.js';
import { adicionarFileNaLista } from '../files.js';
import { vistaDe } from '../colunas.js';
import { isHistoryOpen } from '../layout.js';

const { btnHistorySearch, btnShowQuestion, btnShowThoughts, btnShowTools } = dom;

let repinturaCol3 = null;
let repinturaPendente = null;
let repinturaAgendada = 0;

const ESPERA_DA_REPINTURA_MS = 250;

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
    function _repintarCol3Agora() {
        repinturaAgendada = 0;
        const grupo = repinturaPendente;
        repinturaPendente = null;
        if (!repinturaCol3) return;
        const alvo = ['dock', 'historico'].map(id => vistaDe(id)).find(v => v && v.col3Aberta());
        if (!alvo) return;
        state.suppressCol3Anim = true;
        try { repinturaCol3(alvo, grupo); } finally { state.suppressCol3Anim = false; }
    }
    function repintarCol3Aberta(grupo) {
        if (!repinturaCol3) return false;
        repinturaPendente = grupo;
        if (!repinturaAgendada) repinturaAgendada = setTimeout(_repintarCol3Agora, ESPERA_DA_REPINTURA_MS);
        return true;
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
    repintarCol3Aberta,
    updateActionButtons,
    setHistoryActionButtonsVisible,
    selectHistoryTask
};
