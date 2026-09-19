const ENDERECO_LEITOR = '/vendor/viewer/pptx.browser.es.js';

export async function montar(caixa, alvo, ctx) {
    ctx.avisar('a carregar o leitor de apresentacoes...', 0.1);
    const modulo = await import(ENDERECO_LEITOR);

    ctx.avisar('a ler a apresentacao...', 0.3);
    const resposta = await fetch(alvo.url);
    if (!resposta.ok) throw new Error('HTTP ' + resposta.status + ' ao ler a apresentacao');
    const dados = await resposta.arrayBuffer();

    caixa.style.overflowY = 'auto';
    caixa.style.overflowX = 'hidden';
    caixa.style.position = 'absolute';
    caixa.style.inset = '0';

    const palco = document.createElement('div');
    caixa.appendChild(palco);

    const vistas = await modulo.PptxViewer.open(dados, palco, {
        zipLimits: modulo.RECOMMENDED_ZIP_LIMITS,
        lazySlides: true,
        lazyMedia: true,
        listOptions: { windowed: true, initialSlides: 4, batchSize: 4 },
        pdfjs: false
    });
    ctx.concluir();

    const contagem = document.createElement('span');
    contagem.textContent = vistas.slideCount + ' diapositivo(s)';

    const remontar = () => {
        if (!vistas.slideCount) return;
        vistas.renderList({ windowed: true, initialSlides: 4, batchSize: 4 })
            .catch((erro) => console.warn(erro));
    };

    return {
        aoAtivar() {
            ctx.ferramentas.appendChild(contagem);
            remontar();
        },
        aoMostrar: remontar,
        destruir() {
            try {
                vistas.destroy();
            } catch (erro) {
                console.warn(erro);
            }
        }
    };
}
