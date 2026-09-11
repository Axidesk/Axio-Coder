import { state } from './state.js';
import * as dom from './dom.js';
import { adicionarFileNaLista, atualizarBotoesUndoRedo, createChildBalloon } from './files.js';
import { clearCol3Overlay, closeCol3, closeHistoryAndResetDock, closePanelCol, isCol3Open, isHistoryOpen, openCol3Panel, openHistory, openLogDockInWorkspace, openPanelCol, resetCol3State, syncHistoryContainerWidth, syncLogDockFlex } from './layout.js';
import { escapeHtml, showQuestionPanel } from './messages.js';
import { showAlert, syncMenuIcons, syncWorkspaceTopBar } from './ui.js';

const { btnCancelRestore, btnConfirmRestoreYes, btnDeleteTask, btnHistorySearch, btnRestoreTask, btnSaveTask, btnSaveTaskIcon, btnShowQuestion, btnShowThoughts, btnShowTools, codeViewContainer, col3Title, confirmDeleteContent, confirmDeletePopup, filesListContainer, historyLogsWrapper, historySearchInputInline, historySearchPanel, historySearchResultsInline, input, lblDeleteMessage, lblRestoreMessage, logDock, logListContainer, panelCol1, panelCol2, panelCol3, panelTitle, restoreConfirmContent, restoreConfirmPopup, results, slidingPanelContainer } = dom;


    function preloadSessionHistory() {
        // Se o cache já está pronto, não há o que pré-carregar.
        if (state.sessionHistoryLoaded) return;
        fetchSessionHistoryData()
            .then(() => {
                prefetchSessionDetails();
            })
            .catch(() => {
                // Flask pode ainda estar subindo (ex.: app aberto antes do servidor,
                // ou após um restart): agenda nova tentativa em segundo plano para a
                // aba abrir instantaneamente assim que o servidor responder.
                if (state.historyPreloadTimer) return;
                state.historyPreloadTimer = setTimeout(() => {
                    state.historyPreloadTimer = null;
                    preloadSessionHistory();
                }, 2000);
            });
    }
    function renderDayRoundCards(savedLogs, body) {
        if (!savedLogs || savedLogs.length === 0) {
            body.innerHTML = '<div class="p-3 text-xs text-[var(--text-mutado)] font-mono">Nenhuma rodada de edição neste dia.</div>';
            return;
        }
        const groups = savedLogs.map(saved => rebuildGroupFromSaved(saved));
        // Nomeia as tarefas em ordem cronológica (mais antiga = "Tarefa 1").
        // Nomes personalizados (group.name) são preservados e têm prioridade.
        const ordemCronológica = [...groups].sort((a, b) => epochDeId(a.id) - epochDeId(b.id));
        ordemCronológica.forEach((g, idx) => {
            g.displayName = g.name || ('Tarefa ' + (idx + 1));
        });
        // Exibe da rodada mais recente para a mais antiga (ordem decrescente).
        groups.sort((a, b) => epochDeId(b.id) - epochDeId(a.id));
        body.innerHTML = '';
        groups.forEach(group => body.appendChild(createHistoryRoundCard(group)));
    }
    async function loadDayRoundCards(sessoes, body) {
        const savedLogs = [];
        let precisaBuscar = false;
        sessoes.forEach(sessao => {
            const cached = state.sessionDetailCache[sessao.filename];
            if (cached !== undefined) {
                savedLogs.push(...cached);
            } else {
                precisaBuscar = true;
            }
        });
        if (!precisaBuscar) {
            renderDayRoundCards(savedLogs, body);
            return;
        }
        body.innerHTML = '<div class="p-3 text-xs text-[var(--text-mutado)] font-mono">Carregando rodadas...</div>';
        try {
            for (const sessao of sessoes) {
                if (state.sessionDetailCache[sessao.filename] !== undefined) continue;
                const resp = await fetch(`http://127.0.0.1:5000/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
                const data = await resp.json();
                if (data.error) continue;
                const logs = (data.logs || []).map(l => ({ ...l, __session: sessao.filename }));
                state.sessionDetailCache[sessao.filename] = logs;
                savedLogs.push(...logs);
            }
        } catch (e) {
            console.error('Erro ao carregar rodadas do dia:', e);
            body.innerHTML = '<div class="p-3 text-xs text-red-400 font-mono">Erro ao carregar rodadas.</div>';
            return;
        }
        renderDayRoundCards(savedLogs, body);
    }
    function epochDeId(id) {
        if (!id) return 0;
        const m = String(id).match(/(\d+)$/);
        return m ? Number(m[1]) : 0;
    }
    function collectAllRoundIds() {
        // Reúne todos os turnos conhecidos (cache de detalhes + cards renderizados)
        // para calcular quais foram descartados por uma restauração.
        const ids = new Set();
        state.sessionHistoryList.forEach(sessao => {
            const logs = state.sessionDetailCache[sessao.filename];
            if (Array.isArray(logs)) {
                logs.forEach(l => {
                    if (l && l.id !== undefined && l.id !== null) ids.add(String(l.id));
                });
            }
        });
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (el.dataset.turnId) ids.add(String(el.dataset.turnId));
        });
        return ids;
    }
    function marcarCheckpoint(el, id) {
        // Risca (diminui + tachado) os cards posteriores ao checkpoint restaurado,
        // indicando que o estado daquele turno não está mais aplicado ao disco.
        // Turnos já descartados em restaurações anteriores permanecem riscados.
        if (!id) return;
        const foiDescartado = state.discardedRounds.has(String(id));
        const e = epochDeId(id);
        const cp = epochDeId(state.currentCheckpointId);
        const posteriorAoCheckpoint = state.currentCheckpointId && e > cp;
        const criadaAntesDaRestauracao = !state.checkpointRestoredAt || e < state.checkpointRestoredAt;
        if (foiDescartado || (posteriorAoCheckpoint && criadaAntesDaRestauracao)) {
            el.classList.add('history-round-ahead');
            el.title = 'Estado posterior ao checkpoint restaurado (não aplicado)';
        } else {
            el.classList.remove('history-round-ahead');
            el.removeAttribute('title');
        }
    }
    function createHistoryRoundCard(group) {
        const sub = document.createElement('div');
        sub.className = 'history-round-card relative flex flex-col gap-1 w-full text-left px-3.5 py-2.5 rounded-[10px] cursor-pointer text-sm';
        const hora = group.timestamp ? escapeHtml(group.timestamp) : '—';
        const data = group.__date ? ' - ' + escapeHtml(group.__date) : '';
        const nome = escapeHtml(group.displayName || group.name || 'Tarefa');
        const content = document.createElement('div');
        content.className = 'flex-1 min-w-0';
        content.innerHTML = `
            <div class="text-[13px] leading-tight">
                <span class="history-round-name font-bold text-[var(--text-code-dark)]">${nome}</span>
            </div>
            <div class="text-[11px] text-[var(--text-mutado)] truncate leading-tight">${roundMetaHtml(group)}</div>
            <div class="text-[11px] text-[var(--text-mutado)] leading-tight">${hora}${data}</div>
        `;
        const row = document.createElement('div');
        row.className = 'flex items-start gap-2';
        row.appendChild(content);
        // Ícone verde à direita para indicar tarefa salva (persistente).
        sub.appendChild(row);
        if (group.salvo) {
            _injectSavedIcon(sub);
        }
        sub.dataset.turnId = group.id;
        group.domElement = sub;
        group.nameEl = sub.querySelector('.history-round-name');
        sub._group = group;
        marcarCheckpoint(sub, group.id);
        sub.addEventListener('click', () => {
            const isSelected = state.currentSelectedHistoryGroup === group;
            if (!isSelected) {
                selectHistoryTask(group, sub);
                openFilesPanel(group);
                return;
            }
            if (isCol3Open()) {
                closeCol3();
                return;
            }
            showQuestionPanel(group);
        });
        return sub;
    }
    function setupAccordion(card, header, body, bodyInner, toggleIcon, loadCallback) {
        function collapse() {
            body.classList.remove('card-collapsible-open');
            header.classList.remove('session-history-active');
            card.classList.remove('session-history-expanded');
            if (toggleIcon) toggleIcon.textContent = '+';
        }
        async function expand() {
            document.querySelectorAll('.session-history-body').forEach(b => {
                if (b === body) return;
                if (b.classList.contains('card-collapsible-open')) {
                    b.classList.remove('card-collapsible-open');
                    const otherHeader = b.parentElement.querySelector('.session-history-header');
                    if (otherHeader) {
                        otherHeader.classList.remove('session-history-active');
                        otherHeader.parentElement.classList.remove('session-history-expanded');
                    }
                    const otherIcon = b.parentElement.querySelector('.session-history-toggle-icon');
                    if (otherIcon) otherIcon.textContent = '+';
                }
            });
            header.classList.add('session-history-active');
            if (toggleIcon) toggleIcon.textContent = '...';
            if (loadCallback) await loadCallback();
            body.classList.add('card-collapsible-open');
            card.classList.add('session-history-expanded');
            if (toggleIcon) toggleIcon.textContent = '-';
        }
        if (toggleIcon) {
            toggleIcon.addEventListener('click', (e) => {
                e.stopPropagation();
                if (body.classList.contains('card-collapsible-open')) collapse(); else expand();
            });
        }
        header.addEventListener('click', () => {
            if (body.classList.contains('card-collapsible-open')) collapse(); else expand();
        });
    }
    function mountCollapsibleCard(card, header, loadCallback) {
        const body = document.createElement('div');
        body.className = 'session-history-body card-collapsible';
        const bodyClip = document.createElement('div');
        bodyClip.className = 'card-collapsible-clip';
        const bodyInner = document.createElement('div');
        bodyInner.className = 'p-2 flex flex-col gap-2';
        bodyClip.appendChild(bodyInner);
        body.appendChild(bodyClip);
        let loaded = false;
        const toggleIcon = header.querySelector('.session-history-toggle-icon');
        setupAccordion(card, header, body, bodyInner, toggleIcon, async () => {
            if (!loaded) {
                loaded = true;
                await loadCallback(bodyInner);
            }
        });
        card.appendChild(header);
        card.appendChild(body);
        historyLogsWrapper.appendChild(card);
    }
    function _injectSavedIcon(el) {
        const existing = el.querySelector('.history-round-saved-icon');
        if (existing) existing.remove();
        const row = el.firstElementChild;
        if (!row) return;
        const savedIcon = document.createElement('span');
        savedIcon.className = 'shrink-0 mt-0.5 history-round-saved-icon';
        savedIcon.title = 'Tarefa salva';
        savedIcon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-[var(--oliva)]" viewBox="0 0 24 24" fill="currentColor"><path d="M6 2h12a2 2 0 0 1 2 2v18l-8-4-8 4V4a2 2 0 0 1 2-2z"/></svg>`;
        row.appendChild(savedIcon);
    }
    function updateRoundCardSavedIconByTurnId(turnId, salvo) {
        // Atualiza o ícone verde de "salvo" em TODOS os cards que representam a
        // mesma tarefa (ex.: o card no histórico E o card no "Salvo"), não apenas
        // no card atualmente selecionado.
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (String(el.dataset.turnId) !== String(turnId)) return;
            const g = el._group;
            if (g) g.salvo = !!salvo;
            const existing = el.querySelector('.history-round-saved-icon');
            if (existing) existing.remove();
            if (salvo) _injectSavedIcon(el);
        });
    }
    function updateRoundCardNameByTurnId(turnId, novoNome) {
        // Sincroniza o nome renomeado em TODOS os cards da mesma tarefa
        // (card do historico e card dentro de "Salvo"), sem re-renderizar a aba.
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (String(el.dataset.turnId) !== String(turnId)) return;
            const g = el._group;
            if (g) {
                g.name = novoNome;
                g.displayName = novoNome;
            }
            const nameEl = el.querySelector('.history-round-name');
            if (nameEl) nameEl.textContent = novoNome;
        });
    }
    async function toggleSaveSelectedTask(group) {
        if (!group || !group.__session) {
            showAlert('Não foi possível identificar a sessão desta tarefa para salvar.');
            return;
        }
        try {
            const resp = await fetch('http://127.0.0.1:5000/api/session_log/toggle_save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: group.__session, round_id: group.id || '' })
            });
            const data = await resp.json();
            if (data && data.status === 'ok') {
                group.salvo = !!data.salvo;
                // Atualiza o cache para que o ícone verde apareca corretamente.
                Object.keys(state.sessionDetailCache).forEach(key => {
                    (state.sessionDetailCache[key] || []).forEach(saved => {
                        if (String(saved.id) === String(group.id)) {
                            saved.salvo = !!data.salvo;
                        }
                    });
                });
                updateActionButtons();
                updateRoundCardSavedIconByTurnId(group.id, !!data.salvo);
                renderSalvoCardIfNeeded();
            } else {
                showAlert(data && data.message ? data.message : 'Erro ao salvar tarefa.');
            }
        } catch (e) {
            console.error('Erro ao salvar tarefa:', e);
        }
    }
    function collectSavedRounds() {
        const saved = [];
        for (const sessao of state.sessionHistoryList) {
            const logs = state.sessionDetailCache[sessao.filename] || [];
            logs.forEach(l => {
                if (l.salvo) saved.push({ ...l, __session: sessao.filename, __date: (sessao.datetime || '').split(' ')[0] || '' });
            });
        }
        return saved;
    }
    function renderSalvoCardIfNeeded() {
        // Remove o card "Salvo" existente para re-renderizar de forma idempotente.
        const existing = document.querySelector('.session-history-card[data-salvo="true"]');
        if (existing) existing.remove();
        // So renderiza quando há ao menos uma tarefa salva (card condicional).
        if (collectSavedRounds().length === 0) return;
        renderSalvoCard();
    }
    function assignDisplayNamesByDay() {
        // Nomeia as tarefas em ordem cronológica POR DIA (mais antiga = "Tarefa 1").
        // Usa TODAS as tarefas do dia (não so as salvas), garantindo que uma tarefa
        // salva mantenha o mesmo número exibido no histórico (ex.: "Tarefa 46").
        const logsPorDia = new Map();
        for (const sessao of state.sessionHistoryList) {
            const logs = state.sessionDetailCache[sessao.filename] || [];
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            if (!logsPorDia.has(dia)) logsPorDia.set(dia, []);
            logsPorDia.get(dia).push(...logs);
        }
        logsPorDia.forEach((logs) => {
            const ordem = [...logs].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
            ordem.forEach((log, idx) => {
                log.displayName = log.name || ('Tarefa ' + (idx + 1));
            });
        });
    }
    function renderSalvoCard() {
        const card = document.createElement('div');
        card.className = 'session-history-card';
        card.dataset.salvo = 'true';
        const header = document.createElement('div');
        header.className = 'session-history-header relative flex flex-col gap-1 justify-center w-full text-left px-3.5 py-2.5 cursor-pointer min-h-[54px]';
        header.innerHTML = `
            <span class="block text-[13px] font-semibold text-[var(--oliva)] leading-tight pr-6">Salvo</span>
            <span class="session-history-toggle-icon absolute top-2.5 right-3 text-[var(--text-mutado)] text-lg font-mono leading-none cursor-pointer hover:text-[var(--text-branco)] transition-colors select-none">+</span>
        `;
        mountCollapsibleCard(card, header, loadSavedRoundCards);
    }
    async function ensureSessionDetailsLoaded() {
        for (const sessao of state.sessionHistoryList) {
            if (state.sessionDetailCache[sessao.filename] !== undefined) continue;
            try {
                const resp = await fetch(`http://127.0.0.1:5000/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
                const data = await resp.json();
                if (!data.error) {
                    state.sessionDetailCache[sessao.filename] = (data.logs || []).map(l => ({ ...l, __session: sessao.filename }));
                }
            } catch (e) {
                console.error('Erro ao carregar detalhes da sessão:', e);
            }
        }
    }
    async function loadSavedRoundCards(body) {
        await ensureSessionDetailsLoaded();
        // Reutiliza a MESMA numeração cronológica por dia usada no histórico,
        // para que a tarefa salva mantenha o mesmo nome (ex.: "Tarefa 46") em vez
        // de ser renumerada como "Tarefa 1" dentro do card "Salvo".
        assignDisplayNamesByDay();
        const savedLogs = collectSavedRounds();
        if (savedLogs.length === 0) {
            body.innerHTML = '<div class="p-3 text-xs text-[var(--text-mutado)] font-mono">Nenhuma tarefa salva.</div>';
            return;
        }
        const groups = savedLogs.map(saved => rebuildGroupFromSaved(saved));
        const dataKey = d => {
            const p = (d || '').split('/');
            return p.length === 3 ? `${p[2]}${p[1]}${p[0]}` : '';
        };
        groups.sort((a, b) => {
            const ka = dataKey(a.__date) + (a.timestamp || '');
            const kb = dataKey(b.__date) + (b.timestamp || '');
            return kb.localeCompare(ka);
        });
        body.innerHTML = '';
        groups.forEach(group => body.appendChild(createHistoryRoundCard(group)));
    }
    function selectHistoryTaskInPile(dia, turnId) {
        if (!dia || !turnId) return;
        const dayCard = Array.from(document.querySelectorAll('.session-history-card')).find(c => c.dataset.dia === dia);
        if (!dayCard) return; // dia não renderizado (ex.: mais antigo que os 3 dias exibidos)
        const header = dayCard.querySelector('.session-history-header');
        const body = dayCard.querySelector('.session-history-body');
        if (!header || !body) return;
        const selectRound = () => {
            const round = Array.from(body.querySelectorAll('.history-round-card')).find(el => el.dataset.turnId === turnId);
            if (!round) return false;
            document.querySelectorAll('.history-round-card').forEach(el => el.classList.remove('history-round-selected'));
            round.classList.add('history-round-selected');
            state.currentSelectedHistoryGroup = round._group || null;
            state.currentSelectedHistoryEl = round;
            updateActionButtons();
            round.scrollIntoView({ block: 'nearest' });
            return true;
        };
        // Garante que o dia esteja expandido (o expand também carrega as rodadas, se preciso).
        if (!body.classList.contains('card-collapsible-open')) {
            header.click();
        }
        if (selectRound()) return;
        // As rodadas podem estar carregando de forma assíncrona (primeira expansao do dia).
        let tentativas = 0;
        const poll = setInterval(() => {
            if (selectRound() || ++tentativas >= 30) clearInterval(poll);
        }, 100);
    }
    function openHistorySearchInCol3() {
        resetCol3State();
        if (btnHistorySearch) {
            btnHistorySearch.classList.add('text-[var(--oliva)]');
            btnHistorySearch.classList.remove('text-[var(--text-mutado)]');
        }
        openCol3Panel();
        col3Title.textContent = 'Buscar nas Conversas';
        col3Title.onclick = null;
        col3Title.ondblclick = null;
        col3Title.title = '';
        col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
        col3Title.classList.add('text-[var(--text)]');
        codeViewContainer.style.display = 'flex';
        codeViewContainer.style.flexDirection = 'column';
        codeViewContainer.innerHTML = `
            <div class="flex-1 min-h-0 flex flex-col gap-3 font-sans whitespace-normal">
                <div class="relative shrink-0">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-mutado)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
                    </svg>
                    <input id="history-search-input" type="text" placeholder="O que está procurando?"
                        class="w-full bg-[var(--bg)] rounded-2xl pl-9 pr-3 py-2.5 text-sm text-[var(--text)] placeholder-[var(--text-mutado)] focus:outline-none transition-colors">
                </div>
                <div id="history-search-results" class="flex-1 min-h-0 overflow-y-auto flex flex-col gap-2 pr-1"></div>
            </div>
        `;
        if (input) input.focus();
        let searchTimer = null;
        if (input) {
            input.addEventListener('input', () => {
                clearTimeout(searchTimer);
                const termo = input.value.trim();
                if (!termo) {
                    results.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">Digite para buscar nas mensagens enviadas.</div>';
                    return;
                }
                searchTimer = setTimeout(() => performHistorySearch(termo, results), 200);
            });
        }
    }
    function collapseHistorySearchInline() {
        state.historySearchInlineActive = false;
        if (historySearchPanel) historySearchPanel.classList.add('hidden');
        if (logListContainer) logListContainer.classList.remove('hidden');
        if (panelCol1) panelCol1.classList.remove('history-search-expanded');
        if (slidingPanelContainer) slidingPanelContainer.classList.remove('history-search-expanded');
        if (btnHistorySearch) {
            btnHistorySearch.classList.remove('text-[var(--oliva)]');
            btnHistorySearch.classList.add('text-[var(--text-mutado)]');
        }
    }
    function toggleHistorySearchInline() {
        if (!historySearchPanel) return;
        if (state.historySearchInlineActive) {
            collapseHistorySearchInline();
            syncHistoryContainerWidth();
            return;
        }
        state.historySearchInlineActive = true;
        if (logListContainer) logListContainer.classList.add('hidden');
        historySearchPanel.classList.remove('hidden');
        if (panelCol1) panelCol1.classList.add('history-search-expanded');
        if (slidingPanelContainer) slidingPanelContainer.classList.add('history-search-expanded');
        if (btnHistorySearch) {
            btnHistorySearch.classList.add('text-[var(--oliva)]');
            btnHistorySearch.classList.remove('text-[var(--text-mutado)]');
        }
        syncHistoryContainerWidth();
        if (historySearchResultsInline) historySearchResultsInline.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">Digite para buscar nas mensagens enviadas.</div>';
        if (historySearchInputInline) historySearchInputInline.focus();
        let searchTimer = null;
        if (historySearchInputInline && historySearchResultsInline) {
            historySearchInputInline.addEventListener('input', () => {
                clearTimeout(searchTimer);
                const termo = historySearchInputInline.value.trim();
                if (!termo) {
                    historySearchResultsInline.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">Digite para buscar nas mensagens enviadas.</div>';
                    return;
                }
                searchTimer = setTimeout(() => performHistorySearch(termo, historySearchResultsInline), 200);
            });
        }
    }
    function openHistorySearchPanel() {
        const col3Open = panelCol3 && !panelCol3.classList.contains('panel-col-closed');
        if (col3Open) {
            openHistorySearchInCol3();
        } else {
            toggleHistorySearchInline();
        }
    }
    async function performHistorySearch(termo, resultsContainer) {
        resultsContainer.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">Buscando...</div>';
        const termoLower = termo.toLowerCase();
        // Reutiliza o mesmo carregamento de detalhes do histórico salvo.
        await ensureSessionDetailsLoaded();
        // Nomeia as tarefas em ordem cronológica POR DIA (mesma regra usada no
        // histórico). Antes a numeração era por sessão: quando havia várias sessões
        // no mesmo dia, a busca mostrava "Tarefa 2" para um log que no histórico
        // aparecia como "Tarefa 4", fazendo parecer que a tarefa errada tinha sido
        // selecionada na pilha (a seleção por id já estava correta, mas o rotulo não).
        assignDisplayNamesByDay();
        const resultados = [];
        for (const sessao of state.sessionHistoryList) {
            const logs = state.sessionDetailCache[sessao.filename] || [];
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            logs.forEach(saved => {
                const questoes = saved.questions || [];
                for (const q of questoes) {
                    if (String(q).toLowerCase().includes(termoLower)) {
                        resultados.push({
                            nome: saved.displayName || saved.name || 'Tarefa',
                            dia,
                            hora: saved.timestamp || '',
                            pergunta: q,
                            saved
                        });
                        break; // uma entrada por tarefa é suficiente
                    }
                }
            });
        }
        if (resultados.length === 0) {
            resultsContainer.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">Nenhuma mensagem encontrada com esse termo.</div>';
            return;
        }
        resultsContainer.innerHTML = '';
        resultados.forEach((r, i) => {
            if (i > 0) {
                const sep = document.createElement('div');
                sep.className = 'border-t border-[var(--border)] my-1';
                resultsContainer.appendChild(sep);
            }
            resultsContainer.appendChild(createHistorySearchResultCard(r, termoLower));
        });
    }
    function createHistorySearchResultCard(r, termoLower) {
        const card = document.createElement('div');
        card.className = 'flex flex-col gap-1 py-1';
        const nome = document.createElement('div');
        nome.className = 'text-[13px] font-bold text-[var(--text-code-dark)] leading-tight cursor-pointer hover:text-[var(--oliva)] hover:underline transition-colors';
        nome.textContent = r.nome;
        nome.title = 'Abrir tarefa correspondente';
        nome.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!r.saved) return;
            if (state.historySearchInlineActive) toggleHistorySearchInline();
            const group = rebuildGroupFromSaved(r.saved);
            group.displayName = r.nome;
            selectHistoryTaskInPile(r.dia, r.saved.id);
        });
        const meta = document.createElement('div');
        meta.className = 'text-[10px] text-[var(--cinza-meta)] leading-tight';
        meta.textContent = [r.dia, r.hora].filter(Boolean).join(' | ');
        const trecho = document.createElement('div');
        trecho.className = 'text-[12px] text-[var(--text-usuario)] leading-relaxed';
        trecho.innerHTML = buildSearchSnippet(r.pergunta, termoLower);
        card.appendChild(nome);
        if (meta.textContent) card.appendChild(meta);
        card.appendChild(trecho);
        return card;
    }
    function buildSearchSnippet(texto, termoLower) {
        const source = String(texto);
        const idx = source.toLowerCase().indexOf(termoLower);
        const radius = 60;
        let inicio = 0;
        let fim = source.length;
        if (idx > radius) inicio = idx - radius;
        if (idx + termoLower.length + radius < source.length) fim = idx + termoLower.length + radius;
        let snippet = (inicio > 0 ? '…' : '') + source.slice(inicio, fim) + (fim < source.length ? '…' : '');
        const escaped = escapeHtml(snippet);
        const termoEscaped = escapeHtml(termoLower).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return escaped.replace(new RegExp(termoEscaped, 'gi'), (m) => `<span class="text-[var(--oliva)] font-semibold">${m}</span>`);
    }
    function moveColsToHistory() {
        if (!slidingPanelContainer) return;
        clearCol3Overlay();
        if (panelCol2 && panelCol2.parentNode !== slidingPanelContainer) slidingPanelContainer.appendChild(panelCol2);
        if (panelCol3 && panelCol3.parentNode !== slidingPanelContainer) slidingPanelContainer.appendChild(panelCol3);
        syncLogDockFlex();
        syncHistoryContainerWidth();
    }
    function moveColsToDock() {
        if (!logDock) return;
        clearCol3Overlay();
        if (panelCol2 && panelCol2.parentNode !== logDock) logDock.appendChild(panelCol2);
        if (panelCol3 && panelCol3.parentNode !== logDock) logDock.appendChild(panelCol3);
        syncLogDockFlex();
        syncHistoryContainerWidth();
    }
    function openFilesPanel(group) {
        if (isHistoryOpen()) {
            moveColsToHistory();
            openPanelCol(panelCol2);
        } else {
            moveColsToDock();
            openLogDockInWorkspace();
            openPanelCol(panelCol2);
        }
        window.currentActiveLogGroup = group;
        state.currentViewingTools = group.tools || [];
        state.currentViewingThoughts = group.thoughts || [];
        state.currentViewingQuestions = group.questions || [];
        state.thoughtsExpanded = false;
        state.currentViewingAiResponse = group.aiResponse || '';
        updateShowButtonsState();
        closeCol3();
        filesListContainer.innerHTML = '';
        if ((group.files || []).length === 0) {
            filesListContainer.innerHTML = '<div class="panel-empty">Nenhum arquivo modificado neste turno.</div>';
        }
        (group.files || []).forEach(fileData => adicionarFileNaLista(fileData));
        // Reaplica o riscado (desfeito) aos cards após renderizar, para que o
        // estado de undo/redo do backend fique refletido assim que a aba abre.
        atualizarBotoesUndoRedo();
    }
    function updateActionButtons() {
        const enabled = !!state.currentSelectedHistoryGroup;
        [btnRestoreTask, btnSaveTask, btnDeleteTask].forEach(btn => {
            if (!btn) return;
            btn.disabled = !enabled;
            btn.classList.toggle('opacity-40', !enabled);
            btn.classList.toggle('cursor-default', !enabled);
        });
        // Destaca o ícone de salvar em verde quando a tarefa selecionada já está salva.
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
    function closeConfirmDeletePopup() {
        confirmDeletePopup.classList.remove('opacity-100', 'pointer-events-auto');
        confirmDeletePopup.classList.add('opacity-0', 'pointer-events-none');
        confirmDeleteContent.classList.remove('scale-100');
        confirmDeleteContent.classList.add('scale-95');
    }
    function requestDeleteSelectedTask(group) {
        if (!group || !group.__session) {
            showAlert('Não foi possível identificar a sessão desta tarefa para excluir.');
            return;
        }
        state.pendingDelete = { filename: group.__session, turn_id: group.id || '' };
        const nome = group.displayName || group.name || 'Tarefa';
        if (lblDeleteMessage) {
            lblDeleteMessage.textContent = `Excluir a tarefa "${nome}"? Esta ação não pode ser desfeita.`;
        }
        confirmDeletePopup.classList.remove('opacity-0', 'pointer-events-none');
        confirmDeletePopup.classList.add('opacity-100', 'pointer-events-auto');
        confirmDeleteContent.classList.remove('scale-95');
        confirmDeleteContent.classList.add('scale-100');
    }
    async function performDeleteSelectedTask() {
        if (!state.pendingDelete) return;
        const { filename, turn_id } = state.pendingDelete;
        state.pendingDelete = null;
        if (!filename || !turn_id) return;
        try {
            const resp = await fetch('http://127.0.0.1:5000/api/session_log/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: [], turn_ids: [], turns: [{ filename, turn_id }] })
            });
            const data = await resp.json();
            // Remove o card selecionado do DOM e limpa a seleção atual.
            const ids = new Set([String(turn_id)]);
            window.sessionLogsData = (window.sessionLogsData || []).filter(g => {
                if (ids.has(String(g.id))) {
                    if (g.domElement) g.domElement.remove();
                    return false;
                }
                return true;
            });
            state.currentTurnLogs = state.currentTurnLogs.filter(g => !ids.has(String(g.id)));
            if (window.currentGroupBalloon && ids.has(String(window.currentGroupBalloon.id))) {
                window.currentGroupBalloon = null;
            }
            if (state.currentSelectedHistoryEl) {
                state.currentSelectedHistoryEl.remove();
            }
            state.currentSelectedHistoryGroup = null;
            state.currentSelectedHistoryEl = null;
            updateActionButtons();
            if (data && data.status === 'ok') {
                // Remove a rodada excluída do cache local e atualiza o card "Salvo"
                // em tempo real, sem recolher os cards de dia.
                if (state.sessionDetailCache[filename]) {
                    state.sessionDetailCache[filename] = state.sessionDetailCache[filename].filter(l => String(l.id) !== String(turn_id));
                }
                renderSalvoCardIfNeeded();
                showAlert('Tarefa excluída.');
            } else {
                showAlert(data && data.message ? data.message : 'Erro ao excluir tarefa.');
            }
        } catch (e) {
            console.error('Erro ao excluir tarefa:', e);
        }
    }
    function countLabelHtml(count, singularLabel, pluralLabel) {
        const label = count === 1 ? singularLabel : pluralLabel;
        const padded = String(count).padStart(2, '0');
        return `<span style="color:var(--oliva);font-weight:700;">${padded}</span> <span style="color:var(--text-inline);">${escapeHtml(label)}</span>`;
    }
    function roundMetaHtml(group) {
        const fileCount = (group.files || []).length;
        const toolCount = (group.tools || []).length;
        const duracao = formatRoundDuration(group.duration);
        const textoArquivos = fileCount === 1 ? '1 arquivo' : `${fileCount} arquivos`;
        const textoFerramentas = toolCount === 1 ? '1 ferramenta' : `${toolCount} ferramentas`;
        return `${textoArquivos} - ${textoFerramentas} - ${duracao}`;
    }
    function formatRoundDuration(duration) {
        const ms = Number(duration) || 0;
        if (ms <= 0) return '—';
        const sec = Math.round(ms / 1000);
        return `${Math.max(1, Math.round(sec / 60))}min`;
    }
    function cancelRestorePreview() {
        if (state.restoreAbortController) {
            state.restoreAbortController.abort();
            state.restoreAbortController = null;
        }
    }
    function openRestorePopup() {
        if (!restoreConfirmPopup) return;
        restoreConfirmPopup.classList.remove('opacity-0', 'pointer-events-none');
        restoreConfirmPopup.classList.add('opacity-100', 'pointer-events-auto');
        restoreConfirmContent.classList.remove('scale-95');
        restoreConfirmContent.classList.add('scale-100');
    }
    function closeRestoreConfirmPopup() {
        if (!restoreConfirmPopup) return;
        cancelRestorePreview();
        restoreConfirmPopup.classList.remove('opacity-100', 'pointer-events-auto');
        restoreConfirmPopup.classList.add('opacity-0', 'pointer-events-none');
        restoreConfirmContent.classList.remove('scale-100');
        restoreConfirmContent.classList.add('scale-95');
    }
    function resetRestoreConfirmButtons() {
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.disabled = false;
            btnConfirmRestoreYes.classList.remove('hidden', 'opacity-50', 'cursor-not-allowed');
        }
        if (btnCancelRestore) {
            btnCancelRestore.textContent = 'Cancelar';
            btnCancelRestore.disabled = false;
            btnCancelRestore.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
    function renderRestoreLoadingMessage(texto) {
        if (lblRestoreMessage) {
            lblRestoreMessage.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:8px 0;">' +
                '<span class="logs-spinner" style="width:24px;height:24px;border-width:3px;"></span>' +
                '<span style="font-weight:700;color:var(--text-inline);">' + escapeHtml(texto) + '</span>' +
                '</div>';
        }
    }
    function showRestorePreviewLoading() {
        renderRestoreLoadingMessage('Carregando...');
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.disabled = true;
            btnConfirmRestoreYes.classList.add('opacity-50', 'cursor-not-allowed');
        }
        if (btnCancelRestore) {
            btnCancelRestore.textContent = 'Cancelar';
            btnCancelRestore.disabled = false;
            btnCancelRestore.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        openRestorePopup();
    }
    function showRestoreLoading() {
        resetRestoreConfirmButtons();
        renderRestoreLoadingMessage('Restaurando...');
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.disabled = true;
            btnConfirmRestoreYes.classList.add('opacity-50', 'cursor-not-allowed');
        }
        if (btnCancelRestore) {
            btnCancelRestore.disabled = true;
            btnCancelRestore.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
    function showRestoreResult(html) {
        if (lblRestoreMessage) lblRestoreMessage.innerHTML = html;
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.classList.add('hidden');
        }
        if (btnCancelRestore) {
            btnCancelRestore.textContent = 'Fechar';
            btnCancelRestore.disabled = false;
            btnCancelRestore.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
    async function requestRestoreTask(group) {
        if (!group.__session) {
            showAlert('Não foi possível identificar a sessão desta tarefa para restaurar.');
            return;
        }
        const nome = group.displayName || group.name || 'Tarefa';
        const hora = group.timestamp || '';
        const label = `${nome}${hora ? ' (' + hora + ')' : ''}`;
        state.pendingRestore = { filename: group.__session, round_id: group.id || '', label };
        cancelRestorePreview();
        const abortController = new AbortController();
        state.restoreAbortController = abortController;
        showRestorePreviewLoading();
        let restored = [];
        let kept = [];
        let orphans = [];
        let empty = false;
        try {
            const resp = await fetch('http://127.0.0.1:5000/api/session_restore_preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: group.__session, round_id: group.id || '' }),
                signal: abortController.signal
            });
            const data = await resp.json();
            restored = data.restored || [];
            kept = data.kept || [];
            orphans = data.orphans || [];
            empty = !!data.empty;
        } catch (e) {
            if (abortController.signal.aborted) {
                state.pendingRestore = null;
                closeRestoreConfirmPopup();
                return;
            }
            console.error('Erro ao carregar prévia da restauração:', e);
            const snapshot = group.snapshot || {};
            restored = Object.keys(snapshot).map(rel => {
                const info = snapshot[rel];
                const removido = info && typeof info === 'object' && info.conteudo === null;
                return removido ? { caminho: rel, acao: 'removido' } : { caminho: rel, acao: 'restaurado' };
            });
        }
        const toRestore = restored.filter(r => r.acao !== 'removido').map(r => r.caminho);
        const toRemoveFromRestored = restored.filter(r => r.acao === 'removido').map(r => r.caminho);
        const allRemoved = [...toRemoveFromRestored, ...orphans];
        const tituloRestaurar = `Restaurar a ${escapeHtml(nome)}`;
        const hasChanges = toRestore.length > 0 || allRemoved.length > 0;
        let msg = `<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--text-inline);">${tituloRestaurar}</div>`;
        if (hora) {
            msg += `<div style="text-align:center;font-size:0.75rem;color:var(--text-mutado);margin-top:2px;">${escapeHtml(hora)}</div>`;
        }
        msg += '<div style="height:14px;"></div>';
        if (toRestore.length) {
            msg += `${countLabelHtml(toRestore.length, 'Arquivo a Restaurar', 'Arquivos a Restaurar')}<br>${toRestore.map(p => '• ' + escapeHtml(p)).join('<br>')}<br><br>`;
        } else if (empty && !allRemoved.length) {
            msg += 'Esta tarefa não possui checkpoint de código salvo (nenhum arquivo foi editado nela).<br><br>';
        } else if (!hasChanges) {
            msg += 'Nenhum arquivo precisa ser alterado.<br><br>';
        }
        if (allRemoved.length) {
            msg += `${countLabelHtml(allRemoved.length, 'Arquivo a Remover', 'Arquivos a Remover')}<br>${allRemoved.map(p => '• ' + escapeHtml(p)).join('<br>')}<br><br>`;
        }
        if (kept.length && hasChanges) {
            msg += `<details class="restore-details"><summary><span>${countLabelHtml(kept.length, 'Arquivo Inalterado', 'Arquivos Inalterados')}</span></summary><div class="restore-kept-list">${kept.map(p => '• ' + escapeHtml(p)).join('<br>')}</div></details>`;
        }
        state.restoreAbortController = null;
        if (lblRestoreMessage) lblRestoreMessage.innerHTML = msg;
        resetRestoreConfirmButtons();
        openRestorePopup();
    }
    async function performSessionRestore() {
        if (!state.pendingRestore) return;
        const filename = state.pendingRestore.filename;
        const roundId = state.pendingRestore.round_id || '';
        state.pendingRestore = null;
        showRestoreLoading();
        try {
            const resp = await fetch('http://127.0.0.1:5000/api/session_restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, round_id: roundId })
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                const cpEpoch = epochDeId(roundId);
                const agoraEpoch = Date.now();
                if (roundId) {
                    document.querySelectorAll('.history-round-card.history-round-ahead').forEach(el => {
                        if (el.dataset.turnId) state.discardedRounds.add(String(el.dataset.turnId));
                    });
                    collectAllRoundIds().forEach(tid => {
                        const e = epochDeId(tid);
                        if (e > cpEpoch && e < agoraEpoch) state.discardedRounds.add(tid);
                    });
                    state.discardedRounds.delete(String(roundId));
                }
                state.currentCheckpointId = roundId || null;
                state.checkpointRestoredAt = roundId ? agoraEpoch : 0;
                saveCheckpointState();
                document.querySelectorAll('.history-round-card').forEach(el => {
                    marcarCheckpoint(el, el.dataset.turnId);
                });
                const alterados = data.altered || [];
                const criadosRemovidos = alterados.filter(a => (a.acao || '').includes('criado')).length;
                let restMsgHtml = '<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--text-inline);">Restauração concluída</div>';
                restMsgHtml += '<div style="height:12px;"></div>';
                if (data.count > 0) {
                    const linhas = [`${countLabelHtml(data.count, 'Arquivo Alterado', 'Arquivos Alterados')}`];
                    if (criadosRemovidos > 0) linhas.push(`${countLabelHtml(criadosRemovidos, 'Arquivo Criado Removido', 'Arquivos Criados Removidos')}`);
                    restMsgHtml += `<div style="color:var(--text-claro);">${linhas.join('<br>')}</div>`;
                } else {
                    restMsgHtml += '<div style="color:var(--text-claro);">Nenhuma alteração necessária — o código já estava no estado da sessão.</div>';
                }
                showRestoreResult(restMsgHtml);
            } else if (data.status === 'empty') {
                showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--text-inline);">' + (data.message || 'Esta sessão não possui checkpoint de código para restaurar.') + '</div>');
            } else {
                showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--perigo);">Erro ao restaurar: ' + (data.message || 'falha desconhecida.') + '</div>');
            }
        } catch (e) {
            console.error('Erro ao restaurar sessão:', e);
            showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--perigo);">Erro ao conectar para restaurar a sessão.</div>');
        }
    }
    function createLogGroupCard(group) {
        const card = document.createElement('div');
        const timeSpan = document.createElement('span');
        const titleSpan = document.createElement('span');
        const spinner = document.createElement('span');
        card.className = 'log-card relative flex flex-col gap-1 w-full text-left px-3.5 py-2.5 rounded-[10px] cursor-pointer text-sm';
        timeSpan.className = 'text-[13px] font-semibold text-[var(--text-code-dark)] leading-tight';
        titleSpan.className = 'text-[11px] text-[var(--text-usuario)] truncate leading-tight pr-6';
        spinner.className = 'hidden logs-spinner absolute top-2.5 right-3';
        spinner.title = 'Editando...';
        card.appendChild(timeSpan);
        card.appendChild(titleSpan);
        card.appendChild(spinner);
        card.addEventListener('click', () => {
            const wasActive = card.classList.contains('log-card-active');
            const col2Open = panelCol2 && !panelCol2.classList.contains('panel-col-closed');
            const col3Open = panelCol3 && !panelCol3.classList.contains('panel-col-closed');
            if (wasActive && (col2Open || col3Open)) {
                closePanelCol(panelCol2);
                closeCol3();
                return;
            }
            document.querySelectorAll('.log-card').forEach(el => el.classList.remove('log-card-active'));
            card.classList.add('log-card-active');
            openFilesPanel(group);
            if (panelCol3) void panelCol3.offsetWidth;
            showQuestionPanel(group);
        });
        group.domElement = card;
        group.timeSpan = timeSpan;
        group.titleSpan = titleSpan;
        group.spinner = spinner;
        return card;
    }
    function serializeGroup(g) {
        const label = (g.files && g.files.length)
            ? g.files.map(f => f.name).join(', ')
            : (g.titleSpan ? g.titleSpan.textContent.replace(/^\s*\[[^\]]*\]\s*/, '').trim() : '');
        return {
            id: g.id,
            timestamp: g.timestamp,
            title: label,
            name: g.name || '',
            aiResponse: g.aiResponse || '',
            salvo: !!g.salvo,
            duration: g.duration || 0,
            tools: g.tools || [],
            thoughts: g.thoughts || [],
            questions: g.questions || [],
            files: (g.files || []).map(f => ({
                name: f.name,
                deleted: !!f.deleted,
                diffs: (f.diffElements || []).map(el => el._data || null).filter(Boolean)
            }))
        };
    }
    async function saveCurrentTurnSession() {
        if (!state.currentTurnLogs.length) return;
        const payload = {
            summary: state.currentTurnSummary || '',
            logs: state.currentTurnLogs.map(serializeGroup)
        };
        try {
            await fetch('http://127.0.0.1:5000/api/session_log/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            console.error('Erro ao salvar log da sessão:', e);
        }
    }
    function rebuildGroupFromSaved(saved) {
        return {
            id: saved.id,
            timestamp: saved.timestamp,
            title: saved.title || '',
            name: saved.name || '',
            displayName: saved.displayName || '',
            __session: saved.__session || '',
            __date: saved.__date || '',
            snapshot: saved.snapshot || {},
            aiResponse: saved.aiResponse || '',
            salvo: !!saved.salvo,
            duration: saved.duration || 0,
            tools: saved.tools || [],
            thoughts: saved.thoughts || [],
            questions: saved.questions || [],
            files: (saved.files || []).map(f => ({
                name: f.name,
                deleted: !!f.deleted,
                diffElements: (f.diffs || []).map(d => createChildBalloon(
                    d.title, d.htmlContent, d.snippetHtml, d.rawTextOld, d.rawTextNew, d.fileName,
                    null, d.fullOriginalText, d.fullNewText, d.deletedLines, d.addedLines, d.origToMod, d.modToOrig, d.subtitle
                ))
            }))
        };
    }
    async function toggleSessionHistory() {
        if (isHistoryOpen()) {
            closeHistoryAndResetDock();
            return;
        }
        openHistory();
        moveColsToHistory();
        openPanelCol(panelCol2);
        if (filesListContainer) {
            filesListContainer.innerHTML = '<div class="panel-empty">Selecione uma tarefa no histórico para ver os arquivos.</div>';
        }
        syncWorkspaceTopBar(true);
        state.isShowingSessionHistory = true;
        state.currentSelectedHistoryGroup = null;
        state.currentSelectedHistoryEl = null;
        updateActionButtons();
        setHistoryActionButtonsVisible(true);
        if (panelTitle) panelTitle.textContent = 'Historico';
        syncMenuIcons();
        if (state.sessionHistoryLoaded) {
            renderHistoryCards();
        } else {
            if (historyLogsWrapper) {
                historyLogsWrapper.innerHTML = '<div class="p-4 text-sm text-[var(--text-mutado)] font-mono">Carregando histórico...</div>';
            }
            await loadSessionHistoryList();
        }
    }
    async function fetchSessionHistoryData() {
        const resp = await fetch('http://127.0.0.1:5000/api/session_history');
        const data = await resp.json();
        state.sessionHistoryList = data.sessions || [];
        state.sessionDetailCache = {};
        state.sessionHistoryLoaded = true;
        await fetchCheckpointState();
    }
    async function fetchCheckpointState() {
        try {
            const resp = await fetch('http://127.0.0.1:5000/api/checkpoint_state');
            const data = await resp.json();
            state.currentCheckpointId = data.checkpoint_id || null;
            state.checkpointRestoredAt = data.checkpoint_restored_at || 0;
            state.discardedRounds.clear();
            (data.discarded_rounds || []).forEach(r => {
                if (r !== undefined && r !== null) state.discardedRounds.add(String(r));
            });
        } catch (e) {
            console.error('Erro ao carregar estado do checkpoint:', e);
        }
    }
    async function saveCheckpointState() {
        try {
            await fetch('http://127.0.0.1:5000/api/checkpoint_state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ checkpoint_id: state.currentCheckpointId, checkpoint_restored_at: state.checkpointRestoredAt, discarded_rounds: Array.from(state.discardedRounds) })
            });
        } catch (e) {
            console.error('Erro ao salvar estado do checkpoint:', e);
        }
    }
    async function loadSessionHistoryList({ silent = false } = {}) {
        try {
            await fetchSessionHistoryData();
            renderHistoryCards();
            prefetchSessionDetails();
        } catch (e) {
            console.error('Erro ao carregar histórico:', e);
            if (!silent && historyLogsWrapper) {
                historyLogsWrapper.innerHTML = '<div class="p-4 text-sm text-red-400 font-mono">Erro ao carregar histórico.</div>';
            }
        }
    }
    function renderHistoryCards() {
        state.currentSelectedHistoryGroup = null;
        state.currentSelectedHistoryEl = null;
        updateActionButtons();
        setHistoryActionButtonsVisible(true);
        if (historyLogsWrapper) {
            historyLogsWrapper.innerHTML = '';
        }
        if (state.sessionHistoryList.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'p-4 text-sm text-[var(--text-mutado)] font-mono';
            empty.textContent = 'Nenhuma sessão anterior encontrada.';
            historyLogsWrapper.appendChild(empty);
            return;
        }
        // Agrupa as sessões por dia (DD/MM/AAAA extraído de datetime).
        const sessoesPorDia = new Map();
        state.sessionHistoryList.forEach(sessao => {
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            if (!sessoesPorDia.has(dia)) sessoesPorDia.set(dia, []);
            sessoesPorDia.get(dia).push(sessao);
        });
        // Ordena os dias do mais recente para o mais antigo (pela sessão mais recente do dia).
        const dias = Array.from(sessoesPorDia.keys()).sort((a, b) => {
            const ta = Math.max(...sessoesPorDia.get(a).map(s => s.timestamp || 0));
            const tb = Math.max(...sessoesPorDia.get(b).map(s => s.timestamp || 0));
            return tb - ta;
        });
        // Card "Salvo" é renderizado de forma condicional após o pré-carregamento
        // dos detalhes (renderSalvoCardIfNeeded), para so aparecer se houver salvos.
        // Mantém apenas os 3 dias mais recentes (substitui os mais antigos).
        dias.slice(0, 3).forEach(dia => {
            const sessoes = sessoesPorDia.get(dia);
            const card = document.createElement('div');
            card.className = 'session-history-card';
            card.dataset.dia = dia;
            const header = document.createElement('div');
            header.className = 'session-history-header relative flex flex-col gap-1 justify-center w-full text-left px-3.5 py-2.5 cursor-pointer min-h-[54px]';
            const temSessaoAtual = sessoes.some(s => s.current);
            const subtitulo = temSessaoAtual
                ? '<span class="block text-[11px] font-semibold text-[var(--oliva-claro)] leading-tight pr-6">Em curso</span>'
                : '';
            header.innerHTML = `
                <span class="block text-[13px] font-semibold text-[var(--text-code-dark)] leading-tight pr-6">${escapeHtml(dia)}</span>
                ${subtitulo}
                <span class="session-history-toggle-icon absolute top-2.5 right-3 text-[var(--text-mutado)] text-lg font-mono leading-none cursor-pointer hover:text-[var(--text-branco)] transition-colors select-none">+</span>
            `;
            mountCollapsibleCard(card, header, (bodyInner) => loadDayRoundCards(sessoes, bodyInner));
        });
        renderSalvoCardIfNeeded();
    }
    async function prefetchSessionDetails() {
        await ensureSessionDetailsLoaded();
        renderSalvoCardIfNeeded();
    }


