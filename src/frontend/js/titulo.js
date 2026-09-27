const CHAVE_DO_TEMA = 'axio-dock-theme';
const balao = document.getElementById('titulo-menu');
const botoes = [
    { el: document.getElementById('title-bar-exibir'), lista: itensExibir },
    { el: document.getElementById('title-bar-ferramentas'), lista: itensFerramentas }
];
let inspecionar = false;
let asan = false;
let plataforma = '';
let plataformas = [];
let aberto = null;
let zoom = 1;
let zoomMinimo = 0.5;
let zoomMaximo = 2;
const ESPERA_DO_ZOOM_MS = 400;

function ponte() {
    try {
        return window.require('electron').ipcRenderer;
    } catch (erro) {
        return null;
    }
}

function temaAtual() {
    try {
        return localStorage.getItem(CHAVE_DO_TEMA) === 'espacial' ? 'espacial' : 'dark';
    } catch (erro) {
        return 'dark';
    }
}

function itensExibir() {
    return [
        { rotulo: 'Tema Dark', marca: temaAtual() === 'dark', acao: 'tema', valor: 'dark' },
        { rotulo: 'Tema Cinza Espacial', marca: temaAtual() === 'espacial', acao: 'tema', valor: 'espacial' },
        { separador: true },
        { zoom: true },
        { separador: true },
        { rotulo: 'Recarregar', acao: 'reload' },
        { rotulo: 'Recarregar ignorando cache', atalho: 'Ctrl+Shift+R', acao: 'reload-sem-cache' },
        { separador: true },
        { rotulo: 'Reiniciar Backend', atalho: 'Ctrl+Shift+B', acao: 'reiniciar-backend' }
    ];
}

function itensFerramentas() {
    return [
        { rotulo: 'Dev Tools', atalho: 'Ctrl+Shift+I', acao: 'devtools' },
        { separador: true },
        { rotulo: 'Modo Inspecionar', marca: inspecionar, acao: 'inspect' },
        { grupo: 'C++', itens: [
            grupoDeCompilacao(),
            { separador: true },
            { rotulo: 'Depurar com AddressSanitizer', marca: asan, acao: 'asan' }
        ] }
    ];
}

function grupoDeCompilacao() {
    if (plataformas.length > 1) {
        return { grupo: 'Compilar', itens: plataformas.map((p) => ({
            grupo: p,
            nota: p === plataforma ? 'do projeto' : '',
            itens: configuracoesDeBuild(p)
        })) };
    }
    const unica = plataformas[0] || plataforma;
    return { grupo: unica ? 'Compilar (' + unica + ')' : 'Compilar', itens: configuracoesDeBuild(unica) };
}

function configuracoesDeBuild(plataformaEscolhida) {
    return [
        { rotulo: 'Debug', acao: 'compilar', valor: 'debug', plataforma: plataformaEscolhida },
        { rotulo: 'Release', acao: 'compilar', valor: 'release', plataforma: plataformaEscolhida },
        { rotulo: 'AddressSanitizer', acao: 'compilar', valor: 'asan', plataforma: plataformaEscolhida }
    ];
}

function agir(acao, valor) {
    const ipc = ponte();
    if (ipc) ipc.send('menu:acao', acao, valor);
}

function construirItem(item) {
    if (item.separador) {
        const traco = document.createElement('div');
        traco.className = 'titulo-separador';
        return traco;
    }
    if (item.grupo) return construirGrupo(item);
    if (item.zoom) return construirZoom();
    const botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'titulo-item';
    const marca = document.createElement('span');
    marca.className = 'titulo-marca';
    marca.textContent = item.marca ? '✓' : '';
    const rotulo = document.createElement('span');
    rotulo.textContent = item.rotulo;
    botao.append(marca, rotulo);
    if (item.atalho) {
        const atalho = document.createElement('span');
        atalho.className = 'titulo-atalho';
        atalho.textContent = item.atalho;
        botao.appendChild(atalho);
    }
    botao.addEventListener('click', () => {
        if (item.acao === 'compilar') {
            pedirCompilacao(item.valor, item.plataforma);
            fechar();
            return;
        }
        if (item.acao === 'inspect') inspecionar = !inspecionar;
        if (item.acao === 'asan') {
            asan = !asan;
            gravarAsan(asan);
        }
        agir(item.acao, item.valor);
        fechar();
    });
    return botao;
}

