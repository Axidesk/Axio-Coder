import { state } from './state.js';
import * as dom from './dom.js';
import { vistaDe } from './colunas.js';
import { resetCol3State, syncCopyButtons, syncDocTopBar } from './layout.js';
import { updateRoundCardNameByTurnId } from './historico/cards.js';
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
        if (group && (group.displayName || group.name)) {
            titulo.classList.remove("text-[var(--text)]");
            titulo.classList.add("cursor-pointer", "hover:underline", "text-[var(--oliva)]");
            titulo.title = "Clique duas vezes para renomear a rodada";
            titulo.ondblclick = () => beginRenameRound(group, alvo);
        } else {
            titulo.ondblclick = null;
            titulo.title = "";
        }
        renderQuestions(alvo);
        syncDocTopBar();
    }
    function beginRenameRound(group, vista) {
        const titulo = ((vista || vistaDe('dock')) || {}).titulo;
        if (!titulo) return;
        const atual = group.displayName || group.name || "Taref     a";
        const input = document.createElement("input");
        input.type = "text";
        input.value = atual;
        input.className = "bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1 text-sm text-[var(--text)] focus:outline-none focus:border-[var(--oliva)] w-full";
        titulo.innerHTML = "";
        titulo.appendChild(input);
        input.focus();
        input.select();
        let finalizado = false;
        const commit = async () => {
            if (finalizado) return;
            finalizado = true;
            const novoNome = input.value.trim() || atual;
            titulo.textContent = novoNome;
            await renameRound(group, novoNome);
        };
        const cancelar = () => {
            if (finalizado) return;
            finalizado = true;
            titulo.textContent = atual;
        };
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            else if (e.key === "Escape") { e.preventDefault(); cancelar(); }
        });
        input.addEventListener("blur", commit);
        input.addEventListener("click", (e) => e.stopPropagation());
        input.addEventListener("dblclick", (e) => e.stopPropagation());
    }
    async function renameRound(group, novoNome) {
        group.name = novoNome;
        group.displayName = novoNome;
        if (group.nameEl) {
            group.nameEl.textContent = novoNome;
        }
        Object.keys(state.sessionDetailCache).forEach(key => {
            const logs = state.sessionDetailCache[key] || [];
            logs.forEach(saved => {
                if (String(saved.id) === String(group.id)) {
                    saved.name = novoNome;
                    saved.displayName = novoNome;
                }
            });
        });
        updateRoundCardNameByTurnId(group.id, novoNome);
        try {
            await fetch('/api/session_log/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ round_id: group.id, name: novoNome })
            });
        } catch (e) {
            console.error('Erro ao renomear rodada:', e);
        }
    }

export { showQuestionPanel, beginRenameRound, renameRound };
