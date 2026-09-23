import { state } from '../state.js';
import * as dom from '../dom.js';
import { createChildBalloon } from '../files.js';
import { vistaDe } from '../colunas.js';
import { escapeHtml, showQuestionPanel } from '../messages.js';
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
            __saved: saved,
            snapshot: saved.snapshot || {},
            aiResponse: saved.aiResponse || '',
            salvo: !!saved.salvo,
            commit: saved.commit || '',
            duration: saved.duration || 0,
            nFerramentas: saved.nFerramentas,
            tools: saved.tools || [],
            thoughts: saved.thoughts || [],
            questions: saved.questions || [],
            files: filesDoSaved(saved)
        };
    }
    function filesDoSaved(saved) {
        return (saved.files || []).map(f => ({
            name: f.name,
            deleted: !!f.deleted,
            diffElements: (f.diffs || []).map(d => createChildBalloon(
                d.title, d.htmlContent, d.snippetHtml, d.rawTextOld, d.rawTextNew, d.fileName,
                null, d.fullOriginalText, d.fullNewText, d.deletedLines, d.addedLines, d.origToMod, d.modToOrig, d.subtitle
            ))
        }));
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
        const toolCount = (group.tools || []).length || group.nFerramentas || 0;
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
        if (group.commit) _marcasDoCard(sub, group);
        sub.dataset.turnId = group.id;
        group.domElement = sub;
        group.nameEl = sub.querySelector('.history-round-name');
        sub._group = group;
        marcarCheckpoint(sub, group.id);
        sub.addEventListener('click', async () => {
            const vista = vistaDe('historico');
            const isSelected = state.currentSelectedHistoryGroup === group;
            if (!isSelected) {
                selectHistoryTask(group, sub);
                openFilesPanel(await hidratarGroup(group), vista);
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
    const SVG_AVIAO_CARD = `<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-[var(--oliva)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`;

    const SVG_SALVAR_CARD = `<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-[var(--text-suave)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>`;

    function _injectMarcas(el, titulo, tag, enviada) {
        el.querySelectorAll('.history-round-saved-icon, .history-round-tag').forEach(m => m.remove());
        const row = el.firstElementChild;
        if (!row) return;
        if (tag) {
            const chip = document.createElement('span');
            chip.className = 'shrink-0 mt-0.5 history-round-tag';
            chip.textContent = tag;
            row.appendChild(chip);
        }
        if (!titulo) return;
        const salvo = document.createElement('span');
        salvo.className = 'shrink-0 mt-0.5 history-round-saved-icon';
        salvo.title = titulo;
        salvo.innerHTML = SVG_SALVAR_CARD;
        row.appendChild(salvo);
        if (!enviada) return;
        const aviao = document.createElement('span');
        aviao.className = 'shrink-0 mt-0.5 history-round-saved-icon';
        aviao.title = 'Enviada para o GitHub';
        aviao.innerHTML = SVG_AVIAO_CARD;
        row.appendChild(aviao);
    }
    function enviadaParaOServidor(hash) {
        if (!hash || !state.temRemotoGit || !state.porSubirLido) return false;
        return !(state.commitsPorSubir || []).includes(hash);
    }
    function _marcasDoCard(el, grupo) {
        const commit = grupo && grupo.commit ? grupo.commit : '';
        if (!commit) {
            _injectMarcas(el, '', '', false);
            return;
        }
        const tag = tagDoCommit(commit);
        const curto = String(commit).slice(0, 7);
        if (!enviadaParaOServidor(commit)) {
            _injectMarcas(el, 'Guardada no PC (' + curto + '), por enviar', tag, false);
            return;
        }
        _injectMarcas(el, 'Guardada e enviada para o GitHub (' + curto + ')', tag, true);
    }
    function atualizarMarcasDosCards() {
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (el._group) _marcasDoCard(el, el._group);
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
    function updateRoundCardCommitByTurnId(turnId, hash) {
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (String(el.dataset.turnId) !== String(turnId)) return;
            const g = el._group;
            if (g) g.commit = hash || '';
            if (g) _marcasDoCard(el, g);
        });
    }
    function turnosComCommit() {
        const turnos = [];
        for (const sessao of state.sessionHistoryList) {
            const logs = state.sessionDetailCache[sessao.filename] || [];
            logs.forEach(l => {
                if (l.commit) turnos.push({ ...l, __session: sessao.filename, __date: (sessao.datetime || '').split(' ')[0] || '' });
            });
        }
        return turnos;
    }
    function tarefasDaTag(tag) {
        const alvo = new Set((tag && tag.commits) || []);
        if (!alvo.size) return [];
        return turnosComCommit().filter(l => alvo.has(l.commit)).map(rebuildGroupFromSaved);
    }
    function nomeDaTarefaDoCommit(hash) {
        if (!hash) return '';
        const daLista = (lista) => {
            const achado = (lista || []).find(l => (l.commit || (state.commitsDosTurnos || {})[String(l.id)] || '') === hash);
            return achado ? (achado.displayName || achado.name || '') : '';
        };
        const doTurnoAtual = daLista(state.currentTurnLogs);
        if (doTurnoAtual) return doTurnoAtual;
        for (const sessao of state.sessionHistoryList) {
            const nome = daLista(state.sessionDetailCache[sessao.filename]);
            if (nome) return nome;
        }
        return '';
    }
    function tagDoCommit(hash) {
        if (!hash || !state.versoesGit) return '';
        const tag = (state.versoesGit.tags || []).find(t => t.ponto === hash);
        return tag ? tag.nome : '';
    }
    function dataKey(d) {
        const p = (d || '').split('/');
        return p.length === 3 ? `${p[2]}${p[1]}${p[0]}` : '';
    }
    function ordenarPorTempo(groups) {
        return groups.sort((a, b) => {
            const ka = dataKey(a.__date) + (a.timestamp || '');
            const kb = dataKey(b.__date) + (b.timestamp || '');
            return kb.localeCompare(ka);
        });
    }
    function formatarData(iso) {
        const dia = String(iso || '').slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dia)) return '';
        const [a, m, d] = dia.split('-');
        return `${d}/${m}/${a}`;
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
    function criarCardDePilha(titulo, subtitulo, marca, loadCallback) {
        const card = document.createElement('div');
        card.className = 'session-history-card session-history-versoes';
        card.dataset[marca] = 'true';
        const header = document.createElement('div');
        header.className = 'session-history-header relative flex flex-col gap-1 justify-center w-full text-left px-3.5 py-2.5 cursor-pointer min-h-[54px]';
        header.innerHTML = `
            <span class="block text-[13px] font-semibold text-[var(--oliva)] leading-tight pr-6">${escapeHtml(titulo)}</span>
            ${subtitulo ? `<span class="block text-[11px] text-[var(--text-mutado)] leading-tight pr-6">${escapeHtml(subtitulo)}</span>` : ''}
            <span class="session-history-toggle-icon absolute top-2.5 right-3 text-[var(--text-mutado)] text-lg font-mono leading-none cursor-pointer hover:text-[var(--text-branco)] transition-colors select-none">+</span>
        `;
        mountCollapsibleCard(card, header, loadCallback);
        return card;
    }
    function subtituloDaTag(tag) {
        const partes = [];
        const tarefas = tarefasDaTag(tag).length;
        if (tag.fora) partes.push('ponto fora da historia atual');
        else if (tarefas) partes.push(tarefas === 1 ? '1 tarefa' : `${tarefas} tarefas`);
        else if (tag.truncado) partes.push(`${(tag.commits || []).length}+ commits`);
        else partes.push(`${(tag.commits || []).length} commits`);
        const data = formatarData(tag.data);
        if (data) partes.push(data);
        return partes.join(' · ');
    }
    function subtituloDoRamo(ramo) {
        const partes = [ramo.atual ? 'em uso' : ramo.nome];
        partes.push(ramo.por_publicar
            ? (ramo.por_publicar === 1 ? '1 por publicar' : `${ramo.por_publicar} por publicar`)
            : 'tudo publicado');
        return partes.join(' · ');
    }
    let versoesGeracao = 0;
    async function renderVersoesCards() {
        const geracao = ++versoesGeracao;
        const versoes = await carregarVersoes();
        if (geracao !== versoesGeracao || !historyLogsWrapper) return;
        historyLogsWrapper.querySelectorAll('.session-history-versoes').forEach(el => el.remove());
        (versoes.ramos || []).forEach(ramo => {
            const card = criarCardDePilha(
                ramo.atual ? `Ramo ${ramo.nome}` : ramo.nome,
                subtituloDoRamo(ramo),
                'ramo',
                body => loadRamoCards(ramo, body)
            );
            historyLogsWrapper.appendChild(card);
        });
        (versoes.tags || []).forEach(tag => {
            const card = criarCardDePilha(tag.nome, subtituloDaTag(tag), 'versoes', body => loadVersaoCards(tag, body));
            historyLogsWrapper.appendChild(card);
        });
        marcarTagsNosCards();
    }
    async function loadVersaoCards(tag, body) {
        await ensureSessionDetailsLoaded();
        assignDisplayNamesByDay();
        const grupos = tarefasDaTag(tag);
        if (!grupos.length) {
            const aviso = tag.fora
                ? 'O ponto desta etiqueta nao esta na historia atual.'
                : 'Nenhuma tarefa do historico foi commitada neste intervalo.';
            body.innerHTML = `<div class="p-3 text-xs text-[var(--text-mutado)] font-mono">${aviso}</div>`;
            return;
        }
        body.innerHTML = '';
        ordenarPorTempo(grupos).forEach(g => body.appendChild(createHistoryRoundCard(g)));
    }
    async function loadRamoCards(ramo, body) {
        await ensureSessionDetailsLoaded();
        assignDisplayNamesByDay();
        const alvo = new Set(ramo.todos && ramo.todos.length ? ramo.todos : ramo.commits || []);
        const grupos = turnosComCommit().filter(l => alvo.has(l.commit)).map(rebuildGroupFromSaved);
        if (!grupos.length) {
            body.innerHTML = '<div class="p-3 text-xs text-[var(--text-mutado)] font-mono">Nenhuma tarefa commitada neste ramo.</div>';
            return;
        }
        body.innerHTML = '';
        ordenarPorTempo(grupos).forEach(g => body.appendChild(createHistoryRoundCard(g)));
    }
    function marcarTagsNosCards() {
        document.querySelectorAll('.history-round-card').forEach(el => {
            const grupo = el._group;
            if (!grupo || !grupo.commit) return;
            _marcasDoCard(el, grupo);
        });
    }
    async function ensureSessionDetailsLoaded() {
        await carregarPorSubir();
        if (!state.sessionHistoryList.some(s => state.sessionDetailCache[s.filename] === undefined)) return;
        if (!state.sessionIndiceEmCurso) state.sessionIndiceEmCurso = carregarIndiceDeSessoes();
        try {
            await state.sessionIndiceEmCurso;
        } finally {
            state.sessionIndiceEmCurso = null;
        }
    }
    async function carregarIndiceDeSessoes() {
        try {
            const resp = await fetch('/api/sessions_index');
            const data = await resp.json();
            (data.sessions || []).forEach(s => {
                state.sessionDetailCache[s.filename] = (s.rounds || []).map(r => ({ ...r, __session: s.filename, __leve: true }));
            });
        } catch (e) {
            console.error('Erro ao carregar o índice de sessões:', e);
        }
    }
    async function carregarVersoes() {
        if (state.versoesGit) return state.versoesGit;
        if (!state.versoesEmCurso) {
            state.versoesEmCurso = fetch('/api/git/versoes')
                .then(r => r.json())
                .then(d => (d && d.status === 'ok'
                    ? { tags: d.tags || [], ramos: d.ramos || [] }
                    : { tags: [], ramos: [], semRepo: true }))
                .catch(() => ({ tags: [], ramos: [], erro: true }))
                .finally(() => { state.versoesEmCurso = null; });
        }
        state.versoesGit = await state.versoesEmCurso;
        return state.versoesGit;
    }
    async function carregarPorSubir(forcar) {
        if (!forcar && state.porSubirLido) return;
        if (!forcar && state.porSubirEmCurso) return state.porSubirEmCurso;
        state.porSubirEmCurso = fetch('/api/git/por_subir')
            .then(r => r.json())
            .then(d => {
                if (!d || d.status !== 'ok') return;
                state.temRemotoGit = !!d.remoto;
                state.commitsPorSubir = (d.commits ? d.commits : []).map(c => c.hash);
                state.porSubirLido = true;
                atualizarMarcasDosCards();
            })
            .catch(() => {})
            .finally(() => { state.porSubirEmCurso = null; });
        return state.porSubirEmCurso;
    }
    async function carregarRodadaCompleta(saved) {
        if (!saved || !saved.__leve || !saved.__session) return saved;
        if (!saved.__pesadaEmCurso) saved.__pesadaEmCurso = _buscarRodadaCompleta(saved);
        try {
            return await saved.__pesadaEmCurso;
        } finally {
            delete saved.__pesadaEmCurso;
        }
    }
    async function _buscarRodadaCompleta(saved) {
        try {
            const resp = await fetch(`/api/session_round?file=${encodeURIComponent(saved.__session)}&id=${encodeURIComponent(saved.id)}`);
            const data = await resp.json();
            if (data && !data.error) {
                saved.files = data.files || [];
                saved.snapshot = data.snapshot || {};
                saved.tools = data.tools || [];
                saved.thoughts = data.thoughts || [];
                saved.questions = data.questions || saved.questions || [];
                saved.aiResponse = data.aiResponse || saved.aiResponse || '';
                delete saved.__leve;
            }
        } catch (e) {
            console.error('Erro ao carregar a tarefa completa:', e);
        }
        return saved;
    }
    async function hidratarGroup(group) {
        if (!group || !group.__saved) return group;
        const saved = await carregarRodadaCompleta(group.__saved);
        group.snapshot = saved.snapshot || {};
        group.aiResponse = saved.aiResponse || '';
        group.tools = saved.tools || [];
        group.thoughts = saved.thoughts || [];
        group.questions = saved.questions || [];
        group.nFerramentas = group.tools.length || saved.nFerramentas || 0;
        group.files = filesDoSaved(saved);
        return group;
    }
    async function selectHistoryTaskInPile(dia, turnId) {
        if (!dia || !turnId) return null;
        const dayCard = Array.from(document.querySelectorAll('.session-history-card')).find(c => c.dataset.dia === dia);
        if (!dayCard) return null;
        const header = dayCard.querySelector('.session-history-header');
        const body = dayCard.querySelector('.session-history-body');
        if (!header || !body) return null;
        const selectRound = () => {
            const round = Array.from(body.querySelectorAll('.history-round-card')).find(el => el.dataset.turnId === turnId);
            if (!round) return null;
            document.querySelectorAll('.history-round-card').forEach(el => el.classList.remove('history-round-selected'));
            round.classList.add('history-round-selected');
            state.currentSelectedHistoryGroup = round._group || null;
            state.currentSelectedHistoryEl = round;
            updateActionButtons();
            round.scrollIntoView({ block: 'nearest' });
            return round._group || null;
        };
        if (!body.classList.contains('card-collapsible-open')) {
            header.click();
        }
        const direto = selectRound();
        if (direto) return direto;
        for (let tentativas = 0; tentativas < 30; tentativas++) {
            await new Promise(resolve => setTimeout(resolve, 100));
            const grupo = selectRound();
            if (grupo) return grupo;
        }
        return null;
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
        await ensureSessionDetailsLoaded();
        const savedLogs = [];
        sessoes.forEach(sessao => {
            savedLogs.push(...(state.sessionDetailCache[sessao.filename] || []));
        });
        renderDayRoundCards(savedLogs, body);
    }


export {
    createLogGroupCard,
    roundMetaHtml,
    loadDayRoundCards,
    mountCollapsibleCard,
    renderVersoesCards,
    nomeDaTarefaDoCommit,
    assignDisplayNamesByDay,
    ensureSessionDetailsLoaded,
    hidratarGroup,
    rebuildGroupFromSaved,
    selectHistoryTaskInPile,
    updateRoundCardCommitByTurnId,
    updateRoundCardNameByTurnId,
    carregarPorSubir,
    atualizarMarcasDosCards,
    enviadaParaOServidor
};
