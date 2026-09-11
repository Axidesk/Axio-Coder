const { ipcRenderer } = window.require('electron');
import { state } from './state.js';
import * as dom from './dom.js';
import { closeCol3, closePlusMenus, isCol3Open, isHistoryOpen, openCol3Overlay, openLogDockInWorkspace, openPanelCol, setupCol3ForFileView } from './layout.js';
import { escapeHtml } from './messages.js';
import { resetWorkspaceUI } from './ui.js';
import { createCopyButton } from './clipboard.js';

const { btnEyeDiff, btnRedo, btnSelectFolder, btnUndo, codeViewContainer, col3Title, filesListContainer, lblFolder, lblRedoCount, lblStatus, lblUndoCount, panelCol3 } = dom;
const NL = String.fromCharCode(10);


    function setCodeViewContent(html, plainText) {
        if (plainText) {
            codeViewContainer.textContent = html;
        } else {
            codeViewContainer.innerHTML = html;
        }
        if (state.suppressCol3Anim) return;
        codeViewContainer.classList.remove('code-view-enter');
        void codeViewContainer.offsetWidth;
        codeViewContainer.classList.add('code-view-enter');
    }
    function encontrarArquivoUndo(nomeRelativo) {
        if (!state.undoRedoFiles || !state.undoRedoFiles.length) return null;
        const alvo = (nomeRelativo || '').replace(/\\/g, '/');
        const base = alvo.split('/').pop() || alvo;
        return state.undoRedoFiles.find(f =>
            ((f.caminho_relativo || '').replace(/\\/g, '/') === alvo) ||
            ((f.nome || '') === base)
        ) || null;
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
        // Reaplica o riscado (undo-struck) a TODOS os arquivos do grupo ativo,
        // não apenas ao arquivo selecionado. Assim, quando o agente desfaz uma
        // edição durante a execução, todos os cards da pilha de ficheiros do log
        // refletem o estado desfeito (mesmo visual do histórico).
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
        // Localiza o objeto de arquivo (com diffElements) no grupo de log ativo pelo nome.
        const grupoAtual = window.currentActiveLogGroup;
        if (!grupoAtual || !grupoAtual.files) return null;
        const base = (caminho || '').replace(/\\/g, '/').split('/').pop();
        return grupoAtual.files.find(f => (f.name || '') === base) || null;
    }
    function selecionarDiffElement(fileData, indice) {
        // Move o destaque de seleção para o item da pilha indicado, sem fechar/recarregar
        // a coluna 3 (a exibição do arquivo já é tratada por carregarConteudoArquivo).
        if (!fileData || !fileData.diffElements) return;
        const el = fileData.diffElements[indice];
        if (!el) return;
        document.querySelectorAll('.diff-selected').forEach(n => n.classList.remove('diff-selected'));
        el.classList.add('diff-selected');
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    function carregarConteudoOriginal(caminho) {
        if (!caminho) {
            codeViewContainer.textContent = '';
            return;
        }
        fetch(`http://127.0.0.1:5000/api/file_original?caminho=${encodeURIComponent(caminho)}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    setCodeViewContent('Erro: ' + data.error, true);
                    return;
                }
                if (data.criado) {
                    setCodeViewContent('<span class="text-[var(--text-mutado)] italic">(arquivo criado nesta sessão — não havia código original)</span>');
                    return;
                }
                setCodeViewContent(data.conteudo || '', true);
            })
            .catch(err => {
                console.error('Erro ao carregar conteúdo original do arquivo:', err);
                setCodeViewContent('Erro de conexão ao carregar o arquivo original.', true);
            });
    }
    function rolarParaDestaque() {
        // Rola suavemente até o primeiro trecho destacado (vermelho/verde).
        // Usamos dois rAF para o layout já estar pronto após o re-render
        // (innerHTML). Isso evita a rolagem "pulada"/brusca ao subir.
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                const alvo = codeViewContainer.querySelector('.diff-deleted, .diff-added');
                rolarSuave(alvo, codeViewContainer);
            });
        });
    }
    function rolarSuave(elemento, container) {
        if (!elemento || !container) return;
        const containerRect = container.getBoundingClientRect();
        const elRect = elemento.getBoundingClientRect();
        // Tolerância: se o trecho já está visível, não rola de novo
        // (corrige o movimento desnecessário quando o texto está proximo).
        const MARGEM = 40;
        const jaVisivel = elRect.top >= containerRect.top + MARGEM &&
                          elRect.bottom <= containerRect.bottom - MARGEM;
        if (jaVisivel) return;
        // Centraliza o trecho calculando a posição manualmente. O scrollTo com
        // 'smooth' sobe e desce de forma suave (mais confiável que scrollIntoView).
        const topoAlvo = container.scrollTop + (elRect.top - containerRect.top) -
                         (container.clientHeight / 2) + (elRect.height / 2);
        container.scrollTo({ top: Math.max(0, topoAlvo), behavior: 'smooth' });
    }
    function selecionarArquivo(fileData) {
        // Ao abrir o arquivo pelo cabeçalho, limpa o destaque de item específico
        document.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
        const arquivo = encontrarArquivoUndo(fileData.name);
        let caminhoAlvo = arquivo ? arquivo.caminho : fileData.name;
        const basePath = document.getElementById('lbl-folder').textContent;
        if (basePath && !/^([a-zA-Z]:[\\/]|\/)/.test(caminhoAlvo)) {
            caminhoAlvo = window.require('path').join(basePath, caminhoAlvo);
        }
        state.currentUndoFile = caminhoAlvo;

        if (isHistoryOpen()) {
            openCol3Overlay();
            state.currentFileDataRef = fileData;
        } else {
            openPanelCol(panelCol3);
        }

        setupCol3ForFileView(fileData.name, false);
        state.currentOpenedDiff = null;
        col3Title.onclick = () => {
            openLogDockInWorkspace();
            if (window.WorkspaceView && typeof window.WorkspaceView.openFileFromLog === 'function') {
                window.WorkspaceView.openFileFromLog(caminhoAlvo);
            }
        };
        carregarConteudoOriginal(state.currentUndoFile);
        atualizarBotoesUndoRedo();
    }
    function encurtarNomeArquivo(caminho) {
        const partes = (caminho || '').replace(/\\/g, '/').split('/').filter(Boolean);
        if (partes.length <= 1) return caminho || '';
        return partes.slice(-2).join('/');
    }
    function marcarFileSelecionado(fileHeader) {
        document.querySelectorAll('.file-card-header').forEach(h => h.classList.remove('file-card-selected'));
        if (fileHeader) fileHeader.classList.add('file-card-selected');
    }
    function adicionarFileNaLista(fileData) {
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
            // Acordeão: recolhe os demais cards de arquivo para manter apenas um aberto
            Array.from(filesListContainer.children).forEach(card => {
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
        // Clique no cabeçalho (fora do ícone): abre/seleciona. Se já expandido, apenas
        // seleciona novamente (NÃO recolhe). Recolher so pelo ícone de "-".
        fileHeader.addEventListener('click', () => {
            if (!isHistoryOpen() && state.currentFileDataRef === fileData && isCol3Open()) {
                closeCol3();
                return;
            }
            const estavaFechado = !fileContent.classList.contains('card-collapsible-open');
            if (estavaFechado) {
                expandir();
            }
            marcarFileSelecionado(fileHeader);
            state.currentFileDataRef = fileData;
            selecionarArquivo(fileData);
        });
        if (toggleIcon) {
            toggleIcon.addEventListener('click', (e) => {
                e.stopPropagation();
                if (!fileContent.classList.contains('card-collapsible-open')) {
                    expandir();
                    marcarFileSelecionado(fileHeader);
                    state.currentFileDataRef = fileData;
                    selecionarArquivo(fileData);
                } else {
                    recolher();
                }
            });
        }
        fileEl.appendChild(fileHeader);
        fileEl.appendChild(fileContent);
        filesListContainer.appendChild(fileEl);
        // Guarda referência ao cabeçalho do arquivo para o undo/redo conseguir
        // "selecionar o arquivo" (conteúdo original) quando todas as edições forem desfeitas (0/N).
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
        // Consulta o estado das pilhas no backend e habilita/desabilita os botões
        fetch('http://127.0.0.1:5000/api/undo_redo_status')
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
                // Falha silenciosa: mantém os botões como estão
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
        // Captura o estado da pilha ANTES da operação para selecionar o item correto depois.
        // diffElements está em ordem cronológica: índice 0 = edição mais antiga,
        // índice total-1 = edição mais recente. O backend desfaz/refaz sempre o topo (LIFO).
        const fileData = state.currentFileDataRef || encontrarFileDataPorCaminho(state.currentUndoFile);
        const totalItens = fileData ? fileData.diffElements.length : 0;
        const arquivoAtual = encontrarArquivoUndo(state.currentUndoFile);
        const redoCountAntes = arquivoAtual ? arquivoAtual.redo_count : 0;
        fetch(`http://127.0.0.1:5000/api/${acao}`, {
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
                        // Mapeia a ação para o item da pilha recém-desfeito/refeito,
                        // fazendo a seleção "caminhar" junto com a linha do tempo.
                        const indice = acao === 'undo'
                            ? totalItens - redoCountAntes - 2
                            : totalItens - redoCountAntes;
                        // Se desfez tudo (0/N), seleciona o cabeçalho do arquivo (conteúdo original).
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
    async function selectFolder() {
        closePlusMenus();
        try {
            const folderPath = await ipcRenderer.invoke('select-folder');
            if (folderPath) {
                let success = false;
                lblStatus.textContent = 'Iniciando sistema...';
                for (let i = 0; i < 20; i++) {
                    try {
                        const response = await fetch('http://127.0.0.1:5000/api/set_folder', { 
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ folder: folderPath })
                        });
                        if (response.ok) {
                            const data = await response.json();
                            if (data.folder) {
                                lblFolder.textContent = data.folder;
                                lblStatus.textContent = 'Diretório selecionado.';
                                if (btnSelectFolder) {
                                    btnSelectFolder.classList.remove('text-[var(--text-branco)]');
                                    btnSelectFolder.classList.add('text-[var(--oliva)]');
                                    btnSelectFolder.classList.add('folder-selected');
                                    btnSelectFolder.title = data.folder;
                                }
                                resetWorkspaceUI();
                                if (window.WorkspaceView && typeof window.WorkspaceView.reloadExplorer === 'function') {
                                    window.WorkspaceView.reloadExplorer();
                                }
                                if (window.WorkspaceView && typeof window.WorkspaceView.loadVenvName === 'function') {
                                    window.WorkspaceView.loadVenvName();
                                }
                                success = true;
                                break;
                            }
                        }
                    } catch (e) {
                        console.log(`Tentativa ${i+1} falhou, aguardando servidor...`);
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
                if (!success) {
                    lblStatus.textContent = 'Erro: Servidor não respondeu.';
                    console.error('Erro ao selecionar pasta após várias tentativas.');
                }
            }
        } catch (error) {
            console.error('Erro ao selecionar pasta:', error);
        }
    }
    function restaurarPastaSelecionada() {
        fetch('http://127.0.0.1:5000/api/env_info')
            .then(r => r.json())
            .then(data => {
                if (data && data.folder) {
                    lblFolder.textContent = data.folder;
                    if (btnSelectFolder) {
                        btnSelectFolder.classList.remove('text-[var(--text-branco)]');
                        btnSelectFolder.classList.add('text-[var(--oliva)]');
                        btnSelectFolder.classList.add('folder-selected');
                        btnSelectFolder.title = data.folder;
                    }
                }
            })
            .catch(() => {});
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
                if (ehUltima && linhaTexto === '') return; // ignora vazio final (texto terminava em \n)
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
        // Cada lado mostra apenas as linhas que lhe pertencem. Isso impede que
        // linhas "added" vazem para o painel original (e vice-versa), fazendo
        // as linhas de referência (cinza) coincidirem entre os dois painéis.
        const ehPertinente = (tipo) => lado === 'original'
            ? (tipo === 'unmodified' || tipo === 'deleted' || tipo === 'modified')
            : (tipo === 'unmodified' || tipo === 'added');
        const linhas = dividirDiffEmLinhas(diffParts).filter(l => ehPertinente(l.tipo));
        if (!linhas.length) return '';
        const marcadas = linhas.map(l => ehAlterada(l.tipo));
        const incluir = new Array(linhas.length).fill(false);
        // Localiza a faixa de alteração (primeiro..último trecho marcado).
        let primeiro = -1;
        let ultimo = -1;
        for (let i = 0; i < linhas.length; i++) {
            if (!marcadas[i]) continue;
            if (primeiro === -1) primeiro = i;
            ultimo = i;
        }
        if (primeiro === -1) return '';
        // Mantém todo o bloco de mudança (incluindo linhas idênticas internas).
        for (let i = primeiro; i <= ultimo; i++) incluir[i] = true;
        const linhaVazia = (i) => linhas[i].texto.trim() === '';
        // Contexto anterior: até LINHAS_CONTEXTO linhas com conteúdo antes do bloco.
        let contagem = 0;
        for (let j = primeiro - 1; j >= 0 && contagem < LINHAS_CONTEXTO; j--) {
            if (linhaVazia(j)) continue;
            incluir[j] = true;
            contagem++;
        }
        // Contexto posterior: até LINHAS_CONTEXTO linhas com conteúdo depois do bloco.
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
        header.addEventListener('click', (e) => {
            e.stopPropagation();
            // Se clicar no mesmo arquivo que já está aberto, ele fecha a coluna 3
            // (clique duplo não fecha mais a coluna 3)
            // Marca este item como selecionado na pilha de edições (destaque fixo).
            // Limpa GLOBALMENTE para não deixar item de outra pilha/arquivo selecionado.
            document.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
            child.classList.add('diff-selected');
            // Garante que o undo/redo atue no arquivo deste item da pilha.
            const arquivo = encontrarArquivoUndo(fileName);
            let caminhoAlvo = arquivo ? arquivo.caminho : fileName;
            const basePath = document.getElementById('lbl-folder').textContent;
            if (basePath && !/^([a-zA-Z]:[\\/]|\/)/.test(caminhoAlvo)) {
                caminhoAlvo = window.require('path').join(basePath, caminhoAlvo);
            }
            state.currentUndoFile = caminhoAlvo;
            const grupoAtual = window.currentActiveLogGroup;
            if (grupoAtual && grupoAtual.files) {
                const fd = grupoAtual.files.find(f => f.name === fileName);
                if (fd) state.currentFileDataRef = fd;
                if (fd && fd._headerEl) marcarFileSelecionado(fd._headerEl);
            }
            window.currentActiveFileBalloonHtml = htmlContent;
            const isHistOpen = isHistoryOpen();
            if (isHistOpen) {
                openCol3Overlay();
                state.currentUndoFile = caminhoAlvo;
                if (grupoAtual && grupoAtual.files) {
                    const fd = grupoAtual.files.find(f => f.name === fileName);
                    if (fd) state.currentFileDataRef = fd;
                }
            } else {
                openPanelCol(panelCol3);
            }
            
            setupCol3ForFileView(fileName, true);
            atualizarIconeOlho();
            
            const openInWorkspace = () => {
                openLogDockInWorkspace();
                if (window.WorkspaceView && typeof window.WorkspaceView.openFileFromLog === 'function') {
                    window.WorkspaceView.openFileFromLog(caminhoAlvo, rawTextNew || rawTextOld, {
                        original: fullOriginalText || rawTextOld || '',
                        modified: fullNewText || rawTextNew || '',
                        full: !!(fullOriginalText && fullNewText),
                        deletedLines: deletedLines || [],
                        addedLines: addedLines || [],
                        origToMod: origToMod || [],
                        modToOrig: modToOrig || []
                    });
                }
            };
            
            col3Title.onclick = openInWorkspace;
            state.currentOpenedDiff = { fullHtml: htmlContent, snippetHtml: snippetHtml, fileName: fileName };
            codeViewContainer.innerHTML = (state.isEyeMode && snippetHtml) ? snippetHtml : htmlContent;
            rolarParaDestaque();
            atualizarBotoesUndoRedo();
            
            if (!isHistOpen) {
                openInWorkspace();
            }
        });
        // Permite ao undo/redo "simular" o clique neste item da pilha, reutilizando
        // toda a lógica de abertura (destaque, cores, rolagem automática, botões).
        child._abrirDiff = () => header.click();
        child._data = {
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
        child.appendChild(header);
        return child;
    }
