const LIMITE_BYTES = 2 * 1024 * 1024;

export async function montar(caixa, alvo, ctx) {
    ctx.avisar('a ler o ficheiro...', 0.2);
    const resposta = await fetch(alvo.url);
    if (!resposta.ok) throw new Error('HTTP ' + resposta.status + ' ao ler o ficheiro');
    const texto = await resposta.text();

    const pre = document.createElement('pre');
    pre.className = 'vw-texto';
    pre.textContent = texto.length > LIMITE_BYTES
        ? texto.slice(0, LIMITE_BYTES) + '\n\n[...] ficheiro truncado na exibicao'
        : texto;
    caixa.appendChild(pre);

    const linhas = document.createElement('span');
    linhas.textContent = texto.split('\n').length + ' linha(s)';
    ctx.concluir();

    return {
        aoAtivar() {
            ctx.ferramentas.appendChild(linhas);
        },
        destruir() {
            pre.remove();
        }
    };
}
