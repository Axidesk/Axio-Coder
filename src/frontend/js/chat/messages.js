import { state } from './state.js';
import * as dom from './dom.js';
import { renderImagePreviews } from './attach.js';
import { atualizarBotoesUndoRedo, createChildBalloon, gerarSnippetHtml, restaurarPastaSelecionada, sincronizarArquivosEmTempoReal } from './files.js';
import { createLogGroupCard, roundMetaHtml, updateRoundCardCommitByTurnId } from './historico/cards.js';
import { epochDeId } from './historico/checkpoint.js';
import { fetchSessionHistoryData, saveCurrentTurnSession } from './historico/estado.js';
import { prefetchSessionDetails, preloadSessionHistory } from './historico/painel.js';
import { activateWorkspaceIcon, escrevendoNoChat, esconderChip, renderCurrentSessionLogs, resetSendButton, resetTurnUI, setLogsLoading, showAlert, showWorkspaceView } from './ui.js';
import { escapeHtml } from './escape.js';
import { formatMessage, formatInlineText, formatInline } from './markdown.js';
import { createPlanStepCard, _createStackCard, _setStepIcon, _collapseStep, _formatExecutingStatus, _resumoNavegacao, _pararPlanoEmCurso } from './plan_cards.js';
import { reavaliarBuscaChat } from './busca_chat.js';
import { alimentarRaciocinio } from '../editor/preview_raciocinio.js';

const { alertPopup, alertPopupContent, btnSend, btnShowThoughts, btnShowTools, chatContainerLeft, chatContainerRight, chatInnerLeft, chatInnerRight, contextAcumuladaFill, contextInfoLimite, contextSessaoFill, contextUsage, contextUsageAcumulada, contextUsageFill, contextUsageLabel, contextUsageSessao, currentLogsList, currentLogsWrapper, inputText, lblExecuting, lblFolder, lblMetrics, lblStatus, terminalMode } = dom;

let currentPlanContainer = null;

function corDeUsoContexto(pct, emExecucao) {
    if (emExecucao) return { cor: 'var(--azul-acao)', glow: 'var(--azul-glow)' };
    if (pct >= 85) return { cor: 'var(--vermelho-vivo)', glow: 'var(--vermelho-glow)' };
    if (pct >= 60) return { cor: 'var(--ambar-vivo)', glow: 'var(--ambar-glow)' };
    return { cor: 'var(--oliva)', glow: 'var(--oliva-glow)' };
}

function aplicarCorBarraContexto(el, pct, emExecucao) {
    if (!el) return;
    const { cor, glow } = corDeUsoContexto(pct, emExecucao);
    el.style.background = cor;
    el.style.filter = 'drop-shadow(0 0 3px ' + glow + ')';
}

function _fmtTokens(n) {
    return n >= 1000000 ? (n / 1000000).toFixed(1) + 'M' : n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
}

function _textoDoTeto(limite) {
    const tokens = limite >= 1000000 ? (limite / 1000000) + ' milhão de tokens' : (limite / 1000) + ' mil tokens';
    return tokens + ' (cerca de ' + Math.round(limite * 0.7 / 1000) + ' mil palavras)';
}

export {
  sendMessage,
  startSSE,
  addMessage,
  limparConversa,
  formatMessage,
  formatInline,
  formatInlineText,
  attachCodeBlockListeners,
  escapeHtml,
  countLines,
  setStopButton,
};

export { renderThoughts, applyThoughtClamp, renderQuestions, renderTools, sortToolArgsKeys } from './col3_views.js';
export { showQuestionPanel, beginRenameRound, renameRound } from './question_panel.js';
export { renderImagePreviews, addImage } from './attach.js';
    
