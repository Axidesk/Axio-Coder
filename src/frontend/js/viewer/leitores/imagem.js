export async function montar(caixa, alvo, ctx) {
    caixa.style.textAlign = 'center';
    caixa.style.padding = '10px';
    const imagem = document.createElement('img');
    imagem.className = 'vw-imagem';
    imagem.src = alvo.url;
    imagem.alt = alvo.nome;
    imagem.addEventListener('load', () => ctx.concluir());
    imagem.addEventListener('error', () => ctx.falhar('Nao consegui carregar a imagem.'));
    caixa.appendChild(imagem);

    const dimensoes = document.createElement('span');
    imagem.addEventListener('load', () => {
        dimensoes.textContent = imagem.naturalWidth + ' x ' + imagem.naturalHeight + ' px';
    });

    return {
        aoAtivar() {
            ctx.ferramentas.appendChild(dimensoes);
        },
        destruir() {
            imagem.remove();
        }
    };
}
