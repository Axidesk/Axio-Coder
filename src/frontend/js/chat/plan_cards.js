import { escapeHtml } from './escape.js';

export function createPlanStepCard(step, ativo = false, expandido = true) {
    const card = document.createElement('div');
    card.className = 'plan-card-in bg-[var(--bg-panel)] border border-[var(--border)] rounded-xl overflow-hidden transition-colors duration-300';
    card.dataset.stepId = step.id;

    const header = document.createElement('div');
    header.className = 'px-4 py-3 flex items-center justify-between bg-[var(--bg-panel-2)] cursor-pointer select-none';
    header.onclick = () => {
        const collapsible = card.querySelector('.card-collapsible');
        const chevron = card.querySelector('.step-chevron');
        if (!collapsible) return;
        const aberto = collapsible.classList.toggle('card-collapsible-open');
        chevron.style.transform = aberto ? 'rotate(180deg)' : 'rotate(0deg)';
    };

    const titleWrap = document.createElement('div');
    titleWrap.className = 'flex items-center gap-3';

    const title = document.createElement('h3');
    title.className = 'font-semibold text-[var(--text)] text-sm';
    title.textContent = step.titulo;

    titleWrap.appendChild(title);

    const rightWrap = document.createElement('div');
    rightWrap.className = 'flex items-center gap-2.5';

    const statusIcon = document.createElement('div');
    statusIcon.className = 'step-status-icon flex items-center justify-center w-6 h-6';
    statusIcon.innerHTML = ativo ? _iconSpinner() : _iconAguardando();

    const chevron = document.createElement('div');
    chevron.className = 'step-chevron transition-transform duration-200 text-[var(--text-mutado)]';
    chevron.innerHTML = `<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>`;
    if (expandido) chevron.style.transform = 'rotate(180deg)';

    rightWrap.appendChild(statusIcon);
    rightWrap.appendChild(chevron);

    header.appendChild(titleWrap);
    header.appendChild(rightWrap);

    const collapsible = document.createElement('div');
    collapsible.className = 'card-collapsible' + (expandido ? ' card-collapsible-open' : '');
    const clip = document.createElement('div');
    clip.className = 'card-collapsible-clip';
    const body = document.createElement('div');
    body.className = 'step-body px-4 py-3 border-t border-[var(--border)]';

    const ul = document.createElement('ul');
    ul.className = 'space-y-2';

    (step.tarefas || []).forEach(tarefa => {
        const li = document.createElement('li');
        li.className = 'flex items-start gap-2 text-sm text-[var(--text)] transition-all duration-300';
        li.innerHTML = `
            <svg class="w-4 h-4 text-[var(--text-mutado)] shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <circle cx="12" cy="12" r="4" fill="currentColor"></circle>
            </svg>
            <span>${escapeHtml(tarefa)}</span>
        `;
        ul.appendChild(li);
    });

    body.appendChild(ul);
    clip.appendChild(body);
    collapsible.appendChild(clip);
    card.appendChild(header);
    card.appendChild(collapsible);

    return card;
}

