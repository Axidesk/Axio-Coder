import { state } from './state.js';
import { state as chatState } from '../chat/state.js';
import { definirPastaDaArea } from '../chat/files.js';

const CABECALHO = 'X-Axio-Workspace';
const ELEMENTOS_DA_CENA = ['chat-inner-left', 'chat-inner-right', 'current-logs-wrapper', 'history-logs-wrapper'];
const ELEMENTOS_DE_ESTADO = ['lbl-status', 'lbl-executing', 'lbl-metrics', 'btn-send'];
const TIPOS_GLOBAIS = new Set([
    'files_changed', 'process_started', 'process_output', 'process_finished',
    'debug_stop', 'debug_estado', 'debug_fim', 'despertar', 'envio',
]);
const CHAVE_GUARDADA = 'axio-workspaces';
const PRINCIPAL = 'principal';
const NOME_DE_PARTIDA = 'Novo projeto';
const BASE = {
    isGenerating: false, currentTurnId: null, currentTurnLogs: [], currentTurnSummary: '',
    isShowingSessionHistory: false, sessionHistoryList: [], sessionHistoryLoaded: false,
    sessionDetailCache: {}, sessionLogArquivo: '', sessionIndiceEmCurso: null,
    commitsDosTurnos: {}, commitsPorSubir: [], porSubirTruncado: false, porSubirLido: false,
    porSubirEmCurso: null, temRemotoGit: false, gitRemoto: '', versoesGit: null, versoesEmCurso: null,
    currentCheckpointId: null, checkpointRestoredAt: 0, restoreEvents: [],
    currentViewingTools: [], currentViewingThoughts: [], currentViewingQuestions: [],
    isShowingTools: false, isShowingGit: false, isShowingThoughts: false, isShowingQuestions: false,
    thoughtsExpanded: false, currentActiveFileBalloonHtml: '', undoRedoFiles: [], currentUndoFile: null,
    currentFileDataRef: null, isEyeMode: false, currentOpenedDiff: null,
    codigoDoHistoricoNoEditor: false, vistaDocAtual: 'chat', currentViewingAiResponse: '',
    areaDoTurnoDoEstado: '',
    attachedImages: [], imageCounter: 1, currentSelectedHistoryGroup: null,
    currentSelectedHistoryEl: null,
};
const CHAVES_DO_ESTADO = Object.keys(BASE);

let areas = [];
let ativa = PRINCIPAL;
const cenas = {};
const pendentes = {};
let fetchOriginal = null;
let emTroca = false;
const areasGerando = new Set();

function basename(caminho) {
    const partes = String(caminho || '').replace(/\\/g, '/').split('/').filter(Boolean);
    return partes.length ? partes[partes.length - 1] : '';
}

function normalizar(caminho) {
    return String(caminho || '').replace(/\//g, '\\').replace(/\\+$/, '').toLowerCase();
}

function copiarValor(valor) {
    if (Array.isArray(valor)) return valor.slice();
    if (valor instanceof Set) return new Set(valor);
    if (valor instanceof Map) return new Map(valor);
    if (valor && typeof valor === 'object' && Object.getPrototypeOf(valor) === Object.prototype) {
        return Object.assign({}, valor);
    }
    return valor;
}

function fotoDoEstado() {
    const foto = {};
    CHAVES_DO_ESTADO.forEach(k => { foto[k] = copiarValor(chatState[k]); });
    return foto;
}

function aplicarEstado(foto) {
    const origem = foto || BASE;
    CHAVES_DO_ESTADO.forEach(k => { chatState[k] = copiarValor(origem[k]); });
}

function fotoDosElementos() {
    const foto = {};
    ELEMENTOS_DE_ESTADO.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        foto[id] = { html: el.innerHTML, titulo: el.title || '', desativado: !!el.disabled };
    });
    return foto;
}

function aplicarElementos(foto) {
    ELEMENTOS_DE_ESTADO.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const guardado = (foto && foto[id]) || null;
        el.innerHTML = guardado ? guardado.html : '';
        el.title = guardado ? guardado.titulo : '';
        if ('disabled' in el) el.disabled = guardado ? guardado.desativado : false;
    });
}

