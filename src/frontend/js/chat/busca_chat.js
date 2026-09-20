import * as dom from './dom.js';
import { limparMarcas, marcarTermo } from './marcar_termo.js';

const CLASSE_FORA = 'conversa-busca-fora';
const CLASSE_CASA = 'conversa-busca-casa';
const ESPERA_MS = 180;

let aberta = false;
let termo = '';
const marcadas = new Set();

function _mensagens() {
    return [dom.chatInnerLeft, dom.chatInnerRight]
        .filter(Boolean)
        .flatMap(painel => Array.from(painel.children));
}

function _contagem(achadas, total) {
    const alvo = dom.chatSearchCount;
    if (!alvo) return;
    if (!termo.trim()) {
        alvo.textContent = '';
        return;
    }
    if (!total) {
        alvo.textContent = 'sem mensagens';
        return;
    }
    alvo.textContent = achadas ? `${achadas} de ${total}` : 'nenhuma';
}

function _limparMarcas() {
    marcadas.forEach(no => limparMarcas(no));
    marcadas.clear();
}

function aplicarFiltro(novoTermo) {
    termo = novoTermo || '';
    const alvo = termo.trim().toLowerCase();
    const mensagens = _mensagens();
    _limparMarcas();
    if (!alvo) {
        mensagens.forEach(no => no.classList.remove(CLASSE_FORA, CLASSE_CASA));
        _contagem(0, mensagens.length);
        return;
    }
    let achadas = 0;
    mensagens.forEach(no => {
        const casa = (no.textContent || '').toLowerCase().includes(alvo);
        no.classList.toggle(CLASSE_FORA, !casa);
        no.classList.toggle(CLASSE_CASA, casa);
        if (!casa) return;
        achadas += 1;
        marcarTermo(no, alvo);
        marcadas.add(no);
    });
    _contagem(achadas, mensagens.length);
}

function reavaliarBuscaChat() {
    if (!termo.trim()) return;
    aplicarFiltro(termo);
}

function abrirBuscaChat() {
    aberta = true;
    if (dom.chatSearchBox) dom.chatSearchBox.classList.add('aberta');
    if (dom.btnChatSearch) dom.btnChatSearch.classList.add('hide');
    if (dom.chatSearchInput) {
        dom.chatSearchInput.focus();
        dom.chatSearchInput.select();
    }
}

function fecharBuscaChat() {
    aberta = false;
    if (dom.chatSearchInput) dom.chatSearchInput.value = '';
    if (dom.chatSearchBox) dom.chatSearchBox.classList.remove('aberta');
    if (dom.btnChatSearch) dom.btnChatSearch.classList.remove('hide');
    aplicarFiltro('');
}

function alternarBuscaChat() {
    if (aberta) fecharBuscaChat();
    else abrirBuscaChat();
}

function _ligar() {
    if (dom.btnChatSearch) dom.btnChatSearch.addEventListener('click', alternarBuscaChat);
    if (dom.chatSearchLupa) {
        dom.chatSearchLupa.addEventListener('click', () => {
            if (aberta) fecharBuscaChat();
        });
    }
    if (!dom.chatSearchInput) return;
    let relogio = null;
    dom.chatSearchInput.addEventListener('input', () => {
        clearTimeout(relogio);
        const valor = dom.chatSearchInput.value;
        relogio = setTimeout(() => aplicarFiltro(valor), ESPERA_MS);
    });
    dom.chatSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            e.stopPropagation();
            fecharBuscaChat();
        }
    });
}

_ligar();

export { alternarBuscaChat, fecharBuscaChat, reavaliarBuscaChat };
