import { state } from './state.js';
import { nomeDe } from './familia_ficheiro.js';
import { ordenarPorChaves, tornarAbasArrastaveis } from './arrastar_abas.js';

const PAGINA_INICIAL = 'https://www.google.com/';
const MAX_FECHADAS = 8;
const LARGURA_DO_MENU = 250;
const ALTURA_DO_MENU = 130;
const SVG_PINO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/></svg>';

let aoTrocarDeAba = null;
let abaDoMenu = null;
let gravacaoAgendada = null;

export function definirAoTrocarDeAba(fn) {
    aoTrocarDeAba = fn;
}

export function abaAtiva() {
    return state.previewAbas.find((aba) => aba.id === state.previewAbaAtiva) || null;
}

export function enderecoDaAbaAtiva() {
    const aba = abaAtiva();
    return aba ? aba.alvo : '';
}

function abasFixadas() {
    return state.previewAbas.filter((aba) => aba.fixada);
}

function ordenarAbas() {
    state.previewAbas.sort((a, b) => (b.fixada ? 1 : 0) - (a.fixada ? 1 : 0));
}

function gravarFixadas() {
    const lista = abasFixadas().map((aba) => ({ tipo: aba.tipo, alvo: aba.alvo }));
    fetch('/api/settings/parcial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preview: { abas_fixadas: lista } })
    }).catch(() => {});
}

function agendarGravacao() {
    if (gravacaoAgendada) clearTimeout(gravacaoAgendada);
    gravacaoAgendada = setTimeout(() => {
        gravacaoAgendada = null;
        gravarFixadas();
    }, 400);
}

function guardarFechada(aba) {
    state.previewAbasFechadas.push({ tipo: aba.tipo, alvo: aba.alvo, fixada: !!aba.fixada });
    if (state.previewAbasFechadas.length > MAX_FECHADAS) state.previewAbasFechadas.shift();
}

export async function restaurarAbasFixadas() {
    let lista = [];
    try {
        const resposta = await fetch('/api/settings');
        const dados = await resposta.json();
        lista = (((dados || {}).preview || {}).abas_fixadas) || [];
    } catch (erro) {
        return [];
    }
    const criadas = [];
    for (const item of lista) {
        if (!item || !item.alvo) continue;
        const existente = state.previewAbas.find((aba) => aba.tipo === item.tipo && mesmaAbaDe(aba, item.alvo));
        if (existente) continue;
        criadas.push(criar(item.tipo === 'web' ? 'web' : 'ficheiro', item.alvo, true));
    }
    if (criadas.length) pintar();
    return criadas;
}

