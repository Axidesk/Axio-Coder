(function () {
    'use strict';

    var JANELA_ARRANQUE_MS = 4000;
    var MAX_ITENS = 12;
    var ESPERA_DISCO_MS = 8000;

    var inicio = Date.now();
    var problemas = [];
    var vistos = {};
    var painel = null;
    var lista = null;
    var rodape = null;
    var agendado = null;
    var statusLigado = false;

    var RE_EXPORT = /does not provide an export named '([^']+)'/;
    var RE_MODULO = /requested module '([^']+)'/;
    var RE_QUEBRA = /does not provide an export named|Failed to resolve module specifier|Failed to fetch dynamically imported module|Importing a module script failed|Cannot use import statement|Unexpected token 'export'/;

    function el(id) {
        return document.getElementById(id);
    }

    function criar(tag, classe, texto) {
        var no = document.createElement(tag);
        if (classe) no.className = classe;
        if (texto) no.textContent = texto;
        return no;
    }

    function limpo(valor) {
        return String(valor === undefined || valor === null ? '' : valor).replace(/\s+/g, ' ').trim();
    }

    function adicionar(problema) {
        var chave = [problema.tipo, problema.ficheiro, problema.linha, problema.simbolo, problema.modulo, problema.mensagem].join('|');
        if (vistos[chave]) return false;
        vistos[chave] = true;
        problemas.push(problema);
        return true;
    }

    function descreveErro(mensagem, ficheiro, linha) {
        var msg = limpo(mensagem);
        var exportado = RE_EXPORT.exec(msg);
        var modulo = RE_MODULO.exec(msg);
        var problema = {
            tipo: 'browser',
            ficheiro: limpo(ficheiro),
            linha: linha || 0,
            mensagem: msg,
            simbolo: exportado ? exportado[1] : '',
            modulo: modulo ? modulo[1] : ''
        };
        problema.fatal = RE_QUEBRA.test(msg);
        return problema;
    }

    function textoDoProblema(p) {
        if (p.tipo === 'disco') {
            var alvo = p.simbolo && p.simbolo !== '*' ? 'o nome "' + p.simbolo + '"' : 'o modulo';
            return 'importa ' + alvo + ' de "' + p.modulo + '" - ' + p.motivo;
        }
        if (p.simbolo && p.modulo) {
            return 'importa "' + p.simbolo + '" de "' + p.modulo + '", que nao o exporta';
        }
        return p.mensagem || 'erro sem mensagem';
    }

    function ondeDoProblema(p) {
        if (!p.ficheiro) return '(sem ficheiro)';
        return p.ficheiro + (p.linha ? ':' + p.linha : '');
    }

    function abrir() {
        if (!painel) painel = construirPainel();
        painel.classList.add('diag-aberto');
        if (lista) lista.focus();
    }

    function fechar() {
        if (painel) painel.classList.remove('diag-aberto');
    }

    function construirPainel() {
        var cx = criar('div', 'diag-painel');
        cx.id = 'boot-diag';
        cx.setAttribute('role', 'alertdialog');
        cx.setAttribute('aria-label', 'Falha ao carregar a interface');

        var caixa = criar('div', 'diag-caixa');
        var cabecalho = criar('div', 'diag-cabecalho');
        cabecalho.appendChild(criar('span', 'diag-titulo', 'Falha ao carregar a interface'));
        var fecharBtn = criar('button', 'diag-fechar', '×');
        fecharBtn.type = 'button';
        fecharBtn.title = 'Fechar (o aviso fica no rodape)';
        fecharBtn.addEventListener('click', fechar);
        cabecalho.appendChild(fecharBtn);
        caixa.appendChild(cabecalho);

        var corpo = criar('div', 'diag-corpo');
        corpo.appendChild(criar('p', 'diag-intro', 'Parte do codigo da interface nao carregou. Abaixo esta o que o browser reportou e o que a leitura dos ficheiros no disco encontrou.'));
        lista = criar('div', 'diag-lista');
        lista.tabIndex = -1;
        corpo.appendChild(lista);
        caixa.appendChild(corpo);

        rodape = criar('div', 'diag-rodape');
        var copiar = criar('button', 'diag-copiar', 'Copiar diagnostico');
        copiar.type = 'button';
        copiar.addEventListener('click', copiarTudo);
        rodape.appendChild(copiar);
        rodape.appendChild(criar('span', 'diag-aviso', ''));
        caixa.appendChild(rodape);

        cx.appendChild(caixa);
        document.body.appendChild(cx);
        return cx;
    }

    function pintar() {
        if (!painel) painel = construirPainel();
        while (lista.firstChild) lista.removeChild(lista.firstChild);
        problemas.slice(0, MAX_ITENS).forEach(function (p) {
            var item = criar('div', 'diag-item' + (p.tipo === 'disco' ? ' diag-item-disco' : ''));
            var onde = criar('span', 'diag-onde', ondeDoProblema(p));
            item.appendChild(onde);
            item.appendChild(criar('span', 'diag-oque', textoDoProblema(p)));
            if (p.tipo === 'browser' && p.mensagem) {
                item.appendChild(criar('span', 'diag-msg', p.mensagem));
            }
            lista.appendChild(item);
        });
        if (problemas.length > MAX_ITENS) {
            lista.appendChild(criar('div', 'diag-mais', 'e mais ' + (problemas.length - MAX_ITENS) + ' problema(s) - veja o diagnostico copiado'));
        }
        escreverStatus();
    }

    function escreverStatus() {
        var st = el('lbl-status');
        if (!st) return;
        st.classList.add('diag-status-erro');
        st.textContent = 'Erro de arranque: ' + problemas.length + ' problema(s) - clique aqui para ver o diagnostico';
        if (!statusLigado) {
            statusLigado = true;
            st.addEventListener('click', abrir);
        }
    }

    function marcarAviso(texto) {
        var aviso = rodape ? rodape.querySelector('.diag-aviso') : null;
        if (aviso) aviso.textContent = texto;
    }

    function textoCompleto() {
        var linhas = ['=== Axio: diagnostico de arranque do frontend ===', new Date().toLocaleString(), ''];
        var disco = problemas.filter(function (p) { return p.tipo === 'disco'; });
        var browser = problemas.filter(function (p) { return p.tipo !== 'disco'; });
        if (disco.length) {
            linhas.push('IMPORTS QUE NAO RESOLVEM (leitura dos ficheiros no disco):');
            disco.forEach(function (p) {
                linhas.push('- ' + ondeDoProblema(p) + '  ' + textoDoProblema(p));
            });
            linhas.push('');
        }
        if (browser.length) {
            linhas.push('ERROS REPORTADOS PELO BROWSER:');
            browser.forEach(function (p) {
                linhas.push('- ' + ondeDoProblema(p) + '  ' + (p.mensagem || textoDoProblema(p)));
            });
            linhas.push('');
        }
        linhas.push('Regra geral: em ES modules um import que nao resolve derruba o modulo inteiro.');
        linhas.push('Corrigir = acrescentar de volta o nome exportado, ou remover o import de quem o pede.');
        return linhas.join('\n');
    }

    function copiarTudo() {
        var texto = textoCompleto();
        var pronto = function () { marcarAviso('Copiado.'); };
        var falhou = function () { marcarAviso('Nao foi possivel copiar - selecione o texto na consola (AxioDiagnostico.texto()).'); };
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(texto).then(pronto, falhou);
                return;
            }
        } catch (e) { }
        try {
            var area = document.createElement('textarea');
            area.value = texto;
            area.setAttribute('readonly', 'readonly');
            area.className = 'diag-area';
            document.body.appendChild(area);
            area.select();
            document.execCommand('copy');
            document.body.removeChild(area);
            pronto();
        } catch (e2) {
            falhou();
        }
    }

    function agendar() {
        if (agendado) return;
        agendado = setTimeout(function () {
            agendado = null;
            pintar();
            abrir();
        }, 120);
    }

    function reportar(problema, forcar) {
        var vale = forcar || problema.fatal || (Date.now() - inicio <= JANELA_ARRANQUE_MS);
        if (!vale) return;
        if (!adicionar(problema)) return;
        agendar();
    }

    function defeitoDoDisco(d) {
        return {
            tipo: 'disco',
            ficheiro: 'src/frontend/js/' + d.arquivo,
            linha: d.linha || 0,
            simbolo: d.simbolo,
            modulo: d.modulo,
            motivo: d.motivo,
            fatal: true
        };
    }

    function consultarDisco() {
        if (!window.fetch) return;
        var corta = setTimeout(function () { }, ESPERA_DISCO_MS);
        window.fetch('/api/diagnostico_frontend').then(function (r) {
            return r.ok ? r.json() : null;
        }).then(function (dados) {
            clearTimeout(corta);
            if (!dados || !dados.defeitos) return;
            dados.defeitos.forEach(function (d) { reportar(defeitoDoDisco(d), true); });
        }).catch(function () {
            clearTimeout(corta);
        });
    }

    function instalar() {
        window.addEventListener('error', function (ev) {
            var alvo = ev.target;
            if (alvo && alvo !== window && alvo.tagName) {
                var src = alvo.src || alvo.href || '';
                reportar({
                    tipo: 'browser',
                    ficheiro: src,
                    linha: 0,
                    mensagem: 'o recurso nao carregou (' + alvo.tagName.toLowerCase() + ')',
                    fatal: src.indexOf('.js') !== -1 || src.indexOf('/chat/') !== -1 || src.indexOf('/editor/') !== -1
                }, false);
                return;
            }
            var mensagem = ev.message || '';
            reportar(descreveErro(mensagem, ev.filename, ev.lineno), false);
        }, true);

        window.addEventListener('unhandledrejection', function (ev) {
            var motivo = ev.reason || {};
            var mensagem = motivo.message || String(motivo);
            reportar(descreveErro(mensagem, motivo.fileName, motivo.lineNumber), false);
        });

        window.AxioDiagnostico = {
            problemas: function () { return problemas.slice(); },
            texto: textoCompleto,
            abrir: abrir,
            limpar: function () { problemas = []; vistos = {}; fechar(); }
        };

        consultarDisco();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', instalar);
    } else {
        instalar();
    }
})();
