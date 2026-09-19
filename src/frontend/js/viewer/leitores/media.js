import { extensaoDe } from '../../editor/familia_ficheiro.js';

const DE_VIDEO = ['mp4', 'webm', 'ogv', 'mov'];

export async function montar(caixa, alvo, ctx) {
    const ehVideo = DE_VIDEO.indexOf(extensaoDe(alvo.nome)) !== -1;
    caixa.style.display = 'flex';
    caixa.style.alignItems = 'center';
    caixa.style.justifyContent = 'center';
    caixa.style.background = '#000';

    const media = document.createElement(ehVideo ? 'video' : 'audio');
    media.className = 'vw-media';
    media.controls = true;
    media.preload = 'metadata';
    media.src = alvo.url;
    if (ehVideo) media.style.maxHeight = '100%';
    media.addEventListener('loadedmetadata', () => {
        if (ehVideo && media.videoWidth) {
            dimensoes.textContent = media.videoWidth + ' x ' + media.videoHeight + ' px';
        }
        ctx.concluir();
    });
    media.addEventListener('error', () => ctx.falhar('Nao consegui abrir este ficheiro de media.'));
    caixa.appendChild(media);

    const dimensoes = document.createElement('span');

    return {
        aoAtivar() {
            ctx.ferramentas.appendChild(dimensoes);
        },
        destruir() {
            media.pause();
            media.removeAttribute('src');
            media.load();
            media.remove();
        }
    };
}
