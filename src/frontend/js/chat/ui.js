import { state } from './state.js';
import * as dom from './dom.js';
import { setHistoryActionButtonsVisible, updateActionButtons } from './historico/acoes.js';
import { closeCol3, closePanelCol, isHistoryOpen, isLogDockOpen, openLogDock } from './layout.js';
import { sendMessage, startSSE } from './messages.js';

const { btnClearContext, btnOpenLog, btnSend, btnSessionHistory, btnWorkspace, chatContainerLeft, chatContainerRight, chatInnerLeft, chatInnerRight, chatMode, confirmClearContextContent, confirmClearContextPopup, contextUsageLabel, contextUsagePopup, currentLogsList, currentLogsWrapper, glossaryChip, historyLogsWrapper, inputText, lblExecuting, lblFolder, lblStatus, panelCol2, termInput, terminalMode } = dom;

export const INSTRUCAO_LIMPAR_CONTEXTO = 'Salve na memória de longo prazo o que é importante desta conversa: decisões, regras, arquivos alterados e o que ficou pendente';

    function recolherContextPopup() {
        if (contextUsageLabel) contextUsageLabel.classList.remove('balao-visible');
        if (contextUsagePopup) contextUsagePopup.classList.remove('balao-visible');
        state.contextPopupExpanded = false;
    }
    function openClearContextPopup() {
        if (!confirmClearContextPopup) return;
        confirmClearContextPopup.classList.remove('opacity-0', 'pointer-events-none');
        confirmClearContextPopup.classList.add('opacity-100', 'pointer-events-auto');
        if (confirmClearContextContent) {
            confirmClearContextContent.classList.remove('scale-95');
            confirmClearContextContent.classList.add('scale-100');
        }
    }
    function closeClearContextPopup() {
        if (!confirmClearContextPopup) return;
        confirmClearContextPopup.classList.remove('opacity-100', 'pointer-events-auto');
        confirmClearContextPopup.classList.add('opacity-0', 'pointer-events-none');
        if (confirmClearContextContent) {
            confirmClearContextContent.classList.remove('scale-100');
            confirmClearContextContent.classList.add('scale-95');
        }
    }
    async function clearContextMemory() {
        closeClearContextPopup();
        if (state.isGenerating) {
            showAlert('Aguarde a conclusão da resposta atual antes de limpar o contexto.');
            return;
        }
        if (!lblFolder.textContent) {
            showAlert('Selecione uma pasta antes de limpar o contexto.');
            return;
        }
        window.pendingContextClear = true;
        const anterior = inputText.value;
        inputText.value = INSTRUCAO_LIMPAR_CONTEXTO;
        await sendMessage();
        inputText.value = anterior;
        inputText.dispatchEvent(new Event('input'));
        if (!state.isGenerating) {
            window.pendingContextClear = false;
        }
    }
    function updateClearContextButton(disabled) {
        if (!btnClearContext) return;
        btnClearContext.disabled = !!disabled;
        btnClearContext.classList.toggle('context-popup-x-disabled', !!disabled);
        btnClearContext.title = disabled ? 'Aguarde a conclusão da resposta atual' : 'Zerar memória acumulada';
    }
    function resizeChatInput() {
        if (!inputText) return;
        if (inputText.offsetParent === null) return;
        inputText.style.height = 'auto';
        inputText.style.height = inputText.scrollHeight + 'px';
    }
    function normalizarTermo(s) {
        return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    }
    async function loadGlossary() {
        try {
            const resp = await fetch('/api/glossary');
            if (resp.ok) {
                const dados = await resp.json();
                window.glossary = (dados && dados.termos) || [];
            }
        } catch (e) {
            console.log('glossary: servidor indisponivel', e);
        }
    }
    function esconderChip() {
        if (glossaryChip) glossaryChip.classList.remove('balao-visible');
        state.glossaryMatchCurrent = null;
    }
    function findGlossaryMatch(texto) {

        const alvo = normalizarTermo(texto);
        if (!alvo.trim()) return null;
        let melhor = null;
        for (const entrada of window.glossary) {
            const identNorm = normalizarTermo(entrada.identificador);
            if (identNorm && alvo.includes(identNorm)) continue;
            const candidatos = [entrada.termo].concat(entrada.aliases || []);
            for (const c of candidatos) {
                const norm = normalizarTermo(c).trim();
                if (!norm || !alvo.endsWith(norm)) continue;

                if (!melhor || norm.length > melhor.comprimento) {
                    melhor = { entrada: entrada, termoOriginal: c, comprimento: norm.length };
                }
            }
        }
        return melhor;
    }
    function showGlossaryChip() {
        const match = findGlossaryMatch(inputText.value);
        if (!match) { esconderChip(); return; }
        state.glossaryMatchCurrent = match;
        if (glossaryChip) {
            const desc = match.entrada.descricao || match.termoOriginal;
            glossaryChip.textContent = 'quer dizer ' + match.entrada.identificador + ' (' + desc + ')? [Tab]';
            glossaryChip.classList.add('balao-visible');
        }
        if (contextUsageLabel) contextUsageLabel.classList.remove('balao-visible');
    }
    function applyGlossaryChip() {
        if (!state.glossaryMatchCurrent) return;
        const match = state.glossaryMatchCurrent;
        const texto = inputText.value;

        const corte = texto.length - match.comprimento;
        if (corte >= 0) {
            inputText.value = texto.slice(0, corte) + match.entrada.identificador;
            inputText.dispatchEvent(new Event('input'));
        }
        esconderChip();
        inputText.focus();
    }
        function acharCaixaInput(input) {
            let n = input ? input.parentElement : null;
            while (n && n !== document.body) {
                const cls = (n.getAttribute && n.getAttribute('class')) || '';
                if (typeof cls === 'string' && cls.indexOf('bg-[var(--bg-input)]') !== -1) return n;
                n = n.parentElement;
            }
            return input ? input.parentElement : null;
        }
        function caixaInputAtiva() {
            const terminalAtivo = terminalMode && !terminalMode.classList.contains('hidden');
            if (terminalAtivo && termInput) return acharCaixaInput(termInput);
            if (inputText) return acharCaixaInput(inputText);
            return null;
        }
        function contextPopupVisivel() {
            return state.contextPopupExpanded || contextUsageLabel.classList.contains('balao-visible');
        }
        
        let contextAncoraAtual = null;
        let contextUsageRO = null;
        
        function posicionarContextUsageUI() {
            const caixa = caixaInputAtiva();
            if (!caixa) return;
            if (caixa !== contextAncoraAtual) {
                if (contextUsageRO) { contextUsageRO.disconnect(); contextUsageRO = null; }
                contextAncoraAtual = caixa;
                if (typeof ResizeObserver !== 'undefined') {
                    contextUsageRO = new ResizeObserver(() => {
                        if (contextPopupVisivel()) posicionarContextUsageUI();
                    });
                    contextUsageRO.observe(caixa);
                }
            }
            const br = caixa.getBoundingClientRect();
            const gap = 8;
            if (contextUsagePopup) {
                contextUsagePopup.style.width = br.width + 'px';
                const w = contextUsagePopup.offsetWidth || br.width;
                const left = Math.min(Math.max(8, br.left), Math.max(8, window.innerWidth - w - 8));
                contextUsagePopup.style.left = left + 'px';
                contextUsagePopup.style.top = '';
                contextUsagePopup.style.bottom = (window.innerHeight - br.top + gap) + 'px';
            }
            if (contextUsageLabel) {
                const lw = contextUsageLabel.offsetWidth || 320;
                const lleft = Math.min(Math.max(8, br.left), Math.max(8, window.innerWidth - lw - 8));
                contextUsageLabel.style.left = lleft + 'px';
                contextUsageLabel.style.top = '';
                contextUsageLabel.style.bottom = (window.innerHeight - br.top + gap) + 'px';
            }
        }
    export const iconTooltip = document.createElement('div');
    iconTooltip.id = 'icon-tooltip';
    iconTooltip.className = 'balao balao-fade';
    document.body.appendChild(iconTooltip);

    function posicionarIconTooltip(target) {
        const r = target.getBoundingClientRect();
        iconTooltip.style.left = '0px';
        iconTooltip.style.top = '0px';
        const w = iconTooltip.offsetWidth;
        const h = iconTooltip.offsetHeight;
        const sidebar = document.querySelector('.w-14.shrink-0');
        const inSidebar = sidebar && sidebar.contains(target);
        let left;
        let top;
        if (inSidebar) {
            left = sidebar.getBoundingClientRect().right + 8;
            top = r.top + r.height / 2 - h / 2;
            if (top < 8) top = 8;
            if (top + h > window.innerHeight - 8) top = window.innerHeight - 8 - h;
        } else {
            left = r.left + r.width / 2 - w / 2;
            top = r.top - h - 8;
            if (left < 8) left = 8;
            if (left + w > window.innerWidth - 8) left = window.innerWidth - 8 - w;
            if (top < 8) top = r.bottom + 8;
        }
        iconTooltip.style.left = left + 'px';
        iconTooltip.style.top = top + 'px';
    }
    const ICON_TOOLTIP_DELAY = 500;
    function mostrarIconTooltip(target, texto, imediato) {
        clearTimeout(state.iconTooltipTimer);
        const mostrar = () => {
            iconTooltip.textContent = texto;
            posicionarIconTooltip(target);
            iconTooltip.classList.add('balao-visible');
        };

        if (imediato) {
            mostrar();
            return;
        }
        state.iconTooltipTimer = setTimeout(mostrar, ICON_TOOLTIP_DELAY);
    }
    function esconderIconTooltip() {
        clearTimeout(state.iconTooltipTimer);
        iconTooltip.classList.remove('balao-visible');
    }
    function resetSendButton() {
        if (btnSend) {
            btnSend.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform rotate-90" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>`;
            btnSend.classList.remove('opacity-50', 'cursor-default');
        }
    }
    function resetTurnUI() {
        if (window.lastUserMessageDiv) {
            window.lastUserMessageDiv.remove();
            window.lastUserMessageDiv = null;
        }
        if (window.lastUserMessageText) {
            inputText.value = window.lastUserMessageText;
            inputText.style.height = 'auto';
            inputText.style.height = (inputText.scrollHeight) + 'px';
            window.lastUserMessageText = null;
        }
        if (window.currentGroupBalloon && window.currentGroupBalloon.domElement) {
            window.currentGroupBalloon.domElement.remove();
        }
        if (window.currentAIMessageDiv) {
            window.currentAIMessageDiv.remove();
            window.currentAIMessageDiv = null;
        }
        lblStatus.textContent = 'Aguardando instrução';
        lblExecuting.textContent = '';
        lblExecuting.classList.remove('animate-pulse');
        window.pendingUserQuestion = null;
        window.pendingContextClear = false;
        state.currentTurnLogs = [];
        state.currentTurnSummary = '';
        state.isGenerating = false;
        state.currentTurnId = null;
        resetSendButton();
        setLogsLoading(false);
        window.currentGroupBalloon = null;
    }

    function bloquearChat(ativo, opcoes) {
        const cfg = opcoes || {};
        if (inputText) {
            inputText.disabled = !!ativo;
            inputText.placeholder = ativo ? (cfg.placeholder || 'Aguarde...') : 'Digite seu comando aqui';
            if (ativo) inputText.blur();
        }
        if (btnSend) btnSend.disabled = !!ativo;
        if (cfg.classe) document.body.classList.toggle(cfg.classe, !!ativo);
        if (!lblStatus) return;
        if (ativo) {
            if (lblStatus.dataset.antesBloqueio === undefined) {
                lblStatus.dataset.antesBloqueio = lblStatus.textContent || '';
            }
            lblStatus.textContent = cfg.status || 'Aguarde...';
        } else if (lblStatus.dataset.antesBloqueio !== undefined) {
            lblStatus.textContent = lblStatus.dataset.antesBloqueio;
            delete lblStatus.dataset.antesBloqueio;
        }
    }
    function setLogsLoading(active) {
        updateClearContextButton(active);
        document.querySelectorAll('#current-logs-wrapper > div.log-pulsing').forEach(el => el.classList.remove('log-pulsing'));
        document.querySelectorAll('#current-logs-wrapper .logs-spinner').forEach(el => el.classList.add('hidden'));
        if (active) {

            const alvo = window.currentGroupBalloon;
            if (alvo && alvo.domElement) {
                alvo.domElement.classList.add('log-pulsing');
            }
            if (alvo && alvo.spinner) alvo.spinner.classList.remove('hidden');
        }
    }
    function activateWorkspaceIcon(active) {
        state.isWorkspaceActive = !!active;
        if (btnWorkspace) {
            btnWorkspace.classList.toggle('sidebar-active', state.isWorkspaceActive);
        }
    }
    function showWorkspaceView(open) {
        if (!chatMode || !terminalMode) return;
        const incoming = open ? terminalMode : chatMode;
        const outgoing = open ? chatMode : terminalMode;
        incoming.style.opacity = '0';
        incoming.classList.remove('hidden');
        incoming.classList.add('flex');
        if (open) {
            const termBox = terminalMode.querySelector('.term-input-box');
            if (termBox) {
                termBox.classList.remove('term-input-drop');
                void termBox.offsetWidth;
                termBox.classList.add('term-input-drop');
            }
            const termLog = terminalMode.querySelector('#term-log');
            if (termLog) {
                termLog.classList.remove('term-content-drop');
                void termLog.offsetWidth;
                termLog.classList.add('term-content-drop');
            }
            if (window.WorkspaceView && window.WorkspaceView.fitTerminal) {
                requestAnimationFrame(() => window.WorkspaceView.fitTerminal());
                setTimeout(() => window.WorkspaceView.fitTerminal(), 350);
            }
        } else {
            const chatScroll = chatMode.querySelector('#chat-container-left');
            if (chatScroll) {
                chatScroll.classList.remove('chat-content-up');
                void chatScroll.offsetWidth;
                chatScroll.classList.add('chat-content-up');
            }
            const chatInput = chatMode.querySelector('#input-footer-inner');
            if (chatInput) {
                chatInput.classList.remove('chat-input-up');
                void chatInput.offsetWidth;
                chatInput.classList.add('chat-input-up');
            }
        }
        requestAnimationFrame(() => {
            incoming.style.opacity = '1';
            outgoing.style.opacity = '0';
        });
        window.setTimeout(() => {
            outgoing.classList.add('hidden');
            outgoing.classList.remove('flex');
            outgoing.style.opacity = '1';
            if (!open) {
                resizeChatInput();
            }
        }, 220);
        activateWorkspaceIcon(open);
        if (window.WorkspaceView && typeof window.WorkspaceView.setActive === 'function') {
            window.WorkspaceView.setActive(open);
        }
        if (open) {
            if (window.WorkspaceView && typeof window.WorkspaceView.activate === 'function') {
                window.WorkspaceView.activate();
            }
        }
    }
    function toggleWorkspaceView() {
        if (!terminalMode) return;
        const isOpen = !terminalMode.classList.contains('hidden');
        showWorkspaceView(!isOpen);
    }

    function escrevendoNoChat() {
        const el = document.activeElement;
        if (!el || !chatMode || !chatMode.contains(el)) return false;
        return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
    }
    function syncMenuIcons() {
        if (btnOpenLog) {
            const active = isLogDockOpen();
            btnOpenLog.classList.toggle('sidebar-active', active);
        }
        if (btnSessionHistory) {
            const active = isHistoryOpen();
            btnSessionHistory.classList.toggle('sidebar-active', active);
        }
    }
    function syncWorkspaceTopBar(hidden = false) {
        if (window.WorkspaceView && typeof window.WorkspaceView.setTopBarHidden === 'function') {
            window.WorkspaceView.setTopBarHidden(hidden);
        }
    }
    function selectFirstSessionLogCard() {
        if (!currentLogsWrapper) return;
        currentLogsWrapper.querySelectorAll('.log-card').forEach(el => el.classList.remove('log-card-active'));
        const first = currentLogsWrapper.querySelector('.log-card');
        if (first) first.classList.add('log-card-active');
    }
    function renderCurrentSessionLogs(opcoes) {

        const fecharColunas = !opcoes || opcoes.fecharColunas !== false;
        state.isShowingSessionHistory = false;
        setHistoryActionButtonsVisible(false);
        state.currentSelectedHistoryGroup = null;
        state.currentSelectedHistoryEl = null;
        updateActionButtons();
        if (historyLogsWrapper) {
            historyLogsWrapper.innerHTML = '';
        }
        syncMenuIcons();
        if (fecharColunas) {
            closePanelCol(panelCol2);
            closeCol3();
        }
        if (currentLogsList) currentLogsList.scrollTop = 0;
        selectFirstSessionLogCard();
    }
    function resetWorkspaceUI() {
        window.sessionLogsData = [];
        if (currentLogsWrapper) currentLogsWrapper.innerHTML = '';
        state.currentTurnLogs = [];
        state.currentTurnSummary = '';
        state.currentCheckpointId = null;
        state.checkpointRestoredAt = 0;
        state.restoreEvents = [];
        window.currentGroupBalloon = null;
        window.currentActiveLogGroup = null;
        state.sessionHistoryLoaded = false;
        state.sessionHistoryList = [];
        state.sessionDetailCache = {};
        state.porSubirLido = false;
        state.temRemotoGit = false;
        state.commitsPorSubir = [];
        if (chatInnerLeft) chatInnerLeft.innerHTML = '';
        if (chatInnerRight) chatInnerRight.innerHTML = '';
        if (chatContainerLeft) chatContainerLeft.scrollTop = 0;
        if (chatContainerRight) chatContainerRight.scrollTop = 0;
        renderCurrentSessionLogs();
        openLogDock();

        if (state.eventSource) {
            state.eventSource.close();
        }
        startSSE();
    }
    function _openAlertPopup() {
        dom.alertPopup.classList.remove('opacity-0', 'pointer-events-none');
        dom.alertPopup.classList.add('opacity-100', 'pointer-events-auto');
        dom.alertPopupContent.classList.remove('scale-95');
        dom.alertPopupContent.classList.add('scale-100');
    }
    function showAlert(message) {
        if (dom.lblAlertMessage) dom.lblAlertMessage.textContent = message;
        _openAlertPopup();
    }
export {
    recolherContextPopup,
    openClearContextPopup,
    closeClearContextPopup,
    clearContextMemory,
    updateClearContextButton,
    resizeChatInput,
    normalizarTermo,
    loadGlossary,
    esconderChip,
    findGlossaryMatch,
    showGlossaryChip,
    applyGlossaryChip,
    acharCaixaInput,
    caixaInputAtiva,
    contextPopupVisivel,
    posicionarContextUsageUI,
    posicionarIconTooltip,
    mostrarIconTooltip,
    esconderIconTooltip,
    bloquearChat,
    toggleWorkspaceView,
    showWorkspaceView,
    escrevendoNoChat,
    activateWorkspaceIcon,
    syncMenuIcons,
    renderCurrentSessionLogs,
    syncWorkspaceTopBar,
    showAlert,
    _openAlertPopup,
    resetWorkspaceUI,
    selectFirstSessionLogCard,
    resetTurnUI,
    resetSendButton,
    setLogsLoading
};