async function sendMessage() {
        if (state.isGenerating) {

            resetTurnUI();
            restaurarImagensDoTurno();
            startSSE();
            try {
                fetch('/api/cancel', { method: 'POST' }).catch(() => {});
            } catch (e) { console.error(e); }
            return;
        }

        let text = inputText.value.trim();

        if (text.length > 500 && !text.includes(' ')) {
            text = '';
        }
        
        if (!text && state.attachedImages.length === 0) return;
        
        if (!lblFolder.textContent) {
            alertPopup.classList.remove('opacity-0', 'pointer-events-none');
            alertPopup.classList.add('opacity-100', 'pointer-events-auto');
            alertPopupContent.classList.remove('scale-95');
            alertPopupContent.classList.add('scale-100');
            return;
        }

        state.isGenerating = true;
        window.currentRoundStartedAt = Date.now();
        state.currentTurnLogs = [];
        state.currentTurnSummary = text;
        window.pendingUserQuestion = text;
        
        if (state.isShowingSessionHistory) {
            state.isShowingSessionHistory = false;
            renderCurrentSessionLogs({ fecharColunas: false });
        }
        setStopButton();
        setLogsLoading(true);

        let messageText = text;
        const msgDiv = addMessage('user', messageText || ' ');
        window.lastUserMessageDiv = msgDiv;
        window.lastUserMessageText = text;
        
        if (state.attachedImages.length > 0) {
            const imgContainer = document.createElement('div');
            imgContainer.className = 'flex flex-wrap gap-2 mt-3';
            state.attachedImages.forEach(img => {
                const imgWrapper = document.createElement('div');
                imgWrapper.className = 'relative';
                const imgNode = document.createElement('img');
                imgNode.src = img.dataUrl;
                imgNode.className = 'max-w-sm max-h-64 rounded-lg border border-[var(--border-suave)] shadow-md cursor-pointer hover:opacity-90 transition-opacity';
                imgNode.onclick = () => window.expandImage(img.dataUrl);
                imgNode.title = img.name;
                imgWrapper.appendChild(imgNode);
                imgContainer.appendChild(imgWrapper);
            });
            msgDiv.appendChild(imgContainer);
        }

        state.currentTurnId = Date.now() + '-' + Math.random().toString(36).slice(2);
        const payload = { message: text, mode: state.currentMode, use_deepseek: state.selectedModel === 'deepseek', ai_model: state.selectedModel, turn_id: state.currentTurnId };
        if (state.attachedImages.length > 0) {
            payload.images = state.attachedImages.map(img => ({ base64: img.base64, name: img.name, mime: img.mime }));
        }
        
        window.lastUserImages = state.attachedImages.length ? state.attachedImages.slice() : null;
        inputText.value = '';
        inputText.style.height = 'auto';
        if (typeof esconderChip === 'function') esconderChip();
        state.attachedImages = [];
        state.imageCounter = 1;
        renderImagePreviews();
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                if (msgDiv && msgDiv.parentNode) msgDiv.parentNode.removeChild(msgDiv);
                restaurarImagensDoTurno();
                inputText.value = messageText || '';
                inputText.style.height = 'auto';
                window.pendingUserQuestion = null;
                state.isGenerating = false;
                resetSendButton();
                setLogsLoading(false);
                const mensagemErro = (errData && errData.error) || 'Erro de configuração';
                showAlert(mensagemErro);
            }
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
            addMessage('system', 'Erro ao conectar com o servidor local.');
            lblStatus.textContent = 'Erro de conexão';
            window.pendingUserQuestion = null;
            state.isGenerating = false;
            resetSendButton();
            setLogsLoading(false);
        }
    }
function startSSE() {
    if (state.eventSource) {
        state.eventSource.close();
    }
    state.eventSource = new EventSource('/api/stream');
    resetEstadoDoTurno();
    state.eventSource.onmessage = async function(event) {
        if (!event.data || event.data.trim() === '') return;
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            return;
        }
        if (data.turn_id && data.turn_id !== state.currentTurnId) return;
        alimentarRaciocinio(data);
        if (window.WorkspaceView && typeof window.WorkspaceView.onSSE === 'function') {
            window.WorkspaceView.onSSE(data);
        }
        if (window.pendingUserQuestion && currentSessionQuestions.length === 0) {
            currentSessionQuestions.push(window.pendingUserQuestion);
            window.pendingUserQuestion = null;
        }
        const tratar = HANDLERS[data.type];
        if (tratar) await tratar(data);
    };
    state.eventSource.onopen = function() {
        restaurarPastaSelecionada();
        if (state.sessionHistoryLoaded) {
            fetchSessionHistoryData().then(() => prefetchSessionDetails()).catch(() => {});
        } else {
            preloadSessionHistory();
        }
    };
    state.eventSource.onerror = function(err) {
        console.error("EventSource failed:", err);
        state.isGenerating = false;
        state.currentTurnId = null;
        resetSendButton();
        setLogsLoading(false);
    };
}

let currentAIMessageDiv = null;
let currentGroupBalloon = null;
let currentGroupFiles = [];
let currentSessionTools = [];
let currentSessionThoughts = [];
let currentSessionQuestions = [];
let currentSessionAiResponse = '';
const wsProcessosIA = new Set();
let wsAutoMostrado = false;

if (!window._statusLinkListener) {
    window._statusLinkListener = true;
    document.addEventListener('click', (e) => {
        const link = e.target.closest('.status-link');
        if (!link) return;
        if (link.tagName === 'A' && link.getAttribute('href')) return;
        const path = link.dataset.path;
        if (path && window.WorkspaceView && typeof window.WorkspaceView.openFileFromLog === 'function') {
            window.WorkspaceView.openFileFromLog(path);
        }
    });
}


