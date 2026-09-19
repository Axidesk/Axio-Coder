import { familiaDe, nomeDe } from '../editor/familia_ficheiro.js';

const palco = document.getElementById('vw-palco');
const vazio = document.getElementById('vw-vazio');
const ferramentas = document.getElementById('vw-ferramentas');

const MAX_LEITORES = 4;

const leitores = new Map();
let ativo = null;
let marca = 0;

function caminhoDaUrl() {
    const dados = new URLSearchParams((location.hash || '').replace(/^#/, ''));
    const daHash = dados.get('f');
    if (daHash) return daHash;
    return new URLSearchParams(location.search).get('f') || '';
}

function enderecoDoFicheiro(caminho) {
    return '/preview/' + String(caminho).split(/[\\/]/).map(encodeURIComponent).join('/');
}

function desenharEstado(registro, texto, tipo) {
    if (!registro.estado || !registro.estado.isConnected) {
        const novo = document.createElement('div');
        novo.className = 'vw-estado';
        registro.caixa.appendChild(novo);
        registro.estado = novo;
    }
    registro.estado.className = 'vw-estado' + (tipo === 'erro' ? ' vw-erro' : '');
    registro.estado.innerHTML = '';
    registro.barra = null;
    const linha = document.createElement('div');
    linha.className = 'vw-estado-texto';
    linha.textContent = texto;
    registro.estado.appendChild(linha);
    if (tipo === 'erro') return;
    const moldura = document.createElement('div');
    moldura.className = 'vw-barra-progresso';
    const barra = document.createElement('i');
    moldura.appendChild(barra);
    registro.estado.appendChild(moldura);
    registro.barra = barra;
}

function progressoDe(registro, fracao) {
    if (!registro.barra) return;
    const pct = Math.round(Math.max(0, Math.min(1, Number(fracao) || 0)) * 100);
    registro.barra.style.width = pct + '%';
}

function concluirAbertura(registro) {
    if (registro.estado && registro.estado.parentNode) registro.estado.remove();
    registro.estado = null;
    registro.barra = null;
}

function libertar(registro) {
    if (!registro) return;
    leitores.delete(registro.caminho);
    if (ativo === registro) ativo = null;
    if (registro.api && registro.api.destruir) {
        try {
            registro.api.destruir();
        } catch (erro) {
            console.warn('falha ao libertar o leitor', erro);
        }
    }
    registro.caixa.remove();
}

function podar() {
    while (leitores.size > MAX_LEITORES) {
        let vitima = null;
        for (const registro of leitores.values()) {
            if (registro === ativo) continue;
            if (!vitima || registro.usado < vitima.usado) vitima = registro;
        }
        if (!vitima) return;
        libertar(vitima);
    }
}

function mostrar(registro) {
    if (ativo === registro) return;
    ativo = registro;
    for (const outro of leitores.values()) {
        outro.caixa.classList.toggle('vw-visivel', outro === registro);
    }
    ferramentas.innerHTML = '';
    if (!registro) return;
    registro.usado = ++marca;
    document.title = registro.nome;
    if (registro.api && registro.api.aoAtivar) registro.api.aoAtivar();
    if (registro.api && registro.api.aoMostrar) registro.api.aoMostrar();
}

async function montar(caminho) {
    const limpo = String(caminho || '');
    if (!limpo) {
        mostrar(null);
        vazio.classList.remove('vw-escondido');
        document.title = 'Visualizador';
        return;
    }
    vazio.classList.add('vw-escondido');

    const guardado = leitores.get(limpo);
    if (guardado) {
        mostrar(guardado);
        return;
    }

    const nome = nomeDe(limpo) || 'Ficheiro';
    const familia = familiaDe(limpo);
    const caixa = document.createElement('div');
    caixa.className = 'vw-caixa';
    palco.appendChild(caixa);

    const registro = { caminho: limpo, nome, caixa, estado: null, barra: null, api: null, usado: ++marca };
    leitores.set(limpo, registro);
    caixa.getBoundingClientRect();
    mostrar(registro);
    desenharEstado(registro, 'abrindo ' + nome + '...');
    podar();

    if (!familia) {
        desenharEstado(registro, 'Sem visualizador para "' + nome + '".', 'erro');
        return;
    }

    const vivo = () => leitores.get(limpo) === registro;
    const ctx = {
        ferramentas,
        avisar: (texto, fracao) => {
            if (!vivo()) return;
            const linha = registro.estado && registro.estado.querySelector('.vw-estado-texto');
            if (linha) linha.textContent = texto;
            progressoDe(registro, fracao);
        },
        concluir: () => {
            if (vivo()) concluirAbertura(registro);
        },
        falhar: (texto) => {
            if (vivo()) desenharEstado(registro, texto, 'erro');
        }
    };

    try {
        const endereco = '/vendor/viewer/dist/leitores/' + familia.id + '.js';
        const modulo = await import(endereco);
        if (!vivo()) return;
        const api = await modulo.montar(caixa, {
            caminho: limpo,
            url: enderecoDoFicheiro(limpo),
            nome,
            familia
        }, ctx);
        if (!vivo()) {
            if (api && api.destruir) {
                try {
                    api.destruir();
                } catch (erro) {
                    console.warn('falha ao libertar o leitor', erro);
                }
            }
            return;
        }
        registro.api = api;
        if (ativo === registro) {
            if (api && api.aoAtivar) api.aoAtivar();
            if (api && api.aoMostrar) api.aoMostrar();
        }
    } catch (erro) {
        ctx.falhar('Nao consegui abrir: ' + ((erro && erro.message) || erro));
    }
}

function aplicarFerramentas(ligado) {
    document.body.classList.toggle('vw-com-ferramentas', !!ligado);
    if (ativo && ativo.api && ativo.api.aoMostrar) ativo.api.aoMostrar();
}

document.addEventListener('axio-ferramentas', (e) => aplicarFerramentas(e.detail));

window.addEventListener('hashchange', () => montar(caminhoDaUrl()));

montar(caminhoDaUrl());
