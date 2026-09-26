import { state } from './state.js';
import { fragmentoDeSaida } from './diagnosticos.js';
import { limparLinhaDoDepurador } from './linha_depurador.js';

const LIMITE_SAIDA = 300000;
const VARREDURA_MS = 120;

const SVG_SETA = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>';
const SVG_REPETIR = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';
const SVG_FECHAR = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
const SVG_PREVIEW = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/></svg>';

const PLACEHOLDER_INPUT = 'Terminal';
const PLACEHOLDER_CARD = 'Responder ao card';
const PREFIXO_ECO = '> ';

const cards = new Map();
const lancamentos = new Map();
let sugestoesAtuais = [];
let zona = null;
let selecionado = null;

function _zona() {
    if (!zona) {
        zona = document.getElementById('term-cards');
        if (zona) zona.addEventListener('scroll', _reavaliarSeguir, { passive: true });
    }
    return zona;
}

function _estaRodando(card) {
    return !!card && card.el.classList.contains('term-card-rodando');
}

function _sincronizarPlaceholder() {
    if (!state.termInput) return;
    state.termInput.placeholder = selecionado ? PLACEHOLDER_CARD : PLACEHOLDER_INPUT;
}

function _deixarDeSugerir(card) {
    if (!card.sugerido) return;
    card.sugerido = false;
    card.fim.textContent = '';
    card.el.classList.remove('term-card-sugerido');
}

function _voltarASugerir(card) {
    card.sugerido = true;
    card.el.classList.add('term-card-sugerido');
    _aplicarEstado(card, 'parado');
}

function _soltarSelecao() {
    if (!selecionado) return;
    selecionado.el.classList.remove('term-card-sel');
    selecionado = null;
    _sincronizarPlaceholder();
}

function _selecionarCard(card) {
    _soltarSelecao();
    selecionado = card;
    card.el.classList.add('term-card-sel');
    _sincronizarPlaceholder();
}

export function temCardSelecionado() {
    return !!selecionado;
}

export function descartarSelecao() {
    if (!selecionado) return false;
    _soltarSelecao();
    return true;
}

function _atualizarVazio() {
    const z = _zona();
    if (z) z.classList.toggle('term-cards-vazio', z.childElementCount === 0);
}

function _rotuloFim(status, exitCode) {
    if (status === 'rodando') return '';
    if (status === 'ok') return 'ok';
    if (status === 'timeout') return 'timeout';
    if (status === 'parado') return 'parado';
    return exitCode == null ? 'erro' : 'erro (' + exitCode + ')';
}

function _aplicarEstado(card, status) {
    const efetivo = status || 'parado';
    card.el.classList.toggle('term-card-rodando', efetivo === 'rodando');
    card.el.classList.toggle('term-card-erro', efetivo === 'erro' || efetivo === 'timeout');
    if (card.sugerido) {
        card.ponto.title = 'Sugestao pronta a executar';
        card.fim.textContent = card.dica || '';
    } else {
        card.ponto.title = efetivo === 'rodando' ? 'A correr: clica para parar' : 'Parado';
        card.fim.textContent = _rotuloFim(efetivo, card.exitCode);
    }
}

function _fimDoCardVisivel(card) {
    const z = _zona();
    if (!z) return true;
    return card.el.getBoundingClientRect().bottom <= z.getBoundingClientRect().bottom + 24;
}

function _rolarAteAoFim(card) {
    const z = _zona();
    if (!z) return;
    const excesso = card.el.getBoundingClientRect().bottom - z.getBoundingClientRect().bottom;
    if (excesso > 0) z.scrollTop += excesso;
}

function _reavaliarSeguir() {
    cards.forEach((c) => {
        if (!c.el.classList.contains('term-card-aberto')) return;
        c.seguirFim = _fimDoCardVisivel(c);
    });
}

function _pintar(card, novo) {
    if (!card.el.classList.contains('term-card-aberto')) return;
    if (novo == null) {
        card.saida.replaceChildren(fragmentoDeSaida(card.texto, card.cwd));
    } else {
        card.saida.appendChild(fragmentoDeSaida(novo, card.cwd));
    }
    if (card.seguirFim) _rolarAteAoFim(card);
}

