import { state } from '../state.js';
import * as dom from '../dom.js';
import { showAlert } from '../ui.js';
import { updateActionButtons } from './acoes.js';
import { renderSalvoCardIfNeeded } from './cards.js';

const { confirmDeleteContent, confirmDeletePopup, lblDeleteMessage } = dom;

    function closeConfirmDeletePopup() {
        confirmDeletePopup.classList.remove('opacity-100', 'pointer-events-auto');
        confirmDeletePopup.classList.add('opacity-0', 'pointer-events-none');
        confirmDeleteContent.classList.remove('scale-100');
        confirmDeleteContent.classList.add('scale-95');
    }
    function requestDeleteSelectedTask(group) {
        if (!group || !group.__session) {
            showAlert('Não foi possível identificar a sessão desta tarefa para excluir.');
            return;
        }
        state.pendingDelete = { filename: group.__session, turn_id: group.id || '' };
        const nome = group.displayName || group.name || 'Tarefa';
        if (lblDeleteMessage) {
            lblDeleteMessage.textContent = `Excluir a tarefa "${nome}"? Esta ação não pode ser desfeita.`;
        }
        confirmDeletePopup.classList.remove('opacity-0', 'pointer-events-none');
        confirmDeletePopup.classList.add('opacity-100', 'pointer-events-auto');
        confirmDeleteContent.classList.remove('scale-95');
        confirmDeleteContent.classList.add('scale-100');
    }
    async function performDeleteSelectedTask() {
        if (!state.pendingDelete) return;
        const { filename, turn_id } = state.pendingDelete;
        state.pendingDelete = null;
        if (!filename || !turn_id) return;
        try {
            const resp = await fetch('/api/session_log/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: [], turn_ids: [], turns: [{ filename, turn_id }] })
            });
            const data = await resp.json();
            const ids = new Set([String(turn_id)]);
            window.sessionLogsData = (window.sessionLogsData || []).filter(g => {
                if (ids.has(String(g.id))) {
                    if (g.domElement) g.domElement.remove();
                    return false;
                }
                return true;
            });
            state.currentTurnLogs = state.currentTurnLogs.filter(g => !ids.has(String(g.id)));
            if (window.currentGroupBalloon && ids.has(String(window.currentGroupBalloon.id))) {
                window.currentGroupBalloon = null;
            }
            if (state.currentSelectedHistoryEl) {
                state.currentSelectedHistoryEl.remove();
            }
            state.currentSelectedHistoryGroup = null;
            state.currentSelectedHistoryEl = null;
            updateActionButtons();
            if (data && data.status === 'ok') {
                if (state.sessionDetailCache[filename]) {
                    state.sessionDetailCache[filename] = state.sessionDetailCache[filename].filter(l => String(l.id) !== String(turn_id));
                }
                renderSalvoCardIfNeeded();
                showAlert('Tarefa excluída.');
            } else {
                showAlert(data && data.message ? data.message : 'Erro ao excluir tarefa.');
            }
        } catch (e) {
            console.error('Erro ao excluir tarefa:', e);
        }
    }


export {
    closeConfirmDeletePopup,
    requestDeleteSelectedTask,
    performDeleteSelectedTask
};
