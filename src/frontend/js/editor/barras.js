import { state } from './state.js';

const CLASSE = 'editor-barras-acesas';

let iniciado = false;
let agendado = false;
let pendente = null;
let ultimoPonto = null;

function hosts() {
    return [state.editorHost, state.diffHost].filter(Boolean);
}

function dentroDe(host, x, y) {
    const area = host.getBoundingClientRect();
    return x >= area.left && x <= area.right && y >= area.top && y <= area.bottom;
}

function aplicar(ponto) {
    ultimoPonto = ponto;
    hosts().forEach((h) => h.classList.toggle(CLASSE, dentroDe(h, ponto[0], ponto[1])));
}

function apagar() {
    hosts().forEach((h) => h.classList.toggle(CLASSE, false));
}

function agendar(x, y) {
    pendente = [x, y];
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => {
        agendado = false;
        const ponto = pendente;
        pendente = null;
        if (ponto) aplicar(ponto);
    });
}

function seguir(ev) {
    agendar(ev.clientX, ev.clientY);
}

export function iniciarBarrasDoEditor() {
    if (iniciado) return;
    iniciado = true;
    document.addEventListener('mousemove', seguir, { passive: true });
    document.addEventListener('mouseover', (ev) => {
        if (ev.target && ev.target.closest && ev.target.closest('#editor-host, #diff-host')) seguir(ev);
    }, { passive: true });
    const observador = new ResizeObserver(reavaliarBarrasDoEditor);
    hosts().forEach((h) => {
        h.addEventListener('mouseleave', apagar);
        observador.observe(h);
    });
    window.addEventListener('resize', reavaliarBarrasDoEditor, { passive: true });
    window.addEventListener('focus', reavaliarBarrasDoEditor, { passive: true });
}

export function reavaliarBarrasDoEditor() {
    if (ultimoPonto) aplicar(ultimoPonto);
}
