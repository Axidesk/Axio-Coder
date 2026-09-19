import * as OBC from '@thatopen/components';
import { aoDuploCliqueDoMeio } from '../gestos.js';

const CAMINHO_WASM = '/vendor/viewer/dist/';
const CAMINHO_WORKER = '/vendor/viewer/dist/fragments.worker.js';
const CAMINHO_WORKER_IFC = '/vendor/viewer/dist/ifc_worker.js';
const URL_DO_CONVERTIDO = '/api/modelo_convertido?caminho=';

let motor = null;
let contador = 0;

async function preparar() {
    if (motor) return motor;
    motor = (async () => {
        const componentes = new OBC.Components();
        const fragments = componentes.get(OBC.FragmentsManager);
        fragments.init(CAMINHO_WORKER);
        const carregador = componentes.get(OBC.IfcLoader);
        await carregador.setup({
            autoSetWasm: false,
            wasm: { path: CAMINHO_WASM, absolute: true }
        });
        componentes.init();
        fragments.core.models.materials.list.onItemSet.add(({ value: material }) => {
            if ('isLodMaterial' in material && material.isLodMaterial) return;
            material.polygonOffset = true;
            material.polygonOffsetUnits = 1;
            material.polygonOffsetFactor = Math.random();
        });
        return { componentes, fragments, carregador, mundos: componentes.get(OBC.Worlds) };
    })();
    return motor;
}

async function enquadrar(mundo) {
    if (typeof mundo.camera.fitToItems !== 'function') return;
    try {
        await mundo.camera.fitToItems();
    } catch (erro) {
        console.warn(erro);
    }
}

async function lerFicheiro(url) {
    const resposta = await fetch(url);
    if (!resposta.ok) throw new Error('HTTP ' + resposta.status + ' ao ler o ficheiro');
    return new Uint8Array(await resposta.arrayBuffer());
}

async function pedirConvertido(caminho) {
    if (!caminho) return null;
    try {
        const resposta = await fetch(URL_DO_CONVERTIDO + encodeURIComponent(caminho));
        if (!resposta.ok) return null;
        const dados = await resposta.arrayBuffer();
        return dados.byteLength ? dados : null;
    } catch (erro) {
        console.warn(erro);
        return null;
    }
}

async function guardarConvertido(caminho, conteudo) {
    if (!caminho || !conteudo || !conteudo.byteLength) return;
    try {
        await fetch(URL_DO_CONVERTIDO + encodeURIComponent(caminho), { method: 'POST', body: conteudo });
    } catch (erro) {
        console.warn(erro);
    }
}

let conversor = null;
let pedido = 0;
let fila = Promise.resolve();
const emCurso = new Map();

function workerDeConversao() {
    if (conversor) return conversor;
    conversor = new Worker(CAMINHO_WORKER_IFC);
    conversor.onmessage = (evento) => {
        const resposta = evento.data || {};
        const aberto = emCurso.get(resposta.id);
        if (!aberto) return;
        if (resposta.tipo === 'progresso') {
            aberto.progresso(resposta.valor, resposta.fase);
            return;
        }
        emCurso.delete(resposta.id);
        if (resposta.tipo === 'pronto') {
            aberto.resolver(new Uint8Array(resposta.buffer));
            return;
        }
        aberto.rejeitar(new Error(resposta.mensagem || 'falha na conversao'));
    };
    conversor.onerror = (evento) => {
        for (const [id, aberto] of emCurso) {
            aberto.rejeitar(new Error((evento && evento.message) || 'falha no worker de conversao'));
            emCurso.delete(id);
        }
        conversor.terminate();
        conversor = null;
    };
    return conversor;
}

function converterNoWorker(bytes, progresso) {
    const enviar = () => {
        const id = ++pedido;
        return new Promise((resolver, rejeitar) => {
            emCurso.set(id, { resolver, rejeitar, progresso: progresso || (() => { }) });
            workerDeConversao().postMessage({
                id,
                bytes,
                wasm: { path: CAMINHO_WASM, absolute: true }
            });
        });
    };
    const encadeado = fila.then(enviar, enviar);
    fila = encadeado.catch(() => { });
    return encadeado;
}

