import { state } from '../state.js';
import * as dom from '../dom.js';
import { createChildBalloon } from '../files.js';
import { vistaDe } from '../colunas.js';
import { escapeHtml, showQuestionPanel } from '../messages.js';
import { showAlert } from '../ui.js';
import { openFilesPanel, selectHistoryTask, updateActionButtons } from './acoes.js';
import { epochDeId, marcarCheckpoint } from './checkpoint.js';

const { historyLogsWrapper } = dom;

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
            const vista = vistaDe('dock');
            const wasActive = card.classList.contains('log-card-active');
            const col2Open = !!vista.col2 && !vista.col2.classList.contains('panel-col-closed');
            if (wasActive && col2Open) {
                vista.fecharCol2();
                return;
            }
            document.querySelectorAll('.log-card').forEach(el => el.classList.remove('log-card-active'));
            card.classList.add('log-card-active');
            openFilesPanel(group, vista);
        });
        group.domElement = card;
        group.timeSpan = timeSpan;
        group.titleSpan = titleSpan;
        group.spinner = spinner;
        return card;
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
            const vista = vistaDe('historico');
            const isSelected = state.currentSelectedHistoryGroup === group;
            if (!isSelected) {
                selectHistoryTask(group, sub);
                openFilesPanel(group, vista);
                return;
            }
            if (vista.col3Aberta()) {
                vista.fecharCol3();
                return;
            }
            showQuestionPanel(group, vista);
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
            const resp = await fetch('/api/session_log/toggle_save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: group.__session, round_id: group.id || '' })
            });
            const data = await resp.json();
            if (data && data.status === 'ok') {
                group.salvo = !!data.salvo;
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
        const existing = document.querySelector('.session-history-card[data-salvo="true"]');
        if (existing) existing.remove();
        if (collectSavedRounds().length === 0) return;
        renderSalvoCard();
    }
    function assignDisplayNamesByDay() {
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
                const resp = await fetch(`/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
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
        if (!dayCard) return;
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
        if (!body.classList.contains('card-collapsible-open')) {
            header.click();
        }
        if (selectRound()) return;
        let tentativas = 0;
        const poll = setInterval(() => {
            if (selectRound() || ++tentativas >= 30) clearInterval(poll);
        }, 100);
    }
    function renderDayRoundCards(savedLogs, body) {
        if (!savedLogs || savedLogs.length === 0) {
            body.innerHTML = '<div class="p-3 text-xs text-[var(--text-mutado)] font-mono">Nenhuma rodada de edição neste dia.</div>';
            return;
        }
        const groups = savedLogs.map(saved => rebuildGroupFromSaved(saved));
        const ordemCronológica = [...groups].sort((a, b) => epochDeId(a.id) - epochDeId(b.id));
        ordemCronológica.forEach((g, idx) => {
            g.displayName = g.name || ('Tarefa ' + (idx + 1));
        });
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
                const resp = await fetch(`/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
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


export {
    createLogGroupCard,
    roundMetaHtml,
    loadDayRoundCards,
    mountCollapsibleCard,
    renderSalvoCardIfNeeded,
    assignDisplayNamesByDay,
    ensureSessionDetailsLoaded,
    rebuildGroupFromSaved,
    selectHistoryTaskInPile,
    updateRoundCardNameByTurnId,
    toggleSaveSelectedTask
};
