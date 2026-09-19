import * as dom from './dom.js';
import { showAlert } from './ui.js';
import { SVG_OLHO, SVG_OLHO_RISCADO } from './icones.js';

const ORDEM = ['identidade', 'email', 'site', 'servidor'];
const ESPERA_DO_ARMADO = 4000;
const ID_DA_DICA = 'cofre-info-';

let categorias = {};
let entradas = [];
let revelar = false;

function _fechado() {
    return { aberto: false, editando: false, valores: {}, titulo: '' };
}

export async function carregarCofre(opcoes = {}) {
    if (!dom.cofreCorpo) return;
    const anterior = opcoes.preservar ? _estadoDoDom() : new Map();
    if (opcoes.recolher) anterior.set(opcoes.recolher, _fechado());
    if (!(await _buscarDoServidor())) return;
    _renderizar(anterior);
}

async function _buscarDoServidor() {
    try {
        const resp = await fetch('/api/cofre' + (revelar ? '?revelar=1' : ''));
        const dados = await resp.json();
        if (!dados.ok) {
            showAlert('Nao consegui ler o cofre: ' + (dados.error || 'resposta invalida'));
            return false;
        }
        categorias = dados.categorias || {};
        entradas = dados.entradas || [];
        return true;
    } catch (erro) {
        showAlert('Servidor indisponivel para ler o cofre: ' + erro.message);
        return false;
    }
}

function _renderizar(anterior) {
    const corpo = dom.cofreCorpo;
    if (!corpo) return;
    corpo.textContent = '';
    for (const chave of ORDEM) {
        const meta = categorias[chave];
        if (meta) corpo.appendChild(_secao(chave, meta, anterior));
    }
}

function _secao(chave, meta, anterior) {
    const secao = document.createElement('section');
    secao.className = 'cofre-secao';
    secao.dataset.categoria = chave;

    const titulo = document.createElement('div');
    titulo.className = 'cofre-secao-titulo';
    const esquerda = document.createElement('div');
    esquerda.className = 'cofre-secao-esquerda';
    const rotulo = document.createElement('span');
    rotulo.textContent = meta.rotulo || chave;
    esquerda.appendChild(rotulo);
    if (meta.dica) esquerda.appendChild(_botaoDaDica(chave));

    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'cofre-nova';
    botao.dataset.categoria = chave;
    botao.textContent = '+ nova';
    titulo.append(esquerda, botao);
    secao.appendChild(titulo);

    if (meta.dica) secao.appendChild(_textoDaDica(chave, meta.dica));

    const daCategoria = entradas.filter((entrada) => entrada.categoria === chave);
    if (!daCategoria.length) {
        const vazio = document.createElement('div');
        vazio.className = 'cofre-vazio';
        vazio.textContent = 'nada guardado';
        secao.appendChild(vazio);
    }
    for (const entrada of daCategoria) {
        secao.appendChild(_cartao(entrada, chave, anterior.get(entrada.id) || _fechado()));
    }
    return secao;
}

function _botaoDaDica(chave) {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'cofre-info';
    botao.dataset.acao = 'dica';
    botao.dataset.dica = chave;
    botao.title = 'Sobre esta seccao';
    botao.textContent = 'i';
    return botao;
}

function _textoDaDica(chave, dica) {
    const bloco = document.createElement('div');
    bloco.className = 'settings-info-text';
    bloco.id = ID_DA_DICA + chave;
    const dentro = document.createElement('div');
    dentro.className = 'settings-info-text-inner';
    dentro.textContent = dica;
    bloco.appendChild(dentro);
    return bloco;
}

