const { ipcRenderer } = require('electron');

document.addEventListener('DOMContentLoaded', () => {
    const chatContainerLeft = document.getElementById('chat-container-left');
    const chatContainerRight = document.getElementById('chat-container-right');
    const chatInnerLeft = document.getElementById('chat-inner-left');
    const chatInnerRight = document.getElementById('chat-inner-right');
    const inputFooter = document.getElementById('input-footer');
    const inputFooterInner = document.getElementById('input-footer-inner');
    const inputText = document.getElementById('input-text');

    let lastScrollTop = chatContainerLeft.scrollTop;
    const folderDisplay = document.getElementById('folder-display-container');

    chatContainerLeft.addEventListener('scroll', () => {
        const currentScrollTop = chatContainerLeft.scrollTop;
        const isScrolledUp = chatContainerLeft.scrollHeight - currentScrollTop - chatContainerLeft.clientHeight > 50;
        
        if (currentScrollTop > lastScrollTop || !isScrolledUp) {
            inputFooter.style.opacity = '1';
            inputFooterInner.style.pointerEvents = 'auto';
        } else {
            inputFooter.style.opacity = '0';
            inputFooterInner.style.pointerEvents = 'none';
        }
        lastScrollTop = currentScrollTop;
    });
    const btnSend = document.getElementById('btn-send');
    const btnSelectFolder = document.getElementById('btn-select-folder');
    const btnOpenLog = document.getElementById('btn-open-log');
    const btnModeSelect = document.getElementById('btn-mode-select');
    const btnCounselor = document.getElementById('btn-counselor');
    const modePopup = document.getElementById('mode-popup');
    const modeOptions = document.querySelectorAll('.mode-option');
    let currentMode = 'auto';
    let isCounselorMode = false;
    let isGenerating = false;

    if (btnCounselor) {
        btnCounselor.addEventListener('click', () => {
            if (isGenerating) return;
            isCounselorMode = !isCounselorMode;
            if (isCounselorMode) {
                btnCounselor.classList.remove('text-white');
                btnCounselor.classList.add('text-[#3b82f6]');
            } else {
                btnCounselor.classList.add('text-white');
                btnCounselor.classList.remove('text-[#3b82f6]');
            }
            chatContainerLeft.scrollTop = chatContainerLeft.scrollHeight;
            chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
        });
    }

    if (btnModeSelect && modePopup) {
        btnModeSelect.addEventListener('click', (e) => {
            e.stopPropagation();
            modePopup.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!modePopup.contains(e.target) && !btnModeSelect.contains(e.target)) {
                modePopup.classList.add('hidden');
            }
        });

        // Set initial active state
        modeOptions.forEach(opt => {
            if (opt.dataset.mode === currentMode) {
                opt.classList.add('text-[rgb(144,160,21)]');
            }
        });

        modeOptions.forEach(option => {
            option.addEventListener('click', (e) => {
                currentMode = e.target.dataset.mode;
                modePopup.classList.add('hidden');
                let modeName = e.target.textContent;
                btnModeSelect.title = `Modo de Operação: ${modeName}`;
                
                // Update colors
                modeOptions.forEach(opt => opt.classList.remove('text-[rgb(144,160,21)]'));
                e.target.classList.add('text-[rgb(144,160,21)]');
                
                // Change button icon color to indicate a mode is selected (if not auto)
                if (currentMode !== 'auto') {
                    btnModeSelect.classList.add('text-[#3b82f6]');
                    btnModeSelect.classList.remove('text-white');
                } else {
                    btnModeSelect.classList.remove('text-[#3b82f6]');
                    btnModeSelect.classList.add('text-white');
                }
            });
        });
    }

    const slidingPanelContainer = document.getElementById('sliding-panel-container');
    const btnClosePanel = document.getElementById('btn-close-panel');
    const logListContainer = document.getElementById('log-list-container');
    const currentLogsWrapper = document.getElementById('current-logs-wrapper');
    const historyLogsWrapper = document.getElementById('history-logs-wrapper');
    const btnSessionHistory = document.getElementById('btn-session-history');
    const panelTitle = document.getElementById('panel-title');
    const btnHistorySearch = document.getElementById('btn-history-search');
    
    const panelCol2 = document.getElementById('panel-col-2');
    const filesListContainer = document.getElementById('files-list-container');
    const btnCloseCol2 = document.getElementById('btn-close-col-2');
    
    const panelCol3 = document.getElementById('panel-col-3');
    const codeViewContainer = document.getElementById('code-view-container');
    const col3Title = document.getElementById('col-3-title');
    const btnCloseCol3 = document.getElementById('btn-close-col-3');
    const btnShowTools = document.getElementById("btn-show-tools");
    const btnShowThoughts = document.getElementById("btn-show-thoughts");
    const btnCopyTools = document.getElementById("btn-copy-tools");
    const btnUndo = document.getElementById("btn-undo");
    const btnRedo = document.getElementById("btn-redo");
    const lblUndoCount = document.getElementById("lbl-undo-count");
    const lblRedoCount = document.getElementById("lbl-redo-count");
    const btnEyeDiff = document.getElementById("btn-eye-diff");
    const logDeleteBar = document.getElementById("log-delete-bar");
    const btnConfirmDelete = document.getElementById("btn-confirm-delete");
    const lblDeleteCount = document.getElementById("lbl-delete-count");
    const confirmDeletePopup = document.getElementById("confirm-delete-popup");
    const confirmDeleteContent = document.getElementById("confirm-delete-content");
    const lblDeleteMessage = document.getElementById("lbl-delete-message");
    const btnCancelDelete = document.getElementById("btn-cancel-delete");
    const btnConfirmDeleteYes = document.getElementById("btn-confirm-delete-yes");

    let currentViewingTools = [];
    let currentViewingThoughts = [];
    let currentViewingQuestions = [];
    let isShowingTools = false;
    let isShowingThoughts = false;
    let isShowingQuestions = false;
    let currentActiveFileBalloonHtml = "";
    let undoRedoFiles = [];
    let currentUndoFile = null;
    let currentFileDataRef = null;
    let isEyeMode = false;
    let currentOpenedDiff = null; // { fullHtml, snippetHtml, fileName }
    let isShowingSessionHistory = false;
    let sessionHistoryList = [];
    let sessionDetailCache = {};
    let sessionHistoryLoaded = false;
    let currentTurnLogs = [];
    let currentTurnSummary = '';
    let selectedSessionFiles = new Set();
    let selectedTurnIds = new Set();

    function resetCol3State() {
        isShowingTools = false;
        isShowingThoughts = false;
        isShowingQuestions = false;
        currentActiveFileBalloonHtml = "";
        currentUndoFile = null;
        currentFileDataRef = null;

        // Limpa o destaque de seleção da pilha de edições
        document.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
        
        if (btnShowTools) {
            btnShowTools.classList.remove('text-[rgb(144,160,21)]');
            btnShowTools.classList.add('text-gray-500');
        }
        if (btnShowThoughts) {
            btnShowThoughts.classList.remove('text-[#3b82f6]');
            btnShowThoughts.classList.add('text-gray-500');
        }
        if (btnCopyTools) btnCopyTools.classList.add('hidden');
        if (btnUndo) btnUndo.classList.add('hidden');
        if (btnRedo) btnRedo.classList.add('hidden');
        if (btnEyeDiff) btnEyeDiff.classList.add('hidden');
        if (lblUndoCount) lblUndoCount.classList.add('hidden');
        if (lblRedoCount) lblRedoCount.classList.add('hidden');
        currentOpenedDiff = null;

        col3Title.textContent = 'Código';
        col3Title.onclick = null;
        col3Title.ondblclick = null;
        col3Title.title = "";
        col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[rgb(144,160,21)]');
        col3Title.classList.add('text-gray-200');

        // Restaura o layout padrão da Col 3 (usado pelo modo de busca).
        codeViewContainer.style.display = '';
        codeViewContainer.style.flexDirection = '';
        codeViewContainer.style.padding = '';
    }

    function closeCol3() {
        panelCol3.classList.add('hidden');
        resetCol3State();
    }

    if (btnShowThoughts) {
        btnShowThoughts.addEventListener("click", (e) => {
            e.stopPropagation();
            if (isShowingThoughts) {
                closeCol3(); // Se já está aberto, fecha tudo
            } else {
                isShowingThoughts = true;
                isShowingTools = false;
                isShowingQuestions = false;
                panelCol3.classList.remove("hidden");
                
                btnShowThoughts.classList.remove("text-gray-500");
                btnShowThoughts.classList.add("text-[#3b82f6]");
                
                if (btnShowTools) {
                    btnShowTools.classList.remove("text-[rgb(144,160,21)]");
                    btnShowTools.classList.add("text-gray-500");
                }
                if (btnCopyTools) btnCopyTools.classList.remove("hidden");
                if (btnUndo) btnUndo.classList.add("hidden");
                if (btnRedo) btnRedo.classList.add("hidden");
                if (lblUndoCount) lblUndoCount.classList.add("hidden");
                if (lblRedoCount) lblRedoCount.classList.add("hidden");
                atualizarBotoesUndoRedo();

                col3Title.textContent = isCounselorMode ? "Raciocínio do Counselor" : "Raciocínio do Coder";
                col3Title.onclick = null;
                col3Title.ondblclick = null;
                col3Title.title = "";
                col3Title.classList.remove("cursor-pointer", "hover:underline", "text-[rgb(144,160,21)]");
                col3Title.classList.add("text-gray-200");

                renderThoughts();
            }
        });
    }

    function renderThoughts() {
        let thoughtsHtml = '<div class="flex flex-col gap-6">';
        if (!currentViewingThoughts || currentViewingThoughts.length === 0) {
            thoughtsHtml += '<div class="text-gray-500 italic">Nenhum raciocínio registrado neste turno.</div>';
        } else {
            currentViewingThoughts.forEach(t => {
                // Converte strings literais \n para quebras de linha reais e remove \n\n literais
                t = t.replace(/\\n\\n/g, ' ').replace(/\\n/g, '\n');
                let formattedText = formatMessage(t, true);

                // Captura o <strong> no início, cria uma div com título maior e mais claro,
                // e remove os <br> excedentes que geravam o buraco vazio.
                formattedText = formattedText.replace(/^<strong>(.*?)<\/strong>(?:<br>|\s)*/i, '<div class="text-gray-100 font-bold text-[15px] mb-1">$1</div>');

                thoughtsHtml += `<div class="text-gray-300 text-sm leading-relaxed">${formattedText}</div>`;
            });
        }
        thoughtsHtml += "</div>";
        codeViewContainer.innerHTML = thoughtsHtml;
    }

    function renderQuestions() {
        let questionsHtml = '<div class="flex flex-col gap-6">';
        if (!currentViewingQuestions || currentViewingQuestions.length === 0) {
            questionsHtml += '<div class="text-gray-500 italic">Nenhuma pergunta registrada neste turno.</div>';
        } else {
            currentViewingQuestions.forEach(q => {
                const formattedText = formatMessage(q, true);
                questionsHtml += `<div class="text-gray-300 text-sm leading-relaxed">${formattedText}</div>`;
            });
        }
        questionsHtml += "</div>";
        codeViewContainer.innerHTML = questionsHtml;
    }

    function renderTools() {
        let toolsHtml = '<div class="space-y-4">';
        if (!currentViewingTools || currentViewingTools.length === 0) {
            toolsHtml += '<div class="text-gray-500 italic">Nenhuma ferramenta associada a este turno.</div>';
        } else {
            currentViewingTools.forEach(t => {
                toolsHtml += `<div class="flex flex-col gap-1.5">`;
                toolsHtml += `<div class="text-[rgb(144,160,21)] font-bold text-sm tracking-wide">FERRAMENTA: ${t.name}</div>`;
                if (t.args && Object.keys(t.args).length > 0) {
                    const ordemChaves = ['caminho_relativo', 'linha_inicio', 'linha_fim', 'termo', 'comando', 'texto_antigo', 'texto_novo', 'conteudo'];

                    const chavesOrdenadas = Object.keys(t.args).sort((a, b) => {
                        let posA = ordemChaves.indexOf(a);
                        let posB = ordemChaves.indexOf(b);
                        if (posA === -1) posA = 999;
                        if (posB === -1) posB = 999;
                        return posA - posB;
                    });

                    chavesOrdenadas.forEach(key => {
                        let val = t.args[key];
                        let displayVal = val;
                        if (key === 'texto_antigo' || key === 'texto_novo' || key === 'conteudo') {
                            const escapedCode = val.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                            displayVal = `<a href="#" class="text-[rgb(144,160,21)] hover:underline" onclick="const codeEl = this.nextElementSibling; if(codeEl.classList.contains('hidden')){codeEl.classList.remove('hidden'); this.textContent='[Recolher]';}else{codeEl.classList.add('hidden'); this.textContent='[Ver Código]';}; return false;">[Ver Código]</a><div class="hidden mt-2 p-3 bg-[#121212] rounded font-mono text-xs whitespace-pre-wrap text-gray-300 border border-[#333] max-h-64 overflow-y-auto custom-scrollbar">${escapedCode}</div>`;
                        } else if (typeof val === 'string') {
                            displayVal = val.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                        } else {
                            displayVal = JSON.stringify(val);
                        }
                        toolsHtml += `<div class="text-gray-400 text-xs font-mono ml-4"><span class="text-gray-500">-&gt;</span> ${key}: <span class="text-gray-300">${displayVal}</span></div>`;
                    });
                } else {
                    toolsHtml += `<div class="text-gray-400 text-xs font-mono ml-4"><span class="text-gray-500">-&gt;</span> Sem argumentos (Chamada simples)</div>`;
                }
                if (t.urls && t.urls.length > 0) {
                    const urlItems = t.urls.map(url =>
                        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="block text-[rgb(144,160,21)] hover:underline break-all font-mono text-xs py-1" title="${escapeHtml(url)}">${escapeHtml(url)}</a>`
                    ).join('');
                    toolsHtml += `<div class="text-gray-400 text-xs font-mono ml-4"><span class="text-gray-500">-&gt;</span> `;
                    toolsHtml += `<a href="#" class="text-[rgb(144,160,21)] hover:underline" onclick="const box=this.nextElementSibling; if(box.classList.contains('hidden')){box.classList.remove('hidden'); this.textContent='[Recolher fontes]';}else{box.classList.add('hidden'); this.textContent='[Ver ${t.urls.length} fonte(s)]';}; return false;">[Ver ${t.urls.length} fonte(s)]</a>`;
                    toolsHtml += `<div class="hidden mt-2 p-3 bg-[#121212] rounded border border-[#333] max-h-64 overflow-y-auto custom-scrollbar">${urlItems}</div>`;
                    toolsHtml += `</div>`;
                }
                toolsHtml += `<hr class="border-[#333] mt-3 mb-1 w-1/2">`;
                toolsHtml += `</div>`;
            });
        }
        toolsHtml += '</div>';
        codeViewContainer.innerHTML = toolsHtml;
    }

    // Exibe o painel da pergunta do usuário (agora o comportamento padrão ao
    // selecionar uma rodada, substituindo o antigo estado vazio "Código").
    function showQuestionPanel(group) {
        resetCol3State();
        isShowingQuestions = true;
        panelCol3.classList.remove("hidden");
        if (btnCopyTools) btnCopyTools.classList.remove("hidden");

        const nome = (group && (group.displayName || group.name)) || "Pergunta do Usuário";
        col3Title.textContent = nome;
        col3Title.onclick = null;

        if (group && (group.displayName || group.name)) {
            col3Title.classList.remove("text-gray-200");
            col3Title.classList.add("cursor-pointer", "hover:underline", "text-[rgb(144,160,21)]");
            col3Title.title = "Clique duas vezes para renomear a rodada";
            col3Title.ondblclick = () => beginRenameRound(group);
        } else {
            col3Title.ondblclick = null;
            col3Title.title = "";
        }

        renderQuestions();
    }

    function beginRenameRound(group) {
        const atual = group.displayName || group.name || "Tarefa";
        const input = document.createElement("input");
        input.type = "text";
        input.value = atual;
        input.className = "bg-[#121212] border border-[#333] rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-[rgb(144,160,21)] w-full";
        col3Title.innerHTML = "";
        col3Title.appendChild(input);
        input.focus();
        input.select();

        let finalizado = false;
        const commit = async () => {
            if (finalizado) return;
            finalizado = true;
            const novoNome = input.value.trim() || atual;
            col3Title.textContent = novoNome;
            await renameRound(group, novoNome);
        };
        const cancelar = () => {
            if (finalizado) return;
            finalizado = true;
            col3Title.textContent = atual;
        };

        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            else if (e.key === "Escape") { e.preventDefault(); cancelar(); }
        });
        input.addEventListener("blur", commit);
        input.addEventListener("click", (e) => e.stopPropagation());
        input.addEventListener("dblclick", (e) => e.stopPropagation());
    }

    async function renameRound(group, novoNome) {
        group.name = novoNome;
        group.displayName = novoNome;
        if (group.nameEl) {
            group.nameEl.textContent = novoNome;
        }
        // Atualiza o cache de detalhes para não perder o novo nome em re-renderizações.
        Object.keys(sessionDetailCache).forEach(key => {
            const logs = sessionDetailCache[key] || [];
            logs.forEach(saved => {
                if (String(saved.id) === String(group.id)) {
                    saved.name = novoNome;
                }
            });
        });
        try {
            await fetch('http://127.0.0.1:5000/api/session_log/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ round_id: group.id, name: novoNome })
            });
        } catch (e) {
            console.error('Erro ao renomear rodada:', e);
        }
    }

    if (btnShowTools) {
        btnShowTools.addEventListener('click', (e) => {
            e.stopPropagation();
            if (isShowingTools) {
                closeCol3(); // Se já está aberto, fecha tudo
            } else {
                isShowingTools = true;
                isShowingThoughts = false;
                isShowingQuestions = false;
                panelCol3.classList.remove('hidden');

                btnShowTools.classList.remove('text-gray-500');
                btnShowTools.classList.add('text-[rgb(144,160,21)]');
                
                if (btnShowThoughts) {
                    btnShowThoughts.classList.remove('text-[#3b82f6]');
                    btnShowThoughts.classList.add('text-gray-500');
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
                col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[rgb(144,160,21)]');
                col3Title.classList.add('text-gray-200');

                renderTools();
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
            
            if (isShowingQuestions) {
                // MODO PERGUNTA: copia o texto puro da pergunta feita ao usuário
                if (currentViewingQuestions && currentViewingQuestions.length > 0) {
                    currentViewingQuestions.forEach((q, i) => {
                        let plainText = q.replace(/<[^>]*>/g, '');
                        plainText = plainText.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
                        clipboardText += plainText;
                        if (i < currentViewingQuestions.length - 1) {
                            clipboardText += '\n\n---\n\n';
                        }
                    });
                } else {
                    clipboardText = 'Nenhuma pergunta registrada neste turno.';
                }
            } else if (isShowingThoughts) {
                // MODO PENSAMENTOS (MEMÓRIAS): copia o texto puro
                if (currentViewingThoughts && currentViewingThoughts.length > 0) {
                    currentViewingThoughts.forEach((t, i) => {
                        // Remove tags HTML para texto limpo
                        let plainText = t.replace(/<[^>]*>/g, '');
                        // Decodifica entidades HTML comuns
                        plainText = plainText.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"');
                        clipboardText += plainText;
                        if (i < currentViewingThoughts.length - 1) {
                            clipboardText += '\n\n---\n\n';
                        }
                    });
                } else {
                    clipboardText = 'Nenhum raciocínio registrado neste turno.';
                }
            } else {
                // MODO FERRAMENTAS: comportamento original
                if (currentViewingTools && currentViewingTools.length > 0) {
                    currentViewingTools.forEach(t => {
                        clipboardText += `FERRAMENTA: ${t.name}\n`;
                        if (t.args && Object.keys(t.args).length > 0) {
                            const ordemChaves = ['caminho_relativo', 'linha_inicio', 'linha_fim', 'termo', 'comando', 'texto_antigo', 'texto_novo', 'conteudo'];
                            const chavesOrdenadas = Object.keys(t.args).sort((a, b) => {
                                let posA = ordemChaves.indexOf(a);
                                let posB = ordemChaves.indexOf(b);
                                if (posA === -1) posA = 999;
                                if (posB === -1) posB = 999;
                                return posA - posB;
                            });

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

            navigator.clipboard.writeText(clipboardText.trim());
            btnCopyTools.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-[rgb(144,160,21)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
            
            // Restaura usando a variável fixa
            setTimeout(() => { btnCopyTools.innerHTML = originalToolsIcon; }, 2000);
        });
    }

    // ============================================================
    // DESFAZER / REFAZER (UNDO / REDO)
    // ============================================================
    function encontrarArquivoUndo(nomeRelativo) {
        if (!undoRedoFiles || !undoRedoFiles.length) return null;
        const alvo = (nomeRelativo || '').replace(/\\/g, '/');
        const base = alvo.split('/').pop() || alvo;
        return undoRedoFiles.find(f =>
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

    function carregarConteudoArquivo(caminho) {
        if (!caminho) {
            codeViewContainer.textContent = '';
            return;
        }
        fetch(`http://127.0.0.1:5000/api/file_content?caminho=${encodeURIComponent(caminho)}`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    codeViewContainer.textContent = 'Erro: ' + data.error;
                    return;
                }
                codeViewContainer.textContent = data.conteudo || '';
            })
            .catch(err => {
                console.error('Erro ao carregar conteúdo do arquivo:', err);
                codeViewContainer.textContent = 'Erro de conexão ao carregar o arquivo.';
            });
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
                    codeViewContainer.textContent = 'Erro: ' + data.error;
                    return;
                }
                if (data.criado) {
                    codeViewContainer.innerHTML = '<span class="text-gray-500 italic">(arquivo criado nesta sess\u00e3o \u2014 n\u00e3o havia c\u00f3digo original)</span>';
                    return;
                }
                codeViewContainer.textContent = data.conteudo || '';
            })
            .catch(err => {
                console.error('Erro ao carregar conte\u00fado original do arquivo:', err);
                codeViewContainer.textContent = 'Erro de conex\u00e3o ao carregar o arquivo original.';
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
        // (corrige o movimento desnecessário quando o texto está próximo).
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
            caminhoAlvo = require('path').join(basePath, caminhoAlvo);
        }
        currentUndoFile = caminhoAlvo;

        panelCol3.classList.remove('hidden');
        isShowingTools = false;
        isShowingThoughts = false;
        isShowingQuestions = false;
        if (btnShowTools) {
            btnShowTools.classList.remove('text-[rgb(144,160,21)]');
            btnShowTools.classList.add('text-gray-500');
        }
        if (btnShowThoughts) {
            btnShowThoughts.classList.remove('text-[#3b82f6]');
            btnShowThoughts.classList.add('text-gray-500');
        }
        if (btnCopyTools) btnCopyTools.classList.add('hidden');
        if (btnUndo) btnUndo.classList.remove('hidden');
        if (btnRedo) btnRedo.classList.remove('hidden');
        if (btnEyeDiff) btnEyeDiff.classList.add('hidden');
        if (lblUndoCount) lblUndoCount.classList.remove('hidden');
        if (lblRedoCount) lblRedoCount.classList.remove('hidden');
        currentOpenedDiff = null;

        col3Title.textContent = fileData.name;
        col3Title.title = 'Abrir pasta no Windows';
        col3Title.classList.remove('text-gray-200', 'text-white');
        col3Title.classList.add('cursor-pointer', 'hover:underline', 'text-[rgb(144,160,21)]');
        col3Title.ondblclick = null;
        col3Title.onclick = () => {
            const { shell } = require('electron');
            const path = require('path');
            const basePath = document.getElementById('lbl-folder').textContent;
            if (basePath) {
                const fullPath = path.join(basePath, fileData.name);
                shell.showItemInFolder(fullPath);
            }
        };

        carregarConteudoOriginal(currentUndoFile);
        atualizarBotoesUndoRedo();
    }

    function adicionarFileNaLista(fileData) {
        const fileEl = document.createElement('div');
        fileEl.className = 'rounded-[10px] overflow-hidden';

        const fileHeader = document.createElement('div');
        fileHeader.className = 'file-card-header px-3.5 py-2.5 text-[13px] text-[rgb(144,160,21)] cursor-pointer transition-colors flex justify-between items-center min-h-[54px]';
        fileHeader.innerHTML = `<span class="flex-1 truncate font-semibold">${fileData.name}</span><span class="file-toggle-icon text-gray-500 text-lg font-mono leading-none ml-2 cursor-pointer hover:text-white transition-colors select-none">+</span>`;

        const fileContent = document.createElement('div');
        fileContent.className = 'p-2 hidden flex-col gap-2';

        fileData.diffElements.forEach(diffEl => fileContent.appendChild(diffEl));
        if (fileData.diffElements.length === 0) {
            fileContent.innerHTML = `<div class="p-2 text-sm text-gray-500 font-mono">Nenhuma alteração de código.</div>`;
        }

        const toggleIcon = fileHeader.querySelector('.file-toggle-icon');

        function expandir() {
            // Acordeão: recolhe os demais cards de arquivo para manter apenas um aberto
            Array.from(filesListContainer.children).forEach(card => {
                if (card === fileEl) return;
                const content = card.children[1];
                const icon = card.querySelector('.file-toggle-icon');
                if (content && !content.classList.contains('hidden')) {
                    content.classList.add('hidden');
                    content.classList.remove('flex');
                    if (icon) icon.textContent = '+';
                }
            });
            fileContent.classList.remove('hidden');
            fileContent.classList.add('flex');
            if (toggleIcon) toggleIcon.textContent = '-';
        }

        function recolher() {
            fileContent.classList.add('hidden');
            fileContent.classList.remove('flex');
            if (toggleIcon) toggleIcon.textContent = '+';
        }

        function marcarSelecionado() {
            document.querySelectorAll('.file-card-header').forEach(h => h.classList.remove('file-card-selected'));
            fileHeader.classList.add('file-card-selected');
        }

        // Clique no cabeçalho (fora do ícone): abre/seleciona. Se já expandido, apenas
        // seleciona novamente (NÃO recolhe). Recolher só pelo ícone de "-".
        fileHeader.addEventListener('click', () => {
            const estavaFechado = fileContent.classList.contains('hidden');
            if (estavaFechado) {
                expandir();
            }
            marcarSelecionado();
            currentFileDataRef = fileData;
            selecionarArquivo(fileData);
        });

        if (toggleIcon) {
            toggleIcon.addEventListener('click', (e) => {
                e.stopPropagation();
                if (fileContent.classList.contains('hidden')) {
                    expandir();
                    marcarSelecionado();
                    currentFileDataRef = fileData;
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
    }

    function atualizarBotoesUndoRedo() {
        // Consulta o estado das pilhas no backend e habilita/desabilita os bot\u00f5es
        fetch('http://127.0.0.1:5000/api/undo_redo_status')
            .then(r => r.json())
            .then(data => {
                undoRedoFiles = data.files || [];
                atualizarEstadoBotoes();

                if (currentFileDataRef) {
                    const arquivo = encontrarArquivoUndo(currentFileDataRef.name);
                    if (arquivo) {
                        currentUndoFile = arquivo.caminho;
                        aplicarRiscadoUndo(currentFileDataRef, arquivo.redo_count);
                    }
                }
            })
            .catch(() => {
                // Falha silenciosa: mant\u00e9m os bot\u00f5es como est\u00e3o
            });
    }

    function normalizarCaminho(c) {
        return (c || '').replace(/\\/g, '/').toLowerCase();
    }

    function atualizarEstadoBotoes() {
        const alvo = normalizarCaminho(currentUndoFile);
        const selecionado = undoRedoFiles.find(f => normalizarCaminho(f.caminho) === alvo);
        if (btnUndo) btnUndo.disabled = !selecionado || !selecionado.can_undo;
        if (btnRedo) btnRedo.disabled = !selecionado || !selecionado.can_redo;
        if (lblUndoCount) lblUndoCount.textContent = selecionado ? selecionado.undo_count : '';
        if (lblRedoCount) lblRedoCount.textContent = selecionado ? selecionado.redo_count : '';
    }

    function executarUndoRedo(acao) {
        const btn = acao === 'undo' ? btnUndo : btnRedo;
        if (btn && btn.disabled) return;
        if (!currentUndoFile) return;

        // Captura o estado da pilha ANTES da opera\u00e7\u00e3o para selecionar o item correto depois.
        // diffElements est\u00e1 em ordem cronol\u00f3gica: \u00edndice 0 = edi\u00e7\u00e3o mais antiga,
        // \u00edndice total-1 = edi\u00e7\u00e3o mais recente. O backend desfaz/refaz sempre o topo (LIFO).
        const fileData = currentFileDataRef || encontrarFileDataPorCaminho(currentUndoFile);
        const totalItens = fileData ? fileData.diffElements.length : 0;
        const arquivoAtual = encontrarArquivoUndo(currentUndoFile);
        const redoCountAntes = arquivoAtual ? arquivoAtual.redo_count : 0;

        fetch(`http://127.0.0.1:5000/api/${acao}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caminho: currentUndoFile })
        })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'ok' || data.status === 'empty') {
                    currentOpenedDiff = null;
                    atualizarBotoesUndoRedo();

                    if (data.status === 'ok' && totalItens > 0) {
                        // Mapeia a a\u00e7\u00e3o para o item da pilha rec\u00e9m-desfeito/refeito,
                        // fazendo a sele\u00e7\u00e3o "caminhar" junto com a linha do tempo.
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
                    lblStatus.textContent = 'Erro: ' + (data.message || 'opera\u00e7\u00e3o falhou');
                }
            })
            .catch(err => {
                console.error(`Erro ao executar ${acao}:`, err);
                lblStatus.textContent = `Erro de conex\u00e3o ao ${acao === 'undo' ? 'desfazer' : 'refazer'}.`;
            });
    }

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

    const lblFolder = document.getElementById('lbl-folder');
    const lblStatus = document.getElementById('lbl-status');
    const lblExecuting = document.getElementById('lbl-executing');
    const lblMetrics = document.getElementById('lbl-metrics');
    const alertPopup = document.getElementById('alert-popup');
    const alertPopupContent = document.getElementById('alert-popup-content');
    const btnCloseAlert = document.getElementById('btn-close-alert');

    // Store session logs data
    window.sessionLogsData = [];

    btnCloseAlert.addEventListener('click', () => {
        alertPopup.classList.remove('opacity-100', 'pointer-events-auto');
        alertPopup.classList.add('opacity-0', 'pointer-events-none');
        alertPopupContent.classList.remove('scale-100');
        alertPopupContent.classList.add('scale-95');
    });

    btnConfirmDelete.addEventListener('click', () => {
        const total = selectedSessionFiles.size + selectedTurnIds.size;
        if (total === 0) return;
        if (lblDeleteMessage) {
            lblDeleteMessage.textContent = `Tem certeza que deseja excluir ${total} registro(s)? Esta ação não pode ser desfeita.`;
        }
        confirmDeletePopup.classList.remove('opacity-0', 'pointer-events-none');
        confirmDeletePopup.classList.add('opacity-100', 'pointer-events-auto');
        confirmDeleteContent.classList.remove('scale-95');
        confirmDeleteContent.classList.add('scale-100');
    });

    btnCancelDelete.addEventListener('click', (e) => {
        e.stopPropagation();
        closeConfirmDeletePopup();
    });

    btnConfirmDeleteYes.addEventListener('click', async (e) => {
        e.stopPropagation();
        closeConfirmDeletePopup();
        await performDeleteLogs();
    });

    // Evita que cliques no overlay de confirmação fechem o painel lateral por baixo.
    confirmDeletePopup.addEventListener('click', (e) => e.stopPropagation());

    btnOpenLog.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = slidingPanelContainer.classList.contains('translate-x-0');
        if (!isOpen) {
            // Abre o painel já mostrando a aba de logs da sessão.
            slidingPanelContainer.classList.remove('-translate-x-full');
            slidingPanelContainer.classList.add('translate-x-0');
            renderCurrentSessionLogs();
        } else if (isShowingSessionHistory) {
            // Painel aberto no histórico: troca para os logs da sessão.
            renderCurrentSessionLogs();
        } else {
            // Painel aberto nos logs da sessão: fecha o painel.
            slidingPanelContainer.classList.remove('translate-x-0');
            slidingPanelContainer.classList.add('-translate-x-full');
            syncMenuIcons();
        }
    });

    btnClosePanel.addEventListener('click', () => {
        slidingPanelContainer.classList.remove('translate-x-0');
        slidingPanelContainer.classList.add('-translate-x-full');
        syncMenuIcons();
    });

    // Fecha o painel lateral automaticamente ao clicar fora dele (ex.: no chat).
    document.addEventListener('click', (e) => {
        if (slidingPanelContainer.classList.contains('translate-x-0')) {
            if (!slidingPanelContainer.contains(e.target) && !btnOpenLog.contains(e.target) && !btnSessionHistory.contains(e.target)) {
                slidingPanelContainer.classList.remove('translate-x-0');
                slidingPanelContainer.classList.add('-translate-x-full');
                syncMenuIcons();
            }
        }
    });

    if(btnCloseCol2) btnCloseCol2.addEventListener('click', () => {
        panelCol2.classList.add('hidden');
        closeCol3();
    });

    if(btnCloseCol3) btnCloseCol3.addEventListener('click', () => {
        closeCol3();
    });

    // Auto-resize textarea
    inputText.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    inputText.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    btnSend.addEventListener('click', sendMessage);

    const { ipcRenderer } = require('electron');

    btnSelectFolder.addEventListener('click', async () => {
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
                                btnSelectFolder.title = data.folder;
                                btnSelectFolder.classList.remove('text-white', 'hover:text-gray-300');
                                btnSelectFolder.classList.add('text-[rgb(144,160,21)]', 'hover:brightness-110');
                                lblStatus.textContent = 'Pasta selecionada';
                                resetWorkspaceUI();
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
    });

    function addMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        let prefix = '';
        if (role === 'ai') {
            const agentName = isCounselorMode ? 'Axio Counselor' : 'Axio Coder';
            const agentColor = isCounselorMode ? 'text-blue-400' : 'text-[rgb(144,160,21)]';
            prefix = `<div class="flex items-center gap-2 mb-1"><span class="${agentColor} font-bold cursor-pointer hover:underline" onclick="event.stopPropagation(); const logId = this.closest('.message').dataset.logId; if(logId) { const log = window.sessionLogsData.find(l => l.id === logId); if(log) { if(document.getElementById('sliding-panel-container').classList.contains('-translate-x-full')) document.getElementById('btn-open-log').click(); setTimeout(() => log.domElement.click(), 100); } }" title="Ver análise desta resposta">${agentName}</span><button class="btn-copy-msg text-gray-500 hover:text-white transition-colors" title="Copiar mensagem"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg></button></div>`;
        }

        const linhas = text.split('\n').length;

        if (role === 'user' && linhas > 7) {
            const contentDiv = document.createElement('div');
            contentDiv.className = 'overflow-hidden transition-all duration-300 relative';
            contentDiv.style.maxHeight = '150px';
            contentDiv.innerHTML = formatMessage(text, true);

            const fadeDiv = document.createElement('div');
            fadeDiv.className = 'absolute bottom-0 left-0 w-full h-16 bg-gradient-to-t from-[#121212] to-[#121212]/0 pointer-events-none transition-opacity duration-300';
            contentDiv.appendChild(fadeDiv);

            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'mt-2 text-white/50 hover:text-white focus:outline-none w-full flex justify-center transition-colors';
            toggleBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>`;

            toggleBtn.addEventListener('click', () => {
                if (contentDiv.style.maxHeight === '150px') {
                    contentDiv.style.maxHeight = 'none';
                    toggleBtn.querySelector('svg').classList.add('rotate-180');
                    fadeDiv.classList.add('opacity-0');
                    
                    setTimeout(() => {
                        msgDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
                    }, 310);
                } else {
                    contentDiv.style.maxHeight = '150px';
                    toggleBtn.querySelector('svg').classList.remove('rotate-180');
                    fadeDiv.classList.remove('opacity-0');
                }
            });

            msgDiv.appendChild(contentDiv);
            msgDiv.appendChild(toggleBtn);

            contentDiv.querySelectorAll('pre code').forEach((block) => {
                if (typeof hljs !== 'undefined') hljs.highlightElement(block);
            });
            attachCodeBlockListeners(contentDiv);
            
        } else if (role === 'ai' || role === 'user') {
            msgDiv.innerHTML = prefix + formatMessage(text, role === 'user');
            if (role === 'ai') {
                const copyBtn = msgDiv.querySelector('.btn-copy-msg');
                if (copyBtn) {
                    copyBtn.addEventListener('click', () => {
                        navigator.clipboard.writeText(text);
                        const originalIcon = copyBtn.innerHTML;
                        copyBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
                        setTimeout(() => { copyBtn.innerHTML = originalIcon; }, 2000);
                    });
                }
            }
            msgDiv.querySelectorAll('pre code').forEach((block) => {
                if (typeof hljs !== 'undefined') hljs.highlightElement(block);
            });
            attachCodeBlockListeners(msgDiv);
        } else {
            msgDiv.textContent = text;
        }
        
        if (role === 'user') {
            chatInnerLeft.appendChild(msgDiv);
            chatContainerLeft.scrollTop = chatContainerLeft.scrollHeight;
        } else {
            chatInnerRight.appendChild(msgDiv);
            chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
        }
        return msgDiv;
    }

    function formatMessage(text, escape = false) {
        if (escape) {
            text = escapeHtml(text);
        }
        
        const parts = text.split(/(```[\s\S]*?```)/g);
        for (let i = 0; i < parts.length; i++) {
            if (parts[i].startsWith('```') && parts[i].endsWith('```')) {
                const match = parts[i].match(/```(\w+)?\n([\s\S]*?)```/);
                let lang = '';
                let code = '';
                
                if (match) {
                    lang = match[1] || 'text';
                    code = escapeHtml(match[2]);
                } else {
                    code = escapeHtml(parts[i].slice(3, -3));
                    lang = 'text';
                }

                const displayLang = lang === 'text' ? 'Código' : lang;

                const headerHtml = `<div class="flex justify-between items-center px-4 py-2 bg-[#2a2a2a] text-xs text-gray-300 font-sans border-b border-[#333]"><span class="capitalize">${displayLang}</span><button class="copy-code-btn text-gray-400 hover:text-white transition-colors focus:outline-none" title="Copiar código"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg></button></div>`;

                parts[i] = `<div class="code-block-container bg-[#1e1e1e] rounded-xl overflow-hidden mt-0 mb-1">${headerHtml}<div class="p-4 overflow-x-auto custom-scrollbar"><pre><code class="language-${lang}">${code}</code></pre></div></div>`;
                } else {
                    parts[i] = parts[i].replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                    parts[i] = parts[i].replace(/`([^`]+)`/g, (match, p1) => {
                        return `<code class="bg-[#2d2d2d] text-[#e2e8f0] px-1.5 py-0.5 rounded text-sm font-mono">${escapeHtml(p1)}</code>`;
                    });
                    parts[i] = parts[i].replace(/\n/g, '<br>');
                }
        }
        return parts.join('');
    }

    function attachCodeBlockListeners(container) {
        // Ícone fixo
        const originalCodeIcon = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>`;

        container.querySelectorAll('.copy-code-btn').forEach(btn => {
            if (btn.dataset.listenerAttached) return;
            btn.dataset.listenerAttached = 'true';

            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const codeBlock = btn.closest('.code-block-container').querySelector('code');
                if (codeBlock) {
                    navigator.clipboard.writeText(codeBlock.textContent);
                    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-[rgb(144,160,21)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
                    
                    // Restaura usando a variável fixa
                    setTimeout(() => { btn.innerHTML = originalCodeIcon; }, 2000);
                }
            });
        });
    }

    function createCopyButton(textToCopy, iconColorClass, titleText) {
        const btn = document.createElement('button');
        btn.className = `ml-2 ${iconColorClass} hover:text-white transition-colors focus:outline-none`;
        btn.title = titleText;
        
        // Ícone fixo
        const originalDiffIcon = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>`;
        btn.innerHTML = originalDiffIcon;
        
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            navigator.clipboard.writeText(textToCopy);
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>`;
            
            // Restaura usando a variável fixa
            setTimeout(() => { btn.innerHTML = originalDiffIcon; }, 2000);
        });
        return btn;
    }

    const NL = String.fromCharCode(10);

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
        if (isEyeMode) {
            btnEyeDiff.classList.remove('text-gray-500');
            btnEyeDiff.classList.add('text-[rgb(144,160,21)]');
            btnEyeDiff.title = 'Modo foco ATIVADO: exibir apenas trechos alterados';
            if (eyeOn) eyeOn.classList.remove('hidden');
            if (eyeOff) eyeOff.classList.add('hidden');
        } else {
            btnEyeDiff.classList.remove('text-[rgb(144,160,21)]');
            btnEyeDiff.classList.add('text-gray-500');
            btnEyeDiff.title = 'Modo foco: exibir apenas trechos alterados';
            if (eyeOn) eyeOn.classList.add('hidden');
            if (eyeOff) eyeOff.classList.remove('hidden');
        }
    }

    if (btnEyeDiff) {
        btnEyeDiff.addEventListener('click', (e) => {
            e.stopPropagation();
            isEyeMode = !isEyeMode;
            atualizarIconeOlho();
            // Só re-renderiza o trecho se o painel atual for o de código.
            // Em Ferramentas/Raciocínio/Pergunta, apenas alterna o estado visual
            // (o modo foco continua valendo quando o usuário voltar para a pilha).
            if (currentOpenedDiff && !isShowingTools && !isShowingThoughts && !isShowingQuestions) {
                codeViewContainer.innerHTML = (isEyeMode && currentOpenedDiff.snippetHtml)
                    ? currentOpenedDiff.snippetHtml
                    : currentOpenedDiff.fullHtml;
                rolarParaDestaque();
            }
        });
    }

    function createChildBalloon(title, htmlContent, snippetHtml, rawTextOld, rawTextNew, fileName, sessionTools) {
        const child = document.createElement('div');
        child.className = 'rounded-[10px] overflow-hidden';
        
        const header = document.createElement('div');
        header.className = 'px-3.5 py-2.5 cursor-pointer flex justify-between items-center hover:bg-white/5 transition-colors min-h-[54px]';
        
        const titleContainer = document.createElement('div');
        titleContainer.className = 'flex items-center flex-1';
        titleContainer.innerHTML = `<span class="undo-title text-[13px] text-[#ddd] leading-tight hover:text-white transition-colors">${title}</span>`;
        
        const actionsContainer = document.createElement('div');
        actionsContainer.className = 'flex items-center gap-2';
        
        const isSubstitution = rawTextOld && rawTextNew;
        
        if (rawTextOld) {
            const color = 'text-[#f43f5e]';
            const tooltip = isSubstitution ? 'Copiar código substituído' : 'Copiar código';
            actionsContainer.appendChild(createCopyButton(rawTextOld, color, tooltip));
        }
        
        if (rawTextNew) {
            const color = 'text-[rgb(144,160,21)]';
            const tooltip = isSubstitution ? 'Copiar código atualizado' : 'Copiar código';
            actionsContainer.appendChild(createCopyButton(rawTextNew, color, tooltip));
        }
        
        header.appendChild(titleContainer);
        header.appendChild(actionsContainer);
        
        header.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Se clicar no mesmo arquivo que já está aberto, ele fecha a coluna 3
            // (clique duplo n\u00e3o fecha mais a coluna 3)

            // Marca este item como selecionado na pilha de edições (destaque fixo).
            // Limpa GLOBALMENTE para não deixar item de outra pilha/arquivo selecionado.
            document.querySelectorAll('.diff-selected').forEach(el => el.classList.remove('diff-selected'));
            child.classList.add('diff-selected');

            // Garante que o undo/redo atue no arquivo deste item da pilha.
            const arquivo = encontrarArquivoUndo(fileName);
            let caminhoAlvo = arquivo ? arquivo.caminho : fileName;
            const basePath = document.getElementById('lbl-folder').textContent;
            if (basePath && !/^([a-zA-Z]:[\\/]|\/)/.test(caminhoAlvo)) {
                caminhoAlvo = require('path').join(basePath, caminhoAlvo);
            }
            currentUndoFile = caminhoAlvo;

            const grupoAtual = window.currentActiveLogGroup;
            if (grupoAtual && grupoAtual.files) {
                const fd = grupoAtual.files.find(f => f.name === fileName);
                if (fd) currentFileDataRef = fd;
            }

            window.currentActiveFileBalloonHtml = htmlContent;
            panelCol3.classList.remove('hidden');
            
            // Força a nuvem e o martelo a ficarem inativos (cinzas) ao ler um arquivo
            isShowingTools = false;
            isShowingThoughts = false;
            if (btnShowTools) {
                btnShowTools.classList.remove('text-[rgb(144,160,21)]');
                btnShowTools.classList.add('text-gray-500');
            }
            if (btnShowThoughts) {
                btnShowThoughts.classList.remove('text-[#3b82f6]');
                btnShowThoughts.classList.add('text-gray-500');
            }
            if (btnCopyTools) btnCopyTools.classList.add('hidden');
            if (btnUndo) btnUndo.classList.remove('hidden');
            if (btnRedo) btnRedo.classList.remove('hidden');
            if (btnEyeDiff) btnEyeDiff.classList.remove('hidden');
            if (lblUndoCount) lblUndoCount.classList.remove('hidden');
            if (lblRedoCount) lblRedoCount.classList.remove('hidden');
            atualizarIconeOlho();

            col3Title.textContent = fileName;
            col3Title.title = "Abrir pasta no Windows";
            col3Title.classList.remove('text-gray-200', 'text-white');
            col3Title.classList.add('cursor-pointer', 'hover:underline', 'text-[rgb(144,160,21)]');

            col3Title.onclick = () => {
                const { shell } = require('electron');
                const path = require('path');
                const basePath = document.getElementById('lbl-folder').textContent;
                if (basePath) {
                    const fullPath = path.join(basePath, fileName);
                    shell.showItemInFolder(fullPath);
                }
            };

            currentOpenedDiff = { fullHtml: htmlContent, snippetHtml: snippetHtml, fileName: fileName };
            codeViewContainer.innerHTML = (isEyeMode && snippetHtml) ? snippetHtml : htmlContent;
            rolarParaDestaque();
            atualizarBotoesUndoRedo();
        });
        
        // Permite ao undo/redo "simular" o clique neste item da pilha, reutilizando
        // toda a lógica de abertura (destaque, cores, rolagem automática, botões).
        child._abrirDiff = () => header.click();

        child._data = {
            title: title,
            htmlContent: htmlContent,
            snippetHtml: snippetHtml,
            rawTextOld: rawTextOld,
            rawTextNew: rawTextNew,
            fileName: fileName
        };

        child.appendChild(header);
        return child;
    }

    function escapeHtml(unsafe) {
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    const fileInput = document.getElementById('file-input');
    const btnAttach = document.getElementById('btn-attach');
    const imagePreviewContainer = document.getElementById('image-preview-container');
    let attachedImages = []; // Array of { base64, dataUrl, name }
    let imageCounter = 1;

    function renderImagePreviews() {
        imagePreviewContainer.innerHTML = '';
        if (attachedImages.length === 0) {
            imagePreviewContainer.classList.add('hidden');
            return;
        }
        imagePreviewContainer.classList.remove('hidden');
        
        attachedImages.forEach((img, index) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'relative inline-block w-20 h-20 group';
            
            const imgEl = document.createElement('img');
            imgEl.className = 'w-full h-full object-cover rounded-lg border border-[#444]';
            imgEl.src = img.dataUrl;
            imgEl.title = img.name;
            
            const btnRemove = document.createElement('button');
            btnRemove.className = 'absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-red-600 focus:outline-none opacity-0 group-hover:opacity-100 transition-opacity';
            btnRemove.innerHTML = '✕';
            btnRemove.onclick = () => {
                attachedImages.splice(index, 1);
                renderImagePreviews();
            };
            
            wrapper.appendChild(imgEl);
            wrapper.appendChild(btnRemove);
            imagePreviewContainer.appendChild(wrapper);
        });
    }

    function addImage(file) {
        const reader = new FileReader();
        reader.onload = (readerEvent) => {
            const dataUrl = readerEvent.target.result;
            const base64 = dataUrl.split(',')[1];
            const name = `imagem${imageCounter++}`;
            attachedImages.push({ base64, dataUrl, name });
            renderImagePreviews();
        };
        reader.readAsDataURL(file);
    }

    btnAttach.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        for (let i = 0; i < files.length; i++) {
            addImage(files[i]);
        }
        fileInput.value = ''; // Reset input
    });

    // === NOVO CÓDIGO: CAPTURA DE CTRL+V (COLAR IMAGEM) ===
    inputText.addEventListener('paste', (e) => {
        const clipboardData = e.clipboardData || window.clipboardData;
        if (!clipboardData) return;

        let imagePasted = false;

        for (let i = 0; i < clipboardData.items.length; i++) {
            const item = clipboardData.items[i];
            if (item.type.indexOf('image/') !== -1) {
                imagePasted = true;
                e.preventDefault(); // Bloqueio total: proíbe o navegador de colar o texto
                
                const file = item.getAsFile();
                if (file) {
                    addImage(file);
                }
            }
        }
        
        // Limpeza de segurança: Se o navegador for teimoso e já tiver colado o Base64, nós apagamos.
        if (imagePasted) {
            setTimeout(() => {
                // Se for um texto gigante sem nenhum espaço (característica de Base64), apaga.
                if (inputText.value.length > 500 && !inputText.value.includes(' ')) {
                    inputText.value = '';
                    inputText.style.height = 'auto';
                }
            }, 10);
        }
    });
    // ====================================================

    // Função para expandir imagem
    window.expandImage = function(src) {
        const modal = document.getElementById('image-modal');
        const expandedImg = document.getElementById('expanded-image');
        expandedImg.src = src;
        modal.classList.remove('hidden');
    };

    function setStopButton() {
        if (btnSend) {
            btnSend.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><rect x="3" y="3" width="14" height="14" rx="2" /></svg>`;
            btnSend.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }

    function resetSendButton() {
        if (btnSend) {
            btnSend.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform rotate-90" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" /></svg>`;
            btnSend.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }

    // Sincroniza o indicador de carregamento (spinner no card + card pulsando) com o estado de processamento.
    // O spinner NÃO fica mais no topo (ao lado de "Logs da Sessão"): apenas dentro do card correspondente.
    function setLogsLoading(active) {
        document.querySelectorAll('#current-logs-wrapper > div.log-pulsing').forEach(el => el.classList.remove('log-pulsing'));

        if (active) {
            // Só o card da rodada EM ANDAMENTO deve pulsar/mostrar spinner.
            // O fallback para currentActiveLogGroup reativava o spinner de um
            // card antigo que estava selecionado na janela de arquivos.
            const alvo = window.currentGroupBalloon;
            if (alvo && alvo.domElement) {
                alvo.domElement.classList.add('log-pulsing');
            }
            if (alvo && alvo.spinner) alvo.spinner.classList.remove('hidden');
        } else {
            document.querySelectorAll('#current-logs-wrapper .logs-spinner').forEach(el => el.classList.add('hidden'));
        }
    }

    // Alterna suavemente entre o wrapper de logs da sessão e o de histórico,
    // aplicando fade-out no que está visível e fade-in no que vai aparecer.
    function fadeSwapLogs(showCurrent) {
        const showEl = showCurrent ? currentLogsWrapper : historyLogsWrapper;
        const hideEl = showCurrent ? historyLogsWrapper : currentLogsWrapper;
        if (!showEl || !hideEl || showEl === hideEl) return;

        // Fade-out do wrapper atualmente visível.
        if (!hideEl.classList.contains('hidden')) {
            hideEl.classList.remove('logs-fade-in');
            hideEl.classList.add('logs-fade-out');
            setTimeout(() => {
                hideEl.classList.add('hidden');
                hideEl.classList.remove('logs-fade-out');
            }, 200);
        }

        // Fade-in do wrapper que vai aparecer.
        showEl.classList.remove('hidden');
        showEl.classList.remove('logs-fade-out');
        showEl.classList.remove('logs-fade-in');
        void showEl.offsetWidth; // força reflow para reiniciar a animação
        showEl.classList.add('logs-fade-in');
    }

    // Mantem as cores dos icones do menu lateral coerentes com o estado do painel.
    // Padrao: selecionado = azul (#3b82f6, igual ao balao do conselheiro), exceto a pasta (verde).
    function syncMenuIcons() {
        const panelOpen = slidingPanelContainer.classList.contains('translate-x-0');
        const blue = 'text-[#3b82f6]';
        if (btnOpenLog) {
            const active = panelOpen && !isShowingSessionHistory;
            btnOpenLog.classList.toggle(blue, active);
            btnOpenLog.classList.toggle('text-white', !active);
        }
        if (btnSessionHistory) {
            const active = panelOpen && isShowingSessionHistory;
            btnSessionHistory.classList.toggle(blue, active);
            btnSessionHistory.classList.toggle('text-white', !active);
        }
    }

    function renderCurrentSessionLogs() {
        isShowingSessionHistory = false;
        clearDeleteSelection();
        if (historyLogsWrapper) {
            historyLogsWrapper.innerHTML = '';
        }
        fadeSwapLogs(true);
        syncMenuIcons();
        if (panelTitle) panelTitle.textContent = 'Logs da Sessão';
        if (btnHistorySearch) btnHistorySearch.classList.add('hidden');
        // Ao desativar o histórico, fecha as janelas laterais (arquivos/código)
        // e mantém visível apenas a janela de logs da sessão.
        panelCol2.classList.add('hidden');
        closeCol3();
        logListContainer.scrollTop = 0;
    }

    // Reseta todo o estado visual do workspace ao trocar de pasta/projeto,
    // para que Log da Sessão, Histórico e chat reflitam o novo projeto.
    function resetWorkspaceUI() {
        // Log da Sessão (memória + DOM)
        window.sessionLogsData = [];
        if (currentLogsWrapper) currentLogsWrapper.innerHTML = '';
        currentTurnLogs = [];
        currentTurnSummary = '';
        window.currentGroupBalloon = null;
        window.currentActiveLogGroup = null;

        // Histórico (cache + DOM)
        sessionHistoryLoaded = false;
        sessionHistoryList = [];
        sessionDetailCache = {};

        // Chat
        if (chatInnerLeft) chatInnerLeft.innerHTML = '';
        if (chatInnerRight) chatInnerRight.innerHTML = '';
        if (chatContainerLeft) chatContainerLeft.scrollTop = 0;
        if (chatContainerRight) chatContainerRight.scrollTop = 0;

        // Restaura o painel lateral para a aba de logs da sessão (vazia) e fecha Col2/Col3.
        renderCurrentSessionLogs();

        // Reinicia o stream SSE para descartar eventos pendentes do projeto anterior
        // e zerar as variáveis locais da closure (currentGroupBalloon, etc.).
        if (eventSource) {
            eventSource.close();
        }
        startSSE();
    }

    // Abre a Col 2 (janela de arquivos) mostrando os arquivos/diffs de um grupo de log.
    function openFilesPanel(group) {
        window.currentActiveLogGroup = group;
        currentViewingTools = group.tools || [];
        currentViewingThoughts = group.thoughts || [];
        currentViewingQuestions = group.questions || [];
        panelCol2.classList.remove('hidden');
        // Ao selecionar uma rodada, exibe sempre a pergunta do usuário na Col 3
        // (comportamento padrão). O usuário pode alternar para raciocínio/ferramentas
        // pelos ícones, e a próxima rodada selecionada volta para a pergunta.
        showQuestionPanel(group);
        filesListContainer.innerHTML = '';
        if ((group.files || []).length === 0) {
            filesListContainer.innerHTML = '<div class="panel-empty">Nenhum arquivo modificado neste turno.</div>';
        }
        (group.files || []).forEach(fileData => adicionarFileNaLista(fileData));
    }

    function updateDeleteBar() {
        const total = selectedSessionFiles.size + selectedTurnIds.size;
        if (logDeleteBar) logDeleteBar.classList.toggle('hidden', total === 0);
        if (lblDeleteCount) lblDeleteCount.textContent = `${total} selecionado(s)`;
    }

    function clearDeleteSelection() {
        selectedSessionFiles.clear();
        selectedTurnIds.clear();
        document.querySelectorAll('.log-delete-selected').forEach(el => el.classList.remove('log-delete-selected'));
        updateDeleteBar();
    }

    function closeConfirmDeletePopup() {
        confirmDeletePopup.classList.remove('opacity-100', 'pointer-events-auto');
        confirmDeletePopup.classList.add('opacity-0', 'pointer-events-none');
        confirmDeleteContent.classList.remove('scale-100');
        confirmDeleteContent.classList.add('scale-95');
    }

    async function performDeleteLogs() {
        const files = Array.from(selectedSessionFiles);
        const turnIds = Array.from(selectedTurnIds);
        if (!files.length && !turnIds.length) return;

        try {
            const resp = await fetch('http://127.0.0.1:5000/api/session_log/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files, turn_ids: turnIds })
            });
            await resp.json();

            // Remove os cards (turnos) do DOM e da memória da sessão atual.
            if (turnIds.length) {
                const ids = new Set(turnIds);
                window.sessionLogsData = (window.sessionLogsData || []).filter(g => {
                    if (ids.has(g.id)) {
                        if (g.domElement) g.domElement.remove();
                        return false;
                    }
                    return true;
                });
                currentTurnLogs = currentTurnLogs.filter(g => !ids.has(g.id));
                if (window.currentGroupBalloon && ids.has(window.currentGroupBalloon.id)) {
                    window.currentGroupBalloon = null;
                }
            }

            // Recarrega o cache do histórico e, se estiver na aba, re-renderiza.
            sessionHistoryLoaded = false;
            await fetchSessionHistoryData();
            if (isShowingSessionHistory) {
                renderHistoryCards();
            }

            clearDeleteSelection();
        } catch (e) {
            console.error('Erro ao excluir logs:', e);
        }
    }

    // Cria o card (balão) de um grupo de log e liga o clique que abre a Col 2
    // com os arquivos/diffs. Reutilizado tanto na sessão atual quanto no histórico.
    function createLogGroupCard(group) {
        const card = document.createElement('div');
        const timeSpan = document.createElement('span');
        const titleSpan = document.createElement('span');
        const spinner = document.createElement('span');
        card.className = 'log-card relative flex flex-col gap-1 w-full text-left px-3.5 py-2.5 rounded-[10px] cursor-pointer text-sm';
        timeSpan.className = 'text-[13px] font-semibold text-[#ddd] leading-tight';
        titleSpan.className = 'text-[11px] text-[#888] truncate leading-tight pr-6';
        spinner.className = 'hidden logs-spinner absolute top-2.5 right-3';
        spinner.title = 'Editando...';
        card.appendChild(timeSpan);
        card.appendChild(titleSpan);
        card.appendChild(spinner);

        card.addEventListener('click', (e) => {
            if (e.ctrlKey || e.metaKey) {
                e.stopPropagation();
                if (selectedTurnIds.has(group.id)) {
                    selectedTurnIds.delete(group.id);
                    card.classList.remove('log-delete-selected');
                } else {
                    selectedTurnIds.add(group.id);
                    card.classList.add('log-delete-selected');
                }
                updateDeleteBar();
                return;
            }
            document.querySelectorAll('.log-card').forEach(el => el.classList.remove('log-card-active'));
            card.classList.add('log-card-active');
            openFilesPanel(group);
        });

        group.domElement = card;
        group.timeSpan = timeSpan;
        group.titleSpan = titleSpan;
        group.spinner = spinner;
        return card;
    }

    function serializeGroup(g) {
        const label = (g.files && g.files.length)
            ? g.files.map(f => f.name).join(', ')
            : (g.titleSpan ? g.titleSpan.textContent.replace(/^\s*\[[^\]]*\]\s*/, '').trim() : '');
        return {
            id: g.id,
            timestamp: g.timestamp,
            title: label,
            name: g.name || '',
            tools: g.tools || [],
            thoughts: g.thoughts || [],
            questions: g.questions || [],
            files: (g.files || []).map(f => ({
                name: f.name,
                diffs: (f.diffElements || []).map(el => el._data || null).filter(Boolean)
            }))
        };
    }

    async function saveCurrentTurnSession() {
        if (!currentTurnLogs.length) return;
        const payload = {
            summary: currentTurnSummary || '',
            logs: currentTurnLogs.map(serializeGroup)
        };
        try {
            await fetch('http://127.0.0.1:5000/api/session_log/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            console.error('Erro ao salvar log da sessão:', e);
        }
    }

    function rebuildGroupFromSaved(saved) {
        return {
            id: saved.id,
            timestamp: saved.timestamp,
            title: saved.title || '',
            name: saved.name || '',
            tools: saved.tools || [],
            thoughts: saved.thoughts || [],
            questions: saved.questions || [],
            files: (saved.files || []).map(f => ({
                name: f.name,
                diffElements: (f.diffs || []).map(d => createChildBalloon(
                    d.title, d.htmlContent, d.snippetHtml, d.rawTextOld, d.rawTextNew, d.fileName
                ))
            }))
        };
    }

    async function toggleSessionHistory() {
        const isOpen = slidingPanelContainer.classList.contains('translate-x-0');
        if (!isOpen) {
            // Abre o painel. Se já estava no histórico (conteúdo preservado), só reabre.
            slidingPanelContainer.classList.remove('-translate-x-full');
            slidingPanelContainer.classList.add('translate-x-0');
            if (isShowingSessionHistory) {
                syncMenuIcons();
                return;
            }
        } else if (isShowingSessionHistory) {
            // Painel já aberto no histórico: fecha o painel.
            slidingPanelContainer.classList.remove('translate-x-0');
            slidingPanelContainer.classList.add('-translate-x-full');
            syncMenuIcons();
            return;
        }

        // Aqui: painel aberto e estamos na aba de logs da sessão -> mostra o histórico.
        isShowingSessionHistory = true;
        clearDeleteSelection();
        if (panelTitle) panelTitle.textContent = 'Histórico';
        if (btnHistorySearch) btnHistorySearch.classList.remove('hidden');
        syncMenuIcons();

        if (sessionHistoryLoaded) {
            // Renderiza instantaneamente a partir do cache, sem placeholder.
            // (renderHistoryCards já faz o fadeSwapLogs para exibir o histórico.)
            renderHistoryCards();
        } else {
            if (historyLogsWrapper) {
                historyLogsWrapper.innerHTML = '<div class="p-4 text-sm text-gray-500 font-mono">Carregando histórico...</div>';
            }
            fadeSwapLogs(false);
            await loadSessionHistoryList();
        }
    }

    async function fetchSessionHistoryData() {
        const resp = await fetch('http://127.0.0.1:5000/api/session_history');
        const data = await resp.json();
        sessionHistoryList = data.sessions || [];
        sessionDetailCache = {};
        sessionHistoryLoaded = true;
    }

    async function loadSessionHistoryList({ silent = false } = {}) {
        try {
            await fetchSessionHistoryData();
            renderHistoryCards();
            prefetchSessionDetails();
        } catch (e) {
            console.error('Erro ao carregar histórico:', e);
            if (!silent && historyLogsWrapper) {
                historyLogsWrapper.innerHTML = '<div class="p-4 text-sm text-red-400 font-mono">Erro ao carregar histórico.</div>';
                fadeSwapLogs(false);
            }
        }
    }

    function renderHistoryCards() {
        if (historyLogsWrapper) {
            historyLogsWrapper.innerHTML = '';
        }
        fadeSwapLogs(false);

        if (sessionHistoryList.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'p-4 text-sm text-gray-500 font-mono';
            empty.textContent = 'Nenhuma sessão anterior encontrada.';
            historyLogsWrapper.appendChild(empty);
            return;
        }

        // Agrupa as sessões por dia (DD/MM/AAAA extraído de datetime).
        const sessoesPorDia = new Map();
        sessionHistoryList.forEach(sessao => {
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            if (!sessoesPorDia.has(dia)) sessoesPorDia.set(dia, []);
            sessoesPorDia.get(dia).push(sessao);
        });

        // Ordena os dias do mais recente para o mais antigo (pela sessão mais recente do dia).
        const dias = Array.from(sessoesPorDia.keys()).sort((a, b) => {
            const ta = Math.max(...sessoesPorDia.get(a).map(s => s.timestamp || 0));
            const tb = Math.max(...sessoesPorDia.get(b).map(s => s.timestamp || 0));
            return tb - ta;
        });

        // Mantém apenas os 3 dias mais recentes (substitui os mais antigos).
        dias.slice(0, 3).forEach(dia => {
            const sessoes = sessoesPorDia.get(dia);
            const card = document.createElement('div');
            card.className = 'session-history-card overflow-hidden';
            card.dataset.dia = dia;

            const header = document.createElement('div');
            header.className = 'session-history-header relative flex flex-col gap-1 w-full text-left px-3.5 py-2.5 cursor-pointer';

            const temSessaoAtual = sessoes.some(s => s.current);
            const subtitulo = temSessaoAtual
                ? '<span class="block text-[11px] font-semibold text-[rgb(180,200,40)] leading-tight pr-6">Em curso</span>'
                : '';

            header.innerHTML = `
                <span class="block text-[13px] font-semibold text-[#ddd] leading-tight pr-6">${escapeHtml(dia)}</span>
                ${subtitulo}
                <span class="session-history-toggle-icon absolute top-2.5 right-3 text-gray-500 text-lg font-mono leading-none cursor-pointer hover:text-white transition-colors select-none">+</span>
            `;

            const body = document.createElement('div');
            body.className = 'session-history-body p-2 hidden flex-col gap-2';
            let loaded = false;

            const toggleIcon = header.querySelector('.session-history-toggle-icon');

            function collapseDay() {
                body.classList.add('hidden');
                body.classList.remove('flex');
                header.classList.remove('session-history-active');
                card.classList.remove('session-history-expanded');
                if (toggleIcon) toggleIcon.textContent = '+';
            }

            function expandDay() {
                // Acordeão: recolhe os demais dias expandidos antes de abrir este.
                document.querySelectorAll('.session-history-body').forEach(b => {
                    if (b === body) return;
                    if (!b.classList.contains('hidden')) {
                        b.classList.add('hidden');
                        b.classList.remove('flex');
                        const otherHeader = b.parentElement.querySelector('.session-history-header');
                        if (otherHeader) {
                            otherHeader.classList.remove('session-history-active');
                            otherHeader.parentElement.classList.remove('session-history-expanded');
                        }
                        const otherIcon = b.parentElement.querySelector('.session-history-toggle-icon');
                        if (otherIcon) otherIcon.textContent = '+';
                    }
                });
                body.classList.remove('hidden');
                body.classList.add('flex');
                header.classList.add('session-history-active');
                card.classList.add('session-history-expanded');
                if (toggleIcon) toggleIcon.textContent = '-';
                if (!loaded) {
                    loaded = true;
                    loadDayRoundCards(sessoes, body);
                }
            }

            if (toggleIcon) {
                toggleIcon.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isOpen = !body.classList.contains('hidden');
                    if (isOpen) {
                        collapseDay();
                    } else {
                        expandDay();
                    }
                });
            }

            header.addEventListener('click', (e) => {
                // Ctrl+clique seleciona/deseleciona o dia inteiro para exclusão (sem expandir).
                if (e.ctrlKey || e.metaKey) {
                    e.stopPropagation();
                    const filenames = sessoes.map(s => s.filename);
                    const todosSelecionados = filenames.length > 0 && filenames.every(f => selectedSessionFiles.has(f));
                    filenames.forEach(f => {
                        if (todosSelecionados) {
                            selectedSessionFiles.delete(f);
                        } else {
                            selectedSessionFiles.add(f);
                        }
                    });
                    header.classList.toggle('log-delete-selected', !todosSelecionados);
                    updateDeleteBar();
                    return;
                }

                const isOpen = !body.classList.contains('hidden');
                if (isOpen) {
                    collapseDay();
                } else {
                    expandDay();
                }
            });

            card.appendChild(header);
            card.appendChild(body);
            historyLogsWrapper.appendChild(card);
        });
    }

    async function prefetchSessionDetails() {
        for (const sessao of sessionHistoryList) {
            if (sessionDetailCache[sessao.filename]) continue;
            try {
                const resp = await fetch(`http://127.0.0.1:5000/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
                const data = await resp.json();
                if (!data.error) {
                    sessionDetailCache[sessao.filename] = data.logs || [];
                }
            } catch (e) {
                console.error('Erro ao pré-carregar rodadas da sessão:', e);
            }
        }
    }

    let historyPreloadTimer = null;
    function preloadSessionHistory() {
        // Se o cache já está pronto, não há o que pré-carregar.
        if (sessionHistoryLoaded) return;

        fetchSessionHistoryData()
            .then(() => {
                prefetchSessionDetails();
            })
            .catch(() => {
                // Flask pode ainda estar subindo (ex.: app aberto antes do servidor,
                // ou após um restart): agenda nova tentativa em segundo plano para a
                // aba abrir instantaneamente assim que o servidor responder.
                if (historyPreloadTimer) return;
                historyPreloadTimer = setTimeout(() => {
                    historyPreloadTimer = null;
                    preloadSessionHistory();
                }, 2000);
            });
    }

    function renderDayRoundCards(savedLogs, body) {
        if (!savedLogs || savedLogs.length === 0) {
            body.innerHTML = '<div class="p-3 text-xs text-gray-500 font-mono">Nenhuma rodada de edição neste dia.</div>';
            return;
        }

        const groups = savedLogs.map(saved => rebuildGroupFromSaved(saved));

        // Nomeia as tarefas em ordem cronológica (mais antiga = "Tarefa 1").
        // Nomes personalizados (group.name) são preservados e têm prioridade.
        const ordemCronologica = [...groups].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
        ordemCronologica.forEach((g, idx) => {
            g.displayName = g.name || ('Tarefa ' + (idx + 1));
        });

        // Exibe da rodada mais recente para a mais antiga (ordem decrescente).
        groups.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

        body.innerHTML = '';
        groups.forEach(group => body.appendChild(createHistoryRoundCard(group)));
    }

    async function loadDayRoundCards(sessoes, body) {
        const savedLogs = [];
        let precisaBuscar = false;
        sessoes.forEach(sessao => {
            const cached = sessionDetailCache[sessao.filename];
            if (cached !== undefined) {
                savedLogs.push(...cached);
            } else {
                precisaBuscar = true;
            }
        });

        if (!precisaBuscar) {
            renderDayRoundCards(savedLogs, body);
            return;
        }

        body.innerHTML = '<div class="p-3 text-xs text-gray-500 font-mono">Carregando rodadas...</div>';
        try {
            for (const sessao of sessoes) {
                if (sessionDetailCache[sessao.filename] !== undefined) continue;
                const resp = await fetch(`http://127.0.0.1:5000/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
                const data = await resp.json();
                if (data.error) continue;
                const logs = data.logs || [];
                sessionDetailCache[sessao.filename] = logs;
                savedLogs.push(...logs);
            }
        } catch (e) {
            console.error('Erro ao carregar rodadas do dia:', e);
            body.innerHTML = '<div class="p-3 text-xs text-red-400 font-mono">Erro ao carregar rodadas.</div>';
            return;
        }

        renderDayRoundCards(savedLogs, body);
    }

    function createHistoryRoundCard(group) {
        const sub = document.createElement('div');
        sub.className = 'history-round-card relative flex flex-col gap-1 w-full text-left px-3.5 py-2.5 rounded-[10px] cursor-pointer text-sm';

        const filesLabel = (group.files && group.files.length)
            ? group.files.map(f => f.name).join(', ')
            : (group.title || 'Análise concluída');

        const hora = group.timestamp ? escapeHtml(group.timestamp) : '—';
        const nome = escapeHtml(group.displayName || group.name || 'Tarefa');
        sub.innerHTML = `
            <div class="text-[13px] leading-tight">
                <span class="history-round-name font-bold text-[#ddd]">${nome}</span>
                <span class="text-[#888]"> | ${hora}</span>
            </div>
            <div class="text-[11px] text-[#888] truncate leading-tight">${escapeHtml(filesLabel)}</div>
        `;

        sub.dataset.turnId = group.id;
        group.domElement = sub;
        group.nameEl = sub.querySelector('.history-round-name');

        sub.addEventListener('click', () => {
            document.querySelectorAll('.history-round-card').forEach(el => el.classList.remove('history-round-selected'));
            sub.classList.add('history-round-selected');
            openFilesPanel(group);
        });

        return sub;
    }

    // Seleciona a tarefa correspondente na pilha do histórico (se o dia estiver visível).
    // Usado pela busca: ao clicar no título do resultado, a tarefa equivalente na
    // pilha de tarefas do histórico também é destacada.
    function selectHistoryTaskInPile(dia, turnId) {
        if (!dia || !turnId) return;
        const dayCard = Array.from(document.querySelectorAll('.session-history-card')).find(c => c.dataset.dia === dia);
        if (!dayCard) return; // dia não renderizado (ex.: mais antigo que os 3 dias exibidos)

        const header = dayCard.querySelector('.session-history-header');
        const body = dayCard.querySelector('.session-history-body');
        if (!header || !body) return;

        const selectRound = () => {
            const round = Array.from(body.querySelectorAll('.history-round-card')).find(el => el.dataset.turnId === turnId);
            if (!round) return false;
            document.querySelectorAll('.history-round-card').forEach(el => el.classList.remove('history-round-selected'));
            round.classList.add('history-round-selected');
            round.scrollIntoView({ block: 'nearest' });
            return true;
        };

        // Garante que o dia esteja expandido (o expand também carrega as rodadas, se preciso).
        if (body.classList.contains('hidden')) {
            header.click();
        }

        if (selectRound()) return;

        // As rodadas podem estar carregando de forma assíncrona (primeira expansão do dia).
        let tentativas = 0;
        const poll = setInterval(() => {
            if (selectRound() || ++tentativas >= 30) clearInterval(poll);
        }, 100);
    }

    // Abre a Col 3 com um campo de busca no histórico. Pesquisa nas mensagens
    // enviadas pelo usuário (questions) de todas as tarefas de todas as sessões.
    function openHistorySearchPanel() {
        resetCol3State();
        panelCol3.classList.remove('hidden');
        col3Title.textContent = 'Buscar nas Conversas';
        col3Title.onclick = null;
        col3Title.ondblclick = null;
        col3Title.title = '';
        col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[rgb(144,160,21)]');
        col3Title.classList.add('text-gray-200');

        codeViewContainer.style.display = 'flex';
        codeViewContainer.style.flexDirection = 'column';

        codeViewContainer.innerHTML = `
            <div class="flex-1 min-h-0 flex flex-col gap-3 font-sans whitespace-normal">
                <div class="relative shrink-0">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35M17 11a6 6 0 11-12 0 6 6 0 0112 0z" />
                    </svg>
                    <input id="history-search-input" type="text" placeholder="O que está procurando?"
                        class="w-full bg-[#121212] rounded-2xl pl-9 pr-3 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none transition-colors">
                </div>
                <div id="history-search-results" class="flex-1 min-h-0 overflow-y-auto flex flex-col gap-2 pr-1"></div>
            </div>
        `;

        const input = document.getElementById('history-search-input');
        const results = document.getElementById('history-search-results');
        if (input) input.focus();

        let searchTimer = null;
        if (input) {
            input.addEventListener('input', () => {
                clearTimeout(searchTimer);
                const termo = input.value.trim();
                if (!termo) {
                    results.innerHTML = '<div class="text-xs text-gray-500 italic">Digite para buscar nas mensagens enviadas.</div>';
                    return;
                }
                searchTimer = setTimeout(() => performHistorySearch(termo, results), 200);
            });
        }
    }

    async function performHistorySearch(termo, resultsContainer) {
        resultsContainer.innerHTML = '<div class="text-xs text-gray-500 italic">Buscando...</div>';
        const termoLower = termo.toLowerCase();

        try {
            // Garante que todos os detalhes de sessão estejam carregados.
            for (const sessao of sessionHistoryList) {
                if (sessionDetailCache[sessao.filename] !== undefined) continue;
                const resp = await fetch(`http://127.0.0.1:5000/api/session_detail?file=${encodeURIComponent(sessao.filename)}`);
                const data = await resp.json();
                if (data.error) continue;
                sessionDetailCache[sessao.filename] = data.logs || [];
            }
        } catch (e) {
            console.error('Erro ao carregar detalhes para busca:', e);
            resultsContainer.innerHTML = '<div class="text-xs text-red-400 italic">Erro ao carregar histórico para busca.</div>';
            return;
        }

        // Nomeia as tarefas em ordem cronológica POR DIA (mesma regra usada no
        // histórico). Antes a numeração era por sessão: quando havia várias sessões
        // no mesmo dia, a busca mostrava "Tarefa 2" para um log que no histórico
        // aparecia como "Tarefa 4", fazendo parecer que a tarefa errada tinha sido
        // selecionada na pilha (a seleção por id já estava correta, mas o rótulo não).
        const logsPorDia = new Map();
        for (const sessao of sessionHistoryList) {
            const logs = sessionDetailCache[sessao.filename] || [];
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';
            if (!logsPorDia.has(dia)) logsPorDia.set(dia, []);
            logsPorDia.get(dia).push(...logs);
        }
        logsPorDia.forEach((logs) => {
            const ordemCronologica = [...logs].sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
            ordemCronologica.forEach((saved, idx) => {
                saved.displayName = saved.name || ('Tarefa ' + (idx + 1));
            });
        });

        const resultados = [];
        for (const sessao of sessionHistoryList) {
            const logs = sessionDetailCache[sessao.filename] || [];
            const dia = (sessao.datetime || '').split(' ')[0] || 'Data desconhecida';

            logs.forEach(saved => {
                const questoes = saved.questions || [];
                for (const q of questoes) {
                    if (String(q).toLowerCase().includes(termoLower)) {
                        resultados.push({
                            nome: saved.displayName || saved.name || 'Tarefa',
                            dia,
                            hora: saved.timestamp || '',
                            pergunta: q,
                            saved
                        });
                        break; // uma entrada por tarefa é suficiente
                    }
                }
            });
        }

        if (resultados.length === 0) {
            resultsContainer.innerHTML = '<div class="text-xs text-gray-500 italic">Nenhuma mensagem encontrada com esse termo.</div>';
            return;
        }

        resultsContainer.innerHTML = '';
        resultados.forEach((r, i) => {
            if (i > 0) {
                const sep = document.createElement('div');
                sep.className = 'border-t border-[#333] my-1';
                resultsContainer.appendChild(sep);
            }
            resultsContainer.appendChild(createHistorySearchResultCard(r, termoLower));
        });
    }

    function createHistorySearchResultCard(r, termoLower) {
        const card = document.createElement('div');
        card.className = 'flex flex-col gap-1 py-1';

        const nome = document.createElement('div');
        nome.className = 'text-[13px] font-bold text-[#ddd] leading-tight cursor-pointer hover:text-[rgb(144,160,21)] hover:underline transition-colors';
        nome.textContent = r.nome;
        nome.title = 'Abrir tarefa correspondente';
        nome.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!r.saved) return;
            const group = rebuildGroupFromSaved(r.saved);
            group.displayName = r.nome;
            openFilesPanel(group);
            selectHistoryTaskInPile(r.dia, r.saved.id);
        });

        const meta = document.createElement('div');
        meta.className = 'text-[10px] text-[#666] leading-tight';
        meta.textContent = [r.dia, r.hora].filter(Boolean).join(' | ');

        const trecho = document.createElement('div');
        trecho.className = 'text-[12px] text-[#888] leading-relaxed';
        trecho.innerHTML = buildSearchSnippet(r.pergunta, termoLower);

        card.appendChild(nome);
        if (meta.textContent) card.appendChild(meta);
        card.appendChild(trecho);
        return card;
    }

    // Monta um trecho ao redor da primeira ocorrência do termo, destacando-o.
    function buildSearchSnippet(texto, termoLower) {
        const source = String(texto);
        const idx = source.toLowerCase().indexOf(termoLower);
        const radius = 60;
        let inicio = 0;
        let fim = source.length;
        if (idx > radius) inicio = idx - radius;
        if (idx + termoLower.length + radius < source.length) fim = idx + termoLower.length + radius;

        let snippet = (inicio > 0 ? '…' : '') + source.slice(inicio, fim) + (fim < source.length ? '…' : '');
        const escaped = escapeHtml(snippet);
        const termoEscaped = escapeHtml(termoLower).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return escaped.replace(new RegExp(termoEscaped, 'gi'), (m) => `<span class="text-[rgb(144,160,21)] font-semibold">${m}</span>`);
    }

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

