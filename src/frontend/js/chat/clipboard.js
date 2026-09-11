import * as dom from './dom.js';

function clipboardNativo() {
    try {
        return require('electron').clipboard;
    } catch (e) {
        return null;
    }
}

export function copiarTexto(texto) {
    const nativo = clipboardNativo();
    if (nativo) {
        try {
            nativo.writeText(String(texto == null ? '' : texto));
            return;
        } catch (e) {}
    }
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(texto).catch(err => {
            console.error('Erro ao copiar via clipboard API:', err);
            fallbackCopiarTexto(texto);
        });
    } else {
        fallbackCopiarTexto(texto);
    }
}

function fallbackCopiarTexto(texto) {
    const textArea = document.createElement("textarea");
    textArea.value = texto;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
    } catch (err) {
        console.error('Fallback de cópia falhou', err);
        if (dom.lblAlertMessage) dom.lblAlertMessage.textContent = 'Não foi possível copiar o texto.';
        if (dom.alertPopup) {
            dom.alertPopup.classList.remove('opacity-0', 'pointer-events-none');
            dom.alertPopup.classList.add('opacity-100', 'pointer-events-auto');
        }
        if (dom.alertPopupContent) {
            dom.alertPopupContent.classList.remove('scale-95');
            dom.alertPopupContent.classList.add('scale-100');
        }
    }
    textArea.remove();
}

export function createCopyButton(textToCopy, colorClass, tooltipText) {
    const btn = document.createElement('button');
    btn.className = `p-1.5 hover:bg-[var(--bg-hover)] rounded transition-colors ${colorClass}`;
    btn.title = tooltipText || 'Copiar';
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
    btn.onclick = (e) => {
        e.stopPropagation();
        copiarTexto(textToCopy);
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        setTimeout(() => { btn.innerHTML = originalHtml; }, 2000);
    };
    return btn;
}
