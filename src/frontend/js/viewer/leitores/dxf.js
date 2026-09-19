import { DxfViewer } from 'dxf-viewer';
import { aoDuploCliqueDoMeio } from '../gestos.js';

const CAMINHO_WORKER = '/vendor/viewer/dist/dxf_worker.js';
const ESCALA_DA_RODA = 1.0013;
const AMORTECIMENTO_DO_ZOOM_MS = 85;
const LIMITE_DE_APROXIMACAO = 0.02;
const LIMITE_DE_AFASTAMENTO = 40;

function criarWorker() {
    return new Worker(CAMINHO_WORKER);
}

export async function montar(caixa, alvo, ctx) {
    const area = document.createElement('div');
    area.style.position = 'relative';
    area.style.width = '100%';
    area.style.height = '100%';
    area.style.overflow = 'hidden';
    caixa.appendChild(area);

    const vistas = new DxfViewer(area, {
        autoResize: true,
        antialias: true,
        colorCorrection: true
    });

    await vistas.Load({
        url: alvo.url,
        fonts: null,
        workerFactory: criarWorker,
        progressCbk: (fase, feito, total) => {
            const fracao = total ? feito / total : 0;
            ctx.avisar('a preparar o desenho (' + fase + ')...', fracao);
        }
    });

    const camadas = document.createElement('span');
    const nomes = [];
    for (const camada of vistas.GetLayers()) nomes.push(camada.name);
    camadas.textContent = nomes.length + ' camada(s)';

    const repintar = () => {
        try {
            vistas.Render();
        } catch (erro) {
            console.warn(erro);
        }
    };

    const larguraDaVista = () => {
        const camara = vistas.GetCamera();
        if (!camara) return 0;
        const zoom = camara.zoom || 1;
        return (camara.right - camara.left) / zoom;
    };

    const pixelsDoCanvas = () => {
        const canvas = vistas.GetCanvas();
        if (!canvas) return null;
        const caixa = canvas.getBoundingClientRect();
        const largura = canvas.clientWidth || caixa.width;
        const altura = canvas.clientHeight || caixa.height;
        if (largura <= 0 || altura <= 0) return null;
        return { esquerda: caixa.left, topo: caixa.top, largura: largura, altura: altura };
    };

    let animacao = null;
    let ultimoInstante = 0;
    let larguraBase = 0;
    let larguraAtual = 0;
    let larguraAlvo = 0;
    let ancora = null;

    const pontoSobOCursor = (px, py, tela, largura) => {
        const camara = vistas.GetCamera();
        const altura = largura * tela.altura / tela.largura;
        return {
            x: camara.position.x + (px / tela.largura - 0.5) * largura,
            y: camara.position.y + (0.5 - py / tela.altura) * altura
        };
    };

    const centroParaALargura = (largura) => {
        const tela = pixelsDoCanvas();
        const altura = largura * tela.altura / tela.largura;
        return { x: ancora.x - ancora.sx * largura, y: ancora.y - ancora.sy * altura };
    };

    const passoDoZoom = (agora) => {
        const intervalo = ultimoInstante ? Math.min(64, agora - ultimoInstante) : 16;
        ultimoInstante = agora;
        larguraAtual += (larguraAlvo - larguraAtual) * (1 - Math.exp(-intervalo / AMORTECIMENTO_DO_ZOOM_MS));
        const resto = Math.abs(larguraAlvo - larguraAtual) / larguraAlvo;
        const chegou = resto < 0.0015;
        if (chegou) larguraAtual = larguraAlvo;
        vistas.SetView(centroParaALargura(larguraAtual), larguraAtual);
        vistas.Render();
        if (chegou) {
            animacao = null;
            ultimoInstante = 0;
            return;
        }
        animacao = requestAnimationFrame(passoDoZoom);
    };

    const pararZoom = () => {
        if (animacao !== null) cancelAnimationFrame(animacao);
        animacao = null;
        ultimoInstante = 0;
        larguraBase = 0;
    };

    const aoRoda = (evento) => {
        if (!vistas.HasRenderer() || area.clientWidth <= 0) return;
        const tela = pixelsDoCanvas();
        if (!tela) return;
        evento.preventDefault();
        evento.stopPropagation();
        const px = evento.clientX - tela.esquerda;
        const py = evento.clientY - tela.topo;
        const atual = larguraDaVista();
        if (animacao === null || !larguraBase) {
            larguraBase = atual;
            larguraAlvo = atual;
        }
        larguraAtual = atual;
        const mundo = pontoSobOCursor(px, py, tela, atual);
        ancora = { x: mundo.x, y: mundo.y, sx: px / tela.largura - 0.5, sy: 0.5 - py / tela.altura };
        const passos = evento.deltaMode === 1 ? evento.deltaY * 16 : (evento.deltaMode === 2 ? evento.deltaY * 100 : evento.deltaY);
        const pedido = larguraAlvo * Math.pow(ESCALA_DA_RODA, passos);
        larguraAlvo = Math.min(larguraBase * LIMITE_DE_AFASTAMENTO, Math.max(larguraBase * LIMITE_DE_APROXIMACAO, pedido));
        if (animacao === null) animacao = requestAnimationFrame(passoDoZoom);
    };

    const enquadrar = () => {
        pararZoom();
        try {
            const limites = vistas.GetBounds();
            if (!limites) return;
            const origem = vistas.GetOrigin();
            vistas.FitView(
                limites.minX - origem.x,
                limites.maxX - origem.x,
                limites.minY - origem.y,
                limites.maxY - origem.y,
                0.1
            );
        } catch (erro) {
            console.warn(erro);
            return;
        }
        repintar();
    };

    const camaraInteira = () => {
        const camara = vistas.GetCamera();
        if (!camara) return false;
        return Number.isFinite(camara.left) && Number.isFinite(camara.right)
            && Number.isFinite(camara.top) && Number.isFinite(camara.bottom)
            && camara.right > camara.left && camara.top > camara.bottom;
    };

    const aoMostrar = () => {
        requestAnimationFrame(() => requestAnimationFrame(() => {
            if (area.clientWidth <= 0) return;
            if (camaraInteira()) repintar();
            else enquadrar();
        }));
    };

    vistas.Subscribe('resized', repintar);
    enquadrar();

    area.addEventListener('wheel', aoRoda, { capture: true, passive: false });

    const aoDuploClique = () => enquadrar();
    area.addEventListener('dblclick', aoDuploClique);
    const largarDuploMeio = aoDuploCliqueDoMeio(area, enquadrar);

    ctx.concluir();

    return {
        aoAtivar() {
            ctx.ferramentas.appendChild(camadas);
        },
        aoMostrar,
        destruir() {
            pararZoom();
            area.removeEventListener('wheel', aoRoda, { capture: true });
            area.removeEventListener('dblclick', aoDuploClique);
            largarDuploMeio();
            try {
                vistas.Destroy();
            } catch (erro) {
                console.warn(erro);
            }
            area.remove();
        }
    };
}
