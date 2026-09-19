const INTERVALO_DO_DUPLO_CLIQUE_MS = 420;

export function aoDuploCliqueDoMeio(elemento, aoDisparar) {
    let ultimoToque = 0;
    const aoPremir = (evento) => {
        if (evento.button !== 1) return;
        const agora = performance.now();
        if (agora - ultimoToque > INTERVALO_DO_DUPLO_CLIQUE_MS) {
            ultimoToque = agora;
            return;
        }
        ultimoToque = 0;
        evento.preventDefault();
        aoDisparar();
    };
    elemento.addEventListener('mousedown', aoPremir);
    return () => elemento.removeEventListener('mousedown', aoPremir);
}
