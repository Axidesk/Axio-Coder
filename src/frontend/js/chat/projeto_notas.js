import * as dom from './dom.js';
import { state } from './state.js';
import { state as estadoEditor } from '../editor/state.js';
import { ordenarPorChaves, tornarAbasArrastaveis } from '../editor/arrastar_abas.js';
import { showAlert } from './ui.js';
import { criarVista } from './colunas.js';
import { syncDocTopBar } from './layout.js';
import { defineEditorTheme } from '../editor/themes.js';
import { opcoesBase, PADDING_TOPO } from '../editor/metricas.js';
import { ensureMonacoReady } from '../editor/workspace.js';

const ESPERA_GRAVACAO = 700;

const AVISO_ERRO = 'Não foi possível ler as notas do projeto.';
const AVISO_VAZIO_PADRAO = 'Escreva aqui as suas anotações...';

const AVISO_VAZIO = dom.projectNotesPlaceholder ? dom.projectNotesPlaceholder.textContent : AVISO_VAZIO_PADRAO;

const SVG_FECHAR = '<svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

let editorNotas = null;
let vigiaNotas = null;
let montando = false;
let leituraOk = false;
let gravacaoPendente = false;
let relogioGravacao = null;
let aAplicarLeitura = false;
let criarDepoisDeCarregar = false;
let modeloVazio = null;

let abas = [];
let ativaId = null;
const vistasPorAba = new Map();
const notasFechadas = [];

function _mostrarAviso(texto) {
    if (!dom.projectNotesPlaceholder) return;
    dom.projectNotesPlaceholder.textContent = texto;
    dom.projectNotesPlaceholder.classList.add('visivel');
}

function _atualizarAviso() {
    if (!dom.projectNotesPlaceholder || !editorNotas) return;
    const modelo = editorNotas.getModel();
    if (!modelo || modelo.getValue().trim() === '') _mostrarAviso(AVISO_VAZIO);
    else dom.projectNotesPlaceholder.classList.remove('visivel');
}

function _documento() {
    return {
        abas: abas.map(function (aba) {
            return {
                id: aba.id,
                titulo: aba.titulo,
                texto: aba.modelo ? aba.modelo.getValue() : ''
            };
        }),
        ativa: ativaId
    };
}

function _agendarGravacao() {
    if (!leituraOk || !editorNotas) return;
    gravacaoPendente = true;
    if (relogioGravacao) clearTimeout(relogioGravacao);
    relogioGravacao = setTimeout(_gravarAgora, ESPERA_GRAVACAO);
}

function _gravarAgora() {
    if (relogioGravacao) {
        clearTimeout(relogioGravacao);
        relogioGravacao = null;
    }
    if (!gravacaoPendente || !editorNotas) return;
    gravacaoPendente = false;
    _enviarNotas(_documento());
}

function _aoEscrever() {
    _atualizarAviso();
    if (aAplicarLeitura) return;
    _agendarGravacao();
}

function _idsUsados() {
    return new Set(abas.map(function (aba) { return aba.id; }));
}

function _idNovo() {
    let ident = 'n' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    while (_idsUsados().has(ident)) ident += 'x';
    return ident;
}

function _novaAba(titulo, texto) {
    return {
        id: _idNovo(),
        titulo: titulo,
        modelo: estadoEditor.monaco.editor.createModel(String(texto || ''), 'markdown')
    };
}

function _proximoNumero() {
    let maior = 0;
    abas.forEach(function (aba) {
        const casa = /^Nota\s+(\d+)$/.exec(aba.titulo || '');
        if (casa) maior = Math.max(maior, parseInt(casa[1], 10));
    });
    return Math.max(maior + 1, abas.length + 1);
}

