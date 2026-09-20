const { ipcRenderer } = window.require('electron');
import { state } from './state.js';
import * as dom from './dom.js';
import { closeCol3, closePanelCol, closePlusMenus, openCol3Panel, openLogDockInWorkspace, openPanelCol, setupCol3ForFileView, syncCopyButtons, syncDocTopBar } from './layout.js';
import { criarVista, vistaDoElemento } from './colunas.js';
import { escapeHtml } from './messages.js';
import { resetWorkspaceUI } from './ui.js';
import { createCopyButton } from './clipboard.js';

import { ALTURA_LINHA, PADDING_TOPO } from '../editor/metricas.js';

const { btnEyeDiff, btnRedo, btnSelectFolder, btnUndo, codeViewContainer, codeViewContainerHistory, col3Title, col3TitleHistory, filesListContainer, filesListContainerHistory, lblFolder, lblRedoCount, lblStatus, lblUndoCount, panelCol2, panelCol2History, panelCol3, panelCol3History } = dom;
const NL = String.fromCharCode(10);


    const vistaDock = criarVista({
        id: 'dock',
        col2: panelCol2,
        col3: panelCol3,
        lista: filesListContainer,
        codigo: codeViewContainer,
        titulo: col3Title,
        lerArquivoAtual: () => state.currentFileDataRef,
        gravarArquivoAtual: (fileData) => { state.currentFileDataRef = fileData; },
        abrirCol2() {
            openLogDockInWorkspace();
            openPanelCol(panelCol2);
        },
        fecharCol2() {
            closePanelCol(panelCol2);
        },
        abrirCol3() {
            openCol3Panel();
        },
        fecharCol3() {
            closeCol3();
        },
        aoAbrirGrupo() {
            atualizarBotoesUndoRedo();
        },
        abrirArquivo(fileData) {
            const arquivo = encontrarArquivoUndo(fileData.name);
            const caminhoAlvo = arquivo ? arquivo.caminho : caminhoAbsolutoDoArquivo(fileData.name);
            state.currentUndoFile = caminhoAlvo;
            _focarAbaDoArquivo(caminhoAlvo);
            setupCol3ForFileView(fileData.name, false);
            state.currentOpenedDiff = null;

            vistaDock.marcarCaminhoEntrega(null);
            vistaDock.marcarCaminhoOriginal(caminhoAlvo);

            col3Title.onclick = () => entregarAoMonaco(vistaDock);
            carregarConteudoOriginal(caminhoAlvo, vistaDock);
            atualizarBotoesUndoRedo();
        },
        abrirDiff(dados) {
            const arquivo = encontrarArquivoUndo(dados.fileName);
            const caminhoAlvo = arquivo ? arquivo.caminho : caminhoAbsolutoDoArquivo(dados.fileName);
            state.currentUndoFile = caminhoAlvo;
            _focarAbaDoArquivo(caminhoAlvo);
            const grupoAtual = window.currentActiveLogGroup;
            if (grupoAtual && grupoAtual.files) {

                const fd = grupoAtual.files.find(f => normalizarCaminho(f.name) === normalizarCaminho(dados.fileName));
                if (fd) {
                    state.currentFileDataRef = fd;
                    if (fd._headerEl) marcarFileSelecionado(fd._headerEl);
                }
            }
            window.currentActiveFileBalloonHtml = dados.htmlContent;

            setCodeViewContent((state.isEyeMode && dados.snippetHtml)
                ? dados.snippetHtml
                : dados.htmlContent, false, vistaDock, false);
            setupCol3ForFileView(dados.fileName, true);
            atualizarIconeOlho();

            col3Title.onclick = () => entregarAoMonaco(vistaDock);
            state.currentOpenedDiff = {
                fullHtml: dados.htmlContent,
                snippetHtml: dados.snippetHtml,
                fileName: dados.fileName,

                addedLines: dados.addedLines || [],
                deletedLines: dados.deletedLines || []
            };

            marcarLinhasAlteradas(codeViewContainer, dados);
            rolarParaDestaque(vistaDock);
            atualizarBotoesUndoRedo();

            if (window.WorkspaceView && typeof window.WorkspaceView.revealAndSelectFile === 'function') {
                window.WorkspaceView.revealAndSelectFile(caminhoAlvo);
            }

            vistaDock.marcarCaminhoEntrega(caminhoAlvo);
            vistaDock.marcarCaminhoOriginal(caminhoAlvo);
            syncDocTopBar();
        }
    });

    const vistaHistorico = criarVista({
        id: 'historico',
        col2: panelCol2History,
        col3: panelCol3History,
        lista: filesListContainerHistory,
        codigo: codeViewContainerHistory,
        titulo: col3TitleHistory,
        abrirCol3() {

            if (window.WorkspaceView && typeof window.WorkspaceView.showEditor === 'function') {
                window.WorkspaceView.showEditor();
            }
            if (panelCol3History) panelCol3History.classList.remove('panel-col-closed');
            syncDocTopBar();
        },
        abrirArquivo(fileData) {
            const caminho = caminhoAbsolutoDoArquivo(fileData.name);

            vistaHistorico.marcarCaminhoEntrega(null);
            vistaHistorico.marcarCaminhoOriginal(caminho);
            _modoCodigoHistorico();
            if (col3TitleHistory) col3TitleHistory.textContent = fileData.name;
            carregarConteudoOriginal(caminho, vistaHistorico);
        },
        abrirDiff(dados) {
            const caminho = caminhoAbsolutoDoArquivo(dados.fileName);
            vistaHistorico.marcarCaminhoEntrega(caminho);
            vistaHistorico.marcarCaminhoOriginal(caminho);
            _modoCodigoHistorico();
            if (col3TitleHistory) col3TitleHistory.textContent = dados.fileName;

            setCodeViewContent(dados.htmlContent, false, vistaHistorico, false);
            marcarLinhasAlteradas(codeViewContainerHistory, dados);
            rolarParaDestaque(vistaHistorico);
        }
    });


    function _modoCodigoHistorico() {
        state.isShowingTools = false;
        state.isShowingThoughts = false;
        state.isShowingQuestions = false;
        syncCopyButtons(vistaHistorico, null);
        syncDocTopBar();
    }

    function _focarAbaDoArquivo(caminho) {
        const wv = window.WorkspaceView;
        if (wv && typeof wv.focarAba === 'function') wv.focarAba(caminho);
    }



    function setCodeViewContent(html, plainText, vista = vistaDock, entrar = true) {
        const alvo = vista.codigo;
        if (!alvo) return;

        const novo = plainText
            ? '<pre class="code-view-plain">' + escapeHtml(html) + '</pre>'
            : html;

        if (alvo.innerHTML === novo) return;
        alvo.innerHTML = novo;
        if (state.suppressCol3Anim || !entrar) return;
        alvo.classList.remove('code-view-enter');
        void alvo.offsetWidth;
        alvo.classList.add('code-view-enter');
    }
    function caminhoAbsolutoDoArquivo(nome) {

        const basePath = lblFolder ? lblFolder.textContent : '';
        if (basePath && !/^([a-zA-Z]:[\\/]|\/)/.test(nome)) {
            return window.require('path').join(basePath, nome);
        }
        return nome;
    }
    function encontrarArquivoUndo(nomeRelativo) {

        if (!state.undoRedoFiles || !state.undoRedoFiles.length) return null;
        const alvo = normalizarCaminho(nomeRelativo);
        if (!alvo) return null;
        const exato = state.undoRedoFiles.find(f => normalizarCaminho(f.caminho_relativo) === alvo);
        if (exato) return exato;
        const porSufixo = state.undoRedoFiles.filter(f => {
            const rel = normalizarCaminho(f.caminho_relativo);
            return !!rel && rel.endsWith('/' + alvo);
        });
        if (porSufixo.length === 1) return porSufixo[0];
        const base = alvo.split('/').pop();
        const porNome = state.undoRedoFiles.filter(f => normalizarCaminho(f.nome) === base);
        return porNome.length === 1 ? porNome[0] : null;
    }
    function aplicarRiscadoUndo(fileData, redoCount) {
        if (!fileData || !fileData.diffElements) return;
        const total = fileData.diffElements.length;
        fileData.diffElements.forEach((el, i) => {
            const estaDesfeito = i >= (total - redoCount);
            el.classList.toggle('undo-struck', estaDesfeito);
        });
    }
    function aplicarRiscadoEmTodosArquivos() {

        const grupo = window.currentActiveLogGroup;
        if (!grupo || !grupo.files) return;
        grupo.files.forEach(fileData => {
            const arquivo = encontrarArquivoUndo(fileData.name);
            if (arquivo) {
                aplicarRiscadoUndo(fileData, arquivo.redo_count);
            }
        });
    }
    function encontrarFileDataPorCaminho(caminho) {

        const grupoAtual = window.currentActiveLogGroup;
        if (!grupoAtual || !grupoAtual.files) return null;
        const alvo = normalizarCaminho(caminho);
        if (!alvo) return null;
        const doFim = grupoAtual.files.filter(f => {
            const nome = normalizarCaminho(f.name);
            return !!nome && (nome === alvo || alvo.endsWith('/' + nome));
        });
        if (doFim.length === 1) return doFim[0];
        if (doFim.length > 1) return doFim.find(f => normalizarCaminho(f.name) === alvo) || null;
        const base = alvo.split('/').pop();
        const porNome = grupoAtual.files.filter(f => normalizarCaminho(f.name).split('/').pop() === base);
        return porNome.length === 1 ? porNome[0] : null;
    }
    function selecionarDiffElement(fileData, indice) {
        if (!fileData || !fileData.diffElements) return;
        const el = fileData.diffElements[indice];
        if (!el) return;
        document.querySelectorAll('.diff-selected').forEach(n => n.classList.remove('diff-selected'));
        el.classList.add('diff-selected');
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    const originaisEmCache = new Map();
    function aplicarOriginal(data, vista) {
        if (data.error) {
            setCodeViewContent('Erro: ' + data.error, true, vista);
            return;
        }
        if (data.criado) {
            setCodeViewContent('<span class="text-[var(--text-mutado)] italic">(arquivo criado nesta sessão — não havia código original)</span>', false, vista);
            return;
        }
        if (data.mensagem) {
            setCodeViewContent(data.mensagem, true, vista);
            return;
        }
        setCodeViewContent(data.conteudo || '', true, vista);
    }
    function carregarConteudoOriginal(caminho, vista = vistaDock) {
        if (!caminho) {
            if (vista.codigo) vista.codigo.textContent = '';
            return;
        }
        const emCache = originaisEmCache.get(caminho);
        if (emCache) {
            aplicarOriginal(emCache, vista);
            return;
        }
        fetch(`/api/file_original?caminho=${encodeURIComponent(caminho)}`)
            .then(r => r.json())
            .then(data => {
                if (!data.error) originaisEmCache.set(caminho, data);
                aplicarOriginal(data, vista);
            })
            .catch(err => {
                console.error('Erro ao carregar conteúdo original do arquivo:', err);
                setCodeViewContent('Erro de conexão ao carregar o arquivo original.', true, vista);
            });
    }
    function rolarParaDestaque(vista = vistaDock) {

        const container = vista.codigo;
        if (!container) return;
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                const alvo = container.querySelector('.diff-deleted, .diff-added');
                rolarSuave(alvo, container);
            });
        });
    }
    function rolarSuave(elemento, container) {
        if (!elemento || !container) return;
        const containerRect = container.getBoundingClientRect();
        const elRect = elemento.getBoundingClientRect();

        const MARGEM = 40;
        const jaVisivel = elRect.top >= containerRect.top + MARGEM &&
                          elRect.bottom <= containerRect.bottom - MARGEM;
        if (jaVisivel) return;
        const topoAlvo = container.scrollTop + (elRect.top - containerRect.top) -
                         (container.clientHeight / 2) + (elRect.height / 2);
        const maxScroll = Math.max(0, container.scrollHeight - container.clientHeight);
        const destino = Math.max(0, Math.min(maxScroll, Math.round(topoAlvo)));

        container.scrollTo({ top: destino, behavior: 'smooth' });
    }

    function marcarLado(container, classe, linhas) {
        if (!linhas || !linhas.length) return;
        let consumidas = 0;
        Array.from(container.querySelectorAll('.' + classe)).forEach(no => {
            const pedacos = String(no.textContent).split(NL);

            const quebraFinal = pedacos.length > 1 && pedacos[pedacos.length - 1] === '';
            if (quebraFinal) pedacos.pop();
            if (!pedacos.length) return;
            const frag = document.createDocumentFragment();
            pedacos.forEach((texto, k) => {
                const num = linhas[consumidas + k];
                const s = document.createElement('span');
                s.className = classe;
                if (num != null) s.dataset.ln = String(num);
                s.textContent = texto + (k < pedacos.length - 1 || quebraFinal ? NL : '');
                frag.appendChild(s);
            });
            consumidas += pedacos.length;
            no.replaceWith(frag);
        });
    }
    function marcarLinhasAlteradas(container, dados) {
        if (!container || !dados) return;

        const duasColunas = !!container.querySelector('.diff-two-col');
        const classe = (duasColunas || container.querySelector('.diff-added')) ? 'diff-added' : 'diff-deleted';
        marcarLado(container, classe, classe === 'diff-added' ? dados.addedLines : dados.deletedLines);
    }
    function linhaDoTopo(container, porGrelha) {

        const marcas = [];
        const base = container.getBoundingClientRect().top - container.scrollTop;
        container.querySelectorAll('[data-ln]').forEach(no => {
            const r = no.getBoundingClientRect();
            marcas.push({ ln: Number(no.dataset.ln), topo: r.top - base });
        });
        if (!marcas.length) {

            if (!porGrelha) return null;
            return (container.scrollTop - PADDING_TOPO) / ALTURA_LINHA + 1;
        }
        marcas.sort((a, b) => a.topo - b.topo);
        const topo = container.scrollTop;
        const primeira = marcas[0];
        const ultima = marcas[marcas.length - 1];
        const spanLinhas = ultima.ln - primeira.ln;
        const spanPx = ultima.topo - primeira.topo;
        const altura = (spanLinhas > 0 && spanPx > 0) ? spanPx / spanLinhas : 18;
        if (topo <= primeira.topo) return primeira.ln - (primeira.topo - topo) / altura;
        if (topo >= ultima.topo) return ultima.ln + (topo - ultima.topo) / altura;
        for (let i = 1; i < marcas.length; i++) {
            const a = marcas[i - 1];
            const b = marcas[i];
            if (topo > b.topo) continue;
            const t = b.topo === a.topo ? 0 : (topo - a.topo) / (b.topo - a.topo);
            return a.ln + t * (b.ln - a.ln);
        }
        return ultima.ln;
    }

    function linhaNoFicheiroAtual(container, linha) {
        if (linha == null) return linha;
        const removidas = container.querySelectorAll('.diff-deleted[data-ln]');
        if (!removidas.length || container.querySelector('.diff-added')) return linha;
        let acima = 0;
        removidas.forEach(no => {
            if (Number(no.dataset.ln) < linha) acima++;
        });
        return linha - acima;
    }
    function entregarAoMonaco(vista) {
        const container = vista.codigo;
        if (!container) return false;

        const doHistorico = vista.id === 'historico';
        const painelAberto = state.isShowingTools || state.isShowingThoughts || state.isShowingQuestions;
        const manterCamada = painelAberto && doHistorico;
        if (painelAberto && !manterCamada) return false;

        const caminhoMonaco = vista.caminhoEntrega();
        const caminhoOriginal = vista.caminhoOriginal();
        const alvo = caminhoMonaco || caminhoOriginal;

        const linha = painelAberto ? null : (container.querySelector('[data-ln]')
            ? linhaNoFicheiroAtual(container, linhaDoTopo(container))
            : (caminhoMonaco ? null : linhaDoTopo(container, true)));
        vista.marcarCaminhoEntrega(null);
        if (!alvo) {
            if (!manterCamada) vista.fecharCol3();
            return false;
        }
        const wv = window.WorkspaceView;
 
        const fechar = () => {
            if (!manterCamada) vista.fecharCol3();
            syncDocTopBar();
        };
        if (wv && typeof wv.transferirDaCamada === 'function') {

            if (!caminhoMonaco && vista.id === 'dock') openLogDockInWorkspace();
            const entrega = wv.transferirDaCamada(caminhoMonaco, linha, caminhoMonaco ? null : caminhoOriginal);
            state.codigoDoHistoricoNoEditor = doHistorico;
            if (entrega && typeof entrega.then === 'function') {
                entrega.then(fechar, fechar);
                return true;
            }
            fechar();
            return !!entrega;
        }
        fechar();
        return false;
    }

    function sincronizarColunasDiff(e) {
        const col = e.target;
        if (!col || !col.classList || !col.classList.contains('diff-col')) return;
        const pai = col.parentElement;
        if (!pai) return;
        const colunas = pai.querySelectorAll(':scope > .diff-col');
        if (colunas.length < 2) return;
        const outra = colunas[0] === col ? colunas[1] : colunas[0];
        if (!outra || Math.abs(outra.scrollLeft - col.scrollLeft) < 0.5) return;
        outra.scrollLeft = col.scrollLeft;
    }
    function instalarSincroniaDeColunas(container) {
        if (container) container.addEventListener('scroll', sincronizarColunasDiff, true);
    }
    instalarSincroniaDeColunas(codeViewContainer);
    instalarSincroniaDeColunas(codeViewContainerHistory);
    if (codeViewContainer) {
        codeViewContainer.addEventListener('click', (e) => {
            if (e.target.closest('button, a, input, textarea, select')) return;
            const selecao = window.getSelection();
            if (selecao && String(selecao).length > 0) return;
            entregarAoMonaco(vistaDock);
        });
    }

    if (codeViewContainerHistory) {
        codeViewContainerHistory.addEventListener('click', (e) => {
            if (e.target.closest('button, a, input, textarea, select')) return;
            const selecao = window.getSelection();
            if (selecao && String(selecao).length > 0) return;
            entregarAoMonaco(vistaHistorico);
        });
    }
    function selecionarArquivo(fileData, vista = vistaDock) {

        const raiz = vista.col2 || document;
        raiz.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
        vista.abrirCol3();
        vista.marcarArquivoAtual(fileData);
        vista.abrirArquivo(fileData);
    }
    function encurtarNomeArquivo(caminho) {
        const partes = (caminho || '').replace(/\\/g, '/').split('/').filter(Boolean);
        if (partes.length <= 1) return caminho || '';
        return partes.slice(-2).join('/');
    }
    function marcarFileSelecionado(fileHeader) {

        const raiz = (fileHeader && typeof fileHeader.closest === 'function' && fileHeader.closest('[data-col-vista]')) || document;
        raiz.querySelectorAll('.file-card-header').forEach(h => h.classList.remove('file-card-selected'));
        if (fileHeader) fileHeader.classList.add('file-card-selected');
    }
    function adicionarFileNaLista(fileData, vista = vistaDock) {
        if (!vista || !vista.lista) return;
        const fileEl = document.createElement('div');
        fileEl.className = 'rounded-[10px] overflow-hidden';
        const fileHeader = document.createElement('div');
        fileHeader.className = 'file-card-header px-3.5 py-2.5 text-[13px] text-[var(--oliva)] cursor-pointer transition-colors flex justify-between items-center min-h-[54px]';
        if (fileData.deleted) fileHeader.classList.add('file-deleted');
        fileHeader.innerHTML = `<span class="flex-1 truncate font-semibold" title="${fileData.name}">${encurtarNomeArquivo(fileData.name)}</span><span class="file-toggle-icon text-[var(--text-mutado)] text-lg font-mono leading-none ml-2 cursor-pointer hover:text-[var(--text-branco)] transition-colors select-none">+</span>`;
        const fileContent = document.createElement('div');
        fileContent.className = 'card-collapsible';
        const fileContentClip = document.createElement('div');
        fileContentClip.className = 'card-collapsible-clip';
        const fileContentInner = document.createElement('div');
        fileContentInner.className = 'p-2 flex flex-col gap-2';
        fileContentClip.appendChild(fileContentInner);
        fileContent.appendChild(fileContentClip);
        fileData.diffElements.forEach(diffEl => fileContentInner.appendChild(diffEl));
        if (fileData.diffElements.length === 0) {
            fileContentInner.innerHTML = `<div class="p-2 text-sm text-[var(--text-mutado)] font-mono">Nenhuma alteração de código.</div>`;
        }
        const toggleIcon = fileHeader.querySelector('.file-toggle-icon');
        function expandir() {
            Array.from(vista.lista.children).forEach(card => {
                if (card === fileEl) return;
                const content = card.children[1];
                const icon = card.querySelector('.file-toggle-icon');
                if (content && content.classList.contains('card-collapsible-open')) {
                    content.classList.remove('card-collapsible-open');
                    if (icon) icon.textContent = '+';
                }
            });
            fileContent.classList.add('card-collapsible-open');
            if (toggleIcon) toggleIcon.textContent = '-';
        }
        function recolher() {
            fileContent.classList.remove('card-collapsible-open');
            if (toggleIcon) toggleIcon.textContent = '+';
        }

        fileHeader.addEventListener('click', () => {
            if (vista.arquivoAtual() === fileData && vista.col3Aberta()) {
                vista.fecharCol3();
                return;
            }
            const estavaFechado = !fileContent.classList.contains('card-collapsible-open');
            if (estavaFechado) {
                expandir();
            }
            marcarFileSelecionado(fileHeader);
            if (vista.aoSelecionarArquivo) vista.aoSelecionarArquivo();
            selecionarArquivo(fileData, vista);
        });
        if (toggleIcon) {
            toggleIcon.addEventListener('click', (e) => {
                e.stopPropagation();
                if (!fileContent.classList.contains('card-collapsible-open')) {
                    expandir();
                    marcarFileSelecionado(fileHeader);
                    selecionarArquivo(fileData, vista);
                } else {
                    recolher();
                }
            });
        }
        fileEl.appendChild(fileHeader);
        fileEl.appendChild(fileContent);
        vista.lista.appendChild(fileEl);

        fileData._headerEl = fileHeader;
        fileData._fileEl = fileEl;
        fileData._contentInner = fileContentInner;
        fileData._toggleIcon = toggleIcon;
    }
    function sincronizarArquivosEmTempoReal(group, fileData, isNewFile) {
        if (window.currentActiveLogGroup !== group) return;
        if (!filesListContainer) return;
        const placeholder = filesListContainer.querySelector('.panel-empty');
        if (placeholder) placeholder.remove();
        if (isNewFile) {
            adicionarFileNaLista(fileData);
        } else if (fileData._contentInner) {
            fileData._contentInner.innerHTML = '';
            fileData.diffElements.forEach(diffEl => fileData._contentInner.appendChild(diffEl));
            if (fileData.diffElements.length === 0) {
                fileData._contentInner.innerHTML = '<div class="p-2 text-sm text-[var(--text-mutado)] font-mono">Nenhuma alteração de código.</div>';
            }
        }
    }
    function atualizarBotoesUndoRedo() {
        fetch('/api/undo_redo_status')
            .then(r => r.json())
            .then(data => {
                state.undoRedoFiles = data.files || [];
                atualizarEstadoBotoes();
                if (state.currentFileDataRef) {
                    const arquivo = encontrarArquivoUndo(state.currentFileDataRef.name);
                    if (arquivo) {
                        state.currentUndoFile = arquivo.caminho;
                    }
                }
                aplicarRiscadoEmTodosArquivos();
            })
            .catch(() => {
            });
    }
    function normalizarCaminho(c) {
        return (c || '').replace(/\\/g, '/').toLowerCase();
    }
    function atualizarEstadoBotoes() {
        const alvo = normalizarCaminho(state.currentUndoFile);
        const selecionado = state.undoRedoFiles.find(f => normalizarCaminho(f.caminho) === alvo);
        if (btnUndo) btnUndo.disabled = !selecionado || !selecionado.can_undo;
        if (btnRedo) btnRedo.disabled = !selecionado || !selecionado.can_redo;
        if (lblUndoCount) lblUndoCount.textContent = selecionado ? selecionado.undo_count : '';
        if (lblRedoCount) lblRedoCount.textContent = selecionado ? selecionado.redo_count : '';
    }
    function executarUndoRedo(acao) {
        const btn = acao === 'undo' ? btnUndo : btnRedo;
        if (btn && btn.disabled) return;
        if (!state.currentUndoFile) return;

        const fileData = state.currentFileDataRef || encontrarFileDataPorCaminho(state.currentUndoFile);
        const totalItens = fileData ? fileData.diffElements.length : 0;
        const arquivoAtual = encontrarArquivoUndo(state.currentUndoFile);
        const redoCountAntes = arquivoAtual ? arquivoAtual.redo_count : 0;
        fetch(`/api/${acao}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminho: state.currentUndoFile })
        })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'ok' || data.status === 'empty') {
                    state.currentOpenedDiff = null;
                    atualizarBotoesUndoRedo();
                    if (data.status === 'ok' && totalItens > 0) {

                        const indice = acao === 'undo'
                            ? totalItens - redoCountAntes - 2
                            : totalItens - redoCountAntes;
                        if (indice < 0) {
                            if (fileData && fileData._headerEl) {
                                fileData._headerEl.click();
                            }
                            return;
                        }
                        const el = fileData.diffElements[indice];
                        if (el && typeof el._abrirDiff === 'function') {
                            el._abrirDiff();
                            el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                            return;
                        }
                        selecionarDiffElement(fileData, indice);
                    }
                } else {
                    lblStatus.textContent = 'Erro: ' + (data.message || 'operação falhou');
                }
            })
            .catch(err => {
                console.error(`Erro ao executar ${acao}:`, err);
                lblStatus.textContent = `Erro de conexão ao ${acao === 'undo' ? 'desfazer' : 'refazer'}.`;
            });
    }
    let pastaSelecionada = '';
    let restauracaoEmCurso = null;

    function aplicarPastaSelecionada(folder) {
        const jaEra = pastaSelecionada === folder;
        pastaSelecionada = folder;
        lblFolder.textContent = folder;
        if (btnSelectFolder) {
            btnSelectFolder.classList.remove('text-[var(--text-branco)]');
            btnSelectFolder.classList.add('text-[var(--oliva)]');
            btnSelectFolder.classList.add('folder-selected');
            btnSelectFolder.title = folder;
        }
        if (!jaEra) {
            resetWorkspaceUI();
            if (window.WorkspaceView && typeof window.WorkspaceView.reloadExplorer === 'function') {
                window.WorkspaceView.reloadExplorer();
            }
            if (window.WorkspaceView && typeof window.WorkspaceView.loadVenvName === 'function') {
                window.WorkspaceView.loadVenvName();
            }
        }
    }

    async function abrirPasta(folderPath, recarregando) {
        lblStatus.textContent = 'Carregando diretório...';
        for (let i = 0; i < 20; i++) {
            try {
                const response = await fetch('/api/set_folder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folder: folderPath })
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data.folder) {
                        aplicarPastaSelecionada(data.folder);
                        lblStatus.textContent = recarregando
                            ? 'Diretório recarregado.'
                            : 'Diretório carregado.';
                        return true;
                    }
                }
            } catch (e) {
                console.log(`Tentativa ${i+1} falhou, aguardando servidor...`);
            }
            await new Promise(r => setTimeout(r, 1000));
        }
        lblStatus.textContent = 'Erro: Servidor não respondeu.';
        console.error('Erro ao selecionar pasta após várias tentativas.');
        return false;
    }

    async function selectFolder() {
        closePlusMenus();
        try {
            const folderPath = await ipcRenderer.invoke('select-folder', pastaSelecionada);
            if (folderPath) await abrirPasta(folderPath, false);
        } catch (error) {
            console.error('Erro ao selecionar pasta:', error);
        }
    }

    function restaurarPastaSelecionada() {

        if (restauracaoEmCurso) return restauracaoEmCurso;
        restauracaoEmCurso = _restaurarPasta().finally(() => {
            restauracaoEmCurso = null;
        });
        return restauracaoEmCurso;
    }

    async function _restaurarPasta() {
        let data = null;
        try {
            const r = await fetch('/api/env_info');
            data = await r.json();
        } catch (e) {
            return;
        }
        if (!data) return;
        if (data.folder) {
            const jaEra = pastaSelecionada === data.folder;
            aplicarPastaSelecionada(data.folder);
            if (!jaEra) lblStatus.textContent = 'Diretório recarregado.';
            return;
        }
        if (data.ultima_pasta) await abrirPasta(data.ultima_pasta, true);
    }
    function normalizeFsPath(p) {
        return (p || '').replace(/\\/g, '/');
    }
    function dividirDiffEmLinhas(diffParts) {
        const linhas = [];
        diffParts.forEach(part => {
            const pedacos = String(part.text || '').split(NL);
            pedacos.forEach((linhaTexto, idx) => {
                const ehUltima = idx === pedacos.length - 1;
                if (ehUltima && linhaTexto === '') return;
                const conteudo = ehUltima ? linhaTexto : linhaTexto + NL;
                linhas.push({ tipo: part.type, texto: conteudo });
            });
        });
        return linhas;
    }
    function gerarSnippetHtml(diffParts, lado) {
        const LINHAS_CONTEXTO = 2;
        const ehAlterada = (tipo) => lado === 'original'
            ? (tipo === 'deleted' || tipo === 'modified')
            : (tipo === 'added');

        const ehPertinente = (tipo) => lado === 'original'
            ? (tipo === 'unmodified' || tipo === 'deleted' || tipo === 'modified')
            : (tipo === 'unmodified' || tipo === 'added');
        const linhas = dividirDiffEmLinhas(diffParts).filter(l => ehPertinente(l.tipo));
        if (!linhas.length) return '';
        const marcadas = linhas.map(l => ehAlterada(l.tipo));
        const incluir = new Array(linhas.length).fill(false);

        let primeiro = -1;
        let ultimo = -1;
        for (let i = 0; i < linhas.length; i++) {
            if (!marcadas[i]) continue;
            if (primeiro === -1) primeiro = i;
            ultimo = i;
        }
        if (primeiro === -1) return '';
        for (let i = primeiro; i <= ultimo; i++) incluir[i] = true;
        const linhaVazia = (i) => linhas[i].texto.trim() === '';

        let contagem = 0;
        for (let j = primeiro - 1; j >= 0 && contagem < LINHAS_CONTEXTO; j--) {
            if (linhaVazia(j)) continue;
            incluir[j] = true;
            contagem++;
        }

        contagem = 0;
        for (let j = ultimo + 1; j < linhas.length && contagem < LINHAS_CONTEXTO; j++) {
            if (linhaVazia(j)) continue;
            incluir[j] = true;
            contagem++;
        }
        let html = '';
        let ultimoIncluido = -1;
        for (let i = 0; i < linhas.length; i++) {
            if (!incluir[i]) continue;
            if (ultimoIncluido !== -1 && i > ultimoIncluido + 1) {
                html += `<span class="diff-unmodified">


</span>`;
            }
            const l = linhas[i];
            const colorClass = marcadas[i]
                ? (lado === 'original' ? 'diff-deleted' : 'diff-added')
                : 'diff-unmodified';
            html += `<span class="${colorClass}">${escapeHtml(l.texto)}</span>`;
            ultimoIncluido = i;
        }
        return html;
    }
    function atualizarIconeOlho() {
        if (!btnEyeDiff) return;
        const eyeOn = btnEyeDiff.querySelector('#eye-on');
        const eyeOff = btnEyeDiff.querySelector('#eye-off');
        if (state.isEyeMode) {
            btnEyeDiff.classList.remove('text-[var(--text-mutado)]');
            btnEyeDiff.classList.add('text-[var(--oliva)]');
            btnEyeDiff.title = 'Modo foco ATIVADO: exibir apenas trechos alterados';
            if (eyeOn) eyeOn.classList.remove('hidden');
            if (eyeOff) eyeOff.classList.add('hidden');
        } else {
            btnEyeDiff.classList.remove('text-[var(--oliva)]');
            btnEyeDiff.classList.add('text-[var(--text-mutado)]');
            btnEyeDiff.title = 'Modo foco: exibir apenas trechos alterados';
            if (eyeOn) eyeOn.classList.add('hidden');
            if (eyeOff) eyeOff.classList.remove('hidden');
        }
    }

export {
    setCodeViewContent,
    encontrarArquivoUndo,
    aplicarRiscadoUndo,
    aplicarRiscadoEmTodosArquivos,
    encontrarFileDataPorCaminho,
    selecionarDiffElement,
    carregarConteudoOriginal,
    rolarParaDestaque,
    rolarSuave,
    selecionarArquivo,
    adicionarFileNaLista,
    sincronizarArquivosEmTempoReal,
    atualizarBotoesUndoRedo,
    normalizarCaminho,
    atualizarEstadoBotoes,
    executarUndoRedo,
    selectFolder,
    restaurarPastaSelecionada,
    normalizeFsPath,
    gerarSnippetHtml,
    atualizarIconeOlho,
    marcarLinhasAlteradas,
    createChildBalloon
};
    function createChildBalloon(title, htmlContent, snippetHtml, rawTextOld, rawTextNew, fileName, sessionTools, fullOriginalText, fullNewText, deletedLines, addedLines, origToMod, modToOrig, subtitle) {
        const child = document.createElement('div');
        child.className = 'rounded-[10px] overflow-hidden';
        const header = document.createElement('div');
        header.className = 'px-3.5 py-2.5 cursor-pointer flex justify-between items-center hover:bg-[var(--bg-hover-suave)] transition-colors min-h-[54px]';
        const titleContainer = document.createElement('div');
        titleContainer.className = 'flex flex-col justify-center flex-1';
        const titleSpan = document.createElement('span');
        titleSpan.className = 'undo-title text-[13px] text-[var(--text-code-dark)] leading-tight hover:text-[var(--text-branco)] transition-colors';
        titleSpan.textContent = title;
        titleContainer.appendChild(titleSpan);
        if (subtitle) {
            const subSpan = document.createElement('span');
            subSpan.className = 'text-[11px] text-[var(--text-mutado)] leading-tight mt-0.5';
            subSpan.textContent = subtitle;
            subSpan.title = subtitle;
            titleContainer.appendChild(subSpan);
        }
        const actionsContainer = document.createElement('div');
        actionsContainer.className = 'flex items-center gap-2';
        const isSubstitution = rawTextOld && rawTextNew;
        if (rawTextOld) {
            const color = 'text-[var(--perigo)]';
            const tooltip = isSubstitution ? 'Copiar código substituído' : 'Copiar código';
            actionsContainer.appendChild(createCopyButton(rawTextOld, color, tooltip));
        }
        if (rawTextNew) {
            const color = 'text-[var(--oliva)]';
            const tooltip = isSubstitution ? 'Copiar código atualizado' : 'Copiar código';
            actionsContainer.appendChild(createCopyButton(rawTextNew, color, tooltip));
        }
        header.appendChild(titleContainer);
        header.appendChild(actionsContainer);

        const dados = {
            title: title,
            subtitle: subtitle || '',
            htmlContent: htmlContent,
            snippetHtml: snippetHtml,
            rawTextOld: rawTextOld,
            rawTextNew: rawTextNew,
            fileName: fileName,
            fullOriginalText: fullOriginalText || '',
            fullNewText: fullNewText || '',
            deletedLines: deletedLines || [],
            addedLines: addedLines || [],
            origToMod: origToMod || [],
            modToOrig: modToOrig || []
        };
        header.addEventListener('click', (e) => {
            e.stopPropagation();

            const vista = vistaDoElemento(child) || vistaDock;
            const raiz = vista.col2 || document;
            raiz.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
            child.classList.add('diff-selected');
            vista.abrirCol3();
            vista.abrirDiff(dados);
            

            

            

            
        });

        child._abrirDiff = () => header.click();
        child._data = dados;
        child.appendChild(header);
        return child;
    }
