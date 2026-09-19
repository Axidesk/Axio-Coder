import { state } from '../state.js';
import * as dom from '../dom.js';
import { closeHistoryPanel, isHistoryOpen, openHistory } from '../layout.js';
import { escapeHtml } from '../messages.js';
import { syncMenuIcons } from '../ui.js';
import { setHistoryActionButtonsVisible, updateActionButtons } from './acoes.js';
import { abrirColunasDoHistorico } from './busca.js';
import { ensureSessionDetailsLoaded, loadDayRoundCards, mountCollapsibleCard, renderSalvoCardIfNeeded } from './cards.js';
import { fetchSessionHistoryData } from './estado.js';

const { historyLogsWrapper, panelTitle } = dom;

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
        const sessoesPorDia = new Map();
        state.sessionHistoryList.forEach(sessao => {
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            if (!sessoesPorDia.has(dia)) sessoesPorDia.set(dia, []);
            sessoesPorDia.get(dia).push(sessao);
        });
        const dias = Array.from(sessoesPorDia.keys()).sort((a, b) => {
            const ta = Math.max(...sessoesPorDia.get(a).map(s => s.timestamp || 0));
            const tb = Math.max(...sessoesPorDia.get(b).map(s => s.timestamp || 0));
            return tb - ta;
        });
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
    async function toggleSessionHistory() {
        if (isHistoryOpen()) {
            closeHistoryPanel();
            return;
        }
        abrirColunasDoHistorico();
        openHistory();
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
    function preloadSessionHistory() {
        if (state.sessionHistoryLoaded) return;
        fetchSessionHistoryData()
            .then(() => {
                prefetchSessionDetails();
            })
            .catch(() => {
                if (state.historyPreloadTimer) return;
                state.historyPreloadTimer = setTimeout(() => {
                    state.historyPreloadTimer = null;
                    preloadSessionHistory();
                }, 2000);
            });
    }


export {
    preloadSessionHistory,
    toggleSessionHistory,
    prefetchSessionDetails
};
