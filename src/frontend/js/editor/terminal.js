import { loadVenvName } from './workspace.js';
import { loadExplorer } from './explorer.js';
import { state } from './state.js';
import { termClear, termFit, termGetSelection, termOnResize, termWrite } from './xterm.js';
import { copiarTexto } from '../chat/clipboard.js';
import { colarNoInputText } from '../chat/inspect.js';
import { aviso, descartarSelecao, limparCards } from './terminal_cards.js';
import { pontosDeParagem } from './pontos_paragem.js';

let termStatusTimer = null;

function marcarAtividadeTerminal() {
    if (state.wsStatus) state.wsStatus.textContent = 'executando...';
    if (termStatusTimer) clearTimeout(termStatusTimer);
    termStatusTimer = setTimeout(() => {
        if (state.wsStatus) state.wsStatus.textContent = 'pronto';
        loadVenvName();
    }, 400);
}

export function appendLine(text, cls) {
    aviso(text == null || text === '' ? ' ' : text, cls);
}
export function clearLog() {
    if (state.termSocket && state.termSocket.connected) {
        state.termSocket.emit('pty:input', { data: comandoLimparTerminal() + '\n' });
    }
    termClear();
    limparCards();
}

let termPtyTimer = null;
let termPtyCols = 0;
let termPtyRows = 0;
function enviarTamanhoPty(cols, rows) {
    if (!state.termSocket || !state.termSocket.connected) return;
    if (cols === termPtyCols && rows === termPtyRows) return;
    termPtyCols = cols;
    termPtyRows = rows;
    if (termPtyTimer) clearTimeout(termPtyTimer);
    termPtyTimer = setTimeout(() => {
        if (state.termSocket && state.termSocket.connected) {
            state.termSocket.emit('pty:resize', { cols: cols, rows: rows });
        }
    }, 120);
}

