import { state } from '../state.js';
import { esconderIconTooltip, mostrarIconTooltip } from '../ui.js';
import { svgDoRestauro } from '../icones.js';
import { requestGitRestore } from './restauro.js';
import { diaDoCommit } from './marcas_envio.js';
import { tituloDaTarefaDoCommit, partesDoTituloDoCommit, turnosComCommit } from './cards.js';

const LIMITE = 20;
const TETO_PAGINAS = 6;
const TITULO = 'Mais antigo';

let commitsAMostrar = LIMITE;
let diasVisiveis = [];
let repositorio = null;
let leituraValida = false;
let pedidoEmCurso = null;
let alvoComBalao = null;
let commitsCarregados = [];
let totalNoRepo = 0;
let paginaEmCurso = null;
let paginasPedidas = 0;

    async function carregarRepositorio(forcar) {
        if (!forcar && leituraValida) return repositorio;
        if (pedidoEmCurso) return pedidoEmCurso;
        pedidoEmCurso = fetch('/api/git/estado')
            .then(r => r.json())
            .then(d => {
                const estado = (d && d.estado) || {};
                repositorio = estado.repo
                    ? { commits: estado.commits || [], tags: estado.tags || [] }
                    : { commits: [], tags: [] };
                leituraValida = !!estado.repo;
                commitsCarregados = repositorio.commits.slice();
                totalNoRepo = Number(estado.total_commits) > 0 ? Number(estado.total_commits) : commitsCarregados.length;
                return repositorio;
            })
            .catch(() => {
                repositorio = { commits: [], tags: [] };
                leituraValida = false;
                commitsCarregados = [];
                totalNoRepo = 0;
                return repositorio;
            })
            .finally(() => { pedidoEmCurso = null; });
        return pedidoEmCurso;
    }
    async function carregarMais() {
        if (paginaEmCurso) return paginaEmCurso;
        if (commitsCarregados.length >= totalNoRepo) return false;
        const vistos = new Set(commitsCarregados.map(c => c.hash));
        paginaEmCurso = fetch('/api/git/commits?skip=' + commitsCarregados.length)
            .then(r => r.json())
            .then(d => {
                const novos = (d && d.commits) || [];
                novos.forEach(c => {
                    if (c && c.hash && !vistos.has(c.hash)) {
                        vistos.add(c.hash);
                        commitsCarregados.push(c);
                    }
                });
                if (d && Number(d.total) > 0) totalNoRepo = Number(d.total);
                return novos.length > 0;
            })
            .catch(() => false)
            .finally(() => { paginaEmCurso = null; });
        return paginaEmCurso;
    }
    function _completarEmFundo() {
        if (paginasPedidas >= TETO_PAGINAS || commitsCarregados.length >= totalNoRepo) return;
        carregarMais().then(cresceu => {
            if (!cresceu) return;
            paginasPedidas += 1;
            const atual = document.querySelector('.history-antigos');
            if (atual) _preencher(atual);
        });
    }
    function _hashesComCard() {
        const comCard = new Set();
        turnosComCommit().forEach(t => {
            if (diasVisiveis.indexOf(t.__date) !== -1) comCard.add(t.commit);
        });
        Object.keys(state.commitsDosTurnos || {}).forEach(id => comCard.add(state.commitsDosTurnos[id]));
        (state.currentTurnLogs || []).forEach(l => {
            if (l.commit) comCard.add(l.commit);
        });
        return comCard;
    }
    function commitsAntigos() {
        const comCard = _hashesComCard();
        return commitsCarregados.filter(c => {
            const dia = diaDoCommit(c.data);
            const diaNosCards = !!dia && diasVisiveis.indexOf(dia) !== -1;
            return !comCard.has(c.hash) && !diaNosCards;
        });
    }
    function _tituloDoCommit(commit) {
        return tituloDaTarefaDoCommit(commit.hash, commit.mensagem) || commit.mensagem || '';
    }
    function _partesDoCommit(commit) {
        const partes = partesDoTituloDoCommit(commit.hash, commit.mensagem);
        if (!partes.base && !partes.resumo) return { base: '', resumo: commit.mensagem || '' };
        return partes;
    }
    function _tagsDoCommit(hash) {
        return ((repositorio && repositorio.tags) || [])
            .filter(t => t && typeof t === 'object' && t.ponto === hash)
            .map(t => t.nome)
            .filter(Boolean);
    }
    function _linha(commit) {
        const linha = document.createElement('div');
        linha.className = 'history-antigo-linha';
        const topo = document.createElement('div');
        topo.className = 'history-antigo-topo';
        const hash = document.createElement('span');
        hash.className = 'history-antigo-hash';
        hash.textContent = commit.curto || String(commit.hash).slice(0, 7);
        const partes = _partesDoCommit(commit);
        const tarefa = document.createElement('span');
        tarefa.className = 'history-antigo-tarefa';
        tarefa.textContent = partes.base;
        const mensagem = document.createElement('span');
        mensagem.className = 'history-antigo-msg';
        mensagem.textContent = partes.resumo;
        mensagem.dataset.info = _tituloDoCommit(commit);
        const restaurar = document.createElement('button');
        restaurar.type = 'button';
        restaurar.className = 'history-round-restore-icon focus:outline-none';
        restaurar.dataset.info = 'Restaurar este ponto';
        restaurar.innerHTML = svgDoRestauro('h-3.5 w-3.5');
        restaurar.addEventListener('click', (evento) => {
            evento.stopPropagation();
            requestGitRestore(commit.hash, _tituloDoCommit(commit) || hash.textContent, '');
        });
        topo.appendChild(hash);
        if (partes.base) topo.appendChild(tarefa);
        _tagsDoCommit(commit.hash).forEach(nome => {
            const chip = document.createElement('span');
            chip.className = 'history-antigo-tag';
            chip.textContent = nome;
            topo.appendChild(chip);
        });
        topo.appendChild(restaurar);
        linha.appendChild(topo);
        linha.appendChild(mensagem);
        return linha;
    }
    function _ligarBaloes(raiz) {
        if (raiz.__baloesLigados) return;
        raiz.__baloesLigados = true;
        raiz.addEventListener('mouseover', (evento) => {
            const alvo = evento.target && evento.target.closest ? evento.target.closest('[data-info]') : null;
            if (!alvo || alvo === alvoComBalao) return;
            if (alvo.classList.contains('history-antigo-msg') && alvo.scrollWidth <= alvo.clientWidth + 1) return;
            alvoComBalao = alvo;
            mostrarIconTooltip(alvo, alvo.dataset.info);
        });
        raiz.addEventListener('mouseout', (evento) => {
            if (!alvoComBalao) return;
            const destino = evento.relatedTarget;
            if (destino && alvoComBalao.contains(destino)) return;
            if (destino && destino.closest && destino.closest('[data-info]')) return;
            alvoComBalao = null;
            esconderIconTooltip();
        });
    }
    function _pintar(clip) {
        clip.innerHTML = '';
        const lista = commitsAntigos();
        const visiveis = lista.slice(0, commitsAMostrar);
        let diaAtual = '';
        visiveis.forEach(commit => {
            const dia = diaDoCommit(commit.data);
            if (dia && dia !== diaAtual) {
                diaAtual = dia;
                const marca = document.createElement('div');
                marca.className = 'history-antigos-dia';
                marca.textContent = dia;
                clip.appendChild(marca);
            }
            clip.appendChild(_linha(commit));
        });
        const restantes = lista.length - visiveis.length;
        const porLer = commitsCarregados.length < totalNoRepo;
        if (restantes > 0 || porLer) {
            const acoes = document.createElement('div');
            acoes.className = 'git-acoes';
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'git-pill';
            botao.textContent = restantes > 0
                ? 'Ver mais ' + Math.min(restantes, LIMITE) + ' de ' + restantes + (porLer ? '+' : '')
                : 'Ver mais';
            botao.addEventListener('click', async () => {
                commitsAMostrar += LIMITE;
                if (commitsAMostrar > lista.length && commitsCarregados.length < totalNoRepo) {
                    botao.disabled = true;
                    botao.textContent = 'A carregar…';
                    await carregarMais();
                }
                _pintar(clip);
            });
            acoes.appendChild(botao);
            clip.appendChild(acoes);
        }
        _ligarBaloes(clip);
    }
    function _bloco() {
        const bloco = document.createElement('div');
        bloco.className = 'projeto-grupo history-antigos';
        const cabecalho = document.createElement('div');
        cabecalho.className = 'projeto-cabecalho history-antigos-cabecalho';
        cabecalho.innerHTML = '<span class="projeto-secao-titulo">' + TITULO + '</span>'
            + '<span class="projeto-secao-sep">|</span>'
            + '<span class="projeto-secao-resumo"></span>'
            + '<span class="projeto-mais">+</span>';
        const filhos = document.createElement('div');
        filhos.className = 'projeto-filhos card-collapsible';
        const clip = document.createElement('div');
        clip.className = 'card-collapsible-clip';
        const sinal = cabecalho.querySelector('.projeto-mais');
        const resumo = cabecalho.querySelector('.projeto-secao-resumo');
        let pintado = false;
        cabecalho.addEventListener('click', () => {
            const aberto = bloco.classList.toggle('projeto-aberto');
            sinal.textContent = aberto ? '−' : '+';
            if (!aberto || pintado) return;
            pintado = true;
            _pintar(clip);
        });
        filhos.appendChild(clip);
        bloco.appendChild(cabecalho);
        bloco.appendChild(filhos);
        bloco.dataset.resumo = 'pendente';
        bloco._resumo = resumo;
        bloco._clip = clip;
        return bloco;
    }
    function montarHistoricoAntigo(container, dias) {
        if (!container) return;
        diasVisiveis = dias || [];
        commitsAMostrar = LIMITE;
        paginasPedidas = 0;
        const anterior = container.querySelector('.history-antigos');
        if (anterior) anterior.remove();
        const bloco = _bloco();
        container.appendChild(bloco);
        if (leituraValida) {
            _preencher(bloco);
            return;
        }
        carregarRepositorio().then(() => { _preencher(bloco); });
    }
    function atualizarHistoricoAntigo() {
        const bloco = document.querySelector('.history-antigos');
        if (!bloco) return;
        if (leituraValida) {
            _preencher(bloco);
            return;
        }
        carregarRepositorio().then(() => { _preencher(bloco); });
    }
    function _preencher(bloco) {
        if (!bloco.isConnected) return;
        const total = commitsAntigos().length;
        const porLer = commitsCarregados.length < totalNoRepo;
        if (leituraValida && !total && !porLer) {
            bloco.remove();
            return;
        }
        bloco.style.display = leituraValida ? '' : 'none';
        bloco._resumo.textContent = porLer ? total + '+' : String(total);
        bloco.dataset.resumo = leituraValida ? 'pronto' : 'pendente';
        if (leituraValida && bloco.classList.contains('projeto-aberto')) _pintar(bloco._clip);
        if (leituraValida && porLer) _completarEmFundo();
    }

export {
    carregarRepositorio,
    montarHistoricoAntigo,
    atualizarHistoricoAntigo
};
