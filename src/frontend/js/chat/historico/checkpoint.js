import { state } from '../state.js';

    function epochDeId(id) {
        if (!id) return 0;
        const m = String(id).match(/(\d+)$/);
        return m ? Number(m[1]) : 0;
    }
    function _intervalosAplicados(epochAlvo, eventos) {
        const anteriores = eventos.filter(ev => ev.ts < epochAlvo);
        if (!anteriores.length) return [[0, epochAlvo]];
        const ultimo = anteriores[anteriores.length - 1];
        const alvoPai = Math.min(epochDeId(ultimo.checkpoint_id), ultimo.ts - 1);
        return _intervalosAplicados(alvoPai, eventos).concat([[ultimo.ts, epochAlvo]]);
    }
    function _intervalosAplicadosHoje() {
        if (!state.currentCheckpointId) return null;
        const eventos = state.restoreEvents || [];
        const base = _intervalosAplicados(epochDeId(state.currentCheckpointId), eventos);
        return state.checkpointRestoredAt
            ? base.concat([[state.checkpointRestoredAt, Number.MAX_SAFE_INTEGER]])
            : base;
    }
    function estadoAplicado(id) {
        const intervalos = _intervalosAplicadosHoje();
        if (!intervalos) return true;
        const e = epochDeId(id);
        return intervalos.some(iv => e > iv[0] && e <= iv[1]);
    }
    function marcarCheckpoint(el, id) {
        if (!id) return;
        if (estadoAplicado(id)) {
            el.classList.remove('history-round-ahead');
            el.removeAttribute('title');
        } else {
            el.classList.add('history-round-ahead');
            el.title = 'Estado posterior ao checkpoint restaurado (não aplicado)';
        }
    }


export {
    epochDeId,
    estadoAplicado,
    marcarCheckpoint
};