function _initCurrentGroupBalloon(titleText, isAnalysis) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    currentGroupBalloon = {
        id: 'session-' + Date.now(),
        timestamp: timeStr,
        files: [],
        tools: currentSessionTools,
        thoughts: currentSessionThoughts,
        questions: currentSessionQuestions,
        aiResponse: currentSessionAiResponse
    };
    const card = createLogGroupCard(currentGroupBalloon);
    currentGroupBalloon.timeSpan.textContent = timeStr;
    currentGroupBalloon.titleSpan.textContent = titleText;
    if (isAnalysis) {
        currentGroupBalloon.titleSpan.className = 'text-[11px] text-[var(--text-mutado)] truncate leading-tight pr-6 italic';
    }
    if (currentLogsWrapper) {
        currentLogsWrapper.insertBefore(card, currentLogsWrapper.firstChild);
    }
    state.currentTurnLogs.push(currentGroupBalloon);
    window.sessionLogsData = window.sessionLogsData || [];
    window.sessionLogsData.push(currentGroupBalloon);
    window.currentActiveLogGroup = currentGroupBalloon;
    window.currentGroupBalloon = currentGroupBalloon;
    setLogsLoading(true);
    if (currentLogsWrapper) {
        currentLogsWrapper.querySelectorAll('.log-card').forEach(el => el.classList.remove('log-card-active'));
    }
    card.classList.add('log-card-active');
}