function aplicarZoom(valor) {
    zoom = valor;
    const ipc = ponte();
    if (ipc) ipc.send('menu:acao', 'zoom', valor);
}

function cabecaDeItem(rotulo, antes) {
    const cabeca = document.createElement('button');
    cabeca.type = 'button';
    cabeca.className = 'titulo-item';
    const marca = document.createElement('span');
    marca.className = 'titulo-marca';
    const texto = document.createElement('span');
    texto.textContent = rotulo;
    const seta = document.createElement('span');
    seta.className = 'titulo-seta';
    seta.textContent = '›';
    cabeca.append(marca, texto);
    if (antes) cabeca.appendChild(antes);
    cabeca.appendChild(seta);
    return cabeca;
}

function notaDeGrupo(texto) {
    const nota = document.createElement('span');
    nota.className = 'titulo-nota';
    nota.textContent = texto;
    return nota;
}

function construirZoom() {
    const bloco = document.createElement('div');
    bloco.className = 'titulo-zoom';

    const atual = document.createElement('span');
    atual.className = 'titulo-atalho';
    const cabeca = cabecaDeItem('Zoom', atual);

    const corpo = document.createElement('div');
    corpo.className = 'titulo-zoom-corpo';
    const barra = document.createElement('input');
    barra.type = 'range';
    barra.className = 'titulo-zoom-barra';
    barra.min = String(Math.round(zoomMinimo * 100));
    barra.max = String(Math.round(zoomMaximo * 100));
    barra.step = '10';
    barra.value = String(Math.round(zoom * 100));

    const mostrar = (valor) => {
        atual.textContent = Math.round(valor * 100) + '%';
    };
    mostrar(zoom);

    let agendado = null;
    const comprometer = () => {
        if (agendado) clearTimeout(agendado);
        agendado = null;
        aplicarZoom(Number(barra.value) / 100);
    };

    barra.addEventListener('input', () => {
        mostrar(Number(barra.value) / 100);
        if (agendado) clearTimeout(agendado);
        agendado = setTimeout(comprometer, ESPERA_DO_ZOOM_MS);
    });
    barra.addEventListener('change', comprometer);

    const repor = document.createElement('button');
    repor.type = 'button';
    repor.className = 'titulo-zoom-repor';
    repor.textContent = 'Repor 100%';
    repor.addEventListener('click', () => {
        barra.value = '100';
        mostrar(1);
        aplicarZoom(1);
    });

    cabeca.addEventListener('click', () => bloco.classList.toggle('aberto'));
    corpo.append(barra, repor);
    bloco.append(cabeca, corpo);
    return bloco;
}

function construirGrupo(item) {
    const bloco = document.createElement('div');
    bloco.className = 'titulo-grupo';

    const cabeca = cabecaDeItem(item.grupo, item.nota ? notaDeGrupo(item.nota) : null);

    const corpo = document.createElement('div');
    corpo.className = 'titulo-grupo-corpo';
    for (const filho of item.itens) corpo.appendChild(construirItem(filho));

    cabeca.addEventListener('click', (evento) => {
        evento.stopPropagation();
        bloco.classList.toggle('aberto');
    });
    bloco.append(cabeca, corpo);
    return bloco;
}

function repintarMenuAberto() {
    const ferramentas = botoes.find((b) => b.lista === itensFerramentas);
    if (aberto && ferramentas && aberto === ferramentas.el) abrir(aberto, itensFerramentas);
}

function gravarAsan(ligado) {
    fetch('/api/settings/parcial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ depurador: { asan: !!ligado } })
    }).catch(() => {});
}

