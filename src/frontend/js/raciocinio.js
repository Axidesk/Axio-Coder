const api = window.raciocinio || {
    aoAbrir: () => {},
    aoEvento: () => {},
    aoHistorico: () => {},
    recolher: () => {}
};

const janela = document.getElementById('rc-janela');
const botao = document.getElementById('rc-recolher');
const contador = document.getElementById('rc-contador');
const estado = document.getElementById('rc-estado');
const registo = document.getElementById('rc-registo');

const ENTRADA = [
    { opacity: 0, transform: 'translateY(-14px) scale(0.98)' },
    { opacity: 1, transform: 'translateY(0) scale(1)' }
];

const ESPERA_DA_RECOLHA_MS = 130;

let recolhido = false;
let passos = 0;

function limpar() {
    while (registo.firstChild) registo.removeChild(registo.firstChild);
    estado.textContent = '';
    passos = 0;
    contador.textContent = '';
}

function aoFundo() {
    registo.scrollTop = registo.scrollHeight;
}

function acrescentar(elemento) {
    registo.appendChild(elemento);
    passos += 1;
    contador.textContent = passos === 1 ? '1 passo' : passos + ' passos';
    aoFundo();
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

function aplicar(evento) {
    if (!evento || !evento.tipo) return;
    if (evento.tipo === 'ferramenta') return acrescentar(linhaDaFerramenta(evento));
    if (evento.tipo === 'pensamento') return acrescentar(linhaDoPensamento(evento));
    if (evento.tipo === 'estado') {
        estado.textContent = evento.texto || '';
        return;
    }
    limpar();
    if (evento.tipo === 'inicio' && definirRecolha(false)) api.recolher(false);
}

function rotuloDaRecolha() {
    return recolhido ? 'Exibir' : 'Recolher';
}

function definirRecolha(valor) {
    const mudou = recolhido !== !!valor;
    recolhido = !!valor;
    document.body.classList.toggle('rc-recolhido', recolhido);
    botao.title = rotuloDaRecolha();
    botao.setAttribute('aria-label', rotuloDaRecolha());
    return mudou;
}

function alternarRecolha() {
    const proximo = !recolhido;
    definirRecolha(proximo);
    if (proximo) window.setTimeout(() => api.recolher(true), ESPERA_DA_RECOLHA_MS);
    else api.recolher(false);
}

function animarEntrada() {
    if (typeof janela.animate !== 'function') return;
    janela.animate(ENTRADA, { duration: 280, easing: 'cubic-bezier(0.4, 0, 0.2, 1)' });
}

botao.addEventListener('click', alternarRecolha);
api.aoAbrir(animarEntrada);
api.aoEvento(aplicar);
api.aoHistorico((lista) => {
    limpar();
    for (const evento of lista) aplicar(evento);
});
