import * as dom from './dom.js';
import { showAlert } from './ui.js';

let _alvo = 0;
let _relogio = null;

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
        : 'a acordar…';
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

function _guardarNotaNoCampo(nota) {
    if (!dom.inputText || !nota) return;
    if ((dom.inputText.value || '').trim()) return;
    dom.inputText.value = nota;
    dom.inputText.dispatchEvent(new Event('input'));
}

export function tratarDespertador(data) {
    const estado = String(data.estado || '');
    if (estado === 'armado') {
        _mostrar(data.descricao, Number(data.falta) || 0);
        return;
    }
    if (estado === 'disparado') {
        _mostrar('acordei agora', 0);
        _guardarNotaNoCampo(data.nota || '');
        fetch('/api/despertador/entregue', { method: 'POST' }).catch(() => {});
        return;
    }
    if (estado === 'cancelado' || estado === 'entregue') {
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
            return;
        }
        if (dados.estado === 'disparado') {
            _mostrar('acordei agora', 0);
            _guardarNotaNoCampo(dados.nota || '');
            fetch('/api/despertador/entregue', { method: 'POST' }).catch(() => {});
            return;
        }
        _esconder();
    } catch (erro) {
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