async function tratar_status(data) {
    if (window._statusClearTimeout) {
        clearTimeout(window._statusClearTimeout);
        window._statusClearTimeout = null;
    }
    if (data.message === " " || data.message === "") {
        window._statusClearTimeout = setTimeout(() => {
            lblStatus.textContent = '';
            lblExecuting.textContent = '';
            lblExecuting.classList.remove('animate-pulse');
            window.lastStatusError = false;
            window._statusClearTimeout = null;
        }, 400);
    } else if (data.message) {
        lblExecuting.textContent = '';
        lblExecuting.classList.remove('animate-pulse');
        let text = data.message.replace(/[\r\n]+/g, ' ');
        const isNavegando = text.startsWith("Navegando: ");
        const isGrounding = text.startsWith("Grounding: ");
        const isErro = text.startsWith("Erro:");
        const limiteStatus = (isNavegando || isGrounding) ? 300 : 100;
        if (!isErro && text.length > limiteStatus) text = text.substring(0, limiteStatus) + '...';
        if (text.startsWith("Erro:")) {
            lblStatus.innerHTML = `<span class="text-red-400 font-bold">${escapeHtml(text)}</span>`;
            window.lastStatusError = true;
        } else if (isNavegando) {
            lblStatus.innerHTML = `Navegando: <span class="text-[var(--oliva)]">${_resumoNavegacao(text.substring(11))}</span>`;
            window.lastStatusError = false;
        } else if (isGrounding) {
            lblStatus.innerHTML = `Grounding: <span class="text-[var(--oliva)]">${_resumoNavegacao(text.substring(11))}</span>`;
            window.lastStatusError = false;
        } else if (text.startsWith("Extraindo informação: ")) {
            lblStatus.innerHTML = `Extraindo informação: <span class="text-[var(--oliva)]">${escapeHtml(text.substring(22))}</span>`;
            window.lastStatusError = false;
        } else {
            lblStatus.textContent = text;
            window.lastStatusError = false;
        }
    } else {
        if (!window.lastStatusError) {

            const statusAtual = (lblStatus.textContent || '').trim();
            const isFallbackGenerico = statusAtual === '' ||
                statusAtual === 'Pensando...' ||
                statusAtual === 'Raciocinando...' ||
                statusAtual === 'Enviando...';
            if (isFallbackGenerico) {
                if (lblExecuting.textContent) {
                    lblStatus.textContent = '';
                    lblExecuting.classList.add('animate-pulse');
                } else {
                    lblStatus.innerHTML =
                      '<span class="animate-pulse text-[var(--terminal)]">Raciocinando...</span>';
                }
            }
        }
    }
}
async function tratar_error(data) {

    await tratar_status(data);
    addMessage('system', data.message || 'Erro na resposta da IA.');
}
async function tratar_executing(data) {
    if (!window.lastStatusError) lblStatus.textContent = '';
    lblExecuting.classList.remove('animate-pulse');
    if (data.function) {
        let text = data.function.replace(/[\r\n]+/g, ' ');
        if (text.length > 120) text = text.substring(0, 120) + '...';
        lblExecuting.innerHTML = _formatExecutingStatus(text);
    }
}
async function tratar_tool_used_ai_thought(data) {
    if (data.type === 'tool_used') currentSessionTools.push({ name: data.name, args: data.args });
    if (data.type === 'ai_thought') currentSessionThoughts.push(data.text);
    if (!currentGroupBalloon) {
        _initCurrentGroupBalloon('Analisando...', true);
    }
    if (window.currentActiveLogGroup === currentGroupBalloon) {
        if (state.isShowingTools) {
            state.suppressCol3Anim = true;
            try { state.isShowingTools = false; btnShowTools.click(); } finally { state.suppressCol3Anim = false; }
        } else if (state.isShowingThoughts) {
            state.suppressCol3Anim = true;
            try { state.isShowingThoughts = false; btnShowThoughts.click(); } finally { state.suppressCol3Anim = false; }
        }
    }
}
async function tratar_tool_sources(data) {
    for (let i = currentSessionTools.length - 1; i >= 0; i--) {
        if (currentSessionTools[i].name === 'tool_buscar_web') {
            currentSessionTools[i].urls = data.urls || [];
            break;
        }
    }
    if (state.isShowingTools) {
        state.suppressCol3Anim = true;
        try {
            state.isShowingTools = false;
            btnShowTools.click();
        } finally { state.suppressCol3Anim = false; }
    }
}
async function tratar_metrics(data) {
    lblMetrics.textContent = data.message;
}
async function tratar_context_usage(data) {
    const pct = Math.max(0, Math.min(100, data.percent || 0));
    const emExecucao = data.fase === 'execucao';
    if (contextUsageFill) {
        const C = 100;
        contextUsageFill.style.strokeDashoffset = String(C - (C * pct / 100));
        const { cor, glow } = corDeUsoContexto(pct, emExecucao);
        contextUsageFill.style.stroke = cor;
        contextUsageFill.style.filter = 'drop-shadow(0 0 3px ' + glow + ')';
    }
    const fmtTok = _fmtTokens;
    if (contextUsageLabel) {
        let txt = `${fmtTok(data.usado)} / ${fmtTok(data.limite)} (${pct}%)`;
        if (data.compactacoes > 0) txt += ` · compactou ${data.compactacoes}x`;
        const titulo = emExecucao ? 'Memória usada na sessão' : 'Memória Acumulada';
        contextUsageLabel.innerHTML = '<span class="balao-titulo">' + titulo + ':</span> ' + escapeHtml(txt);
    }
    if (contextUsageSessao) {
        const pctSessao = Math.max(0, Math.min(100, data.percent_sessao != null ? data.percent_sessao : pct));
        const usSessao = data.usado_sessao != null ? data.usado_sessao : data.usado;
        contextUsageSessao.textContent = `${fmtTok(usSessao)} / ${fmtTok(data.limite)} (${pctSessao}%)`;
    }
    if (contextUsageAcumulada) {
        const pctAcum = Math.max(0, Math.min(100, data.percent_acumulado != null ? data.percent_acumulado : 0));
        const usAcum = data.usado_acumulado != null ? data.usado_acumulado : 0;
        contextUsageAcumulada.textContent = `${fmtTok(usAcum)} / ${fmtTok(data.limite)} (${pctAcum}%)`;
    }
    if (contextSessaoFill) {
        const pctSessao = Math.max(0, Math.min(100, data.percent_sessao != null ? data.percent_sessao : pct));
        aplicarCorBarraContexto(contextSessaoFill, pctSessao, emExecucao);
        contextSessaoFill.style.transform = 'scaleX(' + (pctSessao / 100) + ')';
    }
    if (contextAcumuladaFill) {
        const pctAcumulada = Math.max(0, Math.min(100, data.percent_acumulado != null ? data.percent_acumulado : 0));
        aplicarCorBarraContexto(contextAcumuladaFill, pctAcumulada, false);
        contextAcumuladaFill.style.transform = 'scaleX(' + (pctAcumulada / 100) + ')';
    }
    if (contextInfoLimite && data.limite) contextInfoLimite.textContent = _textoDoTeto(data.limite);
}
async function tratar_context_limit(data) {
    if (contextInfoLimite && data.limite) contextInfoLimite.textContent = _textoDoTeto(data.limite);
    if (lblStatus) lblStatus.textContent = 'Memória da rodada reajustada.';
    if (contextUsage) {
        contextUsage.classList.remove('context-usage-limite');
        void contextUsage.offsetWidth;
        contextUsage.classList.add('context-usage-limite');
        setTimeout(() => contextUsage.classList.remove('context-usage-limite'), 1600);
    }
}
async function tratar_workspace_activate() {

    if (escrevendoNoChat()) return;
    showWorkspaceView(true);
    clearTimeout(state.workspaceAutoHideTimer);
    state.workspaceAutoHideTimer = setTimeout(() => {
        if (terminalMode && !terminalMode.classList.contains('hidden')) {
            showWorkspaceView(false);
        }
    }, 4000);
}
async function tratar_process_started(data) {
    activateWorkspaceIcon(true);
    if (data.modo !== 'terminal') {
        wsProcessosIA.add(data.pid);
        clearTimeout(state.workspaceAutoHideTimer);

        if (terminalMode && terminalMode.classList.contains('hidden') && !escrevendoNoChat()) {
            wsAutoMostrado = true;
            showWorkspaceView(true);
        }
    }
}
async function tratar_process_finished(data) {
    if (wsProcessosIA.has(data.pid)) {
        wsProcessosIA.delete(data.pid);
        if (wsProcessosIA.size === 0 && wsAutoMostrado) {
            wsAutoMostrado = false;
            clearTimeout(state.workspaceAutoHideTimer);
            state.workspaceAutoHideTimer = setTimeout(() => {
                if (terminalMode && !terminalMode.classList.contains('hidden')) {
                    showWorkspaceView(false);
                }
            }, 4000);
        }
    }
}
async function tratar_ai_question(data) {
    if (!currentSessionQuestions.includes(data.text)) {
        currentSessionQuestions.push(data.text);
    }
    if (currentGroupBalloon) {
        currentGroupBalloon.questions = currentSessionQuestions;
    }
}
async function tratar_plan_started(data) {
    if (currentPlanContainer) {
        currentPlanContainer.remove();
    }
    currentPlanContainer = document.createElement('div');
    currentPlanContainer.className = 'flex flex-col gap-3 my-4 w-full max-w-3xl mx-auto';
    chatInnerRight.appendChild(currentPlanContainer);
    const stack = data.stack || null;
    if (stack) {
        currentPlanContainer.appendChild(_createStackCard(stack));
    }
    (data.plan || []).forEach((step, i) => {
        currentPlanContainer.appendChild(createPlanStepCard(step, i === 0, i === 0));
    });
    chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
}
async function tratar_plan_updated(data) {
    if (currentPlanContainer) {
        const card = currentPlanContainer.querySelector(`[data-step-id="${data.id_etapa}"]`);
        if (card) {
            const lis = card.querySelectorAll('li');
            const concluirTodas = !!data.etapa_concluida;
            lis.forEach(li => {
                const span = li.querySelector('span');
                const nome = span ? span.textContent.trim() : li.textContent.trim();
                if (concluirTodas || nome === data.tarefa_concluida) {
                    li.classList.add('line-through', 'text-[var(--text-mutado)]');
                    const circle = li.querySelector('circle');
                    if (circle) circle.setAttribute('fill', 'var(--oliva)');
                }
            });
            if (data.etapa_concluida) {
                _setStepIcon(card, 'concluido');
                const titleEl = card.querySelector('h3');
                if (titleEl) titleEl.classList.add('line-through', 'text-[var(--text-mutado)]');
                _collapseStep(card);
            } else {
                _setStepIcon(card, 'ativo');
            }
        }
    }
}
async function tratar_plan_step_added(data) {
    if (currentPlanContainer && data.step) {
        Array.from(currentPlanContainer.querySelectorAll('[data-step-id]')).forEach(_collapseStep);
        currentPlanContainer.appendChild(createPlanStepCard(data.step, true, true));
        chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
    }
}
async function tratar_ai_response(data) {
    currentSessionAiResponse = data.message;
    if (currentGroupBalloon) {
        currentGroupBalloon.aiResponse = data.message;
    }
    if (!currentAIMessageDiv) {
        currentAIMessageDiv = addMessage('ai', data.message);
        window.currentAIMessageDiv = currentAIMessageDiv;
        if (currentGroupBalloon) {
            currentAIMessageDiv.dataset.logId = currentGroupBalloon.id;
        }
    } else {
        currentAIMessageDiv.innerHTML = formatMessage(data.message, false);
        currentAIMessageDiv.querySelectorAll('pre code').forEach((block) => {
            if (typeof hljs !== 'undefined') hljs.highlightElement(block);
        });
        attachCodeBlockListeners(currentAIMessageDiv);
        chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
    }
    if (!window.lastStatusError) lblExecuting.textContent = '';
}
async function tratar_undo_changed() {

    if (typeof atualizarBotoesUndoRedo === 'function') atualizarBotoesUndoRedo();
}
async function tratar_action_diff(data) {
    if (typeof atualizarBotoesUndoRedo === 'function') atualizarBotoesUndoRedo();
    let fileName = data.actionName;
    if (fileName.indexOf(' -> ') !== -1) {
        fileName = fileName.split(' -> ').pop();
    } else if (fileName.indexOf(': ') !== -1) {
        fileName = fileName.split(': ')[1];
    }

    if (!currentGroupBalloon) {
        _initCurrentGroupBalloon('Editando...', false);
    } else {
        currentGroupBalloon.timeSpan.textContent = currentGroupBalloon.timestamp;
        currentGroupBalloon.titleSpan.classList.remove('italic', 'text-[var(--text-suave)]');
        currentGroupBalloon.titleSpan.textContent = 'Editando...';
    }
    if (currentGroupBalloon.spinner) currentGroupBalloon.spinner.classList.remove('hidden');


    if (!state.isShowingSessionHistory) {
        window.currentActiveLogGroup = currentGroupBalloon;
    }

    if (!currentGroupFiles.includes(fileName)) {
        currentGroupFiles.push(fileName);
    }
    let fileData = currentGroupBalloon.files.find(f => f.name === fileName);
    let isNewFile = false;
    if (!fileData) {
        fileData = {
            name: fileName,
            diffElements: []
        };
        isNewFile = true;
    }
    if (data.diff) {
        let snippetOriginalText = '';
        let snippetNewText = '';
        let fullOriginalText = '';
        let fullNewText = '';
        let originalHtml = '';
        let newHtml = '';
        let hasChanges = false;
        let hasDeletions = false;
        let hasAdditions = false;
        let deletedLines = [];
        let addedLines = [];
        let origToMod = [];
        let modToOrig = [];
        let origLine = 1;
        let modLine = 1;
        data.diff.forEach(part => {
            const n = countLines(part.text);
            if (part.type === 'unmodified') {
                originalHtml += `<span class="diff-unmodified">${escapeHtml(part.text)}</span>`;
                newHtml += `<span class="diff-unmodified">${escapeHtml(part.text)}</span>`;
                fullOriginalText += part.text;
                fullNewText += part.text;
                for (let k = 0; k < n; k++) {
                    origToMod[origLine + k] = modLine + k;
                    modToOrig[modLine + k] = origLine + k;
                }
                origLine += n;
                modLine += n;
            } else if (part.type === 'deleted' || part.type === 'modified') {
                originalHtml += `<span class="diff-deleted">${escapeHtml(part.text)}</span>`;
                snippetOriginalText += part.text;
                fullOriginalText += part.text;
                for (let k = 0; k < n; k++) deletedLines.push(origLine + k);
                origLine += n;
                hasChanges = true;
                hasDeletions = true;
            } else if (part.type === 'added') {
                newHtml += `<span class="diff-added">${escapeHtml(part.text)}</span>`;
                snippetNewText += part.text;
                fullNewText += part.text;
                for (let k = 0; k < n; k++) addedLines.push(modLine + k);
                modLine += n;
                hasChanges = true;
                hasAdditions = true;
            }
        });
        const snippetOriginalHtml = gerarSnippetHtml(data.diff, 'original');
        const snippetNewHtml = gerarSnippetHtml(data.diff, 'new');
        if (hasChanges) {
            if (data.actionType === 'moved') {
                const compareHtml = `<div class="diff-two-col"><div class="diff-col"><div class="diff-col-text">${originalHtml}</div></div><div class="diff-col"><div class="diff-col-text">${newHtml}</div></div></div>`;
                const compareSnippetHtml = `<div class="diff-two-col"><div class="diff-col"><div class="diff-col-text">${snippetOriginalHtml}</div></div><div class="diff-col"><div class="diff-col-text">${snippetNewHtml}</div></div></div>`;
                const nomeOrigem = (data.origem || '').replace(/\\/g, '/').split('/').pop();
                const nomeDestino = (data.destino || '').replace(/\\/g, '/').split('/').pop();
                const subtitulo = `${nomeOrigem} -> ${nomeDestino}`;
                fileData.diffElements.push(createChildBalloon('Codigo Movido', compareHtml, compareSnippetHtml, snippetOriginalText, snippetNewText, fileName, currentSessionTools, fullOriginalText, fullNewText, deletedLines, addedLines, origToMod, modToOrig, subtitulo));
            } else if (hasDeletions && hasAdditions) {
                const compareHtml = `<div class="diff-two-col"><div class="diff-col"><div class="diff-col-text">${originalHtml}</div></div><div class="diff-col"><div class="diff-col-text">${newHtml}</div></div></div>`;
                const compareSnippetHtml = `<div class="diff-two-col"><div class="diff-col"><div class="diff-col-text">${snippetOriginalHtml}</div></div><div class="diff-col"><div class="diff-col-text">${snippetNewHtml}</div></div></div>`;
                fileData.diffElements.push(createChildBalloon('Codigo Substituído', compareHtml, compareSnippetHtml, snippetOriginalText, snippetNewText, fileName, currentSessionTools, fullOriginalText, fullNewText, deletedLines, addedLines, origToMod, modToOrig));
            } else if (hasDeletions && !hasAdditions) {
                fileData.diffElements.push(createChildBalloon('Codigo Removido', originalHtml, snippetOriginalHtml, snippetOriginalText, null, fileName, currentSessionTools, fullOriginalText, fullNewText, deletedLines, addedLines, origToMod, modToOrig));
            } else if (!hasDeletions && hasAdditions) {
                const tituloNovo = data.actionType === 'created' ? 'Módulo Novo' : 'Codigo Novo';
                fileData.diffElements.push(createChildBalloon(tituloNovo, newHtml, snippetNewHtml, null, snippetNewText, fileName, currentSessionTools, fullOriginalText, fullNewText, deletedLines, addedLines, origToMod, modToOrig));
            }
        }
    }
    if (isNewFile) {
        currentGroupBalloon.files.push(fileData);
    }
    sincronizarArquivosEmTempoReal(currentGroupBalloon, fileData, isNewFile);
    if (currentLogsList) currentLogsList.scrollTop = 0;
}
function restaurarImagensDoTurno() {
    const ultimas = window.lastUserImages;
    window.lastUserImages = null;
    if (!ultimas || ultimas.length === 0) return;
    state.attachedImages = ultimas;
    renderImagePreviews();
}

