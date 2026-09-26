import { state } from '../state.js';
import * as dom from '../dom.js';
import { escapeHtml } from '../messages.js';
import { showAlert } from '../ui.js';
import { marcarCheckpoint } from './checkpoint.js';
import { saveCheckpointState } from './estado.js';

const { btnCancelRestore, btnConfirmRestoreYes, lblRestoreMessage, restoreConfirmContent, restoreConfirmPopup } = dom;

    function cancelRestorePreview() {
        if (state.restoreAbortController) {
            state.restoreAbortController.abort();
            state.restoreAbortController = null;
        }
    }
    function openRestorePopup() {
        if (!restoreConfirmPopup) return;
        restoreConfirmPopup.classList.remove('opacity-0', 'pointer-events-none');
        restoreConfirmPopup.classList.add('opacity-100', 'pointer-events-auto');
        restoreConfirmContent.classList.remove('scale-95');
        restoreConfirmContent.classList.add('scale-100');
    }
    function closeRestoreConfirmPopup() {
        if (!restoreConfirmPopup) return;
        cancelRestorePreview();
        restoreConfirmPopup.classList.remove('opacity-100', 'pointer-events-auto');
        restoreConfirmPopup.classList.add('opacity-0', 'pointer-events-none');
        restoreConfirmContent.classList.remove('scale-100');
        restoreConfirmContent.classList.add('scale-95');
    }
    function resetRestoreConfirmButtons() {
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.disabled = false;
            btnConfirmRestoreYes.classList.remove('hidden', 'opacity-50', 'cursor-not-allowed');
        }
        if (btnCancelRestore) {
            btnCancelRestore.textContent = 'Cancelar';
            btnCancelRestore.disabled = false;
            btnCancelRestore.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
    function renderRestoreLoadingMessage(texto) {
        if (lblRestoreMessage) {
            lblRestoreMessage.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:8px 0;">' +
                '<span class="logs-spinner" style="width:24px;height:24px;border-width:3px;"></span>' +
                '<span style="font-weight:700;color:var(--text-inline);">' + escapeHtml(texto) + '</span>' +
                '</div>';
        }
    }
    function showRestorePreviewLoading() {
        renderRestoreLoadingMessage('Carregando...');
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.disabled = true;
            btnConfirmRestoreYes.classList.add('opacity-50', 'cursor-not-allowed');
        }
        if (btnCancelRestore) {
            btnCancelRestore.textContent = 'Cancelar';
            btnCancelRestore.disabled = false;
            btnCancelRestore.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        openRestorePopup();
    }
    function showRestoreLoading() {
        resetRestoreConfirmButtons();
        renderRestoreLoadingMessage('Restaurando...');
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.disabled = true;
            btnConfirmRestoreYes.classList.add('opacity-50', 'cursor-not-allowed');
        }
        if (btnCancelRestore) {
            btnCancelRestore.disabled = true;
            btnCancelRestore.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
    function showRestoreResult(html) {
        if (lblRestoreMessage) lblRestoreMessage.innerHTML = html;
        if (btnConfirmRestoreYes) {
            btnConfirmRestoreYes.classList.add('hidden');
        }
        if (btnCancelRestore) {
            btnCancelRestore.textContent = 'Fechar';
            btnCancelRestore.disabled = false;
            btnCancelRestore.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
    function _quebrasRestauroHtml(quebras, limite) {
        const lista = (quebras || []).slice(0, limite || 12);
        let html = lista.map(q =>
            `• <span style="color:var(--text-claro);">${escapeHtml(q.arquivo)}:${q.linha}</span> importa <b>${escapeHtml(q.simbolo)}</b> de <span style="color:var(--text-claro);">${escapeHtml(q.modulo)}</span> — ${escapeHtml(q.motivo)}`
        ).join('<br>');
        const restantes = (quebras || []).length - lista.length;
        if (restantes > 0) html += `<br>• e mais ${restantes}…`;
        return html;
    }
    function _pontoGravadoHtml(commit) {
        const info = commit || {};
        if (info.status === 'ok') {
            const plural = info.count === 1 ? 'arquivo' : 'arquivos';
            return `<div style="height:10px;"></div><div style="text-align:center;font-size:0.78rem;color:var(--text-mutado);">Ponto gravado: <b style="color:var(--oliva);">${escapeHtml(info.curto || '')}</b> — ${info.count} ${plural}. O envio leva este codigo.</div>`;
        }
        if (info.status === 'error') {
            return `<div style="height:10px;"></div><div style="text-align:center;font-size:0.78rem;color:var(--perigo);">Ponto nao gravado: ${escapeHtml(info.message || '')}</div>`;
        }
        return '';
    }
    async function requestRestoreTask(group) {
        if (!group.__session) {
            showAlert('Não foi possível identificar a sessão desta tarefa para restaurar.');
            return;
        }
        const nome = group.displayName || group.name || 'Tarefa';
        const hora = group.timestamp || '';
        const label = `${nome}${hora ? ' (' + hora + ')' : ''}`;
        state.pendingRestore = { filename: group.__session, round_id: group.id || '', label };
        cancelRestorePreview();
        const abortController = new AbortController();
        state.restoreAbortController = abortController;
        showRestorePreviewLoading();
        let restored = [];
        let kept = [];
        let orphans = [];
        let foraDoAlcance = [];
        let quebras = [];
        let empty = false;
        try {
            const resp = await fetch('/api/session_restore_preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: group.__session, round_id: group.id || '' }),
                signal: abortController.signal
            });
            const data = await resp.json();
            restored = data.restored || [];
            kept = data.kept || [];
            orphans = data.orphans || [];
            foraDoAlcance = data.fora_do_alcance || [];
            quebras = data.quebras || [];
            empty = !!data.empty;
        } catch (e) {
            if (abortController.signal.aborted) {
                state.pendingRestore = null;
                closeRestoreConfirmPopup();
                return;
            }
            console.error('Erro ao carregar prévia da restauração:', e);
            const snapshot = group.snapshot || {};
            restored = Object.keys(snapshot).map(rel => {
                const info = snapshot[rel];
                const removido = info && typeof info === 'object' && info.conteudo === null;
                return removido ? { caminho: rel, acao: 'removido' } : { caminho: rel, acao: 'restaurado' };
            });
        }
        const toRestore = restored.filter(r => r.acao !== 'removido').map(r => r.caminho);
        const toRemoveFromRestored = restored.filter(r => r.acao === 'removido').map(r => r.caminho);
        const allRemoved = [...toRemoveFromRestored, ...orphans];
        const tituloRestaurar = `Restaurar a ${escapeHtml(nome)}`;
        const hasChanges = toRestore.length > 0 || allRemoved.length > 0;
        let msg = `<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--text-inline);">${tituloRestaurar}</div>`;
        if (hora) {
            msg += `<div style="text-align:center;font-size:0.75rem;color:var(--text-mutado);margin-top:2px;">${escapeHtml(hora)}</div>`;
        }
        msg += '<div style="height:14px;"></div>';
        if (toRestore.length) {
            msg += `${countLabelHtml(toRestore.length, 'Arquivo a Restaurar', 'Arquivos a Restaurar')}<br>${toRestore.map(p => '• ' + escapeHtml(p)).join('<br>')}<br><br>`;
        } else if (empty && !allRemoved.length) {
            msg += 'Esta tarefa não possui checkpoint de código salvo (nenhum arquivo foi editado nela).<br><br>';
        } else if (!hasChanges) {
            msg += 'Nenhum arquivo precisa ser alterado.<br><br>';
        }
        if (allRemoved.length) {
            msg += `${countLabelHtml(allRemoved.length, 'Arquivo a Remover', 'Arquivos a Remover')}<br>${allRemoved.map(p => '• ' + escapeHtml(p)).join('<br>')}<br><br>`;
        }
        if (kept.length && hasChanges) {
            msg += `<details class="restore-details"><summary><span>${countLabelHtml(kept.length, 'Arquivo Mantido', 'Arquivos Mantidos')}</span></summary><div class="restore-kept-list">${kept.map(p => '• ' + escapeHtml(p)).join('<br>')}</div></details>`;
        }
        if (foraDoAlcance.length) {
            msg += `<details class="restore-details"><summary><span>${countLabelHtml(foraDoAlcance.length, 'Arquivo Fora do Alcance', 'Arquivos Fora do Alcance')}</span></summary><div class="restore-kept-list">${foraDoAlcance.map(p => '• ' + escapeHtml(p)).join('<br>')}</div></details>`;
        }
        if (quebras.length) {
            msg += `<div style="color:var(--perigo);font-size:0.78rem;line-height:1.5;"><b>Restauração recusada: ${quebras.length} import(s) sem destino.</b><br>${_quebrasRestauroHtml(quebras, 6)}</div><br>`;
        }
        state.restoreAbortController = null;
        if (lblRestoreMessage) lblRestoreMessage.innerHTML = msg;
        resetRestoreConfirmButtons();
        openRestorePopup();
    }
    async function performSessionRestore() {
        if (!state.pendingRestore) return;
        if (state.pendingRestore.tipo === 'git') return performGitRestore();
        const filename = state.pendingRestore.filename;
        const roundId = state.pendingRestore.round_id || '';
        const label = state.pendingRestore.label || '';
        state.pendingRestore = null;
        showRestoreLoading();
        try {
            const resp = await fetch('/api/session_restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, round_id: roundId, label })
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                const agoraEpoch = Date.now();
                if (roundId) {
                    state.restoreEvents.push({ ts: agoraEpoch, checkpoint_id: String(roundId) });
                }
                state.currentCheckpointId = roundId || null;
                state.checkpointRestoredAt = roundId ? agoraEpoch : 0;
                saveCheckpointState();
                document.querySelectorAll('.history-round-card').forEach(el => {
                    marcarCheckpoint(el, el.dataset.turnId);
                });
                const alterados = data.altered || [];
                const criadosRemovidos = alterados.filter(a => (a.acao || '').includes('criado')).length;
                let restMsgHtml = '<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--text-inline);">Restauração concluída</div>';
                restMsgHtml += '<div style="height:12px;"></div>';
                if (data.count > 0) {
                    const linhas = [`${countLabelHtml(data.count, 'Arquivo Alterado', 'Arquivos Alterados')}`];
                    if (criadosRemovidos > 0) linhas.push(`${countLabelHtml(criadosRemovidos, 'Arquivo Criado Removido', 'Arquivos Criados Removidos')}`);
                    restMsgHtml += `<div style="color:var(--text-claro);">${linhas.join('<br>')}</div>`;
                } else {
                    restMsgHtml += '<div style="color:var(--text-claro);">Nenhuma alteração necessária — o código já estava no estado da sessão.</div>';
                }
                restMsgHtml += _pontoGravadoHtml(data.commit);
                showRestoreResult(restMsgHtml);
            } else if (data.status === 'empty') {
                showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--text-inline);">' + (data.message || 'Esta sessão não possui checkpoint de código para restaurar.') + '</div>');
            } else if (data.status === 'blocked') {
                let bloqueadoHtml = '<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--perigo);">Restauração cancelada</div>';
                bloqueadoHtml += '<div style="height:8px;"></div>';
                bloqueadoHtml += '<div style="text-align:center;color:var(--text-claro);">' + escapeHtml(data.message || '') + '</div>';
                if (data.quebras && data.quebras.length) {
                    bloqueadoHtml += '<div style="height:12px;"></div>';
                    bloqueadoHtml += `<div style="font-size:0.78rem;line-height:1.5;">${_quebrasRestauroHtml(data.quebras, 8)}</div>`;
                }
                bloqueadoHtml += '<div style="height:12px;"></div>';
                bloqueadoHtml += '<div style="text-align:center;color:var(--text-mutado);font-size:0.78rem;">Escolha um ponto mais recente do histórico.</div>';
                showRestoreResult(bloqueadoHtml);
            } else {
                showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--perigo);">Erro ao restaurar: ' + (data.message || 'falha desconhecida.') + '</div>');
            }
        } catch (e) {
            console.error('Erro ao restaurar sessão:', e);
            showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--perigo);">Erro ao conectar para restaurar a sessão.</div>');
        }
    }
    async function requestGitRestore(revisao, label, roundId) {
        if (!revisao) return;
        cancelRestorePreview();
        const abortController = new AbortController();
        state.restoreAbortController = abortController;
        showRestorePreviewLoading();
        let restaurar = [];
        let remover = [];
        let quebras = [];
        let vazio = false;
        try {
            const resp = await fetch('/api/git/restauro_preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ revisao }),
                signal: abortController.signal
            });
            const data = await resp.json();
            restaurar = data.restaurar || [];
            remover = data.remover || [];
            quebras = data.quebras || [];
            vazio = !!data.vazio;
        } catch (e) {
            if (abortController.signal.aborted) {
                state.pendingRestore = null;
                closeRestoreConfirmPopup();
                return;
            }
            console.error('Erro ao carregar a previa do restauro:', e);
        }
        state.restoreAbortController = null;
        state.pendingRestore = {
            tipo: 'git',
            revisao,
            round_id: roundId || '',
            restaurar,
            remover,
            label: label || revisao
        };
        const curtoHash = String(revisao).slice(0, 7);
        let msg = `<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--text-inline);">Restaurar a ${escapeHtml(label || curtoHash)}</div>`;
        msg += `<div style="text-align:center;font-size:0.75rem;color:var(--text-mutado);margin-top:2px;">commit ${escapeHtml(curtoHash)}</div>`;
        msg += '<div style="height:14px;"></div>';
        if (restaurar.length) {
            msg += `${countLabelHtml(restaurar.length, 'Arquivo a Restaurar', 'Arquivos a Restaurar')}<br>${restaurar.map(r => '• ' + escapeHtml(r.caminho)).join('<br>')}<br><br>`;
        } else if (!remover.length) {
            msg += 'O codigo ja esta no estado deste commit.<br><br>';
        }
        if (remover.length) {
            msg += `${countLabelHtml(remover.length, 'Arquivo a Remover', 'Arquivos a Remover')}<br>${remover.map(p => '• ' + escapeHtml(p)).join('<br>')}<br><br>`;
        }
        if (quebras.length) {
            msg += `<div style="color:var(--perigo);font-size:0.78rem;line-height:1.5;"><b>Restauracao recusada: ${quebras.length} import(s) sem destino.</b><br>${_quebrasRestauroHtml(quebras, 6)}</div><br>`;
        }
        if (vazio && !quebras.length) {
            showRestoreResult(msg);
            return;
        }
        if (lblRestoreMessage) lblRestoreMessage.innerHTML = msg;
        resetRestoreConfirmButtons();
        openRestorePopup();
    }
    async function performGitRestore() {
        const pendente = state.pendingRestore;
        if (!pendente) return;
        state.pendingRestore = null;
        showRestoreLoading();
        try {
            const resp = await fetch('/api/git/restauro', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    revisao: pendente.revisao,
                    restaurar: pendente.restaurar || [],
                    remover: pendente.remover || [],
                    label: pendente.label || ''
                })
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                const agoraEpoch = Date.now();
                const roundId = pendente.round_id || '';
                if (roundId) {
                    state.restoreEvents.push({ ts: agoraEpoch, checkpoint_id: String(roundId) });
                    state.currentCheckpointId = roundId;
                    state.checkpointRestoredAt = agoraEpoch;
                    saveCheckpointState();
                }
                document.querySelectorAll('.history-round-card').forEach(el => {
                    marcarCheckpoint(el, el.dataset.turnId);
                });
                let restMsgHtml = '<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--text-inline);">Restauracao concluida</div>';
                restMsgHtml += '<div style="height:12px;"></div>';
                if (data.count > 0) {
                    restMsgHtml += `<div style="color:var(--text-claro);">${countLabelHtml(data.count, 'Arquivo Alterado', 'Arquivos Alterados')}</div>`;
                } else {
                    restMsgHtml += '<div style="color:var(--text-claro);">Nenhuma alteração necessária — o código já estava neste commit.</div>';
                }
                restMsgHtml += _pontoGravadoHtml(data.commit);
                showRestoreResult(restMsgHtml);
            } else if (data.status === 'blocked') {
                let bloqueadoHtml = '<div style="text-align:center;font-weight:700;font-size:1rem;color:var(--perigo);">Restauracao cancelada</div>';
                bloqueadoHtml += '<div style="height:8px;"></div>';
                bloqueadoHtml += '<div style="text-align:center;color:var(--text-claro);">' + escapeHtml(data.message || '') + '</div>';
                if (data.quebras && data.quebras.length) {
                    bloqueadoHtml += '<div style="height:12px;"></div>';
                    bloqueadoHtml += `<div style="font-size:0.78rem;line-height:1.5;">${_quebrasRestauroHtml(data.quebras, 8)}</div>`;
                }
                showRestoreResult(bloqueadoHtml);
            } else {
                showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--perigo);">Erro ao restaurar: ' + escapeHtml(data.message || 'falha desconhecida.') + '</div>');
            }
        } catch (e) {
            console.error('Erro ao restaurar pelo git:', e);
            showRestoreResult('<div style="text-align:center;font-weight:700;color:var(--perigo);">Erro ao conectar para restaurar este commit.</div>');
        }
    }
    function countLabelHtml(count, singularLabel, pluralLabel) {
        const label = count === 1 ? singularLabel : pluralLabel;
        const padded = String(count).padStart(2, '0');
        return `<span style="color:var(--oliva);font-weight:700;">${padded}</span> <span style="color:var(--text-inline);">${escapeHtml(label)}</span>`;
    }


export {
    closeRestoreConfirmPopup,
    requestGitRestore,
    requestRestoreTask,
    performSessionRestore
};
