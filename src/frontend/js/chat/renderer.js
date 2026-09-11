import {
    chatContainerLeft,
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
    slidingPanelContainer,
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
    col3Title,
    btnCloseCol3,
    btnCloseCol2,
    btnShowTools,
    btnShowThoughts,
    btnShowQuestion,
    btnWorkspace,
    btnEditor,
    terminalMode,
    btnCopyTools,
    btnUndo,
    btnRedo,
    lblUndoCount,
    lblRedoCount,
    btnEyeDiff,
    btnRestoreTask,
    btnSaveTask,
    btnDeleteTask,
    confirmDeletePopup,
    btnCancelDelete,
    btnConfirmDeleteYes,
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
    settingsModal,
    wsTopBar,
    chatMode,
    glossaryChip,
    btnInspect,
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
import { atualizarBotoesUndoRedo, atualizarIconeOlho, executarUndoRedo, normalizeFsPath, restaurarPastaSelecionada, rolarParaDestaque, selectFolder } from './files.js';
import { closeConfirmDeletePopup, closeRestoreConfirmPopup, moveColsToDock, openHistorySearchPanel, performDeleteSelectedTask, performSessionRestore, preloadSessionHistory, requestDeleteSelectedTask, requestRestoreTask, toggleSaveSelectedTask, toggleSessionHistory } from './history.js';
import { ativarInspect, atualizarHintInspect, avancarItemInspect, desativarInspect, executarItemInspect, renderizarInspect, selecionarItemInspect, suprimirTooltipNativo } from './inspect.js';
import { closeCol3, closeHistory, closeHistoryAndResetDock, closeLogDock, closePanelCol, isHistoryOpen, isLogDockOpen, openCol3Panel, openLogDockInWorkspace, toggleLogColumn } from './layout.js';
import { renderThoughts, renderTools, sendMessage, showQuestionPanel, sortToolArgsKeys, startSSE } from './messages.js';
import { aplicarEstadoReveal, aplicarEstadoToggleDeepseek, aplicarEstadoToggleGemini, aplicarEstadoToggleNav, aplicarEstadoToggleVertex, atualizarBotaoLimparVertex, closeSettingsModal, limparErroDeepseek, limparErroGemini, mostrarErroDeepseek, mostrarErroGemini, mostrarErroTavily, openSettingsModal, salvarConfiguracoes, validarChaveDeepseek, validarChaveStudio, validarChaveTavily } from './settings.js';
import { applyGlossaryChip, clearContextMemory, closeClearContextPopup, contextPopupVisivel, esconderChip, esconderIconTooltip, loadGlossary, mostrarIconTooltip, openClearContextPopup, posicionarContextUsageUI, posicionarIconTooltip, recolherContextPopup, renderCurrentSessionLogs, resizeChatInput, showAlert, showGlossaryChip, syncMenuIcons, syncWorkspaceTopBar, toggleWorkspaceView } from './ui.js';
import { copiarTexto } from './clipboard.js';

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
            toggleWorkspaceView();
        });
    }
    if (btnEditor) {
        btnEditor.addEventListener('click', () => {
            const wsOpen = terminalMode && !terminalMode.classList.contains('hidden');
            const view = (window.WorkspaceView && typeof window.WorkspaceView.getView === 'function')
                ? window.WorkspaceView.getView()
                : 'chat';
            if (view === 'editor') {
                if (window.WorkspaceView && typeof window.WorkspaceView.setView === 'function') {
                    window.WorkspaceView.setView('chat');
                }
                if (!wsOpen && window.WorkspaceView && typeof window.WorkspaceView.setActive === 'function') {
                    window.WorkspaceView.setActive(false);
                }
            } else {
                if (!isHistoryOpen()) {
                    moveColsToDock();
                    closePanelCol(panelCol2);
                    closeCol3();
                }
                openLogDockInWorkspace();
            }
        });
    }

 // { fullHtml, snippetHtml, fileName }
 // id da tarefa restaurada (epoch ms) p/ riscar cards posteriores
   // epoch ms do momento da restauração (p/ não riscar tarefas criadas depois)

    if (btnShowThoughts) {
        btnShowThoughts.addEventListener("click", (e) => {
            e.stopPropagation();
            if (state.isShowingThoughts) {
                closeCol3(); // Se já está aberto, fecha tudo
            } else {
                state.isShowingThoughts = true;
                state.isShowingTools = false;
                state.isShowingQuestions = false;
                openCol3Panel();
                btnShowThoughts.classList.remove("text-[var(--text-mutado)]");
                btnShowThoughts.classList.add("text-[var(--oliva)]");
                if (btnShowTools) {
                    btnShowTools.classList.remove("text-[var(--oliva)]");
                    btnShowTools.classList.add("text-[var(--text-mutado)]");
                }
                if (btnShowQuestion) {
                    btnShowQuestion.classList.remove("text-[var(--oliva)]");
                    btnShowQuestion.classList.add("text-[var(--text-mutado)]");
                }
                if (btnCopyTools) btnCopyTools.classList.remove("hidden");
                if (btnUndo) btnUndo.classList.add("hidden");
                if (btnRedo) btnRedo.classList.add("hidden");
                if (lblUndoCount) lblUndoCount.classList.add("hidden");
                if (lblRedoCount) lblRedoCount.classList.add("hidden");
                atualizarBotoesUndoRedo();
                col3Title.textContent = "Raciocínio do Coder";
                col3Title.onclick = null;
                col3Title.ondblclick = null;
                col3Title.title = "";
                col3Title.classList.remove("cursor-pointer", "hover:underline", "text-[var(--oliva)]");
                col3Title.classList.add("text-[var(--text)]");
                renderThoughts();
            }
        });
    }

    if (btnShowQuestion) {
        btnShowQuestion.addEventListener("click", (e) => {
            e.stopPropagation();
            if (state.isShowingQuestions) {
                closeCol3();
            } else {
                const group = window.currentActiveLogGroup || {};
                showQuestionPanel(group);
                btnShowQuestion.classList.remove("text-[var(--text-mutado)]");
                btnShowQuestion.classList.add("text-[var(--oliva)]");
            }
        });
    }

    // Exibe o painel da pergunta do usuário (agora o comportamento padrão ao
    // selecionar uma rodada, substituindo o antigo estado vazio "Codigo").
    if (btnShowTools) {
        btnShowTools.addEventListener('click', (e) => {
            e.stopPropagation();
            if (state.isShowingTools) {
                closeCol3(); // Se já está aberto, fecha tudo
            } else {
                state.isShowingTools = true;
                state.isShowingThoughts = false;
                state.isShowingQuestions = false;
                openCol3Panel();
                btnShowTools.classList.remove('text-[var(--text-mutado)]');
                btnShowTools.classList.add('text-[var(--oliva)]');
                if (btnShowThoughts) {
                    btnShowThoughts.classList.remove('text-[var(--oliva)]');
                    btnShowThoughts.classList.add('text-[var(--text-mutado)]');
                }
                if (btnShowQuestion) {
                    btnShowQuestion.classList.remove('text-[var(--oliva)]');
                    btnShowQuestion.classList.add('text-[var(--text-mutado)]');
                }
                if (btnCopyTools) btnCopyTools.classList.remove('hidden');
                if (btnUndo) btnUndo.classList.add('hidden');
                if (btnRedo) btnRedo.classList.add('hidden');
                if (lblUndoCount) lblUndoCount.classList.add('hidden');
                if (lblRedoCount) lblRedoCount.classList.add('hidden');
                atualizarBotoesUndoRedo();
                col3Title.textContent = 'Ferramentas Usadas';
                col3Title.onclick = null;
                col3Title.ondblclick = null;
                col3Title.title = "";
                col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[var(--oliva)]');
                col3Title.classList.add('text-[var(--text)]');
                renderTools();
            }
        });
    }

    if (btnEyeDiff) {
        btnEyeDiff.addEventListener('click', (e) => {
            e.stopPropagation();
            state.isEyeMode = !state.isEyeMode;
            atualizarIconeOlho();
            if (state.currentOpenedDiff && !state.isShowingTools && !state.isShowingThoughts && !state.isShowingQuestions) {
                codeViewContainer.innerHTML = (state.isEyeMode && state.currentOpenedDiff.snippetHtml)
                    ? state.currentOpenedDiff.snippetHtml
                    : state.currentOpenedDiff.fullHtml;
                rolarParaDestaque();
            }
            if (isHistoryOpen() && window.WorkspaceView && typeof window.WorkspaceView.setFocusMode === 'function') {
                window.WorkspaceView.setFocusMode(state.isEyeMode);
            }
        });
    }

    // NOVA LÓGICA DE CÓPIA DAS FERRAMENTAS
    if (btnCopyTools) {
        // Salva o ícone padrão uma única vez, blindando contra cliques duplos
        const originalToolsIcon = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>`;
        btnCopyTools.addEventListener('click', (e) => {
            e.stopPropagation();
            let clipboardText = '';
            if (state.isShowingQuestions) {
                // MODO PERGUNTA: copia o texto puro da pergunta feita ao usuário.
                // Se a resposta final da IA estiver expandida, copia pergunta + resposta.
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
                // MODO PENSAMENTOS (MEMÓRIAS): copia o texto puro
                if (state.currentViewingThoughts && state.currentViewingThoughts.length > 0) {
                    state.currentViewingThoughts.forEach((t, i) => {
                        // Remove tags HTML para texto limpo
                        let plainText = t.replace(/<[^>]*>/g, '');
                        // Decodifica entidades HTML comuns
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
                // MODO FERRAMENTAS: comportamento original
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
            btnCopyTools.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-[var(--oliva)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
            // Restaura usando a variável fixa
            setTimeout(() => { btnCopyTools.innerHTML = originalToolsIcon; }, 2000);
        });
    }

    // ============================================================
    // DESFAZER / REFAZER (UNDO / REDO)
    // ============================================================


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

    // Store session logs data
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

    btnCancelDelete.addEventListener('click', (e) => {
        e.stopPropagation();
        closeConfirmDeletePopup();
    });

    btnConfirmDeleteYes.addEventListener('click', async (e) => {
        e.stopPropagation();
        closeConfirmDeletePopup();
        await performDeleteSelectedTask();
    });

    btnDeleteTask.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!state.currentSelectedHistoryGroup) {
            showAlert('Selecione uma tarefa no histórico para excluir.');
            return;
        }
        requestDeleteSelectedTask(state.currentSelectedHistoryGroup);
    });

    btnRestoreTask.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!state.currentSelectedHistoryGroup) {
            showAlert('Selecione uma tarefa no histórico para restaurar.');
            return;
        }
        requestRestoreTask(state.currentSelectedHistoryGroup);
    });

    btnSaveTask.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!state.currentSelectedHistoryGroup) {
            showAlert('Selecione uma tarefa no histórico para salvar.');
            return;
        }
        toggleSaveSelectedTask(state.currentSelectedHistoryGroup);
    });

    // Evita que cliques no overlay de confirmação fechem o painel lateral por baixo.
    confirmDeletePopup.addEventListener('click', (e) => e.stopPropagation());

    // --- Restauração de sessão (Fase 1) ---
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

    // Fecha o dock de logs/histórico automaticamente ao clicar fora deles.
    document.addEventListener('click', (e) => {
        // Usa composedPath() (snapshot do caminho no momento do dispatch) para a
        // checagem continuar correta mesmo quando um handler anterior desconecta o
        // alvo do clique (ex: btnSend troca o innerHTML e desacopla o <svg> clicado).
        const path = (typeof e.composedPath === 'function') ? e.composedPath() : [];
        const hit = (el) => !!el && path.includes(el);
        const clickedOnModal = hit(confirmDeletePopup) || hit(restoreConfirmPopup) ||
                               hit(confirmClearContextPopup) || hit(alertPopup) || hit(settingsModal);
        if (clickedOnModal) return;
        const sidebar = document.querySelector('.w-14.shrink-0');
        const insideWorkspace = hit(editorView) || hit(wsTopBar);
        const insideChat = hit(chatMode);
        const insideTerminal = hit(terminalMode);
        const clickedSidebar = hit(sidebar);
        if (isLogDockOpen()) {
            if (!insideWorkspace && !insideChat && !insideTerminal && !clickedSidebar && !hit(slidingPanelContainer) && !hit(panelCol3) && !hit(btnOpenLog) && !hit(btnSessionHistory)) {
                closeLogDock();
                syncMenuIcons();
                syncWorkspaceTopBar();
            }
        }
        if (isHistoryOpen()) {
            if (!clickedSidebar && !hit(slidingPanelContainer) && !hit(panelCol3) && !hit(btnSessionHistory) && !hit(btnOpenLog)) {
                closeHistoryAndResetDock();
            }
        }
    });

    if(btnCloseCol3) btnCloseCol3.addEventListener('click', () => {
        closeCol3();
    });

    if(btnCloseCol2) btnCloseCol2.addEventListener('click', () => {
        closePanelCol(panelCol2);
        closeCol3();
    });

    if (btnDockLogSession) btnDockLogSession.addEventListener('click', () => toggleLogColumn(panelLogSession));
    if (btnDockFiles) btnDockFiles.addEventListener('click', () => toggleLogColumn(panelCol2));
    if (btnDockCode) btnDockCode.addEventListener('click', () => toggleLogColumn(panelCol3));

    // Auto-resize textarea
    inputText.addEventListener('input', resizeChatInput);

    inputText.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    btnSend.addEventListener('click', sendMessage);
    // === Glossario: termo leigo -> identificador de codigo (autocomplete + inspecao) ===
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

    // Balão do contexto: hover mostra a versão enxuta; clique fixa/expande o popup detalhado.
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

    // Explicações do popup de contexto: clique no "i" expande o texto abaixo da barra.
    setupInfoToggles('.context-popup-info', '.context-popup-info-text');

    // Explicações do modal de configurações (chaves de API): clique no "i" expande o tutorial.
    setupInfoToggles('.settings-info', '.settings-info-text');

    // Tooltip customizado (substitui o title nativo dos ícones pelo balão padronizado)

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
    if (btnInspect) btnInspect.addEventListener('click', ativarInspect);

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
        if (btnInspect && (e.target === btnInspect || btnInspect.contains(e.target))) {
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
                atualizarHintInspect('Clique em um item para copiar/abrir · Esc: sair');
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
            openHistorySearchPanel();
        });
    }

    // Pré-carrega a lista do histórico em segundo plano (sem tocar na UI),
    // para que a aba abra instantaneamente, sem o placeholder "Carregando histórico...".
    if ('requestIdleCallback' in window) {
        requestIdleCallback(() => preloadSessionHistory(), { timeout: 4000 });
    } else {
        setTimeout(preloadSessionHistory, 1500);
    }

    // Iniciar SSE para pegar status inicial
    startSSE();

    // Atualiza os cards de arquivo (log da sessao/historico) quando o usuario
    // renomeia, exclui ou restaura um ficheiro pelo doc (workspace).

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