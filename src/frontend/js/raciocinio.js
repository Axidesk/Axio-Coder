const api = window.raciocinio || {
    aoAbrir: () => {},
    aoEvento: () => {},
    aoHistorico: () => {},
    aoRecolha: () => {},
    aoSair: () => {},
    aoCaixa: () => {},
    aoEscala: () => {},
    alternar: () => {},
    assentar: () => {}
};

const botao = document.getElementById('rc-recolher');
const contador = document.getElementById('rc-contador');
const estado = document.getElementById('rc-estado');
const registo = document.getElementById('rc-registo');
const janela = document.getElementById('rc-janela');
const recorte = document.getElementById('rc-clip');

const MARGEM_DO_FIM_PX = 4;
const VIGIA_DA_ENTRADA_MS = 1000;
const DURACAO_DA_CAIXA_MS = 250;
const CURVA_DA_CAIXA = 'cubic-bezier(0.4, 0, 0.2, 1)';

let recolhido = false;
let passos = 0;
let colado = true;
let pendentes = [];
let agendado = 0;
let entradaResolvida = false;
let escala = 1;
let caixaDaJanela = null;
let movimentoDaCaixa = null;

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
    if (caixaDaJanela) aplicarCaixa({ largura: caixaDaJanela.largura, altura: caixaDaJanela.altura, animar: false });
}

function aplicarCaixa(caixa) {
    if (!caixa) return;
    const largura = Number(caixa.largura);
    const altura = Number(caixa.altura);
    if (!Number.isFinite(largura) || !Number.isFinite(altura) || largura < 1 || altura < 1) return;
    caixaDaJanela = { largura: largura, altura: altura };
    const alvoL = largura / escala;
    const alvoA = altura / escala;
    const anterior = janela.getBoundingClientRect();
    if (movimentoDaCaixa) {
        movimentoDaCaixa.cancel();
        movimentoDaCaixa = null;
    }
    janela.style.width = alvoL + 'px';
    janela.style.height = alvoA + 'px';
    if (caixa.animar && anterior.width > 1) {
        recorte.style.width = Math.max(anterior.width, alvoL) + 'px';
        movimentoDaCaixa = janela.animate(
            [
                { width: anterior.width + 'px', height: anterior.height + 'px' },
                { width: alvoL + 'px', height: alvoA + 'px' }
            ],
            { duration: DURACAO_DA_CAIXA_MS, easing: CURVA_DA_CAIXA }
        );
        movimentoDaCaixa.finished.then(assentarCaixa, () => {});
        return;
    }
    recorte.style.width = alvoL + 'px';
}

function assentarCaixa() {
    movimentoDaCaixa = null;
    if (caixaDaJanela) recorte.style.width = (caixaDaJanela.largura / escala) + 'px';
    api.assentar();
}

function sair() {
    document.body.classList.add('rc-saindo');
}

function avisarFimDoMovimento(evento) {
    if (evento.target !== janela || evento.propertyName !== 'transform') return;
    if (movimentoDaCaixa) return;
    api.assentar();
}

botao.addEventListener('click', alternarRecolha);
registo.addEventListener('scroll', acompanharRolagem, { passive: true });
registo.addEventListener('wheel', marcarGesto, { passive: true });
registo.addEventListener('pointerdown', marcarGesto, { passive: true });
new ResizeObserver(marcarCorteNoTopo).observe(registo);
janela.addEventListener('transitionend', avisarFimDoMovimento);
document.body.classList.add('rc-saindo');
api.aoAbrir(animarEntrada);
setTimeout(() => {
    if (!entradaResolvida) animarEntrada();
}, VIGIA_DA_ENTRADA_MS);
api.aoCaixa(aplicarCaixa);
api.aoEscala(aplicarEscala);
api.aoSair(sair);
api.aoRecolha(definirRecolha);
api.aoEvento(aplicar);
api.aoHistorico((lista) => {
    limpar();
    for (const evento of lista) aplicar(evento);
});
