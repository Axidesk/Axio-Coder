const FAMILIAS = [
    { id: 'ifc', rotulo: 'Modelo BIM', extensoes: ['ifc', 'frag'] },
    { id: 'pdf', rotulo: 'Documento PDF', extensoes: ['pdf'] },
    { id: 'docx', rotulo: 'Documento', extensoes: ['docx', 'odt'] },
    { id: 'planilha', rotulo: 'Planilha', extensoes: ['xlsx', 'xlsm', 'xls', 'ods', 'csv', 'tsv'] },
    { id: 'pptx', rotulo: 'Apresentacao', extensoes: ['pptx', 'odp'] },
    { id: 'dxf', rotulo: 'Desenho CAD', extensoes: ['dxf'] },
    { id: 'imagem', rotulo: 'Imagem', extensoes: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico', 'svg', 'avif'] },
    { id: 'media', rotulo: 'Media', extensoes: ['mp4', 'webm', 'ogv', 'mov', 'mp3', 'wav', 'ogg', 'm4a', 'flac'] },
    { id: 'texto', rotulo: 'Texto', extensoes: ['txt', 'log', 'md', 'json', 'xml', 'yml', 'yaml', 'ini', 'conf'] }
];

const DO_EDITOR = new Set(['imagem', 'texto']);

export function nomeDe(caminho) {
    return String(caminho || '').split(/[\\/]/).pop() || '';
}

export function extensaoDe(caminho) {
    const nome = nomeDe(caminho);
    const ponto = nome.lastIndexOf('.');
    return ponto > 0 ? nome.slice(ponto + 1).toLowerCase() : '';
}

export function familiaDe(caminho) {
    const ext = extensaoDe(caminho);
    if (!ext) return null;
    return FAMILIAS.find((familia) => familia.extensoes.indexOf(ext) !== -1) || null;
}

export function abreNoViewer(caminho) {
    const familia = familiaDe(caminho);
    return !!familia && !DO_EDITOR.has(familia.id);
}

export function enderecoDoViewer(caminho) {
    const origem = (typeof location !== 'undefined' && location.origin) || '';
    return origem + '/vendor/viewer/index.html#f=' + encodeURIComponent(caminho);
}