function _renderAbas() {
    if (!dom.projectNotesTabs) return;
    dom.projectNotesTabs.innerHTML = '';
    abas.forEach(function (aba) {
        const alvo = document.createElement('div');
        alvo.className = 'editor-tab' + (aba.id === ativaId ? ' editor-tab-active' : '');
        alvo.dataset.id = aba.id;
        alvo.title = aba.titulo;
        const nome = document.createElement('span');
        nome.className = 'editor-tab-name';
        nome.textContent = aba.titulo;
        const fechar = document.createElement('button');
        fechar.className = 'editor-tab-close';
        fechar.title = 'Excluir nota';
        fechar.innerHTML = SVG_FECHAR;
        alvo.appendChild(nome);
        alvo.appendChild(fechar);
        alvo.addEventListener('click', function (e) {
            if (e.target.closest('.editor-tab-close') || aba.id === ativaId) return;
            _ativarAba(aba.id, true);
        });
        alvo.addEventListener('dblclick', function () { _renomearAba(aba, alvo, nome); });
        alvo.addEventListener('contextmenu', function (e) {
            e.preventDefault();
            _abrirMenuNotas(e.clientX, e.clientY);
        });
        fechar.addEventListener('click', function (e) {
            e.stopPropagation();
            _fecharAba(aba.id);
        });
        dom.projectNotesTabs.appendChild(alvo);
    });
    tornarAbasArrastaveis(dom.projectNotesTabs, _reordenarAbas);
}

function _reordenarAbas(ordem) {
    ordenarPorChaves(abas, ordem, function (aba) { return aba.id; });
    _renderAbas();
    _agendarGravacao();
}

function _renomearAba(aba, alvo, nome) {
    if (!alvo || alvo.querySelector('input')) return;
    const input = document.createElement('input');
    input.className = 'editor-tab-rename';
    input.value = aba.titulo;
    input.spellcheck = false;
    input.addEventListener('click', function (e) { e.stopPropagation(); });
    input.addEventListener('dblclick', function (e) { e.stopPropagation(); });
    nome.replaceWith(input);
    input.focus();
    input.select();
    let terminado = false;
    const terminar = function (gravar) {
        if (terminado) return;
        terminado = true;
        const novo = input.value.replace(/\s+/g, ' ').trim();
        if (gravar && novo && novo !== aba.titulo) {
            aba.titulo = novo;
            _agendarGravacao();
        }
        _renderAbas();
    };
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            terminar(true);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            terminar(false);
        }
    });
    input.addEventListener('blur', function () { terminar(true); });
}

function _abrirMenuNotas(x, y) {
    if (!dom.notesContextMenu) return;
    if (dom.btnNotesReopen) dom.btnNotesReopen.disabled = !notasFechadas.length;
    dom.notesContextMenu.style.left = Math.max(8, Math.min(x, window.innerWidth - 220)) + 'px';
    dom.notesContextMenu.style.top = Math.max(8, Math.min(y, window.innerHeight - 70)) + 'px';
    dom.notesContextMenu.classList.add('menu-open');
}

function _fecharMenuNotas() {
    if (dom.notesContextMenu) dom.notesContextMenu.classList.remove('menu-open');
}

function _ativarAba(id, focar) {
    if (!editorNotas) return;
    const alvo = abas.find(function (aba) { return aba.id === id; }) || abas[0];
    if (!alvo) return;
    if (ativaId && ativaId !== alvo.id && editorNotas.getModel()) {
        vistasPorAba.set(ativaId, editorNotas.saveViewState());
    }
    ativaId = alvo.id;
    if (editorNotas.getModel() !== alvo.modelo) editorNotas.setModel(alvo.modelo);
    const vista = vistasPorAba.get(alvo.id);
    if (vista) editorNotas.restoreViewState(vista);
    _renderAbas();
    _atualizarAviso();
    if (focar) editorNotas.focus();
}

export function criarNota() {
    if (!editorNotas) {
        criarDepoisDeCarregar = true;
        _montarEditor();
        return;
    }
    const nova = _novaAba('Nota ' + _proximoNumero(), '');
    abas.push(nova);
    _ativarAba(nova.id, true);
    _agendarGravacao();
}

function _fecharAba(id) {
    const indice = abas.findIndex(function (aba) { return aba.id === id; });
    if (indice < 0) return;
    const fora = abas[indice];
    abas.splice(indice, 1);
    vistasPorAba.delete(id);
    _guardarFechada(fora);
    if (!abas.length) {
        abas.push(_novaAba('Nota 1', ''));
        _ativarAba(abas[0].id, false);
    } else if (ativaId === id) {
        _ativarAba(abas[Math.min(indice, abas.length - 1)].id, false);
    }
    const modeloAtual = editorNotas ? editorNotas.getModel() : null;
    if (fora.modelo && fora.modelo !== modeloAtual) fora.modelo.dispose();
    _renderAbas();
    _atualizarAviso();
    _agendarGravacao();
    if (editorNotas) editorNotas.focus();
}

