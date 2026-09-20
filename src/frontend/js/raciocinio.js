const api = window.raciocinio || {
    aoAbrir: () => {},
    aoEvento: () => {},
    aoHistorico: () => {},
    aoRecolha: () => {},
    aoSair: () => {},
    alternar: () => {}
};

const botao = document.getElementById('rc-recolher');
const contador = document.getElementById('rc-contador');
const estado = document.getElementById('rc-estado');
const registo = document.getElementById('rc-registo');

const MARGEM_DO_FIM_PX = 24;

let recolhido = false;
let passos = 0;
let seguirFim = true;
let pendentes = [];
let agendado = 0;

function limpar() {
    if (agendado) {
        cancelAnimationFrame(agendado);
        agendado = 0;
    }
    pendentes = [];
    while (registo.firstChild) registo.removeChild(registo.firstChild);
    estado.textContent = '';
    passos = 0;
    contador.textContent = '';
    seguirFim = true;
}

function noFimDoRegisto() {
    return registo.scrollHeight - registo.scrollTop - registo.clientHeight <= MARGEM_DO_FIM_PX;
}

function aoFundo() {
    if (!seguirFim) return;
    registo.scrollTop = registo.scrollHeight;
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
    aoFundo();
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

botao.addEventListener('click', alternarRecolha);
registo.addEventListener('scroll', () => {
    seguirFim = noFimDoRegisto();
}, { passive: true });
registo.addEventListener('wheel', () => {
    seguirFim = false;
}, { passive: true });
registo.addEventListener('pointerdown', () => {
    seguirFim = false;
}, { passive: true });
document.body.classList.add('rc-saindo');
api.aoAbrir(animarEntrada);
api.aoTrocar(marcarTroca);
api.aoEscala(aplicarEscala);
api.aoSair(sair);
api.aoRecolha(definirRecolha);
api.aoEvento(aplicar);
api.aoHistorico((lista) => {
    limpar();
    for (const evento of lista) aplicar(evento);
});
