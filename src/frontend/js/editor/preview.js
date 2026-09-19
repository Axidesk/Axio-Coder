import { state } from './state.js';
import { setView } from './explorer.js';
import { abreNoViewer, enderecoDoViewer } from './familia_ficheiro.js';
import { abrirAbaDeFicheiro, abrirAbaWeb, ativarAlvoJaCarregado, definirAoTrocarDeAba, sincronizarEndereco } from './preview_abas.js';

const ESQUEMA_URL = /^[a-z][a-z0-9+.-]*:\/\//i;
const HOST_SEM_PORTA = /^(localhost|127\.0\.0\.1|\d{1,3}(\.\d{1,3}){3})(:\d+)?([/?#]|$)/i;
const HOST_NA_WEB = /^[\w-]+(\.[\w-]+)+(:\d+)?([/?#].*)?$/;
const EXTENSAO_DE_FICHEIRO = /\.(js|mjs|cjs|jsx|ts|tsx|json|html?|css|scss|py|pyw|md|txt|log|yml|yaml|toml|ini|env|csv|tsv|xlsx?|ods|docx?|odt|pptx?|odp|pdf|dxf|dwg|dwf|ifc|frag|step|stp|stl|obj|glb|gltf|skp|png|jpe?g|gif|webp|bmp|ico|svg|tiff?|mp4|webm|mov|mkv|mp3|wav|ogg|flac|zip|rar|7z|tar|gz|bat|cmd|ps1|sh|c|h|hpp|cpp|cxx|cc|cs|java|kt|go|rs|rb|php|sql|ipynb|xml|sln|vcxproj|ui|qrc|blend|max|f3d)$/i;
const MOTOR_DE_BUSCA = 'https://www.google.com/search?q=';
const FALHAS_SEM_QUEDA = /^(ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED|ERR_BLOCKED_BY_CLIENT)/;
const SEGUIR_PAINEL_MS = 460;
const SEGUIR_LAYOUT_MS = 140;
const DURACAO_USO_MS = 2600;
const DURACAO_AVISO_MS = 8000;
const ESPERA_ENTRADA_MS = 250;
const CAIXA_DE_RECURSO = { direita: 16, topo: 6, largura: 28, altura: 28 };
const CAMADAS_SEM_TAPAO = new Set(['sliding-panel-container', 'preview-float']);

const PAI_DO_ICONE = state.btnPreview ? state.btnPreview.parentElement : null;
let entradaEm = 0;
let iconeNaBarra = false;

let ipcRenderer = null;
try {
    ipcRenderer = window.require('electron').ipcRenderer;
} catch (e) {
    ipcRenderer = null;
}

function invocar(canal, ...args) {
    if (!ipcRenderer) return Promise.resolve(null);
    return ipcRenderer.invoke(canal, ...args).catch(() => null);
}

function enviar(canal, ...args) {
    if (!ipcRenderer) return;
    ipcRenderer.send(canal, ...args);
}

function normalizarAlvo(texto) {
    const alvo = String(texto || '').trim();
    if (!alvo) return '';
    if (/^[a-z][a-z0-9+.-]*:\/\//i.test(alvo)) return alvo;
    if (HOST_SEM_PORTA.test(alvo)) return 'http://' + alvo;
    if (/^[a-z]:[\\/]/i.test(alvo) || alvo.startsWith('\\\\')) return alvo;
    const raiz = state.rootPath || state.currentCwd || '';
    if (!raiz) return alvo;
    return raiz.replace(/[\\/]+$/, '') + '\\' + alvo.replace(/^[\\/]+/, '');
}

function pareceEnderecoWeb(texto) {
    if (/\s/.test(texto)) return false;
    if (HOST_SEM_PORTA.test(texto)) return false;
    if (!HOST_NA_WEB.test(texto)) return false;
    return !EXTENSAO_DE_FICHEIRO.test(texto);
}

function alvoEhEnderecoWeb(texto) {
    if (ESQUEMA_URL.test(texto)) return true;
    if (/^[a-z]:[\\/]/i.test(texto) || texto.startsWith('\\\\')) return false;
    if (HOST_SEM_PORTA.test(texto)) return true;
    return pareceEnderecoWeb(texto);
}

function urlDeBusca(texto) {
    return MOTOR_DE_BUSCA + encodeURIComponent(texto);
}

function mesmaPaginaWeb(a, b) {
    try {
        const x = new URL(a);
        const y = new URL(b);
        return x.origin === y.origin && x.pathname === y.pathname;
    } catch (erro) {
        return false;
    }
}

function alternativaHttp(pedido, urlFalhada) {
    if (!pedido || !pedido.de || !pedido.para) return '';
    return mesmaPaginaWeb(pedido.de, urlFalhada) ? pedido.para : '';
}

function quedaHttp(destino) {
    if (!destino || destino.tipo !== 'web' || !destino.implicito) return null;
    if (!/^https:\/\//i.test(destino.url)) return null;
    return { de: destino.url, para: 'http://' + destino.url.slice(8) };
}

function destinoDaBarra(texto) {
    const alvo = String(texto || '').trim();
    if (!alvo) return null;
    if (ESQUEMA_URL.test(alvo)) return { tipo: 'web', url: alvo, implicito: false };
    if (/^[a-z]:[\\/]/i.test(alvo) || alvo.startsWith('\\\\') || alvo.startsWith('/')) {
        return { tipo: 'ficheiro', alvo: alvo };
    }
    if (HOST_SEM_PORTA.test(alvo)) return { tipo: 'web', url: 'http://' + alvo, implicito: true };
    if (pareceEnderecoWeb(alvo)) return { tipo: 'web', url: 'https://' + alvo, implicito: true };
    if (EXTENSAO_DE_FICHEIRO.test(alvo) || /[\\/]/.test(alvo)) return { tipo: 'ficheiro', alvo: alvo };
    return { tipo: 'busca', url: urlDeBusca(alvo) };
}

function relativoAoProjeto(caminho) {
    const raiz = String(state.rootPath || state.currentCwd || '').replace(/[\\/]+$/, '').replace(/\//g, '\\');
    const alvo = String(caminho || '').replace(/\//g, '\\');
    if (!raiz) return alvo;
    const base = raiz.toLowerCase() + '\\';
    if (alvo.toLowerCase().startsWith(base)) return alvo.slice(base.length);
    return alvo;
}

function urlDeFicheiroLocal(caminho) {
    const raiz = String(state.rootPath || state.currentCwd || '').replace(/[\\/]+$/, '');
    if (!raiz) return '';
    const absoluto = (/^[a-z]:[\\/]/i.test(caminho) || caminho.startsWith('\\\\'))
        ? caminho
        : raiz + '\\' + caminho.replace(/^[\\/]+/, '');
    const alvo = absoluto.replace(/\\/g, '/');
    const base = raiz.replace(/\\/g, '/').replace(/\/+$/, '');
    const chave = (s) => s.toLowerCase();
    if (chave(alvo) !== chave(base) && !chave(alvo).startsWith(chave(base) + '/')) return '';
    const relativo = alvo.slice(base.length).replace(/^\//, '');
    if (!relativo) return '';
    return location.origin + '/preview/' + relativo.split('/').map(encodeURIComponent).join('/');
}

function caminhoDoUrlDeFicheiro(url) {
    try {
        const alvo = new URL(url);
        const caminho = decodeURIComponent(alvo.pathname).replace(/^\//, '');
        const comHost = alvo.host ? '\\\\' + alvo.host + '\\' + caminho : caminho;
        return comHost.replace(/\//g, '\\');
    } catch (erro) {
        return '';
    }
}

function urlDoTexto(texto) {
    if (ESQUEMA_URL.test(texto)) return texto;
    return (HOST_SEM_PORTA.test(texto) ? 'http://' : 'https://') + texto;
}

function bordaEsquerdaLivre() {
    const painel = document.getElementById('sliding-panel-container');
    if (!painel || painel.classList.contains('dock-closed')) return 0;
    return painel.getBoundingClientRect().right;
}

function limitesDoHost() {
    const host = state.previewHost;
    if (!host) return null;
    const caixa = host.getBoundingClientRect();
    if (!caixa.width || !caixa.height) return null;
    const esquerda = Math.max(caixa.left, bordaEsquerdaLivre());
    const largura = caixa.right - esquerda;
    if (largura <= 0) return null;
    return { x: esquerda, y: caixa.top, width: largura, height: caixa.height };
}

function estaTapado(limites) {
    const centro = document.elementFromPoint(
        limites.x + limites.width / 2,
        limites.y + limites.height / 2
    );
    if (!centro) return true;
    if (centro !== state.previewHost && !state.previewHost.contains(centro)) return true;
    return !!camadaFlutuante(limites);
}

function camadaFlutuante(limites) {
    for (const camada of document.body.children) {
        if (CAMADAS_SEM_TAPAO.has(camada.id)) continue;
        const estilo = getComputedStyle(camada);
        if (estilo.position !== 'fixed') continue;
        if (estilo.visibility === 'hidden' || estilo.opacity === '0' || estilo.pointerEvents === 'none') continue;
        const caixa = camada.getBoundingClientRect();
        if (!caixa.width || !caixa.height) continue;
        if (caixa.right <= limites.x || caixa.left >= limites.x + limites.width) continue;
        if (caixa.bottom <= limites.y || caixa.top >= limites.y + limites.height) continue;
        return camada;
    }
    return null;
}

function mudancaDeCamada(mutacao) {
    const alvo = mutacao.target;
    if (!alvo || alvo.nodeType !== 1) return false;
    if (alvo === document.body) return true;
    if (alvo.parentElement !== document.body) return false;
    return getComputedStyle(alvo).position === 'fixed';
}

function sincronizar() {
    if (!state.previewHost) return;
    const ativa = state.currentView === 'preview';
    const limites = ativa ? limitesDoHost() : null;
    const quer = !!limites && state.previewTemPagina && !estaTapado(limites);
    const estreia = quer && state.previewVisivelEnviado !== true;
    if (estreia) {
        if (!entradaEm) {
            entradaEm = performance.now();
            agendar(ESPERA_ENTRADA_MS);
        }
    } else {
        entradaEm = 0;
    }
    const mostrar = quer && (!estreia || performance.now() - entradaEm >= ESPERA_ENTRADA_MS);
    if (mostrar) enviar('preview:limites', limites);
    if (mostrar === state.previewVisivelEnviado) return;
    state.previewVisivelEnviado = mostrar;
    enviar('preview:visivel', mostrar);
}

function passoDeSincronia() {
    sincronizar();
    if (performance.now() < state.previewRafAte) {
        state.previewRaf = requestAnimationFrame(passoDeSincronia);
    } else {
        state.previewRaf = null;
    }
}

function agendar(duracao) {
    state.previewRafAte = Math.max(state.previewRafAte, performance.now() + (duracao || 0));
    if (state.previewRaf === null) {
        state.previewRaf = requestAnimationFrame(passoDeSincronia);
    }
}

function pintarAviso(erro) {
    if (state.previewErro) state.previewErro.classList.toggle('hidden', !erro);
    if (state.previewVazio) state.previewVazio.classList.toggle('hidden', !!erro || state.previewTemPagina);
    if (erro && state.previewErroTexto) state.previewErroTexto.textContent = erro;
}

function pintarEstado(estado) {
    if (!estado) return;
    const temUrl = !!estado.url;
    if (estado.carregando) {
        state.previewErroAtivo = false;
        if (temUrl) state.previewTemPagina = true;
        pintarAviso(null);
    } else if (temUrl && !state.previewErroAtivo) {
        state.previewTemPagina = true;
        pintarAviso(null);
    }
    if (estado.url) sincronizarEndereco(estado.url);
    if (state.previewBack) state.previewBack.disabled = !estado.podeVoltar;
    if (state.previewForward) state.previewForward.disabled = !estado.podeAvancar;
    if (state.previewBar) state.previewBar.classList.toggle('preview-carregando', !!estado.carregando);
    agendar();
}

function caixaDoIconeAVista() {
    if (!state.btnPreview) return null;
    const caixa = state.btnPreview.getBoundingClientRect();
    if (!caixa.width || !caixa.height) return null;
    if (caixa.bottom <= 0 || caixa.top >= window.innerHeight) return null;
    return caixa;
}

function memorizarIcone() {
    const caixa = caixaDoIconeAVista();
    if (!caixa) return false;
    state.previewIconeCaixa = {
        direita: window.innerWidth - caixa.right,
        topo: caixa.top,
        largura: caixa.width,
        altura: caixa.height
    };
    return true;
}

function esconderAvisoDeUso() {
    if (state.previewFloatTimer) {
        clearTimeout(state.previewFloatTimer);
        state.previewFloatTimer = null;
    }
    if (state.previewFloat) state.previewFloat.classList.remove('preview-float-visible');
}

function mostrarAvisoDeUso() {
    if (!state.previewFloat) return;
    if (memorizarIcone()) {
        esconderAvisoDeUso();
        return;
    }
    const caixa = state.previewIconeCaixa || CAIXA_DE_RECURSO;
    state.previewFloat.style.right = Math.max(0, Math.round(caixa.direita)) + 'px';
    state.previewFloat.style.top = Math.max(0, Math.round(caixa.topo)) + 'px';
    state.previewFloat.style.width = Math.max(1, Math.round(caixa.largura)) + 'px';
    state.previewFloat.style.height = Math.max(1, Math.round(caixa.altura)) + 'px';
    state.previewFloat.classList.add('preview-float-visible');
    if (state.previewFloatTimer) clearTimeout(state.previewFloatTimer);
    state.previewFloatTimer = window.setTimeout(esconderAvisoDeUso, DURACAO_AVISO_MS);
}

function marcarUsoDoPreview(uso) {
    const interage = !!(uso && uso.interage);
    if (interage && state.currentView !== 'preview') setView('preview');
    agendar(interage ? SEGUIR_LAYOUT_MS : 0);
    if (state.btnPreview) {
        state.btnPreview.classList.add('preview-em-uso');
        if (state.previewUsoTimer) clearTimeout(state.previewUsoTimer);
        state.previewUsoTimer = window.setTimeout(() => {
            state.previewUsoTimer = null;
            state.btnPreview.classList.remove('preview-em-uso');
        }, DURACAO_USO_MS);
    }
    mostrarAvisoDeUso();
}

function posicionarIconeNaBarra(naBarra) {
    if (!state.btnPreview || iconeNaBarra === naBarra) return;
    const destino = naBarra ? state.previewBar : PAI_DO_ICONE;
    if (!destino) return;
    iconeNaBarra = naBarra;
    state.btnPreview.classList.toggle('preview-btn', naBarra);
    destino.appendChild(state.btnPreview);
}

function destinoDaAba(aba) {
    if (aba.tipo === 'web') return aba.alvo;
    const alvo = String(aba.alvo || '');
    if (abreNoViewer(alvo)) return enderecoDoViewer(alvo);
    const absoluto = normalizarAlvo(alvo);
    if (/^[a-z]:[\\/]/i.test(absoluto) || absoluto.startsWith('\\\\')) {
        return urlDeFicheiroLocal(absoluto) || absoluto;
    }
    return absoluto;
}

export function abrirPreviewDoFicheiro(caminho) {
    const texto = String(caminho || '').trim();
    if (!texto) return null;
    setView('preview');
    if (alvoEhEnderecoWeb(texto)) return abrirAbaWeb(urlDoTexto(texto));
    return abrirAbaDeFicheiro(relativoAoProjeto(texto));
}

function refletirAlvoDoPreview(url) {
    const alvo = String(url || '').trim();
    if (!alvo) return null;
    if (/^file:/i.test(alvo)) {
        const caminho = caminhoDoUrlDeFicheiro(alvo);
        return caminho ? ativarAlvoJaCarregado(relativoAoProjeto(caminho), 'ficheiro') : null;
    }
    if (!ESQUEMA_URL.test(alvo)) return null;
    return ativarAlvoJaCarregado(alvo, 'web');
}

function atualizarOpcoesDoFicheiro(aba) {
    if (!state.previewOpcoes) return;
    const pode = !!(aba && aba.tipo === 'ficheiro' && abreNoViewer(aba.alvo));
    state.previewOpcoes.disabled = !pode;
}

async function abrirAba(aba) {
    atualizarOpcoesDoFicheiro(aba);
    if (!aba) {
        state.previewTemPagina = false;
        state.previewUltimoAlvo = '';
        state.previewErroAtivo = false;
        pintarAviso(null);
        agendar();
        return false;
    }
    return carregarNaVista(destinoDaAba(aba));
}

async function executarAcao(acao, valor) {
    const resposta = await invocar('preview:acao', acao, valor);
    if (resposta && resposta.ok === false && resposta.erro && state.previewErroTexto) {
        state.wsStatus.textContent = resposta.erro;
    }
    return resposta;
}

function carregarDaBarra() {
    const texto = (state.previewAddress ? state.previewAddress.value : '').trim();
    if (!texto) return;
    if (state.currentView !== 'preview') setView('preview');
    const destino = destinoDaBarra(texto);
    if (!destino) return;
    if (destino.tipo === 'ficheiro') {
        state.previewQuedaHttp = null;
        abrirAbaDeFicheiro(relativoAoProjeto(destino.alvo));
        return;
    }
    state.previewQuedaHttp = quedaHttp(destino);
    abrirAbaWeb(destino.url, true);
}

async function alternarFerramentasDoFicheiro() {
    state.previewFerramentas = !state.previewFerramentas;
    if (state.previewOpcoes) {
        state.previewOpcoes.classList.toggle('preview-btn-ativo', state.previewFerramentas);
        state.previewOpcoes.title = state.previewFerramentas ? 'Ocultar as ferramentas do ficheiro' : 'Mostrar as ferramentas do ficheiro';
    }
    await executarAcao('ferramentas', state.previewFerramentas);
    agendar(SEGUIR_LAYOUT_MS);
}

async function carregarNaVista(destino) {
    if (!destino) {
        pintarAviso('Endereço vazio.');
        agendar();
        return false;
    }
    state.previewErroAtivo = false;
    pintarAviso(null);
    const resposta = await invocar('preview:carregar', destino);
    if (!resposta || !resposta.ok) {
        state.previewTemPagina = false;
        state.previewErroAtivo = true;
        pintarAviso((resposta && resposta.erro) || 'Não foi possível carregar o endereço.');
        agendar();
        return false;
    }
    state.previewTemPagina = true;
    state.previewUltimoAlvo = destino;
    agendar(SEGUIR_LAYOUT_MS);
    return true;
}

function ligarBarra() {
    if (state.previewFloat) {
        state.previewFloat.addEventListener('click', () => {
            esconderAvisoDeUso();
            if (state.currentView !== 'preview') setView('preview');
            agendar(SEGUIR_LAYOUT_MS);
        });
    }
    if (state.previewBack) state.previewBack.addEventListener('click', () => executarAcao('voltar'));
    if (state.previewForward) state.previewForward.addEventListener('click', () => executarAcao('avancar'));
    if (state.previewReload) state.previewReload.addEventListener('click', () => executarAcao('recarregar'));
    if (state.previewExternal) state.previewExternal.addEventListener('click', () => executarAcao('externo'));
    if (state.previewOpcoes) {
        state.previewOpcoes.addEventListener('click', () => alternarFerramentasDoFicheiro());
    }
    if (state.previewFile) {
        state.previewFile.addEventListener('click', async () => {
            const resposta = await executarAcao('ficheiro', state.rootPath);
            if (resposta && resposta.ok) {
                state.previewTemPagina = true;
                state.previewErroAtivo = false;
                pintarAviso(null);
                agendar(SEGUIR_LAYOUT_MS);
            }
        });
    }
    if (state.previewAddress) {
        state.previewAddress.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                state.previewAddress.blur();
                carregarDaBarra();
            } else if (e.key === 'Escape') {
                state.previewAddress.value = state.previewUltimoAlvo || '';
                state.previewAddress.blur();
            }
        });
    }
}

function ligarEventos() {
    if (ipcRenderer) {
        ipcRenderer.on('preview:estado', (e, estado) => pintarEstado(estado));
        ipcRenderer.on('preview:novo', () => {
            state.previewVisivelEnviado = null;
            agendar();
        });
        ipcRenderer.on('preview:uso', (e, uso) => marcarUsoDoPreview(uso));
        ipcRenderer.on('preview:alvo', (e, dados) => refletirAlvoDoPreview(dados && dados.alvo));
        ipcRenderer.on('menu:set-zoom', () => agendar(SEGUIR_LAYOUT_MS));
        ipcRenderer.on('preview:erro', (e, falha) => {
            const descricao = (falha && falha.descricao) || '';
            const alternativa = alternativaHttp(state.previewQuedaHttp, (falha && falha.url) || '');
            state.previewQuedaHttp = null;
            if (alternativa && !FALHAS_SEM_QUEDA.test(descricao)) {
                abrirAbaWeb(alternativa, true);
                return;
            }
            state.previewErroAtivo = true;
            state.previewTemPagina = false;
            pintarAviso((falha && (falha.descricao || falha.url)) || 'Falha ao carregar.');
            agendar();
        });
    }
    window.addEventListener('axio-preview-open', (e) => {
        const detalhe = e.detail || {};
        if (!detalhe.path) return;
        if (detalhe.auto && state.currentView === 'preview' && state.previewUltimoAlvo === detalhe.path) return;
        abrirPreviewDoFicheiro(detalhe.path);
    });
    window.addEventListener('axio-view-change', (e) => {
        posicionarIconeNaBarra(!!(e.detail && e.detail.view === 'preview'));
        agendar(SEGUIR_LAYOUT_MS);
    });
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && !e.shiftKey && !e.altKey && (e.key === 'l' || e.key === 'L')) {
            if (state.currentView !== 'preview' || !state.previewAddress) return;
            e.preventDefault();
            state.previewAddress.focus();
            state.previewAddress.select();
        }
    });
}

function vigiarLayout() {
    if (typeof ResizeObserver === 'function') {
        const vigia = new ResizeObserver(() => agendar(SEGUIR_LAYOUT_MS));
        if (state.previewHost) vigia.observe(state.previewHost);
        if (state.previewView) vigia.observe(state.previewView);
    }
    window.addEventListener('resize', () => agendar(SEGUIR_LAYOUT_MS));
    if (typeof MutationObserver === 'function') {
        new MutationObserver((mutacoes) => {
            if (mutacoes.some(mudancaDeCamada)) agendar(SEGUIR_LAYOUT_MS);
        }).observe(document.body, {
            attributes: true,
            subtree: true,
            attributeFilter: ['class', 'style']
        });
    }
    const painel = document.getElementById('sliding-panel-container');
    if (!painel) return;
    new MutationObserver(() => agendar(SEGUIR_PAINEL_MS)).observe(painel, {
        attributes: true,
        attributeFilter: ['class']
    });
    painel.addEventListener('transitionend', () => agendar(SEGUIR_LAYOUT_MS));
}

definirAoTrocarDeAba((aba) => {
    if (aba && state.currentView !== 'preview') setView('preview');
    return abrirAba(aba);
});

ligarBarra();
ligarEventos();
vigiarLayout();
atualizarOpcoesDoFicheiro(null);
agendar();
