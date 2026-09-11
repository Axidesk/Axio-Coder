import { state } from './state.js';
import * as dom from './dom.js';
import { atualizarBotoesUndoRedo, createChildBalloon, gerarSnippetHtml, restaurarPastaSelecionada, setCodeViewContent, sincronizarArquivosEmTempoReal } from './files.js';
import { createLogGroupCard, epochDeId, fetchSessionHistoryData, prefetchSessionDetails, preloadSessionHistory, roundMetaHtml, saveCurrentTurnSession, updateRoundCardNameByTurnId } from './history.js';
import { closePlusMenus, openCol3Panel, resetCol3State } from './layout.js';
import { activateWorkspaceIcon, esconderChip, renderCurrentSessionLogs, resetSendButton, resetTurnUI, setLogsLoading, showAlert, showWorkspaceView } from './ui.js';

const { alertPopup, alertPopupContent, btnAttach, btnAttachImage, btnCopyTools, btnSend, btnShowQuestion, btnShowThoughts, btnShowTools, chatContainerLeft, chatContainerRight, chatInnerLeft, chatInnerRight, codeViewContainer, col3Title, contextAcumuladaFill, contextSessaoFill, contextUsageAcumulada, contextUsageFill, contextUsageLabel, contextUsageSessao, currentLogsList, currentLogsWrapper, expandedImg, fileInput, imagePreviewContainer, inputText, lblExecuting, lblFolder, lblMetrics, lblStatus, modal, terminalMode } = dom;

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

export {
  sendMessage,
  startSSE,
  renderThoughts,
  applyThoughtClamp,
  renderQuestions,
  renderTools,
  sortToolArgsKeys,
  showQuestionPanel,
  beginRenameRound,
  renameRound,
  addMessage,
  formatMessage,
  formatInline,
  formatInlineText,
  attachCodeBlockListeners,
  escapeHtml,
  countLines,
  renderImagePreviews,
  addImage,
  setStopButton,
};
    
