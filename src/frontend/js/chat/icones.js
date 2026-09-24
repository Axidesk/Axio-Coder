export const SVG_OLHO = '<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';

export const SVG_OLHO_RISCADO = '<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

function icone(caminhos, classe) {
    return '<svg xmlns="http://www.w3.org/2000/svg" class="' + classe + '" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + caminhos + '</svg>';
}

const CAMINHOS_DO_PONTO = '<path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/>';
const CAMINHOS_DO_AVIAO = '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>';
const CAMINHOS_DO_RESTAURO = '<path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>';

export function svgDoPonto(classe) {
    return icone(CAMINHOS_DO_PONTO, classe);
}

export function svgDoAviao(classe) {
    return icone(CAMINHOS_DO_AVIAO, classe);
}

export function svgDoRestauro(classe) {
    return icone(CAMINHOS_DO_RESTAURO, classe);
}