async function tratar_cancel() {
    resetTurnUI();
    _pararPlanoEmCurso(currentPlanContainer);
    restaurarImagensDoTurno();
    currentAIMessageDiv = null;
    currentGroupBalloon = null;
    currentGroupFiles = [];
    currentSessionTools = [];
    currentSessionThoughts = [];
    currentSessionQuestions = [];
    currentSessionAiResponse = '';
}
async function tratar_done() {
    if (!window.lastStatusError) {
        lblStatus.textContent = 'Aguardando instrução';
    }
    lblExecuting.textContent = '';
    lblExecuting.classList.remove('animate-pulse');
    _pararPlanoEmCurso(currentPlanContainer);
    state.isGenerating = false;
    state.currentTurnId = null;
    resetSendButton();
    setLogsLoading(false);
    if (currentGroupBalloon) {
        currentGroupBalloon.timeSpan.textContent = currentGroupBalloon.timestamp;
        currentGroupBalloon.duration = Date.now() - (window.currentRoundStartedAt || epochDeId(currentGroupBalloon.id));
        currentGroupBalloon.titleSpan.innerHTML = roundMetaHtml(currentGroupBalloon);
        currentGroupBalloon.titleSpan.className = 'text-[11px] text-[var(--text-mutado)] truncate leading-tight pr-6';
        if (currentGroupBalloon.spinner) currentGroupBalloon.spinner.classList.add('hidden');
    }
    const commitsDaRodada = await saveCurrentTurnSession();
    Object.entries(commitsDaRodada || {}).forEach(([turnId, hash]) => {
        updateRoundCardCommitByTurnId(turnId, hash);
        const grupo = state.currentTurnLogs.find(g => String(g.id) === String(turnId));
        if (grupo) grupo.commit = hash;
    });
    if (window.pendingContextClear) {
        window.pendingContextClear = false;
        try {
            await fetch('/api/clear_context', { method: 'POST' });
        } catch (e) { console.error(e); }
    }

    (async () => {
        try {
            await fetchSessionHistoryData();
            prefetchSessionDetails();
        } catch (e) {
            console.error('Erro ao atualizar cache do histórico:', e);
        }
    })();
    state.currentTurnLogs = [];
    state.currentTurnSummary = '';
    currentAIMessageDiv = null;
    currentGroupBalloon = null;
    currentGroupFiles = [];
    currentSessionTools = [];
    currentSessionThoughts = [];
    currentSessionQuestions = [];
    currentSessionAiResponse = '';
    window.pendingUserQuestion = null;
    window.currentAIMessageDiv = null;
    window.currentGroupBalloon = null;
}

