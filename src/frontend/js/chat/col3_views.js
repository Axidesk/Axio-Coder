import { state } from './state.js';
import { vistaDe } from './colunas.js';
import { setCodeViewContent } from './files.js';
import { escapeHtml } from './escape.js';
import { formatMessage } from './markdown.js';

    function renderThoughts(vista = vistaDe('dock')) {
        let thoughtsHtml = '';
        if (!state.currentViewingThoughts || state.currentViewingThoughts.length === 0) {
            thoughtsHtml = '<div class="text-[var(--text-mutado)] italic">Nenhum raciocínio registrado neste turno.</div>';
        } else {
            thoughtsHtml = '<div class="thought-clamp-wrap"><div class="thought-clamp-body flex flex-col gap-6">';
            state.currentViewingThoughts.forEach(t => {
                t = t.replace(/\\n\\n/g, ' ').replace(/\\n/g, '\n');
                let formattedText = formatMessage(t, true);
                formattedText = formattedText.replace(/^<strong>(.*?)<\/strong>(?:<br>|\s)*/i, '<div class="text-[var(--text-label)] font-bold text-[15px] mb-1">$1</div>');
                thoughtsHtml += `<div class="text-[var(--text-claro)] text-sm leading-relaxed">${formattedText}</div>`;
            });
            thoughtsHtml += '</div>';
            thoughtsHtml += '<button class="thought-toggle hidden text-[var(--oliva)] hover:underline text-sm font-semibold focus:outline-none mt-3">Ver mais</button>';
            thoughtsHtml += '</div>';
        }
        setCodeViewContent(thoughtsHtml, false, vista);
        applyThoughtClamp(vista);
    }
    function applyThoughtClamp(vista = vistaDe('dock')) {
        const container = vista.codigo;
        if (!container) return;
        const body = container.querySelector('.thought-clamp-body');
        const btn = container.querySelector('.thought-toggle');
        if (!body || !btn) return;
        let lineH = 23;
        const sample = body.querySelector('div');
        if (sample) {
            const lh = parseFloat(getComputedStyle(sample).lineHeight);
            if (!isNaN(lh) && lh > 0) lineH = lh;
        }
        const THOUGHT_MAX_H = Math.round(lineH * 30);
        const setClamped = (clamped) => {
            if (clamped) {
                body.classList.add('thought-clamped');
                body.style.maxHeight = THOUGHT_MAX_H + 'px';
                btn.textContent = 'Ver mais';
            } else {
                body.classList.remove('thought-clamped');
                body.style.maxHeight = body.scrollHeight + 'px';
                btn.textContent = 'Ver menos';
            }
            state.thoughtsExpanded = !clamped;
        };
        body.style.maxHeight = '';
        if (body.scrollHeight <= THOUGHT_MAX_H) {
            btn.classList.add('hidden');
            body.classList.remove('thought-clamped');
            state.thoughtsExpanded = false;
            return;
        }
        setClamped(!state.thoughtsExpanded);
        btn.classList.remove('hidden');
        btn.onclick = () => {
            setClamped(!body.classList.contains('thought-clamped'));
        };
    }
    function renderQuestions(vista = vistaDe('dock')) {
        let questionsHtml = '<div class="flex flex-col gap-6">';
        if (!state.currentViewingQuestions || state.currentViewingQuestions.length === 0) {
            questionsHtml += '<div class="text-[var(--text-mutado)] italic">Nenhuma pergunta registrada neste turno.</div>';
        } else {
            state.currentViewingQuestions.forEach((q, idx) => {
                const formattedText = formatMessage(q, true);
                questionsHtml += `<div class="text-[var(--text-claro)] text-sm leading-relaxed">${formattedText}`;
                if (idx === state.currentViewingQuestions.length - 1 && state.currentViewingAiResponse) {
                    const resposta = formatMessage(state.currentViewingAiResponse, true);
                    questionsHtml += `<div class="mt-1 text-left whitespace-normal"><button class="text-[var(--oliva)] hover:underline text-sm font-semibold focus:outline-none ai-answer-toggle">Ver Resposta</button><div class="ai-answer-wrap"><div class="ai-answer-inner"><div class="mt-1 border-t border-[var(--border)] pt-1"><div class="text-[var(--text)] text-sm leading-relaxed">${resposta}</div><button class="mt-1 text-[var(--oliva)] hover:underline text-sm font-semibold focus:outline-none ai-answer-toggle-less">Ver menos</button></div></div></div></div>`;
                }
                questionsHtml += `</div>`;
            });
        }
        questionsHtml += "</div>";

        setCodeViewContent(questionsHtml, false, vista);

        const container = vista.codigo;
        const wrap = container ? container.querySelector('.ai-answer-wrap') : null;
        const btnToggle = container ? container.querySelector('.ai-answer-toggle') : null;
        const btnToggleLess = container ? container.querySelector('.ai-answer-toggle-less') : null;
        
        function setAiAnswerExpanded(expanded) {
            if (!wrap) return;
            if (expanded) {
                if (btnToggle) btnToggle.classList.add('hidden');
                wrap.classList.add('ai-answer-open');
            } else {
                wrap.classList.remove('ai-answer-open');
            }
        }
        if (btnToggle) btnToggle.addEventListener('click', () => setAiAnswerExpanded(true));
        if (btnToggleLess) btnToggleLess.addEventListener('click', () => setAiAnswerExpanded(false));
        if (wrap) wrap.addEventListener('transitionend', (e) => {
            if (e.propertyName === 'grid-template-rows' && !wrap.classList.contains('ai-answer-open')) {
                if (btnToggle) btnToggle.classList.remove('hidden');
            }
        });
    }
    function sortToolArgsKeys(keys) {
        const ordemChaves = ['caminho_relativo', 'linha_inicio', 'linha_fim', 'termo', 'comando', 'texto_antigo', 'texto_novo', 'conteudo'];
        return keys.sort((a, b) => {
            let posA = ordemChaves.indexOf(a);
            let posB = ordemChaves.indexOf(b);
            if (posA === -1) posA = 999;
            if (posB === -1) posB = 999;
            return posA - posB;
        });
    }
    function renderTools(vista = vistaDe('dock')) {
        let toolsHtml = '<div class="space-y-4">';
        if (!state.currentViewingTools || state.currentViewingTools.length === 0) {
            toolsHtml += '<div class="text-[var(--text-mutado)] italic">Nenhuma ferramenta associada a este turno.</div>';
        } else {
            state.currentViewingTools.forEach(t => {
                toolsHtml += `<div class="flex flex-col gap-1.5">`;
                toolsHtml += `<div class="text-[var(--oliva)] font-bold text-sm tracking-wide">FERRAMENTA: ${t.name}</div>`;
                if (t.args && Object.keys(t.args).length > 0) {
                    const chavesOrdenadas = sortToolArgsKeys(Object.keys(t.args));
                    chavesOrdenadas.forEach(key => {
                        let val = t.args[key];
                        let displayVal = val;
                        if (key === 'texto_antigo' || key === 'texto_novo' || key === 'conteudo') {
                            const escapedCode = val.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                            displayVal = `<a href="#" class="text-[var(--oliva)] hover:underline" onclick="const codeEl = this.nextElementSibling; if(codeEl.classList.contains('hidden')){codeEl.classList.remove('hidden'); this.textContent='[Recolher]';}else{codeEl.classList.add('hidden'); this.textContent='[Ver Codigo]';}; return false;">[Ver Codigo]</a><div class="hidden mt-2 p-3 bg-[var(--bg)] rounded font-mono text-xs whitespace-pre-wrap text-[var(--text-claro)] border border-[var(--border)] max-h-64 overflow-y-auto custom-scrollbar">${escapedCode}</div>`;
                        } else if (typeof val === 'string') {
                            displayVal = val.replace(/</g, "&lt;").replace(/>/g, "&gt;");
                        } else {
                            displayVal = JSON.stringify(val);
                        }
                        toolsHtml += `<div class="text-[var(--text-suave)] text-xs font-mono ml-4"><span class="text-[var(--text-mutado)]">-&gt;</span> ${key}: <span class="text-[var(--text-claro)]">${displayVal}</span></div>`;
                    });
                } else {
                    toolsHtml += `<div class="text-[var(--text-suave)] text-xs font-mono ml-4"><span class="text-[var(--text-mutado)]">-&gt;</span> Sem argumentos (Chamada simples)</div>`;
                }
                if (t.urls && t.urls.length > 0) {
                    const urlItems = t.urls.map(url =>
                        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="block text-[var(--oliva)] hover:underline break-all font-mono text-xs py-1" title="${escapeHtml(url)}">${escapeHtml(url)}</a>`
                    ).join('');
                    toolsHtml += `<div class="text-[var(--text-suave)] text-xs font-mono ml-4"><span class="text-[var(--text-mutado)]">-&gt;</span> `;
                    toolsHtml += `<a href="#" class="text-[var(--oliva)] hover:underline" onclick="const box=this.nextElementSibling; if(box.classList.contains('hidden')){box.classList.remove('hidden'); this.textContent='[Recolher fontes]';}else{box.classList.add('hidden'); this.textContent='[Ver ${t.urls.length} fonte(s)]';}; return false;">[Ver ${t.urls.length} fonte(s)]</a>`;
                    toolsHtml += `<div class="hidden mt-2 p-3 bg-[var(--bg)] rounded border border-[var(--border)] max-h-64 overflow-y-auto custom-scrollbar">${urlItems}</div>`;
                    toolsHtml += `</div>`;
                }
                toolsHtml += `<hr class="border-[var(--border)] mt-3 mb-1 w-1/2">`;
                toolsHtml += `</div>`;
            });
        }
        toolsHtml += '</div>';
        setCodeViewContent(toolsHtml, false, vista);
    }

export { renderThoughts, applyThoughtClamp, renderQuestions, renderTools, sortToolArgsKeys };
