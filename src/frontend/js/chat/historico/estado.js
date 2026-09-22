import { state } from '../state.js';

    async function fetchSessionHistoryData() {
        const resp = await fetch('/api/session_history');
        const data = await resp.json();
        state.sessionHistoryList = data.sessions || [];
        state.sessionDetailCache = {};
        state.porSubirLido = false;
        state.sessionHistoryLoaded = true;
        await fetchCheckpointState();
    }
    async function fetchCheckpointState() {
        try {
            const resp = await fetch('/api/checkpoint_state');
            const data = await resp.json();
            state.currentCheckpointId = data.checkpoint_id || null;
            state.checkpointRestoredAt = data.checkpoint_restored_at || 0;
            state.restoreEvents = (data.restores || []).filter(ev => ev && ev.ts && ev.checkpoint_id);
        } catch (e) {
            console.error('Erro ao carregar estado do checkpoint:', e);
        }
    }
    async function saveCheckpointState() {
        try {
            await fetch('/api/checkpoint_state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ checkpoint_id: state.currentCheckpointId, checkpoint_restored_at: state.checkpointRestoredAt, restores: state.restoreEvents })
            });
        } catch (e) {
            console.error('Erro ao salvar estado do checkpoint:', e);
        }
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
            aiResponse: g.aiResponse || '',
            salvo: !!g.salvo,
            commit: g.commit || (state.commitsDosTurnos || {})[g.id] || '',
            duration: g.duration || 0,
            tools: g.tools || [],
            thoughts: g.thoughts || [],
            questions: g.questions || [],
            files: (g.files || []).map(f => ({
                name: f.name,
                deleted: !!f.deleted,
                diffs: (f.diffElements || []).map(el => el._data || null).filter(Boolean)
            }))
        };
    }
    async function saveCurrentTurnSession() {
        if (!state.currentTurnLogs.length) return {};
        const payload = {
            summary: state.currentTurnSummary || '',
            logs: state.currentTurnLogs.map(serializeGroup)
        };
        try {
            const resp = await fetch('/api/session_log/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            await resp.json();
        } catch (e) {
            console.error('Erro ao salvar log da sessão:', e);
            return {};
        }
    }


export {
    fetchSessionHistoryData,
    saveCheckpointState,
    saveCurrentTurnSession
};