function lerEstadoDoTurno() {
    const gancho = window.__axioEstadoDoTurno;
    return gancho && typeof gancho.ler === 'function' ? gancho.ler() : null;
}

function aplicarEstadoDoTurno(foto) {
    const gancho = window.__axioEstadoDoTurno;
    if (gancho && typeof gancho.por === 'function') gancho.por(foto || {});
}

function pastaViva() {
    const rotulo = document.getElementById('lbl-folder');
    return rotulo ? (rotulo.textContent || '').trim() : '';
}

function ponteElectron() {
    try {
        const { ipcRenderer } = window.require('electron');
        return ipcRenderer || null;
    } catch (e) {
        return null;
    }
}

function pastaNoTemporario(pasta) {
    const alvo = normalizar(pasta);
    if (!alvo) return false;
    let raiz = '';
    try {
        raiz = normalizar(require('os').tmpdir());
    } catch (e) {
        return false;
    }
    return !!raiz && (alvo === raiz || alvo.startsWith(raiz + '\\'));
}

function nomeDaArea(area) {
    if (!area) return NOME_DE_PARTIDA;
    if (area.pasta) return basename(area.pasta);
    return area.nome || NOME_DE_PARTIDA;
}

function desembrulharGuardado(bruto) {
    let dados = bruto;
    for (let i = 0; i < 3 && dados && !Array.isArray(dados.areas) && dados.areas && typeof dados.areas === 'object'; i++) {
        dados = dados.areas;
    }
    return dados;
}

function lerGuardado() {
    try {
        const bruto = desembrulharGuardado(JSON.parse(localStorage.getItem(CHAVE_GUARDADA) || 'null'));
        if (bruto && Array.isArray(bruto.areas) && bruto.areas.length) {
            areas = bruto.areas
                .filter(a => a && a.chave)
                .map(a => ({ chave: a.chave, nome: a.nome || '', pasta: a.pasta || '', rascunho: a.rascunho || '' }));
            ativa = bruto.ativa && areas.some(a => a.chave === bruto.ativa) ? bruto.ativa : areas[0].chave;
        }
    } catch (e) {
        areas = [];
    }
    if (!areas.some(a => a.chave === PRINCIPAL)) {
        areas.unshift({ chave: PRINCIPAL, nome: '', pasta: '' });
    }
    ativa = PRINCIPAL;
}

function guardar() {
    try {
        localStorage.setItem(CHAVE_GUARDADA, JSON.stringify({ areas, ativa }));
    } catch (e) {
        return;
    }
}

function areaDe(chave) {
    return areas.find(a => a.chave === chave) || null;
}

function donoDoPedido() {
    if (!areasGerando.size) return ativa;
    if (areasGerando.has(ativa)) return ativa;
    return areasGerando.values().next().value;
}

function instalarFetch() {
    if (fetchOriginal) return;
    fetchOriginal = window.fetch.bind(window);
    window.fetch = (entrada, opcoes) => {
        const copia = Object.assign({}, opcoes || {});
        const dono = copia.__area || donoDoPedido();
        delete copia.__area;
        if (dono && dono !== PRINCIPAL && typeof entrada === 'string') {
            const cabecalhos = new Headers(copia.headers || {});
            cabecalhos.set(CABECALHO, dono);
            copia.headers = cabecalhos;
        }
        return fetchOriginal(entrada, copia);
    };
}

function desenhar() {
    const barra = document.getElementById('ws-barra');
    const lista = document.getElementById('ws-abas');
    if (!barra || !lista) return;
    lista.innerHTML = '';
    barra.classList.toggle('hidden', areas.length < 2);
    areas.forEach(area => {
        const aba = document.createElement('div');
        aba.className = 'ws-aba' + (area.chave === ativa ? ' ativa' : '');
        const rotulo = nomeDaArea(area);
        aba.title = area.pasta || rotulo;
        const nome = document.createElement('span');
        nome.className = 'ws-aba-nome';
        nome.textContent = rotulo;
        if (areas.length > 1) {
            const fechar = document.createElement('button');
            fechar.type = 'button';
            fechar.className = 'ws-aba-fechar';
            fechar.title = 'Fechar área de trabalho';
            fechar.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
            fechar.addEventListener('click', (e) => {
                e.stopPropagation();
                fecharArea(area.chave);
            });
            aba.appendChild(fechar);
        }
        aba.appendChild(nome);
        aba.addEventListener('click', () => trocarPara(area.chave));
        lista.appendChild(aba);
    });
    atualizarSetasDosWorkspaces();
}