export function connectTermSocket() {
    ligarClipboardTerminal();
    termOnResize(enviarTamanhoPty);
    if (typeof io === 'undefined') {
        appendLine('[socket.io nao carregado - reinicie o servidor]', 'term-err');
        return;
    }
    if (state.termSocket) return;
    state.termSocket = io(state.API, { transports: ['websocket', 'polling'] });
    state.termSocket.on('connect', () => {
        state.wsStatus.textContent = 'pronto';
        termPtyCols = 0;
        termPtyRows = 0;
        termFit();
        loadVenvName();
        loadShellInfo();
        state.termSocket.emit('pty:replay');
    });
    state.termSocket.on('pty:output', (msg) => {
        if (!msg || msg.data == null) return;
        termWrite(msg.data);
        marcarAtividadeTerminal();
    });
    state.termSocket.on('pty:session', (msg) => {
        termClear();
        if (msg && msg.shell) aplicarShellAtual(msg.shell);
    });
    state.termSocket.on('pty:replay', (msg) => {
        termClear();
        if (msg && msg.data) termWrite(msg.data);
    });
    state.termSocket.on('connect_error', () => {
        state.wsStatus.textContent = 'erro';
    });
    state.termSocket.on('disconnect', () => {
        state.wsStatus.textContent = 'desconectado';
    });
}
export function runCommand(cmd) {
    state.wsStatus.textContent = 'executando...';
    const trimmed = cmd.trim();
    const isCd = /^cd\b/i.test(trimmed);
    if (!isCd && state.termSocket && state.termSocket.connected) {
        state.termSocket.emit('pty:input', { data: cmd + '\n' });
    } else if (!isCd) {
        appendLine('[terminal nao conectado - reinicie o servidor]', 'term-err');
        state.wsStatus.textContent = 'erro';
    }
    if (isCd) {
        let target = '~';
        if (!/^cd\s*$/i.test(trimmed)) {
            const cdMatch = trimmed.match(/^cd\s*(?:\/d\s+)?(.*)$/i);
            const parsed = (cdMatch && cdMatch[1] || '').trim().replace(/^["']|["']$/g, '');
            if (parsed) target = parsed;
        }
        changeTerminalCwd(target);
    }
    loadVenvName();
}
export function basename(p) {
    const parts = String(p || '').split(/[\\/]/);
    return parts[parts.length - 1] || p;
}
export function joinPath(base, rel) {
    const sep = String(base).includes('\\') ? '\\' : '/';
    return String(base).replace(/[\\/]+$/, '') + sep + String(rel || '');
}
export function quotePath(p) {
    const s = String(p || '');
    return /\s/.test(s) ? '"' + s + '"' : s;
}
export function cdCommandFor(path) {
    const shell = state.shellAtual || 'cmd';
    const q = quotePath(path);
    return shell === 'cmd' ? 'cd /d ' + q : 'cd ' + q;
}
function comandoLimparTerminal() {
    const shell = state.shellAtual || 'cmd';
    if (shell === 'cmd' || shell === 'powershell' || shell === 'pwsh') return 'cls';
    return 'clear';
}
function terminalEmFoco() {
    return !!(state.termLog && state.termLog.contains(document.activeElement));
}
function focoForaDoTerminal() {
    const ativo = document.activeElement;
    if (!ativo || ativo === document.body) return false;
    if (ativo.classList && ativo.classList.contains('xterm-helper-textarea')) return false;
    if (ativo.closest && ativo.closest('.monaco-editor')) return true;
    const tag = String(ativo.tagName || '').toLowerCase();
    if (tag !== 'input' && tag !== 'textarea') return false;
    try {
        return ativo.selectionStart !== ativo.selectionEnd;
    } catch (e) {
        return true;
    }
}
function teclaDeAtalho(ev) {
    const codigo = String(ev.code || '');
    if (codigo === 'KeyC') return 'c';
    if (codigo === 'KeyV') return 'v';
    const nome = String(ev.key || '').toLowerCase();
    return nome === 'c' || nome === 'v' ? nome : '';
}
function focarTerminal() {
    if (!state.termLog) return;
    const campo = state.termLog.querySelector('.xterm-helper-textarea');
    if (campo && document.activeElement !== campo) campo.focus();
}
function colarNoTerminal() {
    try {
        const texto = require('electron').clipboard.readText() || '';
        if (texto) colarNoInputText(texto);
    } catch (e) {}
}
function interromperShell() {
    if (state.termSocket && state.termSocket.connected) {
        state.termSocket.emit('pty:input', { data: '\x03' });
    }
}
function tratarAtalhoTerminal(ev) {
    if (!(ev.ctrlKey || ev.metaKey) || ev.altKey) return;
    const tecla = teclaDeAtalho(ev);
    if (!tecla) return;
    if (tecla === 'c') {
        if (focoForaDoTerminal()) return;
        const selecao = termGetSelection();
        if (!selecao && !state.shellAtivo) return;
        if (selecao) copiarTexto(selecao);
        else interromperShell();
        ev.preventDefault();
        ev.stopPropagation();
    } else if (tecla === 'v') {
        if (!terminalEmFoco()) return;
        colarNoTerminal();
        ev.preventDefault();
        ev.stopPropagation();
    }
}
let clipboardLigado = false;
let focoTerminalLigado = false;
function ligarClipboardTerminal() {
    if (!focoTerminalLigado && state.termLog) {
        focoTerminalLigado = true;
        state.termLog.addEventListener('mousedown', focarTerminal);
    }
    if (clipboardLigado) return;
    clipboardLigado = true;
    document.addEventListener('keydown', tratarAtalhoTerminal, true);
}
export function buildExplorerSegments(data) {
    const root = (data && data.root) || '';
    const raizNome = (data && data.raiz_nome) || basename(root);
    if (!(data && data.dentro_da_raiz) || !root) {
        const cwd = (data && data.cwd) || root;
        return [{ label: cwd || 'raiz', abs: cwd || root }];
    }
    let rel = ((data && data.relativo) || '').replace(/\//g, '\\');
    if (rel === '.') rel = '';
    const parts = rel ? rel.split('\\').filter(Boolean) : [];
    const segments = [];
    segments.push({ label: raizNome || 'raiz', abs: root });
    let acc = root;
    parts.forEach(p => {
        acc = joinPath(acc, p);
        segments.push({ label: p, abs: acc });
    });
    return segments;
}
export function handleCrumbClick(seg, isLast, data) {
    const root = (data && data.root) || '';
    if (seg.abs === root && isLast) {
        try {
            const { shell } = require('electron');
            shell.openPath(root || seg.abs);
        } catch (e) {}
        return;
    }
    changeTerminalCwd(seg.abs);
}
const CLASSE_RETICENCIA = 'explorer-crumb-elipse';
let observadorDoCaminho = null;

export function pintarCaminho(itens) {
    if (!state.explorerPath) return;
    const lista = itens || [];
    state.explorerPath.innerHTML = '';
    lista.forEach((item, i) => {
        const isLast = i === lista.length - 1;
        const span = document.createElement('span');
        span.className = 'explorer-crumb' + (isLast ? ' active' : '');
        span.textContent = item.texto;
        span.title = item.titulo || item.texto;
        if (typeof item.clicar === 'function') {
            span.addEventListener('click', (e) => {
                e.stopPropagation();
                item.clicar();
            });
        }
        state.explorerPath.appendChild(span);
        if (!isLast) {
            const sep = document.createElement('span');
            sep.className = 'explorer-crumb-sep';
            sep.textContent = '\\';
            state.explorerPath.appendChild(sep);
        }
    });
    state.explorerPath.title = lista.map(item => item.titulo || item.texto).join('\\');
    garantirObservadorDoCaminho();
    ajustarRetcenciasDoCaminho();
}
function ocultarCrumb(crumb, oculto) {
    crumb.style.display = oculto ? 'none' : '';
    const vizinho = crumb.nextElementSibling;
    if (vizinho && vizinho.classList && vizinho.classList.contains('explorer-crumb-sep')) {
        vizinho.style.display = oculto ? 'none' : '';
    }
}
function ajustarRetcenciasDoCaminho() {
    const barra = state.explorerPath;
    if (!barra || !barra.querySelectorAll) return;
    const anterior = barra.querySelector('.' + CLASSE_RETICENCIA);
    if (anterior) anterior.remove();
    const crumbs = barra.querySelectorAll('.explorer-crumb');
    for (let i = 0; i < crumbs.length; i++) ocultarCrumb(crumbs[i], false);
    if (crumbs.length < 2 || !barra.clientWidth || barra.scrollWidth <= barra.clientWidth) return;
    const elipse = document.createElement('span');
    elipse.className = CLASSE_RETICENCIA;
    elipse.textContent = '…';
    barra.insertBefore(elipse, crumbs[0]);
    const escondidas = [];
    for (let i = 0; i < crumbs.length - 1 && barra.scrollWidth > barra.clientWidth; i++) {
        ocultarCrumb(crumbs[i], true);
        escondidas.push(crumbs[i].textContent);
    }
    if (!escondidas.length) {
        elipse.remove();
        return;
    }
    for (let i = 0; i < crumbs.length; i++) {
        if (crumbs[i].style.display === 'none') continue;
        const antes = crumbs[i].previousElementSibling;
        if (antes && antes.classList && antes.classList.contains('explorer-crumb-sep')) antes.style.display = '';
        break;
    }
    elipse.title = escondidas.join('\\');
}
function garantirObservadorDoCaminho() {
    if (observadorDoCaminho || !state.explorerPath || typeof ResizeObserver === 'undefined') return;
    observadorDoCaminho = new ResizeObserver(() => ajustarRetcenciasDoCaminho());
    observadorDoCaminho.observe(state.explorerPath);
}
export function updateExplorerPath(data) {
    if (!state.explorerPath || !data) return;
    const segs = buildExplorerSegments(data);
    pintarCaminho(segs.map((seg, i) => {
        const prefixo = i === 0 && data.dentro_da_raiz ? '\\' : '';
        return {
            texto: prefixo + seg.label,
            titulo: seg.abs || prefixo + seg.label,
            clicar: () => handleCrumbClick(seg, i === segs.length - 1, data)
        };
    }));
}
export function changeTerminalCwd(pathArg, recarregar = true) {
    return fetch(state.API + '/api/terminal/cwd', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathArg })
    }).then(r => r.json()).then(data => {
        if (data && data.error) {
            appendLine('[explorer] ' + data.error, 'term-err');
            return null;
        }
        if (state.termSocket && state.termSocket.connected) {
            const cdCmd = cdCommandFor(data.cwd);
            state.termSocket.emit('pty:input', { data: cdCmd + '\n' });
        }
        state.currentCwd = data.cwd || '';
        state.currentCwdRel = data.dentro_da_raiz ? (data.relativo === '.' ? '' : (data.relativo || '')) : (data.cwd || '');
        state.explorerNavigatedAt = Date.now();
        return recarregar ? loadExplorer() : data;
    }).catch(e => {
        appendLine('[explorer] erro: ' + e.message, 'term-err');
        return null;
    });
}
export function isAbsolutePath(p) {
    return /^[a-zA-Z]:[\\/]/.test(String(p || '')) || String(p || '').startsWith('/');
}
export function enterDir(relPath, recarregar = true) {
    const abs = isAbsolutePath(relPath) ? relPath : (relPath ? joinPath(state.rootPath, relPath) : state.rootPath);
    return changeTerminalCwd(abs, recarregar);
}
export function loadShellInfo() {
    fetch(state.API + '/api/terminal/shells')
        .then(r => r.json())
        .then(data => {
            if (!data || !Array.isArray(data.shells)) return;
            if (data.atual) state.shellAtual = data.atual;
            _renderModoTerminal();
            if (!state.wsShellMenu) return;
            state.wsShellMenu.innerHTML = '';
            data.shells.forEach(s => {
                const aceso = s.nome === state.shellAtual;
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'ws-shell-item' + (aceso ? ' active' : '');
                btn.textContent = s.nome;
                btn.title = aceso ? 'Escolhido' : 'Usar ' + s.nome;
                btn.addEventListener('click', () => setTerminalShell(s.nome));
                state.wsShellMenu.appendChild(btn);
            });
        })
        .catch(() => {});
}
export function setTerminalShell(shell) {
    closeShellMenu();
    const trocou = state.shellAtual !== shell;
    state.shellAtual = shell;
    ativarShell();
    if (!trocou) {
        loadShellInfo();
        return;
    }
    fetch(state.API + '/api/terminal/shell', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shell: shell })
    }).then(r => r.json()).then(data => {
        if (data && data.error) {
            aviso('[terminal] ' + data.error, 'term-err');
            desativarShell();
            loadShellInfo();
            return;
        }
        if (data && data.atual) state.shellAtual = data.atual;
        if (state.termSocket) state.termSocket.emit('pty:restart');
        _renderModoTerminal();
        loadShellInfo();
    }).catch(() => {
        desativarShell();
    });
}
export function openShellMenu() {
    state.shellMenuOpen = true;
    if (state.wsShellMenu) state.wsShellMenu.classList.add('expanded');
    if (state.wsShellArrow) {
        state.wsShellArrow.textContent = '<';
        state.wsShellArrow.classList.add('menu-open');
    }
    loadShellInfo();
}
export function closeShellMenu() {
    state.shellMenuOpen = false;
    if (state.wsShellMenu) state.wsShellMenu.classList.remove('expanded');
    if (state.wsShellArrow) {
        state.wsShellArrow.textContent = '>';
        state.wsShellArrow.classList.remove('menu-open');
    }
}
export function toggleShellMenu() {
    if (state.shellMenuOpen) closeShellMenu(); else openShellMenu();
}
function _renderModoTerminal() {
    if (state.wsShellLabel) {
        state.wsShellLabel.classList.toggle('aceso', state.shellAtivo);
        state.wsShellLabel.title = 'Sessao interativa (' + state.shellAtual + ')';
    }
    if (state.wsModoCards) {
        state.wsModoCards.classList.toggle('aceso', !state.shellAtivo);
    }
}
export function aplicarShellAtual(nome) {
    if (nome) state.shellAtual = nome;
    _renderModoTerminal();
}
export function ativarShell() {
    if (state.shellAtivo) return;
    state.shellAtivo = true;
    descartarSelecao();
    if (state.termMode) state.termMode.classList.add('shell-ativo');
    _renderModoTerminal();
    termFit();
}
export function desativarShell() {
    if (!state.shellAtivo) return;
    state.shellAtivo = false;
    if (state.termMode) state.termMode.classList.remove('shell-ativo');
    _renderModoTerminal();
    termFit();
}
export function depurarProjeto() {
    fetch(state.API + '/api/terminal/depurar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pontos: pontosDeParagem(), arquivo: state.currentFile || '' })
    }).then(r => r.json()).then(data => {
        if (data && data.error) aviso('[debug] ' + data.error, 'term-err');
    }).catch(() => aviso('[debug] nao consegui falar com o servidor.', 'term-err'));
}
if (state.btnDebug) {
    state.btnDebug.addEventListener('click', (e) => {
        e.stopPropagation();
        depurarProjeto();
    });
}
if (state.btnClear) {
    state.btnClear.addEventListener('click', clearLog);
}
if (state.wsModoCards) {
    state.wsModoCards.addEventListener('click', (e) => {
        e.stopPropagation();
        closeShellMenu();
        desativarShell();
    });
}
if (state.wsShellLabel) {
    state.wsShellLabel.addEventListener('click', (e) => {
        e.stopPropagation();
        closeShellMenu();
        ativarShell();
    });
}
if (state.wsShellArrow) {
    state.wsShellArrow.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleShellMenu();
    });
}
document.addEventListener('click', (e) => {
    if (state.shellMenuOpen && !e.target.closest('#ws-shell')) closeShellMenu();
});
_renderModoTerminal();
ligarClipboardTerminal();
