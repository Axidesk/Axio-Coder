import { state } from '../state.js';
import * as dom from '../dom.js';
import { createChildBalloon } from '../files.js';
import { vistaDe } from '../colunas.js';
import { escapeHtml, showQuestionPanel } from '../messages.js';
import { openFilesPanel, selectHistoryTask, updateActionButtons } from './acoes.js';
import { epochDeId, marcarCheckpoint } from './checkpoint.js';
import { esquecerCache as esquecerMarcasDeEnvio, marcasDeEnvio, registarLeitura, semearSeVazio } from './marcas_envio.js';
import { svgDoPonto, svgDoAviao, svgDoRestauro } from '../icones.js';

const { historyLogsWrapper } = dom;

let sincronizacaoDoEnvio = null;
let apiDeRestauro = null;
let cacheDoUltimoEnviado = '';
let cacheDoUltimoEnviadoValida = false;

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
            commitNome: saved.commit_nome || '',
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
    function createHistoryRoundCard(group, opcoes) {
        const absorvido = !!(opcoes && opcoes.absorvido);
        const sub = document.createElement('div');
        sub.className = 'history-round-card relative flex flex-col gap-1 w-full text-left px-3.5 py-2.5 rounded-[10px] cursor-pointer text-sm'
            + (absorvido ? ' history-round-card-absorvido' : '');
        const hora = group.timestamp ? escapeHtml(group.timestamp) : '—';
        const data = group.__date ? ' - ' + escapeHtml(group.__date) : '';
        const nome = escapeHtml(tituloDaTarefa(group));
        const content = document.createElement('div');
        content.className = 'flex-1 min-w-0';
        const meta = absorvido ? '' : `<div class="text-[11px] text-[var(--text-mutado)] truncate leading-tight">${roundMetaHtml(group)}</div>`;
        content.innerHTML = `
            <div class="text-[13px] leading-tight">
                <span class="history-round-name font-bold text-[var(--text-code-dark)]">${nome}</span>
            </div>
            ${meta}
            <div class="text-[11px] text-[var(--text-mutado)] leading-tight">${hora}${data}</div>
        `;
        const row = document.createElement('div');
        row.className = 'flex items-start gap-2';
        row.appendChild(content);
        sub.appendChild(row);
        _marcasDoCard(sub, group);
        if (!absorvido && group.absorveu && group.absorveu.length) {
            sub.appendChild(montarGaveta(group.absorveu));
        }
        sub.dataset.turnId = group.id;
        group.domElement = sub;
        group.nameEl = sub.querySelector('.history-round-name');
        sub._group = group;
        marcarCheckpoint(sub, group.id);
        sub.addEventListener('click', async (evento) => {
            evento.stopPropagation();
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
    function montarGaveta(absorbidos) {
        const gaveta = document.createElement('div');
        gaveta.className = 'history-absorvidos';
        const cabecalho = document.createElement('button');
        cabecalho.type = 'button';
        cabecalho.className = 'history-absorvidos-cabecalho';
        const quantas = absorbidos.length === 1 ? '1 tarefa absorvida' : `${absorbidos.length} tarefas absorvidas`;
        cabecalho.innerHTML = `<span>${quantas}</span><span class="history-absorvidos-sinal">+</span>`;
        const corpo = document.createElement('div');
        corpo.className = 'card-collapsible';
        const clip = document.createElement('div');
        clip.className = 'card-collapsible-clip';
        const lista = document.createElement('div');
        lista.className = 'history-absorvidos-lista';
        absorbidos.forEach(g => lista.appendChild(createHistoryRoundCard(g, { absorvido: true })));
        clip.appendChild(lista);
        corpo.appendChild(clip);
        gaveta.appendChild(cabecalho);
        gaveta.appendChild(corpo);
        const sinal = cabecalho.querySelector('.history-absorvidos-sinal');
        cabecalho.addEventListener('click', (evento) => {
            evento.stopPropagation();
            const aberto = corpo.classList.toggle('card-collapsible-open');
            sinal.textContent = aberto ? '-' : '+';
        });
        return gaveta;
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
    function _injectMarcas(el, grupo, titulo, tag, ultimo) {
        el.querySelectorAll('.history-round-saved-icon, .history-round-enviado-icon, .history-round-restore-icon, .history-round-tag').forEach(m => m.remove());
        const row = el.firstElementChild;
        if (!row) return;
        if (tag) {
            const chip = document.createElement('span');
            chip.className = 'shrink-0 mt-0.5 history-round-tag';
            chip.textContent = tag;
            row.appendChild(chip);
        }
        if (titulo && !ultimo) {
            const salvo = document.createElement('span');
            salvo.className = 'shrink-0 mt-0.5 history-round-saved-icon';
            salvo.title = titulo;
            salvo.innerHTML = svgDoPonto('h-3.5 w-3.5 text-[var(--text-suave)]');
            row.appendChild(salvo);
        }
        if (apiDeRestauro && apiDeRestauro.pode(grupo)) {
            const restaurar = document.createElement('button');
            restaurar.type = 'button';
            restaurar.className = 'shrink-0 mt-0.5 history-round-restore-icon cursor-pointer text-[var(--text-mutado)] hover:text-[var(--oliva)] transition-colors focus:outline-none';
            restaurar.title = 'Restaurar esta tarefa';
            restaurar.innerHTML = svgDoRestauro('h-3.5 w-3.5');
            restaurar.addEventListener('click', (evento) => {
                evento.stopPropagation();
                apiDeRestauro.restaurar(grupo);
            });
            row.appendChild(restaurar);
        }
        if (!ultimo) return;
        const naNuvem = document.createElement('span');
        naNuvem.className = 'shrink-0 mt-0.5 history-round-enviado-icon';
        naNuvem.title = 'Enviado para o GitHub (' + String((grupo && grupo.commit) || '').slice(0, 7) + ')';
        naNuvem.innerHTML = svgDoAviao('h-3.5 w-3.5 text-[var(--oliva)]');
        row.appendChild(naNuvem);
    }
    function enviadaParaOServidor(hash) {
        if (!hash || !state.temRemotoGit || !state.porSubirLido) return false;
        if (state.porSubirTruncado) return false;
        return !(state.commitsPorSubir || []).includes(hash);
    }
    function _esquecerUltimoEnviado() {
        cacheDoUltimoEnviadoValida = false;
    }
    function ultimoEnviadoParaOServidor() {
        if (cacheDoUltimoEnviadoValida) return cacheDoUltimoEnviado;
        let melhor = '';
        let melhorEpoch = -1;
        turnosComCommit().forEach(turno => {
            if (!turno.commit || !enviadaParaOServidor(turno.commit)) return;
            const epoch = epochDeId(turno.id);
            if (epoch < melhorEpoch) return;
            melhorEpoch = epoch;
            melhor = turno.commit;
        });
        cacheDoUltimoEnviado = melhor;
        cacheDoUltimoEnviadoValida = true;
        return melhor;
    }
    function _semearMarcaDeEnvio() {
        if (!state.gitRemoto) return;
        const hash = ultimoEnviadoParaOServidor();
        if (!hash) return;
        const turno = turnosComCommit().find(t => t.commit === hash);
        semearSeVazio(state.gitRemoto, hash, turno ? turno.__date : '');
    }
    function _marcasDoCard(el, grupo) {
        const commit = grupo && grupo.commit ? grupo.commit : '';
        if (!commit) {
            _injectMarcas(el, grupo, '', '', false);
            return;
        }
        const curto = String(commit).slice(0, 7);
        const naNuvem = enviadaParaOServidor(commit);
        const ultimo = marcasDeEnvio().porCommit.has(commit);
        const onde = naNuvem ? ', na nuvem' : ', por enviar';
        _injectMarcas(el, grupo, 'Salvo localmente (' + curto + onde + ')', tagDoCommit(commit), ultimo);
    }
    function _marcasDoDia(el) {
        const anterior = el.querySelector('.history-day-saved-icon');
        if (anterior) anterior.remove();
        if (!marcasDeEnvio().porDia.has(el.dataset.dia || '')) return;
        const row = el.firstElementChild;
        if (!row) return;
        const aviao = document.createElement('span');
        aviao.className = 'shrink-0 mt-0.5 history-day-saved-icon';
        aviao.title = 'O envio automatico levou o trabalho deste dia';
        aviao.innerHTML = svgDoAviao('h-3.5 w-3.5 text-[var(--oliva)]');
        row.appendChild(aviao);
    }
    function atualizarMarcasDosCards() {
        _esquecerUltimoEnviado();
        esquecerMarcasDeEnvio();
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (!el._group) return;
            _marcasDoCard(el, el._group);
            if (el.nameEl) el.nameEl.textContent = tituloDaTarefa(el._group);
        });
        document.querySelectorAll('.session-history-card[data-dia]').forEach(_marcasDoDia);
        _semearMarcaDeEnvio();
        if (sincronizacaoDoEnvio) sincronizacaoDoEnvio();
    }
    function registrarSincronizacaoDoEnvio(fn) {
        sincronizacaoDoEnvio = fn;
    }
    function registrarRestauroDaTarefa(api) {
        apiDeRestauro = api;
    }
    function updateRoundCardCommitByTurnId(turnId, hash) {
        _esquecerUltimoEnviado();
        document.querySelectorAll('.history-round-card').forEach(el => {
            if (String(el.dataset.turnId) !== String(turnId)) return;
            const g = el._group;
            if (g) g.commit = hash || '';
            if (g) _marcasDoCard(el, g);
            if (g && el.nameEl) el.nameEl.textContent = tituloDaTarefa(g);
        });
    }
    const CHAVE_LEMBRETE = 'axio.git.lembrete-visto';

    function turnosSemCommit() {
        const todos = [];
        state.sessionHistoryList.forEach(sessao => {
            todos.push(...(state.sessionDetailCache[sessao.filename] || []));
        });
        todos.sort((a, b) => epochDeId(a.id) - epochDeId(b.id));
        let semPonto = 0;
        for (let i = todos.length - 1; i >= 0 && !todos[i].commit; i--) semPonto++;
        return semPonto;
    }

    async function talvezLembrarDeGuardar() {
        const balao = document.getElementById('git-lembrete-chip');
        if (!balao || localStorage.getItem(CHAVE_LEMBRETE)) return;
        const semPonto = turnosSemCommit();
        if (semPonto < 3) {
            balao.classList.remove('balao-visible');
            return;
        }
        let modo = null;
        try {
            modo = await (await fetch('/api/git/modo')).json();
        } catch (e) {
            return;
        }
        if (!modo || modo.automatico) return;
        balao.textContent = `${semPonto} tarefas ficaram sem ponto de salvamento. Clica para as guardar.`;
        balao.classList.add('balao-visible');
        if (balao.dataset.ligado) return;
        balao.dataset.ligado = 'true';
        balao.addEventListener('click', () => {
            balao.classList.remove('balao-visible');
            localStorage.setItem(CHAVE_LEMBRETE, '1');
            const botao = document.getElementById('btn-show-git-history');
            if (botao) botao.click();
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
    function turnoDoCommit(hash) {
        if (!hash) return null;
        const daLista = (lista) => (lista || []).find(l => (l.commit || (state.commitsDosTurnos || {})[String(l.id)] || '') === hash) || null;
        const doTurnoAtual = daLista(state.currentTurnLogs);
        if (doTurnoAtual) return doTurnoAtual;
        for (const sessao of state.sessionHistoryList) {
            const achado = daLista(state.sessionDetailCache[sessao.filename]);
            if (achado) return achado;
        }
        return null;
    }
    function nomeDaTarefaDoCommit(hash) {
        const turno = turnoDoCommit(hash);
        return turno ? (turno.displayName || turno.name || '') : '';
    }
    function resumoDoCommit(texto) {
        return String(texto || '').trim().split(/\s+/).join(' ');
    }
    function tituloDaTarefa(group) {
        const base = (group && (group.displayName || group.name)) || 'Tarefa';
        return comporTitulo(base, resumoDoCommit(group && group.commitNome));
    }
    function tituloDaTarefaDoCommit(hash, resumoDoPonto) {
        const turno = turnoDoCommit(hash);
        const base = turno ? (turno.displayName || turno.name || '') : '';
        const resumo = resumoDoCommit(resumoDoPonto) || (turno ? resumoDoCommit(turno.commitNome) : '');
        return comporTitulo(base, resumo);
    }
    function comporTitulo(base, resumo) {
        return [base, resumo].filter(Boolean).join(' - ');
    }
    function tagDoCommit(hash) {
        if (!hash || !state.versoesGit) return '';
        const tag = (state.versoesGit.tags || []).find(t => t.ponto === hash);
        return tag ? tag.nome : '';
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
    function marcarTagsNosCards() {
        document.querySelectorAll('.history-round-card').forEach(el => {
            const grupo = el._group;
            if (!grupo || !grupo.commit) return;
            _marcasDoCard(el, grupo);
        });
    }
    async function sincronizarEtiquetasNosCards() {
        await carregarVersoes();
        marcarTagsNosCards();
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
                state.gitRemoto = d.remoto || '';
                state.commitsPorSubir = (d.commits ? d.commits : []).map(c => c.hash);
                state.porSubirTruncado = !!d.truncado;
                state.porSubirLido = true;
                registarLeitura(d.remoto, d.commits || [], !!d.truncado);
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
    function aplicarAbsorvidos(groups) {
        const cronologico = [...groups].sort((a, b) => epochDeId(a.id) - epochDeId(b.id));
        let dono = null;
        const recolhidos = new Set();
        for (let i = cronologico.length - 1; i >= 0; i--) {
            const g = cronologico[i];
            if (g.commit) {
                dono = g;
                continue;
            }
            if (!dono) continue;
            if (!dono.absorveu) dono.absorveu = [];
            dono.absorveu.unshift(g);
            recolhidos.add(g.id);
        }
        if (!recolhidos.size) return groups;
        return groups.filter(g => !recolhidos.has(g.id));
    }
    async function renderDayRoundCards(savedLogs, body) {
        _esquecerUltimoEnviado();
        esquecerMarcasDeEnvio();
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
        const visiveis = aplicarAbsorvidos(groups);
        body.innerHTML = '';
        visiveis.forEach(group => body.appendChild(createHistoryRoundCard(group)));
    }
    async function loadDayRoundCards(sessoes, body) {
        await ensureSessionDetailsLoaded();
        body.classList.add('history-day-rounds');
        body.__sessoes = sessoes;
        const savedLogs = [];
        sessoes.forEach(sessao => {
            savedLogs.push(...(state.sessionDetailCache[sessao.filename] || []));
        });
        await renderDayRoundCards(savedLogs, body);
        talvezLembrarDeGuardar();
    }
    async function reagruparPilhaDoDia() {
        const selecionado = state.currentSelectedHistoryGroup ? String(state.currentSelectedHistoryGroup.id) : '';
        for (const body of Array.from(document.querySelectorAll('.history-day-rounds'))) {
            if (body.__sessoes) await loadDayRoundCards(body.__sessoes, body);
        }
        if (!selecionado) return;
        const card = Array.from(document.querySelectorAll('.history-round-card'))
            .find(el => String(el.dataset.turnId) === selecionado);
        if (!card) return;
        card.classList.add('history-round-selected');
        state.currentSelectedHistoryEl = card;
        state.currentSelectedHistoryGroup = card._group || state.currentSelectedHistoryGroup;
    }


export {
    createLogGroupCard,
    roundMetaHtml,
    loadDayRoundCards,
    mountCollapsibleCard,
    sincronizarEtiquetasNosCards,
    nomeDaTarefaDoCommit,
    tituloDaTarefaDoCommit,
    assignDisplayNamesByDay,
    ensureSessionDetailsLoaded,
    hidratarGroup,
    rebuildGroupFromSaved,
    selectHistoryTaskInPile,
    updateRoundCardCommitByTurnId,
    carregarPorSubir,
    atualizarMarcasDosCards,
    registrarSincronizacaoDoEnvio,
    registrarRestauroDaTarefa,
    enviadaParaOServidor,
    turnosComCommit,
    talvezLembrarDeGuardar,
    reagruparPilhaDoDia
};