function atualizarSetasDosWorkspaces() {
    const lista = document.getElementById('ws-abas');
    const antes = document.getElementById('btn-ws-anterior');
    const depois = document.getElementById('btn-ws-seguinte');
    if (!lista) return;
    const transborda = lista.scrollWidth > lista.clientWidth + 1;
    if (antes) antes.classList.toggle('hidden', !transborda || lista.scrollLeft <= 1);
    if (depois) depois.classList.toggle('hidden', !transborda || lista.scrollLeft + lista.clientWidth >= lista.scrollWidth - 1);
}

function atualizarSetasDasAbas() {
    const lista = document.getElementById('editor-tabs');
    const antes = document.getElementById('btn-tabs-anterior');
    const depois = document.getElementById('btn-tabs-seguinte');
    if (!lista) return;
    const transborda = lista.scrollWidth > lista.clientWidth + 1;
    if (antes) antes.classList.toggle('hidden', !transborda || lista.scrollLeft <= 1);
    if (depois) depois.classList.toggle('hidden', !transborda || lista.scrollLeft + lista.clientWidth >= lista.scrollWidth - 1);
}

function rolarLista(lista, sentido) {
    if (!lista) return;
    lista.scrollBy({ left: sentido * Math.max(120, lista.clientWidth * 0.7), behavior: 'smooth' });
    setTimeout(() => {
        atualizarSetasDosWorkspaces();
        atualizarSetasDasAbas();
    }, 260);
}

function campoDeEntrada() {
    return document.getElementById('input-text');
}

function guardarCena(chave) {
    const nos = {};
    ELEMENTOS_DA_CENA.forEach(id => {
        const el = document.getElementById(id);
        nos[id] = el ? Array.from(el.children) : [];
        if (el) el.replaceChildren();
    });
    const entrada = campoDeEntrada();
    const status = document.getElementById('lbl-status');
    cenas[chave] = {
        nos,
        texto: entrada ? entrada.value : '',
        status: status ? { html: status.innerHTML, bloqueio: status.dataset.antesBloqueio } : null,
        elementos: fotoDosElementos(),
        estado: fotoDoEstado(),
        turno: lerEstadoDoTurno(),
        abas: Array.isArray(state.openTabs) ? [...state.openTabs] : [],
        abaAtiva: state.abaAtiva || '',
        atual: state.currentFile || '',
        logs: Array.isArray(window.sessionLogsData) ? [...window.sessionLogsData] : [],
    };
}

function restaurarCena(chave) {
    const cena = cenas[chave];
    ELEMENTOS_DA_CENA.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.replaceChildren(...((cena && cena.nos && cena.nos[id]) || []));
    });
    aplicarEstado(cena ? cena.estado : null);
    aplicarEstadoDoTurno(cena ? cena.turno : null);
    aplicarElementos(cena ? cena.elementos : null);
    const statusEl = document.getElementById('lbl-status');
    const statusGuardado = cena && cena.status;
    if (statusEl && statusGuardado) {
        statusEl.innerHTML = statusGuardado.html || '';
        if (statusGuardado.bloqueio !== undefined) statusEl.dataset.antesBloqueio = statusGuardado.bloqueio;
        else delete statusEl.dataset.antesBloqueio;
    }
    window.sessionLogsData = cena && cena.logs ? [...cena.logs] : [];
    const entrada = campoDeEntrada();
    const area = areaDe(chave);
    const rascunho = cena ? (cena.texto || '') : (area ? (area.rascunho || '') : '');
    if (entrada) {
        entrada.value = rascunho;
        entrada.dispatchEvent(new Event('input', { bubbles: true }));
    }
    state.openTabs = cena ? [...cena.abas] : [];
    state.abaAtiva = cena ? cena.abaAtiva : '';
    state.currentFile = cena ? cena.atual : '';
    const wv = window.WorkspaceView;
    if (wv && typeof wv.renderTabs === 'function') wv.renderTabs();
    setTimeout(atualizarSetasDasAbas, 30);
}

