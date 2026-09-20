import { state } from '../state.js';
import * as dom from '../dom.js';
import { vistaDe } from '../colunas.js';
import { escapeHtml } from '../messages.js';
import { openFilesPanel } from './acoes.js';
import { assignDisplayNamesByDay, carregarRodadaCompleta, ensureSessionDetailsLoaded, rebuildGroupFromSaved, selectHistoryTaskInPile } from './cards.js';

const { btnHistorySearch, historySearchBox, historySearchLupa, historySearchInputInline, historySearchResultsInline, historySearchRespostas, buscaContaPerguntas, buscaContaRespostas, panelCol1, slidingPanelContainer } = dom;

const MSG_VAZIO_PERGUNTAS = 'Nenhuma pergunta encontrada com esse termo.';
const MSG_VAZIO_RESPOSTAS = 'Nenhuma resposta encontrada com esse termo.';

    function collapseHistorySearchInline() {
        state.historySearchInlineActive = false;
        if (panelCol1) panelCol1.classList.remove('history-search-open', 'history-search-expanded');
        if (slidingPanelContainer) slidingPanelContainer.classList.remove('history-search-expanded');
        if (btnHistorySearch) btnHistorySearch.classList.remove('hide');
        if (historySearchBox) historySearchBox.classList.remove('aberta');
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
        if (btnHistorySearch) btnHistorySearch.classList.add('hide');
        if (historySearchBox) historySearchBox.classList.add('aberta');
        const termoAberto = historySearchInputInline ? historySearchInputInline.value.trim() : '';
        if (termoAberto) performHistorySearch(termoAberto);
        else if (!jaAberta) limparColunas();
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
        if (historySearchLupa) historySearchLupa.addEventListener('click', () => collapseHistorySearchInline());
        let searchTimer = null;
        historySearchInputInline.addEventListener('input', () => {
            clearTimeout(searchTimer);
            const termo = historySearchInputInline.value.trim();
            if (!termo) {
                limparColunas();
                return;
            }
            searchTimer = setTimeout(() => performHistorySearch(termo), 200);
        });
        historySearchInputInline.addEventListener('focus', () => {
            if (!panelCol1 || !panelCol1.classList.contains('history-search-expanded')) abrirBuscaInline();
        });
    }
    async function performHistorySearch(termo) {
        const buscando = '<div class="text-xs text-[var(--text-mutado)] italic">Buscando...</div>';
        if (historySearchResultsInline) historySearchResultsInline.innerHTML = buscando;
        if (historySearchRespostas) historySearchRespostas.innerHTML = buscando;
        const termoLower = termo.toLowerCase();
        await ensureSessionDetailsLoaded();
        assignDisplayNamesByDay();
        const perguntas = [];
        const respostas = [];
        for (const sessao of state.sessionHistoryList) {
            const logs = state.sessionDetailCache[sessao.filename] || [];
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            logs.forEach(saved => {
                const comum = {
                    nome: saved.displayName || saved.name || 'Tarefa',
                    dia,
                    hora: saved.timestamp || '',
                    saved
                };
                const pergunta = primeiroComTermo(saved.questions || [], termoLower);
                if (pergunta) perguntas.push(Object.assign({ texto: pergunta }, comum));
                const resposta = primeiroComTermo([saved.aiResponse || ''], termoLower);
                if (resposta) respostas.push(Object.assign({ texto: resposta }, comum));
            });
        }
        pintarColuna(historySearchResultsInline, buscaContaPerguntas, perguntas, termoLower, MSG_VAZIO_PERGUNTAS);
        pintarColuna(historySearchRespostas, buscaContaRespostas, respostas, termoLower, MSG_VAZIO_RESPOSTAS);
    }
    function limparColunas() {
        if (historySearchResultsInline) historySearchResultsInline.innerHTML = '';
        if (historySearchRespostas) historySearchRespostas.innerHTML = '';
        if (buscaContaPerguntas) buscaContaPerguntas.textContent = '';
        if (buscaContaRespostas) buscaContaRespostas.textContent = '';
    }
    function primeiroComTermo(textos, termoLower) {
        for (const texto of textos) {
            const bruto = String(texto == null ? '' : texto);
            if (bruto.toLowerCase().includes(termoLower)) return bruto;
        }
        return '';
    }
    function pintarColuna(container, conta, resultados, termoLower, vazio) {
        if (!container) return;
        if (conta) conta.textContent = resultados.length ? String(resultados.length) : '';
        if (resultados.length === 0) {
            container.innerHTML = '<div class="text-xs text-[var(--text-mutado)] italic">' + vazio + '</div>';
            return;
        }
        container.innerHTML = '';
        resultados.forEach((r, i) => {
            if (i > 0) {
                const sep = document.createElement('div');
                sep.className = 'busca-separador';
                container.appendChild(sep);
            }
            container.appendChild(createHistorySearchResultCard(r, termoLower));
        });
    }
    function createHistorySearchResultCard(r, termoLower) {
        const card = document.createElement('div');
        card.className = 'flex flex-col gap-1 py-1';
        const nome = document.createElement('div');
        nome.className = 'text-[13px] font-bold text-[var(--text-code-dark)] leading-tight cursor-pointer hover:text-[var(--oliva)] hover:underline transition-colors';
        nome.textContent = r.nome;
        nome.title = 'Abrir tarefa correspondente';
        nome.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!r.saved) return;
            collapseHistorySearchInline();
            await carregarRodadaCompleta(r.saved);
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
        trecho.innerHTML = buildSearchSnippet(r.texto, termoLower);
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
        vista.aoSelecionarArquivo = collapseHistorySearchInline;
        vista.abrirCol2();
        vista.lista.innerHTML = '<div class="panel-empty">Selecione uma tarefa no histórico para ver os arquivos editados.</div>';
    }


export {
    collapseHistorySearchInline,
    toggleHistorySearchInline,
    abrirColunasDoHistorico
};
