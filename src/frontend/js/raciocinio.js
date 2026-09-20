const api = window.raciocinio || {
    aoAbrir: () => {},
    aoEvento: () => {},
    aoHistorico: () => {},
    aoRecolha: () => {},
    aoSair: () => {},
    aoAnimacao: () => {},
    alternar: () => {},
    tique: () => {}
};

const botao = document.getElementById('rc-recolher');
const contador = document.getElementById('rc-contador');
const estado = document.getElementById('rc-estado');
const registo = document.getElementById('rc-registo');

const MARGEM_DO_FIM_PX = 4;
const VIGIA_DA_ENTRADA_MS = 1000;
const PORTAO_DO_GESTO_MS = 300;

let recolhido = false;
let passos = 0;
let portaoDoGesto = 0;
let pendentes = [];
let agendado = 0;
let entradaResolvida = false;
let relogio = 0;
let relogioLigado = false;

function limpar() {
    if (agendado) {
        cancelAnimationFrame(agendado);
        agendado = 0;
    }
    pendentes = [];
    while (registo.firstChild) registo.removeChild(registo.firstChild);
    registo.classList.remove('rc-por-cima');
    estado.textContent = '';
    passos = 0;
    contador.textContent = '';
    portaoDoGesto = 0;
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

function portaoAberto() {
    return performance.now() >= portaoDoGesto;
}

function marcarGesto() {
    if (!noFimDoRegisto()) return;
    portaoDoGesto = performance.now() + PORTAO_DO_GESTO_MS;
}

function libertarGesto() {
    portaoDoGesto = 0;
}

function acompanharRolagem() {
    marcarCorteNoTopo();
    if (!noFimDoRegisto()) libertarGesto();
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
    const estavaNoFundo = noFimDoRegisto();
    for (const evento of lista) {
        registo.appendChild(evento.tipo === 'ferramenta' ? linhaDaFerramenta(evento) : linhaDoPensamento(evento));
        passos += 1;
    }
    contador.textContent = passos === 1 ? '1 passo' : passos + ' passos';
    if (estavaNoFundo && portaoAberto()) colarAoFundo();
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
    document.body.classList.remove('rc-trocando');
}

function marcarTroca(valor) {
    document.body.classList.toggle('rc-trocando', !!valor);
}

function aplicarEscala(zoom) {
    document.documentElement.style.setProperty('--rc-zoom', String(zoom > 0 ? zoom : 1));
}

function sair() {
    document.body.classList.add('rc-saindo');
}

function passoDoRelogio() {
    relogio = 0;
    if (!relogioLigado) return;
    relogio = requestAnimationFrame(passoDoRelogio);
    api.tique();
}

function ligarRelogio(ligado) {
    relogioLigado = !!ligado;
    if (relogio) {
        cancelAnimationFrame(relogio);
        relogio = 0;
    }
    if (relogioLigado) relogio = requestAnimationFrame(passoDoRelogio);
}

botao.addEventListener('click', alternarRecolha);
registo.addEventListener('scroll', acompanharRolagem, { passive: true });
registo.addEventListener('scrollend', libertarGesto, { passive: true });
registo.addEventListener('wheel', marcarGesto, { passive: true });
registo.addEventListener('pointerdown', marcarGesto, { passive: true });
new ResizeObserver(() => {
    marcarCorteNoTopo();
    if (portaoAberto() && noFimDoRegisto()) colarAoFundo();
}).observe(registo);
document.body.classList.add('rc-saindo');
api.aoAbrir(animarEntrada);
setTimeout(() => {
    if (!entradaResolvida) animarEntrada();
}, VIGIA_DA_ENTRADA_MS);
api.aoTrocar(marcarTroca);
api.aoAnimacao(ligarRelogio);
api.aoEscala(aplicarEscala);
api.aoSair(sair);
api.aoRecolha(definirRecolha);
api.aoEvento(aplicar);
api.aoHistorico((lista) => {
    limpar();
    for (const evento of lista) aplicar(evento);
});