// Funções de mensagens e chat
async function sendMessage() {
        if (state.isGenerating) {
            // Cancelamento instantâneo: reseta a UI na hora (como se nunca tivesse
            // enviado) e só então avisa o backend para interromper o loop, que roda
            // em thread separada e pode levar alguns segundos para perceber o cancel.
            resetTurnUI();
            startSSE();
            try {
                fetch('http://127.0.0.1:5000/api/cancel', { method: 'POST' }).catch(() => {});
            } catch (e) { console.error(e); }
            return;
        }

        let text = inputText.value.trim();

        // Filtro final: Nunca envia o código gigante como se fosse mensagem de texto
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
        
        // Mantém o checkpoint restaurado (e o riscado) até o usuário restaurar de novo.
        if (state.isShowingSessionHistory) {
            state.isShowingSessionHistory = false;
            renderCurrentSessionLogs();
        }
        setStopButton();
        setLogsLoading(true);

        // === CORREÇÃO: Cria a mensagem de texto separada da imagem ===
        // Se houver texto, cria o balão com ele. Se tiver so a imagem, cria com um espaço vazio.
        // Adiciona referências das imagens no texto se houver imagens e texto
        let messageText = text;
        const msgDiv = addMessage('user', messageText || ' ');
        window.lastUserMessageDiv = msgDiv;
        window.lastUserMessageText = text;
        
        // Anexa as imagens nativamente no DOM para burlar o escapeHtml
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
                imgNode.title = img.name; // Tooltip nativo do navegador
                imgWrapper.appendChild(imgNode);
                imgContainer.appendChild(imgWrapper);
            });
            msgDiv.appendChild(imgContainer);
        }

        // =============================================================
        state.currentTurnId = Date.now() + '-' + Math.random().toString(36).slice(2);
        const payload = { message: text, mode: state.currentMode, use_deepseek: state.selectedModel === 'deepseek', turn_id: state.currentTurnId };
        if (state.attachedImages.length > 0) {
            payload.images = state.attachedImages.map(img => ({ base64: img.base64, name: img.name }));
        }
        
        inputText.value = '';
        inputText.style.height = 'auto';
        if (typeof esconderChip === 'function') esconderChip();
        state.attachedImages = [];
        state.imageCounter = 1;
        renderImagePreviews();
        try {
            const response = await fetch('http://127.0.0.1:5000/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                if (msgDiv && msgDiv.parentNode) msgDiv.parentNode.removeChild(msgDiv);
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
        state.eventSource = new EventSource('http://127.0.0.1:5000/api/stream');
        let currentAIMessageDiv = null;
        let currentGroupBalloon = null;
        let currentGroupFiles = [];
        let currentSessionTools = [];
        let currentSessionThoughts = [];
        let currentSessionQuestions = [];
        let currentSessionAiResponse = '';
        const wsProcessosIA = new Set();
        let wsAutoMostrado = false;

        function createPlanStepCard(step, ativo = false, expandido = true) {
            const card = document.createElement('div');
            card.className = 'plan-card-in bg-[var(--bg-panel)] border border-[var(--border)] rounded-xl overflow-hidden transition-colors duration-300';
            card.dataset.stepId = step.id;
            
            const header = document.createElement('div');
            header.className = 'px-4 py-3 flex items-center justify-between bg-[var(--bg-panel-2)] cursor-pointer select-none';
            header.onclick = () => {
                const collapsible = card.querySelector('.card-collapsible');
                const chevron = card.querySelector('.step-chevron');
                if (!collapsible) return;
                const aberto = collapsible.classList.toggle('card-collapsible-open');
                chevron.style.transform = aberto ? 'rotate(180deg)' : 'rotate(0deg)';
            };
            
            const titleWrap = document.createElement('div');
            titleWrap.className = 'flex items-center gap-3';
            
            const title = document.createElement('h3');
            title.className = 'font-semibold text-[var(--text)] text-sm';
            title.textContent = step.titulo;
            
            titleWrap.appendChild(title);
            
            const rightWrap = document.createElement('div');
            rightWrap.className = 'flex items-center gap-2.5';
            
            const statusIcon = document.createElement('div');
            statusIcon.className = 'step-status-icon flex items-center justify-center w-6 h-6';
            statusIcon.innerHTML = ativo ? _iconSpinner() : _iconAguardando();
            
            const chevron = document.createElement('div');
            chevron.className = 'step-chevron transition-transform duration-200 text-[var(--text-mutado)]';
            chevron.innerHTML = `<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>`;
            if (expandido) chevron.style.transform = 'rotate(180deg)';
            
            rightWrap.appendChild(statusIcon);
            rightWrap.appendChild(chevron);
            
            header.appendChild(titleWrap);
            header.appendChild(rightWrap);
            
            const collapsible = document.createElement('div');
            collapsible.className = 'card-collapsible' + (expandido ? ' card-collapsible-open' : '');
            const clip = document.createElement('div');
            clip.className = 'card-collapsible-clip';
            const body = document.createElement('div');
            body.className = 'step-body px-4 py-3 border-t border-[var(--border)]';
            
            const ul = document.createElement('ul');
            ul.className = 'space-y-2';
            
            (step.tarefas || []).forEach(tarefa => {
                const li = document.createElement('li');
                li.className = 'flex items-start gap-2 text-sm text-[var(--text)] transition-all duration-300';
                li.innerHTML = `
                    <svg class="w-4 h-4 text-[var(--text-mutado)] shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <circle cx="12" cy="12" r="4" fill="currentColor"></circle>
                    </svg>
                    <span>${escapeHtml(tarefa)}</span>
                `;
                ul.appendChild(li);
            });
            
            body.appendChild(ul);
            clip.appendChild(body);
            collapsible.appendChild(clip);
            card.appendChild(header);
            card.appendChild(collapsible);
            
            return card;
        }

        function _createStackCard(stack) {
            const card = document.createElement('div');
            card.className = 'plan-card-in stack-card bg-[var(--bg-panel)] border border-[var(--border)] rounded-xl overflow-hidden transition-colors duration-300';
            
            const stackHeader = document.createElement('div');
            stackHeader.className = 'px-4 py-3 flex items-center justify-between bg-[var(--bg-panel-2)] cursor-pointer select-none';
            stackHeader.onclick = () => {
                const collapsible = card.querySelector('.card-collapsible');
                const chevron = card.querySelector('.stack-chevron');
                if (!collapsible) return;
                const aberto = collapsible.classList.toggle('card-collapsible-open');
                chevron.style.transform = aberto ? 'rotate(180deg)' : 'rotate(0deg)';
            };
            
            const stackTitle = document.createElement('div');
            stackTitle.className = 'flex items-center gap-2';
            stackTitle.innerHTML = `<svg class="w-4 h-4 text-[var(--azul-acao)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>`;
            const stackLabel = document.createElement('span');
            stackLabel.className = 'font-semibold text-[var(--text)] text-xs uppercase tracking-wide';
            stackLabel.textContent = 'Stack';
            stackTitle.appendChild(stackLabel);
            
            const stackChevron = document.createElement('div');
            stackChevron.className = 'stack-chevron transition-transform duration-200 text-[var(--text-mutado)]';
            stackChevron.innerHTML = `<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>`;
            
            stackHeader.appendChild(stackTitle);
            stackHeader.appendChild(stackChevron);
            
            const collapsible = document.createElement('div');
            collapsible.className = 'card-collapsible';
            const clip = document.createElement('div');
            clip.className = 'card-collapsible-clip';
            const content = document.createElement('div');
            content.className = 'stack-content px-4 py-3 space-y-2';
            
            const campos = [
                { rotulo: 'Tecnologias', valor: stack.stack, tipo: 'texto' },
                { rotulo: 'Estrutura de pastas', valor: stack.estrutura_pastas, tipo: 'arvore' },
                { rotulo: 'Referências', valor: stack.urls_pesquisadas, tipo: 'links' },
            ];
            campos.forEach(({ rotulo, valor, tipo }) => {
                if (!valor) return;
                const bloco = document.createElement('div');
                const lab = document.createElement('div');
                lab.className = 'text-[10px] font-bold text-[var(--text-mutado)] uppercase tracking-wide';
                lab.textContent = rotulo;
                const val = document.createElement('div');
                val.className = 'text-xs text-[var(--text)] leading-relaxed';
                if (tipo === 'arvore') {
                    val.className += ' font-mono whitespace-pre';
                    const linhasArvore = valor.split('\n').filter(l => l.trim());
                    const inds = [...new Set(linhasArvore.map(l => (l.match(/^\s*/) || [''])[0].length))].sort((a, b) => a - b);
                    const nivelDe = ind => inds.indexOf(ind);
                    const itens = linhasArvore.map(l => ({ n: nivelDe((l.match(/^\s*/) || [''])[0].length), nome: l.trim() }));
                    for (let i = 0; i < itens.length; i++) {
                        const { n, nome } = itens[i];
                        let prefixo = '';
                        for (let d = 0; d < n; d++) {
                            let temDepois = false;
                            for (let j = i + 1; j < itens.length; j++) {
                                if (itens[j].n < d) break;
                                if (itens[j].n === d) { temDepois = true; break; }
                            }
                            prefixo += temDepois ? '│  ' : '   ';
                        }
                        let ehUltimo = true;
                        for (let j = i + 1; j < itens.length; j++) {
                            if (itens[j].n < n) break;
                            if (itens[j].n === n) { ehUltimo = false; break; }
                        }
                        prefixo += ehUltimo ? '└─ ' : '├─ ';
                        const row = document.createElement('div');
                        row.className = 'flex items-center gap-1.5';
                        const ehPasta = nome.endsWith('/') || !/\.[a-z0-9]{1,6}$/i.test(nome);
                        row.innerHTML = `<span class="shrink-0 text-[var(--text-mutado)] whitespace-pre">${prefixo}</span><span class="shrink-0">${ehPasta ? '📁' : '📄'}</span><span>${escapeHtml(nome)}</span>`;
                        val.appendChild(row);
                    }
                } else if (tipo === 'links') {
                    val.className += ' space-y-1';
                    valor.split(/[;\n]+/).forEach(url => {
                        url = url.trim();
                        if (!url) return;
                        if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
                        let nome;
                        try { nome = new URL(url).hostname.replace(/^www\./, ''); } catch (e) { nome = url; }
                        const a = document.createElement('a');
                        a.className = 'block text-[var(--azul-acao)] hover:underline break-all';
                        a.href = url;
                        a.target = '_blank';
                        a.rel = 'noopener';
                        a.textContent = nome;
                        val.appendChild(a);
                    });
                } else {
                    val.className += ' space-y-1';
                    valor.split('\n').forEach(linha => {
                        if (!linha.trim()) return;
                        const row = document.createElement('div');
                        row.className = 'whitespace-pre-wrap break-words';
                        const idx = linha.indexOf(':');
                        if (idx > 0 && idx < 24) {
                            row.innerHTML = `<span class="font-bold">${escapeHtml(linha.slice(0, idx + 1))}</span> <span>${escapeHtml(linha.slice(idx + 1).trim())}</span>`;
                        } else {
                            row.textContent = linha.trim();
                        }
                        val.appendChild(row);
                    });
                }
                bloco.appendChild(lab);
                bloco.appendChild(val);
                content.appendChild(bloco);
            });
            
            clip.appendChild(content);
            collapsible.appendChild(clip);
            card.appendChild(stackHeader);
            card.appendChild(collapsible);
            return card;
        }

        function _iconSpinner() {
            return `<svg class="w-5 h-5 text-[var(--oliva)] animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;
        }

        function _iconAguardando() {
            return `<svg class="w-5 h-5 text-[var(--text-mutado)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="8"></circle></svg>`;
        }

        function _iconConcluido() {
            return `<svg class="w-5 h-5 text-[var(--oliva)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
        }

        function _setStepIcon(card, estado) {
            const iconContainer = card.querySelector('.step-status-icon');
            if (!iconContainer) return;
            if (estado === 'ativo') iconContainer.innerHTML = _iconSpinner();
            else if (estado === 'concluido') iconContainer.innerHTML = _iconConcluido();
            else iconContainer.innerHTML = _iconAguardando();
        }

        function _collapseStep(card) {
            const collapsible = card.querySelector('.card-collapsible');
            const chevron = card.querySelector('.step-chevron');
            if (collapsible) collapsible.classList.remove('card-collapsible-open');
            if (chevron) chevron.style.transform = 'rotate(0deg)';
        }

        const _statusFilePrefixes = [
            'Mapeando', 'Lendo arquivo', 'Lendo trecho', 'Lendo assinaturas',
            'Substituindo texto', 'Salvando Arquivo', 'Excluindo',
            'Substituindo tudo em', 'Desfazendo', 'Refazendo', 'Validando sintaxe',
            'Auditando código', 'Auditando similaridade'
        ];

        function _formatExecutingStatus(text) {
            const idx = text.indexOf(': ');
            if (idx === -1) return escapeHtml(text);
            const prefixo = text.substring(0, idx);
            const restante = text.substring(idx + 2);
            if (_statusFilePrefixes.includes(prefixo) && restante) {
                return `${escapeHtml(prefixo)}: <span class="status-link" data-path="${escapeHtml(restante)}">${escapeHtml(restante)}</span>`;
            }
            return `${escapeHtml(prefixo)}: <span class="text-[var(--oliva)]">${escapeHtml(restante)}</span>`;
        }

        function _resumoNavegacao(texto) {
            if (/^pesquisando /i.test(texto)) return escapeHtml(texto);
            const urls = texto.match(/https?:\/\/[^\s,;]+/g);
            if (!urls) return escapeHtml(texto);
            const vistos = [];
            const partes = [];
            urls.forEach(u => {
                let d;
                try { d = new URL(u).hostname.replace(/^www\./, ''); } catch (e) { d = u; }
                if (vistos.includes(d)) return;
                vistos.push(d);
                partes.push(`<a class="status-link" href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer">${escapeHtml(d)}</a>`);
            });
            return partes.join(', ');
        }

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

        state.eventSource.onmessage = async function(event) {
            // Ignora heartbeats SSE (comentários sem data)
            if (!event.data || event.data.trim() === '') return;
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return; // ignora payloads inválidos (heartbeats, etc)
            }
            // Descarta eventos atrasados de um turno antigo (cancelado/substituído).
            if (data.turn_id && data.turn_id !== state.currentTurnId) return;
            if (window.WorkspaceView && typeof window.WorkspaceView.onSSE === 'function') {
                window.WorkspaceView.onSSE(data);
            }
            if (window.pendingUserQuestion && currentSessionQuestions.length === 0) {
                currentSessionQuestions.push(window.pendingUserQuestion);
                window.pendingUserQuestion = null;
            }
        if (data.type === 'status') {
                // Cancela qualquer debounce pendente de limpeza
                if (window._statusClearTimeout) {
                    clearTimeout(window._statusClearTimeout);
                    window._statusClearTimeout = null;
                }
                if (data.message === " " || data.message === "") {
                    // DEBOUNCE: so limpa após 400ms sem novo status
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
                        // Ferramentas têm prioridade sobre o fallback de raciocínio: mantém o status
                        // atual da ferramenta visível e só mostra "Raciocinando..." quando não há
                        // nenhum status de ferramenta ativo (fallback puro).
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
            } else if (data.type === 'executing') {
                if (!window.lastStatusError) lblStatus.textContent = '';
                lblExecuting.classList.remove('animate-pulse');
                if (data.function) {
                    let text = data.function.replace(/[\r\n]+/g, ' ');
                    if (text.length > 120) text = text.substring(0, 120) + '...';
                    lblExecuting.innerHTML = _formatExecutingStatus(text);
                }
                } else if (data.type === 'tool_used' || data.type === 'ai_thought') {
                if (data.type === 'tool_used') currentSessionTools.push({ name: data.name, args: data.args });
                if (data.type === 'ai_thought') currentSessionThoughts.push(data.text);
                // 1. Cria o balão de log imediatamente para leitura/pensamento (sem esperar edição)
                if (!currentGroupBalloon) {
                    _initCurrentGroupBalloon('Analisando...', true);
                }
                // 2. Atualiza os painéis "Ferramentas" e "Pensamentos" em tempo real (Auto-refresh)
                if (window.currentActiveLogGroup === currentGroupBalloon) {
                    if (state.isShowingTools) {
                        state.suppressCol3Anim = true;
                        try { state.isShowingTools = false; btnShowTools.click(); } finally { state.suppressCol3Anim = false; }
                    } else if (state.isShowingThoughts) {
                        state.suppressCol3Anim = true;
                        try { state.isShowingThoughts = false; btnShowThoughts.click(); } finally { state.suppressCol3Anim = false; }
                    }
                }
            } else if (data.type === 'tool_sources') {
                // Anexa as URLs visitadas à última ferramenta tool_buscar_web registrada
                for (let i = currentSessionTools.length - 1; i >= 0; i--) {
                    if (currentSessionTools[i].name === 'tool_buscar_web') {
                        currentSessionTools[i].urls = data.urls || [];
                        break;
                    }
                }
                // Se o painel de ferramentas estiver aberto, re-renderiza
                if (state.isShowingTools) {
                    state.suppressCol3Anim = true;
                    try {
                        state.isShowingTools = false;
                        btnShowTools.click();
                    } finally { state.suppressCol3Anim = false; }
                }
            } else if (data.type === 'metrics') {
                lblMetrics.textContent = data.message;
            } else if (data.type === 'context_usage') {
                const pct = Math.max(0, Math.min(100, data.percent || 0));
                const emExecucao = data.fase === 'execucao';
                if (contextUsageFill) {
                    const C = 100;
                    contextUsageFill.style.strokeDashoffset = String(C - (C * pct / 100));
                    const { cor, glow } = corDeUsoContexto(pct, emExecucao);
                    contextUsageFill.style.stroke = cor;
                    contextUsageFill.style.filter = 'drop-shadow(0 0 3px ' + glow + ')';
                }
                const fmtTok = (n) => n >= 1000000 ? (n / 1000000).toFixed(1) + 'M' : n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
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
            } else if (data.type === 'workspace_activate') {
                showWorkspaceView(true);
                clearTimeout(state.workspaceAutoHideTimer);
                state.workspaceAutoHideTimer = setTimeout(() => {
                    if (terminalMode && !terminalMode.classList.contains('hidden')) {
                        showWorkspaceView(false);
                    }
                }, 4000);
            } else if (data.type === 'process_started') {
                activateWorkspaceIcon(true);
                if (data.modo !== 'terminal') {
                    wsProcessosIA.add(data.pid);
                    clearTimeout(state.workspaceAutoHideTimer);
                    if (terminalMode && terminalMode.classList.contains('hidden')) {
                        wsAutoMostrado = true;
                        showWorkspaceView(true);
                    }
                }
            } else if (data.type === 'process_finished') {
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
            } else if (data.type === 'ai_question') {
                // Registra a pergunta/resposta final da IA no card de log do turno.
                if (!currentSessionQuestions.includes(data.text)) {
                    currentSessionQuestions.push(data.text);
                }
                if (currentGroupBalloon) {
                    currentGroupBalloon.questions = currentSessionQuestions;
                }
            } else if (data.type === 'plan_started') {
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
            } else if (data.type === 'plan_updated') {
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
            } else if (data.type === 'plan_step_added') {
                if (currentPlanContainer && data.step) {
                    Array.from(currentPlanContainer.querySelectorAll('[data-step-id]')).forEach(_collapseStep);
                    currentPlanContainer.appendChild(createPlanStepCard(data.step, true, true));
                    chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
                }
            } else if (data.type === 'ai_response') {
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
                    // Atualizar mensagem existente (se for streaming de texto)
                    currentAIMessageDiv.innerHTML = formatMessage(data.message, false);
                    currentAIMessageDiv.querySelectorAll('pre code').forEach((block) => {
                        if (typeof hljs !== 'undefined') hljs.highlightElement(block);
                    });
                    attachCodeBlockListeners(currentAIMessageDiv);
                    chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
                }
                if (!window.lastStatusError) lblExecuting.textContent = '';
            } else if (data.type === 'undo_changed') {
                // O agente desfez/refez uma edição durante a execução: recarrega o
                // estado das pilhas e reaplica o riscado nos cards da pilha de ficheiros.
                if (typeof atualizarBotoesUndoRedo === 'function') atualizarBotoesUndoRedo();
            } else if (data.type === 'action_diff') {
                // Uma nova edição altera as pilhas de undo/redo -> atualiza os botões
                if (typeof atualizarBotoesUndoRedo === 'function') atualizarBotoesUndoRedo();
                let fileName = data.actionName;
                if (fileName.indexOf(' -> ') !== -1) {
                    fileName = fileName.split(' -> ').pop();
                } else if (fileName.indexOf(': ') !== -1) {
                    fileName = fileName.split(': ')[1];
                }
                // Ao começar a editar, o card muda para "Editando..." e o spinner
                // passa a aparecer dentro do card (canto direito), em vez do topo.
                if (!currentGroupBalloon) {
                    _initCurrentGroupBalloon('Editando...', false);
                } else {
                    currentGroupBalloon.timeSpan.textContent = currentGroupBalloon.timestamp;
                    currentGroupBalloon.titleSpan.classList.remove('italic', 'text-[var(--text-suave)]');
                    currentGroupBalloon.titleSpan.textContent = 'Editando...';
                }
                // Spinner dentro do card (canto direito), sem spinner no topo
                if (currentGroupBalloon.spinner) currentGroupBalloon.spinner.classList.remove('hidden');
                
                // Garante que a coluna de arquivos acompanhe o turno atual em tempo real,
                // mesmo se o usuário navegou antes por cards do histórico (que trocam o grupo ativo).
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
                // Atualiza a coluna de arquivos em tempo real, caso o card ativo
                // seja o do turno atual (evita precisar clicar de novo no card).
                sincronizarArquivosEmTempoReal(currentGroupBalloon, fileData, isNewFile);
                if (currentLogsList) currentLogsList.scrollTop = 0;
            } else if (data.type === 'cancel') {
                resetTurnUI();
                currentAIMessageDiv = null;
                currentGroupBalloon = null;
                currentGroupFiles = [];
                currentSessionTools = [];
                currentSessionThoughts = [];
                currentSessionQuestions = [];
                currentSessionAiResponse = '';
            } else if (data.type === 'done') {
                if (!window.lastStatusError) {
                    lblStatus.textContent = 'Aguardando instrução';
                }
                lblExecuting.textContent = '';
                lblExecuting.classList.remove('animate-pulse');
                state.isGenerating = false;
                state.currentTurnId = null;
                resetSendButton();
                setLogsLoading(false);
                // --- NOVA LÓGICA: Finaliza o card conforme o que aconteceu no turno ---
                if (currentGroupBalloon) {
                    currentGroupBalloon.timeSpan.textContent = currentGroupBalloon.timestamp;
                    currentGroupBalloon.duration = Date.now() - (window.currentRoundStartedAt || epochDeId(currentGroupBalloon.id));
                    currentGroupBalloon.titleSpan.innerHTML = roundMetaHtml(currentGroupBalloon);
                    currentGroupBalloon.titleSpan.className = 'text-[11px] text-[var(--text-mutado)] truncate leading-tight pr-6';
                    if (currentGroupBalloon.spinner) currentGroupBalloon.spinner.classList.add('hidden');
                }
                // ----------------------------------------------------------------------
                await saveCurrentTurnSession();
                if (window.pendingContextClear) {
                    window.pendingContextClear = false;
                    try {
                        await fetch('http://127.0.0.1:5000/api/clear_context', { method: 'POST' });
                    } catch (e) { console.error(e); }
                }
                // Atualiza o cache do histórico em segundo plano (sem re-renderizar a UI),
                // para que a proxima abertura da aba reflita a nova rodada salva
                // (incluindo a possível rotação de dia feita no backend).
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
        };
        state.eventSource.onopen = function() {
            // Conexão SSE (re)estabelecida: garante o cache do histórico
            // populado para a aba abrir instantaneamente após restart do Flask.
            restaurarPastaSelecionada();
            if (state.sessionHistoryLoaded) {
                fetchSessionHistoryData().then(() => prefetchSessionDetails()).catch(() => {});
            } else {
                preloadSessionHistory();
            }
        };
        state.eventSource.onerror = function(err) {
            console.error("EventSource failed:", err);
            // Não fechamos a conexão para permitir reconexão automática
            state.isGenerating = false;
            state.currentTurnId = null;
            resetSendButton();
            setLogsLoading(false);
        };
    }
    function renderThoughts() {
        let thoughtsHtml = '';
        if (!state.currentViewingThoughts || state.currentViewingThoughts.length === 0) {
            thoughtsHtml = '<div class="text-[var(--text-mutado)] italic">Nenhum raciocínio registrado neste turno.</div>';
        } else {
            thoughtsHtml = '<div class="thought-clamp-wrap"><div class="thought-clamp-body flex flex-col gap-6">';
            state.currentViewingThoughts.forEach(t => {
                // Converte strings literais \n para quebras de linha reais e remove \n\n literais
                t = t.replace(/\\n\\n/g, ' ').replace(/\\n/g, '\n');
                let formattedText = formatMessage(t, true);
                // Captura o <strong> no início, cria uma div com título maior e mais claro,
                // e remove os <br> excedentes que geravam o buraco vazio.
                formattedText = formattedText.replace(/^<strong>(.*?)<\/strong>(?:<br>|\s)*/i, '<div class="text-[var(--text-label)] font-bold text-[15px] mb-1">$1</div>');
                thoughtsHtml += `<div class="text-[var(--text-claro)] text-sm leading-relaxed">${formattedText}</div>`;
            });
            thoughtsHtml += '</div>';
            thoughtsHtml += '<button class="thought-toggle hidden text-[var(--oliva)] hover:underline text-sm font-semibold focus:outline-none mt-3">Ver mais</button>';
            thoughtsHtml += '</div>';
        }
        setCodeViewContent(thoughtsHtml);
        applyThoughtClamp();
    }
    function applyThoughtClamp() {
        const body = codeViewContainer.querySelector('.thought-clamp-body');
        const btn = codeViewContainer.querySelector('.thought-toggle');
        if (!body || !btn) return;
        let lineH = 23;
        const sample = body.querySelector('div');
        if (sample) {
            const lh = parseFloat(getComputedStyle(sample).lineHeight);
            if (!isNaN(lh) && lh > 0) lineH = lh;
        }
        const THOUGHT_MAX_H = Math.round(lineH * 30);
        const setClamped = (clamped) => {
            if (clamped) {
                body.classList.add('thought-clamped');
                body.style.maxHeight = THOUGHT_MAX_H + 'px';
                btn.textContent = 'Ver mais';
            } else {
                body.classList.remove('thought-clamped');
                body.style.maxHeight = body.scrollHeight + 'px';
                btn.textContent = 'Ver menos';
            }
            state.thoughtsExpanded = !clamped;
        };
        body.style.maxHeight = '';
        if (body.scrollHeight <= THOUGHT_MAX_H) {
            btn.classList.add('hidden');
            body.classList.remove('thought-clamped');
            state.thoughtsExpanded = false;
            return;
        }
        setClamped(!state.thoughtsExpanded);
        btn.classList.remove('hidden');
        btn.onclick = () => {
            setClamped(!body.classList.contains('thought-clamped'));
        };
    }
    function renderQuestions() {
        let questionsHtml = '<div class="flex flex-col gap-6">';
        if (!state.currentViewingQuestions || state.currentViewingQuestions.length === 0) {
            questionsHtml += '<div class="text-[var(--text-mutado)] italic">Nenhuma pergunta registrada neste turno.</div>';
        } else {
            state.currentViewingQuestions.forEach((q, idx) => {
                const formattedText = formatMessage(q, true);
                questionsHtml += `<div class="text-[var(--text-claro)] text-sm leading-relaxed">${formattedText}`;
                if (idx === state.currentViewingQuestions.length - 1 && state.currentViewingAiResponse) {
                    const resposta = formatMessage(state.currentViewingAiResponse, true);
                    questionsHtml += `<div class="mt-1 text-left whitespace-normal"><button id="btn-toggle-ai-answer" class="text-[var(--oliva)] hover:underline text-sm font-semibold focus:outline-none">Ver Resposta</button><div id="ai-answer-wrap" class="ai-answer-wrap"><div class="ai-answer-inner"><div class="mt-1 border-t border-[var(--border)] pt-1"><div class="text-[var(--text)] text-sm leading-relaxed">${resposta}</div><button id="btn-toggle-ai-answer-less" class="mt-1 text-[var(--oliva)] hover:underline text-sm font-semibold focus:outline-none">Ver menos</button></div></div></div></div>`;
                }
                questionsHtml += `</div>`;
            });
        }
        questionsHtml += "</div>";

        setCodeViewContent(questionsHtml);

        const wrap = document.getElementById('ai-answer-wrap');
        const btnToggle = document.getElementById('btn-toggle-ai-answer');
        const btnToggleLess = document.getElementById('btn-toggle-ai-answer-less');
        
        function setAiAnswerExpanded(expanded) {
            if (!wrap) return;
            if (expanded) {
                if (btnToggle) btnToggle.classList.add('hidden');
                wrap.classList.add('ai-answer-open');
            } else {
                wrap.classList.remove('ai-answer-open');
            }
        }
        if (btnToggle) btnToggle.addEventListener('click', () => setAiAnswerExpanded(true));
        if (btnToggleLess) btnToggleLess.addEventListener('click', () => setAiAnswerExpanded(false));
        if (wrap) wrap.addEventListener('transitionend', (e) => {
            if (e.propertyName === 'grid-template-rows' && !wrap.classList.contains('ai-answer-open')) {
                if (btnToggle) btnToggle.classList.remove('hidden');
            }
        });
    }
    function sortToolArgsKeys(keys) {
        const ordemChaves = ['caminho_relativo', 'linha_inicio', 'linha_fim', 'termo', 'comando', 'texto_antigo', 'texto_novo', 'conteudo'];
        return keys.sort((a, b) => {
            let posA = ordemChaves.indexOf(a);
            let posB = ordemChaves.indexOf(b);
            if (posA === -1) posA = 999;
            if (posB === -1) posB = 999;
            return posA - posB;
        });
    }
    function renderTools() {
        let toolsHtml = '<div class="space-y-4">';
        if (!state.currentViewingTools || state.currentViewingTools.length === 0) {
            toolsHtml += '<div class="text-[var(--text-mutado)] italic">Nenhuma ferramenta associada a este turno.</div>';
        } else {
            state.currentViewingTools.forEach(t => {
                toolsHtml += `<div class="flex flex-col gap-1.5">`;
                toolsHtml += `<div class="text-[var(--oliva)] font-bold text-sm tracking-wide">FERRAMENTA: ${t.name}</div>`;
                if (t.args && Object.keys(t.args).length > 0) {
                    const chavesOrdenadas = sortToolArgsKeys(Object.keys(t.args));
                    chavesOrdenadas.forEach(key => {
                        let val = t.args[key];
                        let displayVal = val;
                        if (key === 'texto_antigo' || key === 'texto_novo' || key === 'conteudo') {
                            const escapedCode = val.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                            displayVal = `<a href="#" class="text-[var(--oliva)] hover:underline" onclick="const codeEl = this.nextElementSibling; if(codeEl.classList.contains('hidden')){codeEl.classList.remove('hidden'); this.textContent='[Recolher]';}else{codeEl.classList.add('hidden'); this.textContent='[Ver Codigo]';}; return false;">[Ver Codigo]</a><div class="hidden mt-2 p-3 bg-[var(--bg)] rounded font-mono text-xs whitespace-pre-wrap text-[var(--text-claro)] border border-[var(--border)] max-h-64 overflow-y-auto custom-scrollbar">${escapedCode}</div>`;
                        } else if (typeof val === 'string') {
                            displayVal = val.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                        } else {
                            displayVal = JSON.stringify(val);
                        }
                        toolsHtml += `<div class="text-[var(--text-suave)] text-xs font-mono ml-4"><span class="text-[var(--text-mutado)]">-&gt;</span> ${key}: <span class="text-[var(--text-claro)]">${displayVal}</span></div>`;
                    });
                } else {
                    toolsHtml += `<div class="text-[var(--text-suave)] text-xs font-mono ml-4"><span class="text-[var(--text-mutado)]">-&gt;</span> Sem argumentos (Chamada simples)</div>`;
                }
                if (t.urls && t.urls.length > 0) {
                    const urlItems = t.urls.map(url =>
                        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="block text-[var(--oliva)] hover:underline break-all font-mono text-xs py-1" title="${escapeHtml(url)}">${escapeHtml(url)}</a>`
                    ).join('');
                    toolsHtml += `<div class="text-[var(--text-suave)] text-xs font-mono ml-4"><span class="text-[var(--text-mutado)]">-&gt;</span> `;
                    toolsHtml += `<a href="#" class="text-[var(--oliva)] hover:underline" onclick="const box=this.nextElementSibling; if(box.classList.contains('hidden')){box.classList.remove('hidden'); this.textContent='[Recolher fontes]';}else{box.classList.add('hidden'); this.textContent='[Ver ${t.urls.length} fonte(s)]';}; return false;">[Ver ${t.urls.length} fonte(s)]</a>`;
                    toolsHtml += `<div class="hidden mt-2 p-3 bg-[var(--bg)] rounded border border-[var(--border)] max-h-64 overflow-y-auto custom-scrollbar">${urlItems}</div>`;
                    toolsHtml += `</div>`;
                }
                toolsHtml += `<hr class="border-[var(--border)] mt-3 mb-1 w-1/2">`;
                toolsHtml += `</div>`;
            });
        }
        toolsHtml += '</div>';
        setCodeViewContent(toolsHtml);
    }
    function showQuestionPanel(group) {
        resetCol3State();
        state.isShowingQuestions = true;
        openCol3Panel();
        if (btnShowQuestion) {
            btnShowQuestion.classList.remove("text-[var(--text-mutado)]");
            btnShowQuestion.classList.add("text-[var(--oliva)]");
        }
        if (btnCopyTools) btnCopyTools.classList.remove("hidden");
        const nome = (group && (group.displayName || group.name)) || "Pergunta do Usuário";
        col3Title.textContent = nome;
        col3Title.onclick = null;
        if (group && (group.displayName || group.name)) {
            col3Title.classList.remove("text-[var(--text)]");
            col3Title.classList.add("cursor-pointer", "hover:underline", "text-[var(--oliva)]");
            col3Title.title = "Clique duas vezes para renomear a rodada";
            col3Title.ondblclick = () => beginRenameRound(group);
        } else {
            col3Title.ondblclick = null;
            col3Title.title = "";
        }
        renderQuestions();
    }
    function beginRenameRound(group) {
        const atual = group.displayName || group.name || "Taref     a";
        const input = document.createElement("input");
        input.type = "text";
        input.value = atual;
        input.className = "bg-[var(--bg)] border border-[var(--border)] rounded px-2 py-1 text-sm text-[var(--text)] focus:outline-none focus:border-[var(--oliva)] w-full";
        col3Title.innerHTML = "";
        col3Title.appendChild(input);
        input.focus();
        input.select();
        let finalizado = false;
        const commit = async () => {
            if (finalizado) return;
            finalizado = true;
            const novoNome = input.value.trim() || atual;
            col3Title.textContent = novoNome;
            await renameRound(group, novoNome);
        };
        const cancelar = () => {
            if (finalizado) return;
            finalizado = true;
            col3Title.textContent = atual;
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
        // Atualiza o cache de detalhes para não perder o novo nome em re-renderizações.
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
            await fetch('http://127.0.0.1:5000/api/session_log/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ round_id: group.id, name: novoNome })
            });
        } catch (e) {
            console.error('Erro ao renomear rodada:', e);
        }
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
            fadeDiv.className = 'absolute bottom-0 left-0 w-full h-16 bg-gradient-to-t from-[var(--bg)] to-[var(--bg)]/0 pointer-events-none transition-opacity duration-[var(--dur-7)]';
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
        return msgDiv;
    }
    function formatMessage(text, escape = false) {
        if (escape) {
            text = escapeHtml(text);
        }
        const parts = text.split(/(```[\s\S]*?```)/g);
        for (let i = 0; i < parts.length; i++) {
            if (parts[i].startsWith('```') && parts[i].endsWith('```')) {
                const match = parts[i].match(/```(\w+)?\n([\s\S]*?)```/);
                let lang = '';
                let code = '';
                if (match) {
                    lang = match[1] || 'text';
                    code = escapeHtml(match[2]);
                } else {
                    code = escapeHtml(parts[i].slice(3, -3));
                    lang = 'text';
                }
                const displayLang = lang === 'text' ? 'Codigo' : lang;
                const headerHtml = `<div class="flex justify-between items-center px-4 py-2 bg-[var(--bg-hover)] text-xs text-[var(--text-claro)] font-sans border-b border-[var(--border)]"><span class="capitalize">${displayLang}</span><button class="copy-code-btn text-[var(--text-suave)] hover:text-[var(--text-branco)] transition-colors focus:outline-none" title="Copiar código"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg></button></div>`;
                parts[i] = `<div class="code-block-container bg-[var(--bg-panel)] rounded-xl overflow-hidden mt-0 mb-1">${headerHtml}<div class="p-4 overflow-x-auto custom-scrollbar"><pre><code class="language-${lang}">${code}</code></pre></div></div>`;
                } else {
                    parts[i] = formatInlineText(parts[i]);
                }
        }
        return parts.join('');
    }
    function isTableSeparator(line) {
        const s = line.trim();
        return s.includes('|') && s.includes('-') && /^[\s|:\-]+$/.test(s);
    }
    function splitTableRow(line) {
        let s = line.trim();
        if (s.startsWith('|')) s = s.slice(1);
        if (s.endsWith('|')) s = s.slice(0, -1);
        return s.split('|').map(c => c.trim());
    }
    function renderTableBlock(block) {
        const lines = block.split('\n').filter(l => l.trim() !== '');
        if (lines.length < 2) return null;
        if (!isTableSeparator(lines[1])) return null;
        const headerCells = splitTableRow(lines[0]);
        if (!headerCells.length) return null;
        const sepCells = splitTableRow(lines[1]);
        const aligns = sepCells.map(c => {
            const t = c.trim();
            if (t.startsWith(':') && t.endsWith(':')) return 'center';
            if (t.endsWith(':')) return 'right';
            if (t.startsWith(':')) return 'left';
            return '';
        });
        let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
        headerCells.forEach((c, i) => {
            const a = aligns[i] ? ` style="text-align:${aligns[i]}"` : '';
            html += `<th${a}>${formatInline(c)}</th>`;
        });
        html += '</tr></thead><tbody>';
        for (let i = 2; i < lines.length; i++) {
            const cells = splitTableRow(lines[i]);
            html += '<tr>';
            for (let j = 0; j < headerCells.length; j++) {
                const a = aligns[j] ? ` style="text-align:${aligns[j]}"` : '';
                html += `<td${a}>${formatInline(cells[j] || '')}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        return html;
    }
    function formatInlineText(text) {
        const lines = text.split('\n');
        const out = [];
        let buffer = [];
        let i = 0;
        while (i < lines.length) {
            if (lines[i].includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
                if (buffer.length) {
                    out.push(processInlineBlock(buffer.join('\n')));
                    buffer = [];
                }
                let end = i + 2;
                while (end < lines.length && lines[end].includes('|')) end++;
                const block = lines.slice(i, end).join('\n');
                const tableHtml = renderTableBlock(block);
                out.push(tableHtml || formatInline(block).replace(/\n/g, '<br>'));
                i = end;
            } else {
                buffer.push(lines[i]);
                i++;
            }
        }
        if (buffer.length) {
            out.push(processInlineBlock(buffer.join('\n')));
        }
        return out.join('');
    }
    function processInlineBlock(text) {
        const niveis = { 1: 'text-2xl font-bold mt-5 mb-3', 2: 'text-xl font-bold mt-4 mb-2', 3: 'text-lg font-bold mt-4 mb-2', 4: 'text-base font-bold mt-3 mb-1', 5: 'text-sm font-bold mt-3 mb-1', 6: 'text-sm font-bold mt-3 mb-1' };
        const linhas = text.split('\n');
        const out = [];
        let buffer = [];
        let lista = null;
        const flush = () => { if (buffer.length) { out.push(formatInline(buffer.join('\n')).replace(/\n/g, '<br>')); buffer = []; } };
        const fecharLista = () => { if (lista) { out.push(`</${lista}>`); lista = null; } };
        for (const linha of linhas) {
            const h = linha.match(/^(#{1,6})\s+(.*)$/);
            if (h) {
                flush();
                fecharLista();
                const nivel = h[1].length;
                out.push(`<h${nivel} class="${niveis[nivel]}">${formatInline(h[2])}</h${nivel}>`);
                continue;
            }
            const b = linha.match(/^\s*[-*]\s+(.*)$/);
            if (b) {
                flush();
                if (lista !== 'ul') { fecharLista(); out.push('<ul class="list-disc pl-5 my-1 space-y-0.5">'); lista = 'ul'; }
                out.push(`<li>${formatInline(b[1])}</li>`);
                continue;
            }
            const n = linha.match(/^\s*\d+[.)]\s+(.*)$/);
            if (n) {
                flush();
                if (lista !== 'ol') { fecharLista(); out.push('<ol class="list-decimal pl-5 my-1 space-y-0.5">'); lista = 'ol'; }
                out.push(`<li>${formatInline(n[1])}</li>`);
                continue;
            }
            fecharLista();
            buffer.push(linha);
        }
        flush();
        fecharLista();
        return out.join('');
    }
    function attachCodeBlockListeners(container) {
        // Ícone fixo
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
                    // Restaura usando a variável fixa
                    setTimeout(() => { btn.innerHTML = originalCodeIcon; }, 2000);
                }
            });
        });
    }
    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
    function countLines(text) {
        if (!text) return 0;
        const parts = text.split('\n');
        if (parts.length && parts[parts.length - 1] === '') parts.pop();
        return parts.length;
    }
    
 // Array of { base64, dataUrl, name }
    
    function renderImagePreviews() {
        imagePreviewContainer.innerHTML = '';
        if (state.attachedImages.length === 0) {
            imagePreviewContainer.classList.add('hidden');
            return;
        }
        imagePreviewContainer.classList.remove('hidden');
        state.attachedImages.forEach((img, index) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'relative inline-block w-20 h-20 group';
            const imgEl = document.createElement('img');
            imgEl.className = 'w-full h-full object-cover rounded-lg border border-[var(--border-suave)]';
            imgEl.src = img.dataUrl;
            imgEl.title = img.name;
            const btnRemove = document.createElement('button');
            btnRemove.className = 'absolute -top-2 -right-2 bg-[var(--perigo)] text-[var(--text-branco)] rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-[var(--vermelho-excluir-hover)] focus:outline-none opacity-0 group-hover:opacity-100 transition-opacity';
            btnRemove.innerHTML = '✕';
            btnRemove.onclick = () => {
                state.attachedImages.splice(index, 1);
                renderImagePreviews();
            };
            wrapper.appendChild(imgEl);
            wrapper.appendChild(btnRemove);
            imagePreviewContainer.appendChild(wrapper);
        });
    }

    function addImage(file) {
        const reader = new FileReader();
        reader.onload = (readerEvent) => {
            const dataUrl = readerEvent.target.result;
            const base64 = dataUrl.split(',')[1];
            const name = `imagem${state.imageCounter++}`;
            state.attachedImages.push({ base64, dataUrl, name });
            renderImagePreviews();
        };
        reader.readAsDataURL(file);
    }

    if (btnAttach) {
        btnAttach.addEventListener('click', () => {
            fileInput.click();
        });
    }

    if (btnAttachImage) {
        btnAttachImage.addEventListener('click', () => {
            closePlusMenus();
            fileInput.click();
        });
    }

    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        for (let i = 0; i < files.length; i++) {
            addImage(files[i]);
        }
        fileInput.value = ''; // Reset input
    });

    // === NOVO CÓDIGO: CAPTURA DE CTRL+V (COLAR IMAGEM) ===
    inputText.addEventListener('paste', (e) => {
        const clipboardData = e.clipboardData || window.clipboardData;
        if (!clipboardData) return;
        let imagePasted = false;
        for (let i = 0; i < clipboardData.items.length; i++) {
            const item = clipboardData.items[i];
            if (item.type.indexOf('image/') !== -1) {
                imagePasted = true;
                e.preventDefault(); // Bloqueio total: proíbe o navegador de colar o texto
                const file = item.getAsFile();
                if (file) {
                    addImage(file);
                }
            }
        }
        // Limpeza de segurança: Se o navegador for teimoso e já tiver colado o Base64, nos apagamos.
        if (imagePasted) {
            setTimeout(() => {
                // Se for um texto gigante sem nenhum espaço (característica de Base64), apaga.
                if (inputText.value.length > 500 && !inputText.value.includes(' ')) {
                    inputText.value = '';
                    inputText.style.height = 'auto';
                }
            }, 10);
        }
    });

    // ====================================================
    // Função para expandir imagem
    window.expandImage = function(src) {
        expandedImg.src = src;
        modal.classList.remove('hidden');
    };

    function setStopButton() {
        if (btnSend) {
            btnSend.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><rect x="3" y="3" width="14" height="14" rx="2" /></svg>`;
            btnSend.classList.remove('opacity-50', 'cursor-default');
        }
    }

    function formatInline(text) {
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/`([^`]+)`/g, (match, p1) => {
            return `<code class="bg-[var(--bg-chip)] text-[var(--text-code)] px-1.5 py-0.5 rounded text-sm font-mono">${escapeHtml(p1)}</code>`;
        });
        // Links Markdown: [texto](url)
        text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" class="text-blue-400 hover:text-blue-300 underline cursor-pointer">$1</a>');
        // URLs soltas (que não estão dentro de um atributo href ou tag a)
        text = text.replace(/(?<!href="|="|>)(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" class="text-blue-400 hover:text-blue-300 underline cursor-pointer">$1</a>');
        return text;
    }