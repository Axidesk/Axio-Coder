const api = window.raciocinio || {
    aoAbrir: () => {},
    aoEvento: () => {},
    aoHistorico: () => {},
    aoRecolha: () => {},
    aoSair: () => {},
    aoEscala: () => {},
    alternar: () => {}
};

const botao = document.getElementById('rc-recolher');
const contador = document.getElementById('rc-contador');
const estado = document.getElementById('rc-estado');
const registo = document.getElementById('rc-registo');

const MARGEM_DO_FIM_PX = 4;
const VIGIA_DA_ENTRADA_MS = 1000;

let recolhido = false;
let passos = 0;
let colado = true;
let pendentes = [];
let agendado = 0;
let entradaResolvida = false;
let escala = 1;

function limpar() {
    if (agendado) {
        cancelAnimationFrame(agendado);
        agendado = 0;
    }
    pendentes = [];
    while (registo.firstChild) registo.removeChild(registo.firstChild);
    registo.classList.remove('rc-por-cima');
    registo.scrollTop = 0;
    estado.textContent = '';
    passos = 0;
    contador.textContent = '';
    colado = true;
}

function noFimDoRegisto() {
    return registo.scrollHeight - registo.scrollTop - registo.clientHeight <= MARGEM_DO_FIM_PX;
}

function marcarCorteNoTopo() {
    registo.classList.toggle('rc-por-cima', registo.scrollTop > 2);
}

function colarAoFundo() {
    registo.scrollTop = registo.scrollHeight;
    marcarCorteNoTopo();
}

function marcarGesto() {
    colado = false;
}

function acompanharRolagem() {
    marcarCorteNoTopo();
    colado = noFimDoRegisto();
}

function linhaDaFerramenta(evento) {
    const linha = document.createElement('div');
    linha.className = 'rc-ferramenta';
    const nome = document.createElement('span');
    nome.className = 'rc-nome';
    nome.textContent = evento.nome || '';
    linha.appendChild(nome);
    if (evento.resumo) {
        const resumo = document.createElement('span');
        resumo.className = 'rc-resumo';
        resumo.textContent = evento.resumo;
        linha.appendChild(resumo);
    }
    return linha;
}

function linhaDoPensamento(evento) {
    const linha = document.createElement('p');
    linha.className = 'rc-pensamento';
    linha.textContent = evento.texto || '';
    return linha;
}

function despejar() {
    agendado = 0;
    const lista = pendentes;
    pendentes = [];
    if (!lista.length) return;
    for (const evento of lista) {
        registo.appendChild(evento.tipo === 'ferramenta' ? linhaDaFerramenta(evento) : linhaDoPensamento(evento));
        passos += 1;
    }
    contador.textContent = passos === 1 ? '1 passo' : passos + ' passos';
    if (colado) colarAoFundo();
}

function agendarDespejo() {
    if (agendado) return;
    agendado = requestAnimationFrame(despejar);
}

function aplicar(evento) {
    if (!evento || !evento.tipo) return;
    if (evento.tipo === 'estado') {
        estado.textContent = evento.texto || '';
        return;
    }
    if (evento.tipo === 'ferramenta' || evento.tipo === 'pensamento') {
        pendentes.push(evento);
        agendarDespejo();
        return;
    }
    limpar();
    if (evento.tipo === 'inicio') definirRecolha(false);
}

function rotuloDaRecolha() {
    return recolhido ? 'Exibir' : 'Recolher';
}

function definirRecolha(valor) {
    recolhido = !!valor;
    document.body.classList.toggle('rc-recolhido', recolhido);
    botao.title = rotuloDaRecolha();
    botao.setAttribute('aria-label', rotuloDaRecolha());
}

function alternarRecolha() {
    api.alternar();
}

function animarEntrada() {
    entradaResolvida = true;
    document.body.classList.remove('rc-saindo');
}

function aplicarEscala(zoom) {
    escala = zoom > 0 ? zoom : 1;
    document.documentElement.style.setProperty('--rc-zoom', String(escala));
}

function sair() {
    document.body.classList.add('rc-saindo');
}

botao.addEventListener('click', alternarRecolha);
registo.addEventListener('scroll', acompanharRolagem, { passive: true });
registo.addEventListener('wheel', marcarGesto, { passive: true });
registo.addEventListener('pointerdown', marcarGesto, { passive: true });
new ResizeObserver(marcarCorteNoTopo).observe(registo);
document.body.classList.add('rc-saindo');
api.aoAbrir(animarEntrada);
setTimeout(() => {
    if (!entradaResolvida) animarEntrada();
}, VIGIA_DA_ENTRADA_MS);
api.aoEscala(aplicarEscala);
api.aoSair(sair);
api.aoRecolha(definirRecolha);
api.aoEvento(aplicar);
api.aoHistorico((lista) => {
    limpar();
    for (const evento of lista) aplicar(evento);
});