export {
    updateShowButtonsState,
    updateActionButtons,
    setHistoryActionButtonsVisible,
    selectHistoryTask,
    toggleSessionHistory,
    closeConfirmDeletePopup,
    requestDeleteSelectedTask,
    performDeleteSelectedTask,
    closeRestoreConfirmPopup,
    requestRestoreTask,
    performSessionRestore,
    toggleSaveSelectedTask,
    renderDayRoundCards,
    loadDayRoundCards,
    epochDeId,
    collectAllRoundIds,
    marcarCheckpoint,
    createHistoryRoundCard,
    updateRoundCardSavedIconByTurnId,
    updateRoundCardNameByTurnId,
    collectSavedRounds,
    renderSalvoCardIfNeeded,
    assignDisplayNamesByDay,
    renderSalvoCard,
    loadSavedRoundCards,
    selectHistoryTaskInPile,
    openHistorySearchInCol3,
    collapseHistorySearchInline,
    toggleHistorySearchInline,
    openHistorySearchPanel,
    performHistorySearch,
    createHistorySearchResultCard,
    buildSearchSnippet,
    moveColsToHistory,
    moveColsToDock,
    createLogGroupCard,
    roundMetaHtml,
    saveCurrentTurnSession,
    fetchSessionHistoryData,
    prefetchSessionDetails,
    preloadSessionHistory
};