function aplicarPastaDaArea(chave) {
    const area = areaDe(chave);
    definirPastaDaArea(area ? area.pasta : '');
}

function pastaDoBackend(area) {
    return fetch('/api/env_info', { __area: area })
        .then(r => (r.ok ? r.json() : null))
        .then(d => (d && d.folder) || '')
        .catch(() => '');
}

async function garantirPastaNoBackend(chave) {
    const area = areaDe(chave);
    if (!area) return false;
    const querida = area.pasta;
    const atual = await pastaDoBackend(chave);
    if (normalizar(querida) === normalizar(atual)) return false;
    if (!querida) {
        if (atual && chave === PRINCIPAL) {
            area.pasta = atual;
            area.nome = basename(atual);
            guardar();
        }
        return false;
    }
    try {
        const resposta = await fetch('/api/set_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder: querida }),
            __area: chave,
        });
        return resposta.ok;
    } catch (e) {
        return false;
    }
}

function arvoreNaPasta(chave) {
    const area = areaDe(chave);
    const querida = normalizar(area ? area.pasta : '');
    return !!querida && querida === normalizar(state.rootPath || '');
}

function recarregarVista(semLimparCache) {
    const wv = window.WorkspaceView;
    if (wv && typeof wv.reloadExplorer === 'function') wv.reloadExplorer(!semLimparCache);
    if (wv && typeof wv.loadVenvName === 'function') wv.loadVenvName();
}

function aplicarArea(chave) {
    ativa = chave;
    guardar();
    desenhar();
    restaurarCena(chave);
    filtrarSSE(chatState.eventSource);
    document.dispatchEvent(new CustomEvent('workspace:mudou', { detail: { chave } }));
    despacharPendentes(chave);
    atualizarAreaEmSegundoPlano(chave);
}

async function atualizarAreaEmSegundoPlano(chave) {
    let mudou = false;
    try {
        mudou = await garantirPastaNoBackend(chave);
    } catch (e) {
        mudou = false;
    }
    if (ativa !== chave) return;
    aplicarPastaDaArea(chave);
    if (mudou || !arvoreNaPasta(chave)) recarregarVista(true);
    chatState.sessionHistoryLoaded = false;
    if (chatState.isShowingSessionHistory) {
        import('../chat/historico/painel.js')
            .then(mod => (typeof mod.loadSessionHistoryList === 'function' ? mod.loadSessionHistoryList({ silent: true }) : null))
            .catch(() => {});
    }
}

async function trocarPara(chave) {
    if (!chave || chave === ativa || emTroca) return;
    emTroca = true;
    try {
        guardarCena(ativa);
        await aplicarArea(chave);
    } finally {
        emTroca = false;
    }
}

async function definirPasta(chave, pasta) {
    const area = areaDe(chave);
    if (!area || !pasta) return false;
    if (pastaNoTemporario(pasta)) {
        const aviso = document.getElementById('lbl-status');
        if (aviso) aviso.textContent = 'Essa pasta é temporária do sistema. Escolha a pasta do projeto.';
        return false;
    }
    let ok = false;
    try {
        const resposta = await fetch('/api/set_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder: pasta }),
            __area: chave,
        });
        ok = resposta.ok;
    } catch (e) {
        ok = false;
    }
    if (!ok) {
        desenhar();
        return false;
    }
    area.pasta = pasta;
    area.nome = basename(pasta);
    guardar();
    desenhar();
    if (chave === ativa) {
        aplicarPastaDaArea(chave);
        recarregarVista();
    }
    return true;
}

async function escolherPastaDaArea() {
    const ponte = ponteElectron();
    if (!ponte) return;
    let pasta = '';
    try {
        pasta = await ponte.invoke('select-folder', areaDe(ativa) ? areaDe(ativa).pasta : '');
    } catch (e) {
        return;
    }
    if (pasta) await definirPasta(ativa, pasta);
}

async function novoWorkspace() {
    if (emTroca) return;
    const chave = 'ws' + Date.now().toString(36);
    emTroca = true;
    try {
        guardarCena(ativa);
        areas.push({ chave, nome: '', pasta: '' });
        await aplicarArea(chave);
    } finally {
        emTroca = false;
    }
    await escolherPastaDaArea();
}

