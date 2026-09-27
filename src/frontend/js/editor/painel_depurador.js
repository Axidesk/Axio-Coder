import { criarVista } from '../chat/colunas.js';
import { syncDocTopBar } from '../chat/layout.js';
import { caminhoRelativoAoProjeto, focarAba, openFileInEditor } from './editor.js';
import { caminhoDoDepurador, marcarLinhaDoDepurador } from './linha_depurador.js';

const ID_DA_CAMADA = 'panel-col-3-debug';

let estadoAtual = null;

const vistaDepurador = criarVista({
    id: 'depurador',
    col3: document.getElementById(ID_DA_CAMADA),
    abrirCol3() {
        if (window.WorkspaceView && typeof window.WorkspaceView.showEditor === 'function') {
            window.WorkspaceView.showEditor();
        }
        const camada = document.getElementById(ID_DA_CAMADA);
        if (camada) camada.classList.remove('panel-col-closed');
        syncDocTopBar();
    },
    fecharCol3() {
        const camada = document.getElementById(ID_DA_CAMADA);
        if (camada) camada.classList.add('panel-col-closed');
        syncDocTopBar();
    }
});

function nomeDoFicheiro(caminho) {
    return String(caminho || '').replace(/\\/g, '/').split('/').pop();
}

export function quadrosDaParagem(estado) {
    if (!estado) return [];
    const atual = { nome: nomeDoFicheiro(estado.arquivo), caminho: estado.arquivo || '',
                    linha: parseInt(estado.linha, 10) || 0, atual: true };
    const anteriores = (estado.quadros || [])
        .map(q => ({ nome: q.nome || nomeDoFicheiro(q.caminho), caminho: q.caminho || '',
                     linha: parseInt(q.linha, 10) || 0, atual: false }))
        .filter(q => !(q.linha === atual.linha && q.nome === atual.nome))
        .reverse();
    return [atual].concat(anteriores);
}

export function variaveisDaParagem(estado) {
    return ((estado && estado.variaveis) || []).map(v => ({
        nome: String(v.nome || ''),
        valor: v.valor === undefined || v.valor === null ? '' : String(v.valor),
        nota: String(v.nota || '')
    }));
}

function bloco(titulo, itens, vazio) {
    const caixa = document.createElement('div');
    caixa.className = 'depurador-bloco';
    const cabecalho = document.createElement('div');
    cabecalho.className = 'depurador-bloco-titulo';
    cabecalho.textContent = titulo;
    caixa.appendChild(cabecalho);
    if (!itens.length) {
        const aviso = document.createElement('div');
        aviso.className = 'depurador-vazio';
        aviso.textContent = vazio;
        caixa.appendChild(aviso);
        return caixa;
    }
    itens.forEach(item => caixa.appendChild(item));
    return caixa;
}

function linhaDeQuadro(quadro) {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'depurador-linha' + (quadro.atual ? ' depurador-linha-atual' : '');
    botao.title = (quadro.caminho || quadro.nome) + ':' + quadro.linha;
    const nome = document.createElement('span');
    nome.className = 'depurador-nome';
    nome.textContent = quadro.nome || '(sem nome)';
    const sitio = document.createElement('span');
    sitio.className = 'depurador-sitio';
    sitio.textContent = ':' + quadro.linha;
    botao.appendChild(nome);
    botao.appendChild(sitio);
    botao.addEventListener('click', () => irPara(quadro));
    return botao;
}

function linhaDeVariavel(variavel) {
    const caixa = document.createElement('div');
    caixa.className = 'depurador-linha';
    const nome = document.createElement('span');
    nome.className = 'depurador-nome';
    nome.textContent = variavel.nome + ' =';
    const valor = document.createElement('span');
    valor.className = 'depurador-valor';
    valor.textContent = variavel.valor;
    if (variavel.nota) valor.title = variavel.nota;
    caixa.appendChild(nome);
    caixa.appendChild(valor);
    return caixa;
}

function irPara(quadro) {
    const caminho = caminhoRelativoAoProjeto(caminhoDoDepurador(quadro.caminho));
    if (!caminho || !quadro.linha) return;
    marcarLinhaDoDepurador(caminho, quadro.linha, false);
    openFileInEditor(caminho, { line: quadro.linha });
    focarAba(caminho);
}

function pintar() {
    const corpo = document.getElementById('debug-panel-corpo');
    if (!corpo) return;
    const sitio = document.getElementById('debug-panel-onde');
    if (sitio) {
        sitio.textContent = estadoAtual
            ? nomeDoFicheiro(estadoAtual.arquivo) + ':' + (estadoAtual.linha || '') : '';
        sitio.title = estadoAtual && estadoAtual.arquivo ? estadoAtual.arquivo : '';
    }
    corpo.textContent = '';
    if (!estadoAtual) {
        const aviso = document.createElement('div');
        aviso.className = 'depurador-vazio';
        aviso.textContent = 'Sem sessao de depuracao aberta.';
        corpo.appendChild(aviso);
        return;
    }
    corpo.appendChild(bloco('Pilha de chamadas',
                            quadrosDaParagem(estadoAtual).map(linhaDeQuadro),
                            'Sem pilha nesta paragem. Carregue em Pilha no card do depurador.'));
    corpo.appendChild(bloco('Variaveis',
                            variaveisDaParagem(estadoAtual).map(linhaDeVariavel),
                            'Sem variaveis nesta paragem. Carregue em Variaveis no card do depurador.'));
}

export function mostrarEstadoDoDepurador(estado) {
    estadoAtual = estado || null;
    pintar();
}

export function abrirPainelDoDepurador() {
    if (!vistaDepurador.col3Aberta()) vistaDepurador.abrirCol3();
    pintar();
}

function ligarFecho() {
    const botao = document.getElementById('btn-close-debug-panel');
    if (botao) botao.addEventListener('click', () => vistaDepurador.fecharCol3());
}

ligarFecho();
