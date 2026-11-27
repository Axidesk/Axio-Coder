import { state } from './state.js';

const CABECALHO = 'X-Axio-Workspace';
const CHAVE_GUARDADA = 'axio-workspaces';
const PRINCIPAL = 'principal';
const NOME_DE_PARTIDA = 'Novo projeto';

let areas = [];
let ativa = PRINCIPAL;
const cenas = {};
const pendentes = {};
let fetchOriginal = null;

function basename(caminho) {
    const partes = String(caminho || '').replace(/\\/g, '/').split('/').filter(Boolean);
    return partes.length ? partes[partes.length - 1] : '';
}

function lerGuardado() {
    try {
        const bruto = JSON.parse(localStorage.getItem(CHAVE_GUARDADA) || 'null');
        if (bruto && Array.isArray(bruto.areas) && bruto.areas.length) {
            areas = bruto.areas
                .filter(a => a && a.chave)
                .map(a => ({ chave: a.chave, nome: a.nome || '', pasta: a.pasta || '' }));
            ativa = bruto.ativa && areas.some(a => a.chave === bruto.ativa) ? bruto.ativa : areas[0].chave;
        }
    } catch (e) {
        areas = [];
    }
    if (!areas.some(a => a.chave === PRINCIPAL)) {
        areas.unshift({ chave: PRINCIPAL, nome: '', pasta: '' });
    }
    if (!areas.some(a => a.chave === ativa)) ativa = areas[0].chave;
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

function instalarFetch() {
    if (fetchOriginal) return;
    fetchOriginal = window.fetch.bind(window);
    window.fetch = (entrada, opcoes) => {
        if (ativa && ativa !== PRINCIPAL && typeof entrada === 'string') {
            const copia = Object.assign({}, opcoes || {});
            const cabecalhos = new Headers(copia.headers || {});
            cabecalhos.set(CABECALHO, ativa);
            copia.headers = cabecalhos;
            return fetchOriginal(entrada, copia);
        }
        return fetchOriginal(entrada, opcoes);
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
        aba.title = area.pasta || area.nome || NOME_DE_PARTIDA;
        const nome = document.createElement('span');
        nome.className = 'ws-aba-nome';
        nome.textContent = area.nome || NOME_DE_PARTIDA;
        aba.appendChild(nome);
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

function guardarCena(chave) {
    const inner = document.getElementById('chat-inner-right');
    cenas[chave] = {
        nos: inner ? Array.from(inner.children) : [],
        abas: Array.isArray(state.openTabs) ? [...state.openTabs] : [],
        abaAtiva: state.abaAtiva || '',
        atual: state.currentFile || '',
        turnId: state.turnId,
    };
    if (inner) inner.replaceChildren();
}

function restaurarCena(chave) {
    const cena = cenas[chave];
    const inner = document.getElementById('chat-inner-right');
    if (inner) inner.replaceChildren(...(cena ? cena.nos : []));
    state.openTabs = cena ? [...cena.abas] : [];
    state.abaAtiva = '';
    state.currentFile = '';
    if (cena && 'turnId' in state) state.turnId = cena.turnId;
    const wv = window.WorkspaceView;
    if (wv && typeof wv.renderTabs === 'function') wv.renderTabs();
    setTimeout(atualizarSetasDasAbas, 30);
}

function atualizarRodape() {
    const area = areaDe(ativa);
    const pasta = area ? area.pasta : '';
    const rotulo = document.getElementById('lbl-folder');
    if (rotulo) rotulo.textContent = pasta;
    const botao = document.getElementById('btn-select-folder');
    if (botao) {
        botao.classList.toggle('folder-selected', !!pasta);
        botao.classList.toggle('text-[var(--oliva)]', !!pasta);
        botao.classList.toggle('text-[var(--text-branco)]', false);
        botao.title = pasta || 'Selecionar Pasta';
    }
}

function recarregarVista() {
    const wv = window.WorkspaceView;
    if (wv && typeof wv.reloadExplorer === 'function') wv.reloadExplorer();
    if (wv && typeof wv.loadVenvName === 'function') wv.loadVenvName();
}

async function trocarPara(chave) {
    if (!chave || chave === ativa) return;
    guardarCena(ativa);
    ativa = chave;
    guardar();
    desenhar();
    restaurarCena(chave);
    atualizarRodape();
    recarregarVista();
    document.dispatchEvent(new CustomEvent('workspace:mudou', { detail: { chave } }));
    despacharPendentes(chave);
}

async function definirPasta(chave, pasta) {
    const area = areaDe(chave);
    if (!area || !pasta) return false;
    const anterior = ativa;
    ativa = chave;
    let ok = false;
    try {
        const resposta = await fetch('/api/set_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder: pasta }),
        });
        ok = resposta.ok;
    } catch (e) {
        ok = false;
    }
    ativa = anterior;
    if (!ok) {
        desenhar();
        return false;
    }
    area.pasta = pasta;
    area.nome = basename(pasta);
    guardar();
    desenhar();
    if (chave === ativa) {
        atualizarRodape();
        recarregarVista();
    }
    return true;
}

async function escolherPastaDaArea() {
    const ponte = window.ipcRenderer || (typeof ipcRenderer !== 'undefined' ? ipcRenderer : null);
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
    const chave = 'ws' + Date.now().toString(36);
    areas.push({ chave, nome: NOME_DE_PARTIDA, pasta: '' });
    guardarCena(ativa);
    ativa = chave;
    guardar();
    desenhar();
    restaurarCena(chave);
    atualizarRodape();
    recarregarVista();
    await escolherPastaDaArea();
}

async function fecharArea(chave) {
    const indice = areas.findIndex(a => a.chave === chave);
    if (indice < 0 || areas.length <= 1) return;
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
    if (eraAtiva) {
        ativa = areas[Math.min(indice, areas.length - 1)].chave;
        guardar();
        desenhar();
        restaurarCena(ativa);
        atualizarRodape();
        recarregarVista();
    } else {
        guardar();
        desenhar();
    }
}

function envolverEventos() {
    const fonte = state.eventSource;
    if (!fonte || fonte.__axioWorkspaces) return Boolean(fonte);
    const original = fonte.onmessage;
    if (typeof original !== 'function') return false;
    fonte.__axioWorkspaces = true;
    fonte.__axioOriginal = original;
    fonte.onmessage = (evento) => {
        let dados = null;
        try {
            dados = JSON.parse(evento.data);
        } catch (e) {
            dados = null;
        }
        const dono = (dados && dados.workspace) || PRINCIPAL;
        if (dono === ativa) return original.call(fonte, evento);
        if (!pendentes[dono]) pendentes[dono] = [];
        pendentes[dono].push(evento.data);
        return undefined;
    };
    return true;
}

function despacharPendentes(chave) {
    const fila = pendentes[chave];
    if (!fila || !fila.length) return;
    delete pendentes[chave];
    const fonte = state.eventSource;
    const original = fonte && fonte.__axioOriginal;
    if (!original) return;
    fila.forEach(texto => original.call(fonte, { data: texto }));
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

async function reidratarPastaDaAreaAtiva() {
    if (ativa === PRINCIPAL) return;
    const area = areaDe(ativa);
    if (!area || !area.pasta) return;
    try {
        await fetch('/api/set_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder: area.pasta }),
        });
    } catch (e) {
        return;
    }
    recarregarVista();
}

function iniciar() {
    lerGuardado();
    instalarFetch();
    desenhar();
    atualizarRodape();
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
    let tentativas = 0;
    const relogio = setInterval(() => {
        tentativas += 1;
        if (envolverEventos() || tentativas > 40) clearInterval(relogio);
    }, 250);
    reidratarPastaDaAreaAtiva();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
} else {
    iniciar();
}
