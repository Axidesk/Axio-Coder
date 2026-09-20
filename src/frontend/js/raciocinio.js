const api = window.raciocinio || {
    aoAbrir: () => {},
    aoEvento: () => {},
    aoHistorico: () => {},
    aoRecolha: () => {},
    aoLargo: () => {},
    aoAnimando: () => {},
    aoSair: () => {},
    aoEscala: () => {},
    alternar: () => {},
    largo: () => {}
};

const botao = document.getElementById('rc-recolher');
const botaoLargo = document.getElementById('rc-largo');
const contador = document.getElementById('rc-contador');
const registo = document.getElementById('rc-registo');

const MARGEM_DO_FIM_PX = 4;
const VIGIA_DA_ENTRADA_MS = 1000;

let recolhido = true;
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
    if (!evento || !evento.tipo || evento.tipo === 'estado') return;
    if (evento.tipo === 'ferramenta' || evento.tipo === 'pensamento') {
        pendentes.push(evento);
        agendarDespejo();
        return;
    }
    limpar();
    if (evento.tipo === 'inicio') definirRecolha(true);
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

function alternarLargo() {
    api.largo();
}

function definirLargo(valor) {
    const alvo = !!valor;
    document.body.classList.toggle('rc-largo', alvo);
    const rotulo = alvo ? 'Restaurar' : 'Maximizar';
    botaoLargo.title = rotulo;
    botaoLargo.setAttribute('aria-label', rotulo);
}

function definirAnimando(valor) {
    document.body.classList.toggle('rc-animando', !!valor);
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
botaoLargo.addEventListener('click', alternarLargo);
registo.addEventListener('scroll', acompanharRolagem, { passive: true });
registo.addEventListener('wheel', marcarGesto, { passive: true });
registo.addEventListener('pointerdown', marcarGesto, { passive: true });
new ResizeObserver(marcarCorteNoTopo).observe(registo);
definirRecolha(true);
document.body.classList.add('rc-saindo');
api.aoAbrir(animarEntrada);
setTimeout(() => {
    if (!entradaResolvida) animarEntrada();
}, VIGIA_DA_ENTRADA_MS);
api.aoEscala(aplicarEscala);
api.aoSair(sair);
api.aoRecolha(definirRecolha);
api.aoLargo(definirLargo);
api.aoAnimando(definirAnimando);
api.aoEvento(aplicar);
api.aoHistorico((lista) => {
    limpar();
    for (const evento of lista) aplicar(evento);
});
