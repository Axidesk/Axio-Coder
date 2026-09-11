import { loadVenvName } from './workspace.js';
import { loadExplorer } from './explorer.js';
import { state } from './state.js';
import { termClear, termFit, termGetSelection, termOnResize, termWrite, termWriteLine } from './xterm.js';
import { copiarTexto } from '../chat/clipboard.js';
import { colarNoInputText } from '../chat/inspect.js';

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
    termWriteLine(text == null || text === '' ? ' ' : text, cls);
}
export function clearLog() {
    if (state.termSocket && state.termSocket.connected) {
        state.termSocket.emit('pty:input', { data: comandoLimparTerminal() + '\n' });
    }
    termClear();
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
    });
    state.termSocket.on('pty:output', (msg) => {
        if (!msg || msg.data == null) return;
        termWrite(msg.data);
        marcarAtividadeTerminal();
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
    const shell = (state.wsShellLabel && state.wsShellLabel.textContent) || 'cmd';
    const q = quotePath(path);
    return shell === 'cmd' ? 'cd /d ' + q : 'cd ' + q;
}
function comandoLimparTerminal() {
    const shell = (state.wsShellLabel && state.wsShellLabel.textContent) || 'cmd';
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
function tratarAtalhoTerminal(ev) {
    if (!(ev.ctrlKey || ev.metaKey) || ev.altKey) return;
    const tecla = teclaDeAtalho(ev);
    if (!tecla) return;
    if (tecla === 'c') {
        if (focoForaDoTerminal()) return;
        const selecao = termGetSelection();
        if (!selecao) return;
        copiarTexto(selecao);
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
export function updateExplorerPath(data) {
    if (!state.explorerPath) return;
    const segs = buildExplorerSegments(data);
    state.explorerPath.innerHTML = '';
    segs.forEach((seg, i) => {
        const isLast = i === segs.length - 1;
        const span = document.createElement('span');
        span.className = 'explorer-crumb' + (isLast ? ' active' : '');
        span.textContent = (i === 0 && data.dentro_da_raiz ? '\\' : '') + seg.label;
        span.title = seg.abs;
        span.addEventListener('click', (e) => {
            e.stopPropagation();
            handleCrumbClick(seg, isLast, data);
        });
        state.explorerPath.appendChild(span);
        if (!isLast) {
            const sep = document.createElement('span');
            sep.className = 'explorer-crumb-sep';
            sep.textContent = '\\';
            state.explorerPath.appendChild(sep);
        }
    });
    state.explorerPath.title = segs.map((s, i) => (i === 0 && data.dentro_da_raiz ? '\\' : '') + s.label).join('\\');
}
export function changeTerminalCwd(pathArg) {
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
        return loadExplorer();
    }).catch(e => {
        appendLine('[explorer] erro: ' + e.message, 'term-err');
        return null;
    });
}
export function isAbsolutePath(p) {
    return /^[a-zA-Z]:[\\/]/.test(String(p || '')) || String(p || '').startsWith('/');
}
export function enterDir(relPath) {
    const abs = isAbsolutePath(relPath) ? relPath : (relPath ? joinPath(state.rootPath, relPath) : state.rootPath);
    return changeTerminalCwd(abs);
}
export function loadShellInfo() {
    fetch(state.API + '/api/terminal/shells')
        .then(r => r.json())
        .then(data => {
            if (!data || !Array.isArray(data.shells)) return;
            if (state.wsShellLabel) state.wsShellLabel.textContent = data.atual || 'cmd';
            if (state.wsShellMenu) {
                state.wsShellMenu.innerHTML = '';
                data.shells.forEach(s => {
                    if (s.nome === data.atual) return;
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'ws-shell-item';
                    btn.textContent = s.nome;
                    btn.addEventListener('click', () => setTerminalShell(s.nome));
                    state.wsShellMenu.appendChild(btn);
                });
            }
        })
        .catch(() => {});
}
export function setTerminalShell(shell) {
    closeShellMenu();
    fetch(state.API + '/api/terminal/shell', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shell: shell })
    }).then(r => r.json()).then(data => {
        if (data && data.atual && state.wsShellLabel) state.wsShellLabel.textContent = data.atual;
        if (state.termSocket) state.termSocket.emit('pty:restart');
        loadShellInfo();
    }).catch(() => {});
}
export function openShellMenu() {
    state.shellMenuOpen = true;
    if (state.wsShellMenu) state.wsShellMenu.classList.add('expanded');
    if (state.wsShellArrow) state.wsShellArrow.textContent = '<';
    if (state.wsShellLabel) state.wsShellLabel.classList.add('menu-open');
    loadShellInfo();
}
export function closeShellMenu() {
    state.shellMenuOpen = false;
    if (state.wsShellMenu) state.wsShellMenu.classList.remove('expanded');
    if (state.wsShellArrow) state.wsShellArrow.textContent = '>';
    if (state.wsShellLabel) state.wsShellLabel.classList.remove('menu-open');
}
export function toggleShellMenu() {
    if (state.shellMenuOpen) closeShellMenu(); else openShellMenu();
}
if (state.btnClear) {
    state.btnClear.addEventListener('click', clearLog);
}
ligarClipboardTerminal();
