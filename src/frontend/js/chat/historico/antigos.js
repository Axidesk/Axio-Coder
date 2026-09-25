import { state } from '../state.js';
import { esconderIconTooltip, mostrarIconTooltip } from '../ui.js';
import { svgDoRestauro } from '../icones.js';
import { requestGitRestore } from './restauro.js';
import { diaDoCommit } from './marcas_envio.js';
import { tituloDaTarefaDoCommit, turnosComCommit } from './cards.js';

const LIMITE = 20;
const TITULO = 'Mais antigo';

let commitsAMostrar = LIMITE;
let diasVisiveis = [];
let repositorio = null;
let leituraValida = false;
let pedidoEmCurso = null;
let alvoComBalao = null;

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
                return repositorio;
            })
            .catch(() => {
                repositorio = { commits: [], tags: [] };
                leituraValida = false;
                return repositorio;
            })
            .finally(() => { pedidoEmCurso = null; });
        return pedidoEmCurso;
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
        return (repositorio ? repositorio.commits : []).filter(c => !comCard.has(c.hash));
    }
    function _tituloDoCommit(commit) {
        return tituloDaTarefaDoCommit(commit.hash, commit.mensagem) || commit.mensagem || '';
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
        const hash = document.createElement('span');
        hash.className = 'history-antigo-hash';
        hash.textContent = commit.curto || String(commit.hash).slice(0, 7);
        const mensagem = document.createElement('span');
        mensagem.className = 'history-antigo-msg';
        mensagem.textContent = _tituloDoCommit(commit);
        mensagem.dataset.info = mensagem.textContent;
        const restaurar = document.createElement('button');
        restaurar.type = 'button';
        restaurar.className = 'history-round-restore-icon focus:outline-none';
        restaurar.dataset.info = 'Restaurar este ponto';
        restaurar.innerHTML = svgDoRestauro('h-3.5 w-3.5');
        restaurar.addEventListener('click', (evento) => {
            evento.stopPropagation();
            requestGitRestore(commit.hash, _tituloDoCommit(commit) || hash.textContent, '');
        });
        linha.appendChild(hash);
        linha.appendChild(mensagem);
        _tagsDoCommit(commit.hash).forEach(nome => {
            const chip = document.createElement('span');
            chip.className = 'history-antigo-tag';
            chip.textContent = nome;
            linha.appendChild(chip);
        });
        linha.appendChild(restaurar);
        return linha;
    }
    function _ligarBaloes(raiz) {
        if (raiz.__baloesLigados) return;
        raiz.__baloesLigados = true;
        raiz.addEventListener('mouseover', (evento) => {
            const alvo = evento.target && evento.target.closest ? evento.target.closest('[data-info]') : null;
            if (!alvo || alvo === alvoComBalao) return;
            if (alvo.classList.contains('history-antigo-msg') && alvo.scrollHeight <= alvo.clientHeight + 1) return;
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
        if (restantes > 0) {
            const acoes = document.createElement('div');
            acoes.className = 'git-acoes';
            const botao = document.createElement('button');
            botao.type = 'button';
            botao.className = 'git-pill';
            botao.textContent = 'Ver mais ' + Math.min(restantes, LIMITE) + ' de ' + restantes;
            botao.addEventListener('click', () => {
                commitsAMostrar += LIMITE;
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
        if (leituraValida && !total) {
            bloco.remove();
            return;
        }
        bloco.style.display = leituraValida ? '' : 'none';
        bloco._resumo.textContent = String(total);
        bloco.dataset.resumo = leituraValida ? 'pronto' : 'pendente';
        if (leituraValida && bloco.classList.contains('projeto-aberto')) _pintar(bloco._clip);
    }

export {
    carregarRepositorio,
    montarHistoricoAntigo,
    atualizarHistoricoAntigo
};