function _despejar(card) {
    card.agendado = false;
    if (!card.pendente) return;
    const corte = Math.max(card.pendente.lastIndexOf('\n'), card.pendente.lastIndexOf('\r'));
    if (corte < 0) return;
    const pronto = card.pendente.slice(0, corte + 1);
    card.pendente = card.pendente.slice(corte + 1);
    card.texto += pronto;
    if (card.texto.length > LIMITE_SAIDA) {
        card.texto = card.texto.slice(-LIMITE_SAIDA);
        _pintar(card, null);
        return;
    }
    _pintar(card, pronto);
}

function _agendar(card) {
    if (card.agendado) return;
    card.agendado = true;
    setTimeout(() => _despejar(card), VARREDURA_MS);
}

function _alternar(card) {
    if (card.el.classList.contains('term-card-aberto')) {
        card.el.classList.remove('term-card-aberto');
        return;
    }
    if (card.pendente) _despejar(card);
    if (!card.texto) return;
    card.el.classList.add('term-card-aberto');
    card.seguirFim = true;
    card.saida.replaceChildren(fragmentoDeSaida(card.texto, card.cwd));
    _rolarAteAoFim(card);
}

async function _parar(pid) {
    try {
        const resp = await fetch(state.API + '/api/processo/' + encodeURIComponent(pid) + '/parar', { method: 'POST' });
        if (!resp.ok) aviso('[terminal] nao consegui encerrar ' + pid, 'term-err');
    } catch (e) {
        aviso('[terminal] erro: ' + e.message, 'term-err');
    }
}

function _assumirIdentidade(card, comando, rotulo) {
    if (card.comando || !comando) return;
    card.comando = comando;
    card.nome.textContent = rotulo || comando;
    card.nome.title = comando;
}

function _fundirCard(card, novoPid, comando, cwd, rotulo, controles) {
    if (!novoPid) return;
    _deixarDeSugerir(card);
    if (cwd) card.cwd = cwd;
    const recem = cards.get(novoPid);
    const controlesDoRecem = recem && recem.controles && recem.controles.length ? recem.controles : null;
    if (recem && recem !== card) {
        card.texto += (card.pendente || '') + (recem.texto || '') + (recem.pendente || '');
        card.pendente = '';
        recem.pendente = '';
        recem.el.remove();
        cards.delete(novoPid);
    }
    cards.delete(card.pid);
    card.pid = novoPid;
    _assumirIdentidade(card, comando, rotulo);
    card.el.dataset.pid = novoPid;
    cards.set(novoPid, card);
    _aplicarControles(card, controles || controlesDoRecem);
    _pintar(card, null);
}

async function _lancar(comando, card) {
    let dados = null;
    if (card) lancamentos.set(card, comando);
    try {
        const resp = await fetch(state.API + '/api/terminal/exec', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cmd: comando, cwd: state.currentCwd || '' })
        });
        dados = await resp.json();
        if (!resp.ok) {
            aviso('[terminal] ' + ((dados && dados.error) || 'nao consegui executar o comando'), 'term-err');
            return null;
        }
        const pid = dados && dados.id;
        if (pid) {
            if (card) _fundirCard(card, pid, comando);
            else if (!cards.has(pid)) _criarCard(pid, comando);
        }
        return dados;
    } catch (e) {
        aviso('[terminal] erro: ' + e.message, 'term-err');
        return null;
    } finally {
        if (card) lancamentos.delete(card);
    }
}

export async function lancarComando(comando) {
    return _lancar(comando, null);
}

function _registarComando(card, comando) {
    if (!comando) return;
    if (card.pendente) _despejar(card);
    const separador = card.texto && !card.texto.endsWith('\n') ? '\n' : '';
    const linha = separador + PREFIXO_ECO + comando + '\n';
    card.texto += linha;
    card.seguirFim = true;
    _pintar(card, linha);
}

async function _executarNoCard(card, comando) {
    if (_estaRodando(card)) return;
    const alvo = comando || card.comando;
    if (!alvo) return;
    const anterior = {
        texto: card.texto,
        pendente: card.pendente,
        exitCode: card.exitCode,
        sugerido: card.sugerido
    };
    _deixarDeSugerir(card);
    card.exitCode = null;
    _registarComando(card, alvo);
    _aplicarEstado(card, 'rodando');
    const dados = await _lancar(alvo, card);
    if (dados) return;
    if (anterior.sugerido) {
        card.texto = anterior.texto;
        card.pendente = anterior.pendente;
        _voltarASugerir(card);
        return;
    }
    card.texto = anterior.texto;
    card.pendente = anterior.pendente;
    card.exitCode = anterior.exitCode;
    _aplicarEstado(card, 'erro');
    _pintar(card, null);
}

