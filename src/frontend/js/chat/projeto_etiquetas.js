import * as dom from './dom.js';
import { state } from './state.js';
import { bloquearChat, esconderIconTooltip, mostrarIconTooltip, showAlert } from './ui.js';

const ESPERA_POLLING = 1500;
const CHAVE_VISIVEIS = 'axio-etiquetas-visiveis';

const SVG_ATUALIZAR = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>';
const SVG_SPINNER = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="9" stroke-dasharray="42 15"/></svg>';
const SVG_OLHO = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const SVG_OLHO_RISCADO = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

let atualizarEl = null;
let olhoEl = null;
let acompanhamento = 0;
let tooltipLigado = false;
let tagComBalao = null;

function _ligarBalaoHover(el) {
    el.addEventListener('mouseover', function () {
        const texto = el.dataset.info;
        if (texto) mostrarIconTooltip(el, texto);
    });
    el.addEventListener('mouseout', function (e) {
        const related = e.relatedTarget;
        if (related && el.contains(related)) return;
        esconderIconTooltip();
    });
}

function _criarBotao(classe, titulo, icones) {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = classe;
    botao.dataset.info = titulo;
    _ligarBalaoHover(botao);
    icones.forEach(function (par) {
        const span = document.createElement('span');
        span.className = 'projeto-controle-icone ' + par[0];
        span.innerHTML = par[1];
        botao.appendChild(span);
    });
    return botao;
}

export function etiquetasVisiveis() {
    return localStorage.getItem(CHAVE_VISIVEIS) !== '0';
}


let destinoColuna = null;
let destinoCabecalho = null;

function _colocarOlho() {
    if (!olhoEl || !destinoColuna || !destinoCabecalho) return;
    const visiveis = etiquetasVisiveis();

    const noLugar = visiveis
        ? olhoEl.parentElement === destinoColuna
        : (olhoEl.parentElement === destinoCabecalho
           && olhoEl.nextElementSibling === destinoColuna);
    if (noLugar) return;

    const noEcra = olhoEl.isConnected;

    olhoEl.classList.remove('projeto-olho-vem');
    void olhoEl.offsetWidth;
    if (visiveis) {
        destinoColuna.appendChild(olhoEl);
    } else {
        destinoCabecalho.insertBefore(olhoEl, destinoColuna);
    }
    if (noEcra) olhoEl.classList.add('projeto-olho-vem');
}

export function anexarOlho(cabecalho, coluna) {
    destinoCabecalho = cabecalho;
    destinoColuna = coluna;
    _colocarOlho();
}

function _aplicarVisibilidade() {
    if (!dom.projectInfoBody) return;
    const visiveis = etiquetasVisiveis();
    dom.projectInfoBody.classList.toggle('etiquetas-ocultas', !visiveis);
    if (!olhoEl) return;
    olhoEl.classList.toggle('etiquetas-desligadas', !visiveis);
    olhoEl.dataset.info = visiveis ? 'Ocultar etiquetas' : 'Mostrar etiquetas';
    _colocarOlho();
}


export function criarControlesEstrutura() {
    const caixa = document.createElement('span');
    caixa.className = 'projeto-controles';
    atualizarEl = _criarBotao('projeto-controle projeto-atualizar', 'Atualizar etiquetas', [
        ['projeto-icone-atualizar', SVG_ATUALIZAR],
        ['projeto-icone-spinner', SVG_SPINNER],
    ]);
    atualizarEl.addEventListener('click', function () {
        iniciarEtiquetagem(false);
    });
    olhoEl = _criarBotao('projeto-controle projeto-olho', 'Ocultar etiquetas', [
        ['projeto-icone-olho', SVG_OLHO],
        ['projeto-icone-olho-riscado', SVG_OLHO_RISCADO],
    ]);
    olhoEl.addEventListener('click', function () {
        localStorage.setItem(CHAVE_VISIVEIS, etiquetasVisiveis() ? '0' : '1');
        _aplicarVisibilidade();
    });
    caixa.appendChild(atualizarEl);
    _aplicarVisibilidade();
    return { caixa: caixa, olho: olhoEl };
}

