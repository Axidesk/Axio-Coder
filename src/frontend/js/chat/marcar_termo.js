const CLASSE_PADRAO = 'busca-termo';
const SEM_TEXTO = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'TITLE']);

function marcarTermo(raiz, alvo, classe) {
    if (!raiz || !alvo) return 0;
    const termo = String(alvo).toLowerCase().trim();
    if (!termo) return 0;
    const nome = classe || CLASSE_PADRAO;
    let total = 0;
    for (const trecho of _trechosDeTexto(raiz, termo)) total += _envolver(trecho, termo, nome);
    return total;
}

function limparMarcas(raiz, classe) {
    if (!raiz) return 0;
    const marcas = raiz.querySelectorAll('.' + (classe || CLASSE_PADRAO));
    if (!marcas.length) return 0;
    marcas.forEach(marca => marca.replaceWith(marca.textContent));
    raiz.normalize();
    return marcas.length;
}

function _trechosDeTexto(raiz, termo) {
    const achados = [];
    const pilha = [raiz];
    while (pilha.length) {
        const filhos = pilha.pop().childNodes;
        for (let i = 0; i < filhos.length; i++) {
            const filho = filhos[i];
            if (filho.nodeType === 3) {
                if ((filho.nodeValue || '').toLowerCase().includes(termo)) achados.push(filho);
            } else if (filho.nodeType === 1 && !SEM_TEXTO.has(filho.nodeName)) {
                pilha.push(filho);
            }
        }
    }
    return achados;
}

function _envolver(noTexto, termo, classe) {
    const texto = noTexto.nodeValue || '';
    const minusculas = texto.toLowerCase();
    let corte = minusculas.indexOf(termo);
    if (corte === -1) return 0;
    let inicio = 0;
    let total = 0;
    const pedacos = document.createDocumentFragment();
    while (corte !== -1) {
        if (corte > inicio) pedacos.appendChild(document.createTextNode(texto.slice(inicio, corte)));
        const marca = document.createElement('span');
        marca.className = classe;
        marca.textContent = texto.slice(corte, corte + termo.length);
        pedacos.appendChild(marca);
        total += 1;
        inicio = corte + termo.length;
        corte = minusculas.indexOf(termo, inicio);
    }
    if (inicio < texto.length) pedacos.appendChild(document.createTextNode(texto.slice(inicio)));
    noTexto.replaceWith(pedacos);
    return total;
}

export { marcarTermo, limparMarcas };