async function _responderStdin(card, linha) {
    let dados = null;
    try {
        const resp = await fetch(state.API + '/api/processo/' + encodeURIComponent(card.pid) + '/input', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto: linha })
        });
        dados = await resp.json();
        if (!resp.ok) {
            aviso('[terminal] ' + ((dados && dados.error) || 'nao consegui escrever no processo'), 'term-err');
            return false;
        }
    } catch (e) {
        aviso('[terminal] erro: ' + e.message, 'term-err');
        return false;
    }
    card.pendente += linha + '\n';
    _agendar(card);
    return true;
}

export async function escreverNoCardSelecionado(texto) {
    const card = selecionado;
    if (!card) return false;
    const linha = String(texto);
    if (_estaRodando(card)) return _responderStdin(card, linha);
    await _executarNoCard(card, linha);
    return true;
}

async function _alternarExecucao(card) {
    if (!card.el.classList.contains('term-card-rodando')) return;
    await _parar(card.pid);
    _aplicarEstado(card, 'parado');
}

function _fecharCard(card) {
    const rodando = _estaRodando(card);
    const pid = card.pid;
    if (selecionado === card) _soltarSelecao();
    _soltarControles(card);
    cards.delete(pid);
    card.el.remove();
    _atualizarVazio();
    if (rodando) _parar(pid);
}

function _criarCard(pid, comando, sugerido, dica, cwd, rotulo, controles) {
    const z = _zona();
    if (!z || !pid) return null;
    const el = document.createElement('div');
    el.className = sugerido ? 'term-card term-card-sugerido' : 'term-card';
    el.dataset.pid = pid;

    const cabeca = document.createElement('div');
    cabeca.className = 'term-card-cabeca';

    const ponto = document.createElement('button');
    ponto.type = 'button';
    ponto.className = 'term-card-ponto';

    const nome = document.createElement('span');
    nome.className = 'term-card-comando';
    nome.textContent = rotulo || comando || pid;
    nome.title = comando || pid;

    const fim = document.createElement('span');
    fim.className = 'term-card-fim';

    const repetir = document.createElement('button');
    repetir.type = 'button';
    repetir.className = 'term-card-btn term-card-repetir';
    repetir.title = 'Executar este comando de novo';
    repetir.innerHTML = SVG_REPETIR;

    const fechar = document.createElement('button');
    fechar.type = 'button';
    fechar.className = 'term-card-btn term-card-fechar';
    fechar.title = 'Fechar o card e encerrar o processo';
    fechar.innerHTML = SVG_FECHAR;

    const seta = document.createElement('span');
    seta.className = 'term-card-seta';
    seta.innerHTML = SVG_SETA;

    cabeca.appendChild(ponto);
    cabeca.appendChild(nome);
    cabeca.appendChild(fim);
    cabeca.appendChild(repetir);
    cabeca.appendChild(fechar);
    cabeca.appendChild(seta);

    const saida = document.createElement('pre');
    saida.className = 'term-card-saida';

    el.appendChild(cabeca);
    el.appendChild(saida);
    z.appendChild(el);

    const card = {
        pid: pid,
        comando: comando || '',
        el: el,
        saida: saida,
        ponto: ponto,
        nome: nome,
        cabeca: cabeca,
        repetir: repetir,
        fim: fim,
        url: '',
        cwd: cwd || '',
        texto: '',
        pendente: '',
        agendado: false,
        seguirFim: true,
        exitCode: null,
        sugerido: !!sugerido,
        persistente: !!sugerido,
        dica: dica || '',
        controles: []
    };
    cards.set(pid, card);
    if (controles && controles.length) _aplicarControles(card, controles);

    cabeca.addEventListener('click', (e) => {
        if (e.target.closest('.term-card-btn') || e.target.closest('.term-card-ponto')) return;
        if (card.sugerido) return;
        _selecionarCard(card);
        _alternar(card);
    });
    ponto.addEventListener('click', (e) => {
        e.stopPropagation();
        _alternarExecucao(card);
    });
    repetir.addEventListener('click', (e) => {
        e.stopPropagation();
        _executarNoCard(card);
    });
    fechar.addEventListener('click', (e) => {
        e.stopPropagation();
        _fecharCard(card);
    });
    saida.addEventListener('click', () => {
        if (selecionado === card) {
            _soltarSelecao();
            return;
        }
        _selecionarCard(card);
    });

    _aplicarEstado(card, sugerido ? 'parado' : 'rodando');
    if (sugerido) z.insertBefore(el, z.firstChild);
    _atualizarVazio();
    return card;
}