async function converterIfc(bytes, identificador, ctx) {
    try {
        const convertido = await converterNoWorker(bytes, (valor) => {
            const fracao = Number(valor) || 0;
            ctx.avisar('a converter o IFC... ' + Math.round(fracao * 100) + '%', 0.05 + fracao * 0.9);
        });
        return { buffer: convertido };
    } catch (erro) {
        console.warn('conversao em segundo plano indisponivel', erro);
    }
    ctx.avisar('a converter o IFC...', 0.05);
    const { carregador } = await preparar();
    const modelo = await carregador.load(bytes, true, identificador, {
        processData: {
            progressCallback: (valor) => {
                const fracao = Number(valor) || 0;
                ctx.avisar('a converter o IFC... ' + Math.round(fracao * 100) + '%', 0.05 + fracao * 0.9);
            }
        }
    });
    return { modelo };
}

export async function montar(caixa, alvo, ctx) {
    const { componentes, fragments: fragmentos, mundos } = await preparar();

    const identificador = alvo.nome.replace(/[^\w.-]+/g, '_') + '-' + (++contador);

    let modelo = null;
    let buffer = null;
    if (/\.frag$/i.test(alvo.nome)) {
        ctx.avisar('a ler o ficheiro...', 0);
        const dados = await lerFicheiro(alvo.url);
        ctx.avisar('a carregar o modelo...', 0.2);
        buffer = dados;
    } else {
        const convertido = await pedirConvertido(alvo.caminho);
        if (convertido) {
            ctx.avisar('a carregar o modelo convertido...', 0.2);
            buffer = convertido;
        } else {
            ctx.avisar('a ler o ficheiro...', 0);
            const dados = await lerFicheiro(alvo.url);
            const resultado = await converterIfc(dados, identificador, ctx);
            if (resultado.modelo) {
                modelo = resultado.modelo;
                guardarConvertido(alvo.caminho, await modelo.getBuffer());
            } else {
                buffer = resultado.buffer;
                guardarConvertido(alvo.caminho, buffer);
            }
        }
    }

    if (!modelo) {
        fragmentos.core.settings.autoCoordinate = true;
        modelo = await fragmentos.core.load(buffer, { modelId: identificador });
    }

    ctx.avisar('a montar a cena...', 0.96);

    const mundo = mundos.create();
    const area = document.createElement('div');
    area.className = 'vw-ifc-palco';
    area.style.position = 'absolute';
    area.style.inset = '0';
    area.style.overflow = 'hidden';
    caixa.appendChild(area);

    mundo.scene = new OBC.SimpleScene(componentes);
    mundo.scene.setup();
    mundo.scene.three.background = null;
    mundo.renderer = new OBC.SimpleRenderer(componentes, area);
    mundo.camera = new OBC.OrthoPerspectiveCamera(componentes);
    componentes.get(OBC.Grids).create(mundo);
    mundo.camera.controls.addEventListener('update', () => fragmentos.core.update());

    modelo.useCamera(mundo.camera.three);
    mundo.scene.three.add(modelo.object);
    fragmentos.core.update(true);
    ctx.concluir();

    await enquadrar(mundo);

    const aoDuploClique = () => enquadrar(mundo);
    area.addEventListener('dblclick', aoDuploClique);
    const largarDuploMeio = aoDuploCliqueDoMeio(area, aoDuploClique);

    let observador = null;
    if (typeof ResizeObserver === 'function') {
        observador = new ResizeObserver(() => {
            try {
                mundo.renderer.resize();
            } catch (erro) {
                console.warn(erro);
            }
        });
        observador.observe(area);
    }

    return {
        aoMostrar() {
            try {
                mundo.renderer.resize();
            } catch (erro) {
                console.warn(erro);
            }
        },
        destruir() {
            area.removeEventListener('dblclick', aoDuploClique);
            largarDuploMeio();
            if (observador) observador.disconnect();
            try {
                mundo.scene.three.remove(modelo.object);
            } catch (erro) {
                console.warn(erro);
            }
            try {
                if (modelo.modelId) fragmentos.core.disposeModel(modelo.modelId);
            } catch (erro) {
                console.warn(erro);
            }
            area.remove();
        }
    };
}
