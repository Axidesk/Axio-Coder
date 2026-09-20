const CLASSE = 'a-esmaecer';
const FOLGA_MS = 140;
const TETO_MS = 1500;

const PROPRIEDADES_DE_LAYOUT = new Set([
    'width', 'height', 'min-width', 'max-width', 'min-height', 'max-height',
    'flex', 'flex-basis', 'flex-grow', 'flex-shrink',
    'padding', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom',
    'margin', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom',
    'left', 'right', 'top', 'bottom', 'inset',
    'gap', 'row-gap', 'column-gap', 'grid-template-columns', 'grid-template-rows',
    'font-size', 'border-width'
]);

function esmaecerEmGesto(opcoes) {
    const config = opcoes || {};
    const alvos = (config.conteudo || []).filter(Boolean);
    if (!alvos.length) return () => {};
    const observados = (config.observar || []).filter(Boolean);
    const folga = Number.isFinite(config.folga) ? config.folga : FOLGA_MS;
    const transicoes = new Map();
    const usarJanela = config.janela !== false;
    let esperaDaJanela = 0;
    let limpeza = 0;
    let teto = 0;
    let aRedimensionar = false;

    const pintar = () => {
        const fora = aRedimensionar || transicoes.size > 0;
        for (const alvo of alvos) alvo.classList.toggle(CLASSE, fora);
    };

    const esquecerTransicoes = () => {
        clearTimeout(limpeza);
        clearTimeout(teto);
        transicoes.clear();
        pintar();
    };

    const adiarLimpeza = () => {
        clearTimeout(limpeza);
        limpeza = setTimeout(esquecerTransicoes, folga);
    };

    const aoComecar = (evento) => {
        if (!PROPRIEDADES_DE_LAYOUT.has(evento.propertyName)) return;
        transicoes.set(evento.propertyName, (transicoes.get(evento.propertyName) || 0) + 1);
        clearTimeout(limpeza);
        clearTimeout(teto);
        teto = setTimeout(esquecerTransicoes, TETO_MS);
        pintar();
    };

    const aoTerminar = (evento) => {
        const quantas = transicoes.get(evento.propertyName) || 0;
        if (!quantas) return;
        if (quantas > 1) transicoes.set(evento.propertyName, quantas - 1);
        else transicoes.delete(evento.propertyName);
        if (!transicoes.size) adiarLimpeza();
    };

    const aoRedimensionar = () => {
        clearTimeout(esperaDaJanela);
        esperaDaJanela = setTimeout(() => {
            aRedimensionar = false;
            pintar();
        }, folga);
        if (aRedimensionar) return;
        aRedimensionar = true;
        pintar();
    };

    for (const elemento of observados) {
        elemento.addEventListener('transitionrun', aoComecar);
        elemento.addEventListener('transitioncancel', aoTerminar);
        elemento.addEventListener('transitionend', aoTerminar);
    }
    if (usarJanela) window.addEventListener('resize', aoRedimensionar);

    return () => {
        clearTimeout(esperaDaJanela);
        clearTimeout(limpeza);
        clearTimeout(teto);
        for (const elemento of observados) {
            elemento.removeEventListener('transitionrun', aoComecar);
            elemento.removeEventListener('transitioncancel', aoTerminar);
            elemento.removeEventListener('transitionend', aoTerminar);
        }
        if (usarJanela) window.removeEventListener('resize', aoRedimensionar);
        for (const alvo of alvos) alvo.classList.remove(CLASSE);
    };
}

export { esmaecerEmGesto };
