import * as dom from './dom.js';
import { limparConversa } from './messages.js';

const SELETOR_NATIVO = 'a, pre, code, img, input, textarea, [contenteditable="true"]';

function _menuNativoAssumiu(e, painel) {
    if (e.target.closest && e.target.closest(SELETOR_NATIVO)) return true;
    const selecao = window.getSelection();
    if (!selecao || selecao.isCollapsed) return false;
    return !!painel.contains(selecao.anchorNode);
}

function _abrirMenuConversa(x, y) {
    const menu = dom.chatContextMenu;
    if (!menu) return;
    const haConversa = [dom.chatInnerLeft, dom.chatInnerRight]
        .some(conteudo => conteudo && conteudo.children.length);
    if (dom.btnChatClear) dom.btnChatClear.disabled = !haConversa;
    menu.style.left = Math.max(8, Math.min(x, window.innerWidth - 220)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, window.innerHeight - 70)) + 'px';
    menu.classList.add('menu-open');
}

function _fecharMenuConversa() {
    if (dom.chatContextMenu) dom.chatContextMenu.classList.remove('menu-open');
}

function _ligarPainelDeConversa(painel) {
    if (!painel) return;
    painel.addEventListener('contextmenu', function (e) {
        if (_menuNativoAssumiu(e, painel)) return;
        e.preventDefault();
        _abrirMenuConversa(e.clientX, e.clientY);
    });
}

_ligarPainelDeConversa(dom.chatContainerLeft);
_ligarPainelDeConversa(dom.chatContainerRight);

if (dom.chatContextMenu) {
    dom.chatContextMenu.addEventListener('click', function (e) {
        e.stopPropagation();
        _fecharMenuConversa();
        limparConversa();
    });
}

document.addEventListener('contextmenu', function (e) {
    if (!e.defaultPrevented) _fecharMenuConversa();
});
document.addEventListener('click', _fecharMenuConversa);
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') _fecharMenuConversa();
});
