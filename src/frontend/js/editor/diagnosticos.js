const EXTENSOES = new Set([
    'c', 'cc', 'cpp', 'cxx', 'h', 'hh', 'hpp', 'hxx', 'inl', 'ipp', 'm', 'mm', 'asm',
    'cs', 'rs', 'go', 'java', 'kt', 'swift', 'rb', 'php', 'pl', 'lua',
    'py', 'pyw', 'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'vue', 'svelte',
    'qml', 'qrc', 'ui', 'pro', 'pri', 'cmake', 'txt',
    'json', 'xml', 'yml', 'yaml', 'toml', 'md', 'html', 'css', 'scss',
    'glsl', 'vert', 'frag', 'comp', 'hlsl', 'rc', 'def', 'idl', 'natvis',
    'sln', 'vcxproj', 'vcproj', 'filters', 'props', 'targets',
    'bat', 'cmd', 'ps1', 'sh', 'sql', 'csv', 'ini', 'conf', 'env'
]);

const RE_ALVO = /((?:[A-Za-z]:[\\/])?(?:[^\\/\s()<>"':]+[\\/])*[^\\/\s()<>"':]+\.([A-Za-z0-9]{1,10}))[\(\:](\d{1,6})(?:[,:](\d{1,6}))?[\)\:]?/g;
const RE_TRACO = /File "([^"]+\.([A-Za-z0-9]{1,10}))", line (\d{1,6})/g;

const LIMITE_CACHE = 600;
const LIMITE_LINHA = 1000;
const cacheResolvidos = new Map();

function _varredura(linha, re) {
    const achados = [];
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(linha)) !== null) {
        if (m[0].length === 0) {
            re.lastIndex += 1;
            continue;
        }
        achados.push({ m: m, inicio: m.index, fim: m.index + m[0].length });
    }
    return achados;
}

function _candidatos(linha) {
    const achados = [];
    _varredura(linha, RE_ALVO).forEach((a) => achados.push({
        inicio: a.inicio, fim: a.fim, caminho: a.m[1], ext: a.m[2],
        linha: parseInt(a.m[3], 10) || 0, coluna: parseInt(a.m[4], 10) || 0
    }));
    _varredura(linha, RE_TRACO).forEach((a) => achados.push({
        inicio: a.inicio, fim: a.fim, caminho: a.m[1], ext: a.m[2],
        linha: parseInt(a.m[3], 10) || 0, coluna: 0
    }));
    return achados
        .filter((a) => EXTENSOES.has(String(a.ext).toLowerCase()))
        .sort((a, b) => a.inicio - b.inicio);
}

function _modulo(nome) {
    try {
        return window.require(nome);
    } catch (e) {
        return null;
    }
}

function _resolver(caminho, cwd) {
    const path = _modulo('path');
    const fs = _modulo('fs');
    let alvo = caminho;
    if (path && !path.isAbsolute(alvo)) {
        if (!cwd) return '';
        alvo = path.join(cwd, alvo);
    }
    if (fs) {
        try {
            if (!fs.existsSync(alvo)) return '';
        } catch (e) {
            return '';
        }
    }
    return alvo.replace(/\\/g, '/');
}

export function partesDaLinha(linha) {
    const partes = [];
    if (linha.length > LIMITE_LINHA) {
        partes.push({ texto: linha });
        return partes;
    }
    let ultimo = 0;
    for (const alvo of _candidatos(linha)) {
        if (alvo.inicio < ultimo) continue;
        if (alvo.inicio > ultimo) partes.push({ texto: linha.slice(ultimo, alvo.inicio) });
        partes.push({
            texto: linha.slice(alvo.inicio, alvo.fim),
            caminho: alvo.caminho,
            linha: alvo.linha,
            coluna: alvo.coluna
        });
        ultimo = alvo.fim;
    }
    if (ultimo < linha.length) partes.push({ texto: linha.slice(ultimo) });
    return partes;
}

export function resolverAlvo(caminho, cwd) {
    if (!caminho) return '';
    const chave = (cwd || '') + '\n' + caminho;
    if (cacheResolvidos.has(chave)) return cacheResolvidos.get(chave);
    const resolvido = _resolver(caminho, cwd);
    if (cacheResolvidos.size > LIMITE_CACHE) cacheResolvidos.clear();
    cacheResolvidos.set(chave, resolvido);
    return resolvido;
}

export function abrirAlvo(caminho, linha, cwd) {
    const alvo = resolverAlvo(caminho, cwd);
    if (!alvo) return false;
    if (!window.WorkspaceView || typeof window.WorkspaceView.openFileAtLine !== 'function') return false;
    window.WorkspaceView.openFileAtLine(alvo, linha || 1);
    return true;
}

function _alvoEl(parte, cwd) {
    const el = document.createElement('span');
    el.className = 'term-diag';
    el.textContent = parte.texto;
    el.title = 'Abrir ' + parte.caminho + (parte.linha ? ':' + parte.linha : '');
    el.addEventListener('click', (e) => {
        e.stopPropagation();
        abrirAlvo(parte.caminho, parte.linha, cwd);
    });
    return el;
}

export function fragmentoDeSaida(texto, cwd) {
    const frag = document.createDocumentFragment();
    const conteudo = String(texto == null ? '' : texto);
    if (!conteudo) return frag;
    const linhas = conteudo.split('\n');
    let acumulado = '';
    for (let i = 0; i < linhas.length; i++) {
        const fim = i < linhas.length - 1 ? '\n' : '';
        const partes = partesDaLinha(linhas[i]);
        if (!partes.some((p) => p.caminho && resolverAlvo(p.caminho, cwd))) {
            acumulado += linhas[i] + fim;
            continue;
        }
        for (const parte of partes) {
            if (!parte.caminho || !resolverAlvo(parte.caminho, cwd)) {
                acumulado += parte.texto;
                continue;
            }
            if (acumulado) {
                frag.appendChild(document.createTextNode(acumulado));
                acumulado = '';
            }
            frag.appendChild(_alvoEl(parte, cwd));
        }
        acumulado += fim;
    }
    if (acumulado) frag.appendChild(document.createTextNode(acumulado));
    return frag;
}
