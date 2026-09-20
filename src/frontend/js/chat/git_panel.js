import { state } from './state.js';
import { vistaDe } from './colunas.js';
import { setCodeViewContent } from './files.js';
import { escapeHtml } from './messages.js';
import { requestGitRestore } from './historico/restauro.js';
import { nomeDaTarefaDoCommit, updateRoundCardCommitByTurnId } from './historico/cards.js';

const LIMITE_COMMITS = 12;

const RASCUNHOS = new Map();
const SUGERIDAS = new Set();

const COMANDO_DE_DEPENDENCIA = {
    'requirements.txt': 'python -m pip install -r requirements.txt',
    'package.json': 'npm install'
};

    function grupoAtivo() {
        return state.currentSelectedHistoryGroup || window.currentActiveLogGroup || null;
    }
    function nomeDaTarefa(grupo) {
        if (!grupo) return '';
        return grupo.displayName || grupo.title || grupo.name || '';
    }
    function nomeRealDaTarefa(grupo) {
        const nome = grupo ? String(grupo.name || '').replace(/\s+/g, ' ').trim() : '';
        return /^Tarefa \d+$/.test(nome) ? '' : nome;
    }
    function mensagemProposta(grupo) {
        const nome = nomeRealDaTarefa(grupo);
        if (nome) return nome.slice(0, 72);
        const perguntas = (grupo && grupo.questions) || [];
        const pergunta = String(perguntas[0] || '').replace(/\s+/g, ' ').trim();
        return pergunta.slice(0, 72);
    }
    function valorDoCampo(grupo) {
        if (!grupo) return '';
        const guardado = RASCUNHOS.get(String(grupo.id));
        return guardado === undefined ? mensagemProposta(grupo) : guardado;
    }
    function textoDaOrigem(grupo) {
        if (!grupo) return '';
        const chave = String(grupo.id);
        const guardado = RASCUNHOS.get(chave);
        if (guardado !== undefined && SUGERIDAS.has(chave)) {
            return 'Sugestao da IA para esta tarefa. Confere antes de commitar.';
        }
        if (guardado !== undefined && guardado !== mensagemProposta(grupo)) {
            return 'Mensagem escrita por ti para esta tarefa.';
        }
        if (nomeRealDaTarefa(grupo)) {
            return 'Proposta a partir do nome desta tarefa. Podes mudar a mensagem antes de commitar.';
        }
        if (mensagemProposta(grupo)) {
            return 'Esta tarefa ainda nao tem nome: a proposta e o inicio da tua pergunta nesta tarefa. Podes mudar a mensagem antes de commitar.';
        }
        return 'Escreve a mensagem do commit, ou pede uma sugestao a IA.';
    }
    function atualizarOrigem(painel, grupo) {
        const alvo = painel ? painel.querySelector('#git-origem') : null;
        if (alvo) alvo.textContent = textoDaOrigem(grupo);
    }
    function ficheirosDaTarefa(grupo) {
        return (grupo && grupo.files ? grupo.files : [])
            .map(f => (typeof f === 'string' ? f : f && f.name))
            .filter(Boolean);
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
    function htmlDaTarefa(grupo, estado, pendentes) {
        const ficheiros = ficheirosDaTarefa(grupo);
        const hash = (grupo && grupo.commit) || '';
        let html = '<div class="git-seccao"><div class="git-seccao-titulo">Esta tarefa</div>';
        if (!grupo) {
            html += '<div class="git-vazio">Seleciona uma tarefa no historico para ver o ponto dela.</div></div>';
            return html;
        }
        const nome = nomeDaTarefa(grupo);
        if (nome) html += linhaRotulo(nome, 'tarefa');
        html += linhaRotulo(String(ficheiros.length), 'ficheiro(s) tocado(s)');
        if (hash) {
            html += linhaRotulo(hash.slice(0, 7), 'commit desta tarefa');
        } else {
            html += '<div class="git-vazio">Esta tarefa ainda nao foi commitada.</div>';
        }
        if (ficheiros.length) {
            const lista = ficheiros.slice(0, 12).map(f => `• ${escapeHtml(f)}`).join('<br>');
            const restantes = ficheiros.length - Math.min(ficheiros.length, 12);
            html += `<details class="git-detalhes"><summary><span>Ver os ficheiros</span></summary><div class="git-lista">${lista}${restantes > 0 ? `<br>• e mais ${restantes}…` : ''}</div></details>`;
        } else {
            html += '<div class="git-vazio">Esta tarefa nao tem ficheiros registados.</div>';
        }
        const porCommitar = pendentes && typeof pendentes.count === 'number' ? pendentes.count : null;
        const podeCommitar = ficheiros.length > 0 && porCommitar !== 0;
        if (ficheiros.length && porCommitar !== null) {
            html += linhaRotulo(String(porCommitar), 'por commitar');
        }
        html += `<input id="git-mensagem" class="git-campo" type="text" spellcheck="false" value="${escapeHtml(valorDoCampo(grupo))}" placeholder="Mensagem do commit">`;
        html += `<div id="git-origem" class="git-origem">${escapeHtml(textoDaOrigem(grupo))}</div>`;
        html += '<div class="git-acoes">';
        html += pill('sugerir', 'Sugerir com IA');
        if (podeCommitar) html += pill('commit', 'Commit desta tarefa', 'git-pill-forte');
        if (hash) html += pill('restaurar', 'Restaurar esta tarefa');
        html += '</div>';
        let nota = 'O commit e local: nada sobe para o remoto sem tu mandares. Entram so os ficheiros desta tarefa.';
        if (!ficheiros.length) nota = 'Sem ficheiros registados nesta tarefa, nao ha um commit dela para fazer.';
        else if (porCommitar === 0) nota = 'Nada por commitar: nenhum ficheiro desta tarefa mudou desde o ultimo commit.';
        html += `<div class="git-nota">${nota}</div>`;
        html += '</div>';
        return html;
    }
    function htmlHistorico(estado, grupo) {
        const pontoDaTarefa = (grupo && grupo.commit) || '';
        let html = '<div class="git-seccao"><div class="git-seccao-titulo">Historico do repositorio</div>';
        const commits = (estado.commits || []).slice(0, LIMITE_COMMITS);
        if (!commits.length) {
            html += '<div class="git-vazio">Nenhum commit neste repositorio.</div></div>';
            return html;
        }
        const visiveis = commits.slice(0, LIMITE_COMMITS);
        const daTarefa = pontoDaTarefa ? commits.find(c => c.hash === pontoDaTarefa) : null;
        const extra = daTarefa && !visiveis.includes(daTarefa) ? daTarefa : null;
        const linhaCommit = (c, daTarefa) => {
            const marcas = (c.tags || []).map(t => `<span class="git-tag${daTarefa ? ' git-tag-acesa' : ''}">${escapeHtml(t)}</span>`).join('');
            return `<div class="git-commit${c.head ? ' git-commit-head' : ''}${daTarefa ? ' git-commit-da-tarefa' : ''}">
                <span class="git-hash">${escapeHtml(c.curto)}</span>
                <span class="git-commit-msg">${escapeHtml(c.mensagem)}</span>
                ${marcas}
            </div>`;
        };
        visiveis.forEach(c => { html += linhaCommit(c, !!pontoDaTarefa && c.hash === pontoDaTarefa); });
        if (extra) {
            html += `<div class="git-nota">e mais ${commits.indexOf(extra) - visiveis.length} commit(s) ate ao desta tarefa</div>`;
            html += linhaCommit(extra, true);
        }
        html += '</div>';
        const tags = estado.tags || [];
        if (tags.length) {
            html += '<div class="git-seccao"><div class="git-seccao-titulo">Etiquetas</div><div class="git-tags">';
            tags.slice(0, 20).forEach(t => {
                const nome = typeof t === 'string' ? t : t.nome;
                const ponto = typeof t === 'string' ? '' : t.ponto;
                const curto = typeof t === 'string' ? '' : t.curto;
                const acesa = !!pontoDaTarefa && ponto === pontoDaTarefa;
                const dono = ponto ? nomeDaTarefaDoCommit(ponto) : '';
                const titulo = curto ? `aponta para ${curto}${dono ? ` · ${dono}` : ''}` : '';
                html += `<span class="git-tag${acesa ? ' git-tag-acesa' : ''}" title="${escapeHtml(titulo)}">${escapeHtml(nome)}`
                    + (curto ? `<span class="git-tag-ponto">${escapeHtml(curto)}</span>` : '')
                    + (dono ? `<span class="git-tag-dono">${escapeHtml(dono)}</span>` : '')
                    + '</span>';
            });
            html += '</div>';
            html += '<div class="git-nota">Cada etiqueta mostra o ponto a que aponta. Acende quando esse ponto e o commit da tarefa selecionada.</div>';
            html += '</div>';
        }
        return html;
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
    function montarPainel(estado, grupo, pendentes) {
        if (!estado || !estado.repo) return htmlSemRepo(estado && estado.motivo);
        let html = '<div class="git-painel">';
        html += htmlCabecalho(estado);
        html += htmlDaTarefa(grupo, estado, pendentes);
        html += htmlHistorico(estado, grupo);
        html += htmlDependencias(estado);
        html += '</div>';
        return html;
    }
    async function renderGitPanel(vista = vistaDe('historico')) {
        const alvo = vista || vistaDe('historico');
        setCodeViewContent('<div class="git-painel"><div class="git-vazio">A ler o repositorio…</div></div>', false, alvo);
        const grupo = grupoAtivo();
        const ficheiros = ficheirosDaTarefa(grupo);
        let dados = null;
        let pendentes = null;
        try {
            const pedidos = [pedirGit('/api/git/estado')];
            if (ficheiros.length) pedidos.push(pedirGit('/api/git/pendentes', { ficheiros }));
            const respostas = await Promise.all(pedidos);
            dados = respostas[0];
            pendentes = respostas[1] || null;
        } catch (e) {
            console.error('Erro ao ler o repositorio:', e);
            dados = { status: 'error', message: `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}` };
        }
        const estado = dados && dados.estado ? dados.estado : { repo: false, motivo: (dados && dados.message) || 'Nao consegui ler o repositorio.' };
        setCodeViewContent(montarPainel(estado, grupo, pendentes), false, alvo);
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
            SUGERIDAS.delete(String(grupo.id));
            atualizarOrigem(painel, grupo);
        });
        painel.addEventListener('click', async (e) => {
            const botao = e.target.closest('[data-git-acao]');
            if (!botao) return;
            e.stopPropagation();
            const acao = botao.dataset.gitAcao;
            if (acao === 'atualizar') return renderGitPanel(vista);
            if (acao === 'sugerir') return sugerirMensagem(vista);
            if (acao === 'deps') return mostrarComandoDeps(vista);
            if (acao === 'commit') return commitarTarefa(vista);
            if (acao === 'restaurar') return restaurarTarefa();
        });
    }
    async function commitarTarefa(vista) {
        const grupo = grupoAtivo();
        if (!grupo) return;
        const campo = vista && vista.codigo ? vista.codigo.querySelector('#git-mensagem') : null;
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
                RASCUNHOS.delete(String(grupo.id));
                SUGERIDAS.delete(String(grupo.id));
                updateRoundCardCommitByTurnId(grupo.id, dados.hash || '');
                await renderGitPanel(vista);
                return;
            }
            avisarNoPainel(vista, (dados && datos.message) || 'Nao foi possivel commitar.');
        } catch (e) {
            console.error('Erro ao commitar a tarefa:', e);
            avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
        }
    }
    async function sugerirMensagem(vista) {
        const grupo = grupoAtivo();
        if (!grupo) return;
        const painel = vista && vista.codigo ? vista.codigo : null;
        const campo = painel ? painel.querySelector('#git-mensagem') : null;
        const botao = painel ? painel.querySelector('[data-git-acao="sugerir"]') : null;
        if (botao) {
            botao.textContent = 'A pensar…';
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
                SUGERIDAS.add(String(grupo.id));
                atualizarOrigem(painel, grupo);
            } else {
                avisarNoPainel(vista, (dados && dados.message) || 'Nao foi possivel sugerir uma mensagem.');
            }
        } catch (e) {
            console.error('Erro ao pedir a sugestao:', e);
            avisarNoPainel(vista, `Nao consegui falar com o servidor: ${e && e.message ? e.message : e}`);
        } finally {
            if (botao) {
                botao.textContent = 'Sugerir com IA';
                botao.disabled = false;
            }
        }
    }
    async function restaurarTarefa() {
        const grupo = grupoAtivo();
        if (!grupo || !grupo.commit) return;
        await requestGitRestore(grupo.commit, nomeDaTarefa(grupo) || 'esta tarefa', grupo.id || '');
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
