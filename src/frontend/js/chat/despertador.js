import * as dom from './dom.js';
import { showAlert, travarPorDespertador } from './ui.js';
import { state } from './state.js';

let _alvo = 0;
let _relogio = null;
let _rascunho = null;
let _modo = 'fixo';
let _rotulo = '';
let _tipo = '';

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

function _textoDaContagem(restante) {
    if (_modo === 'decorrido') {
        return `${_rotulo} · ha ${_humano(Date.now() / 1000 - _alvo)}`;
    }
    return _tipo === 'tempo'
        ? `agendado para ${_humano(restante)}`
        : `${_rotulo} · faltam ${_humano(restante)}`;
}

function _pintarContagem() {
    const { texto } = _elementos();
    if (!texto) return;
    const restante = _alvo - Date.now() / 1000;
    texto.textContent = _modo === 'decorrido' || restante > 0
        ? _textoDaContagem(restante)
        : 'a acordar…';
}

function _pararRelogio() {
    if (_relogio) clearInterval(_relogio);
    _relogio = null;
}

function _semPrazo(descricao) {
    return String(descricao || '').replace(/\s*\(no maximo [^)]*\)/i, '');
}

function _mostrar(dados) {
    const { barra, texto } = _elementos();
    if (!barra || !texto) return;
    barra.hidden = false;
    const falta = Number(dados && dados.falta) || 0;
    const decorrido = Number(dados && dados.decorrido) || 0;
    _rotulo = _semPrazo(dados && dados.descricao) || 'agendado';
    _tipo = String((dados && dados.tipo) || '');
    _pararRelogio();
    if (falta > 0) {
        _modo = 'restante';
        _alvo = Date.now() / 1000 + falta;
        _pintarContagem();
        _relogio = setInterval(_pintarContagem, 1000);
        return;
    }
    if (decorrido > 0) {
        _modo = 'decorrido';
        _alvo = Date.now() / 1000 - decorrido;
        _pintarContagem();
        _relogio = setInterval(_pintarContagem, 1000);
        return;
    }
    _modo = 'fixo';
    texto.textContent = _rotulo;
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
        _mostrar(data);
        _travar(data.nota || '');
        return;
    }
    if (estado === 'disparado') {
        _soltar();
        _mostrar({ descricao: 'acordei agora' });
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
            _mostrar(dados);
            _travar(dados.nota || '');
            return;
        }
        if (dados.estado === 'disparado') {
            _soltar();
            _mostrar({ descricao: 'acordei agora' });
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
