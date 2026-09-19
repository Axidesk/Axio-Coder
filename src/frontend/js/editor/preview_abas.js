import { state } from './state.js';
import { nomeDe } from './familia_ficheiro.js';
import { ordenarPorChaves, tornarAbasArrastaveis } from './arrastar_abas.js';

const PAGINA_INICIAL = 'https://www.google.com/';

let aoTrocarDeAba = null;

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

function criar(tipo, alvo) {
    const aba = {
        id: 'paba-' + (++state.previewAbaSeq),
        tipo,
        alvo,
        nome: tipo === 'web' ? nomeDaAbaWeb(alvo) : (nomeDe(alvo) || 'Ficheiro')
    };
    state.previewAbas.push(aba);
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
    botao.append(nome, fechar);
    botao.addEventListener('click', (evento) => {
        if (evento.target === fechar) {
            fecharAba(aba.id);
            return;
        }
        ativar(aba.id);
    });
    return botao;
}

function pintar() {
    if (!state.previewTabs) return;
    for (const botao of Array.from(state.previewTabs.querySelectorAll('.preview-tab'))) {
        if (!state.previewAbas.some((aba) => aba.id === botao.dataset.aba)) botao.remove();
    }
    for (const aba of state.previewAbas) {
        let botao = state.previewTabs.querySelector('.preview-tab[data-aba="' + aba.id + '"]');
        if (!botao) {
            botao = montarBotao(aba);
            state.previewTabs.appendChild(botao);
        }
        botao.classList.toggle('preview-tab-ativa', aba.id === state.previewAbaAtiva);
        botao.title = aba.alvo;
        const nome = botao.querySelector('.preview-tab-nome');
        if (nome.textContent !== aba.nome) nome.textContent = aba.nome;
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
    return focar(aba.id, false);
}

function reordenar(ordem) {
    ordenarPorChaves(state.previewAbas, ordem, (aba) => aba.id);
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
    state.previewAbas.splice(indice, 1);
    if (eraAtiva) {
        const vizinha = state.previewAbas[indice - 1] || state.previewAbas[0] || null;
        state.previewAbaAtiva = vizinha ? vizinha.id : null;
    }
    pintar();
    if (aoTrocarDeAba) aoTrocarDeAba(abaAtiva());
}

export function sincronizarEndereco(url) {
    const aba = abaAtiva();
    if (!aba || aba.tipo !== 'web') return;
    const alvo = String(url || '');
    if (!alvo || alvo === aba.alvo) return;
    aba.alvo = alvo;
    aba.nome = nomeDaAbaWeb(alvo);
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