function mesmaChave(a, b) {
    const limpar = (valor) => String(valor || '').replace(/\//g, '\\').toLowerCase();
    return limpar(a) === limpar(b);
}

function mesmoEnderecoWeb(a, b) {
    try {
        const x = new URL(a);
        const y = new URL(b);
        const semBarra = (caminho) => caminho.replace(/\/+$/, '');
        return x.origin === y.origin && semBarra(x.pathname) === semBarra(y.pathname);
    } catch (erro) {
        return mesmaChave(a, b);
    }
}

function mesmaAbaDe(aba, alvo) {
    return aba.tipo === 'web' ? mesmoEnderecoWeb(aba.alvo, alvo) : mesmaChave(aba.alvo, alvo);
}

function nomeDaAbaWeb(url) {
    try {
        const alvo = new URL(url);
        if (alvo.protocol === 'file:') {
            const partes = decodeURIComponent(alvo.pathname).split('/').filter(Boolean);
            return partes.pop() || url;
        }
        return (alvo.host || url).replace(/^www\./, '');
    } catch (erro) {
        return url;
    }
}

function criar(tipo, alvo, fixada) {
    const aba = {
        id: 'paba-' + (++state.previewAbaSeq),
        tipo,
        alvo,
        fixada: !!fixada,
        nome: tipo === 'web' ? nomeDaAbaWeb(alvo) : (nomeDe(alvo) || 'Ficheiro')
    };
    state.previewAbas.push(aba);
    ordenarAbas();
    return aba;
}

function pintarEndereco() {
    if (!state.previewAddress) return;
    if (document.activeElement === state.previewAddress) return;
    state.previewAddress.value = enderecoDaAbaAtiva();
}

function montarBotao(aba) {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'preview-tab';
    botao.dataset.aba = aba.id;
    botao.setAttribute('role', 'tab');
    const nome = document.createElement('span');
    nome.className = 'preview-tab-nome';
    nome.textContent = aba.nome;
    const fechar = document.createElement('span');
    fechar.className = 'preview-tab-x';
    fechar.textContent = '×';
    fechar.title = 'Fechar';
    const pino = document.createElement('span');
    pino.className = 'preview-tab-pino';
    pino.innerHTML = SVG_PINO;
    botao.append(pino, nome, fechar);
    botao.addEventListener('click', (evento) => {
        if (evento.target === fechar) {
            fecharAba(aba.id);
            return;
        }
        ativar(aba.id);
    });
    botao.addEventListener('contextmenu', (evento) => {
        evento.preventDefault();
        abrirMenuDaAba(aba, evento.clientX, evento.clientY);
    });
    return botao;
}

function botaoDaAba(id) {
    return Array.from(state.previewTabs.children)
        .find((elemento) => elemento.dataset && elemento.dataset.aba === id) || null;
}

function pintar() {
    if (!state.previewTabs) return;
    for (const botao of Array.from(state.previewTabs.querySelectorAll('.preview-tab'))) {
        if (!state.previewAbas.some((aba) => aba.id === botao.dataset.aba)) botao.remove();
    }
    for (const aba of state.previewAbas) {
        let botao = botaoDaAba(aba.id);
        if (!botao) botao = montarBotao(aba);
        botao.classList.toggle('preview-tab-ativa', aba.id === state.previewAbaAtiva);
        botao.classList.toggle('preview-tab-fixada', !!aba.fixada);
        botao.title = aba.alvo;
        const nome = botao.querySelector('.preview-tab-nome');
        if (nome.textContent !== aba.nome) nome.textContent = aba.nome;
        state.previewTabs.appendChild(botao);
    }
    pintarEndereco();
}

function focar(id, avisar) {
    const aba = state.previewAbas.find((a) => a.id === id);
    if (!aba) return null;
    const mudou = state.previewAbaAtiva !== id;
    state.previewAbaAtiva = id;
    pintar();
    if (mudou && avisar && aoTrocarDeAba) aoTrocarDeAba(aba);
    return aba;
}

function ativar(id) {
    return focar(id, true);
}

export function ativarAlvoJaCarregado(alvo, tipo) {
    const texto = String(alvo || '').trim();
    if (!texto) return null;
    const existente = state.previewAbas.find((aba) => aba.tipo === tipo && mesmaAbaDe(aba, texto));
    const aba = existente || criar(tipo, texto);
    aba.alvo = texto;
    aba.nome = tipo === 'web' ? nomeDaAbaWeb(texto) : (nomeDe(texto) || aba.nome);
    if (existente && aba.fixada) agendarGravacao();
    return focar(aba.id, false);
}

function reordenar(ordem) {
    ordenarPorChaves(state.previewAbas, ordem, (aba) => aba.id);
    ordenarAbas();
    pintar();
}

export function abrirAbaDeFicheiro(caminho) {
    const alvo = String(caminho || '').trim();
    if (!alvo) return null;
    const existente = state.previewAbas.find((aba) => aba.tipo === 'ficheiro' && mesmaChave(aba.alvo, alvo));
    if (existente) {
        existente.alvo = alvo;
        existente.nome = nomeDe(alvo) || existente.nome;
        return ativar(existente.id);
    }
    return ativar(criar('ficheiro', alvo).id);
}

export function abrirAbaWeb(url, mesmaAba) {
    const alvo = String(url || '').trim();
    if (!alvo) return null;
    const ativa = abaAtiva();
    if (ativa && (mesmaAba || ativa.tipo === 'web')) {
        ativa.tipo = 'web';
        ativa.alvo = alvo;
        ativa.nome = nomeDaAbaWeb(alvo);
        if (ativa.fixada) agendarGravacao();
        pintar();
        if (aoTrocarDeAba) aoTrocarDeAba(ativa);
        return ativa;
    }
    return ativar(criar('web', alvo).id);
}

export function novaAba() {
    return ativar(criar('web', PAGINA_INICIAL).id);
}

export function fecharAba(id) {
    const indice = state.previewAbas.findIndex((aba) => aba.id === id);
    if (indice === -1) return;
    const eraAtiva = state.previewAbaAtiva === id;
    const fora = state.previewAbas[indice];
    state.previewAbas.splice(indice, 1);
    guardarFechada(fora);
    if (fora.fixada) gravarFixadas();
    if (eraAtiva) {
        const vizinha = state.previewAbas[indice - 1] || state.previewAbas[0] || null;
        state.previewAbaAtiva = vizinha ? vizinha.id : null;
    }
    pintar();
    if (aoTrocarDeAba) aoTrocarDeAba(abaAtiva());
}

function abrirMenuDaAba(aba, x, y) {
    if (!state.previewTabMenu) return;
    abaDoMenu = aba;
    if (state.previewCtxReabrir) state.previewCtxReabrir.disabled = !state.previewAbasFechadas.length;
    if (state.previewCtxFixarRotulo) {
        state.previewCtxFixarRotulo.textContent = aba.fixada ? 'Desafixar a aba' : 'Fixar a aba';
    }
    state.previewTabMenu.style.left = Math.max(8, Math.min(x, window.innerWidth - LARGURA_DO_MENU)) + 'px';
    state.previewTabMenu.style.top = Math.max(8, Math.min(y, window.innerHeight - ALTURA_DO_MENU)) + 'px';
    state.previewTabMenu.classList.add('menu-open');
}

function fecharMenuDaAba() {
    if (state.previewTabMenu) state.previewTabMenu.classList.remove('menu-open');
    abaDoMenu = null;
}

function reabrirFechada() {
    const guardada = state.previewAbasFechadas.pop();
    if (!guardada) return null;
    const existente = state.previewAbas.find((aba) => aba.tipo === guardada.tipo && mesmaAbaDe(aba, guardada.alvo));
    const aba = existente || criar(guardada.tipo, guardada.alvo, guardada.fixada);
    if (guardada.fixada && !aba.fixada) {
        aba.fixada = true;
        ordenarAbas();
    }
    gravarFixadas();
    return ativar(aba.id);
}

function alternarFixada(aba) {
    aba.fixada = !aba.fixada;
    ordenarAbas();
    gravarFixadas();
    pintar();
}

export function sincronizarEndereco(url) {
    const aba = abaAtiva();
    if (!aba || aba.tipo !== 'web') return;
    const alvo = String(url || '');
    if (!alvo || alvo === aba.alvo) return;
    aba.alvo = alvo;
    aba.nome = nomeDaAbaWeb(alvo);
    if (aba.fixada) agendarGravacao();
    pintar();
}

if (state.previewNova) {
    state.previewNova.addEventListener('click', () => novaAba());
}

if (state.previewTabs) {
    tornarAbasArrastaveis(state.previewTabs, reordenar, {
        seletor: '.preview-tab',
        excluir: '.preview-tab-x, input'
    });
}

if (state.previewCtxReabrir) {
    state.previewCtxReabrir.addEventListener('click', () => {
        fecharMenuDaAba();
        reabrirFechada();
    });
}

if (state.previewCtxFixar) {
    state.previewCtxFixar.addEventListener('click', () => {
        const aba = abaDoMenu;
        fecharMenuDaAba();
        if (aba) alternarFixada(aba);
    });
}

if (state.previewCtxFechar) {
    state.previewCtxFechar.addEventListener('click', () => {
        const aba = abaDoMenu;
        fecharMenuDaAba();
        if (aba) fecharAba(aba.id);
    });
}

document.addEventListener('click', (evento) => {
    if (state.previewTabMenu && state.previewTabMenu.contains(evento.target)) return;
    fecharMenuDaAba();
});

document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape') fecharMenuDaAba();
});

restaurarAbasFixadas();
