import { state } from './state.js';

const URL_XTERM = state.API + '/xterm/xterm/lib/xterm.mjs';
const URL_FIT = state.API + '/xterm/addon-fit/lib/addon-fit.mjs';
const URL_WEBGL = state.API + '/xterm/addon-webgl/lib/addon-webgl.mjs';

let term = null;
let fitAddon = null;
let webglAddon = null;
let inicializando = null;
let pendente = [];
let aoRedimensionar = null;

function lerToken(nome, fallback) {
    const valor = getComputedStyle(document.documentElement).getPropertyValue(nome);
    return (valor || '').trim() || fallback;
}

function corDeFundoTerminal() {
    let node = state.termLog;
    while (node) {
        const cor = (getComputedStyle(node).backgroundColor || '').trim();
        if (cor && cor !== 'transparent' && !/,\s*0\s*\)$/.test(cor)) return cor;
        node = node.parentElement;
    }
    return lerToken('--bg-panel', '#1e1e1e');
}

function temaTerminal() {
    return {
        background: corDeFundoTerminal(),
        foreground: lerToken('--text-corpo', '#d4d4d4'),
        cursor: corDeFundoTerminal(),
        cursorAccent: lerToken('--text-corpo', '#d4d4d4'),
        selectionBackground: 'rgba(255, 255, 255, 0.18)',
        black: lerToken('--bg', '#121212'),
        red: lerToken('--perigo', '#f43f5e'),
        green: lerToken('--terminal', '#82c953'),
        yellow: lerToken('--alerta', '#e8b339'),
        blue: lerToken('--info', '#0ea5e9'),
        magenta: lerToken('--oliva', '#90a015'),
        cyan: lerToken('--info', '#0ea5e9'),
        white: lerToken('--text-claro', '#d1d5db'),
        brightBlack: lerToken('--text-mutado', '#6b7280'),
        brightRed: lerToken('--perigo', '#f43f5e'),
        brightGreen: lerToken('--oliva-claro', '#b4c828'),
        brightYellow: lerToken('--alerta', '#e8b339'),
        brightWhite: lerToken('--text-branco', '#ffffff')
    };
}

function opcoesWindowsPty() {
    try {
        const partes = String(require('os').release() || '').split('.');
        const build = parseInt(partes[2], 10);
        if (build > 0) return { backend: 'conpty', buildNumber: build };
    } catch (e) {}
    return undefined;
}

function ajustar() {
    if (!fitAddon || !state.termLog) return;
    if (state.termLog.offsetWidth === 0 || state.termLog.offsetHeight === 0) return;
    try {
        fitAddon.fit();
    } catch (e) {}
}

function notificarTamanho(cols, rows) {
    if (!aoRedimensionar || !term) return;
    aoRedimensionar(cols || term.cols, rows || term.rows);
}

export function termOnResize(cb) {
    aoRedimensionar = cb;
}

function ligarFadeDoRodape() {
    const viewport = state.termLog.querySelector('.xterm-viewport');
    if (!viewport) return;
    viewport.addEventListener('scroll', () => {
        const atual = viewport.scrollTop;
        const noFim = viewport.scrollHeight - atual - viewport.clientHeight <= 50;
        if (atual > state.termLastScrollTop || noFim) {
            state.termInputFooter.style.opacity = '1';
            state.termInputFooterInner.style.pointerEvents = 'auto';
        } else {
            state.termInputFooter.style.opacity = '0';
            state.termInputFooterInner.style.pointerEvents = 'none';
        }
        state.termLastScrollTop = atual;
    });
}

function vigiarVisibilidade() {
    if (state.xtermVigia) return;
    const alvo = state.termLog;
    if (!alvo) return;
    if (typeof ResizeObserver !== 'undefined') {
        state.xtermVigia = new ResizeObserver(() => {
            ensureTerminal();
            ajustar();
        });
        state.xtermVigia.observe(alvo);
    } else {
        state.xtermVigia = window;
        window.addEventListener('resize', () => {
            ensureTerminal();
            ajustar();
        });
    }
}

async function carregarRenderizadorWebgl(terminal) {
    try {
        const mod = await import(URL_WEBGL);
        webglAddon = new mod.WebglAddon();
        webglAddon.onContextLoss(() => {
            if (webglAddon) webglAddon.dispose();
            webglAddon = null;
        });
        terminal.loadAddon(webglAddon);
    } catch (e) {
        webglAddon = null;
    }
}

async function criarTerminal() {
    const [modXterm, modFit] = await Promise.all([import(URL_XTERM), import(URL_FIT)]);
    term = new modXterm.Terminal({
        allowTransparency: false,
        cursorBlink: false,
        convertEol: true,
        disableStdin: true,
        cursorInactiveStyle: 'none',
        windowsPty: opcoesWindowsPty(),
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        fontSize: 13,
        lineHeight: 1.2,
        scrollback: 5000,
        smoothScrollDuration: 125,
        theme: temaTerminal()
    });
    fitAddon = new modFit.FitAddon();
    term.loadAddon(fitAddon);
    term.onResize(({ cols, rows }) => notificarTamanho(cols, rows));
    term.open(state.termLog);
    carregarRenderizadorWebgl(term);
    state.xterm = term;
    state.xtermFit = fitAddon;
    ajustar();
    ligarFadeDoRodape();
    const enfileirado = pendente;
    pendente = [];
    enfileirado.forEach((texto) => term.write(texto));
    return term;
}

export function ensureTerminal() {
    if (term) return Promise.resolve(term);
    if (inicializando) return inicializando;
    if (!state.termLog || state.termLog.offsetHeight === 0) return Promise.resolve(null);
    inicializando = criarTerminal().catch((erro) => {
        inicializando = null;
        if (state.wsStatus) state.wsStatus.textContent = 'erro no terminal';
        console.error('[xterm] falha ao carregar', erro);
        return null;
    });
    return inicializando;
}

export function termWrite(texto) {
    if (!texto) return;
    if (!term) {
        pendente.push(texto);
        ensureTerminal();
        return;
    }
    term.write(texto);
}

export function termGetSelection() {
    return term ? (term.getSelection() || '') : '';
}

export function termClear() {
    pendente = [];
    if (term) term.write('\x1b[2J\x1b[3J\x1b[H');
}

export function termFit() {
    ensureTerminal().then(() => {
        ajustar();
        notificarTamanho();
    });
}

vigiarVisibilidade();