function _guardarFechada(aba) {
    notasFechadas.push({
        titulo: aba.titulo,
        texto: aba.modelo ? aba.modelo.getValue() : ''
    });
}

function reabrirNotaFechada() {
    const guardada = notasFechadas.pop();
    if (!guardada) return;
    const nova = _novaAba(guardada.titulo, guardada.texto);
    abas.push(nova);
    _ativarAba(nova.id, true);
    _agendarGravacao();
}

const ESPERA_TRADUCAO = 700;

export async function traduzirNota() {
    if (!editorNotas || !leituraOk || !dom.btnNotesWand || dom.btnNotesWand.disabled) return;
    const modelo = editorNotas.getModel();
    if (!modelo) return;
    let intervalo = editorNotas.getSelection();
    if (!intervalo || intervalo.isEmpty()) intervalo = modelo.getFullModelRange();
    const texto = modelo.getValueInRange(intervalo);
    if (!texto.trim()) return;
    _varinhaATrabalhar(true);
    try {
        const resp = await fetch('/api/projeto/traduzir', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                texto: texto,
                use_deepseek: state.selectedModel === 'deepseek'
            })
        });
        const dados = await resp.json().catch(function () { return null; });
        if (!resp.ok || !dados) {
            showAlert((dados && dados.erro) || 'Não foi possível traduzir a nota.');
            return;
        }
        const traduzido = await _esperarTraducao();
        if (!traduzido) {
            showAlert('Não foi possível traduzir a nota.');
            return;
        }
        editorNotas.executeEdits('traducao', [{ range: intervalo, text: traduzido }]);
        editorNotas.pushUndoStop();
        editorNotas.focus();
    } catch (e) {
        showAlert((e && e.message) || 'Não foi possível traduzir a nota.');
    } finally {
        _varinhaATrabalhar(false);
    }
}

function _varinhaATrabalhar(ativo) {
    if (dom.btnNotesWand) {
        dom.btnNotesWand.disabled = ativo;
        dom.btnNotesWand.classList.toggle('a-trabalhar', ativo);
    }
}

