import { state } from './state.js';
import * as dom from './dom.js';
import { vistaDe } from './colunas.js';
import { resetCol3State, syncCopyButtons, syncDocTopBar } from './layout.js';
import { renderQuestions } from './col3_views.js';

const { btnShowQuestion } = dom;

    function showQuestionPanel(group, vista) {
        const alvo = vista || vistaDe('dock');
        const titulo = alvo ? alvo.titulo : null;
        resetCol3State(alvo);
        if (alvo) alvo.abrirCol3();
        state.isShowingQuestions = true;
        if (btnShowQuestion) {
            btnShowQuestion.classList.remove("text-[var(--text-mutado)]");
            btnShowQuestion.classList.add("text-[var(--oliva)]");
        }
        syncCopyButtons(alvo, 'question');
        const nome = (group && (group.displayName || group.name)) || "Pergunta do Usuário";
        if (!titulo) {
            renderQuestions(alvo);
            syncDocTopBar();
            return;
        }
        titulo.textContent = nome;
        titulo.onclick = null;
        renderQuestions(alvo);
        syncDocTopBar();
    }
export { showQuestionPanel };
