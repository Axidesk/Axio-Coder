
import { escapeHtml } from './escape.js';

export function formatMessage(text, escape = false) {
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
                const displayLang = lang === 'text' ? 'Codigo' : lang;
                const headerHtml = `<div class="flex justify-between items-center px-4 py-2 bg-[var(--bg-hover)] text-xs text-[var(--text-claro)] font-sans border-b border-[var(--border)]"><span class="capitalize">${displayLang}</span><button class="copy-code-btn text-[var(--text-suave)] hover:text-[var(--text-branco)] transition-colors focus:outline-none" title="Copiar código"><svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg></button></div>`;
                parts[i] = `<div class="code-block-container bg-[var(--bg-panel)] rounded-xl overflow-hidden mt-0 mb-1">${headerHtml}<div class="p-4 overflow-x-auto custom-scrollbar"><pre><code class="language-${lang}">${code}</code></pre></div></div>`;
                } else {
                    parts[i] = formatInlineText(parts[i]);
                }
        }
        return parts.join('');
    }
    function isTableSeparator(line) {
        const s = line.trim();
        return s.includes('|') && s.includes('-') && /^[\s|:\-]+$/.test(s);
    }
    function splitTableRow(line) {
        let s = line.trim();
        if (s.startsWith('|')) s = s.slice(1);
        if (s.endsWith('|')) s = s.slice(0, -1);
        return s.split('|').map(c => c.trim());
    }
    function renderTableBlock(block) {
        const lines = block.split('\n').filter(l => l.trim() !== '');
        if (lines.length < 2) return null;
        if (!isTableSeparator(lines[1])) return null;
        const headerCells = splitTableRow(lines[0]);
        if (!headerCells.length) return null;
        const sepCells = splitTableRow(lines[1]);
        const aligns = sepCells.map(c => {
            const t = c.trim();
            if (t.startsWith(':') && t.endsWith(':')) return 'center';
            if (t.endsWith(':')) return 'right';
            if (t.startsWith(':')) return 'left';
            return '';
        });
        let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
        headerCells.forEach((c, i) => {
            const a = aligns[i] ? ` style="text-align:${aligns[i]}"` : '';
            html += `<th${a}>${formatInline(c)}</th>`;
        });
        html += '</tr></thead><tbody>';
        for (let i = 2; i < lines.length; i++) {
            const cells = splitTableRow(lines[i]);
            html += '<tr>';
            for (let j = 0; j < headerCells.length; j++) {
                const a = aligns[j] ? ` style="text-align:${aligns[j]}"` : '';
                html += `<td${a}>${formatInline(cells[j] || '')}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';
        return html;
    }
export function formatInlineText(text) {
        const lines = text.split('\n');
        const out = [];
        let buffer = [];
        let i = 0;
        while (i < lines.length) {
            if (lines[i].includes('|') && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
                if (buffer.length) {
                    out.push(processInlineBlock(buffer.join('\n')));
                    buffer = [];
                }
                let end = i + 2;
                while (end < lines.length && lines[end].includes('|')) end++;
                const block = lines.slice(i, end).join('\n');
                const tableHtml = renderTableBlock(block);
                out.push(tableHtml || formatInline(block).replace(/\n/g, '<br>'));
                i = end;
            } else {
                buffer.push(lines[i]);
                i++;
            }
        }
        if (buffer.length) {
            out.push(processInlineBlock(buffer.join('\n')));
        }
        return out.join('');
    }
    function processInlineBlock(text) {
        const niveis = { 1: 'text-2xl font-bold mt-5 mb-3', 2: 'text-xl font-bold mt-4 mb-2', 3: 'text-lg font-bold mt-4 mb-2', 4: 'text-base font-bold mt-3 mb-1', 5: 'text-sm font-bold mt-3 mb-1', 6: 'text-sm font-bold mt-3 mb-1' };
        const linhas = text.split('\n');
        const out = [];
        let buffer = [];
        let lista = null;
        const flush = () => { if (buffer.length) { out.push(formatInline(buffer.join('\n')).replace(/\n/g, '<br>')); buffer = []; } };
        const fecharLista = () => { if (lista) { out.push(`</${lista}>`); lista = null; } };
        for (const linha of linhas) {
            const h = linha.match(/^(#{1,6})\s+(.*)$/);
            if (h) {
                flush();
                fecharLista();
                const nivel = h[1].length;
                out.push(`<h${nivel} class="${niveis[nivel]}">${formatInline(h[2])}</h${nivel}>`);
                continue;
            }
            const b = linha.match(/^\s*[-*]\s+(.*)$/);
            if (b) {
                flush();
                if (lista !== 'ul') { fecharLista(); out.push('<ul class="list-disc pl-5 my-1 space-y-0.5">'); lista = 'ul'; }
                out.push(`<li>${formatInline(b[1])}</li>`);
                continue;
            }
            const n = linha.match(/^\s*\d+[.)]\s+(.*)$/);
            if (n) {
                flush();
                if (lista !== 'ol') { fecharLista(); out.push('<ol class="list-decimal pl-5 my-1 space-y-0.5">'); lista = 'ol'; }
                out.push(`<li>${formatInline(n[1])}</li>`);
                continue;
            }
            fecharLista();
            buffer.push(linha);
        }
        flush();
        fecharLista();
        return out.join('');
    }
export function formatInline(text) {
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/`([^`]+)`/g, (match, p1) => {
            return `<code class="bg-[var(--bg-chip)] text-[var(--text-code)] px-1.5 py-0.5 rounded text-sm font-mono">${escapeHtml(p1)}</code>`;
        });
        text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" class="text-blue-400 hover:text-blue-300 underline cursor-pointer">$1</a>');
        text = text.replace(/(?<!href="|="|>)(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" class="text-blue-400 hover:text-blue-300 underline cursor-pointer">$1</a>');
        return text;
    }