function _ligarTooltipTruncado() {
    const corpo = dom.projectInfoBody;
    if (tooltipLigado || !corpo) return;
    tooltipLigado = true;
    corpo.addEventListener('mouseover', function (e) {

        if (tagComBalao && !tagComBalao.isConnected) {
            tagComBalao = null;
            esconderIconTooltip();
        }
        const tag = e.target && e.target.closest ? e.target.closest('.projeto-tag') : null;
        if (!tag || tag === tagComBalao) return;
        if (tag.scrollWidth <= tag.clientWidth) return;
        tagComBalao = tag;
        mostrarIconTooltip(tag, tag.textContent);
    });
    corpo.addEventListener('mouseout', function (e) {
        if (!tagComBalao) return;
        const related = e.relatedTarget;
        if (related && tagComBalao.contains(related)) return;
        tagComBalao = null;
        esconderIconTooltip();
    });
}

export function aplicarEtiquetas(nos) {
    const corpo = dom.projectInfoBody;
    if (!corpo) return;
    _ligarTooltipTruncado();
    const mapa = nos || {};
    const temEtiquetas = Object.keys(mapa).length > 0;
    corpo.querySelectorAll('[data-caminho]').forEach(function (linha) {
        const tag = (mapa[linha.dataset.caminho] || {}).tag;
        const atual = linha.querySelector('.projeto-tag');
        if (!temEtiquetas) {
            if (atual) atual.remove();
            return;
        }
        // o span vazio reserva a coluna: sem ele o nome e a contagem invadem o fio
        const span = atual || document.createElement('span');
        span.className = 'projeto-tag';
        span.textContent = tag ? '#' + tag : '';
        if (!atual) linha.appendChild(span);
    });

    corpo.classList.toggle('tem-etiquetas', temEtiquetas);
    if (atualizarEl) {
        atualizarEl.dataset.info = temEtiquetas ? 'Atualizar etiquetas' : 'Etiquetar a arvore';
    }
}

function _definirTrabalho(ativo, progresso) {
    if (atualizarEl) {
        atualizarEl.classList.toggle('a-trabalhar', ativo);
        atualizarEl.disabled = ativo;
    }

    bloquearChat(ativo, {
        classe: 'etiquetando',
        placeholder: 'Etiquetando o projeto...',
        status: progresso ? 'Etiquetando... ' + progresso : 'Etiquetando...'
    });
}

async function _pedir(rota, opcoes) {
    try {
        const resp = await fetch(rota, opcoes);
        return await resp.json();
    } catch (e) {
        return null;
    }
}

function _esperar(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function _acompanhar(primeiro) {
    const meu = ++acompanhamento;
    let dados = primeiro || null;
    while (meu === acompanhamento) {
        if (!dados) dados = await _pedir('/api/projeto/etiquetas');
        if (meu !== acompanhamento) break;

        if (!dados) {
            _definirTrabalho(false);
            return;
        }
        aplicarEtiquetas(dados.nos);
        const aTrabalhar = dados.estado === 'a_etiquetar';
        _definirTrabalho(aTrabalhar, dados.progresso);
        if (!aTrabalhar) return;
        dados = null;
        await _esperar(ESPERA_POLLING);
    }
}

export async function carregarEtiquetas(primeiros) {

    const dados = primeiros || await _pedir('/api/projeto/etiquetas');
    if (!dados) return;
    aplicarEtiquetas(dados.nos);
    if (dados.estado === 'a_etiquetar') {
        _definirTrabalho(true, dados.progresso);
        _acompanhar(dados);
        return;
    }

    if (dados.inicial && !state.isGenerating) iniciarEtiquetagem(true);
}

export async function iniciarEtiquetagem(automatico) {
    if (state.isGenerating) {
        if (!automatico) {
            showAlert('Aguarde a conclusão da resposta atual antes de etiquetar o projeto.');
        }
        return;
    }
    _definirTrabalho(true);
    const resposta = await _pedir('/api/projeto/etiquetar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_deepseek: state.selectedModel === 'deepseek' }),
    });
    if (!resposta || resposta.erro) {
        _definirTrabalho(false);
        if (resposta && resposta.erro && !automatico) showAlert(resposta.erro);
        return;
    }
    _acompanhar();
}