function _cartao(entrada, categoria, estado) {
    const meta = categorias[categoria] || {};
    const campos = entrada.campos || {};
    const nomes = [...new Set([...(meta.campos || []), ...Object.keys(campos)])];

    const cartao = document.createElement('div');
    cartao.className = 'cofre-entrada';
    cartao.dataset.id = entrada.id || '';
    cartao.dataset.categoria = categoria;
    cartao.dataset.aberto = estado.aberto ? '1' : '0';
    cartao.dataset.editando = estado.editando ? '1' : '0';

    const cabecalho = document.createElement('div');
    cabecalho.className = 'cofre-cabecalho';

    const alternar = document.createElement('button');
    alternar.type = 'button';
    alternar.className = 'cofre-alternar';
    alternar.dataset.acao = 'alternar';
    const sinal = document.createElement('span');
    sinal.className = 'cofre-sinal';
    const texto = document.createElement('span');
    texto.className = 'cofre-titulo-texto';
    texto.textContent = (entrada.titulo || '').trim() || 'nova entrada';
    alternar.append(sinal, texto);

    const titulo = document.createElement('input');
    titulo.className = 'cofre-titulo';
    titulo.type = 'text';
    titulo.autocomplete = 'off';
    titulo.placeholder = 'nome da entrada';
    titulo.value = estado.titulo || entrada.titulo || '';

    const faltando = entrada.faltando || [];
    const falta = document.createElement('span');
    falta.className = 'cofre-falta';
    falta.textContent = faltando.length ? 'falta: ' + faltando.join(', ') : '';
    if (!faltando.length) falta.classList.add('hidden');

    const editar = document.createElement('button');
    editar.type = 'button';
    editar.className = 'cofre-acao';
    editar.dataset.acao = 'editar';
    editar.textContent = 'Editar';

    const apagar = document.createElement('button');
    apagar.type = 'button';
    apagar.className = 'cofre-acao cofre-apagar';
    apagar.dataset.acao = 'apagar';
    apagar.textContent = 'excluir';

    cabecalho.append(alternar, titulo, falta, editar, apagar);
    cartao.appendChild(cabecalho);

    const corpo = document.createElement('div');
    corpo.className = 'cofre-campos';
    const clip = document.createElement('div');
    clip.className = 'cofre-campos-clip';
    for (const nomeDoCampo of nomes) {
        const linha = document.createElement('label');
        linha.className = 'cofre-campo';
        const rotulo = document.createElement('span');
        rotulo.className = 'cofre-campo-nome';
        rotulo.textContent = (meta.rotulos || {})[nomeDoCampo] || nomeDoCampo;
        const campo = document.createElement('input');
        campo.className = 'settings-input';
        campo.type = 'text';
        campo.autocomplete = 'off';
        campo.dataset.campo = nomeDoCampo;
        const digitado = estado.valores[nomeDoCampo];
        const guardado = campos[nomeDoCampo];
        campo.value = estado.editando && digitado != null
            ? digitado
            : (guardado == null ? '' : String(guardado));
        linha.append(rotulo, campo);
        clip.appendChild(linha);
    }
    corpo.appendChild(clip);
    cartao.appendChild(corpo);
    _aplicarEstado(cartao);
    return cartao;
}

function _aplicarEstado(cartao) {
    const editando = cartao.dataset.editando === '1';
    const botao = cartao.querySelector('[data-acao="guardar"], [data-acao="editar"]');
    if (botao) {
        botao.dataset.acao = editando ? 'guardar' : 'editar';
        botao.textContent = editando ? 'Guardar' : 'Editar';
    }
    cartao.querySelectorAll('input').forEach((campo) => {
        campo.disabled = !editando;
    });
}

function _estadoDoDom() {
    const mapa = new Map();
    const corpo = dom.cofreCorpo;
    if (!corpo) return mapa;
    corpo.querySelectorAll('.cofre-entrada').forEach((cartao) => {
        const id = cartao.dataset.id;
        if (!id) return;
        const valores = {};
        cartao.querySelectorAll('input[data-campo]').forEach((campo) => {
            valores[campo.dataset.campo] = campo.value;
        });
        const campoTitulo = cartao.querySelector('.cofre-titulo');
        mapa.set(id, {
            aberto: cartao.dataset.aberto === '1',
            editando: cartao.dataset.editando === '1',
            valores,
            titulo: campoTitulo ? campoTitulo.value : '',
        });
    });
    return mapa;
}

export function ligarEventosCofre() {
    const corpo = dom.cofreCorpo;
    if (corpo) corpo.addEventListener('click', _aoClicar);
    if (dom.btnCofreRevelar) dom.btnCofreRevelar.addEventListener('click', _alternarValores);
    _pintarOlhinho();
}

function _pintarOlhinho() {
    const botao = dom.btnCofreRevelar;
    if (!botao) return;
    botao.classList.toggle('on', revelar);
    botao.setAttribute('aria-pressed', revelar ? 'true' : 'false');
    botao.title = revelar ? 'Ocultar valores' : 'Mostrar valores';
    botao.innerHTML = revelar ? SVG_OLHO_RISCADO : SVG_OLHO;
}

async function _alternarValores() {
    revelar = !revelar;
    _pintarOlhinho();
    if (!(await _buscarDoServidor())) return;
    _pintarValores();
}

function _pintarValores() {
    const corpo = dom.cofreCorpo;
    if (!corpo) return;
    const porId = new Map(entradas.map((entrada) => [entrada.id, entrada]));
    corpo.querySelectorAll('.cofre-entrada').forEach((cartao) => {
        const entrada = porId.get(cartao.dataset.id);
        if (entrada) _pintarValoresDoCartao(cartao, entrada.campos || {});
    });
}

function _pintarValoresDoCartao(cartao, campos) {
    cartao.querySelectorAll('input[data-campo]').forEach((campo) => {
        const nome = campo.dataset.campo;
        if (nome in campos) campo.value = campos[nome] == null ? '' : String(campos[nome]);
    });
}