let cardComControles = null;

function _aplicarControles(card, controles) {
    if (!controles || !controles.length) return;
    card.controles = controles;
    cardComControles = card;
    _pintarControles();
}

function _pintarControles() {
    const alvo = document.getElementById('term-controles');
    const linha = alvo ? alvo.querySelector('.term-controles-linha') : null;
    if (!linha) return;
    linha.textContent = '';
    const controles = cardComControles ? cardComControles.controles : [];
    controles.forEach((c) => {
        if (!c || !c.comando) return;
        const botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'term-controle';
        botao.textContent = c.rotulo || c.comando;
        botao.title = (c.dica ? c.dica + ' ' : '') + '(comando: ' + c.comando + ')';
        botao.disabled = !!c.passivo;
        if (c.passivo) botao.title = 'O programa terminou - escreva no campo do terminal para conduzir a sessao';
        botao.addEventListener('click', (e) => {
            e.stopPropagation();
            if (cardComControles) _responderStdin(cardComControles, c.comando);
        });
        linha.appendChild(botao);
    });
    alvo.classList.toggle('term-controles-visivel', !!cardComControles);
}

function _soltarControles(card) {
    if (cardComControles !== card) return;
    cardComControles = null;
    limparLinhaDoDepurador();
    _pintarControles();
}

export function marcarDepuracaoTerminada(terminou) {
    if (!cardComControles || !cardComControles.controles) return;
    cardComControles.controles = cardComControles.controles.map((c) => ({
        ...c,
        passivo: c.id === 'terminar' ? false : !!terminou
    }));
    _pintarControles();
}

function _cardEmLancamento(comando) {
    for (const [card, cmd] of lancamentos) {
        if (comando && cmd && cmd !== comando) continue;
        return card;
    }
    return null;
}

export function cardIniciar(data) {
    if (!data || !data.pid) return null;
    const existente = cards.get(data.pid);
    if (existente) {
        existente.exitCode = null;
        existente.cwd = data.cwd || existente.cwd;
        if (data.rotulo) existente.nome.textContent = data.rotulo;
        _aplicarControles(existente, data.controles);
        _aplicarEstado(existente, 'rodando');
        return existente;
    }
    const pendente = _cardEmLancamento(data.comando);
    if (pendente) {
        _fundirCard(pendente, data.pid, data.comando, data.cwd, data.rotulo, data.controles);
        _aplicarEstado(pendente, 'rodando');
        return pendente;
    }
    return _criarCard(data.pid, data.comando, false, '', data.cwd, data.rotulo, data.controles);
}

function _avisarPreview(url, automatico, alternar) {
    window.dispatchEvent(new CustomEvent('axio-preview-open', {
        detail: { path: url, auto: !!automatico, alternar: !!alternar }
    }));
}

let avisoDeLarguraLigado = false;

function _mesmoEndereco(a, b) {
    try {
        const x = new URL(a);
        const y = new URL(b);
        return x.origin === y.origin && x.pathname === y.pathname;
    } catch (erro) {
        return false;
    }
}

function _marcarLargura(detalhe) {
    const alvo = (detalhe || {}).alvo || '';
    const largado = !!(detalhe || {}).largado;
    cards.forEach((card) => {
        const botao = card.cabeca ? card.cabeca.querySelector('.term-card-preview') : null;
        if (!botao) return;
        const meu = !!card.url && !!alvo && _mesmoEndereco(card.url, alvo);
        botao.classList.toggle('term-card-preview-largado', meu && largado);
        botao.title = meu
            ? (largado ? 'Voltar a mostrar no preview: ' + card.url
                       : 'Libertar o preview (a pagina continua a correr): ' + card.url)
            : 'Abrir no preview (arranca o processo se estiver parado): ' + card.url;
    });
}

function _ligarAvisoDeLargura() {
    if (avisoDeLarguraLigado) return;
    avisoDeLarguraLigado = true;
    window.addEventListener('axio-preview-largado', (e) => _marcarLargura(e.detail));
}

