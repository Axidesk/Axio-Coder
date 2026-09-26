import { state } from './state.js';

const CLASSE_ERRO = 'monaco-linha-erro';
const CLASSE_PARAGEM = 'monaco-linha-paragem';

let colecao = null;
let alvo = null;
let instalado = false;

function chave(caminho) {
    return String(caminho || '').replace(/\\/g, '/').toLowerCase();
}

export function marcarLinhaDoDepurador(ficheiro, linha, erro) {
    const numero = parseInt(linha, 10) || 0;
    if (!ficheiro || !numero) return;
    alvo = { ficheiro: chave(ficheiro), linha: numero, erro: !!erro };
    pintar();
}

export function limparLinhaDoDepurador() {
    if (!alvo) return;
    alvo = null;
    pintar();
}

export function instalarLinhaDoDepurador() {
    if (instalado || !state.editor) return;
    instalado = true;
    state.editor.onDidChangeModel(pintar);
}

export function mesmoFicheiro(a, b) {
    const um = chave(a);
    const outro = chave(b);
    if (!um || !outro) return false;
    return um === outro || um.endsWith('/' + outro) || outro.endsWith('/' + um);
}

export function caminhoDoDepurador(caminho) {
    const procurado = chave(caminho);
    if (!procurado) return '';
    if (chave(state.currentFile) === procurado) return state.currentFile;
    for (const aberto of state.openTabs) {
        if (chave(aberto) === procurado) return aberto;
    }
    for (const aberto of state.openTabs) {
        if (mesmoFicheiro(aberto, caminho)) return aberto;
    }
    if (state.currentFile && mesmoFicheiro(state.currentFile, caminho)) return state.currentFile;
    return String(caminho || '').replace(/\\/g, '/');
}

function pintar() {
    if (!state.editor || !state.monaco) return;
    colecao = state.editor.deltaDecorations(colecao || [], decoracoes());
}

function decoracoes() {
    if (!alvo || !mesmoFicheiro(state.currentFile, alvo.ficheiro)) return [];
    const modelo = state.editor.getModel();
    if (!modelo || alvo.linha > modelo.getLineCount()) return [];
    return [{
        range: new state.monaco.Range(alvo.linha, 1, alvo.linha, 1),
        options: { isWholeLine: true, className: alvo.erro ? CLASSE_ERRO : CLASSE_PARAGEM },
    }];
}
