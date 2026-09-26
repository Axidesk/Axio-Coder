import { state } from './state.js';

const CLASSE = 'editor-barras-acesas';

let iniciado = false;
let agendado = false;
let pendente = null;

function hosts() {
    return [state.editorHost, state.diffHost].filter(Boolean);
}

function aceso(ligar) {
    hosts().forEach((h) => h.classList.toggle(CLASSE, ligar));
}

function dentroDe(host, x, y) {
    const area = host.getBoundingClientRect();
    return x >= area.left && x <= area.right && y >= area.top && y <= area.bottom;
}

function avaliar(x, y) {
    aceso(hosts().some((h) => dentroDe(h, x, y)));
}

export function iniciarBarrasDoEditor() {
    if (iniciado) return;
    iniciado = true;
    document.addEventListener('mousemove', (ev) => {
        pendente = [ev.clientX, ev.clientY];
        if (agendado) return;
        agendado = true;
        requestAnimationFrame(() => {
            agendado = false;
            const ponto = pendente;
            pendente = null;
            if (ponto) avaliar(ponto[0], ponto[1]);
        });
    }, { passive: true });
}