export function _createStackCard(stack) {
    const card = document.createElement('div');
    card.className = 'plan-card-in stack-card bg-[var(--bg-panel)] border border-[var(--border)] rounded-xl overflow-hidden transition-colors duration-300';

    const stackHeader = document.createElement('div');
    stackHeader.className = 'px-4 py-3 flex items-center justify-between bg-[var(--bg-panel-2)] cursor-pointer select-none';
    stackHeader.onclick = () => {
        const collapsible = card.querySelector('.card-collapsible');
        const chevron = card.querySelector('.stack-chevron');
        if (!collapsible) return;
        const aberto = collapsible.classList.toggle('card-collapsible-open');
        chevron.style.transform = aberto ? 'rotate(180deg)' : 'rotate(0deg)';
    };

    const stackTitle = document.createElement('div');
    stackTitle.className = 'flex items-center gap-2';
    stackTitle.innerHTML = `<svg class="w-4 h-4 text-[var(--azul-acao)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>`;
    const stackLabel = document.createElement('span');
    stackLabel.className = 'font-semibold text-[var(--text)] text-xs uppercase tracking-wide';
    stackLabel.textContent = 'Stack';
    stackTitle.appendChild(stackLabel);

    const stackChevron = document.createElement('div');
    stackChevron.className = 'stack-chevron transition-transform duration-200 text-[var(--text-mutado)]';
    stackChevron.innerHTML = `<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>`;

    stackHeader.appendChild(stackTitle);
    stackHeader.appendChild(stackChevron);

    const collapsible = document.createElement('div');
    collapsible.className = 'card-collapsible';
    const clip = document.createElement('div');
    clip.className = 'card-collapsible-clip';
    const content = document.createElement('div');
    content.className = 'stack-content px-4 py-3 space-y-2';

    const campos = [
        { rotulo: 'Tecnologias', valor: stack.stack, tipo: 'texto' },
        { rotulo: 'Estrutura de pastas', valor: stack.estrutura_pastas, tipo: 'arvore' },
        { rotulo: 'Referências', valor: stack.urls_pesquisadas, tipo: 'links' },
    ];
    campos.forEach(({ rotulo, valor, tipo }) => {
        if (!valor) return;
        const bloco = document.createElement('div');
        const lab = document.createElement('div');
        lab.className = 'text-[10px] font-bold text-[var(--text-mutado)] uppercase tracking-wide';
        lab.textContent = rotulo;
        const val = document.createElement('div');
        val.className = 'text-xs text-[var(--text)] leading-relaxed';
        if (tipo === 'arvore') {
            val.className += ' font-mono whitespace-pre';
            const linhasArvore = valor.split('\n').filter(l => l.trim());
            const inds = [...new Set(linhasArvore.map(l => (l.match(/^\s*/) || [''])[0].length))].sort((a, b) => a - b);
            const nivelDe = ind => inds.indexOf(ind);
            const itens = linhasArvore.map(l => ({ n: nivelDe((l.match(/^\s*/) || [''])[0].length), nome: l.trim() }));
            for (let i = 0; i < itens.length; i++) {
                const { n, nome } = itens[i];
                let prefixo = '';
                for (let d = 0; d < n; d++) {
                    let temDepois = false;
                    for (let j = i + 1; j < itens.length; j++) {
                        if (itens[j].n < d) break;
                        if (itens[j].n === d) { temDepois = true; break; }
                    }
                    prefixo += temDepois ? '│  ' : '   ';
                }
                let ehUltimo = true;
                for (let j = i + 1; j < itens.length; j++) {
                    if (itens[j].n < n) break;
                    if (itens[j].n === n) { ehUltimo = false; break; }
                }
                prefixo += ehUltimo ? '└─ ' : '├─ ';
                const row = document.createElement('div');
                row.className = 'flex items-center gap-1.5';
                const ehPasta = nome.endsWith('/') || !/\.[a-z0-9]{1,6}$/i.test(nome);
                row.innerHTML = `<span class="shrink-0 text-[var(--text-mutado)] whitespace-pre">${prefixo}</span><span class="shrink-0">${ehPasta ? '📁' : '📄'}</span><span>${escapeHtml(nome)}</span>`;
                val.appendChild(row);
            }
        } else if (tipo === 'links') {
            val.className += ' space-y-1';
            valor.split(/[;\n]+/).forEach(url => {
                url = url.trim();
                if (!url) return;
                if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
                let nome;
                try { nome = new URL(url).hostname.replace(/^www\./, ''); } catch (e) { nome = url; }
                const a = document.createElement('a');
                a.className = 'block text-[var(--azul-acao)] hover:underline break-all';
                a.href = url;
                a.target = '_blank';
                a.rel = 'noopener';
                a.textContent = nome;
                val.appendChild(a);
            });
        } else {
            val.className += ' space-y-1';
            valor.split('\n').forEach(linha => {
                if (!linha.trim()) return;
                const row = document.createElement('div');
                row.className = 'whitespace-pre-wrap break-words';
                const idx = linha.indexOf(':');
                if (idx > 0 && idx < 24) {
                    row.innerHTML = `<span class="font-bold">${escapeHtml(linha.slice(0, idx + 1))}</span> <span>${escapeHtml(linha.slice(idx + 1).trim())}</span>`;
                } else {
                    row.textContent = linha.trim();
                }
                val.appendChild(row);
            });
        }
        bloco.appendChild(lab);
        bloco.appendChild(val);
        content.appendChild(bloco);
    });

    clip.appendChild(content);
    collapsible.appendChild(clip);
    card.appendChild(stackHeader);
    card.appendChild(collapsible);
    return card;
}

