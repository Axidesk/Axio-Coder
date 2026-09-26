import * as dom from './dom.js';
import { closeHistoryPanel, isHistoryOpen } from './layout.js';
import { esconderIconTooltip, mostrarIconTooltip } from './ui.js';
import { anexarOlho, carregarEtiquetas, criarControlesEstrutura } from './projeto_etiquetas.js';

const SVG_PASTA = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>';
const NOMES_LINGUAGEM = {
    '.py': 'Python',
    '.js': 'JavaScript',
    '.mjs': 'JavaScript',
    '.cjs': 'JavaScript',
    '.jsx': 'JavaScript',
    '.ts': 'TypeScript',
    '.tsx': 'TypeScript',
    '.html': 'HTML',
    '.css': 'CSS',
    '.json': 'JSON',
    '.md': 'Markdown',
    '.yaml': 'YAML',
    '.yml': 'YAML',
    '.toml': 'TOML',
    '.sh': 'Shell',
    '.cpp': 'C++',
    '.cc': 'C++',
    '.cxx': 'C++',
    '.h': 'C/C++',
    '.hpp': 'C/C++',
    '.c': 'C',
    '.java': 'Java',
    '.rs': 'Rust',
    '.go': 'Go',
    '.rb': 'Ruby',
    '.php': 'PHP',
};

let carregando = false;

document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('.projeto-pacote')) return;
    esconderIconTooltip();
});

function _el(tag, classe, texto) {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined && texto !== null) el.textContent = texto;
    return el;
}

function _numero(n) {
    return Number(n || 0).toLocaleString('pt-BR');
}

function _linhas(n) {
    return '(' + _numero(n) + ')';
}

function _nomeLinguagem(ext) {
    const chave = String(ext || '').toLowerCase();
    return NOMES_LINGUAGEM[chave] || chave.replace(/^\./, '').toUpperCase() || 'Outros';
}

function _cabecalho(titulo, resumo) {
    const el = _el('div', 'projeto-cabecalho');
    el.appendChild(_el('span', 'projeto-secao-titulo', titulo));
    if (resumo) {
        el.appendChild(_el('span', 'projeto-secao-sep', '|'));
        el.appendChild(_el('span', 'projeto-secao-resumo', resumo));
    }
    return el;
}

function _recolhivel(linha, bloco, mais) {
    linha.classList.add('projeto-linha-clicavel');
    linha.addEventListener('click', function () {
        const aberto = bloco.classList.toggle('projeto-aberto');
        if (mais) mais.textContent = aberto ? '−' : '+';
    });
}

function _blocoRecolhivel(nome, contagem, conteudo) {
    const bloco = _el('div', 'projeto-grupo');
    const linha = _el('div', 'projeto-linha');
    linha.appendChild(_el('span', 'projeto-nome', nome));
    if (contagem) linha.appendChild(_el('span', 'projeto-contagem', contagem));
    const mais = _el('span', 'projeto-mais', conteudo ? '+' : '');
    linha.appendChild(mais);
    bloco.appendChild(linha);
    const filhos = _el('div', 'projeto-filhos card-collapsible');
    const clip = _el('div', 'card-collapsible-clip');
    if (conteudo) {
        clip.appendChild(conteudo);
        _recolhivel(linha, bloco, mais);
    }
    filhos.appendChild(clip);
    bloco.appendChild(filhos);
    return bloco;
}

function _renderStack(stack) {
    const secao = _el('div');
    secao.appendChild(_cabecalho('Stack', stack));
    return secao;
}

function _renderLinguagens(linguagens) {
    const secao = _el('div');
    secao.appendChild(_cabecalho('Linguagens', _numero(linguagens.length)));
    linguagens.forEach(function (l) {
        const detalhe = _el('div', 'projeto-detalhe',
            _numero(l.arquivos) + (l.arquivos === 1 ? ' arquivo, ' : ' arquivos, ')
            + _numero(l.linhas) + (l.linhas === 1 ? ' linha' : ' linhas'));
        secao.appendChild(_blocoRecolhivel(_nomeLinguagem(l.ext), '', detalhe));
    });
    return secao;
}

function _normalizarPacote(nome) {
    return String(nome || '').replace(/[-_.]/g, '').toLowerCase();
}

function _spanPacote(nome) {
    const item = _el('span', 'projeto-pacote');
    item.dataset.pacote = _normalizarPacote(nome);
    item.appendChild(_el('span', 'projeto-pacote-nome', nome));
    item.addEventListener('click', function () {
        _mostrarTooltipPacote(item);
    });
    return item;
}

