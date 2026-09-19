const LIMIAR_ARRASTO = 4;
const ABA_PADRAO = '.editor-tab';
const EXCLUSAO_PADRAO = '.editor-tab-close, input';

function chaveDaAba(elemento) {
    return elemento.dataset.path || elemento.dataset.id || elemento.dataset.aba || '';
}

export function ordenarPorChaves(itens, ordem, chaveDe) {
    if (!Array.isArray(itens) || !Array.isArray(ordem) || !ordem.length) return;
    const usados = new Set(ordem);
    const ordenados = [];
    ordem.forEach(function (chave) {
        const item = itens.find(function (candidato) { return chaveDe(candidato) === chave; });
        if (item && ordenados.indexOf(item) < 0) ordenados.push(item);
    });
    itens.forEach(function (item) {
        if (!usados.has(chaveDe(item))) ordenados.push(item);
    });
    itens.length = 0;
    itens.push(...ordenados);
}

export function tornarAbasArrastaveis(container, aoReordenar, opcoes) {
    if (!container || container.dataset.abasArrastaveis === 'sim') return;
    const ajustes = opcoes || {};
    const seletor = ajustes.seletor || ABA_PADRAO;
    const excluir = ajustes.excluir || EXCLUSAO_PADRAO;
    container.dataset.abasArrastaveis = 'sim';

    let origem = null;
    let xInicial = 0;
    let yInicial = 0;
    let arrastou = false;
    let suprimirClique = false;

    function aoClicar(e) {
        if (!suprimirClique) return;
        suprimirClique = false;
        e.stopPropagation();
        e.preventDefault();
    }

    function largar() {
        if (origem) origem.classList.remove('aba-arrastando');
        container.classList.remove('abas-arrastando');
        document.body.style.cursor = '';
        origem = null;
        arrastou = false;
        document.removeEventListener('pointermove', aoMover, true);
        document.removeEventListener('pointerup', aoSoltar, true);
        document.removeEventListener('pointercancel', aoSoltar, true);
    }

    function mudarDeLugar(e) {
        const abas = Array.prototype.slice.call(container.querySelectorAll(seletor));
        let destino = null;
        for (let i = 0; i < abas.length; i++) {
            const aba = abas[i];
            if (aba === origem) continue;
            const caixa = aba.getBoundingClientRect();
            if (e.clientX < caixa.left + caixa.width / 2) {
                destino = aba;
                break;
            }
        }
        if (destino) {
            if (origem.nextElementSibling !== destino) container.insertBefore(origem, destino);
        } else if (container.lastElementChild !== origem) {
            container.appendChild(origem);
        }
    }

    function aoMover(e) {
        if (!origem) return;
        if (!container.contains(origem)) {
            largar();
            return;
        }
        if (!arrastou) {
            const andouX = Math.abs(e.clientX - xInicial);
            const andouY = Math.abs(e.clientY - yInicial);
            if (andouX < LIMIAR_ARRASTO && andouY < LIMIAR_ARRASTO) return;
            if (container.querySelectorAll(seletor).length < 2) return;
            arrastou = true;
            container.classList.add('abas-arrastando');
            origem.classList.add('aba-arrastando');
            document.body.style.cursor = 'grabbing';
        }
        mudarDeLugar(e);
    }

    function aoSoltar() {
        const houveArrasto = arrastou;
        largar();
        if (!houveArrasto) return;
        suprimirClique = true;
        setTimeout(function () { suprimirClique = false; }, 0);
        if (typeof aoReordenar !== 'function') return;
        const ordem = [];
        container.querySelectorAll(seletor).forEach(function (aba) {
            const chave = chaveDaAba(aba);
            if (chave) ordem.push(chave);
        });
        aoReordenar(ordem);
    }

    function aoPressionar(e) {
        if (e.button !== 0) return;
        if (origem) largar();
        const alvo = e.target;
        if (!alvo || !alvo.closest) return;
        if (alvo.closest(excluir)) return;
        const aba = alvo.closest(seletor);
        if (!aba || !container.contains(aba)) return;
        origem = aba;
        xInicial = e.clientX;
        yInicial = e.clientY;
        arrastou = false;
        document.addEventListener('pointermove', aoMover, true);
        document.addEventListener('pointerup', aoSoltar, true);
        document.addEventListener('pointercancel', aoSoltar, true);
    }

    container.addEventListener('pointerdown', aoPressionar);
    container.addEventListener('click', aoClicar, true);
}