function _esperar(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function _esperarTraducao() {
    while (true) {
        await _esperar(ESPERA_TRADUCAO);
        let dados = null;
        try {
            const resp = await fetch('/api/projeto/traducao');
            dados = await resp.json().catch(function () { return null; });
        } catch (e) {
            return null;
        }
        if (!dados) return null;
        if (dados.estado === 'pronto') return dados.texto;
        if (dados.estado === 'erro') throw new Error(dados.erro || '');
    }
}

function _montarEditor() {
    if (editorNotas || montando || !dom.projectNotesEditor) return;
    montando = true;
    ensureMonacoReady(function () {
        montando = false;
        if (editorNotas || !dom.projectNotesEditor) return;
        defineEditorTheme();
        editorNotas = estadoEditor.monaco.editor.create(dom.projectNotesEditor, Object.assign(opcoesBase(), {
            value: '',
            language: 'markdown',
            theme: 'axio-editor',
            automaticLayout: false,
            lineNumbers: 'off',
            glyphMargin: false,
            folding: false,
            lineDecorationsWidth: 0,
            overviewRulerLanes: 0,
            overviewRulerBorder: false,
            hideCursorInOverviewRuler: true,
            padding: { top: PADDING_TOPO, bottom: PADDING_TOPO },
            wordWrap: 'on',
            wrappingIndent: 'same',
            quickSuggestions: false,
            suggestOnTriggerCharacters: false,
            wordBasedSuggestions: 'off',
            occurrencesHighlight: 'off'
        }));
        modeloVazio = editorNotas.getModel();
        editorNotas.onDidChangeModelContent(_aoEscrever);
        editorNotas.layout();
        _vigiarLayoutDoEditor();
        _carregarNotas();
    });
}

function _vigiarLayoutDoEditor() {
    if (vigiaNotas || !editorNotas || !dom.projectNotesEditor) return;
    const ajustar = function () {
        if (editorNotas && vistaNotas.col3Aberta()) editorNotas.layout();
    };
    if (typeof ResizeObserver !== 'undefined') {
        vigiaNotas = new ResizeObserver(ajustar);
        vigiaNotas.observe(dom.projectNotesEditor);
    } else {
        vigiaNotas = window;
        window.addEventListener('resize', ajustar);
    }
}

const vistaNotas = criarVista({
    id: 'notas',
    col3: dom.panelCol3Notes,
    abrirCol3() {
        if (window.WorkspaceView && typeof window.WorkspaceView.showEditor === 'function') {
            window.WorkspaceView.showEditor();
        }
        if (dom.panelCol3Notes) dom.panelCol3Notes.classList.remove('panel-col-closed');
        syncDocTopBar();
    },
    fecharCol3() {
        if (dom.panelCol3Notes) dom.panelCol3Notes.classList.add('panel-col-closed');
    }
});

vistaNotas.aoFecharCol3 = function () {
    _gravarAgora();
    _sincronizarBotaoNotas();
    _fecharMenuNotas();
    syncDocTopBar();
};

function _sincronizarBotaoNotas() {
    if (dom.btnProjectNotes) dom.btnProjectNotes.classList.toggle('ativo', vistaNotas.col3Aberta());
}

export function alternarCamadaNotas() {
    if (vistaNotas.col3Aberta()) {
        vistaNotas.fecharCol3();
        return;
    }
    vistaNotas.abrirCol3();
    _sincronizarBotaoNotas();
    if (editorNotas) {
        if (!leituraOk) _carregarNotas();
        _renderAbas();
    } else {
        _mostrarAviso(AVISO_VAZIO);
        _montarEditor();
    }
    if (!editorNotas) return;
    editorNotas.layout();
    editorNotas.focus();
}

async function _carregarNotas() {
    const doc = await _pedirNotas();
    if (!doc) {
        leituraOk = false;
        _mostrarAviso(AVISO_ERRO);
        return;
    }
    leituraOk = true;
    _aplicarDocumento(doc);
    if (criarDepoisDeCarregar) {
        criarDepoisDeCarregar = false;
        criarNota();
    }
}

function _aplicarDocumento(doc) {
    const lista = Array.isArray(doc.abas) ? doc.abas : [];
    const antigas = abas;
    abas = lista.map(function (item) {
        return {
            id: String((item && item.id) || ''),
            titulo: String((item && item.titulo) || '').trim() || 'Nota',
            modelo: estadoEditor.monaco.editor.createModel(String((item && item.texto) || ''), 'markdown')
        };
    });
    if (!abas.length) abas = [_novaAba('Nota 1', '')];
    const vistos = new Set();
    abas.forEach(function (aba) {
        if (!aba.id || vistos.has(aba.id)) aba.id = _idNovo();
        vistos.add(aba.id);
    });
    vistasPorAba.clear();
    _ativarAba(String(doc.ativa || ''), false);
    const modeloAtual = editorNotas ? editorNotas.getModel() : null;
    [modeloVazio].concat(antigas.map(function (aba) { return aba.modelo; })).forEach(function (modelo) {
        if (modelo && modelo !== modeloAtual) modelo.dispose();
    });
    modeloVazio = null;
}

async function _pedirNotas() {
    try {
        const resp = await fetch('/api/projeto/notas');
        if (!resp.ok) return null;
        const dados = await resp.json();
        return dados && typeof dados === 'object' ? dados : null;
    } catch (e) {
        return null;
    }
}

async function _enviarNotas(documento) {
    try {
        const resp = await fetch('/api/projeto/notas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(documento)
        });
        if (!resp.ok) gravacaoPendente = true;
    } catch (e) {
        gravacaoPendente = true;
    }
}

if (dom.notesContextMenu) {
    dom.notesContextMenu.addEventListener('click', function (e) {
        e.stopPropagation();
        _fecharMenuNotas();
        reabrirNotaFechada();
    });
}
document.addEventListener('click', _fecharMenuNotas);
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') _fecharMenuNotas();
});

window.addEventListener('resize', function () {
    if (editorNotas) editorNotas.layout();
});

window.addEventListener('beforeunload', function () {
    if (!editorNotas || !gravacaoPendente || !navigator.sendBeacon) return;
    const dados = JSON.stringify(_documento());
    navigator.sendBeacon('/api/projeto/notas', new Blob([dados], { type: 'application/json' }));
});
