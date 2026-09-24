import { vistaDe } from './colunas.js';
import { renderGitPanel, sincronizarBotaoEnvio, podeRestaurar, restaurarTarefa } from './git_panel.js';
import {
    chatContainerLeft,
    chatContainerRight,
    inputFooter,
    inputFooterInner,
    inputText,
    btnSend,
    btnPlus,
    plusMenu,
    btnOpenLog,
    btnModeSelect,
    modeSubmenu,
    btnAiSelect,
    aiSubmenu,
    panelLogSession,
    btnCloseLogSession,
    btnDockLogSession,
    btnDockFiles,
    btnDockCode,
    btnSessionHistory,
    btnHistorySearch,
    panelCol2,
    panelCol3,
    codeViewContainer,
    btnCloseCol2,
    btnCloseCol2History,
    btnCloseCol3History,
    btnShowTools,
    btnShowThoughts,
    btnShowQuestion,
    btnShowToolsHistory,
    btnShowThoughtsHistory,
    btnShowQuestionHistory,
    btnShowGit,
    btnShowGitHistory,
    btnGitEnviarHistory,
    btnWorkspace,
    btnEditor,
    terminalMode,
    btnCopyTools,
    btnCopyToolsHistory,
    btnUndo,
    btnRedo,
    lblUndoCount,
    lblRedoCount,
    btnEyeDiff,
    restoreConfirmPopup,
    btnCancelRestore,
    btnConfirmRestoreYes,
    answerEl,
    contextUsage,
    contextUsageLabel,
    contextUsagePopup,
    btnClearContext,
    confirmClearContextPopup,
    btnCancelClearContext,
    btnConfirmClearContext,
    alertPopup,
    alertPopupContent,
    btnCloseAlert,
    editorView,
    wrap,
    settingsModal,
    chatMode,
    glossaryChip,
    btnProjectInfo,
    btnProjectNotes,
    btnNotesAdd,
    btnNotesWand,
    btnCloseProjectInfo,
    inspectTooltip,
    btnSelectFolder,
    btnSettings,
    inputVertexKey,
    vertexJsonInput,
    inputDeepseekKey,
    inputGeminiKey,
    inputTavilyKey,
    btnDeepseekToggle,
    btnGeminiToggle,
    btnSwitchModel,
    btnNavToggle,
    btnRevealKeys,
    btnVertexClear
} from './dom.js';
import { state } from './state.js';
import { svgDoPonto, svgDoAviao } from './icones.js';
import { atualizarBotoesUndoRedo, atualizarIconeOlho, executarUndoRedo, marcarLinhasAlteradas, normalizeFsPath, restaurarPastaSelecionada, rolarParaDestaque, selectFolder } from './files.js';
import { preloadSessionHistory, toggleSessionHistory } from './historico/painel.js';
import { toggleHistorySearchInline } from './historico/busca.js';
import { registrarRepinturaCol3 } from './historico/acoes.js';
import { registrarRestauroDaTarefa, registrarSincronizacaoDoEnvio } from './historico/cards.js';
import { closeRestoreConfirmPopup, performSessionRestore } from './historico/restauro.js';
import { atualizarHintInspect, avancarItemInspect, desativarInspect, esconderInspectTooltip, executarItemInspect, ligarInspectAoMenu, renderizarInspect, selecionarItemInspect, suprimirTooltipNativo } from './inspect.js';
import { closeCol3, closeHistory, closeHistoryPanel, closeLogDock, closePanelCol, isHistoryOpen, isLogDockOpen, openLogDock, openLogDockInWorkspace, syncCopyButtons, syncDocTopBar, toggleLogColumn } from './layout.js';
import { renderThoughts, renderTools, sendMessage, showQuestionPanel, sortToolArgsKeys, startSSE } from './messages.js';
import { aplicarEstadoReveal, aplicarEstadoToggleDeepseek, aplicarEstadoToggleGemini, aplicarEstadoToggleNav, aplicarEstadoToggleVertex, atualizarBotaoLimparVertex, closeSettingsModal, limparErroDeepseek, limparErroGemini, mostrarErroDeepseek, mostrarErroGemini, mostrarErroTavily, openSettingsModal, salvarConfiguracoes, validarChaveDeepseek, validarChaveStudio, validarChaveTavily } from './settings.js';
import { applyGlossaryChip, clearContextMemory, closeClearContextPopup, contextPopupVisivel, esconderChip, esconderIconTooltip, loadGlossary, mostrarIconTooltip, openClearContextPopup, posicionarContextUsageUI, posicionarIconTooltip, recolherContextPopup, renderCurrentSessionLogs, resizeChatInput, showAlert, showGlossaryChip, syncMenuIcons, syncWorkspaceTopBar, toggleWorkspaceView } from './ui.js';
import { copiarTexto } from './clipboard.js';
import { abrirProjetoInfo, fecharProjetoInfo, projetoInfoAberto } from './projeto.js';
import { alternarCamadaNotas, criarNota, traduzirNota } from './projeto_notas.js';
import './menu_conversa.js';
import './busca_chat.js';

    chatContainerLeft.addEventListener('scroll', () => {
        const currentScrollTop = chatContainerLeft.scrollTop;
        const isScrolledUp = chatContainerLeft.scrollHeight - currentScrollTop - chatContainerLeft.clientHeight > 50;
        if (currentScrollTop > state.lastScrollTop || !isScrolledUp) {
            inputFooter.style.opacity = '1';
            inputFooterInner.style.pointerEvents = 'auto';
        } else {
            inputFooter.style.opacity = '0';
            inputFooterInner.style.pointerEvents = 'none';
        }
        state.lastScrollTop = currentScrollTop;
    });
    
    const modeOptions = document.querySelectorAll('.mode-option');
    const aiOptions = document.querySelectorAll('.ai-option');

    if (btnPlus && plusMenu) {
        btnPlus.addEventListener('click', (e) => {
            e.stopPropagation();
            plusMenu.classList.toggle('menu-open');
            if (plusMenu.classList.contains('menu-open')) {
                if (modeSubmenu) modeSubmenu.classList.remove('menu-open');
                if (aiSubmenu) aiSubmenu.classList.remove('menu-open');
                if (glossaryChip) glossaryChip.classList.remove('balao-visible');
                if (contextUsageLabel) contextUsageLabel.classList.remove('balao-visible');
            }
        });

        document.addEventListener('click', (e) => {
            if (!plusMenu.contains(e.target) && !btnPlus.contains(e.target)) {
                plusMenu.classList.remove('menu-open');
                if (modeSubmenu) modeSubmenu.classList.remove('menu-open');
                if (aiSubmenu) aiSubmenu.classList.remove('menu-open');
            }
        });
    }
    if (btnModeSelect && modeSubmenu) {
        btnModeSelect.addEventListener('click', (e) => {
            e.stopPropagation();
            modeSubmenu.classList.toggle('menu-open');
            if (aiSubmenu) aiSubmenu.classList.remove('menu-open');
        });

        modeOptions.forEach(opt => {
            if (opt.dataset.mode === state.currentMode) {
                opt.classList.add('text-[var(--oliva)]');
            }
        });

        modeOptions.forEach(option => {
            option.addEventListener('click', (e) => {
                state.currentMode = e.target.dataset.mode;
                modeSubmenu.classList.remove('menu-open');
                plusMenu.classList.remove('menu-open');
                const modeName = e.target.textContent;
                btnModeSelect.title = `Modo de Operação: ${modeName}`;
                modeOptions.forEach(opt => opt.classList.remove('text-[var(--oliva)]'));
                e.target.classList.add('text-[var(--oliva)]');
            });
        });
    }
    if (btnAiSelect && aiSubmenu) {
        btnAiSelect.addEventListener('click', (e) => {
            e.stopPropagation();
            aiSubmenu.classList.toggle('menu-open');
            if (modeSubmenu) modeSubmenu.classList.remove('menu-open');
        });

        aiOptions.forEach(opt => {
            if (opt.dataset.model === state.selectedModel) {
                opt.classList.add('text-[var(--oliva)]');
                btnAiSelect.title = `Seleção da IA: ${opt.textContent}`;
            }
        });

        aiOptions.forEach(option => {
            option.addEventListener('click', (e) => {
                state.selectedModel = e.target.dataset.model;
                try { localStorage.setItem('axio-selected-model', state.selectedModel); } catch (err) {}
                aiSubmenu.classList.remove('menu-open');
                plusMenu.classList.remove('menu-open');
                const modelName = e.target.textContent;
                btnAiSelect.title = `Seleção da IA: ${modelName}`;
                aiOptions.forEach(opt => opt.classList.remove('text-[var(--oliva)]'));
                e.target.classList.add('text-[var(--oliva)]');
            });
        });
    }
    if (btnWorkspace) {
        btnWorkspace.addEventListener('click', () => {

            const vaiAbrirTerminal = terminalMode && terminalMode.classList.contains('hidden');
            if (vaiAbrirTerminal) recolherPaineisLaterais();
            toggleWorkspaceView();
        });
    }
    if (btnEditor) {
        btnEditor.addEventListener('click', () => {
            const wsOpen = terminalMode && !terminalMode.classList.contains('hidden');
            const ponte = window.WorkspaceView;
            const view = (ponte && typeof ponte.getView === 'function') ? ponte.getView() : 'chat';
            if (view === 'chat') {
                closePanelCol(panelCol2);
                closeCol3();
                openLogDock();
                if (ponte && typeof ponte.abrirDoc === 'function') ponte.abrirDoc();
            } else {
                if (ponte && typeof ponte.alternarDoc === 'function') ponte.alternarDoc();
                if (!wsOpen && ponte && typeof ponte.setActive === 'function') ponte.setActive(false);
            }
        });
    }

    function pintarBotoesCol3(botoes, ativo, vista) {
        Object.keys(botoes).forEach(tipo => {
            const b = botoes[tipo];
            if (!b) return;
            b.classList.toggle('text-[var(--oliva)]', tipo === ativo);
            b.classList.toggle('text-[var(--text-mutado)]', tipo !== ativo);
        });
        syncCopyButtons(vista, ativo);
    }
    function alternarPainelCol3(tipo, vista, botoes) {
        if (!vista) return;
        const ativo = tipo === 'thoughts' ? state.isShowingThoughts
            : tipo === 'question' ? state.isShowingQuestions
            : tipo === 'git' ? state.isShowingGit
            : state.isShowingTools;
        if (ativo && vista.col3Aberta()) {
            state.isShowingThoughts = false;
            state.isShowingQuestions = false;
            state.isShowingTools = false;
            state.isShowingGit = false;
            vista.fecharCol3();
            pintarBotoesCol3(botoes, null, vista);
            return;
        }
        vista.abrirCol3();
        state.isShowingThoughts = tipo === 'thoughts';
        state.isShowingQuestions = tipo === 'question';
        state.isShowingTools = tipo === 'tools';
        state.isShowingGit = tipo === 'git';
        syncDocTopBar();
        if (tipo === 'question') {
            showQuestionPanel(window.currentActiveLogGroup || {}, vista);
            pintarBotoesCol3(botoes, tipo, vista);
            return;
        }

        if (vista.id === 'dock') {
            if (btnUndo) btnUndo.classList.add('hidden');
            if (btnRedo) btnRedo.classList.add('hidden');
            if (lblUndoCount) lblUndoCount.classList.add('hidden');
            if (lblRedoCount) lblRedoCount.classList.add('hidden');
            atualizarBotoesUndoRedo();
        }
        const titulo = vista.titulo;
        if (titulo) {
            titulo.textContent = tipo === 'thoughts' ? 'Raciocínio do Coder' : tipo === 'git' ? 'Git' : 'Ferramentas Usadas';
            titulo.onclick = null;
            titulo.ondblclick = null;
            titulo.title = '';
            titulo.classList.remove('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
            titulo.classList.add('text-[var(--text)]');
        }
        pintarBotoesCol3(botoes, tipo, vista);
        if (tipo === 'thoughts') renderThoughts(vista);
        else if (tipo === 'git') renderGitPanel(vista);
        else renderTools(vista);
    }

    function ligarBotoesCol3(botoes, idVista) {
        Object.keys(botoes).forEach(tipo => {
            const b = botoes[tipo];
            if (!b) return;
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                const vista = vistaDe(idVista);

                if (vista) vista.aoFecharCol3 = () => pintarBotoesCol3(botoes, null, vista);
                alternarPainelCol3(tipo, vista, botoes);
            });
        });
    }
    btnShowGitHistory.innerHTML = svgDoPonto('h-5 w-5 icon-header-action');
    btnGitEnviarHistory.innerHTML = svgDoAviao('h-5 w-5 icon-header-action');
    ligarBotoesCol3({ question: btnShowQuestion, thoughts: btnShowThoughts, tools: btnShowTools, git: btnShowGit }, 'dock');

    ligarBotoesCol3({ question: btnShowQuestionHistory, thoughts: btnShowThoughtsHistory, tools: btnShowToolsHistory, git: btnShowGitHistory }, 'historico');

    function repintarPainelCol3(vista, grupo) {
        if (state.isShowingGit) return renderGitPanel(vista);
        if (state.isShowingThoughts) return renderThoughts(vista);
        if (state.isShowingQuestions) return showQuestionPanel(grupo || {}, vista);
        if (state.isShowingTools) return renderTools(vista);
    }
    registrarRepinturaCol3(repintarPainelCol3);
    registrarRestauroDaTarefa({ pode: podeRestaurar, restaurar: restaurarTarefa });
    registrarSincronizacaoDoEnvio(sincronizarBotaoEnvio);

    if (btnEyeDiff) {
        btnEyeDiff.addEventListener('click', (e) => {
            e.stopPropagation();
            state.isEyeMode = !state.isEyeMode;
            atualizarIconeOlho();
            if (state.currentOpenedDiff && !state.isShowingTools && !state.isShowingThoughts && !state.isShowingQuestions) {
                codeViewContainer.innerHTML = (state.isEyeMode && state.currentOpenedDiff.snippetHtml)
                    ? state.currentOpenedDiff.snippetHtml
                    : state.currentOpenedDiff.fullHtml;

                marcarLinhasAlteradas(codeViewContainer, state.currentOpenedDiff);
                rolarParaDestaque();
                if (window.WorkspaceView && typeof window.WorkspaceView.setFocusMode === 'function') {
                    window.WorkspaceView.setFocusMode(state.isEyeMode);
                }
            }
        });
    }

    function _copiarPainelAtivo(botao) {
        if (!botao) return;
        const originalToolsIcon = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>`;
        botao.addEventListener('click', (e) => {
            e.stopPropagation();
            let clipboardText = '';
            if (state.isShowingQuestions) {

                if (state.currentViewingQuestions && state.currentViewingQuestions.length > 0) {
                    state.currentViewingQuestions.forEach((q, i) => {
                        let plainText = q.replace(/<[^>]*>/g, '');
                        plainText = plainText.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
                        clipboardText += plainText;
                        if (i < state.currentViewingQuestions.length - 1) {
                            clipboardText += '\n\n---\n\n';
                        }
                    });
                    const expanded = answerEl && !answerEl.classList.contains('hidden');
                    if (expanded && state.currentViewingAiResponse) {
                        let answerText = state.currentViewingAiResponse.replace(/<[^>]*>/g, '');
                        answerText = answerText.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
                        clipboardText += '\n\n---\n\n' + answerText;
                    }
                } else {
                    clipboardText = 'Nenhuma pergunta registrada neste turno.';
                }
            } else if (state.isShowingThoughts) {
                if (state.currentViewingThoughts && state.currentViewingThoughts.length > 0) {
                    state.currentViewingThoughts.forEach((t, i) => {
                        let plainText = t.replace(/<[^>]*>/g, '');
                        plainText = plainText.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
                        clipboardText += plainText;
                        if (i < state.currentViewingThoughts.length - 1) {
                            clipboardText += '\n\n---\n\n';
                        }
                    });
                } else {
                    clipboardText = 'Nenhum raciocínio registrado neste turno.';
                }
            } else {
                if (state.currentViewingTools && state.currentViewingTools.length > 0) {
                    state.currentViewingTools.forEach(t => {
                        clipboardText += `FERRAMENTA: ${t.name}\n`;
                        if (t.args && Object.keys(t.args).length > 0) {
                            const chavesOrdenadas = sortToolArgsKeys(Object.keys(t.args));
                            chavesOrdenadas.forEach(key => {
                                let val = t.args[key];
                                let displayVal = typeof val === 'string' ? val : JSON.stringify(val);
                                if (displayVal.includes('\n')) {
                                    clipboardText += `-> ${key}:\n${displayVal}\n`;
                                } else {
                                    clipboardText += `-> ${key}: ${displayVal}\n`;
                                }
                            });
                        } else {
                            clipboardText += `-> Sem argumentos (Chamada simples)\n`;
                        }
                        if (t.urls && t.urls.length > 0) {
                            t.urls.forEach(url => {
                                clipboardText += `-> ${url}\n`;
                            });
                        }
                        clipboardText += `------------------------------------------------------------\n\n`;
                    });
                } else {
                    clipboardText = 'Nenhuma ferramenta associada a este turno.';
                }
            }
            copiarTexto(clipboardText.trim());
            botao.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-[var(--oliva)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
            setTimeout(() => { botao.innerHTML = originalToolsIcon; }, 2000);
        });
    }
    _copiarPainelAtivo(btnCopyTools);
    _copiarPainelAtivo(btnCopyToolsHistory);



    if (btnUndo) {
        btnUndo.addEventListener('click', (e) => {
            e.stopPropagation();
            executarUndoRedo('undo');
        });
    }

    if (btnRedo) {
        btnRedo.addEventListener('click', (e) => {
            e.stopPropagation();
            executarUndoRedo('redo');
        });
    }

    window.sessionLogsData = [];
    btnCloseAlert.addEventListener('click', () => {
        alertPopup.classList.remove('opacity-100', 'pointer-events-auto');
        alertPopup.classList.add('opacity-0', 'pointer-events-none');
        alertPopupContent.classList.remove('scale-100');
        alertPopupContent.classList.add('scale-95');
    });

    if (btnClearContext) {
        btnClearContext.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            if (state.isGenerating) {
                showAlert('Aguarde a conclusão da resposta atual antes de limpar o contexto.');
                return;
            }
            if (contextUsageLabel) contextUsageLabel.classList.remove('balao-visible');
            if (contextUsagePopup) contextUsagePopup.classList.remove('balao-visible');
            state.contextPopupExpanded = false;
            openClearContextPopup();
        });
    }
    if (btnCancelClearContext) btnCancelClearContext.addEventListener('click', closeClearContextPopup);
    if (btnConfirmClearContext) btnConfirmClearContext.addEventListener('click', clearContextMemory);

    btnCancelRestore.addEventListener('click', (e) => {
        e.stopPropagation();
        closeRestoreConfirmPopup();
    });

    btnConfirmRestoreYes.addEventListener('click', async (e) => {
        e.stopPropagation();
        await performSessionRestore();
    });

    restoreConfirmPopup.addEventListener('click', (e) => e.stopPropagation());
    
    btnOpenLog.addEventListener('click', (e) => {
        e.stopPropagation();
        const editorVisible = editorView && !editorView.classList.contains('hidden');
        const isOpen = isLogDockOpen() && editorVisible;
        if (!isOpen) {
            closeHistory();
            openLogDockInWorkspace();
            renderCurrentSessionLogs();
        } else {
            closeLogDock();
            syncMenuIcons();
        }
        syncWorkspaceTopBar();
    });
    
    if (btnCloseLogSession) {
        btnCloseLogSession.addEventListener('click', () => {
            closePanelCol(panelLogSession);
            closePanelCol(panelCol2);
            closeCol3();
            closeLogDock();
            syncMenuIcons();
            syncWorkspaceTopBar();
        });
    }

    function recolherPaineisLaterais() {
        if (isHistoryOpen()) {
            closeHistoryPanel();
        }
        if (projetoInfoAberto()) {
            fecharProjetoInfo();
        }
    }

    document.addEventListener('click', (e) => {

        const path = (typeof e.composedPath === 'function') ? e.composedPath() : [];
        const hit = (el) => !!el && path.includes(el);
        const clickedOnModal = hit(restoreConfirmPopup) || hit(confirmClearContextPopup) ||
                               hit(alertPopup) || hit(settingsModal);
        if (clickedOnModal) return;
        const clickedLeftColumn = hit(chatMode) || hit(terminalMode);
        const clickedDocContent = hit(wrap) || hit(chatContainerRight);
        if (!clickedLeftColumn && !clickedDocContent) return;

        const col3Hist = vistaDe('historico');
        const col3HistAberta = !!col3Hist && col3Hist.col3Aberta();
        const clicouNaCamadaHistorico = path.some(el => el && el.id === 'panel-col-3-history');
        const clicouNaCamadaNotas = path.some(el => el && el.id === 'panel-col-3-notes');
        if (clicouNaCamadaNotas) return;
        if (hit(wrap) && !hit(chatContainerRight) && (clicouNaCamadaHistorico || col3HistAberta || state.codigoDoHistoricoNoEditor)) return;
        recolherPaineisLaterais();
    });

    if(btnCloseCol2) btnCloseCol2.addEventListener('click', () => {
        closePanelCol(panelCol2);
        closeCol3();
    });

    if(btnCloseCol2History) btnCloseCol2History.addEventListener('click', () => {
        const vista = vistaDe('historico');
        if (vista) vista.fecharCol2();
    });

    if(btnCloseCol3History) btnCloseCol3History.addEventListener('click', () => {
        const vista = vistaDe('historico');
        if (vista) vista.fecharCol3();
    });

    if (btnDockLogSession) btnDockLogSession.addEventListener('click', () => toggleLogColumn(panelLogSession));
    if (btnDockFiles) btnDockFiles.addEventListener('click', () => toggleLogColumn(panelCol2));
    if (btnDockCode) btnDockCode.addEventListener('click', () => toggleLogColumn(panelCol3));

    inputText.addEventListener('input', resizeChatInput);

    inputText.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    btnSend.addEventListener('click', sendMessage);
    window.glossary = [];


    inputText.addEventListener('input', showGlossaryChip);
    inputText.addEventListener('keydown', function(e) {
        if (e.key === 'Tab' && state.glossaryMatchCurrent && !state.inspectAtivo) {
            e.preventDefault();
            applyGlossaryChip();
        } else if (e.key === 'Escape') {
            esconderChip();
        }
    });

    if (glossaryChip) glossaryChip.addEventListener('click', applyGlossaryChip);

    if (contextUsage && contextUsageLabel && contextUsagePopup) {
        document.body.appendChild(contextUsageLabel);
        document.body.appendChild(contextUsagePopup);

        window.addEventListener('resize', () => {
            if (contextPopupVisivel()) posicionarContextUsageUI();
        });

        contextUsage.addEventListener('mouseenter', () => {
            if (state.contextPopupExpanded) return;
            if (glossaryChip) glossaryChip.classList.remove('balao-visible');
            posicionarContextUsageUI();
            contextUsageLabel.classList.add('balao-visible');
        });
        contextUsage.addEventListener('mouseleave', () => {
            if (state.contextPopupExpanded) return;
            contextUsageLabel.classList.remove('balao-visible');
        });
        contextUsage.addEventListener('click', () => {
            state.contextPopupExpanded = !state.contextPopupExpanded;
            contextUsageLabel.classList.remove('balao-visible');
            if (glossaryChip) glossaryChip.classList.remove('balao-visible');
            if (state.contextPopupExpanded) {
                posicionarContextUsageUI();
                contextUsagePopup.classList.add('balao-visible');
            } else {
                contextUsagePopup.classList.remove('balao-visible');
            }
        });

        document.addEventListener('click', (e) => {
            if (!state.contextPopupExpanded) return;
            if (contextUsage.contains(e.target) || contextUsagePopup.contains(e.target)) return;
            recolherContextPopup();
        });
    }

    function setupInfoToggles(infoSelector, textSelector) {
        document.querySelectorAll(infoSelector).forEach(info => {
            info.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetId = info.getAttribute('data-info-target');
                const target = targetId ? document.getElementById(targetId) : null;
                if (!target) return;
                const abrir = !target.classList.contains('open');
                document.querySelectorAll(textSelector).forEach(t => t.classList.remove('open'));
                document.querySelectorAll(infoSelector).forEach(i => i.classList.remove('active'));
                if (abrir) {
                    target.classList.add('open');
                    info.classList.add('active');
                }
            });
        });
    }

    setupInfoToggles('.context-popup-info', '.context-popup-info-text');

    setupInfoToggles('.settings-info', '.settings-info-text');


    document.addEventListener('mouseover', function(e) {
        if (state.inspectAtivo) return;
        const jaNoTooltip = e.target.closest && e.target.closest('[data-tt]');
        if (jaNoTooltip) {
            posicionarIconTooltip(jaNoTooltip);
            return;
        }
        const el = e.target.closest ? e.target.closest('[title]') : null;
        if (!el) return;
        if (el.id === 'context-usage') return;
        if (el.closest && el.closest('#inspect-tooltip')) return;
        const txt = el.getAttribute('title');
        if (!txt) return;
        el.setAttribute('data-tt', txt);
        el.removeAttribute('title');
        mostrarIconTooltip(el, txt);
    }, true);

    document.addEventListener('mouseout', function(e) {
        const el = e.target.closest ? e.target.closest('[data-tt]') : null;
        if (!el) return;
        const related = e.relatedTarget;
        if (related && el.contains(related)) return;
        el.setAttribute('title', el.getAttribute('data-tt'));
        el.removeAttribute('data-tt');
        esconderIconTooltip();
    }, true);

    document.addEventListener('mouseover', suprimirTooltipNativo, true);

    ligarInspectAoMenu();

    if (inspectTooltip) {
        inspectTooltip.addEventListener('mouseover', function(e) {
            const itemEl = e.target.closest ? e.target.closest('.inspect-item') : null;
            if (itemEl) {
                const idx = parseInt(itemEl.getAttribute('data-idx'), 10);
                if (!isNaN(idx)) selecionarItemInspect(idx);
            }
        });
    }

    document.addEventListener('mousemove', function(e) {
        if (!state.inspectAtivo || !inspectTooltip) return;
        if (e.shiftKey) {

            esconderInspectTooltip();
            return;
        }
        if (state.inspectLocked) return;
        if (inspectTooltip.contains(e.target)) return;
        const el = e.target;
        state.inspectLastX = e.clientX;
        state.inspectLastY = e.clientY;
        state.inspectCurrentEl = el;
        renderizarInspect(el, e.clientX, e.clientY);
    });

    document.addEventListener('click', function(e) {
        if (!state.inspectAtivo) return;
        if (e.shiftKey) {

            esconderInspectTooltip();
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        if (inspectTooltip && inspectTooltip.contains(e.target)) {
            const itemEl = e.target.closest ? e.target.closest('.inspect-item') : null;
            if (itemEl) {
                const idx = parseInt(itemEl.getAttribute('data-idx'), 10);
                if (!isNaN(idx)) executarItemInspect(idx);
            }
            return;
        }
        if (!state.inspectLocked) {
            state.inspectLocked = true;
            if (inspectTooltip) {
                inspectTooltip.classList.add('inspect-locked');
                atualizarHintInspect('Clique em um item para copiar/abrir · Shift+clique: interagir · Esc: sair');
            }
            return;
        }
        state.inspectLocked = false;
        if (inspectTooltip) inspectTooltip.classList.remove('inspect-locked');
        state.inspectLastX = e.clientX;
        state.inspectLastY = e.clientY;
        state.inspectCurrentEl = e.target;
        renderizarInspect(e.target, e.clientX, e.clientY);
    }, true);

    document.addEventListener('keydown', function(e) {
        if (!state.inspectAtivo) return;
        if (e.key === 'Tab') {
            e.preventDefault();
            avancarItemInspect();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            executarItemInspect(state.inspectItemIndex);
        } else if (e.key === 'Escape') {
            desativarInspect();
        }
    });

    loadGlossary();

    if (btnSelectFolder) {
        btnSelectFolder.addEventListener('click', selectFolder);
    }

    if (btnSettings) {
        btnSettings.addEventListener('click', (e) => {
            e.stopPropagation();
            openSettingsModal();
        });
    }

    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) {
                closeSettingsModal();
            }
        });
    }

    if (btnProjectInfo) {
        btnProjectInfo.addEventListener('click', (e) => {
            e.stopPropagation();
            if (projetoInfoAberto()) fecharProjetoInfo();
            else abrirProjetoInfo();
        });
    }

    if (btnSessionHistory) {
        btnSessionHistory.addEventListener('click', fecharProjetoInfo);
    }

    if (btnProjectNotes) btnProjectNotes.addEventListener('click', alternarCamadaNotas);
    if (btnNotesAdd) btnNotesAdd.addEventListener('click', criarNota);
    if (btnNotesWand) btnNotesWand.addEventListener('click', traduzirNota);

    if (btnCloseProjectInfo) btnCloseProjectInfo.addEventListener('click', fecharProjetoInfo);

    if (btnDeepseekToggle) btnDeepseekToggle.addEventListener('click', async () => {
        const ativar = !state.settingsDeepseekEnabled;
        if (ativar) {
            const chave = inputDeepseekKey ? inputDeepseekKey.value.trim() : '';
            if (!validarChaveDeepseek(chave)) {
                mostrarErroDeepseek();
                return;
            }
            limparErroDeepseek();
        }
        aplicarEstadoToggleDeepseek(ativar);
        await salvarConfiguracoes({ alertar: false });
    });
    if (btnGeminiToggle) btnGeminiToggle.addEventListener('click', async () => {
        const ativar = !state.settingsGeminiEnabled;
        if (ativar) {
            if (state.settingsVertexMode) {
                if (!state.settingsVertexJsonData) {
                    mostrarErroGemini();
                    return;
                }
            } else {
                const chave = inputGeminiKey ? inputGeminiKey.value.trim() : '';
                if (!validarChaveStudio(chave)) {
                    mostrarErroGemini();
                    return;
                }
            }
            limparErroGemini();
        }
        aplicarEstadoToggleGemini(ativar);
        await salvarConfiguracoes({ alertar: false });
    });
    if (btnNavToggle) btnNavToggle.addEventListener('click', async () => {
        const ativar = !state.settingsNavMode;
        if (ativar) {
            const chave = inputTavilyKey ? inputTavilyKey.value.trim() : '';
            if (!validarChaveTavily(chave)) {
                mostrarErroTavily();
                return;
            }
        }
        aplicarEstadoToggleNav(ativar);
        await salvarConfiguracoes({ alertar: false });
    });
    if (btnSwitchModel) btnSwitchModel.addEventListener('click', async () => {
        aplicarEstadoToggleVertex(!state.settingsVertexMode);
        await salvarConfiguracoes({ alertar: false });
    });
    if (btnRevealKeys) btnRevealKeys.addEventListener('click', () => aplicarEstadoReveal(!state.settingsRevealKeys));
    if (btnVertexClear) btnVertexClear.addEventListener('click', async () => {
        state.settingsVertexJsonName = '';
        state.settingsVertexJsonData = null;
        if (inputVertexKey) inputVertexKey.value = '';
        atualizarBotaoLimparVertex();
        await salvarConfiguracoes({ alertar: false });
    });
    if (inputVertexKey && vertexJsonInput) {
        inputVertexKey.addEventListener('click', () => {
            if (!state.settingsGeminiEnabled) vertexJsonInput.click();
        });
        vertexJsonInput.addEventListener('change', () => {
            const file = vertexJsonInput.files && vertexJsonInput.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const json = JSON.parse(reader.result);
                    state.settingsVertexJsonName = file.name;
                    state.settingsVertexJsonData = json;
                    inputVertexKey.value = file.name;
                    atualizarBotaoLimparVertex();
                    limparErroGemini();
                } catch (err) {
                    showAlert('Ficheiro JSON inválido. Selecione a conta de serviço do Vertex AI.');
                }
            };
            reader.readAsText(file);
        });
    }
    
    restaurarPastaSelecionada();

    if (btnSessionHistory) {
        btnSessionHistory.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSessionHistory();
        });
    }
    if (btnHistorySearch) {
        btnHistorySearch.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleHistorySearchInline();
        });
    }

    if ('requestIdleCallback' in window) {
        requestIdleCallback(() => preloadSessionHistory(), { timeout: 4000 });
    } else {
        setTimeout(preloadSessionHistory, 1500);
    }

    startSSE();


    function allSessionGroups() {
        const groups = [];
        if (window.currentGroupBalloon) groups.push(window.currentGroupBalloon);
        if (window.currentActiveLogGroup) groups.push(window.currentActiveLogGroup);
        (window.sessionLogsData || []).forEach(g => groups.push(g));
        return groups.filter((g, i, arr) => arr.indexOf(g) === i);
    }

    window.addEventListener('axio-fs-renamed', (e) => {
        const { oldPath, newPath } = e.detail || {};
        if (!oldPath || !newPath) return;
        const oldN = normalizeFsPath(oldPath);
        const newN = normalizeFsPath(newPath);
        allSessionGroups().forEach(g => {
            (g.files || []).forEach(fd => {
                const n = normalizeFsPath(fd.name);
                if (n === oldN || n.startsWith(oldN + '/')) {
                    fd.name = newN + n.slice(oldN.length);
                    if (fd._headerEl) {
                        const span = fd._headerEl.querySelector('span:first-child');
                        if (span) span.textContent = fd.name;
                    }
                }
            });
        });
    });

    function handleFsDeleteRestore(e, isDeleted) {
        const path = normalizeFsPath(e.detail && e.detail.path);
        if (!path) return;
        allSessionGroups().forEach(g => {
            (g.files || []).forEach(fd => {
                const n = normalizeFsPath(fd.name);
                if (n === path || n.startsWith(path + '/')) {
                    fd.deleted = isDeleted;
                    if (fd._headerEl) {
                        if (isDeleted) fd._headerEl.classList.add('file-deleted');
                        else fd._headerEl.classList.remove('file-deleted');
                    }
                }
            });
        });
    }

    window.addEventListener('axio-fs-deleted', (e) => handleFsDeleteRestore(e, true));
    window.addEventListener('axio-fs-restored', (e) => handleFsDeleteRestore(e, false));

    window.addEventListener('axio-editor-file-open', () => {
        state.codigoDoHistoricoNoEditor = false;
        ['dock', 'historico', 'notas'].forEach(id => {
            const vista = vistaDe(id);
            if (vista && vista.col3Aberta()) vista.fecharCol3();
        });
        syncDocTopBar();
    });

    window.addEventListener('axio-view-change', (e) => {
        state.vistaDocAtual = e.detail ? e.detail.view : null;
        syncDocTopBar();
    });