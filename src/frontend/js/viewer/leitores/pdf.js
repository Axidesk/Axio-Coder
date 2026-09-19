import * as pdfjs from 'pdfjs-dist';

pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/viewer/dist/pdf.worker.js';

const MARGEM = 24;
const TETO_AMPLIACAO = 3;
const PASSOS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

export async function montar(caixa, alvo, ctx) {
    const carregamento = pdfjs.getDocument({
        url: alvo.url,
        cMapUrl: '/vendor/viewer/dist/cmaps/',
        cMapPacked: true,
        standardFontDataUrl: '/vendor/viewer/dist/standard_fonts/'
    });
    const documento = await carregamento.promise;

    const rolagem = document.createElement('div');
    rolagem.style.position = 'absolute';
    rolagem.style.inset = '0';
    rolagem.style.overflow = 'auto';
    rolagem.style.padding = MARGEM / 2 + 'px';
    caixa.appendChild(rolagem);

    let passo = PASSOS.indexOf(1);
    const desenhadas = new Map();
    const lugares = [];

    function larguraDisponivel() {
        return Math.max(200, rolagem.clientWidth - MARGEM);
    }

    async function desenhar(numero, lugar) {
        if (desenhadas.has(numero)) return desenhadas.get(numero);
        const pagina = await documento.getPage(numero);
        const base = pagina.getViewport({ scale: 1 });
        const fator = Math.min(TETO_AMPLIACAO, (larguraDisponivel() / base.width) * PASSOS[passo]);
        const vista = pagina.getViewport({ scale: fator });
        const densidade = window.devicePixelRatio || 1;
        const tela = document.createElement('canvas');
        tela.className = 'vw-pdf-pagina';
        tela.width = Math.floor(vista.width * densidade);
        tela.height = Math.floor(vista.height * densidade);
        tela.style.width = Math.floor(vista.width) + 'px';
        tela.style.height = Math.floor(vista.height) + 'px';
        const contexto = tela.getContext('2d');
        const tarefa = pagina.render({
            canvasContext: contexto,
            canvas: tela,
            viewport: vista,
            transform: densidade !== 1 ? [densidade, 0, 0, densidade, 0, 0] : null
        });
        await tarefa.promise;
        lugar.innerHTML = '';
        lugar.style.height = '';
        lugar.appendChild(tela);
        desenhadas.set(numero, tela);
        return tela;
    }

    const observador = new IntersectionObserver((entradas) => {
        for (const entrada of entradas) {
            if (!entrada.isIntersecting) continue;
            const lugar = entrada.target;
            observador.unobserve(lugar);
            desenhar(Number(lugar.dataset.pagina), lugar)
                .then(() => ctx.concluir())
                .catch((erro) => ctx.falhar('Falha ao desenhar a pagina: ' + ((erro && erro.message) || erro)));
        }
    }, { root: rolagem, rootMargin: '300px' });

    for (let numero = 1; numero <= documento.numPages; numero++) {
        const pagina = await documento.getPage(numero);
        const vista = pagina.getViewport({ scale: 1 });
        const lugar = document.createElement('div');
        lugar.className = 'vw-pdf-pagina';
        lugar.dataset.pagina = String(numero);
        lugar.style.background = '#fff';
        lugar.style.height = Math.floor((vista.height / vista.width) * larguraDisponivel()) + 'px';
        rolagem.appendChild(lugar);
        lugares.push(lugar);
        observador.observe(lugar);
    }

    function redesenhar() {
        for (const lugar of lugares) {
            desenhadas.delete(Number(lugar.dataset.pagina));
            const numero = Number(lugar.dataset.pagina);
            lugar.style.height = '';
            observador.observe(lugar);
            desenhar(numero, lugar).catch(() => {});
        }
    }

    const anterior = botaoDeZoom('Reduzir', false);
    const proximo = botaoDeZoom('Ampliar', true);
    const contagem = document.createElement('span');
    contagem.textContent = documento.numPages + ' pagina(s)';

    anterior.addEventListener('click', () => {
        passo = Math.max(0, passo - 1);
        redesenhar();
    });
    proximo.addEventListener('click', () => {
        passo = Math.min(PASSOS.length - 1, passo + 1);
        redesenhar();
    });

    return {
        aoAtivar() {
            ctx.ferramentas.append(anterior, proximo, contagem);
        },
        destruir() {
            observador.disconnect();
            try {
                const liberta = carregamento.destroy();
                if (liberta && typeof liberta.catch === 'function') liberta.catch((erro) => console.warn(erro));
            } catch (erro) {
                console.warn(erro);
            }
            rolagem.remove();
        }
    };
}

function botaoDeZoom(titulo, comMais) {
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'vw-ferramenta';
    botao.title = titulo;
    botao.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">'
        + '<circle cx="7" cy="7" r="5"/><path d="M10.8 10.8 14 14"/><path d="M4.5 7h5"/>'
        + (comMais ? '<path d="M7 4.5v5"/>' : '')
        + '</svg>';
    return botao;
}
