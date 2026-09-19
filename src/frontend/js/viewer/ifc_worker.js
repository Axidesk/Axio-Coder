import { IfcImporter } from '@thatopen/fragments';

const COORDENADAS_PARA_A_ORIGEM = { COORDINATE_TO_ORIGIN: true };

self.onmessage = async (evento) => {
    const pedido = evento.data || {};
    try {
        const importador = new IfcImporter();
        importador.wasm = pedido.wasm;
        importador.webIfcSettings = COORDENADAS_PARA_A_ORIGEM;
        const convertido = await importador.process({
            bytes: pedido.bytes,
            progressCallback: (valor, fase) => {
                self.postMessage({ id: pedido.id, tipo: 'progresso', valor, fase });
            }
        });
        const buffer = convertido.buffer.slice(convertido.byteOffset, convertido.byteOffset + convertido.byteLength);
        self.postMessage({ id: pedido.id, tipo: 'pronto', buffer }, [buffer]);
    } catch (erro) {
        self.postMessage({ id: pedido.id, tipo: 'erro', mensagem: (erro && erro.message) || String(erro) });
    }
};