function sincronizarAsan() {
    fetch('/api/settings').then((resposta) => resposta.json()).then((dados) => {
        asan = !!(((dados || {}).depurador) || {}).asan;
        const ipc = ponte();
        if (ipc) ipc.send('asan:set', asan);
    }).catch(() => {});
}

function atualizarPlataforma() {
    return fetch('/api/projeto/plataforma').then((resposta) => resposta.json()).then((dados) => {
        const nova = String((dados || {}).plataforma || '');
        const novas = ((dados || {}).plataformas || []).map(String);
        if (nova === plataforma && novas.join() === plataformas.join()) return;
        plataforma = nova;
        plataformas = novas;
        const ipc = ponte();
        if (ipc) ipc.send('build:plataforma', { plataforma: plataforma, plataformas: plataformas });
        repintarMenuAberto();
    }).catch(() => {});
}

function avisarStatus(texto) {
    const status = document.getElementById('lbl-status');
    if (status) status.textContent = texto;
}

function primeiraLinha(texto) {
    return String(texto || '').split('\n').find((linha) => linha.trim()) || '';
}

function pedirCompilacao(configuracao, plataformaEscolhida) {
    const alvo = plataformaEscolhida || plataforma;
    avisarStatus(alvo ? 'Compilando (' + configuracao + ', ' + alvo + ')...'
                      : 'Compilando (' + configuracao + ')...');
    const pedido = { configuracao: configuracao };
    if (alvo) pedido.plataforma = alvo;
    return fetch('/api/terminal/compilar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pedido)
    }).then((resposta) => resposta.json().then((dados) => ({ ok: resposta.ok, dados: dados }))
    ).then(({ ok, dados }) => {
        if (ok) return;
        avisarStatus(primeiraLinha((dados || {}).error) || 'Nao consegui compilar este projeto.');
    }).catch(() => avisarStatus('Nao consegui falar com o servidor para compilar.'));
}

function abrir(botao, lista) {
    fechar();
    balao.innerHTML = '';
    for (const item of lista()) balao.appendChild(construirItem(item));
    const caixa = botao.getBoundingClientRect();
    balao.style.left = Math.round(caixa.left) + 'px';
    balao.style.top = Math.round(caixa.bottom + 4) + 'px';
    balao.classList.add('menu-open');
    botao.classList.add('aberto');
    aberto = botao;
}

function fechar() {
    balao.classList.remove('menu-open');
    if (aberto) aberto.classList.remove('aberto');
    aberto = null;
}

for (const botao of botoes) {
    if (!botao.el) continue;
    botao.el.addEventListener('click', () => {
        if (aberto === botao.el) {
            fechar();
            return;
        }
        abrir(botao.el, botao.lista);
        if (botao.lista === itensFerramentas) atualizarPlataforma();
    });
}

document.addEventListener('click', (evento) => {
    if (!aberto) return;
    if (balao.contains(evento.target) || aberto.contains(evento.target)) return;
    fechar();
});

document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape') fechar();
});

const ipc = ponte();
if (ipc) {
    ipc.on('menu:set-inspect', (evento, ativo) => {
        inspecionar = !!ativo;
        repintarMenuAberto();
    });
    ipc.on('menu:set-asan', (evento, ativo) => {
        asan = !!ativo;
        gravarAsan(asan);
        repintarMenuAberto();
    });
    ipc.on('menu:compilar', (evento, configuracao, plataformaEscolhida) => {
        pedirCompilacao(configuracao, plataformaEscolhida);
    });
    ipc.on('menu:set-zoom', (evento, valor) => {
        zoom = Number(valor) || 1;
    });
    ipc.invoke('menu:zoom-atual').then((resposta) => {
        if (!resposta || !resposta.ok) return;
        zoom = resposta.zoom;
        zoomMinimo = resposta.minimo;
        zoomMaximo = resposta.maximo;
    }).catch(() => {});
    sincronizarAsan();
}

atualizarPlataforma();