async function fecharAreaDeVez(chave, indice) {
    try {
        await fetch('/api/workspaces/fechar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chave }),
        });
    } catch (e) {
        return;
    }
    const eraAtiva = chave === ativa;
    areas.splice(indice, 1);
    delete cenas[chave];
    delete pendentes[chave];
    if (!eraAtiva) {
        guardar();
        desenhar();
        return;
    }
    guardarCena('');
    delete cenas[''];
    const destino = areas[Math.min(indice, areas.length - 1)].chave;
    await aplicarArea(destino);
}

async function fecharArea(chave) {
    const indice = areas.findIndex(a => a.chave === chave);
    if (indice < 0 || areas.length <= 1) return;
    const nome = nomeDaArea(areaDe(chave));
    let perguntar = null;
    try {
        const mod = await import('../chat/ui.js');
        perguntar = mod.showConfirm || null;
    } catch (e) {
        perguntar = null;
    }
    if (typeof perguntar !== 'function') {
        await fecharAreaDeVez(chave, indice);
        return;
    }
    perguntar(`Fechar a área "${nome}"?`, 'Fechar', () => { fecharAreaDeVez(chave, indice); });
}

function filtrarSSE(fonte) {
    if (!fonte || typeof fonte.onmessage !== 'function') return false;
    if (fonte.onmessage.__axioWrapper) return true;
    const base = fonte.onmessage;
    fonte.__axioBase = base;
    const embrulho = (evento) => {
        let dados = null;
        try {
            dados = JSON.parse(evento.data);
        } catch (e) {
            dados = null;
        }
        if (dados && !dados.workspace && TIPOS_GLOBAIS.has(dados.type)) return base.call(fonte, evento);
        const dono = (dados && dados.workspace) || PRINCIPAL;
        if (dono === ativa) return base.call(fonte, evento);
        if (!pendentes[dono]) pendentes[dono] = [];
        pendentes[dono].push(evento.data);
        return undefined;
    };
    embrulho.__axioWrapper = true;
    fonte.onmessage = embrulho;
    return true;
}

function despacharPendentes(chave) {
    const fila = pendentes[chave];
    if (!fila || !fila.length) return;
    delete pendentes[chave];
    const fonte = chatState.eventSource;
    const base = fonte && fonte.__axioBase;
    if (!base) return;
    let i = 0;
    const passo = () => {
        if (ativa !== chave) {
            pendentes[chave] = fila.slice(i).concat(pendentes[chave] || []);
            return;
        }
        const fim = Math.min(i + 60, fila.length);
        for (; i < fim; i++) base.call(fonte, { data: fila[i] });
        if (i < fila.length) requestAnimationFrame(passo);
    };
    passo();
}

function ligarMenuDasAbas() {
    const lista = document.getElementById('editor-tabs');
    const menu = document.getElementById('tabs-context-menu');
    if (!lista || !menu) return;
    lista.addEventListener('contextmenu', (e) => {
        const aba = e.target.closest('.editor-tab');
        if (!aba) return;
        e.preventDefault();
        menu.style.left = Math.min(e.clientX, window.innerWidth - 190) + 'px';
        menu.style.top = Math.min(e.clientY, window.innerHeight - 60) + 'px';
        menu.classList.add('aberto');
    });
    document.addEventListener('click', (e) => {
        if (e.target.closest('#tabs-context-menu')) return;
        menu.classList.remove('aberto');
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') menu.classList.remove('aberto');
    });
    document.addEventListener('scroll', () => menu.classList.remove('aberto'), true);
    menu.querySelector('[data-acao="fechar-todas"]').addEventListener('click', async () => {
        menu.classList.remove('aberto');
        const mod = await import('./editor.js');
        const caminhos = [...(state.openTabs || [])];
        for (const caminho of caminhos) {
            try {
                if (typeof mod.closeTab === 'function') {
                    await mod.closeTab(caminho);
                } else {
                    state.openTabs = [];
                    state.currentFile = '';
                    state.abaAtiva = '';
                    if (typeof mod.renderTabs === 'function') mod.renderTabs();
                    break;
                }
            } catch (e) {
                continue;
            }
        }
        setTimeout(atualizarSetasDasAbas, 30);
    });
}

