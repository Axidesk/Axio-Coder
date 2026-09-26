import { state } from './state.js';
import * as dom from './dom.js';
import { escapeHtml } from './messages.js';
import { copiarTexto } from './clipboard.js';

const { bpEl, inputText, inspectTooltip, termInputEl, terminalMode } = dom;
const titulosNativos = new Map();

    function obterElementoAlvo(el) {
        if (!el || el.nodeType !== 1) return el;
        if (el.id) return el;
        let node = el.parentElement;
        let depth = 0;
        while (node && node !== document.body && node !== document.documentElement && depth < 6) {
            if (node.id) return node;
            node = node.parentElement;
            depth++;
        }
        return el;
    }
    function gerarSeletor(el) {
        if (!el) return '';
        const alvo = obterElementoAlvo(el);
        if (alvo.id) return '#' + alvo.id;
        if (alvo.classList && alvo.classList.length) {
            return '.' + Array.from(alvo.classList).slice(0, 2).join('.');
        }
        return alvo.tagName ? alvo.tagName.toLowerCase() : '';
    }
    function glossaryDescription(seletor) {
        for (const entrada of window.glossary) {
            if (entrada.identificador === seletor) return entrada;
        }
        return null;
    }
    function suprimirTooltipNativo(e) {
        if (!state.inspectAtivo) return;
        const el = e.target;
        if (el && el.title) {
            if (!titulosNativos.has(el)) titulosNativos.set(el, el.title);
            el.title = '';
        }
    }
    function restaurarTooltipsNativos() {
        titulosNativos.forEach(function(v, el) { el.title = v; });
        titulosNativos.clear();
    }
    function posicionarInspectTooltipXY(x, y) {
        const pad = 14;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        inspectTooltip.style.left = '0px';
        inspectTooltip.style.top = '0px';
        const w = inspectTooltip.offsetWidth;
        const h = inspectTooltip.offsetHeight;
        let left = x + pad;
        let top = y + pad;
        if (left + w > vw - 8) left = x - w - pad;
        if (top + h > vh - 8) top = y - h - pad;
        const livre = areaLivreDaViewDoPreview(left, top, w, h, vw, vh);
        left = livre.left;
        top = livre.top;
        if (left < 8) left = 8;
        if (top < 8) top = 8;
        inspectTooltip.style.left = left + 'px';
        inspectTooltip.style.top = top + 'px';
    }
    function obterEditorMonaco() {
        try {
            if (typeof window.__axioGetEditor === 'function') return window.__axioGetEditor();
        } catch (e) { }
        return null;
    }
    function obterMonacoLib() {
        try {
            if (typeof window.__axioGetMonaco === 'function') return window.__axioGetMonaco();
        } catch (e) { }
        return null;
    }
    function dentroDeParenteses(texto) {
        let aberto = 0;
        for (const ch of texto) {
            if (ch === '(') aberto++;
            else if (ch === ')') aberto = Math.max(0, aberto - 1);
        }
        return aberto > 0;
    }
    function classificarPalavraChave(word) {
        const w = (word || '').toLowerCase();
        const grupos = {
            'if': 'condicional', 'else': 'condicional', 'elif': 'condicional', 'switch': 'condicional', 'case': 'condicional', 'default': 'condicional', 'match': 'condicional',
            'for': 'loop', 'while': 'loop', 'do': 'loop', 'repeat': 'loop', 'foreach': 'loop', 'until': 'loop',
            'try': 'exceção', 'catch': 'exceção', 'finally': 'exceção', 'throw': 'exceção', 'raise': 'exceção', 'except': 'exceção',
            'import': 'módulo', 'export': 'módulo', 'from': 'módulo', 'require': 'módulo', 'module': 'módulo', 'include': 'módulo', 'namespace': 'módulo',
            'return': 'retorno', 'yield': 'retorno',
            'function': 'função', 'def': 'função', 'lambda': 'função', 'fn': 'função', 'func': 'função',
            'class': 'classe/objeto', 'struct': 'estrutura', 'interface': 'interface', 'enum': 'enumeração', 'record': 'registro',
            'const': 'declaração constante', 'let': 'declaração variável', 'var': 'declaração variável', 'val': 'declaração constante',
            'new': 'instanciação', 'this': 'objeto atual', 'self': 'objeto atual', 'super': 'superclasse',
            'async': 'assíncrono', 'await': 'assíncrono', 'extends': 'herança', 'implements': 'interface',
            'break': 'controle', 'continue': 'controle', 'pass': 'controle', 'goto': 'controle',
            'static': 'modificador', 'public': 'modificador', 'private': 'modificador', 'protected': 'modificador', 'readonly': 'modificador', 'final': 'modificador', 'abstract': 'modificador'
        };
        if (grupos[w]) return grupos[w];
        return 'palavra-chave (' + word + ')';
    }
    function classificarIdentificador(word, lineText, col) {
        const w = word || '';
        const lw = w.toLowerCase();
        if (lw === 'this' || lw === 'self') return 'objeto atual';
        const antes = lineText.slice(0, col - 1);
        const depois = lineText.slice(col - 1 + w.length);
        const trimmedAntes = antes.trim();
        if (/\.\s*$/.test(trimmedAntes)) {
            return /^\s*\(/.test(depois) ? 'método' : 'atributo';
        }
        if (dentroDeParenteses(antes)) return 'argumento/parâmetro';
        if (/\b(return|yield)\s*$/.test(trimmedAntes)) return 'valor de retorno';
        if (/\b(function|def|fn|func)\s*$/.test(trimmedAntes)) return 'função';
        if (/\b(class|struct|interface|enum)\s*$/.test(trimmedAntes)) return 'classe/objeto';
        if (/\b(const|let|var|val)\s*$/.test(trimmedAntes)) {
            return /^\s*=/.test(depois) ? 'constante/variável' : 'declaração';
        }
        if (/^\s*\(/.test(depois)) return 'chamada de função/método';
        return 'variável/identificador';
    }
    function classificarPorHeuristica(word, tokenType, lineText, col) {
        const t = (tokenType || '').toLowerCase();
        if (t.indexOf('comment') >= 0) return 'comentário';
        if (t.indexOf('string') >= 0) return 'string';
        if (t.indexOf('number') >= 0) return 'constante numérica';
        if (t.indexOf('keyword') >= 0) return classificarPalavraChave(word);
        if (t.indexOf('type.identifier') >= 0 || t.indexOf('type') >= 0) return 'tipo/objeto';
        if (t.indexOf('identifier') >= 0 || t.indexOf('variable') >= 0) return classificarIdentificador(word, lineText, col);
        if (t.indexOf('delimiter') >= 0 || t.indexOf('operator') >= 0) return 'operador/pontuação';
        if (t) return 'token (' + tokenType + ')';
        return null;
    }
    async function classificarCodigoMonaco(x, y) {
        const ed = obterEditorMonaco();
        const mc = obterMonacoLib();
        if (!ed || !mc || typeof ed.getTargetAtClientPoint !== 'function') return null;
        const model = ed.getModel && ed.getModel();
        if (!model) return null;
        const target = ed.getTargetAtClientPoint(x, y);
        const pos = target && target.position;
        if (!pos) return null;
        const line = pos.lineNumber;
        const col = pos.column;
        const lineText = model.getLineContent(line) || '';
        const wordInfo = model.getWordAtPosition(pos);
        const word = wordInfo ? wordInfo.word : '';
        let tokenType = '';
        try {
            const tokenized = await mc.editor.tokenize(lineText, model.getLanguageId());
            const tokens = (tokenized && tokenized[0]) || [];
            const offset = col - 1;
            for (const tk of tokens) {
                if (offset >= tk.offset && offset < tk.offset + tk.length) {
                    tokenType = tk.type || '';
                    break;
                }
            }
        } catch (e) {
            tokenType = '';
        }
        return classificarPorHeuristica(word, tokenType, lineText, col);
    }
    function infoCor(el) {
        try {
            const cs = getComputedStyle(el);
            const cor = cs.color || '';
            const bg = cs.backgroundColor || '';
            const partes = [];
            if (cor && cor !== 'rgba(0, 0, 0, 0)') partes.push('texto ' + cor);
            if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') partes.push('fundo ' + bg);
            return partes.join(' · ');
        } catch (e) { return ''; }
    }
    async function renderizarInspect(el, x, y) {
        if (!el || !inspectTooltip) return;
        const token = ++state.renderInspectToken;
        const seletor = gerarSeletor(el);
        const g = glossaryDescription(seletor);
        const classes = (el.classList && Array.from(el.classList).join(' ')) || '';
        let codigoTipo = null;
        const dentroMonaco = el.closest && el.closest('.monaco-editor');
        if (dentroMonaco) {
            const r = el.getBoundingClientRect();
            const cx = r.left + r.width / 2;
            const cy = r.top + r.height / 2;
            codigoTipo = await classificarCodigoMonaco(cx, cy);
        }
        if (token !== state.renderInspectToken) return;
        const fonte = infoFonte(el);
        const cor = infoCor(el);
        const itens = [];
        itens.push({ rotulo: 'nome', valor: seletor, kind: 'text' });
        if (g && g.descricao) itens.push({ rotulo: 'descrição', valor: g.descricao, kind: 'text' });
        if (codigoTipo) itens.push({ rotulo: 'tipo', valor: codigoTipo, kind: 'text' });
        if (fonte) itens.push({ rotulo: 'fonte', valor: fonte, kind: 'text' });
        if (cor) itens.push({ rotulo: 'cor', valor: cor, kind: 'text' });
        if (classes) itens.push({ rotulo: 'classes', valor: '.' + classes.replace(/ +/g, '.'), kind: 'text' });
        if (g && g.localizacao && g.localizacao.arquivo) {
            const loc = g.localizacao.arquivo + (g.localizacao.linha ? ':' + g.localizacao.linha : '');
            itens.push({ rotulo: 'localização', valor: loc, kind: 'link', arquivo: g.localizacao.arquivo, linha: g.localizacao.linha });
        }
        const tudo = itens.map(function(it) { return it.rotulo + ': ' + it.valor; }).join('\n');
        itens.push({ rotulo: 'copiar tudo', valor: tudo, kind: 'all' });
        state.inspectItems = itens;
        state.inspectItemIndex = 0;
        let html = '';
        itens.forEach(function(it, i) {
            html += '<div class="inspect-item' + (i === 0 ? ' inspect-item-active' : '') + '" data-idx="' + i + '">';
            html += '<span class="inspect-item-label">' + escapeHtml(it.rotulo) + ':</span> ';
            if (it.kind === 'link') {
                html += '<span class="inspect-link">' + escapeHtml(it.valor) + '</span>';
            } else {
                html += '<span class="inspect-item-value">' + escapeHtml(it.valor) + '</span>';
            }
            html += '</div>';
        });
        html += '<div class="inspect-hint">Tab: selecionar · Enter: copiar/abrir · Shift+clique: interagir · Esc: sair</div>';
        inspectTooltip.innerHTML = html;
        inspectTooltip.classList.remove('hidden');
        posicionarInspectTooltipXY(x, y);
    }
    function selecionarItemInspect(idx) {
        if (!inspectTooltip) return;
        const itensEl = inspectTooltip.querySelectorAll('.inspect-item');
        if (!itensEl.length) return;
        state.inspectItemIndex = ((idx % itensEl.length) + itensEl.length) % itensEl.length;
        itensEl.forEach(function(el, i) {
            el.classList.toggle('inspect-item-active', i === state.inspectItemIndex);
        });
    }
    function avancarItemInspect() {
        if (!state.inspectItems.length) return;
        selecionarItemInspect(state.inspectItemIndex + 1);
    }
    function atualizarHintInspect(texto) {
        if (!inspectTooltip) return;
        const hint = inspectTooltip.querySelector('.inspect-hint');
        if (hint) hint.textContent = texto;
    }
    function abrirArquivoNaLinha(arquivo, linha) {
        let caminho = arquivo || '';
        if (!/^([a-zA-Z]:[\\/]|\/)/.test(caminho)) {
            try {
                const path = window.require('path');
                const fs = window.require('fs');
                const raizApp = process.cwd();
                const noApp = path.join(raizApp, caminho);
                if (fs.existsSync(noApp)) {
                    caminho = noApp;
                } else {
                    const bp = bpEl ? bpEl.textContent : '';
                    if (bp) caminho = path.join(bp, caminho);
                }
            } catch (e) { }
        }
        if (window.WorkspaceView && typeof window.WorkspaceView.openFileAtLine === 'function') {
            window.WorkspaceView.openFileAtLine(caminho, linha);
        } else if (window.WorkspaceView && typeof window.WorkspaceView.openFileFromLog === 'function') {
            window.WorkspaceView.openFileFromLog(caminho);
        }
    }
    function textoParaLinhaUnica(texto) {
        return String(texto == null ? '' : texto).replace(/\r\n|\r|\n/g, ' ').replace(/\s{2,}/g, ' ').trim();
    }
    function colarNoInputText(texto) {
        const terminalAtivo = terminalMode && !terminalMode.classList.contains('hidden');
        if (terminalAtivo) {
            if (termInputEl) {
                const linha = textoParaLinhaUnica(texto);
                const focado = document.activeElement === termInputEl;
                const inicio = focado ? termInputEl.selectionStart : termInputEl.value.length;
                const fim = focado ? termInputEl.selectionEnd : termInputEl.value.length;
                const atual = termInputEl.value;
                termInputEl.value = atual.slice(0, inicio) + linha + atual.slice(fim);
                termInputEl.dispatchEvent(new Event('input', { bubbles: true }));
                termInputEl.focus();
                const novaPos = inicio + linha.length;
                try { termInputEl.setSelectionRange(novaPos, novaPos); } catch (e) {}
            }
            return;
        }
        if (!inputText) return;
        const focado = document.activeElement === inputText;
        const inicio = focado ? inputText.selectionStart : inputText.value.length;
        const fim = focado ? inputText.selectionEnd : inputText.value.length;
        const atual = inputText.value;
        inputText.value = atual.slice(0, inicio) + texto + atual.slice(fim);
        inputText.dispatchEvent(new Event('input', { bubbles: true }));
        inputText.focus();
        const novaPos = inicio + texto.length;
        try { inputText.setSelectionRange(novaPos, novaPos); } catch (e) {}
    }
    function textoDaInspecaoDoPreview(info) {
        if (!info || !info.seletor) return '';
        const medidas = [];
        const caixa = info.caixa || {};
        if (caixa.largura) medidas.push(caixa.largura + 'x' + caixa.altura);
        const espaco = info.espacamento || {};
        if (espaco.padding && espaco.padding !== '0px') medidas.push('padding ' + espaco.padding);
        if (espaco.gap && espaco.gap !== 'normal') medidas.push('gap ' + espaco.gap);
        if (info.arredondamento && info.arredondamento !== '0px') medidas.push('radius ' + info.arredondamento);
        if (info.fundo) medidas.push('fundo ' + info.fundo);
        if (info.cor) medidas.push('cor ' + info.cor);
        if (info.borda) medidas.push('borda ' + info.borda);
        if (info.sombra) medidas.push('sombra ' + info.sombra);
        if (info.layout) medidas.push('layout ' + info.layout);
        if (info.fonte) medidas.push('fonte ' + info.fonte);
        const linhas = ['[preview] ' + (info.caminho || info.seletor)];
        if (medidas.length) linhas.push(medidas.join(' · '));
        if (info.texto) linhas.push('texto "' + info.texto + '"');
        return linhas.join('\n');
    }
    function recolherDoPreview(info) {
        const texto = textoDaInspecaoDoPreview(info);
        if (!texto) return;
        copiarTexto(texto);
        const prefixo = inputText && inputText.value.trim() ? '\n' : '';
        colarNoInputText(prefixo + texto);
    }
    function areaDaViewDoPreview() {
        const vista = document.getElementById('preview-view') || document.getElementById('preview-host');
        if (!vista) return null;
        const caixa = vista.getBoundingClientRect();
        if (caixa.width < 1 || caixa.height < 1) return null;
        const painel = document.getElementById('sliding-panel-container');
        const esquerda = painel && !painel.classList.contains('dock-closed')
            ? Math.max(caixa.left, painel.getBoundingClientRect().right)
            : caixa.left;
        if (caixa.right - esquerda < 1) return null;
        return { left: esquerda, top: caixa.top, right: caixa.right, bottom: caixa.bottom };
    }
    function areaLivreDaViewDoPreview(left, top, w, h, vw, vh) {
        const ocupada = areaDaViewDoPreview();
        if (!ocupada || !_sobrepoe(left, top, w, h, ocupada)) return { left, top };
        const margem = 10;
        const tentativas = [
            { left: ocupada.left - w - margem, top: top },
            { left: left, top: ocupada.top - h - margem },
            { left: left, top: ocupada.bottom + margem },
            { left: ocupada.right + margem, top: top }
        ];
        for (const tentativa of tentativas) {
            if (tentativa.left < 8 || tentativa.top < 8) continue;
            if (tentativa.left + w > vw - 8 || tentativa.top + h > vh - 8) continue;
            if (_sobrepoe(tentativa.left, tentativa.top, w, h, ocupada)) continue;
            return tentativa;
        }
        return { left: Math.max(8, ocupada.left - w - margem), top: top };
    }
    function _sobrepoe(left, top, w, h, outra) {
        return left < outra.right && left + w > outra.left && top < outra.bottom && top + h > outra.top;
    }
    function esconderInspectTooltip() {
        if (inspectTooltip) {
            inspectTooltip.classList.add('hidden');
            inspectTooltip.classList.remove('inspect-locked');
        }
        state.inspectLocked = false;
    }
    function _ipc() {
        try {
            return window.require('electron').ipcRenderer;
        } catch (e) {
            return null;
        }
    }
    function avisarMenuInspect() {
        const ipc = _ipc();
        if (ipc) ipc.send('inspect:set', !!state.inspectAtivo);
    }
    function ligarInspectAoMenu() {
        const ipc = _ipc();
        if (!ipc) return;
        ipc.on('menu:set-inspect', (e, ativo) => definirInspect(ativo));
        ipc.on('preview:inspecao', (e, info) => recolherDoPreview(info));
        document.addEventListener('mouseleave', () => {
            if (state.inspectAtivo && !state.inspectLocked) esconderInspectTooltip();
        });

        ipc.send('inspect:set', !!state.inspectAtivo);
    }
    function definirInspect(ativo) {

        const ligado = !!ativo;
        if (ligado === state.inspectAtivo) return;
        state.inspectAtivo = ligado;
        state.inspectLocked = false;
        document.body.classList.toggle('inspect-mode', ligado);
        esconderInspectTooltip();
        if (!ligado) {
            state.inspectCurrentEl = null;
            state.inspectItems = [];
            state.inspectItemIndex = -1;
            restaurarTooltipsNativos();
            document.body.style.removeProperty('cursor');
        } else {
            document.body.style.cursor = 'crosshair';
        }
        avisarMenuInspect();
    }
    function desativarInspect() {
        definirInspect(false);
    }
    function executarItemInspect(idx) {
        const item = state.inspectItems[idx];
        if (!item) return;
        if (item.kind === 'link') {
            abrirArquivoNaLinha(item.arquivo, item.linha);
            colarNoInputText(item.valor);
            desativarInspect();
            return;
        }
        colarNoInputText(item.valor);
        desativarInspect();
    }

    function infoFonte(el) {
        try {
            const cs = getComputedStyle(el);
            const family = (cs.fontFamily || '').split(',')[0].replace(/["']/g, '').trim();
            const size = cs.fontSize || '';
            const weight = cs.fontWeight || '';
            const estilo = cs.fontStyle || '';
            let s = family || '';
            if (size) s += (s ? ' ' : '') + size;
            if (weight && weight !== '400' && weight !== 'normal') s += (s ? ' ' : '') + weight;
            if (estilo && estilo !== 'normal') s += (s ? ' ' : '') + estilo;
            return s;
        } catch (e) { return ''; }
    }

export {
    obterElementoAlvo,
    gerarSeletor,
    glossaryDescription,
    suprimirTooltipNativo,
    restaurarTooltipsNativos,
    posicionarInspectTooltipXY,
    obterEditorMonaco,
    obterMonacoLib,
    dentroDeParenteses,
    classificarPalavraChave,
    classificarIdentificador,
    classificarPorHeuristica,
    classificarCodigoMonaco,
    infoCor,
    renderizarInspect,
    selecionarItemInspect,
    avancarItemInspect,
    atualizarHintInspect,
    abrirArquivoNaLinha,
    colarNoInputText,
    textoDaInspecaoDoPreview,
    recolherDoPreview,
    esconderInspectTooltip,
    definirInspect,
    ligarInspectAoMenu,
    desativarInspect,
    executarItemInspect,
    infoFonte
};