function _refletirEntrada(cartao, entrada) {
    cartao.dataset.id = entrada.id || '';
    _pintarValoresDoCartao(cartao, entrada.campos || {});
    const texto = cartao.querySelector('.cofre-titulo-texto');
    if (texto) texto.textContent = (entrada.titulo || '').trim() || 'nova entrada';
    const campoDoTitulo = cartao.querySelector('.cofre-titulo');
    if (campoDoTitulo) campoDoTitulo.value = entrada.titulo || '';
    const falta = cartao.querySelector('.cofre-falta');
    if (falta) {
        const faltando = entrada.faltando || [];
        falta.textContent = faltando.length ? 'falta: ' + faltando.join(', ') : '';
        falta.classList.toggle('hidden', !faltando.length);
    }
    cartao.dataset.editando = '0';
    cartao.dataset.aberto = '0';
    _aplicarEstado(cartao);
}

function _aoClicar(evento) {
    const botao = evento.target.closest('button');
    if (!botao) return;
    if (botao.classList.contains('cofre-nova')) {
        criarEntrada(botao.dataset.categoria);
        return;
    }
    if (botao.classList.contains('cofre-info')) {
        _alternarDica(botao);
        return;
    }
    const cartao = botao.closest('.cofre-entrada');
    if (!cartao) return;
    const acao = botao.dataset.acao;
    if (acao === 'alternar') {
        cartao.dataset.aberto = cartao.dataset.aberto === '1' ? '0' : '1';
        return;
    }
    if (acao === 'editar') {
        cartao.dataset.editando = '1';
        cartao.dataset.aberto = '1';
        _aplicarEstado(cartao);
        const titulo = cartao.querySelector('.cofre-titulo');
        if (titulo) titulo.focus();
        return;
    }
    if (acao === 'guardar') guardarEntrada(cartao);
    if (acao === 'apagar') apagarEntrada(cartao, botao);
}

function _alternarDica(botao) {
    const corpo = dom.cofreCorpo;
    const alvo = document.getElementById(ID_DA_DICA + botao.dataset.dica);
    if (!alvo || !corpo) return;
    const abrir = !alvo.classList.contains('open');
    corpo.querySelectorAll('.settings-info-text').forEach((bloco) => bloco.classList.remove('open'));
    corpo.querySelectorAll('.cofre-info').forEach((outro) => outro.classList.remove('active'));
    if (abrir) {
        alvo.classList.add('open');
        botao.classList.add('active');
    }
}

function criarEntrada(categoria) {
    const corpo = dom.cofreCorpo;
    if (!corpo) return;
    const secao = corpo.querySelector(`.cofre-secao[data-categoria="${categoria}"]`);
    if (!secao) return;
    const vazio = secao.querySelector('.cofre-vazio');
    if (vazio) vazio.remove();
    const cartao = _cartao({ id: '', titulo: '', campos: {} }, categoria, {
        aberto: true,
        editando: true,
        valores: {},
        titulo: '',
    });
    secao.appendChild(cartao);
    const titulo = cartao.querySelector('.cofre-titulo');
    if (titulo) titulo.focus();
}

async function guardarEntrada(cartao) {
    const campos = {};
    cartao.querySelectorAll('input[data-campo]').forEach((campo) => {
        campos[campo.dataset.campo] = campo.value;
    });
    const titulo = cartao.querySelector('.cofre-titulo');
    const corpo = {
        id: cartao.dataset.id || '',
        titulo: titulo ? titulo.value.trim() : '',
        categoria: cartao.dataset.categoria || '',
        campos,
    };
    try {
        const resp = await fetch('/api/cofre', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(corpo),
        });
        const dados = await resp.json();
        if (!resp.ok || !dados.ok) {
            showAlert('Nao guardei: ' + (dados.error || 'resposta invalida'));
            return;
        }
        if (await _buscarDoServidor()) {
            const entrada = entradas.find((item) => item.id === ((dados.entrada || {}).id || ''));
            if (entrada) _refletirEntrada(cartao, entrada);
        }
    } catch (erro) {
        showAlert('Erro ao guardar no cofre: ' + erro.message);
    }
}

async function apagarEntrada(cartao, botao) {
    if (botao.dataset.confirmar !== '1') {
        botao.dataset.confirmar = '1';
        botao.textContent = 'confirmar?';
        botao.classList.add('cofre-apagar-armado');
        setTimeout(() => {
            if (!botao.isConnected) return;
            botao.dataset.confirmar = '';
            botao.textContent = 'excluir';
            botao.classList.remove('cofre-apagar-armado');
        }, ESPERA_DO_ARMADO);
        return;
    }
    const id = cartao.dataset.id;
    if (!id) {
        cartao.remove();
        return;
    }
    try {
        await fetch('/api/cofre/' + encodeURIComponent(id), { method: 'DELETE' });
        await carregarCofre({ preservar: true });
    } catch (erro) {
        showAlert('Erro ao excluir do cofre: ' + erro.message);
    }
}
