const ARGUMENTOS_VISIVEIS = 2;
const LIMITE_TEXTO = 600;
const LIMITE_ARGUMENTO = 70;
const EVENTOS_DE_FIM = new Set(['done', 'cancel', 'error']);

let ipcRenderer = null;
try {
    ipcRenderer = window.require('electron').ipcRenderer;
} catch (e) {
    ipcRenderer = null;
}

let turnoAtual = null;

function recortar(texto, limite) {
    const limpo = String(texto == null ? '' : texto).trim();
    return limpo.length > limite ? limpo.slice(0, limite - 1) + '…' : limpo;
}

function numaLinha(texto) {
    return recortar(String(texto == null ? '' : texto).replace(/\s+/g, ' '), LIMITE_TEXTO);
}

function nomeDaFerramenta(nome) {
    return numaLinha(String(nome || '').replace(/^tool_/, '').replace(/_/g, ' '));
}

function resumoDosArgumentos(args) {
    if (!args || typeof args !== 'object') return '';
    const partes = [];
    for (const chave of Object.keys(args)) {
        const valor = args[chave];
        if (valor === null || valor === undefined || valor === '' || valor === false) continue;
        const texto = Array.isArray(valor) ? valor.join(', ') : String(valor);
        partes.push(chave + ': ' + recortar(texto.replace(/\s+/g, ' '), LIMITE_ARGUMENTO));
        if (partes.length >= ARGUMENTOS_VISIVEIS) break;
    }
    return partes.join(' · ');
}

function eventoDoRaciocinio(dados) {
    if (dados.type === 'ai_thought') {
        return dados.text ? { tipo: 'pensamento', texto: recortar(dados.text, LIMITE_TEXTO) } : null;
    }
    if (dados.type === 'tool_used') {
        return { tipo: 'ferramenta', nome: nomeDaFerramenta(dados.name), resumo: resumoDosArgumentos(dados.args) };
    }
    return null;
}

export function alimentarRaciocinio(dados) {
    if (!ipcRenderer || !dados || !dados.type) return;
    if (dados.turn_id && dados.turn_id !== turnoAtual) {
        turnoAtual = dados.turn_id;
        ipcRenderer.send('raciocinio:evento', { tipo: 'inicio' });
    }
    if (EVENTOS_DE_FIM.has(dados.type)) {
        ipcRenderer.send('raciocinio:evento', { tipo: 'fim' });
        return;
    }
    const evento = eventoDoRaciocinio(dados);
    if (evento) ipcRenderer.send('raciocinio:evento', evento);
}
