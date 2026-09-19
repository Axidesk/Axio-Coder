import { state } from '../state.js';
import * as dom from '../dom.js';
import { vistaDe } from '../colunas.js';
import { escapeHtml } from '../messages.js';
import { openFilesPanel } from './acoes.js';
import { assignDisplayNamesByDay, ensureSessionDetailsLoaded, rebuildGroupFromSaved, selectHistoryTaskInPile } from './cards.js';

const { btnHistorySearch, historySearchInputInline, historySearchResultsInline, panelCol1, slidingPanelContainer } = dom;

const MSG_BUSCA_INICIAL = '<div class="text-xs text-[var(--text-mutado)] italic">Digite para buscar nas mensagens enviadas.</div>';

    function collapseHistorySearchInline() {
        state.historySearchInlineActive = false;
        if (panelCol1) panelCol1.classList.remove('history-search-open', 'history-search-expanded');
        if (slidingPanelContainer) slidingPanelContainer.classList.remove('history-search-expanded');
        if (btnHistorySearch) {
            btnHistorySearch.classList.remove('text-[var(--oliva)]');
            btnHistorySearch.classList.add('text-[var(--text-mutado)]');
        }
    }
    function encolherBuscaInline() {
        if (!state.historySearchInlineActive) return;
        if (panelCol1) panelCol1.classList.remove('history-search-expanded');
        if (slidingPanelContainer) slidingPanelContainer.classList.remove('history-search-expanded');
    }
    function abrirBuscaInline() {
        const vistaHistorico = vistaDe('historico');
        if (vistaHistorico && vistaHistorico.col3Aberta()) vistaHistorico.fecharCol3();
        const jaAberta = state.historySearchInlineActive;
        state.historySearchInlineActive = true;
        if (panelCol1) panelCol1.classList.add('history-search-open', 'history-search-expanded');
        if (slidingPanelContainer) slidingPanelContainer.classList.add('history-search-expanded');
        if (btnHistorySearch) {
            btnHistorySearch.classList.add('text-[var(--oliva)]');
            btnHistorySearch.classList.remove('text-[var(--text-mutado)]');
        }
        if (!jaAberta && historySearchResultsInline) historySearchResultsInline.innerHTML = MSG_BUSCA_INICIAL;
        ligarBuscaInline();
        if (historySearchInputInline) historySearchInputInline.focus();
    }
    function toggleHistorySearchInline() {
        const esticada = !!panelCol1 && panelCol1.classList.contains('history-search-expanded');
        if (state.historySearchInlineActive && esticada) {
            collapseHistorySearchInline();
            return;
        }
        abrirBuscaInline();
    }
    function ligarBuscaInline() {
        if (!historySearchInputInline || !historySearchResultsInline) return;
        if (historySearchInputInline.dataset.buscaLigada === '1') return;
        historySearchInputInline.dataset.buscaLigada = '1';
        let searchTimer = null;
        historySearchInputInline.addEventListener('input', () => {
            clearTimeout(searchTimer);
            const termo = historySearchInputInline.value.trim();
            if (!termo) {
                historySearchResultsInline.innerHTML = MSG_BUSCA_INICIAL;
                return;
            }
            searchTimer = setTimeout(() => performHistorySearch(termo, historySearchResultsInline), 200);
        });
        historySearchInputInline.addEventListener('focus', () => {
            if (!panelCol1 || !panelCol1.classList.contains('history-search-expanded')) abrirBuscaInline();
        });
    }
    async function performHistorySearch(termo, resultsContainer) {
        resultsContainer.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">Buscando...</div>';
        const termoLower = termo.toLowerCase();
        await ensureSessionDetailsLoaded();
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
                        break;
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
            const group = rebuildGroupFromSaved(r.saved);
            group.displayName = r.nome;
            selectHistoryTaskInPile(r.dia, r.saved.id);
            openFilesPanel(group, vistaDe('historico'));
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
    function abrirColunasDoHistorico() {
        const vista = vistaDe('historico');
        if (!vista) return;
        vista.aoAbrirCol3 = encolherBuscaInline;
        vista.abrirCol2();
        vista.lista.innerHTML = '<div class="panel-empty">Selecione uma tarefa no histórico para ver os arquivos editados.</div>';
    }


export {
    collapseHistorySearchInline,
    toggleHistorySearchInline,
    abrirColunasDoHistorico
};
