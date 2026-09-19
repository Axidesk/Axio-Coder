import { build } from 'esbuild';
import { copyFile, cp, mkdir, stat } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';

const raiz = process.cwd();
const pagina = join(raiz, 'src', 'frontend', 'vendor', 'viewer');
const dist = join(pagina, 'dist');

const ARQUIVOS = [
    ['node_modules/web-ifc/web-ifc.wasm', join(dist, 'web-ifc.wasm')],
    ['node_modules/@thatopen/fragments/dist/Worker/worker.min.mjs', join(dist, 'fragments.worker.js')],
    ['node_modules/pdfjs-dist/build/pdf.worker.min.mjs', join(dist, 'pdf.worker.js')],
    ['node_modules/@aiden0z/pptx-renderer/dist/aiden0z-pptx-renderer.browser.es.js', join(pagina, 'pptx.browser.es.js')]
];

const PASTAS = [
    ['node_modules/pdfjs-dist/cmaps', join(dist, 'cmaps')],
    ['node_modules/pdfjs-dist/standard_fonts', join(dist, 'standard_fonts')]
];

async function copiar() {
    const copiados = [];
    for (const [origem, destino] of ARQUIVOS) {
        await mkdir(dirname(destino), { recursive: true });
        await copyFile(origem, destino);
        copiados.push(destino);
    }
    for (const [origem, destino] of PASTAS) {
        await mkdir(destino, { recursive: true });
        await cp(origem, destino, { recursive: true, force: true });
        copiados.push(destino + '/');
    }
    return copiados;
}

async function empacotar() {
    const resultado = await build({
        entryPoints: [
            join(raiz, 'src/frontend/js/viewer/viewer.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/ifc.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/pdf.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/docx.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/planilha.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/pptx.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/dxf.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/imagem.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/media.js'),
            join(raiz, 'src/frontend/js/viewer/leitores/texto.js')
        ],
        outdir: dist,
        outbase: join(raiz, 'src/frontend/js/viewer'),
        bundle: true,
        format: 'esm',
        target: 'chrome120',
        minify: true,
        sourcemap: false,
        logLevel: 'warning'
    });
    for (const nome of ['dxf_worker', 'ifc_worker']) {
        await build({
            entryPoints: [join(raiz, 'src/frontend/js/viewer', nome + '.js')],
            outfile: join(dist, nome + '.js'),
            bundle: true,
            format: 'iife',
            target: 'chrome120',
            minify: true,
            sourcemap: false,
            logLevel: 'warning'
        });
    }
    return resultado.metafile ? [] : [];
}

const copiados = await copiar();
await empacotar();

const nomes = ['viewer.js', 'leitores/ifc.js', 'leitores/pdf.js', 'leitores/docx.js', 'leitores/planilha.js',
    'leitores/pptx.js', 'leitores/dxf.js', 'leitores/imagem.js', 'leitores/media.js', 'leitores/texto.js',
    'dxf_worker.js', 'ifc_worker.js'];

let total = 0;
const linhas = [];
for (const nome of nomes) {
    const caminho = join(dist, nome);
    const info = await stat(caminho);
    total += info.size;
    linhas.push(`  ${relative(raiz, caminho).replace(/\\/g, '/')}  ${(info.size / 1024).toFixed(0)} KB`);
}
const daPagina = await stat(join(pagina, 'pptx.browser.es.js'));

console.log('Viewer construido.');
console.log(linhas.join('\n'));
console.log(`  src/frontend/vendor/viewer/pptx.browser.es.js  ${(daPagina.size / 1024).toFixed(0)} KB`);
console.log(`Total dos bundles: ${(total / 1024).toFixed(0)} KB`);
console.log(`Assets copiados: ${copiados.length} (wasm, worker dos fragments, worker do pdf, cmaps, fontes, pptx)`);
