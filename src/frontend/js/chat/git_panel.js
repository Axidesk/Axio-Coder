import { state } from './state.js';
import { vistaDe } from './colunas.js';
import { setCodeViewContent } from './files.js';
import { escapeHtml } from './messages.js';
import { btnGitEnviarHistory, btnGitAutoHistory, lblStatus } from './dom.js';
import { svgDoPonto } from './icones.js';
import { showConfirm } from './ui.js';
import { requestGitRestore, requestRestoreTask } from './historico/restauro.js';
import { esquecerIntencaoManual, marcarProximoComoManual } from './historico/marcas_envio.js';
import { nomeDaTarefaDoCommit, tituloDaTarefaDoCommit, updateRoundCardCommitByTurnId, carregarPorSubir, enviadaParaOServidor, reagruparPilhaDoDia } from './historico/cards.js';

const CHAVE_RASCUNHOS = 'axio.git.rascunhos';

const RASCUNHOS = new Map(Object.entries(rascunhosGuardados()));

const COMANDO_DE_DEPENDENCIA = {
    'requirements.txt': 'python -m pip install -r requirements.txt',
    'package.json': 'npm install'
};

const SVG_VARINHA = '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/></svg>';
const SVG_SPINNER = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="9" stroke-dasharray="42 15"/></svg>';
const SVG_LAPIS = '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>';
const SVG_RAMO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>';
const SVG_ETIQUETA = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/></svg>';

    function grupoAtivo() {
        return state.currentSelectedHistoryGroup || window.currentActiveLogGroup || null;
    }
    function nomeDaTarefa(grupo) {
        if (!grupo) return '';
        return grupo.displayName || grupo.title || grupo.name || '';
    }
    function valorDoCampo(grupo) {
        if (!grupo) return '';
        return RASCUNHOS.get(String(grupo.id)) || '';
    }
    function rascunhosGuardados() {
        if (typeof localStorage === 'undefined') return {};
        try {
            return JSON.parse(localStorage.getItem(CHAVE_RASCUNHOS) || '{}') || {};
        } catch (e) {
            return {};
        }
    }
    function guardarRascunhos() {
        if (typeof localStorage === 'undefined') return;
        try {
            localStorage.setItem(CHAVE_RASCUNHOS, JSON.stringify(Object.fromEntries(RASCUNHOS)));
        } catch (e) {
            console.warn('Nao consegui guardar o rascunho da mensagem:', e);
        }
    }
    function ficheirosDaTarefa(grupo) {
        return (grupo && grupo.files ? grupo.files : [])
            .map(f => (typeof f === 'string' ? f : f && f.name))
            .filter(Boolean);
    }
    function hashDaTarefa(grupo) {
        if (!grupo) return '';
        return grupo.commit || (state.commitsDosTurnos || {})[String(grupo.id)] || '';
    }
    function _pontaDoRamo(estado) {
        const ponta = ((estado && estado.commits) || []).find(c => c.head);
        return ponta ? ponta.hash : '';
    }
    function _podeEmendar(grupo, estado) {
        const hash = hashDaTarefa(grupo);
        if (!hash || !estado || !estado.repo) return false;
        const ponta = _pontaDoRamo(estado);
        if (ponta && ponta !== hash) return false;
        return (estado.por_subir || []).map(c => c.hash).includes(hash);
    }
    function mensagemDoPontoDaTarefa(estado, hash) {
        if (!hash || !estado) return '';
        const daLista = (estado.commits || []).find(c => c.hash === hash);
        if (daLista && daLista.mensagem) return daLista.mensagem;
        const pendente = (estado.por_subir || []).find(c => c.hash === hash);
        return pendente && pendente.mensagem ? pendente.mensagem : '';
    }
    function campoDaTarefa(vista, acao) {
        const painel = vista && vista.codigo ? vista.codigo : null;
        return {
            grupo: grupoAtivo(),
            campo: painel ? painel.querySelector('#git-mensagem') : null,
            botao: painel ? painel.querySelector(`[data-git-acao="${acao}"]`) : null
        };
    }
    async function pedirGit(url, corpo) {
        const opcoes = corpo
            ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) }
            : {};
        const resp = await fetch(url, opcoes);
        const texto = await resp.text();
        try {
            return JSON.parse(texto);
        } catch (e) {
            const amostra = String(texto || '').replace(/\s+/g, ' ').trim().slice(0, 160);
            return { status: 'error', message: `O servidor respondeu ${resp.status}${amostra ? ': ' + amostra : ''}` };
        }
    }
    function pill(acao, texto, extra) {
        return `<button class="git-pill ${extra || ''}" data-git-acao="${acao}">${escapeHtml(texto)}</button>`;
    }
    function varinha(acao, titulo, extra) {
        return `<button class="projeto-notas-acao ${extra || ''}" type="button" data-git-acao="${acao}" title="${escapeHtml(titulo)}">`
            + `<span class="projeto-icone-wand">${SVG_VARINHA}</span>`
            + `<span class="projeto-icone-spinner">${SVG_SPINNER}</span>`
            + '</button>';
    }
    function salvar(acao, titulo, extra) {
        return `<button class="projeto-notas-acao git-salvar${extra ? ' ' + extra : ''}" type="button" data-git-acao="${acao}" title="${escapeHtml(titulo)}">`
            + `<span class="projeto-icone-wand">${svgDoPonto('h-4 w-4')}</span>`
            + `<span class="projeto-icone-spinner">${SVG_SPINNER}</span>`
            + '</button>';
    }
    function lapis() {
        return '<button class="projeto-notas-acao git-lapis" type="button" data-git-acao="lapis" title="Corrigir a mensagem deste ponto">'
            + `<span class="projeto-icone-wand">${SVG_LAPIS}</span>`
            + '</button>';
    }
    function recolhivel(cabecalho, corpo, aberta, extra) {
        return `<div class="projeto-grupo git-recolhivel${extra ? ' ' + extra : ''}${aberta ? ' projeto-aberto' : ''}">`
            + `<div class="projeto-linha projeto-linha-clicavel" data-git-acao="recolher">${cabecalho}<span class="projeto-mais">${aberta ? '−' : '+'}</span></div>`
            + `<div class="projeto-filhos card-collapsible"><div class="card-collapsible-clip">${corpo}</div></div>`
            + '</div>';
    }
    function seccaoRecolhivel(titulo, resumo, corpo, chave, aberta) {
        let cabecalho = `<span class="projeto-secao-titulo">${escapeHtml(titulo)}</span>`;
        if (resumo) {
            cabecalho += '<span class="projeto-secao-sep">|</span>'
                + `<span class="projeto-secao-resumo">${escapeHtml(resumo)}</span>`;
        }
        return `<div class="projeto-grupo git-recolhivel${aberta ? ' projeto-aberto' : ''}"${chave ? ` data-git-seccao="${chave}"` : ''}>`
            + `<div class="projeto-cabecalho git-cabecalho-clicavel" data-git-acao="recolher">${cabecalho}<span class="projeto-mais">${aberta ? '−' : '+'}</span></div>`
            + `<div class="projeto-filhos card-collapsible"><div class="card-collapsible-clip">${corpo}</div></div>`
            + '</div>';
    }
    function linhaComTitulo(titulo, valor, valorEhHtml) {
        let linha = `<span class="git-seccao-titulo">${escapeHtml(titulo)}</span>`;
        if (!valor) return `<div class="git-titulo-linha">${linha}</div>`;
        return `<div class="git-titulo-linha">${linha}<span class="projeto-secao-sep">|</span>`
            + `<span class="git-identidade">${valorEhHtml ? valor : escapeHtml(valor)}</span></div>`;
    }
    async function comBotaoOcupado(botao, tarefa) {
        const antes = botao ? botao.disabled : false;
        if (botao) {
            botao.classList.add('a-trabalhar');
            botao.disabled = true;
        }
        try {
            return await tarefa();
        } finally {
            if (botao) {
                botao.classList.remove('a-trabalhar');
                botao.disabled = antes;
            }
        }
    }
    function alternarRecolhido(cabecalho) {
        const bloco = cabecalho.closest('.projeto-grupo');
        if (!bloco) return;
        const aberto = bloco.classList.toggle('projeto-aberto');
        const mais = cabecalho.querySelector('.projeto-mais');
        if (mais) mais.textContent = aberto ? '−' : '+';
    }
    function alternarEdicao(botao, forcar) {
        const linha = botao.closest('.git-campo-linha');
        if (!linha) return;
        const editando = typeof forcar === 'boolean' ? forcar : !linha.classList.contains('git-editando');
        linha.classList.toggle('git-editando', editando);
        botao.classList.toggle('git-acesa', editando);
        const campo = linha.querySelector('#git-mensagem');
        if (!campo) return;
        campo.readOnly = !editando;
        campo.classList.toggle('git-campo-trancado', !editando);
        if (editando) {
            campo.focus();
            campo.select();
            return;
        }
        const grupo = grupoAtivo();
        if (!grupo) return;
        campo.value = grupo.__mensagemDoPonto || '';
        RASCUNHOS.delete(String(grupo.id));
        guardarRascunhos();
    }
    function htmlSemRepo(motivo) {
        return `<div class="git-painel">
            <div class="git-seccao">
                <div class="git-seccao-titulo">Repositorio</div>
                <div class="git-vazio">${escapeHtml(motivo || 'Esta pasta nao e um repositorio git.')}</div>
                <div class="git-nota">Sem repositorio nao ha commit nem restauro por aqui. Cria um repositorio nesta pasta para usar o painel.</div>
            </div>
        </div>`;
    }
    function htmlCabecalho(estado, grupo, versaoDaTarefa) {
        const ramos = (estado.ramos || []).length || 1;
        let html = `<div class="git-seccao">${linhaComTitulo('Repositorio', estado.slug || 'repositorio local')}`;
        html += '<div class="git-ramo-linha">';
        html += `<span class="git-chip git-chip-acesa">${SVG_RAMO}<span class="git-chip-num">${ramos}</span>`
            + `<span class="git-chip-rotulo">${escapeHtml(estado.branch || 'sem ramo')}</span></span>`;
        html += '</div>';
        html += blocoDeEtiquetas(estado, grupo, versaoDaTarefa);
        html += '</div>';
        return html;
    }
    function chipDeEtiquetas(estado, versaoDaTarefa) {
        const tags = estado.tags || [];
        if (!tags.length) return '';
        const rotulo = versaoDaTarefa || (tags.length === 1 ? 'etiqueta' : 'etiquetas');
        return `<span class="git-chip${versaoDaTarefa ? ' git-chip-acesa' : ''}">`
            + SVG_ETIQUETA
            + `<span class="git-chip-num">${tags.length}</span>`
            + `<span class="git-chip-rotulo">${escapeHtml(rotulo)}</span>`
            + '</span>';
    }
    function listaDeEtiquetas(estado, grupo, versaoDaTarefa) {
        const tags = estado.tags || [];
        if (!tags.length) return '';
        const pontoDaTarefa = hashDaTarefa(grupo);
        const linhas = tags.map(t => {
            const nome = typeof t === 'string' ? t : t.nome;
            const ponto = typeof t === 'string' ? '' : t.ponto;
            const curto = typeof t === 'string' ? '' : t.curto;
            const acesa = (!!pontoDaTarefa && ponto === pontoDaTarefa)
                || (!!versaoDaTarefa && nome === versaoDaTarefa);
            const dono = ponto ? nomeDaTarefaDoCommit(ponto) : '';
            return `<div class="git-tag-linha${acesa ? ' git-tag-acesa' : ''}">`
                + `<span class="git-tag-nome">${escapeHtml(nome)}</span>`
                + (curto ? `<span class="git-tag-ponto">${escapeHtml(curto)}</span>` : '')
                + (dono ? `<span class="git-tag-dono">${escapeHtml(dono)}</span>` : '')
                + '</div>';
        }).join('');
        return `<div class="git-tags-vertical">${linhas}</div>`;
    }
    function blocoDeEtiquetas(estado, grupo, versaoDaTarefa) {
        if (!(estado.tags || []).length) return '';
        return recolhivel(
            chipDeEtiquetas(estado, versaoDaTarefa),
            listaDeEtiquetas(estado, grupo, versaoDaTarefa),
            false,
            'git-grupo-etiquetas'
        );
    }
    function htmlPorSubir(estado) {
        if (!estado.remoto) return '';
        const commits = estado.por_subir || [];
        let corpo = '';
        if (!commits.length) {
            corpo = '<div class="git-nota">Tudo o que esta commitado ja subiu para o remoto.</div>';
        } else {
            corpo = '<div class="git-lista">' + commits.map(c => {
                return `• ${escapeHtml(c.curto)} ${escapeHtml(tituloDaTarefaDoCommit(c.hash, c.mensagem))}`;
            }).join('<br>') + '</div>';
        }
        return seccaoRecolhivel('Por subir', commits.length ? String(commits.length) : 'nada', corpo, '', commits.length > 0);
    }
    function blocoDoPontoEnviado(hash, mensagem) {
        const curto = String(hash || '').slice(0, 7);
        let cabecalho = '<span class="git-seccao-titulo">Ja enviada para o GitHub</span>';
        if (curto) {
            cabecalho += '<span class="projeto-secao-sep">|</span>'
                + `<span class="git-hash">${escapeHtml(curto)}</span>`;
        }
        const titulo = tituloDaTarefaDoCommit(hash, mensagem);
        const corpo = titulo ? `<div class="git-ponto-nome">${escapeHtml(titulo)}</div>` : '';
        return recolhivel(cabecalho, corpo, false, 'git-ponto-enviado');
    }
    function htmlDaTarefa(grupo, pendentes, estado) {
        if (!grupo) {
            return `<div class="git-seccao">${linhaComTitulo('Esta tarefa', '')}`
                + '<div class="git-vazio">Seleciona uma tarefa no historico para ver o ponto dela.</div></div>';
        }
        const ficheiros = ficheirosDaTarefa(grupo);
        const pontoDaTarefa = hashDaTarefa(grupo);
        const porCommitar = pendentes && typeof pendentes.count === 'number' ? pendentes.count : null;
        const levou = (pendentes && pendentes.levou) || null;
        const noutroCommit = !pontoDaTarefa && porCommitar === 0 && !!levou;
        const vaiCommitar = !pontoDaTarefa && ficheiros.length > 0 && porCommitar !== 0;
        const mensagemDoPonto = mensagemDoPontoDaTarefa(estado, pontoDaTarefa);
        const podeCorrigir = !vaiCommitar && !!pontoDaTarefa && !!grupo.__podeEmendar;
        const ponta = _pontaDoRamo(estado);
        const notaTemDepois = pontoDaTarefa && ponta && ponta !== pontoDaTarefa
            ? '<div class="git-nota">Ha commits depois deste: a mensagem dele ja nao se muda.</div>'
            : '';
        const commitDeOutroJaEnviado = noutroCommit && enviadaParaOServidor(levou.hash);
        const donoDesteCommit = noutroCommit ? nomeDaTarefaDoCommit(levou.hash) : '';
        const notaNoutroCommit = noutroCommit && !commitDeOutroJaEnviado
            ? `<div class="git-nota">Estes ficheiros ja foram dentro do commit ${escapeHtml(levou.curto)}`
              + ` (${escapeHtml(donoDesteCommit || 'fora do painel')}) · ${escapeHtml(levou.mensagem)}`
              + ': esta tarefa nao guarda ponto proprio.</div>'
            : '';
        const pontoDaTarefaEnviado = enviadaParaOServidor(pontoDaTarefa);
        const enviado = pontoDaTarefaEnviado
            ? { hash: pontoDaTarefa, mensagem: mensagemDoPonto }
            : (commitDeOutroJaEnviado ? { hash: levou.hash, mensagem: levou.mensagem } : null);
        let html = '<div class="git-seccao">';
        html += enviado
            ? blocoDoPontoEnviado(enviado.hash, enviado.mensagem)
            : linhaComTitulo('Esta tarefa', nomeDaTarefa(grupo));
        html += notaTemDepois + notaNoutroCommit;
        if (vaiCommitar || podeCorrigir) {
            const rascunho = valorDoCampo(grupo);
            const editando = vaiCommitar || !!rascunho;
            const escrito = rascunho || (vaiCommitar ? '' : mensagemDoPonto);
            html += `<div class="git-campo-linha${editando ? ' git-editando' : ''}">`
                + `<input id="git-mensagem" class="git-campo${editando ? '' : ' git-campo-trancado'}" type="text" spellcheck="false"`
                + ` value="${escapeHtml(escrito)}"${editando ? '' : ' readonly'}`
                + ' placeholder="Mensagem do commit">'
                + varinha('sugerir', 'Escrever a mensagem com a IA', 'git-editavel')
                + salvar('salvar', descricaoDoSalvar(vaiCommitar), 'git-editavel')
                + (podeCorrigir ? lapis() : '')
                + '</div>';
        }
        html += '</div>';
        return html;
    }
    function descricaoDoSalvar(vaiCommitar) {
        if (vaiCommitar) return 'Guardar o ponto desta tarefa (so no PC; o envio e feito no fim do dia)';
        return 'Guardar a mensagem corrigida neste commit';
    }
    function descricaoDoEnvio(porSubir, vaiCommitar) {
        const commits = porSubir || [];
        const quantos = commits.length + (vaiCommitar ? 1 : 0);
        const acao = vaiCommitar ? 'Commitar esta tarefa e enviar' : 'Enviar';
        if (quantos <= 1) return vaiCommitar ? `${acao} para o GitHub` : 'Enviar para o GitHub';
        const nomes = commits.map(c => nomeDaTarefaDoCommit(c.hash)).filter(Boolean).slice(0, 3);
        if (!nomes.length) return `${acao} ${quantos} commits para o GitHub`;
        return `${acao} ${quantos} commits para o GitHub (${nomes.join(', ')}${nomes.length < quantos ? ', ...' : ''})`;
    }
    function htmlDependencias(estado) {
        const manifestos = estado.manifestos || [];
        if (!manifestos.length) return '';
        let html = '<div class="git-seccao"><div class="git-seccao-titulo">Dependencias</div>';
        html += `<div class="git-aviso">O manifesto mudou desde o ultimo commit: ${escapeHtml(manifestos.join(', '))}</div>`;
        html += '<div class="git-nota">O ambiente virtual nao entra no git (tem binarios da maquina). Restaurar codigo antigo pode pedir versoes antigas: compara-se o manifesto antes de instalar.</div>';
        html += `<div class="git-acoes">${pill('deps', 'Preparar as dependencias')}</div>`;
        html += '<div id="git-comando"></div>';
        html += '</div>';
        return html;
    }
    function mostrarComandoDeps(vista) {
        const painel = vista && vista.codigo ? vista.codigo.querySelector('.git-painel') : null;
        const caixa = painel ? painel.querySelector('#git-comando') : null;
        if (!caixa) return;
        const anterior = caixa.previousElementSibling;
        const alvo = anterior ? anterior.textContent : '';
        const comandos = Object.keys(COMANDO_DE_DEPENDENCIA)
            .filter(rel => alvo.includes(rel))
            .map(rel => COMANDO_DE_DEPENDENCIA[rel]);
        if (!comandos.length) {
            caixa.innerHTML = '<div class="git-nota">Nao identifiquei o gestor de pacotes deste projeto.</div>';
            return;
        }
        caixa.innerHTML = comandos.map(c => `<div class="git-comando">${escapeHtml(c)}</div>`).join('')
            + '<div class="git-nota">Corre este comando no terminal do Axio: a instalacao e longa e queres ver a saida. O ambiente virtual desta pasta fica pronto para a versao antiga do codigo.</div>';
    }
    function montarPainel(estado, grupo, pendentes, versaoDaTarefa) {
        if (!estado || !estado.repo) return htmlSemRepo(estado && estado.motivo);
        let html = '<div class="git-painel">';
        html += htmlCabecalho(estado, grupo, versaoDaTarefa);
        html += htmlDaTarefa(grupo, pendentes, estado);
        html += htmlPorSubir(estado);
        html += htmlDependencias(estado);
        html += '</div>';
        return html;
    }
    async function renderGitPanel(vista = vistaDe('historico')) {
        const alvo = vista || vistaDe('historico');
        setCodeViewContent('<div class="git-painel"><div class="git-vazio">A ler o repositorio…</div></div>', false, alvo);
        const grupo = grupoAtivo();
        const ficheiros = ficheirosDaTarefa(grupo);
        const hash = hashDaTarefa(grupo);
        let dados = null;
        let pendentes = null;
        let versaoDaTarefa = '';
        try {
            const pedidos = { estado: pedirGit('/api/git/estado') };
            if (ficheiros.length) pedidos.pendentes = pedirGit('/api/git/pendentes', { ficheiros });
            if (hash) pedidos.versao = pedirGit('/api/git/versao', { revisao: hash });
            const nomes = Object.keys(pedidos);
            const respostas = await Promise.all(nomes.map(nome => pedidos[nome]));
            const porNome = {};
            nomes.forEach((nome, i) => { porNome[nome] = respostas[i]; });
            dados = porNome.estado;
            pendentes = porNome.pendentes || null;
            versaoDaTarefa = (porNome.versao && porNome.versao.versao) || '';
        } catch (e) {
            console.error('Erro ao ler o repositorio:', e);
            dados = { status: 'error', message: `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}` };
        }
        const estado = dados && dados.estado ? dados.estado : { repo: false, motivo: (dados && dados.message) || 'Nao consegui ler o repositorio.' };
        if (grupo) {
            grupo.__pendentes = pendentes && typeof pendentes.count === 'number' ? pendentes.count : null;
            grupo.__podeEmendar = _podeEmendar(grupo, estado);
            grupo.__mensagemDoPonto = mensagemDoPontoDaTarefa(estado, hashDaTarefa(grupo));
        }
        setCodeViewContent(montarPainel(estado, grupo, pendentes, versaoDaTarefa), false, alvo);
        sincronizarCabecalhoGit(alvo, estado);
        ligarAcoes(alvo);
    }
    function ligarAcoes(vista) {
        const painel = vista && vista.codigo ? vista.codigo.querySelector('.git-painel') : null;
        if (!painel) return;
        painel.addEventListener('input', (e) => {
            if (!e.target || e.target.id !== 'git-mensagem') return;
            const grupo = grupoAtivo();
            if (!grupo) return;
            RASCUNHOS.set(String(grupo.id), e.target.value);
            guardarRascunhos();
        });
        painel.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape' || !e.target || e.target.id !== 'git-mensagem') return;
            const linha = e.target.closest('.git-campo-linha');
            const botao = linha ? linha.querySelector('[data-git-acao="lapis"]') : null;
            if (botao && linha.classList.contains('git-editando')) alternarEdicao(botao, false);
        });
        painel.addEventListener('click', async (e) => {
            const botao = e.target.closest('[data-git-acao]');
            if (!botao) return;
            e.stopPropagation();
            const acao = botao.dataset.gitAcao;
            if (acao === 'recolher') return alternarRecolhido(botao);
            if (acao === 'sugerir') return sugerirMensagem(vista);
            if (acao === 'deps') return mostrarComandoDeps(vista);
            if (acao === 'salvar') return salvarTarefa(vista);
            if (acao === 'lapis') return alternarEdicao(botao);
        });
    }
    async function salvarTarefa(vista) {
        const { grupo, campo, botao } = campoDaTarefa(vista, 'salvar');
        if (!grupo) return;
        if (botao && botao.disabled) return;
        const mensagem = campo ? campo.value.trim() : '';
        const ficheiros = ficheirosDaTarefa(grupo);
        const porCommitar = grupo.__pendentes;
        const podeCommitar = !hashDaTarefa(grupo) && ficheiros.length > 0 && porCommitar !== 0;
        if (podeCommitar && !mensagem) {
            avisarNoPainel(vista, 'Escreve a mensagem do commit ou usa a varinha antes de guardar.');
            return;
        }
        await comBotaoOcupado(botao, async () => {
            try {
                const commit = await gravarPonto(grupo, mensagem, ficheiros, podeCommitar);
                if (commit && commit.status !== 'ok') {
                    avisarNoPainel(vista, commit.message || 'Nao foi possivel commitar.');
                    return;
                }
                if (!commit) {
                    avisarNoPainel(vista, 'Nada para guardar: a mensagem e a mesma do ponto desta tarefa.');
                    return;
                }
                await renderGitPanel(vista);
            } catch (e) {
                console.error('Erro ao guardar o ponto da tarefa:', e);
                avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
            }
        });
    }
    async function enviarRepositorio(vista, botao) {
        await comBotaoOcupado(botao, async () => {
            try {
                const enviado = await pedirGit('/api/git/enviar', {});
                if (!enviado || enviado.status !== 'ok') {
                    esquecerIntencaoManual();
                    avisarNoPainel(vista, (enviado && enviado.message) || 'Nao foi possivel enviar para o GitHub.');
                    return;
                }
                marcarProximoComoManual();
                state.porSubirLido = false;
                await carregarPorSubir(true);
                const quantos = enviado.enviados || 0;
                await renderGitPanel(vista);
                if (!quantos) {
                    esquecerIntencaoManual();
                    avisarNoPainel(vista, 'O remoto ja tinha tudo: nada foi enviado.');
                }
            } catch (e) {
                console.error('Erro ao enviar para o git:', e);
                avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
            }
        });
    }
    async function alternarAutomatico(vista, botao) {
        const ligado = !(botao && botao.classList.contains('on'));
        const dados = await pedirGit('/api/git/automatico', { ligado });
        if (!dados || dados.status !== 'ok') {
            avisarNoPainel(vista, (dados && dados.message) || 'Nao consegui mudar o interruptor.');
            return;
        }
        await renderGitPanel(vista);
    }
    async function gravarPonto(grupo, mensagem, ficheiros, podeCommitar) {
        let corpo = null;
        if (podeCommitar) {
            corpo = {
                mensagem,
                ficheiros,
                filename: grupo.__session || '',
                round_id: grupo.id || ''
            };
        } else if (mensagem && grupo.__podeEmendar && mensagem !== grupo.__mensagemDoPonto) {
            corpo = {
                emendar: true,
                mensagem,
                revisao: hashDaTarefa(grupo),
                filename: grupo.__session || '',
                round_id: grupo.id || ''
            };
        }
        if (!corpo) return null;
        const resultado = await pedirGit('/api/git/commit', corpo);
        if (resultado && resultado.status === 'ok') {
            grupo.commit = resultado.hash || '';
            grupo.commitNome = (corpo.mensagem || '').trim();
            if (grupo.__saved) {
                grupo.__saved.commit = resultado.hash || '';
                grupo.__saved.commit_nome = grupo.commitNome;
            }
            state.commitsDosTurnos[String(grupo.id)] = resultado.hash || '';
            RASCUNHOS.delete(String(grupo.id));
            guardarRascunhos();
            updateRoundCardCommitByTurnId(grupo.id, resultado.hash || '');
            state.porSubirLido = false;
            await carregarPorSubir(true);
            await reagruparPilhaDoDia();
        }
        return resultado;
    }
    async function sugerirMensagem(vista) {
        const { grupo, campo, botao } = campoDaTarefa(vista, 'sugerir');
        if (!grupo) return;
        const perguntas = (grupo.questions || []).join(' ');
        const resposta = String(grupo.aiResponse || '').slice(0, 800);
        await comBotaoOcupado(botao, async () => {
            try {
                const dados = await pedirGit('/api/git/sugestao', {
                    ficheiros: ficheirosDaTarefa(grupo),
                    contexto: [perguntas, resposta].filter(Boolean).join('\n\n')
                });
                if (dados && dados.status === 'ok' && campo) {
                    campo.value = dados.mensagem;
                    RASCUNHOS.set(String(grupo.id), campo.value);
                    guardarRascunhos();
                } else {
                    avisarNoPainel(vista, (dados && dados.message) || 'Nao foi possivel sugerir uma mensagem.');
                }
            } catch (e) {
                console.error('Erro ao pedir a sugestao:', e);
                avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
            }
        });
    }
    async function restaurarTarefa(grupo) {
        const alvo = grupo || grupoAtivo();
        if (!alvo) return;
        const hash = hashDaTarefa(alvo);
        if (hash) {
            await requestGitRestore(hash, nomeDaTarefa(alvo) || 'esta tarefa', alvo.id || '');
            return;
        }
        if (alvo.__session) await requestRestoreTask(alvo);
    }
    function podeRestaurar(grupo) {
        return !!(grupo && (hashDaTarefa(grupo) || grupo.__session));
    }
    function sincronizarCabecalhoGit(vista, estado) {
        const info = estado && estado.repo ? estado : null;
        const porSubir = (info && info.por_subir) || [];
        pintarBotaoEnvio(info && info.remoto, porSubir.map(c => c.hash));
        if (btnGitAutoHistory) {
            const ligado = !!(info && info.automatico);
            btnGitAutoHistory.classList.toggle('hidden', !info);
            btnGitAutoHistory.classList.toggle('on', ligado);
            btnGitAutoHistory.setAttribute('aria-checked', ligado ? 'true' : 'false');
            btnGitAutoHistory.onclick = info ? (e) => {
                e.stopPropagation();
                alternarAutomatico(vista, btnGitAutoHistory);
            } : null;
        }
    }
    function pintarBotaoEnvio(remoto, hashes) {
        if (!btnGitEnviarHistory) return;
        const lista = hashes || [];
        const pode = !!remoto && lista.length > 0;
        const descricao = pode ? descricaoDoEnvio(lista.map(hash => ({ hash })), false) : '';
        btnGitEnviarHistory.classList.toggle('hidden', !remoto);
        btnGitEnviarHistory.disabled = !pode;
        btnGitEnviarHistory.title = pode ? descricao : 'Tudo o que esta commitado ja subiu';
        btnGitEnviarHistory.onclick = pode ? (e) => {
            e.stopPropagation();
            showConfirm('Deseja ' + descricao.charAt(0).toLowerCase() + descricao.slice(1) + '?', 'Enviar',
                () => enviarRepositorio(vistaDe('historico'), btnGitEnviarHistory));
        } : null;
    }
    function sincronizarBotaoEnvio() {
        pintarBotaoEnvio(state.temRemotoGit, state.commitsPorSubir || []);
    }
    function avisarNoPainel(vista, texto) {
        const painel = vista && vista.codigo ? vista.codigo.querySelector('.git-painel') : null;
        const visivel = painel && state.isShowingGit && typeof vista.col3Aberta === 'function' && vista.col3Aberta();
        if (!visivel) {
            avisarNaBarraDeEstado(texto);
            return;
        }
        const antigo = painel.querySelector('.git-erro');
        if (antigo) antigo.remove();
        const div = document.createElement('div');
        div.className = 'git-erro';
        div.textContent = texto;
        painel.prepend(div);
    }
    function avisarNaBarraDeEstado(texto) {
        if (!lblStatus) return;
        lblStatus.innerHTML = `<span class="text-red-400 font-bold">${escapeHtml(texto)}</span>`;
        window.lastStatusError = true;
    }


export {
    renderGitPanel,
    sincronizarBotaoEnvio,
    restaurarTarefa,
    podeRestaurar,
    grupoAtivo,
    ficheirosDaTarefa
};
