import * as dom from './dom.js';
import { showAlert, travarPorDespertador } from './ui.js';
import { state } from './state.js';

let _alvo = 0;
let _relogio = null;
let _rascunho = null;

function _elementos() {
    return {
        barra: document.getElementById('despertador-barra'),
        texto: document.getElementById('despertador-texto'),
        cancelar: document.getElementById('btn-despertador-cancelar'),
    };
}

function _humano(segundos) {
    segundos = Math.max(0, Math.round(segundos || 0));
    if (segundos < 60) return `${segundos} s`;
    const minutos = Math.floor(segundos / 60);
    if (minutos < 60) return `${minutos} min`;
    const horas = Math.floor(minutos / 60);
    const resto = minutos % 60;
    if (horas < 24) return resto ? `${horas} h ${resto} min` : `${horas} h`;
    const dias = Math.floor(horas / 24);
    return `${dias} d`;
}

function _pintarContagem() {
    const { texto } = _elementos();
    if (!texto) return;
    const restante = _alvo - Date.now() / 1000;
    texto.textContent = restante > 0
        ? `agendado para ${_humano(restante)}`
        : 'a acordar\u2026';
}

function _pararRelogio() {
    if (_relogio) clearInterval(_relogio);
    _relogio = null;
}

function _mostrar(descricao, falta) {
    const { barra, texto } = _elementos();
    if (!barra || !texto) return;
    barra.hidden = false;
    if (falta > 0) {
        _alvo = Date.now() / 1000 + falta;
        _pararRelogio();
        _pintarContagem();
        _relogio = setInterval(_pintarContagem, 1000);
        return;
    }
    _pararRelogio();
    texto.textContent = descricao || 'agendado';
}

function _esconder() {
    const { barra } = _elementos();
    _pararRelogio();
    if (barra) barra.hidden = true;
}

function _travar(nota) {
    travarPorDespertador(true);
    if (!dom.inputText) return;
    if (_rascunho === null) _rascunho = dom.inputText.value || '';
    dom.inputText.value = nota || '';
    dom.inputText.dispatchEvent(new Event('input'));
}

function _soltar() {
    travarPorDespertador(false);
    if (!dom.inputText || _rascunho === null) return;
    const rascunho = _rascunho;
    _rascunho = null;
    dom.inputText.value = rascunho;
    dom.inputText.dispatchEvent(new Event('input'));
}

function _adotarTurno(turnId) {
    if (!turnId) return;
    state.currentTurnId = turnId;
    state.isGenerating = true;
    window.currentRoundStartedAt = Date.now();
}

export function tratarDespertador(data) {
    const estado = String(data.estado || '');
    if (estado === 'armado') {
        _mostrar(data.descricao, Number(data.falta) || 0);
        _travar(data.nota || '');
        return;
    }
    if (estado === 'disparado') {
        _soltar();
        _mostrar('acordei agora', 0);
        _adotarTurno(data.proximo_turno || '');
        fetch('/api/despertador/entregue', { method: 'POST' }).catch(() => {});
        return;
    }
    if (estado === 'cancelado' || estado === 'entregue') {
        _soltar();
        _esconder();
    }
}

async function _carregar() {
    try {
        const resposta = await fetch('/api/despertador');
        const dados = await resposta.json();
        if (!dados || !dados.ok) return;
        if (dados.armado) {
            _mostrar(dados.descricao, Number(dados.falta) || 0);
            _travar(dados.nota || '');
            return;
        }
        if (dados.estado === 'disparado') {
            _soltar();
            _mostrar('acordei agora', 0);
            fetch('/api/despertador/entregue', { method: 'POST' }).catch(() => {});
            return;
        }
        _soltar();
        _esconder();
    } catch (erro) {
        _soltar();
        _esconder();
    }
}

async function _cancelar() {
    try {
        const resposta = await fetch('/api/despertador', { method: 'DELETE' });
        const dados = await resposta.json();
        if (!dados.ok) {
            showAlert('Nao consegui cancelar o despertar.');
            return;
        }
        _soltar();
        _esconder();
    } catch (erro) {
        showAlert('Servidor indisponivel para cancelar o despertar: ' + erro.message);
    }
}

export function iniciarDespertador() {
    const { cancelar } = _elementos();
    if (cancelar && cancelar.dataset.ligado !== '1') {
        cancelar.dataset.ligado = '1';
        cancelar.addEventListener('click', _cancelar);
    }
    _carregar();
}