function _blocoDependencia(nome, contagem, itens) {
    if (!itens.length) return _blocoRecolhivel(nome, contagem, null);
    const grade = _el('div', 'projeto-pacotes');
    itens.forEach(function (p) {
        grade.appendChild(_spanPacote(p));
    });
    return _blocoRecolhivel(nome, contagem, grade);
}

function _renderDependencias(manifests, codigo) {
    const secao = _el('div');
    const naoDeclaradas = codigo.nao_declaradas || [];
    let declarados = 0;
    manifests.forEach(function (m) { declarados += (m.pacotes || []).length; });
    const total = declarados + (manifests.length ? 0 : naoDeclaradas.length);
    secao.appendChild(_cabecalho('Dependencias', total ? _numero(total) + ' pacotes' : ''));
    manifests.forEach(function (m) {
        const itens = m.pacotes || [];
        const contagem = itens.length
            ? '(' + _numero(itens.length) + ' ' + (m.rotulo || 'pacotes') + ')'
            : '(' + _numero(m.linhas) + ' linhas)';
        secao.appendChild(_blocoDependencia(m.manifesto, contagem, itens));
    });
    if (naoDeclaradas.length) {
        secao.appendChild(_blocoDependencia('usado no codigo',
            '(' + _numero(naoDeclaradas.length) + ' por declarar)', naoDeclaradas));
    }
    return secao;
}

function _noDaArvore(no, ehRaiz, caminho) {
    if (no.tipo === 'ficheiro') {
        const linha = _el('div', 'projeto-linha projeto-linha-ficheiro');
        linha.dataset.caminho = caminho;
        linha.appendChild(_el('span', 'projeto-nome', no.nome));
        linha.appendChild(_el('span', 'projeto-contagem', _linhas(no.linhas)));
        return linha;
    }
    const pasta = _el('div', ehRaiz ? 'projeto-pasta projeto-pasta-raiz' : 'projeto-pasta');
    if (!ehRaiz) pasta.classList.add('projeto-aberto');
    const linha = _el('div', 'projeto-linha projeto-linha-clicavel');
    linha.dataset.caminho = caminho;
    const icone = _el('span', 'projeto-icone-pasta');
    icone.innerHTML = SVG_PASTA;
    linha.appendChild(icone);
    linha.appendChild(_el('span', 'projeto-nome projeto-nome-pasta', no.nome));
    linha.appendChild(_el('span', 'projeto-contagem', _linhas(no.linhas)));
    linha.addEventListener('click', function () {
        pasta.classList.toggle('projeto-aberto');
    });
    pasta.appendChild(linha);
    const filhos = _el('div', 'projeto-filhos card-collapsible');
    const clip = _el('div', 'card-collapsible-clip');
    (no.filhos || []).forEach(function (f) {
        const abaixo = caminho ? caminho + '/' + f.nome : f.nome;
        clip.appendChild(_noDaArvore(f, false, abaixo));
    });
    filhos.appendChild(clip);
    pasta.appendChild(filhos);
    return pasta;
}

function _renderEstrutura(totais, arvore) {
    const secao = _el('div');
    const cabecalho = _cabecalho('Estrutura',
        _numero(totais.arquivos) + ' arquivos, ' + _numero(totais.pastas) + ' pastas');

    const coluna = _el('div', 'projeto-coluna-titulo');
    coluna.appendChild(_el('span', 'projeto-secao-titulo', 'Etiquetas'));
    const controlos = criarControlesEstrutura();
    coluna.appendChild(controlos.caixa);
    cabecalho.appendChild(coluna);
    secao.appendChild(cabecalho);
    anexarOlho(cabecalho, coluna);

    const corpo = _el('div', 'projeto-arvore');
    corpo.appendChild(_el('span', 'projeto-fio'));
    corpo.appendChild(_noDaArvore(arvore, true, ''));
    secao.appendChild(corpo);
    return secao;
}

function _render(corpo, dados) {
    const frag = document.createDocumentFragment();
    const codigo = dados.dependencias_codigo || {};
    if (dados.stack) frag.appendChild(_renderStack(dados.stack));
    if ((dados.linguagens || []).length) frag.appendChild(_renderLinguagens(dados.linguagens));
    if ((dados.manifests || []).length || (codigo.usadas || []).length) {
        frag.appendChild(_renderDependencias(dados.manifests || [], codigo));
    }
    if (dados.arvore) frag.appendChild(_renderEstrutura(dados.totais || {}, dados.arvore));
    corpo.replaceChildren(frag);
}

