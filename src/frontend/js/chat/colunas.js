
const vistas = new Map();

function abrir(col) {
    if (col) col.classList.remove('panel-col-closed');
}

function fechar(col) {
    if (col) col.classList.add('panel-col-closed');
}

function fecharOutrasCamadas(vista) {
    vistas.forEach(outra => {
        if (outra !== vista && outra.col3Aberta()) outra.fecharCol3();
    });
}

function criarVista(opcoes) {
    let arquivoInterno = null;
    let caminhoEntrega = null;
    let caminhoOriginal = null;
    const vista = {
        id: opcoes.id,
        col2: opcoes.col2,
        col3: opcoes.col3,
        lista: opcoes.lista,
        codigo: opcoes.codigo,
        titulo: opcoes.titulo,

        caminhoEntrega: () => caminhoEntrega,
        marcarCaminhoEntrega: (c) => { caminhoEntrega = c; },
        caminhoOriginal: () => caminhoOriginal,
        marcarCaminhoOriginal: (c) => { caminhoOriginal = c; },
        abrirCol2: opcoes.abrirCol2 || (() => abrir(opcoes.col2)),
        fecharCol2: opcoes.fecharCol2 || (() => fechar(opcoes.col2)),

        aoAbrirCol3: null,
        abrirCol3() {
            if (vista.aoAbrirCol3) vista.aoAbrirCol3();
            (opcoes.abrirCol3 || (() => abrir(opcoes.col3)))();
            fecharOutrasCamadas(vista);
        },

        aoFecharCol3: null,
        fecharCol3() {
            (opcoes.fecharCol3 || (() => fechar(opcoes.col3)))();
            if (vista.aoFecharCol3) vista.aoFecharCol3();
        },
        col3Aberta: () => !!opcoes.col3 && !opcoes.col3.classList.contains('panel-col-closed'),

        arquivoAtual: () => (opcoes.lerArquivoAtual ? opcoes.lerArquivoAtual() : arquivoInterno),
        marcarArquivoAtual: (fileData) => {
            if (opcoes.gravarArquivoAtual) opcoes.gravarArquivoAtual(fileData);
            else arquivoInterno = fileData;
        },
        abrirArquivo: opcoes.abrirArquivo || (() => {}),
        abrirDiff: opcoes.abrirDiff || (() => {}),
        aoAbrirGrupo: opcoes.aoAbrirGrupo || (() => {})
    };
    vistas.set(vista.id, vista);
    return vista;
}

function vistaDe(id) {
    return vistas.get(id) || null;
}


function vistaDoElemento(el) {
    const raiz = el && typeof el.closest === 'function' ? el.closest('[data-col-vista]') : null;
    return raiz ? vistaDe(raiz.getAttribute('data-col-vista')) : null;
}

export { criarVista, vistaDe, vistaDoElemento };