async function sendMessage() {
        if (isGenerating) {
            try {
                await fetch('http://127.0.0.1:5000/api/cancel', { method: 'POST' });
            } catch (e) { console.error(e); }
            return;
        }
        
        let text = inputText.value.trim();
        
        // Filtro final: Nunca envia o código gigante como se fosse mensagem de texto
        if (text.length > 500 && !text.includes(' ')) {
            text = '';
        }

        if (!text && attachedImages.length === 0) return;

        if (!lblFolder.textContent) {
            alertPopup.classList.remove('opacity-0', 'pointer-events-none');
            alertPopup.classList.add('opacity-100', 'pointer-events-auto');
            alertPopupContent.classList.remove('scale-95');
            alertPopupContent.classList.add('scale-100');
            return;
        }

        isGenerating = true;
        currentTurnLogs = [];
        currentTurnSummary = text;
        if (isShowingSessionHistory) {
            isShowingSessionHistory = false;
            renderCurrentSessionLogs();
        }
        if (btnCounselor) {
            btnCounselor.classList.add('opacity-50', 'cursor-not-allowed');
        }
        setStopButton();
        setLogsLoading(true);

        // === CORREÇÃO: Cria a mensagem de texto separada da imagem ===
        // Se houver texto, cria o balão com ele. Se tiver só a imagem, cria com um espaço vazio.
        
        // Adiciona referências das imagens no texto se houver imagens e texto
        let messageText = text;
        
        const msgDiv = addMessage('user', messageText || ' ');
        window.lastUserMessageDiv = msgDiv;
        window.lastUserMessageText = text;
        
        // Anexa as imagens nativamente no DOM para burlar o escapeHtml
        if (attachedImages.length > 0) {
            const imgContainer = document.createElement('div');
            imgContainer.className = 'flex flex-wrap gap-2 mt-3';
            
            attachedImages.forEach(img => {
                const imgWrapper = document.createElement('div');
                imgWrapper.className = 'relative';
                
                const imgNode = document.createElement('img');
                imgNode.src = img.dataUrl;
                imgNode.className = 'max-w-sm max-h-64 rounded-lg border border-[#444] shadow-md cursor-pointer hover:opacity-90 transition-opacity';
                imgNode.onclick = () => window.expandImage(img.dataUrl);
                imgNode.title = img.name; // Tooltip nativo do navegador
                
                imgWrapper.appendChild(imgNode);
                imgContainer.appendChild(imgWrapper);
            });
            
            msgDiv.appendChild(imgContainer);
        }
        // =============================================================
        
        const payload = { message: text, mode: currentMode, use_deepseek: isCounselorMode };
        if (attachedImages.length > 0) {
            payload.images = attachedImages.map(img => ({ base64: img.base64, name: img.name }));
        }

        inputText.value = '';
        inputText.style.height = 'auto';
        attachedImages = [];
        imageCounter = 1;
        renderImagePreviews();
        lblStatus.textContent = 'Processando...';

        try {
            const response = await fetch('http://127.0.0.1:5000/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
            addMessage('system', 'Erro ao conectar com o servidor local.');
            lblStatus.textContent = 'Erro de conexão';
            isGenerating = false;
            if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
            resetSendButton();
            setLogsLoading(false);
        }
    }

    let eventSource = null;

    function startSSE() {
        if (eventSource) {
            eventSource.close();
        }
        
        eventSource = new EventSource('http://127.0.0.1:5000/api/stream');
        
        let currentAIMessageDiv = null;
        let currentGroupBalloon = null;
        let currentGroupFiles = [];
        let currentSessionTools = [];
        let currentSessionThoughts = [];
        let currentSessionQuestions = [];
        let currentGroupTitleSpan = null;
        let currentGroupContentInner = null;

        eventSource.onmessage = async function(event) {
            // Ignora heartbeats SSE (comentários sem data)
            if (!event.data || event.data.trim() === '') return;
            
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return; // ignora payloads inválidos (heartbeats, etc)
            }
                        
        if (data.type === 'status') {
                // Cancela qualquer debounce pendente de limpeza
                if (window._statusClearTimeout) {
                    clearTimeout(window._statusClearTimeout);
                    window._statusClearTimeout = null;
                }
                
                if (data.message === " " || data.message === "") {
                    // DEBOUNCE: só limpa após 400ms sem novo status
                    window._statusClearTimeout = setTimeout(() => {
                        lblStatus.textContent = '';
                        lblExecuting.textContent = '';
                        lblExecuting.classList.remove('animate-pulse');
                        window.lastStatusError = false;
                        window._statusClearTimeout = null;
                    }, 400);
                } else if (data.message) {
                    lblExecuting.textContent = '';
                    lblExecuting.classList.remove('animate-pulse');
                    let text = data.message.replace(/[\r\n]+/g, ' ');
                    const isNavegando = text.startsWith("Navegando: ");
                    const limiteStatus = isNavegando ? 300 : 100;
                    if (text.length > limiteStatus) text = text.substring(0, limiteStatus) + '...';
                    
                    if (text.startsWith("Erro:")) {
                        lblStatus.innerHTML = `<span class="text-red-400 font-bold">${escapeHtml(text)}</span>`;
                        window.lastStatusError = true;
                    } else if (isNavegando) {
                        lblStatus.innerHTML = `Navegando: <span class="text-[rgb(144,160,21)]">${escapeHtml(text.substring(11))}</span>`;
                        window.lastStatusError = false;
                    } else if (text.startsWith("Extraindo informação: ")) {
                        lblStatus.innerHTML = `Extraindo informação: <span class="text-[rgb(144,160,21)]">${escapeHtml(text.substring(22))}</span>`;
                        window.lastStatusError = false;
                    } else {
                        lblStatus.textContent = text;
                        window.lastStatusError = false;
                    }
                } else {
                    if (!window.lastStatusError) {
                        // Mantém o status "Navegando: <urls>" visível durante o raciocínio
                        // pós-busca, em vez de sobrescrevê-lo com "Pensando...".
                        const statusAtual = (lblStatus.textContent || '').trim();
                        if (!statusAtual.startsWith('Navegando:')) {
                            if (lblExecuting.textContent) {
                                lblStatus.textContent = '';
                                lblExecuting.classList.add('animate-pulse');
                            } else {
                                lblStatus.innerHTML =
                                  '<span class="animate-pulse text-[#82c953]">Pensando...</span>';
                            }
                        }
                    }
                }
            } else if (data.type === 'executing') {
                if (!window.lastStatusError) lblStatus.textContent = '';
                lblExecuting.classList.remove('animate-pulse');
                if (data.function) {
                    let text = data.function.replace(/[\r\n]+/g, ' ');
                    if (text.length > 80) text = text.substring(0, 80) + '...';
                    
                    if (text.includes(': ')) {
                        const parts = text.split(': ');
                        lblExecuting.innerHTML = `${escapeHtml(parts[0])}: <span class="text-[rgb(144,160,21)]">${escapeHtml(parts.slice(1).join(': '))}</span>`;
                    } else {
                        lblExecuting.textContent = text;
                    }
                }
                } else if (data.type === 'tool_used' || data.type === 'ai_thought') {
                if (data.type === 'tool_used') currentSessionTools.push({ name: data.name, args: data.args });
                if (data.type === 'ai_thought') currentSessionThoughts.push(data.text);
                
                // 1. Cria o balão de log imediatamente para leitura/pensamento (sem esperar edição)
                if (!currentGroupBalloon) {
                    const timestamp = new Date().toLocaleTimeString('pt-BR');
                    currentGroupBalloon = {
                        id: 'session-' + Date.now(), timestamp: timestamp, files: [],
                        tools: currentSessionTools, thoughts: currentSessionThoughts,
                        questions: currentSessionQuestions
                    };
                    createLogGroupCard(currentGroupBalloon);
                    currentGroupBalloon.timeSpan.textContent = timestamp;
                    currentGroupBalloon.titleSpan.className = 'text-[11px] text-gray-500 truncate leading-tight pr-6 italic';
                    currentGroupBalloon.titleSpan.textContent = 'Analisando...';
                    currentLogsWrapper.insertBefore(currentGroupBalloon.domElement, currentLogsWrapper.firstChild);
                    window.sessionLogsData.push(currentGroupBalloon);
                    currentTurnLogs.push(currentGroupBalloon);
                    window.currentGroupBalloon = currentGroupBalloon;
                    setLogsLoading(isGenerating);
                }
                
                // 2. Atualiza os painéis "Ferramentas" e "Pensamentos" em tempo real (Auto-refresh)
                if (window.currentActiveLogGroup === currentGroupBalloon) {
                    if (isShowingTools) {
                        isShowingTools = false; btnShowTools.click();
                    } else if (isShowingThoughts) {
                        isShowingThoughts = false; btnShowThoughts.click();
                    }
                }

            } else if (data.type === 'tool_sources') {
                // Anexa as URLs visitadas à última ferramenta tool_buscar_web registrada
                for (let i = currentSessionTools.length - 1; i >= 0; i--) {
                    if (currentSessionTools[i].name === 'tool_buscar_web') {
                        currentSessionTools[i].urls = data.urls || [];
                        break;
                    }
                }
                // Se o painel de ferramentas estiver aberto, re-renderiza
                if (isShowingTools) {
                    isShowingTools = false;
                    btnShowTools.click();
                }

            } else if (data.type === 'metrics') {
                
                lblMetrics.textContent = data.message;
            } else if (data.type === 'ai_question') {
                // Registra a pergunta/resposta final da IA no card de log do turno.
                currentSessionQuestions.push(data.text);
                if (currentGroupBalloon) {
                    currentGroupBalloon.questions = currentSessionQuestions;
                }
            } else if (data.type === 'ai_response') {
                if (!currentAIMessageDiv) {
                    currentAIMessageDiv = addMessage('ai', data.message);
                    if (currentGroupBalloon) {
                        currentAIMessageDiv.dataset.logId = currentGroupBalloon.id;
                    }
                } else {
                    // Atualizar mensagem existente (se for streaming de texto)
                    currentAIMessageDiv.innerHTML = formatMessage(data.message, false);
                    currentAIMessageDiv.querySelectorAll('pre code').forEach((block) => {
                        if (typeof hljs !== 'undefined') hljs.highlightElement(block);
                    });
                    attachCodeBlockListeners(currentAIMessageDiv);
                    chatContainerRight.scrollTop = chatContainerRight.scrollHeight;
                }
                if (!window.lastStatusError) lblExecuting.textContent = '';
            } else if (data.type === 'action_diff') {
                // Uma nova edi\u00e7\u00e3o altera as pilhas de undo/redo -> atualiza os bot\u00f5es
                if (typeof atualizarBotoesUndoRedo === 'function') atualizarBotoesUndoRedo();

                const fileName = data.actionName.includes(': ') ? data.actionName.split(': ')[1] : data.actionName;
                
                // Ao come\u00e7ar a editar, o card muda para "Editando..." e o spinner
                // passa a aparecer dentro do card (canto direito), em vez do topo.
                if (!currentGroupBalloon) {
                    const timestamp = new Date().toLocaleTimeString('pt-BR');
                    currentGroupBalloon = {
                        id: 'session-' + Date.now(),
                        timestamp: timestamp,
                        files: [],
                        tools: currentSessionTools,
                        thoughts: currentSessionThoughts,
                        questions: currentSessionQuestions
                    };
                    createLogGroupCard(currentGroupBalloon);
                    currentGroupBalloon.timeSpan.textContent = timestamp;
                    currentGroupBalloon.titleSpan.className = 'text-[11px] text-gray-500 truncate leading-tight pr-6';
                    currentGroupBalloon.titleSpan.textContent = 'Editando...';
                    currentLogsWrapper.insertBefore(currentGroupBalloon.domElement, currentLogsWrapper.firstChild);
                    window.sessionLogsData.push(currentGroupBalloon);
                    currentTurnLogs.push(currentGroupBalloon);
                    window.currentGroupBalloon = currentGroupBalloon;
                    setLogsLoading(isGenerating);
                } else {
                    currentGroupBalloon.timeSpan.textContent = currentGroupBalloon.timestamp;
                    currentGroupBalloon.titleSpan.classList.remove('italic', 'text-gray-400');
                    currentGroupBalloon.titleSpan.textContent = 'Editando...';
                }

                // Spinner dentro do card (canto direito), sem spinner no topo
                if (currentGroupBalloon.spinner) currentGroupBalloon.spinner.classList.remove('hidden');

                if (!currentGroupFiles.includes(fileName)) {
                    currentGroupFiles.push(fileName);
                }

                let fileData = currentGroupBalloon.files.find(f => f.name === fileName);
                let isNewFile = false;
                if (!fileData) {
                    fileData = {
                        name: fileName,
                        diffElements: []
                    };
                    isNewFile = true;
                }

                if (data.diff) {
                    let snippetOriginalText = '';
                    let snippetNewText = '';
                    let originalHtml = '';
                    let newHtml = '';
                    let hasChanges = false;
                    let hasDeletions = false;
                    let hasAdditions = false;

                    data.diff.forEach(part => {
                        if (part.type === 'unmodified') {
                            originalHtml += `<span class="diff-unmodified">${escapeHtml(part.text)}</span>`;
                            newHtml += `<span class="diff-unmodified">${escapeHtml(part.text)}</span>`;
                        } else if (part.type === 'deleted' || part.type === 'modified') {
                            originalHtml += `<span class="diff-deleted">${escapeHtml(part.text)}</span>`;
                            snippetOriginalText += part.text;
                            hasChanges = true;
                            hasDeletions = true;
                        } else if (part.type === 'added') {
                            newHtml += `<span class="diff-added">${escapeHtml(part.text)}</span>`;
                            snippetNewText += part.text;
                            hasChanges = true;
                            hasAdditions = true;
                        }
                    });

                    const snippetOriginalHtml = gerarSnippetHtml(data.diff, 'original');
                    const snippetNewHtml = gerarSnippetHtml(data.diff, 'new');

                    if (hasChanges) {
                        if (hasDeletions && hasAdditions) {
                            const compareHtml = `<div class="diff-two-col"><div class="diff-col"><div class="diff-col-text">${originalHtml}</div></div><div class="diff-col"><div class="diff-col-text">${newHtml}</div></div></div>`;
                            const compareSnippetHtml = `<div class="diff-two-col"><div class="diff-col"><div class="diff-col-text">${snippetOriginalHtml}</div></div><div class="diff-col"><div class="diff-col-text">${snippetNewHtml}</div></div></div>`;
                            fileData.diffElements.push(createChildBalloon('Código Substituído', compareHtml, compareSnippetHtml, snippetOriginalText, snippetNewText, fileName, currentSessionTools));
                        } else if (hasDeletions && !hasAdditions) {
                            fileData.diffElements.push(createChildBalloon('Código Removido', originalHtml, snippetOriginalHtml, snippetOriginalText, null, fileName, currentSessionTools));
                        } else if (!hasDeletions && hasAdditions) {
                            fileData.diffElements.push(createChildBalloon('Código Novo', newHtml, snippetNewHtml, null, snippetNewText, fileName, currentSessionTools));
                        }
                    }
                }
                
                if (isNewFile) {
                    currentGroupBalloon.files.push(fileData);
                }
                logListContainer.scrollTop = 0;

            } else if (data.type === 'cancel') {
                if (window.lastUserMessageDiv) {
                    window.lastUserMessageDiv.remove();
                    window.lastUserMessageDiv = null;
                }
                if (window.lastUserMessageText) {
                    inputText.value = window.lastUserMessageText;
                    inputText.style.height = 'auto';
                    inputText.style.height = (inputText.scrollHeight) + 'px';
                    window.lastUserMessageText = null;
                }
                if (currentGroupBalloon) {
                    currentGroupBalloon.domElement.remove();
                }
                if (currentAIMessageDiv) {
                    currentAIMessageDiv.remove();
                }
                lblStatus.textContent = 'Aguardando instrução';
                lblExecuting.textContent = '';
                lblExecuting.classList.remove('animate-pulse');
                
                currentAIMessageDiv = null;
                currentGroupBalloon = null;
                currentGroupFiles = [];
                currentSessionTools = [];
                currentSessionThoughts = [];
                currentSessionQuestions = [];
                currentTurnLogs = [];
                currentTurnSummary = '';
                
                isGenerating = false;
                if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
                resetSendButton();
                setLogsLoading(false);
                window.currentGroupBalloon = null;
            } else if (data.type === 'done') {
                if (!window.lastStatusError) {
                    lblStatus.textContent = 'Aguardando instrução';
                }
                lblExecuting.textContent = '';
                lblExecuting.classList.remove('animate-pulse');

                // --- NOVA LÓGICA: Finaliza o card conforme o que aconteceu no turno ---
                if (currentGroupBalloon) {
                    currentGroupBalloon.timeSpan.textContent = currentGroupBalloon.timestamp;
                    const finalTitle = currentGroupFiles.length === 0
                        ? (isCounselorMode ? "Análise concluída | Counselor" : "Análise concluída | Coder")
                        : currentGroupFiles.join(', ');
                    currentGroupBalloon.titleSpan.textContent = finalTitle;
                    // Nomes dos arquivos editados em branco; "Análise concluída..." permanece cinza.
                    currentGroupBalloon.titleSpan.className = currentGroupFiles.length === 0
                        ? 'text-[11px] text-[#888] truncate leading-tight pr-6'
                        : 'text-[11px] text-[#ddd] truncate leading-tight pr-6';
                    if (currentGroupBalloon.spinner) currentGroupBalloon.spinner.classList.add('hidden');
                }
                // ----------------------------------------------------------------------

                await saveCurrentTurnSession();
                // Atualiza o cache do histórico em segundo plano (sem re-renderizar a UI),
                // para que a próxima abertura da aba reflita a nova rodada salva
                // (incluindo a possível rotação de dia feita no backend).
                (async () => {
                    try {
                        await fetchSessionHistoryData();
                        prefetchSessionDetails();
                    } catch (e) {
                        console.error('Erro ao atualizar cache do histórico:', e);
                    }
                })();
                currentTurnLogs = [];
                currentTurnSummary = '';

                currentAIMessageDiv = null;
                currentGroupBalloon = null;
                currentGroupFiles = [];
                currentSessionTools = [];
                currentSessionThoughts = [];
                currentSessionQuestions = [];
                
                isGenerating = false;
                if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
                resetSendButton();
                setLogsLoading(false);
                window.currentGroupBalloon = null;
            }
        };

        eventSource.onopen = function() {
            // Conexão SSE (re)estabelecida: garante o cache do histórico
            // populado para a aba abrir instantaneamente após restart do Flask.
            if (sessionHistoryLoaded) {
                fetchSessionHistoryData().then(() => prefetchSessionDetails()).catch(() => {});
            } else {
                preloadSessionHistory();
            }
        };

        eventSource.onerror = function(err) {
            console.error("EventSource failed:", err);
            // Não fechamos a conexão para permitir reconexão automática
            isGenerating = false;
            if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
            resetSendButton();
            setLogsLoading(false);
        };
    }

    // Pré-carrega a lista do histórico em segundo plano (sem tocar na UI),
    // para que a aba abra instantaneamente, sem o placeholder "Carregando histórico...".
    preloadSessionHistory();

    // Iniciar SSE para pegar status inicial
    startSSE();
});