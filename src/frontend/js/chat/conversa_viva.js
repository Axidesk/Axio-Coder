// sessionStorage: sobrevive a recarregar a janela e morre quando ela fecha - e isso que faz a conversa voltar so no reinicio pedido, e nunca numa abertura limpa.
const CHAVE = 'axio-conversa-viva';
const RODADAS_GUARDADAS = 14;
const TAMANHOS_DE_EMERGENCIA = [RODADAS_GUARDADAS, 6, 2];
const CLASSES_TRANSIENTES = ['conversa-saindo', 'conversa-busca-fora', 'conversa-busca-casa'];
const ATRIBUTO_DE_ESCUTA = 'data-listener-attached';

const rearranjos = [];
const blocos = new Map();

export function aoRestaurar(fn) {
    if (typeof fn === 'function') rearranjos.push(fn);
}

export function registrarBloco(chave, capturar, restaurar) {
    if (typeof capturar === 'function' && typeof restaurar === 'function') {
        blocos.set(chave, { capturar, restaurar });
    }
}

function capturarBlocos(quantas) {
    const guardados = {};
    blocos.forEach((bloco, chave) => {
        try {
            const valor = bloco.capturar(quantas);
            if (valor !== undefined) guardados[chave] = valor;
        } catch (e) {
            console.error('Falha ao capturar o bloco ' + chave + ':', e);
        }
    });
    return guardados;
}

function restaurarBlocos(guardados) {
    blocos.forEach((bloco, chave) => {
        if (!guardados || !(chave in guardados)) return;
        try {
            bloco.restaurar(guardados[chave]);
        } catch (e) {
            console.error('Falha ao restaurar o bloco ' + chave + ':', e);
        }
    });
}

function paineis() {
    return [
        { inner: document.getElementById('chat-inner-left'), rolagem: document.getElementById('chat-container-left') },
        { inner: document.getElementById('chat-inner-right'), rolagem: document.getElementById('chat-container-right') },
    ].filter((par) => par.inner);
}

function recorte(el, quantas) {
    const filhos = Array.from(el.children).slice(-quantas);
    return filhos.map((filho) => {
        const copia = filho.cloneNode(true);
        copia.style.removeProperty('opacity');
        copia.style.removeProperty('transform');
        CLASSES_TRANSIENTES.forEach((classe) => {
            copia.classList.remove(classe);
            copia.querySelectorAll('.' + classe).forEach((no) => no.classList.remove(classe));
        });
        copia.removeAttribute(ATRIBUTO_DE_ESCUTA);
        copia.querySelectorAll('[' + ATRIBUTO_DE_ESCUTA + ']').forEach((no) => no.removeAttribute(ATRIBUTO_DE_ESCUTA));
        return copia.outerHTML;
    }).join('');
}

function chaveDaArea() {
    const fn = window.__axioAreaAtiva;
    return typeof fn === 'function' ? (fn() || 'principal') : 'principal';
}

function lerMapa() {
    let bruto = null;
    try {
        bruto = JSON.parse(sessionStorage.getItem(CHAVE) || 'null');
    } catch (e) {
        return {};
    }
    if (!bruto) return {};
    if (Array.isArray(bruto) || bruto.paineis) return {};
    return bruto;
}

function gravarMapa(mapa) {
    try {
        sessionStorage.setItem(CHAVE, JSON.stringify(mapa));
        return true;
    } catch (e) {
        return false;
    }
}

export function guardarConversa() {
    const partes = paineis();
    if (!partes.length) return false;
    const chave = chaveDaArea();
    for (const quantas of TAMANHOS_DE_EMERGENCIA) {
        const dados = partes.map((par) => ({
            html: recorte(par.inner, quantas),
            rolagem: par.rolagem ? par.rolagem.scrollTop : 0,
        }));
        if (!dados.some((dado) => dado.html)) return false;
        // painel vazio NAO apaga o que ja esta guardado: um bug que limpe a tela nao leva a conversa com ele.
        const mapa = lerMapa();
        mapa[chave] = { paineis: dados, blocos: capturarBlocos(quantas) };
        if (gravarMapa(mapa)) return true;
    }
    return false;
}

export function restaurarConversa() {
    const dados = lerMapa()[chaveDaArea()] || null;
    const paineisGuardados = Array.isArray(dados) ? dados : ((dados && dados.paineis) || []);
    const blocosGuardados = (dados && !Array.isArray(dados) && dados.blocos) || {};
    if (!Array.isArray(paineisGuardados) || !paineisGuardados.length) return false;
    const partes = paineis();
    if (!partes.length) return false;
    const comConteudo = [];
    partes.forEach((par, indice) => {
        const guardado = paineisGuardados[indice];
        if (!guardado || !guardado.html) return;
        par.inner.classList.add('conversa-restaurada');
        par.inner.innerHTML = guardado.html;
        comConteudo.push({ par, rolagem: guardado.rolagem || 0 });
    });
    if (!comConteudo.length) return false;
    const assentarRolagem = () => comConteudo.forEach((item) => {
        if (item.par.rolagem) item.par.rolagem.scrollTop = item.rolagem;
    });
    assentarRolagem();
    setTimeout(() => {
        comConteudo.forEach((item) => item.par.inner.classList.remove('conversa-restaurada'));
        assentarRolagem();
    }, 320);
    restaurarBlocos(blocosGuardados);
    rearranjos.forEach((fn) => {
        try {
            fn();
        } catch (e) {
            console.error('Falha ao rearranjar a conversa restaurada:', e);
        }
    });
    return true;
}

export function esquecerConversa() {
    const mapa = lerMapa();
    const chave = chaveDaArea();
    if (!(chave in mapa)) return;
    delete mapa[chave];
    if (Object.keys(mapa).length === 0) {
        try { sessionStorage.removeItem(CHAVE); } catch (e) {}
        return;
    }
    gravarMapa(mapa);
}

export function reiniciarAInterface() {
    guardarConversa();
    let ipcRenderer = null;
    try {
        ipcRenderer = window.require('electron').ipcRenderer;
    } catch (e) {
        ipcRenderer = null;
    }
    if (!ipcRenderer) return false;
    ipcRenderer.send('interface:reiniciar');
    return true;
}
