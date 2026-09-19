import { renderAsync } from 'docx-preview';

const PROPORCAO_A4 = 297 / 210;
const MARGEM_PADRAO_DO_WORD = 96;

function ajustarFolhas(destino) {
    const folhas = destino.querySelectorAll('.docx-wrapper > section.docx');
    for (const folha of folhas) {
        const medidas = getComputedStyle(folha);
        const espaco = ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft']
            .reduce((soma, lado) => soma + (parseFloat(medidas[lado]) || 0), 0);
        if (!espaco) folha.style.padding = MARGEM_PADRAO_DO_WORD + 'px';
        const largura = folha.clientWidth;
        if (!largura) continue;
        folha.style.minHeight = Math.round(largura * PROPORCAO_A4) + 'px';
    }
}

export async function montar(caixa, alvo, ctx) {
    ctx.avisar('a ler o documento...', 0.1);
    const resposta = await fetch(alvo.url);
    if (!resposta.ok) throw new Error('HTTP ' + resposta.status + ' ao ler o documento');
    const dados = await resposta.arrayBuffer();

    const destino = document.createElement('div');
    destino.className = 'vw-docx';
    caixa.appendChild(destino);

    ctx.avisar('a desenhar o documento...', 0.4);
    await renderAsync(dados, destino, destino, {
        className: 'docx',
        inWrapper: true,
        breakPages: true,
        ignoreWidth: false,
        experimental: true
    });
    ajustarFolhas(destino);
    ctx.concluir();

    return {
        destruir() {
            destino.remove();
        }
    };
}