function ligarObservadorDasAbas() {
    const lista = document.getElementById('editor-tabs');
    if (!lista || typeof MutationObserver !== 'function') return;
    const observador = new MutationObserver(() => atualizarSetasDasAbas());
    observador.observe(lista, { childList: true });
    lista.addEventListener('scroll', atualizarSetasDasAbas, { passive: true });
}

function ligarObservadorDaPasta() {
    const rotulo = document.getElementById('lbl-folder');
    if (!rotulo || typeof MutationObserver !== 'function') return;
    const observador = new MutationObserver(() => {
        const pasta = (rotulo.textContent || '').trim();
        if (pasta === (rotulo.dataset.pastaAplicada || '')) return;
        const area = areaDe(ativa);
        if (!area || pasta === area.pasta) return;
        area.pasta = pasta;
        area.nome = pasta ? basename(pasta) : area.nome;
        guardar();
        desenhar();
    });
    observador.observe(rotulo, { childList: true, characterData: true, subtree: true });
}

function interceptarPastaForaDoPrincipal() {
    document.addEventListener('click', (e) => {
        if (ativa === PRINCIPAL) return;
        if (!e.target.closest('#btn-select-folder')) return;
        e.stopImmediatePropagation();
        e.preventDefault();
        escolherPastaDaArea();
    }, true);
}

function ligarRascunho() {
    const entrada = campoDeEntrada();
    if (!entrada) return;
    entrada.addEventListener('input', () => {
        const area = areaDe(ativa);
        if (!area) return;
        area.rascunho = entrada.value;
    });
}

async function reidratarPastaDaAreaAtiva() {
    const chave = ativa;
    const area = areaDe(chave);
    if (!area || !area.pasta) return;
    await garantirPastaNoBackend(chave);
    if (ativa !== chave) return;
    aplicarPastaDaArea(chave);
    if (!arvoreNaPasta(chave)) recarregarVista(true);
}

function iniciar() {
    lerGuardado();
    instalarFetch();
    const principal = areaDe(PRINCIPAL);
    if (principal && !principal.pasta) {
        const viva = pastaViva();
        if (viva) {
            principal.pasta = viva;
            principal.nome = basename(viva);
            guardar();
        }
    }
    desenhar();
    aplicarPastaDaArea(ativa);
    const novo = document.getElementById('btn-novo-workspace');
    if (novo) novo.addEventListener('click', novoWorkspace);
    const antes = document.getElementById('btn-ws-anterior');
    const depois = document.getElementById('btn-ws-seguinte');
    const listaAreas = document.getElementById('ws-abas');
    if (antes) antes.addEventListener('click', () => rolarLista(listaAreas, -1));
    if (depois) depois.addEventListener('click', () => rolarLista(listaAreas, 1));
    if (listaAreas) listaAreas.addEventListener('scroll', atualizarSetasDosWorkspaces, { passive: true });
    window.addEventListener('resize', () => {
        atualizarSetasDosWorkspaces();
        atualizarSetasDasAbas();
    });
    const listaAbas = document.getElementById('editor-tabs');
    const tabsAntes = document.getElementById('btn-tabs-anterior');
    const tabsDepois = document.getElementById('btn-tabs-seguinte');
    if (tabsAntes) tabsAntes.addEventListener('click', () => rolarLista(listaAbas, -1));
    if (tabsDepois) tabsDepois.addEventListener('click', () => rolarLista(listaAbas, 1));
    ligarObservadorDasAbas();
    ligarObservadorDaPasta();
    ligarMenuDasAbas();
    interceptarPastaForaDoPrincipal();
    ligarRascunho();
    window.__axioFiltrarSSE = filtrarSSE;
    window.__axioAreaAtiva = () => ativa;
    window.__axioMarcarAreaDoTurno = (chave) => { if (chave) areasGerando.add(chave); };
    window.__axioSoltarAreaDoTurno = (chave) => { if (chave) areasGerando.delete(chave); };
    let tentativas = 0;
    const relogio = setInterval(() => {
        tentativas += 1;
        if (filtrarSSE(chatState.eventSource) || tentativas > 40) clearInterval(relogio);
    }, 250);
    reidratarPastaDaAreaAtiva();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
} else {
    iniciar();
}
