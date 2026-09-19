import * as XLSX from 'xlsx';
import { extensaoDe } from '../../editor/familia_ficheiro.js';

const LIMITE_LINHAS = 2000;
const LIMITE_COLUNAS = 60;

function tamanhoDaFolha(folha) {
    const referencia = folha && folha['!ref'];
    if (!referencia) return { linhas: 0, colunas: 0 };
    const faixa = XLSX.utils.decode_range(referencia);
    return { linhas: faixa.e.r - faixa.s.r + 1, colunas: faixa.e.c - faixa.s.c + 1 };
}

function tabelaDe(folha) {
    const dimensoes = tamanhoDaFolha(folha);
    const faixa = XLSX.utils.decode_range(folha['!ref']);
    const cortada = dimensoes.linhas > LIMITE_LINHAS || dimensoes.colunas > LIMITE_COLUNAS;
    const limite = cortada
        ? XLSX.utils.encode_range({
            s: faixa.s,
            e: {
                r: Math.min(faixa.e.r, faixa.s.r + LIMITE_LINHAS - 1),
                c: Math.min(faixa.e.c, faixa.s.c + LIMITE_COLUNAS - 1)
            }
        })
        : folha['!ref'];
    const linhas = XLSX.utils.sheet_to_json(folha, { header: 1, blankrows: false, range: limite });
    const tabela = document.createElement('table');
    tabela.className = 'vw-tabela';
    for (const linha of linhas) {
        const tr = document.createElement('tr');
        for (const celula of linha) {
            const td = document.createElement('td');
            td.textContent = celula === undefined || celula === null ? '' : String(celula);
            tr.appendChild(td);
        }
        tabela.appendChild(tr);
    }
    return { tabela, dimensoes, cortada, mostradas: linhas.length };
}

export async function montar(caixa, alvo, ctx) {
    ctx.avisar('a ler a planilha...', 0.1);
    const resposta = await fetch(alvo.url);
    if (!resposta.ok) throw new Error('HTTP ' + resposta.status + ' ao ler a planilha');
    const extensao = extensaoDe(alvo.nome);
    const conteudo = extensao === 'csv' || extensao === 'tsv'
        ? await resposta.text()
        : new Uint8Array(await resposta.arrayBuffer());

    const livro = XLSX.read(conteudo, {
        type: extensao === 'csv' || extensao === 'tsv' ? 'string' : 'array',
        cellDates: true,
        dense: false
    });
    if (!livro.SheetNames.length) throw new Error('a planilha nao tem folhas');

    const barra = document.createElement('div');
    barra.className = 'vw-sheet-abas';
    const rolagem = document.createElement('div');
    rolagem.className = 'vw-rolagem vw-rolagem-clara';
    rolagem.style.position = 'absolute';
    rolagem.style.inset = '0';
    rolagem.style.top = '0';
    rolagem.style.overflow = 'auto';
    caixa.append(rolagem);

    let atual = livro.SheetNames[0];
    const botoes = new Map();

    function desenhar(nome) {
        atual = nome;
        botoes.forEach((botao, chave) => botao.classList.toggle('vw-ativa', chave === nome));
        rolagem.innerHTML = '';
        const { tabela, dimensoes, cortada, mostradas } = tabelaDe(livro.Sheets[nome]);
        rolagem.appendChild(tabela);
        if (cortada) {
            const aviso = document.createElement('p');
            aviso.className = 'vw-dica';
            aviso.textContent = 'Mostrando ' + mostradas + ' de ' + dimensoes.linhas + ' linhas e '
                + Math.min(dimensoes.colunas, LIMITE_COLUNAS) + ' de ' + dimensoes.colunas + ' colunas.';
            rolagem.appendChild(aviso);
        }
    }

    for (const nome of livro.SheetNames) {
        const botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'vw-sheet-aba';
        botao.textContent = nome;
        botao.addEventListener('click', () => desenhar(nome));
        botoes.set(nome, botao);
        barra.appendChild(botao);
    }

    desenhar(atual);
    ctx.concluir();

    return {
        aoAtivar() {
            if (livro.SheetNames.length > 1) ctx.ferramentas.appendChild(barra);
        },
        destruir() {
            botoes.clear();
            rolagem.remove();
        }
    };
}