function _anunciarUrl(card, url) {
    if (card.url === url) return;
    card.url = url;
    if (card.repetir && card.repetir.parentNode) card.repetir.remove();
    let botao = card.cabeca.querySelector('.term-card-preview');
    if (!botao) {
        botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'term-card-btn term-card-preview';
        botao.innerHTML = SVG_PREVIEW;
        botao.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (_estaRodando(card)) {
                _avisarPreview(card.url, false, true);
                return;
            }
            await _executarNoCard(card);
            _avisarPreview(card.url, false);
        });
        card.cabeca.insertBefore(botao, card.cabeca.querySelector('.term-card-fechar'));
    }
    _ligarAvisoDeLargura();
    botao.title = 'Abrir no preview (arranca o processo se estiver parado): ' + url;
    _avisarPreview(url, true);
}

export function cardSaida(data) {
    if (!data || !data.pid) return;
    const card = cards.get(data.pid);
    if (!card) return;
    if (data.url) _anunciarUrl(card, String(data.url));
    let texto = '';
    if (data.chunk != null) texto = String(data.chunk);
    else if (data.line != null) texto = String(data.line) + '\n';
    if (!texto) return;
    card.pendente += texto;
    _agendar(card);
}

export function cardFinalizar(data) {
    if (!data || !data.pid) return;
    const card = cards.get(data.pid);
    if (!card) return;
    card.exitCode = data.exit_code;
    _aplicarEstado(card, data.status);
    _soltarControles(card);
}

export function aviso(texto, cls) {
    const z = _zona();
    if (!z || texto == null || texto === '') return;
    const el = document.createElement('div');
    el.className = 'term-aviso' + (String(cls || '').includes('term-err') ? ' term-aviso-erro' : '');
    el.textContent = String(texto);
    z.appendChild(el);
    _atualizarVazio();
}

export function limparCards() {
    _soltarSelecao();
    cards.forEach((card) => {
        if (card.persistente || _estaRodando(card)) return;
        _soltarControles(card);
        cards.delete(card.pid);
        card.el.remove();
    });
    const z = _zona();
    if (z) z.querySelectorAll('.term-aviso').forEach((el) => el.remove());
    _atualizarVazio();
}

export async function hidratarCards() {
    let dados = null;
    try {
        const resp = await fetch(state.API + '/api/processos');
        dados = await resp.json();
    } catch (e) {
        return;
    }
    (dados && dados.processos ? dados.processos : []).forEach((reg) => {
        const card = cardIniciar({ pid: reg.id, comando: reg.comando, cwd: reg.cwd, rotulo: reg.rotulo,
                                   controles: reg.controles });
        if (!card) return;
        (reg.log || []).forEach((linha) => {
            card.pendente += String(linha) + '\n';
        });
        if (card.pendente) _despejar(card);
        if (!reg.rodando) {
            cardFinalizar({ pid: reg.id, exit_code: null, status: reg.status === 'rodando' ? 'parado' : reg.status });
        }
    });
    _atualizarVazio();
}

function _removerSugestoes() {
    cards.forEach((card) => {
        if (!card.persistente || _estaRodando(card)) return;
        if (selecionado === card) _soltarSelecao();
        cards.delete(card.pid);
        card.el.remove();
    });
    _atualizarVazio();
}

function _mesmasSugestoes(antigas, novas) {
    if (antigas.length !== novas.length) return false;
    return novas.every((chave, i) => chave === antigas[i]);
}

export async function atualizarSugestoes(pastaRel) {
    let dados = null;
    try {
        const resp = await fetch(state.API + '/api/terminal/sugestoes?path=' + encodeURIComponent(pastaRel || ''));
        dados = await resp.json();
    } catch (e) {
        return;
    }
    const sugestoes = (dados && dados.sugestoes) ? dados.sugestoes : [];
    const chaves = sugestoes.map((s) => JSON.stringify([s.comando || '', s.dica || '']));
    if (_mesmasSugestoes(sugestoesAtuais, chaves)) return;
    sugestoesAtuais = chaves;
    _removerSugestoes();
    for (let i = sugestoes.length - 1; i >= 0; i--) {
        const comando = sugestoes[i].comando;
        if (!comando) continue;
        _criarCard('sug:' + comando, comando, true, sugestoes[i].dica);
    }
}

document.addEventListener('click', (e) => {
    if (!selecionado || !e.target.closest) return;
    if (e.target.closest('.term-card') || e.target.closest('#term-input-footer')) return;
    _soltarSelecao();
});

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !selecionado) return;
    _soltarSelecao();
});

_sincronizarPlaceholder();
hidratarCards();