export function _iconSpinner() {
    return `<svg class="w-5 h-5 text-[var(--oliva)] animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;
}

export function _iconAguardando() {
    return `<svg class="w-5 h-5 text-[var(--text-mutado)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="8"></circle></svg>`;
}

export function _iconConcluido() {
    return `<svg class="w-5 h-5 text-[var(--oliva)]" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>`;
}

export function _setStepIcon(card, estado) {
    const iconContainer = card.querySelector('.step-status-icon');
    if (!iconContainer) return;
    if (estado === 'ativo') iconContainer.innerHTML = _iconSpinner();
    else if (estado === 'concluido') iconContainer.innerHTML = _iconConcluido();
    else iconContainer.innerHTML = _iconAguardando();
}

export function _pararPlanoEmCurso(container) {
    if (!container) return 0;
    const icones = Array.from(container.querySelectorAll('.step-status-icon'))
        .filter((icone) => icone.querySelector('.animate-spin'));
    icones.forEach((icone) => { icone.innerHTML = _iconAguardando(); });
    return icones.length;
}

export function _collapseStep(card) {
    const collapsible = card.querySelector('.card-collapsible');
    const chevron = card.querySelector('.step-chevron');
    if (collapsible) collapsible.classList.remove('card-collapsible-open');
    if (chevron) chevron.style.transform = 'rotate(0deg)';
}

const _statusFilePrefixes = [
    'Mapeando', 'Lendo arquivo', 'Lendo trecho', 'Lendo assinaturas',
    'Substituindo texto', 'Salvando Arquivo', 'Excluindo',
    'Substituindo tudo em', 'Desfazendo', 'Refazendo', 'Validando sintaxe',
    'Auditando código', 'Auditando similaridade'
];

export function _formatExecutingStatus(text) {
    const idx = text.indexOf(': ');
    if (idx === -1) return escapeHtml(text);
    const prefixo = text.substring(0, idx);
    const restante = text.substring(idx + 2);
    if (_statusFilePrefixes.includes(prefixo) && restante) {
        return `${escapeHtml(prefixo)}: <span class="status-link" data-path="${escapeHtml(restante)}">${escapeHtml(restante)}</span>`;
    }
    return `${escapeHtml(prefixo)}: <span class="text-[var(--oliva)]">${escapeHtml(restante)}</span>`;
}

export function _resumoNavegacao(texto) {
    if (/^pesquisando /i.test(texto)) return escapeHtml(texto);
    const urls = texto.match(/https?:\/\/[^\s,;]+/g);
    if (!urls) return escapeHtml(texto);
    const vistos = [];
    const partes = [];
    urls.forEach(u => {
        let d;
        try { d = new URL(u).hostname.replace(/^www\./, ''); } catch (e) { d = u; }
        if (vistos.includes(d)) return;
        vistos.push(d);
        partes.push(`<a class="status-link" href="${escapeHtml(u)}" target="_blank" rel="noopener noreferrer">${escapeHtml(d)}</a>`);
    });
    return partes.join(', ');
}

