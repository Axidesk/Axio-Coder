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
                btnCounselor.classList.add('text-blue-400');
            } else {
                btnCounselor.classList.add('text-white');
                btnCounselor.classList.remove('text-blue-400');
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
                    btnModeSelect.classList.add('text-[rgb(144,160,21)]');
                    btnModeSelect.classList.remove('text-white');
                } else {
                    btnModeSelect.classList.remove('text-[rgb(144,160,21)]');
                    btnModeSelect.classList.add('text-white');
                }
            });
        });
    }

    const slidingPanelContainer = document.getElementById('sliding-panel-container');
    const btnClosePanel = document.getElementById('btn-close-panel');
    const logListContainer = document.getElementById('log-list-container');
    
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

    let currentViewingTools = [];
    let currentViewingThoughts = [];
    let isShowingTools = false;
    let isShowingThoughts = false;
    let currentActiveFileBalloonHtml = "";

    function closeCol3() {
        panelCol3.classList.add('hidden');
        isShowingTools = false;
        isShowingThoughts = false;
        currentActiveFileBalloonHtml = "";
        
        if (btnShowTools) {
            btnShowTools.classList.remove('text-[rgb(144,160,21)]');
            btnShowTools.classList.add('text-gray-500');
        }
        if (btnShowThoughts) {
            btnShowThoughts.classList.remove('text-blue-400');
            btnShowThoughts.classList.add('text-gray-500');
        }
        if (btnCopyTools) btnCopyTools.classList.add('hidden');
    }

    if (btnShowThoughts) {
        btnShowThoughts.addEventListener("click", (e) => {
            e.stopPropagation();
            if (isShowingThoughts) {
                closeCol3(); // Se já está aberto, fecha tudo
            } else {
                isShowingThoughts = true;
                isShowingTools = false;
                panelCol3.classList.remove("hidden");
                
                btnShowThoughts.classList.remove("text-gray-500");
                btnShowThoughts.classList.add("text-blue-400");
                
                if (btnShowTools) {
                    btnShowTools.classList.remove("text-[rgb(144,160,21)]");
                    btnShowTools.classList.add("text-gray-500");
                }
                if (btnCopyTools) btnCopyTools.classList.remove("hidden");

                col3Title.textContent = isCounselorMode ? "Raciocínio do Counselor" : "Raciocínio do Coder";
                col3Title.onclick = null;
                col3Title.classList.remove("cursor-pointer", "hover:underline", "text-[rgb(144,160,21)]");
                col3Title.classList.add("text-gray-200");

                let thoughtsHtml = '<div class="p-5 flex flex-col gap-6">';
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
        });
    }

    if (btnShowTools) {
        btnShowTools.addEventListener('click', (e) => {
            e.stopPropagation();
            if (isShowingTools) {
                closeCol3(); // Se já está aberto, fecha tudo
            } else {
                isShowingTools = true;
                isShowingThoughts = false;
                panelCol3.classList.remove('hidden');

                btnShowTools.classList.remove('text-gray-500');
                btnShowTools.classList.add('text-[rgb(144,160,21)]');
                
                if (btnShowThoughts) {
                    btnShowThoughts.classList.remove('text-blue-400');
                    btnShowThoughts.classList.add('text-gray-500');
                }
                if (btnCopyTools) btnCopyTools.classList.remove('hidden');

                col3Title.textContent = 'Ferramentas Usadas';
                col3Title.onclick = null;
                col3Title.classList.remove('cursor-pointer', 'hover:underline', 'text-[rgb(144,160,21)]');
                col3Title.classList.add('text-gray-200');

                let toolsHtml = '<div class="p-4 space-y-4">';
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
                        toolsHtml += `<hr class="border-[#333] mt-3 mb-1 w-1/2">`;
                        toolsHtml += `</div>`;
                    });
                }
                toolsHtml += '</div>';
                codeViewContainer.innerHTML = toolsHtml;
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
            
            if (isShowingThoughts) {
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

    btnOpenLog.addEventListener('click', (e) => {
        e.stopPropagation();
        if (slidingPanelContainer.classList.contains('translate-x-0')) {
            slidingPanelContainer.classList.remove('translate-x-0');
            slidingPanelContainer.classList.add('-translate-x-full');
            panelCol2.classList.add('hidden');
            closeCol3();
        } else {
            slidingPanelContainer.classList.remove('-translate-x-full');
            slidingPanelContainer.classList.add('translate-x-0');
        }
    });

    document.addEventListener('click', (e) => {
        if (slidingPanelContainer.classList.contains('translate-x-0')) {
            if (!slidingPanelContainer.contains(e.target) && !btnOpenLog.contains(e.target)) {
                slidingPanelContainer.classList.remove('translate-x-0');
                slidingPanelContainer.classList.add('-translate-x-full');
                panelCol2.classList.add('hidden');
                closeCol3();
            }
        }
    });

    btnClosePanel.addEventListener('click', () => {
        slidingPanelContainer.classList.remove('translate-x-0');
        slidingPanelContainer.classList.add('-translate-x-full');
        // Hide other columns
        panelCol2.classList.add('hidden');
        closeCol3();
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

    function createChildBalloon(title, htmlContent, rawTextOld, rawTextNew, fileName, sessionTools) {
        const child = document.createElement('div');
        child.className = 'mt-3 bg-[#1e1e1e] rounded-xl overflow-hidden border border-[#333]';
        
        const header = document.createElement('div');
        header.className = 'px-4 py-3 cursor-pointer flex justify-between items-center text-xs text-gray-400 hover:bg-white/5 transition-colors';
        
        const titleContainer = document.createElement('div');
        titleContainer.className = 'flex items-center flex-1';
        titleContainer.innerHTML = `<span class="hover:text-white transition-colors">${title}</span>`;
        
        const actionsContainer = document.createElement('div');
        actionsContainer.className = 'flex items-center gap-2';
        
        const isSubstitution = rawTextOld && rawTextNew;
        
        if (rawTextOld) {
            const color = isSubstitution ? 'text-[#f43f5e]' : 'text-gray-400';
            const tooltip = isSubstitution ? 'Copiar código substituído' : 'Copiar código';
            actionsContainer.appendChild(createCopyButton(rawTextOld, color, tooltip));
        }
        
        if (rawTextNew) {
            const color = isSubstitution ? 'text-[rgb(144,160,21)]' : 'text-gray-400';
            const tooltip = isSubstitution ? 'Copiar código atualizado' : 'Copiar código';
            actionsContainer.appendChild(createCopyButton(rawTextNew, color, tooltip));
        }
        
        header.appendChild(titleContainer);
        header.appendChild(actionsContainer);
        
        header.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Se clicar no mesmo arquivo que já está aberto, ele fecha a coluna 3
            if (!panelCol3.classList.contains('hidden') && 
                window.currentActiveFileBalloonHtml === htmlContent &&
                !isShowingTools && 
                !isShowingThoughts) {
                closeCol3();
                return;
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
                btnShowThoughts.classList.remove('text-blue-400');
                btnShowThoughts.classList.add('text-gray-500');
            }
            if (btnCopyTools) btnCopyTools.classList.add('hidden');

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

            codeViewContainer.innerHTML = htmlContent;
        });
        
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
        if (btnCounselor) {
            btnCounselor.classList.add('opacity-50', 'cursor-not-allowed');
        }
        setStopButton();

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
        let currentGroupTitleSpan = null;
        let currentGroupContentInner = null;

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
                        
        if (data.type === 'status') {
                if (data.message === " ") {
                    lblStatus.textContent = '';
                    lblExecuting.textContent = '';
                    lblExecuting.classList.remove('animate-pulse');
                    window.lastStatusError = false;
                } else if (data.message) {
                    lblExecuting.textContent = '';
                    lblExecuting.classList.remove('animate-pulse');
                    let text = data.message.replace(/[\r\n]+/g, ' ');
                    if (text.length > 100) text = text.substring(0, 100) + '...';
                    
                    if (text.startsWith("Erro:")) {
                        lblStatus.innerHTML = `<span class="text-red-400 font-bold">${escapeHtml(text)}</span>`;
                        window.lastStatusError = true;
                    } else {
                        lblStatus.textContent = text;
                        window.lastStatusError = false;
                    }
                } else {
                    if (!window.lastStatusError) {
                        if (lblExecuting.textContent) {
                            lblStatus.textContent = '';
                            lblExecuting.classList.add('animate-pulse');
                        } else {
                            lblStatus.innerHTML = '<span class="animate-pulse text-[#00ffff]">Axio está raciocinando...</span>';
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
                        domElement: document.createElement('div'), titleSpan: document.createElement('span')
                    };
                    currentGroupBalloon.domElement.className = 'p-3 bg-[#2a2a2a] hover:bg-[#333] rounded cursor-pointer transition-colors border border-[#444] text-sm flex items-center';
                    currentGroupBalloon.titleSpan.className = 'flex-1 truncate text-gray-400 italic';
                    currentGroupBalloon.titleSpan.innerHTML = `<span class="text-xs text-gray-500 mr-2">[${timestamp}]</span> Analisando...`;
                    currentGroupBalloon.tools = currentSessionTools;
                    currentGroupBalloon.thoughts = currentSessionThoughts;
                    currentGroupBalloon.domElement.appendChild(currentGroupBalloon.titleSpan);
                    
                    const balloonRef = currentGroupBalloon;
                    balloonRef.domElement.addEventListener('click', () => {
                        window.currentActiveLogGroup = balloonRef;
                        currentViewingTools = balloonRef.tools || [];
                        currentViewingThoughts = balloonRef.thoughts || [];
                        document.querySelectorAll('#log-list-container > div').forEach(el => el.classList.remove('border-[rgb(144,160,21)]'));
                        balloonRef.domElement.classList.add('border-[rgb(144,160,21)]');
                        panelCol2.classList.remove('hidden'); closeCol3();
                        
                        filesListContainer.innerHTML = '';
                        if (balloonRef.files.length === 0) {
                            filesListContainer.innerHTML = '<div class="p-4 text-sm text-gray-500 font-mono">Nenhum arquivo editado ainda. Analise as ferramentas.</div>';
                        }
                        
                        balloonRef.files.forEach(fileData => {
                            const fileEl = document.createElement('div');
                            fileEl.className = 'bg-[#1e1e1e] rounded-lg border border-white/5 overflow-hidden';
                            const fileHeader = document.createElement('div');
                            fileHeader.className = 'px-4 py-3 bg-white/5 text-sm font-mono text-[rgb(144,160,21)] border-b border-white/5 cursor-pointer hover:bg-white/10 transition-colors flex justify-between items-center';
                            fileHeader.innerHTML = `<span>${fileData.name}</span><span class="text-gray-500 text-lg font-mono leading-none">+</span>`;
                            const fileContent = document.createElement('div');
                            fileContent.className = 'p-2 hidden flex-col gap-2';
                            
                            fileData.diffElements.forEach(diffEl => fileContent.appendChild(diffEl));
                            
                            if (fileData.diffElements.length === 0) fileContent.innerHTML = `<div class="p-2 text-sm text-gray-500 font-mono">Nenhuma alteração de código.</div>`;
                            
                            fileHeader.addEventListener('click', () => {
                                fileContent.classList.toggle('hidden'); fileContent.classList.toggle('flex');
                                const icon = fileHeader.querySelector('span:last-child');
                                icon.textContent = fileContent.classList.contains('hidden') ? '+' : '-';
                            });
                            fileEl.appendChild(fileHeader); fileEl.appendChild(fileContent);
                            filesListContainer.appendChild(fileEl);
                        });
                    });
                    logListContainer.appendChild(currentGroupBalloon.domElement);
                    window.sessionLogsData.push(currentGroupBalloon);
                }
                
                // 2. Atualiza os painéis "Ferramentas" e "Pensamentos" em tempo real (Auto-refresh)
                if (window.currentActiveLogGroup === currentGroupBalloon) {
                    if (isShowingTools) {
                        isShowingTools = false; btnShowTools.click();
                    } else if (isShowingThoughts) {
                        isShowingThoughts = false; btnShowThoughts.click();
                    }
                }

            } else if (data.type === 'metrics') {
                
                lblMetrics.textContent = data.message;
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
                const fileName = data.actionName.includes(': ') ? data.actionName.split(': ')[1] : data.actionName;
                
                if (currentGroupBalloon && currentGroupBalloon.titleSpan.classList.contains('italic')) {
                    currentGroupBalloon.titleSpan.classList.remove('italic', 'text-gray-400');
                }
                
                if (!currentGroupBalloon) {
                    const timestamp = new Date().toLocaleTimeString('pt-BR');
                    
                    currentGroupBalloon = {
                        id: 'session-' + Date.now(),
                        timestamp: timestamp,
                        files: [],
                        domElement: document.createElement('div'),
                        titleSpan: document.createElement('span')
                    };
                    
                    currentGroupBalloon.domElement.className = 'p-3 bg-[#2a2a2a] hover:bg-[#333] rounded cursor-pointer transition-colors border border-[#444] text-sm flex items-center';
                    currentGroupBalloon.titleSpan.className = 'flex-1 truncate';
                    currentGroupBalloon.titleSpan.innerHTML = `<span class="text-xs text-gray-500 mr-2">[${timestamp}]</span> ${fileName}`;
                    
                    currentGroupBalloon.tools = currentSessionTools;
                    currentGroupBalloon.thoughts = currentSessionThoughts;
                    currentGroupBalloon.domElement.appendChild(currentGroupBalloon.titleSpan);
                    
                    const balloonRef = currentGroupBalloon;
                    balloonRef.domElement.addEventListener('click', () => {
                        window.currentActiveLogGroup = balloonRef;
                        currentViewingTools = balloonRef.tools || [];
                        currentViewingThoughts = balloonRef.thoughts || [];
                        // Highlight selected log
                        document.querySelectorAll('#log-list-container > div').forEach(el => el.classList.remove('border-[rgb(144,160,21)]'));
                        balloonRef.domElement.classList.add('border-[rgb(144,160,21)]');
                        
                        // Open Col 2
                        panelCol2.classList.remove('hidden');
                        closeCol3();
                        
                        // Populate Col 2
                        filesListContainer.innerHTML = '';
                        balloonRef.files.forEach(fileData => {
                            const fileEl = document.createElement('div');
                            fileEl.className = 'bg-[#1e1e1e] rounded-lg border border-white/5 overflow-hidden';
                            
                            const fileHeader = document.createElement('div');
                            fileHeader.className = 'px-4 py-3 bg-white/5 text-sm font-mono text-[rgb(144,160,21)] border-b border-white/5 cursor-pointer hover:bg-white/10 transition-colors flex justify-between items-center';
                            fileHeader.innerHTML = `<span>${fileData.name}</span><span class="text-gray-500 text-lg font-mono leading-none">+</span>`;
                            
                            const fileContent = document.createElement('div');
                            fileContent.className = 'p-2 hidden flex-col gap-2';
                            
                            fileData.diffElements.forEach(diffEl => {
                                fileContent.appendChild(diffEl);
                            });
                            
                            if (fileData.diffElements.length === 0) {
                                fileContent.innerHTML = `<div class="p-2 text-sm text-gray-500 font-mono">Nenhuma alteração de código.</div>`;
                            }
                            
                            fileHeader.addEventListener('click', () => {
                                fileContent.classList.toggle('hidden');
                                fileContent.classList.toggle('flex');
                                const icon = fileHeader.querySelector('span:last-child');
                                icon.textContent = fileContent.classList.contains('hidden') ? '+' : '-';
                            });
                            
                            fileEl.appendChild(fileHeader);
                            fileEl.appendChild(fileContent);
                            filesListContainer.appendChild(fileEl);
                        });
                    });
                    
                    logListContainer.appendChild(currentGroupBalloon.domElement);
                    window.sessionLogsData.push(currentGroupBalloon);
                    currentGroupFiles.push(fileName);
                } else {
                    if (!currentGroupFiles.includes(fileName)) {
                        currentGroupFiles.push(fileName);
                        currentGroupBalloon.titleSpan.innerHTML = `<span class="text-xs text-gray-500 mr-2">[${currentGroupBalloon.timestamp}]</span> ${currentGroupFiles.join(', ')}`;
                    }
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
                    let fullOriginalText = '';
                    let fullNewText = '';
                    let originalHtml = '';
                    let newHtml = '';
                    let hasChanges = false;
                    let hasDeletions = false;
                    let hasAdditions = false;

                    data.diff.forEach(part => {
                        if (part.type === 'unmodified') {
                            originalHtml += `<span class="diff-unmodified">${escapeHtml(part.text)}</span>`;
                            newHtml += `<span class="diff-unmodified">${escapeHtml(part.text)}</span>`;
                            fullOriginalText += part.text;
                            fullNewText += part.text;
                        } else if (part.type === 'deleted' || part.type === 'modified') {
                            originalHtml += `<span class="diff-deleted">${escapeHtml(part.text)}</span>`;
                            fullOriginalText += part.text;
                            hasChanges = true;
                            hasDeletions = true;
                        } else if (part.type === 'added') {
                            newHtml += `<span class="diff-added">${escapeHtml(part.text)}</span>`;
                            fullNewText += part.text;
                            hasChanges = true;
                            hasAdditions = true;
                        }
                    });

                    if (hasChanges) {
                        if (hasDeletions && hasAdditions) {
                            const compareHtml = `<div class="flex h-full divide-x divide-white/5"><div class="flex-1 overflow-y-auto pr-4"><div class="whitespace-pre-wrap">${originalHtml}</div></div><div class="flex-1 overflow-y-auto pl-4"><div class="whitespace-pre-wrap">${newHtml}</div></div></div>`;
                            fileData.diffElements.push(createChildBalloon('Código Substituído', compareHtml, fullOriginalText, fullNewText, fileName, currentSessionTools));
                        } else if (hasDeletions && !hasAdditions) {
                            fileData.diffElements.push(createChildBalloon('Código Removido', originalHtml, fullOriginalText, null, fileName, currentSessionTools));
                        } else if (!hasDeletions && hasAdditions) {
                            fileData.diffElements.push(createChildBalloon('Código Novo', newHtml, null, fullNewText, fileName, currentSessionTools));
                        }
                    }
                }
                
                if (isNewFile) {
                    currentGroupBalloon.files.push(fileData);
                }
                logListContainer.scrollTop = logListContainer.scrollHeight;

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
                
                isGenerating = false;
                if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
                resetSendButton();
            } else if (data.type === 'done') {
                if (!window.lastStatusError) {
                    lblStatus.textContent = 'Aguardando instrução';
                }
                lblExecuting.textContent = '';
                lblExecuting.classList.remove('animate-pulse');

                // --- NOVA LÓGICA: Finaliza o card se foi apenas uma análise/leitura ---
                if (currentGroupBalloon && currentGroupFiles.length === 0) {
                    currentGroupBalloon.titleSpan.classList.remove('italic', 'text-gray-400');
                    const analiseTitle = isCounselorMode ? "Análise concluída | Counselor" : "Análise concluída | Coder";
                    currentGroupBalloon.titleSpan.innerHTML = `<span class="text-xs text-gray-500 mr-2">[${currentGroupBalloon.timestamp}]</span> ${analiseTitle}`;
                }
                // ----------------------------------------------------------------------

                currentAIMessageDiv = null;
                currentGroupBalloon = null;
                currentGroupFiles = [];
                currentSessionTools = [];
                currentSessionThoughts = [];
                
                isGenerating = false;
                if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
                resetSendButton();
            }
        };

        eventSource.onerror = function(err) {
            console.error("EventSource failed:", err);
            // Não fechamos a conexão para permitir reconexão automática
            isGenerating = false;
            if (btnCounselor) btnCounselor.classList.remove('opacity-50', 'cursor-not-allowed');
            resetSendButton();
        };
    }

    // Iniciar SSE para pegar status inicial
    startSSE();
});