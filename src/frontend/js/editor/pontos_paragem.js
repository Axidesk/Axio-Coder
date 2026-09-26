import { state } from './state.js';

const CHAVE = 'axio-pontos-paragem';
const CLASSE = 'ponto-paragem';

const porFicheiro = new Map();
let colecao = null;
let instalado = false;
let pinturaAgendada = null;
let projectoAnotado = null;

function projeto() {
    return state.rootPath || '';
}

function lerGuardados() {
    porFicheiro.clear();
    projectoAnotado = projeto();
    try {
        const tudo = JSON.parse(localStorage.getItem(CHAVE) || '{}') || {};
        const meu = tudo[projectoAnotado] || {};
        Object.keys(meu).forEach(function (ficheiro) {
            const linhas = (meu[ficheiro] || []).filter(function (linha) {
                return Number.isInteger(linha) && linha > 0;
            });
            if (linhas.length) porFicheiro.set(ficheiro, new Set(linhas));
        });
    } catch (e) {}
}

function guardar() {
    try {
        const tudo = JSON.parse(localStorage.getItem(CHAVE) || '{}') || {};
        const meu = {};
        porFicheiro.forEach(function (linhas, ficheiro) {
            if (linhas.size) {
                meu[ficheiro] = Array.from(linhas).sort(function (a, b) { return a - b; });
            }
        });
        if (Object.keys(meu).length) tudo[projeto()] = meu;
        else delete tudo[projeto()];
        localStorage.setItem(CHAVE, JSON.stringify(tudo));
    } catch (e) {}
}

export function linhasDoFicheiro(ficheiro) {
    return Array.from(porFicheiro.get(ficheiro) || []).sort(function (a, b) { return a - b; });
}

export function pontosDeParagem() {
    const pontos = [];
    porFicheiro.forEach(function (linhas, ficheiro) {
        const nome = ficheiro.replace(/\\/g, '/').split('/').pop();
        Array.from(linhas).sort(function (a, b) { return a - b; }).forEach(function (linha) {
            pontos.push(nome + ':' + linha);
        });
    });
    return pontos.join(';');
}

function decoracoes() {
    const lista = [];
    if (!state.currentFile) return lista;
    linhasDoFicheiro(state.currentFile).forEach(function (linha) {
        lista.push({
            range: new state.monaco.Range(linha, 1, linha, 1),
            options: { linesDecorationsClassName: CLASSE }
        });
    });
    return lista;
}

export function pintar() {
    if (!state.editor || !state.monaco) return;
    if (projectoAnotado !== projeto()) lerGuardados();
    colecao = state.editor.deltaDecorations(colecao || [], decoracoes());
}

function agendarPintura() {
    if (pinturaAgendada) clearTimeout(pinturaAgendada);
    pinturaAgendada = setTimeout(function () {
        pinturaAgendada = null;
        pintar();
    }, 0);
}

export function alternar(ficheiro, linha) {
    if (!ficheiro || !linha) return false;
    let linhas = porFicheiro.get(ficheiro);
    if (!linhas) {
        linhas = new Set();
        porFicheiro.set(ficheiro, linhas);
    }
    const posto = !linhas.has(linha);
    if (posto) linhas.add(linha);
    else linhas.delete(linha);
    if (!linhas.size) porFicheiro.delete(ficheiro);
    guardar();
    pintar();
    return posto;
}

export function instalarPontosDeParagem() {
    if (instalado || !state.editor || !state.monaco) return;
    instalado = true;
    lerGuardados();
    state.editor.onMouseDown(function (e) {
        const alvo = e.target;
        if (!alvo || alvo.type !== state.monaco.editor.MouseTargetType.GUTTER_LINE_DECORATIONS) return;
        if (alvo.element && alvo.element.closest && alvo.element.closest('.codicon')) return;
        const linha = alvo.position && alvo.position.lineNumber;
        if (linha) alternar(state.currentFile, linha);
    });
    state.editor.onDidChangeModel(agendarPintura);
    pintar();
    window.__axioPontosDeParagem = function () {
        return { ficheiro: state.currentFile, linhas: linhasDoFicheiro(state.currentFile), todos: pontosDeParagem() };
    };
}