const HANDLERS = {
    status: tratar_status,
    executing: tratar_executing,
    tool_used: tratar_tool_used_ai_thought,
    ai_thought: tratar_tool_used_ai_thought,
    tool_sources: tratar_tool_sources,
    metrics: tratar_metrics,
    context_usage: tratar_context_usage,
    context_limit: tratar_context_limit,
    workspace_activate: tratar_workspace_activate,
    process_started: tratar_process_started,
    process_finished: tratar_process_finished,
    ai_question: tratar_ai_question,
    plan_started: tratar_plan_started,
    plan_updated: tratar_plan_updated,
    plan_step_added: tratar_plan_step_added,
    ai_response: tratar_ai_response,
    undo_changed: tratar_undo_changed,
    action_diff: tratar_action_diff,
    cancel: tratar_cancel,
    done: tratar_done,
    error: tratar_error,
};

function resetEstadoDoTurno() {
    currentAIMessageDiv = null;
    currentGroupBalloon = null;
    currentGroupFiles = [];
    currentSessionTools = [];
    currentSessionThoughts = [];
    currentSessionQuestions = [];
    currentSessionAiResponse = '';
    wsProcessosIA.clear();
    wsAutoMostrado = false;
}


    function addMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        let prefix = '';
        if (role === 'ai') {
            const agentName = 'Axio Coder';
            const agentColor = 'text-[var(--oliva)]';
            prefix = `<div class="flex items-center gap-2 mb-1"><span class="${agentColor} font-bold cursor-pointer hover:underline" onclick="event.stopPropagation(); const logId = this.closest('.message').dataset.logId; if(logId) { const log = window.sessionLogsData.find(l => l.id === logId); if(log) { if(document.getElementById('panel-log-session').classList.contains('panel-col-closed')) document.getElementById('btn-open-log').click(); setTimeout(() => log.domElement.click(), 100); } }" title="Ver análise desta resposta">${agentName}</span><button class="btn-copy-msg text-[var(--text-mutado)] hover:text-[var(--text-branco)] transition-colors" title="Copiar mensagem"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg></button></div>`;
        }
        const linhas = text.split('\n').length;
        if (role === 'user' && linhas > 7) {
            const contentDiv = document.createElement('div');
            contentDiv.className = 'overflow-hidden transition-all duration-[var(--dur-7)] relative';
            contentDiv.style.maxHeight = '150px';
            contentDiv.innerHTML = formatMessage(text, true);
            const fadeDiv = document.createElement('div');
            fadeDiv.className = 'absolute bottom-0 left-0 w-full h-16 bg-gradient-to-t from-[var(--bg)] to-transparent pointer-events-none transition-opacity duration-[var(--dur-7)]';
            contentDiv.appendChild(fadeDiv);
            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'mt-2 text-[var(--text-branco-suave)] hover:text-[var(--text-branco)] focus:outline-none w-full flex justify-center transition-colors';
            toggleBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform transition-transform duration-[var(--dur-7)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>`;
            toggleBtn.addEventListener('click', () => {
                if (contentDiv.style.maxHeight === '150px') {
                    contentDiv.style.maxHeight = 'none';
                    toggleBtn.querySelector('svg').classList.add('rotate-180');
                    fadeDiv.classList.add('opacity-0');
                    setTimeout(() => {
                        msgDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
                    }, 310);
                } else {
                    contentDiv.style.maxHeight = '150px';
                    toggleBtn.querySelector('svg').classList.remove('rotate-180');
                    fadeDiv.classList.remove('opacity-0');
                }
            });
            msgDiv.appendChild(contentDiv);
            msgDiv.appendChild(toggleBtn);
            contentDiv.querySelectorAll('pre code').forEach((block) => {
                if (typeof hljs !== 'undefined') hljs.highlightElement(block);
            });
            attachCodeBlockListeners(contentDiv);
        } else if (role === 'ai' || role === 'user') {
            msgDiv.innerHTML = prefix + formatMessage(text, role === 'user');
            if (role === 'ai') {
                const copyBtn = msgDiv.querySelector('.btn-copy-msg');
                if (copyBtn) {
                    copyBtn.addEventListener('click', () => {
                        navigator.clipboard.writeText(text);
                        const originalIcon = copyBtn.innerHTML;
                        copyBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-[var(--oliva)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
                        setTimeout(() => { copyBtn.innerHTML = originalIcon; }, 2000);
                    });
                }
            }
            msgDiv.querySelectorAll('pre code').forEach((block) => {
                if (typeof hljs !== 'undefined') hljs.highlightElement(block);
            });
            attachCodeBlockListeners(msgDiv);
        } else {
            msgDiv.textContent = text;
        }
        if (role === 'user') {
            chatInnerLeft.appendChild(msgDiv);
            chatContainerLeft.scrollTop = chatContainerLeft.scrollHeight;
        } else {
            chatInnerRight.appendChild(msgDiv);
            chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
        }
        reavaliarBuscaChat();
        return msgDiv;
    }

    const SAIDA_CONVERSA = 300;

    function limparConversa() {
        const paineis = [
            [chatInnerLeft, chatContainerLeft],
            [chatInnerRight, chatContainerRight],
        ].filter(par => par[0] && par[0].children.length);
        if (!paineis.length) return false;
        const saidas = paineis.map(par => {
            const nos = Array.from(par[0].children);
            nos.forEach(no => no.classList.add('conversa-saindo'));
            return { nos, rolagem: par[1] };
        });
        currentAIMessageDiv = null;
        currentPlanContainer = null;
        window.currentAIMessageDiv = null;
        setTimeout(() => {
            saidas.forEach(saida => {
                saida.nos.forEach(no => no.remove());
                if (saida.rolagem) saida.rolagem.scrollTop = 0;
            });
        }, SAIDA_CONVERSA);
        return true;
    }

    function attachCodeBlockListeners(container) {
        const originalCodeIcon = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>`;
        container.querySelectorAll('.copy-code-btn').forEach(btn => {
            if (btn.dataset.listenerAttached) return;
            btn.dataset.listenerAttached = 'true';
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const codeBlock = btn.closest('.code-block-container').querySelector('code');
                if (codeBlock) {
                    navigator.clipboard.writeText(codeBlock.textContent);
                    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-[var(--oliva)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
                    setTimeout(() => { btn.innerHTML = originalCodeIcon; }, 2000);
                }
            });
        });
    }
    function countLines(text) {
        if (!text) return 0;
        const parts = text.split('\n');
        if (parts.length && parts[parts.length - 1] === '') parts.pop();
        return parts.length;
    }
    
    


    function setStopButton() {
        if (btnSend) {
            btnSend.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><rect x="3" y="3" width="14" height="14" rx="2" /></svg>`;
            btnSend.classList.remove('opacity-50', 'cursor-default');
        }
    }