export function projetoInfoAberto() {
    return !!(dom.projectPanelContainer
        && !dom.projectPanelContainer.classList.contains('project-closed'));
}

export function abrirProjetoInfo() {
    if (!dom.projectPanelContainer) return;
    if (isHistoryOpen()) closeHistoryPanel();
    dom.projectPanelContainer.classList.remove('project-closed');
    if (dom.btnProjectInfo) dom.btnProjectInfo.classList.add('sidebar-active');
    carregarProjetoInfo();
}

export function fecharProjetoInfo() {
    if (!dom.projectPanelContainer) return;
    if (dom.btnProjectInfo) dom.btnProjectInfo.classList.remove('sidebar-active');
    dom.projectPanelContainer.classList.add('project-closed');
}

let consultaDesatualizados = 0;

function _tituloPacote(info, versao) {
    if (!info) return versao || '';
    const partes = [(info.atual || versao) + ' -> ' + info.ultima];
    if (info.preso) {
        partes.push(info.preso.dono + ' exige ' + info.preso.margem);
    }
    return partes.join(' | ');
}

function _mostrarTooltipPacote(item) {
    const texto = item.dataset.info;
    if (texto) mostrarIconTooltip(item, texto, true);
}

function marcarPacotesDesatualizados(pacotes, versoes) {
    if (!dom.projectInfoBody) return;
    const marcados = pacotes || {};
    const instaladas = versoes || {};
    dom.projectInfoBody.querySelectorAll('.projeto-pacote').forEach(function (item) {
        const chave = item.dataset.pacote;
        const info = marcados[chave];
        const versao = instaladas[chave] || '';
        const titulo = _tituloPacote(info, versao);

        if (titulo) {
            item.dataset.info = titulo;
        } else {
            delete item.dataset.info;
        }
        const marca = item.querySelector('.projeto-alerta');
        if (!info) {
            if (marca) marca.remove();
            return;
        }
        const alerta = marca || _el('span', 'projeto-alerta', 'i');
        alerta.classList.toggle('projeto-alerta-preso', !!info.preso);

        if (titulo) alerta.title = titulo;
        if (!marca) item.appendChild(alerta);
    });
}

function _esperar(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
}

async function _pedir(rota) {
    try {
        const resp = await fetch(rota);
        return await resp.json();
    } catch (e) {
        return null;
    }
}

async function _insistir(rota, estaPronto, aoProgresso, tentativas, espera) {
    let dados = null;
    for (let tentativa = 0; tentativa < tentativas; tentativa++) {
        dados = await _pedir(rota);
        if (!dados) return null;
        if (aoProgresso) aoProgresso(dados);
        if (estaPronto(dados)) return dados;
        await _esperar(espera);
    }
    return dados;
}

async function carregarDesatualizados() {
    const minha = ++consultaDesatualizados;
    await _insistir('/api/projeto/outdated',
        function (d) { return d.estado !== 'a_verificar'; },
        function (d) {
            if (minha !== consultaDesatualizados) return;
            marcarPacotesDesatualizados(d.pacotes, d.versoes);
        },
        20, 3000);
}


let retratoDesenhado = null;

export async function carregarProjetoInfo() {
    const corpo = dom.projectInfoBody;
    if (!corpo || carregando) return;
    carregando = true;
    try {

        let esqueleto = false;

        const [dados, etiquetas] = await Promise.all([
            _insistir('/api/projeto/info',
                function (d) { return d.estado !== 'a_medir' || !!d.erro; },
                function (d) {
                    if (esqueleto || d.estado !== 'a_medir' || d.erro) return;
                    esqueleto = true;
                    corpo.replaceChildren(_el('div', 'projeto-vazio', 'A medir o projeto...'));
                },
                40, 500),
            _pedir('/api/projeto/etiquetas')
        ]);
        if (!dados) {
            corpo.replaceChildren(_el('div', 'projeto-vazio', 'Nao foi possivel falar com o servidor.'));
            retratoDesenhado = null;
            return;
        }
        if (dados.erro) {
            corpo.replaceChildren(_el('div', 'projeto-vazio', dados.erro));
            retratoDesenhado = null;
            return;
        }
        const retrato = JSON.stringify(dados);

        if (esqueleto || retrato !== retratoDesenhado) {
            _render(corpo, dados);
            retratoDesenhado = retrato;
        }
        carregarEtiquetas(etiquetas);
        carregarDesatualizados();
    } finally {
        carregando = false;
    }
}
