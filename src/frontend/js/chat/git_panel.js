import { state } from './state.js';
import { vistaDe } from './colunas.js';
import { setCodeViewContent } from './files.js';
import { escapeHtml } from './messages.js';
import { btnGitRestoreHistory } from './dom.js';
import { requestGitRestore, requestRestoreTask } from './historico/restauro.js';
import { nomeDaTarefaDoCommit, updateRoundCardCommitByTurnId } from './historico/cards.js';

const LIMITE_COMMITS = 12;
const LIMITE_FICHEIROS = 12;

const RASCUNHOS = new Map();

const COMANDO_DE_DEPENDENCIA = {
    'requirements.txt': 'python -m pip install -r requirements.txt',
    'package.json': 'npm install'
};

const SVG_VARINHA = '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/></svg>';
const SVG_SPINNER = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="12" cy="12" r="9" stroke-dasharray="42 15"/></svg>';
const SVG_AVIAO = '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>';

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
    function ficheirosDaTarefa(grupo) {
        return (grupo && grupo.files ? grupo.files : [])
            .map(f => (typeof f === 'string' ? f : f && f.name))
            .filter(Boolean);
    }
    function hashDaTarefa(grupo) {
        if (!grupo) return '';
        return grupo.commit || (state.commitsDosTurnos || {})[String(grupo.id)] || '';
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
    function linhaRotulo(valor, rotulo) {
        return `<div class="git-linha"><span class="git-valor">${escapeHtml(valor)}</span><span class="git-rotulo">${escapeHtml(rotulo)}</span></div>`;
    }
    function pill(acao, texto, extra) {
        return `<button class="git-pill ${extra || ''}" data-git-acao="${acao}">${escapeHtml(texto)}</button>`;
    }
    function varinha(acao, titulo) {
        return `<button class="projeto-notas-acao" type="button" data-git-acao="${acao}" title="${escapeHtml(titulo)}">`
            + `<span class="projeto-icone-wand">${SVG_VARINHA}</span>`
            + `<span class="projeto-icone-spinner">${SVG_SPINNER}</span>`
            + '</button>';
    }
    function aviao(acao, titulo, desativado) {
        return `<button class="projeto-notas-acao git-aviao" type="button" data-git-acao="${acao}" title="${escapeHtml(titulo)}"${desativado ? ' disabled' : ''}>`
            + `<span class="projeto-icone-wand">${SVG_AVIAO}</span>`
            + `<span class="projeto-icone-spinner">${SVG_SPINNER}</span>`
            + '</button>';
    }
    function recolhivel(cabecalho, corpo, aberta) {
        return `<div class="projeto-grupo git-recolhivel${aberta ? ' projeto-aberto' : ''}">`
            + `<div class="projeto-linha projeto-linha-clicavel" data-git-acao="recolher">${cabecalho}<span class="projeto-mais">${aberta ? '−' : '+'}</span></div>`
            + `<div class="projeto-filhos card-collapsible"><div class="card-collapsible-clip">${corpo}</div></div>`
            + '</div>';
    }
    function seccaoRecolhivel(titulo, resumo, corpo) {
        let cabecalho = `<span class="projeto-secao-titulo">${escapeHtml(titulo)}</span>`;
        if (resumo) {
            cabecalho += '<span class="projeto-secao-sep">|</span>'
                + `<span class="projeto-secao-resumo">${escapeHtml(resumo)}</span>`;
        }
        return `<div class="projeto-grupo git-recolhivel">`
            + `<div class="projeto-cabecalho git-cabecalho-clicavel" data-git-acao="recolher">${cabecalho}<span class="projeto-mais">+</span></div>`
            + `<div class="projeto-filhos card-collapsible"><div class="card-collapsible-clip">${corpo}</div></div>`
            + '</div>';
    }
    function alternarRecolhido(cabecalho) {
        const bloco = cabecalho.closest('.projeto-grupo');
        if (!bloco) return;
        const aberto = bloco.classList.toggle('projeto-aberto');
        const mais = cabecalho.querySelector('.projeto-mais');
        if (mais) mais.textContent = aberto ? '−' : '+';
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
    function htmlCabecalho(estado) {
        const remoto = estado.remoto || 'sem remoto';
        const frente = estado.ahead === null ? 'sem ligacao ao remoto' : `${estado.ahead} por subir, ${estado.behind} por descer`;
        const sujos = estado.total_sujos;
        let html = '<div class="git-seccao"><div class="git-seccao-titulo">Repositorio</div>';
        html += linhaRotulo(estado.branch, 'ramo');
        html += linhaRotulo(remoto, 'remoto');
        html += linhaRotulo(frente, 'em relacao ao remoto');
        html += linhaRotulo(sujos === 0 ? 'limpo' : `${sujos} ficheiro(s) alterado(s)`, 'disco');
        if (estado.ultimo) {
            html += linhaRotulo(`${estado.ultimo.curto} ${estado.ultimo.mensagem}`, 'ultimo commit');
        }
        html += `<div class="git-acoes">${pill('atualizar', 'Atualizar')}</div>`;
        html += '</div>';
        return html;
    }
    function htmlDaTarefa(grupo, pendentes) {
        let html = '<div class="git-seccao"><div class="git-seccao-titulo">Esta tarefa</div>';
        if (!grupo) {
            html += '<div class="git-vazio">Seleciona uma tarefa no historico para ver o ponto dela.</div></div>';
            return html;
        }
        const ficheiros = ficheirosDaTarefa(grupo);
        const hash = hashDaTarefa(grupo);
        const porCommitar = pendentes && typeof pendentes.count === 'number' ? pendentes.count : null;
        const podeCommitar = ficheiros.length > 0 && porCommitar !== 0;
        const rotulo = ficheiros.length === 1 ? '1 ficheiro tocado' : `${ficheiros.length} ficheiros tocados`;
        let cabecalho = `<span class="projeto-nome">${escapeHtml(nomeDaTarefa(grupo) || 'Tarefa sem nome')}</span>`
            + '<span class="projeto-secao-sep">|</span>'
            + `<span class="projeto-contagem">${rotulo}</span>`;
        if (porCommitar !== null) {
            cabecalho += '<span class="projeto-secao-sep">|</span>'
                + `<span class="projeto-contagem">${porCommitar} por commitar</span>`;
        }
        html += recolhivel(cabecalho, corpoDaTarefa(grupo, pendentes)
            + (hash ? `<div class="git-nota">Ponto desta tarefa: ${escapeHtml(hash.slice(0, 7))}</div>` : ''));
        html += '<div class="git-campo-linha">'
            + `<input id="git-mensagem" class="git-campo" type="text" spellcheck="false" value="${escapeHtml(valorDoCampo(grupo))}" placeholder="Mensagem do commit">`
            + aviao('commit', podeCommitar ? 'Commitar esta tarefa no git' : 'Nada por commitar nesta tarefa', !podeCommitar)
            + varinha('sugerir', 'Escrever a mensagem com a IA')
            + '</div>';
        html += '</div>';
        return html;
    }
    function corpoDaTarefa(grupo, pendentes) {
        const ficheiros = ficheirosDaTarefa(grupo);
        if (!ficheiros.length) return '<div class="git-vazio">Esta tarefa nao tem ficheiros registados.</div>';
        const porCommitar = pendentes && typeof pendentes.count === 'number' ? pendentes.count : null;
        const emFalta = (pendentes && pendentes.pendentes) || [];
        const lista = (nomes) => {
            const visiveis = nomes.slice(0, LIMITE_FICHEIROS).map(f => `• ${escapeHtml(f)}`).join('<br>');
            const restantes = nomes.length - Math.min(nomes.length, LIMITE_FICHEIROS);
            return `<div class="git-lista">${visiveis}${restantes > 0 ? `<br>• e mais ${restantes}…` : ''}</div>`;
        };
        if (emFalta.length) return lista(emFalta);
        if (porCommitar === null) {
            return '<div class="git-nota">Nao consegui confirmar o que falta commitar nesta tarefa. O botao de commit continua disponivel.</div>';
        }
        if (porCommitar === 0) {
            return '<div class="git-nota">Nada por commitar: nenhum ficheiro desta tarefa mudou desde o ultimo commit.</div>';
        }
        return lista(ficheiros);
    }
    function linhaCommit(commit, acesa) {
        const marcas = (commit.tags || []).map(t => `<span class="git-tag${acesa ? ' git-tag-acesa' : ''}">${escapeHtml(t)}</span>`).join('');
        return `<div class="git-commit${commit.head ? ' git-commit-head' : ''}${acesa ? ' git-commit-da-tarefa' : ''}">`
            + `<span class="git-hash">${escapeHtml(commit.curto)}</span>`
            + `<span class="git-commit-msg">${escapeHtml(commit.mensagem)}</span>`
            + marcas
            + '</div>';
    }
    function htmlHistorico(estado, grupo) {
        const todos = estado.commits || [];
        if (!todos.length) return '';
        const pontoDaTarefa = hashDaTarefa(grupo);
        const visiveis = todos.slice(0, LIMITE_COMMITS);
        const daTarefa = pontoDaTarefa ? todos.find(c => c.hash === pontoDaTarefa) : null;
        let corpo = '';
        visiveis.forEach(c => { corpo += linhaCommit(c, !!daTarefa && c.hash === pontoDaTarefa); });
        if (daTarefa && !visiveis.includes(daTarefa)) {
            corpo += `<div class="git-nota">e mais ${todos.indexOf(daTarefa) - visiveis.length} commit(s) ate ao desta tarefa</div>`;
            corpo += linhaCommit(daTarefa, true);
        }
        return seccaoRecolhivel('Historico do repositorio', String(todos.length), corpo);
    }
    function htmlEtiquetas(estado, grupo, versaoDaTarefa) {
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
        return seccaoRecolhivel('Etiquetas', String(tags.length), `<div class="git-tags-vertical">${linhas}</div>`);
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
        html += htmlCabecalho(estado);
        html += htmlDaTarefa(grupo, pendentes);
        html += htmlHistorico(estado, grupo);
        html += htmlEtiquetas(estado, grupo, versaoDaTarefa);
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
        setCodeViewContent(montarPainel(estado, grupo, pendentes, versaoDaTarefa), false, alvo);
        sincronizarBotaoRestauro(alvo, grupo);
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
        });
        painel.addEventListener('click', async (e) => {
            const botao = e.target.closest('[data-git-acao]');
            if (!botao) return;
            e.stopPropagation();
            const acao = botao.dataset.gitAcao;
            if (acao === 'recolher') return alternarRecolhido(botao);
            if (acao === 'atualizar') return renderGitPanel(vista);
            if (acao === 'sugerir') return sugerirMensagem(vista);
            if (acao === 'deps') return mostrarComandoDeps(vista);
            if (acao === 'commit') return commitarTarefa(vista);
        });
    }
    async function commitarTarefa(vista) {
        const grupo = grupoAtivo();
        if (!grupo) return;
        const painel = vista && vista.codigo ? vista.codigo : null;
        const campo = painel ? painel.querySelector('#git-mensagem') : null;
        const botao = painel ? painel.querySelector('[data-git-acao="commit"]') : null;
        if (botao && botao.disabled) return;
        if (botao) {
            botao.classList.add('a-trabalhar');
            botao.disabled = true;
        }
        const mensagem = campo ? campo.value.trim() : '';
        const ficheiros = ficheirosDaTarefa(grupo);
        try {
            const dados = await pedirGit('/api/git/commit', {
                mensagem,
                ficheiros,
                filename: grupo.__session || '',
                round_id: grupo.id || ''
            });
            if (dados && dados.status === 'ok') {
                grupo.commit = dados.hash || '';
                state.commitsDosTurnos[String(grupo.id)] = dados.hash || '';
                RASCUNHOS.delete(String(grupo.id));
                updateRoundCardCommitByTurnId(grupo.id, dados.hash || '');
                await renderGitPanel(vista);
                return;
            }
            avisarNoPainel(vista, (dados && datos.message) || 'Nao foi possivel commitar.');
        } catch (e) {
            console.error('Erro ao commitar a tarefa:', e);
            avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
        } finally {
            if (botao) {
                botao.classList.remove('a-trabalhar');
                botao.disabled = false;
            }
        }
    }
    async function sugerirMensagem(vista) {
        const grupo = grupoAtivo();
        if (!grupo) return;
        const painel = vista && vista.codigo ? vista.codigo : null;
        const campo = painel ? painel.querySelector('#git-mensagem') : null;
        const botao = painel ? painel.querySelector('[data-git-acao="sugerir"]') : null;
        if (botao) {
            botao.classList.add('a-trabalhar');
            botao.disabled = true;
        }
        const perguntas = (grupo.questions || []).join(' ');
        const resposta = String(grupo.aiResponse || '').slice(0, 800);
        try {
            const dados = await pedirGit('/api/git/sugestao', {
                ficheiros: ficheirosDaTarefa(grupo),
                contexto: [perguntas, resposta].filter(Boolean).join('\n\n')
            });
            if (dados && dados.status === 'ok' && campo) {
                campo.value = dados.mensagem;
                RASCUNHOS.set(String(grupo.id), campo.value);
            } else {
                avisarNoPainel(vista, (dados && dados.message) || 'Nao foi possivel sugerir uma mensagem.');
            }
        } catch (e) {
            console.error('Erro ao pedir a sugestao:', e);
            avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
        } finally {
            if (botao) {
                botao.classList.remove('a-trabalhar');
                botao.disabled = false;
            }
        }
    }
    async function restaurarTarefa() {
        const grupo = grupoAtivo();
        if (!grupo) return;
        const hash = hashDaTarefa(grupo);
        if (hash) {
            await requestGitRestore(hash, nomeDaTarefa(grupo) || 'esta tarefa', grupo.id || '');
            return;
        }
        if (grupo.__session) await requestRestoreTask(grupo);
    }
    function podeRestaurar(grupo) {
        return !!(grupo && (hashDaTarefa(grupo) || grupo.__session));
    }
    function sincronizarBotaoRestauro(vista, grupo) {
        const btn = vista && vista.id === 'historico' ? btnGitRestoreHistory : null;
        if (!btn) return;
        const pode = podeRestaurar(grupo);
        btn.classList.toggle('hidden', !pode);
        btn.onclick = pode ? (e) => {
            e.stopPropagation();
            restaurarTarefa();
        } : null;
    }
    function avisarNoPainel(vista, texto) {
        const painel = vista && vista.codigo ? vista.codigo.querySelector('.git-painel') : null;
        if (!painel) return;
        const antigo = painel.querySelector('.git-erro');
        if (antigo) antigo.remove();
        const div = document.createElement('div');
        div.className = 'git-erro';
        div.textContent = texto;
        painel.prepend(div);
    }


export {
    renderGitPanel,
    grupoAtivo,
    ficheirosDaTarefa
};
