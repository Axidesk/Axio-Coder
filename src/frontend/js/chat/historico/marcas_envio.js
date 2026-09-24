const CHAVE = 'axio.git.envios';
const LIMITE_MARCAS = 80;

let proximoManual = false;
let cache = null;

    function diaDoCommit(iso) {
        const partes = String(iso || '').slice(0, 10).split('-');
        if (partes.length !== 3) return '';
        return partes[2] + '/' + partes[1] + '/' + partes[0];
    }
    function _lerTudo() {
        if (typeof localStorage === 'undefined') return {};
        try {
            return JSON.parse(localStorage.getItem(CHAVE) || '{}') || {};
        } catch (e) {
            return {};
        }
    }
    function _gravarTudo(tudo) {
        if (typeof localStorage === 'undefined') return;
        try {
            localStorage.setItem(CHAVE, JSON.stringify(tudo));
        } catch (e) {
            console.warn('Nao consegui guardar as marcas de envio:', e);
        }
    }
    function _registo(remoto) {
        const chave = String(remoto || '').trim().toLowerCase();
        if (!chave) return null;
        const tudo = _lerTudo();
        const registo = tudo[chave] || { pendentes: [], marcas: [] };
        registo.pendentes = registo.pendentes || [];
        registo.marcas = registo.marcas || [];
        tudo[chave] = registo;
        return { tudo: tudo, registo: registo };
    }
    function marcarProximoComoManual() {
        proximoManual = true;
    }
    function esquecerIntencaoManual() {
        proximoManual = false;
    }
    function esquecerCache() {
        cache = null;
    }
    function _registarMarca(alvo, hash, dia) {
        if (!hash) return;
        const marcas = alvo.registo.marcas;
        if (marcas.some(m => m.hash === hash)) return;
        marcas.push({ hash: hash, dia: dia || '', tipo: proximoManual ? 'manual' : 'auto' });
        while (marcas.length > LIMITE_MARCAS) marcas.shift();
        proximoManual = false;
    }
    function registarLeitura(remoto, pendentes, truncado) {
        const alvo = _registo(remoto);
        if (!alvo) {
            proximoManual = false;
            return;
        }
        const agora = (pendentes || []).map(c => ({ hash: c.hash, dia: diaDoCommit(c.data) }));
        const antes = alvo.registo.pendentes;
        alvo.registo.pendentes = agora;
        if (!truncado) {
            const idsAgora = new Set(agora.map(p => p.hash));
            const saiu = antes.filter(p => !idsAgora.has(p.hash));
            if (saiu.length) _registarMarca(alvo, saiu[0].hash, saiu[0].dia);
        }
        _gravarTudo(alvo.tudo);
        esquecerCache();
    }
    function semearSeVazio(remoto, hash, dia) {
        const alvo = _registo(remoto);
        if (!alvo || !hash) return;
        if (alvo.registo.marcas.length) return;
        alvo.registo.marcas.push({ hash: hash, dia: dia || '', tipo: 'manual' });
        _gravarTudo(alvo.tudo);
        esquecerCache();
    }
    function marcasDeEnvio() {
        if (cache) return cache;
        const tudo = _lerTudo();
        const porCommit = new Set();
        const porDia = new Set();
        Object.keys(tudo).forEach(chave => {
            ((tudo[chave] || {}).marcas || []).forEach(m => {
                if (m.tipo === 'manual') porCommit.add(m.hash);
                else if (m.dia) porDia.add(m.dia);
            });
        });
        cache = { porCommit: porCommit, porDia: porDia };
        return cache;
    }

export {
    diaDoCommit,
    marcarProximoComoManual,
    esquecerIntencaoManual,
    esquecerCache,
    registarLeitura,
    semearSeVazio,
    marcasDeEnvio
};
