import { state } from './state.js';

const CORES = 6;
const MARGEM_LINHAS = 400;
const LIMITE_TOTAL = 5000;

let colecao = null;
let frame = null;
let janela = null;

function ehPlanilha(path) {
    return /\.(csv|tsv)$/i.test(String(path || ''));
}

function limitesDasCelulas(linha, separador) {
    const limites = [];
    let inicio = 0;
    let dentroDeAspas = false;
    for (let i = 0; i < linha.length; i++) {
        const caracter = linha[i];
        if (caracter === '"') {
            dentroDeAspas = !dentroDeAspas;
        } else if (caracter === separador && !dentroDeAspas) {
            limites.push([inicio, i]);
            inicio = i + 1;
        }
    }
    limites.push([inicio, linha.length]);
    return limites;
}

function guardar(editor, novas) {
    if (!colecao) {
        if (typeof editor.createDecorationsCollection === 'function') {
            colecao = editor.createDecorationsCollection(novas);
            return;
        }
        colecao = { simples: true, ids: editor.deltaDecorations([], novas) };
        return;
    }
    if (colecao.simples) {
        colecao.ids = editor.deltaDecorations(colecao.ids, novas);
        return;
    }
    colecao.set(novas);
}

function limpar(editor) {
    if (!colecao) return;
    if (colecao.simples) {
        colecao.ids = editor.deltaDecorations(colecao.ids, []);
        return;
    }
    colecao.clear();
}

function faixaPintada(editor, total) {
    if (total <= LIMITE_TOTAL) return [1, total];
    let inicio = total;
    let fim = 1;
    for (const faixa of editor.getVisibleRanges()) {
        if (faixa.startLineNumber < inicio) inicio = faixa.startLineNumber;
        if (faixa.endLineNumber > fim) fim = faixa.endLineNumber;
    }
    if (inicio > fim) return [1, Math.min(total, MARGEM_LINHAS)];
    return [Math.max(1, inicio - MARGEM_LINHAS), Math.min(total, fim + MARGEM_LINHAS)];
}

function pintar() {
    const editor = state.editor;
    const monaco = state.monaco;
    if (!editor || !monaco) return;
    const ficheiro = state.currentFile;
    if (!ehPlanilha(ficheiro)) {
        janela = null;
        limpar(editor);
        return;
    }
    const modelo = editor.getModel();
    if (!modelo) {
        janela = null;
        limpar(editor);
        return;
    }
    const total = modelo.getLineCount();
    const faixa = faixaPintada(editor, total);
    const primeira = faixa[0];
    const ultima = faixa[1];
    if (janela && janela.ficheiro === ficheiro && primeira >= janela.primeira && ultima <= janela.ultima) return;
    const separador = /\.tsv$/i.test(ficheiro) ? '\t' : ',';
    const novas = [];
    for (let numero = primeira; numero <= ultima; numero++) {
        const celulas = limitesDasCelulas(modelo.getLineContent(numero), separador);
        for (let coluna = 0; coluna < celulas.length; coluna++) {
            const inicio = celulas[coluna][0];
            const fim = celulas[coluna][1];
            if (fim <= inicio) continue;
            novas.push({
                range: new monaco.Range(numero, inicio + 1, numero, fim + 1),
                options: { inlineClassName: 'csv-col-' + (coluna % CORES) }
            });
        }
    }
    guardar(editor, novas);
    janela = { ficheiro: ficheiro, primeira: primeira, ultima: ultima };
}

function agendar(invalidar) {
    if (invalidar) janela = null;
    if (frame !== null) return;
    frame = requestAnimationFrame(function () {
        frame = null;
        pintar();
    });
}

export function instalarDestaqueCsv() {
    const editor = state.editor;
    if (!editor) return;
    editor.onDidChangeModel(function () { agendar(true); });
    editor.onDidChangeModelContent(function () { agendar(true); });
    editor.onDidScrollChange(function () { agendar(false); });
    agendar(true);
}
