"""Corre um trecho de codigo num processo novo, com o ambiente que ele exige.

O nucleo e `_correr_trecho`: escreve o trecho num ficheiro temporario do sistema,
corre-o com timeout que mata a arvore e apaga-o no fim. Os handlers
`tool_executar_python` e `tool_executar_js` sao cascas sobre o mapa `_TRECHOS`,
logo uma correccao no timeout ou no relatorio vale para os dois.

Os textos que se injetam antes do trecho vivem aqui, ao lado de quem os usa: o
cabecalho Python (sys.path com a raiz do Axio e do projeto aberto, cwd, utf-8), o
cabecalho JavaScript (cwd do projeto, `importarProjeto` para resolver um caminho
relativo a partir da pasta do ficheiro temporario) e o DOM falso, que e o maior
deles e o unico que se le como JavaScript.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from src.backend.config import APP_ROOT
from src.backend.services.saida import recortar_texto
from src.backend.state import emit_event, estado
from src.backend.tools.process import id_processo, run_com_timeout
from src.backend.tools.registry import register

_TIMEOUT_TRECHO_MAX = 300
_ARRANQUE = time.time()
_PREFIXO_TEMP_PYTHON = "axio_python_"
_PREFIXO_TEMP_JS = "axio_js_"

_CABECALHO_PYTHON = '''# -*- coding: utf-8 -*-
"""Gerado por tool_executar_python num ficheiro temporario; apagado no fim."""
import os
import sys

for _raiz in ({raiz_app!r}, {raiz_projeto!r}):
    if _raiz and _raiz not in sys.path:
        sys.path.insert(0, _raiz)
if {raiz_projeto!r} and os.path.isdir({raiz_projeto!r}):
    os.chdir({raiz_projeto!r})
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        _fluxo.reconfigure(encoding="utf-8", errors="replace")

# O estado do Axio nasce VAZIO neste processo: 'pasta_raiz' nao esta definido, e
# uma rota que passe por raiz_abs() (services/file_service.py) responde 400
# ("nenhuma pasta aberta") sem dizer por que. Para exercitar uma rota que le
# ficheiros do projeto, defina-o ANTES de a chamar:
#   from src.backend.state import estado; estado['pasta_raiz'] = os.getcwd()
#
# Para PROVAR UMA ROTA com a app a serio, sem subir servidor, importe o modulo do
# app.py e NAO o extensions: quem regista os blueprints e o app.py, logo
#   import app as axio_app; c = axio_app.app.test_client()
# Importar so 'src.backend.extensions' responde 404 em TODAS as rotas (o objeto
# app existe, mas sem blueprint nenhum registado).

'''

_CABECALHO_JS = '''// Gerado por tool_executar_js num ficheiro temporario; apagado no fim.
// ESM (Node): fs, path e assert JA VEM IMPORTADOS aqui (NAO os reimporte: daria
// "Identifier already declared") e top-level await esta disponivel.
// Caminhos relativos sao a raiz do projeto.
// ATENCAO: um "import './src/...'" e resolvido a partir da PASTA DESTE ficheiro
// (%TEMP%), nunca do cwd. Para carregar um modulo do projeto use a funcao abaixo:
//   const m = await importarProjeto("src/frontend/js/editor/terminal.js");
// Um modulo que LE O DOM ao importar (o state.js do frontend e o caso) rebenta
// DENTRO do import, numa linha qualquer. Ha dois caminhos, e nenhum deles e
// adivinhar: (a) tornar o getElementById tolerante antes de importar (ver a nota
// do criarDomFalso); ou (b) -- melhor para testar VARIAS funcoes do mesmo modulo
// -- extrair o CORPO do ficheiro do disco e avalia-lo com new Function, tirando
// as linhas de import E a palavra export (esquecer os export da
// "SyntaxError: Unexpected token 'export'"):
//   const corpo = fs.readFileSync("src/frontend/js/editor/preview_abas.js", "utf8")
//       .replace(/^import[^\\n]*\\n/gm, "").replace(/^export /gm, "");
//   const f = new Function("state", corpo + "return [abrirAbaWeb, abaAtiva];");
//   const m = f(stateFalso, ...);   // os argumentos sao as dependencias do modulo
// ARMADILHA (custou uma rodada a 2026-09-26): uma funcao que o PROPRIO corpo
// declara SOMBREIA o argumento homonimo - passar animateViewTransition como
// dependencia nao impede o corpo de usar a dele, logo o stub nunca corre e o
// erro aparece em codigo que nao e o teu ("Cannot read properties of undefined
// (reading 'toggle')"). So os nomes que o corpo apenas REFERENCIA podem vir do
// new Function; quando a dependencia e DECLARADA la dentro, quem a chama tem de
// receber objetos a serio (classList, offsetWidth, style...) e nao stubs vazios.
import process from "node:process";
import fs from "node:fs";
import path from "node:path";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { pathToFileURL as __paraUrl } from "node:url";
import { join as __juntar } from "node:path";

try {
    process.chdir({RAIZ_JS});
} catch (_erro) {
    // raiz indisponivel: o trecho corre no cwd atual
}

const importarProjeto = (rel) => import(__paraUrl(__juntar(process.cwd(), rel)));

// Extrai do disco o corpo EXATO de uma funcao nomeada, pronto para new Function.
// Inclui o 'async' quando existe (esquece-lo da um SyntaxError que nao aponta para
// a causa) e equilibra chaves - nao distingue chaves dentro de strings.
const __corpoDeFuncao = (texto, nome) => {
    let inicio = texto.indexOf("function " + nome + "(");
    if (inicio < 0) return "";
    if (texto.slice(inicio - 6, inicio) === "async ") inicio -= 6;
    const abre = texto.indexOf("{", inicio);
    let nivel = 0;
    for (let i = abre; i < texto.length; i++) {
        if (texto[i] === "{") nivel++;
        else if (texto[i] === "}" && --nivel === 0) return texto.slice(inicio, i + 1);
    }
    return "";
};

// Quem define `nome` nos outros .js da MESMA pasta: o import diz de onde o modulo
// a TIRA, nao onde ela vive (messages.js pode reexportar de escape.js), e o erro
// "funcao nao encontrada" sem esta pista custa uma pesquisa ao modelo.
const __vizinhosQueDefinem = (caminho, nome) => {
    const alvo = "function " + nome + "(";
    let ficheiros = [];
    try {
        ficheiros = fs.readdirSync(path.dirname(caminho));
    } catch (_erro) {
        return [];
    }
    return ficheiros
        .filter((f) => f.endsWith(".js"))
        .map((f) => path.join(path.dirname(caminho), f))
        .filter((f) => f !== caminho && fs.readFileSync(f, "utf8").includes(alvo));
};

const funcaoDoDisco = (rel, nome) => {
    const caminho = path.isAbsolute(rel) ? rel : path.join(process.cwd(), rel);
    if (!fs.existsSync(caminho)) {
        throw new Error("ficheiro nao encontrado: " + rel
            + (path.isAbsolute(rel) ? "" : " (o caminho e relativo a raiz do projeto)"));
    }
    const corpo = __corpoDeFuncao(fs.readFileSync(caminho, "utf8"), nome);
    if (corpo) return corpo;
    const vizinhos = __vizinhosQueDefinem(caminho, nome);
    if (vizinhos.length === 1) return __corpoDeFuncao(fs.readFileSync(vizinhos[0], "utf8"), nome);
    const onde = vizinhos.length
        ? " - ela vive em " + vizinhos.map((v) => path.relative(process.cwd(), v).split(path.sep).join("/")).join(" e ") + " (passe esse ficheiro)"
        : "";
    throw new Error("funcao nao encontrada no disco: " + nome + " em " + rel + onde);
};

const funcoesDoDisco = (rel, ...nomes) => nomes.map((n) => funcaoDoDisco(rel, n)).join(String.fromCharCode(10));

// O que a funcao extraida chama de FORA: os nomes que ela usa e nao declara
// dentro. E a resposta a "o que tenho de injetar no new Function?", em vez de a
// descobrir um ReferenceError de cada vez:
//   const faltam = dependenciasDeDisco("src/frontend/js/chat/git_panel.js", "montarPainel");
//   // -> ["RASCUNHOS", "escapeHtml", "state", "svgDoPonto", "tituloDaTarefaDoCommit", ...]
//   const api = new Function(...faltam, fonte + "return {montarPainel};")(...faltam.map(duble));
// E heuristica (nao e um parser): pode apanhar um nome que ja vem de dentro de
// uma funcao extraida a parte, e nao ve nomes obtidos por indice (obj[nome]).
// Serve para dar a LISTA, nunca para decidir sozinha o que existe - o assert e
// do modelo. Os literais de template CONTAM: o ${X} de uma template string e
// codigo vivo, e apagar a template inteira escondia um SVG_RAMO de verdade.
const __GLOBaisConhecidos = new Set(("Array ArrayBuffer Boolean Date decodeURI decodeURIComponent " +
    "encodeURI encodeURIComponent Error EvalError Function Infinity Intl isFinite isNaN JSON Map Math " +
    "Number Object parseFloat parseInt Promise Proxy RangeError ReferenceError Reflect RegExp Set " +
    "String Symbol SyntaxError TypeError URIError WeakMap WeakSet console document window globalThis " +
    "process require module exports localStorage sessionStorage fetch setTimeout clearTimeout " +
    "setInterval clearInterval requestAnimationFrame cancelAnimationFrame queueMicrotask structuredClone " +
    "URL URLSearchParams FormData Blob File FileReader AbortController TextEncoder TextDecoder " +
    "arguments undefined NaN null true false this super new typeof instanceof void delete in of return function class " +
    "const let var if else for while do switch case break continue try catch finally throw await async " +
    "yield import export default static get set").split(" "));

const dependenciasDeDisco = (rel, ...nomes) => {
    const texto = funcoesDoDisco(rel, ...nomes)
        .replace(/\\/\\*[\\s\\S]*?\\*\\//g, " ")
        .replace(/\\/\\/.*/g, " ")
        .replace(/`(?:[^`\\\\]|\\\\[\\s\\S])*`/g, (t) => (t.match(/\\$\\{[^}]*\\}/g) || []).join(" "))
        .replace(/'(?:[^'\\n]|\\.)*'/g, " ")
        .replace(/"(?:[^"\\n]|\\.)*"/g, " ");
    const declarados = new Set();
    let m;
    const varrer = (re, grupo) => {
        while ((m = re.exec(texto))) {
            const bruto = m[grupo].replace(/[{}[\\]]/g, ",");
            bruto.split(",").forEach((p) => {
                const nome = p.trim().replace(/^\\.\\.\\./, "").split(/[\\s=:]/)[0];
                if (nome) declarados.add(nome);
            });
        }
    };
    varrer(/(?:function|class)\\s+([A-Za-z_$][\\w$]*)/g, 1);
    varrer(/(?:const|let|var)\\s+([A-Za-z_$][\\w$]*)/g, 1);
    varrer(/(?:const|let|var)\\s*(\\{[^}]*\\})/g, 1);
    varrer(/\\bfunction\\s*[A-Za-z_$\\w]*\\s*\\(([^()]*)\\)/g, 1);
    varrer(/\\(([^()]*)\\)\\s*=>/g, 1);
    varrer(/([A-Za-z_$][\\w$]*)\\s*=>/g, 1);
    const semMembro = texto
        .replace(/[A-Za-z_$][\\w$]*(?:-[A-Za-z_$][\\w$]*)+/g, " ")
        .replace(/\\.\\s*[A-Za-z_$][\\w$]*/g, " ")
        .replace(/[A-Za-z_$][\\w$]*\\s*:/g, " ")
        .replace(/\\$\\{/g, " ");
    const usados = new Set();
    const nomesUsados = /[A-Za-z_$][\\w$]*/g;
    while ((m = nomesUsados.exec(semMembro))) usados.add(m[0]);
    return Array.from(usados)
        .filter((n) => !declarados.has(n) && !__GLOBaisConhecidos.has(n))
        .sort();
};

// Le o repositorio git do projeto sem passar pelo shell: os argumentos chegam um a
// um ao executavel, logo o '%' de um --pretty=format:%cI chega intacto - num
// execSync do Windows quem o come e o cmd.exe, e o erro que sai ("'%cI' nao e
// reconhecido como um comando") nao aponta para o formato. Um teste que mede
// commits, tags ou o repo real passa a ser uma linha:
//   const linhas = gitDoDisco(["log", "--pretty=format:%H|%cI", "-n", "500"]).split("\\n");
const gitDoDisco = (args) => execFileSync("git", args, { encoding: "utf8", cwd: process.cwd() });
'''

_DOM_FALSO_JS = r'''
// --- DOM falso (criarDomFalso) ---------------------------------------------
// document/window minimos para testar codigo de browser neste processo Node,
// em vez de reescrever o stub a mao em cada harness.
// A FUNCAO criarDomFalso esta sempre disponivel; os globais document/window SO
// passam a existir DEPOIS de a chamares - usar `document` sem a chamar da
// ReferenceError. O valor devolvido serve em qualquer caso e e o caminho seguro:
//   const dom = criarDomFalso({css:{"--oliva":"#90a015"}});   // devolve + instala globais
//   dom.document   dom.window    // passa dom.document a um new Function(...)
//   // devolve tambem: body, el, criar, porId, sel, selTodos, medir, estilo,
//   //   evento, disparar, html, serializar, agora, aguardar, Elemento,
//   //   Documento, Texto, instalar, remover   (NAO existe dom.createElement)
//   dom.el("div",{id:"zona",class:"term-cards",texto:"oi",dataset:{pid:"p1"}})
//   dom.porId("zona")   dom.sel("#a .b")   dom.selTodos(".card")
//   dom.medir(el,{top:40,height:660,scrollHeight:2000})   // rect calculado no pedido
//   dom.estilo(el,{color:"#fff"})                          // getComputedStyle
//   dom.disparar("click",el)      // cria o evento E entrega-o (corre os listeners)
//   dom.evento("click",el,{...})  // SO cria o evento, nao entrega: para o entregar,
//                                 //   el.dispatchEvent(ev)  ou  el.click()
//   dom.serializar(el)   // HTML do elemento. `el.innerHTML` devolve so OS FILHOS;
//                        //   a propria raiz sai em el.outerHTML. dom.html e o INVERSO
//                        //   (parser: monta nos a partir de markup, nao serializa) e
//                        //   DEVOLVE UM ARRAY DE NOS SOLTOS - nao os anexa. Quem os quer
//                        //   no documento: `for (const n of dom.html(markup)) document.body.appendChild(n)`
//   dom.agora()          // corre os requestAnimationFrame pendentes
//   await dom.aguardar() // deixa correr microtasks/timers e os rAF
//   await importarProjeto("src/frontend/js/editor/terminal_cards.js")
// Armadilhas ja resolvidas de raiz: appendChild/insertBefore SOLTAM o no do pai
// anterior; className e classList sao a mesma fonte (escrever num le-se no outro);
// classList.toggle respeita o 2o argumento (forca); getBoundingClientRect e
// CALCULADO a cada pedido a partir de offset*/medir(); dispatchEvent propaga
// (captura -> alvo -> bolha) e um erro dentro do listener NAO e engolido.
// dom.disparar aceita as duas ordens - (tipo, alvo) ou (alvo, tipo) - porque
// trocar os argumentos era um erro silencioso que so aparecia como "elemento
// nao encontrado: click". Outra armadilha de leitura: um elemento SEM classe
// devolve el.className === tagName ("SPAN"), nao string vazia (normalizar nos
// asserts com `el.className || el.tagName`).
// Modulo que le o DOM TODO ao importar (o state.js e o caso) rebenta com
// "Cannot read properties of null" numa linha qualquer. Em vez de andar a
// extrair funcoes ao disco, torne o getElementById tolerante ANTES de importar:
//   const nativo = document.getElementById.bind(document);
//   const reserva = new Map();
//   document.getElementById = (id) => {
//     const achado = nativo(id);
//     if (achado) return achado;
//     if (!reserva.has(id)) reserva.set(id, dom.el("div", { id }));
//     return reserva.get(id);
//   };
// Os elementos que o harness anexou ao body ANTES (o #preview-tabs, o
// #preview-address...) sao devolvidos pelo nativo; os que o modulo procura e
// nao existem recebem um no solto igualmente utilizavel.
// window.require existe (um Proxy que aceita qualquer acesso) para os modulos que
// fazem `const {ipcRenderer} = window.require("electron")` no topo.
// Antes de importar um modulo grande do frontend so para testar uma funcao: o
// state.js le o DOM ao importar e o files.js exige window.require. Se rebentar,
// extraia o texto da funcao do disco por assinatura e avalie-a isolada.
const __domCamel = (nome) => String(nome).replace(/-([a-z0-9])/g, (_t, c) => c.toUpperCase());
const __domKebab = (nome) => String(nome).replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
const __domDefinirGlobal = (nome, valor) => {
    try {
        globalThis[nome] = valor;
        return true;
    } catch (_erro) {
        try {
            Object.defineProperty(globalThis, nome, { value: valor, configurable: true, writable: true });
            return true;
        } catch (_erro2) {
            return false;
        }
    }
};
let __domDocumentoAtual = null;

class __DomListaClasses {
    constructor(dono) {
        this._dono = dono;
        this._itens = new Set();
    }
    get value() { return [...this._itens].join(" "); }
    get length() { return this._itens.size; }
    _marcar() { this._dono._classeDefinida = true; }
    _definir(texto) { this._itens = new Set(String(texto == null ? "" : texto).split(/\s+/).filter(Boolean)); }
    add(...nomes) {
        for (const nome of nomes) {
            const limpo = String(nome == null ? "" : nome).trim();
            if (limpo) this._itens.add(limpo);
        }
        this._marcar();
    }
    remove(...nomes) {
        for (const nome of nomes) this._itens.delete(String(nome == null ? "" : nome).trim());
        this._marcar();
    }
    contains(nome) { return this._itens.has(String(nome == null ? "" : nome).trim()); }
    toggle(nome, forca) {
        const limpo = String(nome == null ? "" : nome).trim();
        const ligar = forca === undefined ? !this._itens.has(limpo) : !!forca;
        if (ligar) this._itens.add(limpo);
        else this._itens.delete(limpo);
        this._marcar();
        return ligar;
    }
    item(indice) { return [...this._itens][indice] ?? null; }
    toString() { return this.value; }
    [Symbol.iterator]() { return [...this._itens][Symbol.iterator](); }
}

class __DomNo {
    constructor() {
        this.parentNode = null;
        this.childNodes = [];
        this._eventos = new Map();
    }
    get parentElement() {
        const pai = this.parentNode;
        return pai && pai.nodeType === 1 ? pai : null;
    }
    get children() { return this.childNodes.filter((no) => no.nodeType === 1); }
    get childElementCount() { return this.children.length; }
    get firstChild() { return this.childNodes[0] || null; }
    get lastChild() { return this.childNodes.length ? this.childNodes[this.childNodes.length - 1] : null; }
    get firstElementChild() { return this.children[0] || null; }
    get lastElementChild() {
        const lista = this.children;
        return lista.length ? lista[lista.length - 1] : null;
    }
    get previousSibling() {
        const pai = this.parentNode;
        if (!pai) return null;
        const indice = pai.childNodes.indexOf(this);
        return indice > 0 ? pai.childNodes[indice - 1] : null;
    }
    get nextSibling() {
        const pai = this.parentNode;
        if (!pai) return null;
        const indice = pai.childNodes.indexOf(this);
        return indice >= 0 && indice < pai.childNodes.length - 1 ? pai.childNodes[indice + 1] : null;
    }
    get textContent() {
        if (this.nodeType === 3) return this.data;
        return this.childNodes.map((no) => no.textContent).join("");
    }
    set textContent(valor) {
        if (this.nodeType === 3) {
            this.data = String(valor == null ? "" : valor);
            return;
        }
        for (const filho of [...this.childNodes]) this.removeChild(filho);
        const texto = String(valor == null ? "" : valor);
        if (texto) this.appendChild(new __DomTexto(texto));
    }
    _soltar(no) { if (no && no.parentNode) no.parentNode.removeChild(no); }
    appendChild(no) {
        if (!no) return no;
        if (no.nodeType === 11) {
            for (const filho of [...no.childNodes]) this.appendChild(filho);
            return no;
        }
        this._soltar(no);
        no.parentNode = this;
        this.childNodes.push(no);
        return no;
    }
    insertBefore(no, referencia) {
        if (!no) return no;
        if (referencia == null) return this.appendChild(no);
        if (this.childNodes.indexOf(referencia) < 0) throw new Error("insertBefore: a referencia nao e filha deste no");
        if (no === referencia) return no;
        if (no.nodeType === 11) {
            for (const filho of [...no.childNodes]) this.insertBefore(filho, referencia);
            return no;
        }
        this._soltar(no);
        no.parentNode = this;
        this.childNodes.splice(this.childNodes.indexOf(referencia), 0, no);
        return no;
    }
    removeChild(no) {
        const indice = this.childNodes.indexOf(no);
        if (indice < 0) throw new Error("removeChild: o no nao e filho deste no");
        this.childNodes.splice(indice, 1);
        no.parentNode = null;
        return no;
    }
    replaceChild(novo, velho) {
        const indice = this.childNodes.indexOf(velho);
        if (indice < 0) throw new Error("replaceChild: o no nao e filho deste no");
        this._soltar(novo);
        novo.parentNode = this;
        this.childNodes[indice] = novo;
        velho.parentNode = null;
        return velho;
    }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    replaceWith(...nos) {
        const pai = this.parentNode;
        if (!pai) return;
        for (const no of nos) {
            const novo = typeof no === "string" ? new __DomTexto(no) : no;
            if (novo !== this) pai.insertBefore(novo, this);
        }
        pai.removeChild(this);
    }
    before(...nos) {
        const pai = this.parentNode;
        if (!pai) return;
        for (const no of nos) {
            const novo = typeof no === "string" ? new __DomTexto(no) : no;
            if (novo !== this) pai.insertBefore(novo, this);
        }
    }
    after(...nos) {
        const pai = this.parentNode;
        if (!pai) return;
        for (const no of [...nos].reverse()) {
            const novo = typeof no === "string" ? new __DomTexto(no) : no;
            if (novo !== this) pai.insertBefore(novo, this.nextSibling);
        }
    }
    contains(no) {
        if (no === this) return true;
        for (const filho of this.childNodes) if (filho.contains(no)) return true;
        return false;
    }
}

class __DomTexto extends __DomNo {
    constructor(texto) {
        super();
        this.nodeType = 3;
        this.data = String(texto == null ? "" : texto);
    }
    get nodeValue() { return this.data; }
    set nodeValue(valor) { this.data = String(valor == null ? "" : valor); }
}

class __DomFragmento extends __DomNo {
    constructor() {
        super();
        this.nodeType = 11;
    }
}

const __domEstilo = (dono) => {
    const consultar = (nome) => {
        const chave = String(nome);
        return dono._estilo[chave] === undefined ? "" : String(dono._estilo[chave]);
    };
    const alvo = {
        setProperty(nome, valor) { dono._estilo[String(nome)] = String(valor); },
        getPropertyValue(nome) { return consultar(__domKebab(nome)); },
        removeProperty(nome) { delete dono._estilo[__domKebab(nome)]; },
        get cssText() { return Object.entries(dono._estilo).map(([k, v]) => k + ": " + v).join("; "); },
    };
    return new Proxy(alvo, {
        get(t, prop) {
            if (typeof prop !== "string") return Reflect.get(t, prop);
            if (prop in t) return t[prop];
            return consultar(prop);
        },
        set(t, prop, valor) {
            if (typeof prop !== "string") return Reflect.set(t, prop, valor);
            if (prop in t) return Reflect.set(t, prop, valor);
            dono._estilo[prop] = String(valor);
            return true;
        },
        has(t, prop) { return typeof prop === "string" && (prop in t || dono._estilo[prop] !== undefined); },
    });
};

const __domDataset = (dono) => new Proxy({}, {
    get(_t, prop) {
        if (typeof prop !== "string") return undefined;
        return dono._dados[prop];
    },
    set(_t, prop, valor) {
        if (typeof prop !== "string") return true;
        dono._dados[prop] = String(valor);
        return true;
    },
    deleteProperty(_t, prop) { delete dono._dados[String(prop)]; return true; },
    has(_t, prop) { return typeof prop === "string" && prop in dono._dados; },
    ownKeys() { return Object.keys(dono._dados); },
    getOwnPropertyDescriptor() { return { enumerable: true, configurable: true }; },
});

class __DomElemento extends __DomNo {
    constructor(tag, ns) {
        super();
        this.nodeType = 1;
        this.localName = String(tag || "").toLowerCase();
        this.tagName = this.localName.toUpperCase();
        this.namespaceURI = ns || "http://www.w3.org/1999/xhtml";
        this._id = "";
        this._classeDefinida = false;
        this._atributos = new Map();
        this._dados = {};
        this._estilo = {};
        this._estiloDeclarado = null;
        this.classList = new __DomListaClasses(this);
        this.style = __domEstilo(this);
        this.dataset = __domDataset(this);
        this.value = "";
        this.checked = false;
        this.disabled = false;
        this.hidden = false;
        this.readOnly = false;
        this.title = "";
        this.placeholder = "";
        this.href = "";
        this.selectionStart = 0;
        this.selectionEnd = 0;
        this._scrollTop = 0;
        this._scrollLeft = 0;
        this.scrollHeight = 0;
        this.scrollWidth = 0;
        this.clientHeight = 0;
        this.clientWidth = 0;
        this.offsetTop = 0;
        this.offsetLeft = 0;
        this.offsetWidth = 0;
        this.offsetHeight = 0;
    }
    get id() { return this._id; }
    set id(valor) { this._id = String(valor == null ? "" : valor); }
    get className() { return this.classList.value; }
    set className(valor) {
        this._classeDefinida = true;
        this.classList._definir(valor);
    }
    get innerHTML() { return this.childNodes.map(__domSerializar).join(""); }
    get outerHTML() { return __domSerializar(this); }
    set innerHTML(markup) {
        for (const filho of [...this.childNodes]) this.removeChild(filho);
        for (const no of __domNosDeHtml(String(markup == null ? "" : markup), (tag) => new __DomElemento(tag))) {
            this.appendChild(no);
        }
    }
    get scrollTop() { return this._scrollTop; }
    set scrollTop(valor) {
        const maximo = this.scrollHeight > 0 ? Math.max(0, this.scrollHeight - this.clientHeight) : Infinity;
        this._scrollTop = Math.min(Math.max(0, Number(valor) || 0), maximo);
    }
    get scrollLeft() { return this._scrollLeft; }
    set scrollLeft(valor) { this._scrollLeft = Math.max(0, Number(valor) || 0); }
    getBoundingClientRect() {
        const topo = this.offsetTop;
        const esquerda = this.offsetLeft;
        const altura = this.offsetHeight;
        const largura = this.offsetWidth;
        return {
            top: topo, left: esquerda, right: esquerda + largura, bottom: topo + altura,
            width: largura, height: altura, x: esquerda, y: topo,
            toJSON() { return { top: topo, left: esquerda, width: largura, height: altura }; },
        };
    }
    setAttribute(nome, valor) {
        const chave = String(nome).toLowerCase();
        const texto = valor == null ? "" : String(valor);
        if (chave === "class") { this.className = texto; return; }
        if (chave === "id") { this._id = texto; return; }
        if (chave === "style") { this._estilo = {}; this.style.cssText; return; }
        if (chave.startsWith("data-")) {
            this._dados[__domCamel(chave.slice(5))] = texto;
            return;
        }
        this._atributos.set(chave, texto);
        if (chave === "value" || chave === "title" || chave === "placeholder" || chave === "href") this[chave] = texto;
        if (chave === "disabled" || chave === "checked" || chave === "hidden") this[chave] = true;
        if (chave === "readonly") this.readOnly = true;
    }
    getAttribute(nome) {
        const chave = String(nome).toLowerCase();
        if (chave === "class") return this._classeDefinida && this.classList.value ? this.classList.value : null;
        if (chave === "id") return this._id || null;
        if (chave.startsWith("data-")) {
            const prop = __domCamel(chave.slice(5));
            return prop in this._dados ? this._dados[prop] : null;
        }
        return this._atributos.has(chave) ? this._atributos.get(chave) : null;
    }
    hasAttribute(nome) { return this.getAttribute(nome) !== null; }
    removeAttribute(nome) {
        const chave = String(nome).toLowerCase();
        if (chave === "class") { this.classList._definir(""); return; }
        if (chave === "id") { this._id = ""; return; }
        if (chave.startsWith("data-")) { delete this._dados[__domCamel(chave.slice(5))]; return; }
        this._atributos.delete(chave);
    }
    get attributes() {
        const lista = [];
        if (this._id) lista.push({ name: "id", value: this._id });
        const classe = this._classeDefinida && this.classList.value ? this.classList.value : "";
        if (classe) lista.push({ name: "class", value: classe });
        for (const [chave, valor] of this._atributos) lista.push({ name: chave, value: valor });
        for (const [chave, valor] of Object.entries(this._dados)) lista.push({ name: "data-" + __domKebab(chave), value: valor });
        return lista;
    }
    matches(seletor) { return __domAnalisar(seletor).some((partes) => __domCorresponde(this, partes)); }
    closest(seletor) {
        let no = this;
        while (no && no.nodeType === 1) {
            if (no.matches(seletor)) return no;
            no = no.parentElement;
        }
        return null;
    }
    querySelector(seletor) {
        const achados = __domProcurar(this, seletor, true);
        return achados.length ? achados[0] : null;
    }
    querySelectorAll(seletor) { return __domProcurar(this, seletor, false); }
    getElementsByClassName(classe) {
        return this.querySelectorAll("." + String(classe).trim().split(/\s+/).join("."));
    }
    getElementsByTagName(tag) { return this.querySelectorAll(String(tag)); }
    append(...nos) {
        for (const no of nos) this.appendChild(typeof no === "string" ? new __DomTexto(no) : no);
    }
    prepend(...nos) {
        const primeiro = this.childNodes[0] || null;
        for (const no of nos) this.insertBefore(typeof no === "string" ? new __DomTexto(no) : no, primeiro);
    }
    replaceChildren(...nos) {
        for (const filho of [...this.childNodes]) this.removeChild(filho);
        this.append(...nos);
    }
    insertAdjacentHTML(posicao, markup) {
        const nos = __domNosDeHtml(String(markup == null ? "" : markup), (tag) => new __DomElemento(tag));
        if (posicao === "beforeend") { for (const no of nos) this.appendChild(no); return; }
        if (posicao === "afterbegin") { for (const no of [...nos].reverse()) this.insertBefore(no, this.childNodes[0] || null); return; }
        const pai = this.parentNode;
        if (!pai) return;
        for (const no of nos) {
            if (posicao === "beforebegin") pai.insertBefore(no, this);
            else pai.insertBefore(no, this.nextSibling);
        }
    }
    scrollTo(a, b) {
        if (a && typeof a === "object") {
            if (a.top !== undefined) this.scrollTop = a.top;
            if (a.left !== undefined) this.scrollLeft = a.left;
            return;
        }
        if (a !== undefined) this.scrollLeft = a;
        if (b !== undefined) this.scrollTop = b;
    }
    scrollBy(a, b) {
        const topo = a && typeof a === "object" ? (a.top || 0) : (b || 0);
        const esquerda = a && typeof a === "object" ? (a.left || 0) : (a || 0);
        this.scrollTo(this.scrollLeft + esquerda, this.scrollTop + topo);
    }
    scrollIntoView() {}
    focus() {
        if (__domDocumentoAtual) __domDocumentoAtual.activeElement = this;
    }
    blur() {
        if (__domDocumentoAtual && __domDocumentoAtual.activeElement === this) {
            __domDocumentoAtual.activeElement = __domDocumentoAtual.body;
        }
    }
    select() {
        if (this.tagName !== "INPUT" && this.tagName !== "TEXTAREA") return;
        this.selectionStart = 0;
        this.selectionEnd = String(this.value == null ? "" : this.value).length;
    }
    click() { return this.dispatchEvent(new __DomEvento("click", { bubbles: true })); }
    setPointerCapture() {}
    releasePointerCapture() {}
    hasPointerCapture() { return false; }
    animate() { return { finished: Promise.resolve(), cancel() {} }; }
    getClientRects() { return [this.getBoundingClientRect()]; }
}

const __DOM_VAZIOS = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);

const __domAtributosDeTexto = (el, texto) => {
    const re = /([\w:@.-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
    let casado;
    while ((casado = re.exec(texto)) !== null) {
        const nome = casado[1];
        let valor = "";
        if (casado[2] !== undefined) valor = casado[2];
        else if (casado[3] !== undefined) valor = casado[3];
        else if (casado[4] !== undefined) valor = casado[4];
        el.setAttribute(nome, valor);
    }
};

const __domNosDeHtml = (markup, criarElemento) => {
    const raiz = [];
    const pilha = [null];
    const re = /<!--[\s\S]*?-->|<\/([a-zA-Z][\w:-]*)\s*>|<([a-zA-Z][\w:-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>|([^<]+)/g;
    let casado;
    while ((casado = re.exec(markup)) !== null) {
        const bruto = casado[0];
        if (bruto.startsWith("<!--")) continue;
        if (casado[1]) {
            if (pilha.length > 1) pilha.pop();
            continue;
        }
        if (casado[2]) {
            const el = criarElemento(casado[2]);
            __domAtributosDeTexto(el, casado[3] || "");
            const pai = pilha[pilha.length - 1];
            if (pai) pai.appendChild(el);
            else raiz.push(el);
            if (!casado[4] && !__DOM_VAZIOS.has(casado[2].toLowerCase())) pilha.push(el);
            continue;
        }
        if (casado[5] !== undefined) {
            const brutoTexto = casado[5];
            if (/^\s*$/.test(brutoTexto) && brutoTexto.indexOf("\n") >= 0) continue;
            const conteudo = brutoTexto.indexOf("\n") >= 0 ? brutoTexto.replace(/\s+/g, " ") : brutoTexto;
            const texto = new __DomTexto(conteudo);
            const pai = pilha[pilha.length - 1];
            if (pai) pai.appendChild(texto);
            else raiz.push(texto);
        }
    }
    return raiz;
};

const __domSerializar = (no) => {
    if (no.nodeType === 3) {
        return String(no.data).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    if (no.nodeType !== 1) return no.childNodes.map(__domSerializar).join("");
    const atributos = [];
    if (no._id) atributos.push('id="' + no._id + '"');
    if (no.classList.length) atributos.push('class="' + no.classList.value + '"');
    for (const [nome, valor] of no._atributos) atributos.push(nome + '="' + String(valor).replace(/"/g, "&quot;") + '"');
    const estilos = Object.entries(no._estilo);
    if (estilos.length) atributos.push('style="' + estilos.map(([k, v]) => k + ": " + v).join("; ") + '"');
    const abre = "<" + no.localName + (atributos.length ? " " + atributos.join(" ") : "") + ">";
    if (__DOM_VAZIOS.has(no.localName)) return abre;
    return abre + no.childNodes.map(__domSerializar).join("") + "</" + no.localName + ">";
};

const __domComposto = (texto) => {
    const negativo = [];
    const posicoes = [];
    const limpo = String(texto).replace(/:not\(([^)]*)\)/g, (_t, dentro) => {
        negativo.push(__domComposto(dentro));
        return "";
    }).replace(/:(nth-child|nth-of-type)\(([^)]*)\)/g, (_t, qual, dentro) => {
        posicoes.push({ qual, valor: String(dentro).trim() });
        return "";
    });
    let tag = null;
    const classes = [];
    const atributos = [];
    const re = /([a-zA-Z*][\w-]*)|#([\w-]+)|\.([\w-]+)|\[([^\]]*)\]/g;
    let casado;
    while ((casado = re.exec(limpo)) !== null) {
        if (casado[1]) tag = casado[1].toLowerCase();
        else if (casado[2]) atributos.push(["@id", casado[2]]);
        else if (casado[3]) classes.push(casado[3]);
        else if (casado[4] !== undefined) {
            const partes = casado[4].split("=");
            const nome = partes[0].trim().toLowerCase();
            const valor = partes.length > 1 ? partes.slice(1).join("=").trim().replace(/^["']|["']$/g, "") : null;
            atributos.push([nome, valor]);
        }
    }
    return { tag, classes, atributos, negativo, posicoes };
};

const __domDividir = (texto, separadores) => {
    const partes = [];
    let atual = "";
    let nivel = 0;
    for (const caractere of texto) {
        if (caractere === "[" || caractere === "(") nivel += 1;
        else if (caractere === "]" || caractere === ")") nivel = Math.max(0, nivel - 1);
        if (nivel === 0 && separadores.includes(caractere)) {
            partes.push(atual);
            atual = "";
            continue;
        }
        atual += caractere;
    }
    partes.push(atual);
    return partes;
};

const __domNormalizar = (texto) => {
    let saida = "";
    let nivel = 0;
    for (const caractere of String(texto).trim()) {
        if (caractere === "[" || caractere === "(") nivel += 1;
        else if (caractere === "]" || caractere === ")") nivel = Math.max(0, nivel - 1);
        if (nivel === 0 && caractere === ">") { saida += " > "; continue; }
        if (nivel === 0 && /\s/.test(caractere)) { saida += " "; continue; }
        saida += caractere;
    }
    return saida.trim();
};

const __domAnalisar = (seletor) => __domDividir(String(seletor), ",").map((grupo) => {
    const bruto = __domNormalizar(grupo);
    if (!bruto) return null;
    const partes = [];
    let combinador = null;
    for (const pedaco of bruto.split(" ")) {
        if (!pedaco) continue;
        if (pedaco === ">") { combinador = ">"; continue; }
        partes.push({ comp: __domComposto(pedaco), combinador: combinador || " " });
        combinador = null;
    }
    return partes.length ? partes : null;
}).filter(Boolean);

const __domPosicao = (el, pos) => {
    const pai = el.parentElement;
    if (!pai) return false;
    const porTipo = pos.qual === "nth-of-type";
    const irmaos = [];
    for (const no of pai.children) {
        if (no.nodeType !== 1) continue;
        if (porTipo && no.localName !== el.localName) continue;
        irmaos.push(no);
    }
    const indice = irmaos.indexOf(el) + 1;
    if (!indice) return false;
    const bruto = String(pos.valor || "").toLowerCase();
    if (bruto === "odd") return indice % 2 === 1;
    if (bruto === "even") return indice % 2 === 0;
    const numero = Number(bruto);
    return Number.isFinite(numero) && indice === numero;
};

const __domTestar = (el, comp) => {
    if (!el || el.nodeType !== 1) return false;
    if (comp.tag && comp.tag !== "*" && el.localName !== comp.tag) return false;
    for (const pos of comp.posicoes || []) if (!__domPosicao(el, pos)) return false;
    for (const classe of comp.classes) if (!el.classList.contains(classe)) return false;
    for (const [nome, valor] of comp.atributos) {
        let atual;
        if (nome === "@id") atual = el.id || null;
        else atual = el.getAttribute(nome);
        if (atual === null || atual === undefined) return false;
        if (valor !== null && atual !== valor) return false;
    }
    for (const nao of comp.negativo) if (__domTestar(el, nao)) return false;
    return true;
};

const __domAntecessores = (el, partes, indice) => {
    if (indice === 0) return true;
    const combinador = partes[indice].combinador;
    let pai = el.parentElement;
    while (pai) {
        if (__domTestar(pai, partes[indice - 1].comp) && __domAntecessores(pai, partes, indice - 1)) return true;
        if (combinador === ">") return false;
        pai = pai.parentElement;
    }
    return false;
};

const __domCorresponde = (el, partes) => {
    if (!__domTestar(el, partes[partes.length - 1].comp)) return false;
    return __domAntecessores(el, partes, partes.length - 1);
};

const __domProcurar = (raiz, seletor, soPrimeiro) => {
    const grupos = __domAnalisar(seletor);
    const achados = [];
    const visitar = (no) => {
        if (soPrimeiro && achados.length) return;
        for (const filho of no.childNodes) {
            if (filho.nodeType !== 1) continue;
            if (grupos.some((partes) => __domCorresponde(filho, partes))) achados.push(filho);
            if (soPrimeiro && achados.length) return;
            visitar(filho);
            if (soPrimeiro && achados.length) return;
        }
    };
    visitar(raiz);
    return achados;
};

class __DomEvento {
    constructor(tipo, opcoes) {
        const o = opcoes || {};
        this.type = String(tipo);
        this.bubbles = o.bubbles !== false;
        this.cancelable = o.cancelable !== false;
        this.defaultPrevented = false;
        this.target = null;
        this.currentTarget = null;
        this.detail = o.detail;
        this.propertyName = o.propertyName;
        this.elapsedTime = o.elapsedTime || 0;
        this.pseudoElement = o.pseudoElement || "";
        this.animationName = o.animationName;
        this.key = o.key;
        this.code = o.code;
        this.ctrlKey = !!o.ctrlKey;
        this.shiftKey = !!o.shiftKey;
        this.altKey = !!o.altKey;
        this.metaKey = !!o.metaKey;
        this.button = o.button || 0;
        this.buttons = o.buttons === undefined ? (o.button ? 0 : 1) : o.buttons;
        this.clientX = o.clientX || 0;
        this.clientY = o.clientY || 0;
        this.pointerId = o.pointerId || 1;
        this.pointerType = o.pointerType || "mouse";
        this.isPrimary = o.isPrimary !== false;
        this._parar = false;
        this._pararJa = false;
        this._caminho = [];
    }
    preventDefault() { this.defaultPrevented = true; }
    stopPropagation() { this._parar = true; }
    stopImmediatePropagation() { this._parar = true; this._pararJa = true; }
    composedPath() { return this._caminho || []; }
}

const __domAddEventListener = function (tipo, fn, opcoes) {
    if (typeof fn !== "function") return;
    const cfg = typeof opcoes === "boolean" ? { capture: opcoes } : (opcoes || {});
    const captura = !!cfg.capture;
    const lista = this._eventos.get(tipo) || [];
    if (lista.some((reg) => reg.fn === fn && reg.capture === captura)) return;
    lista.push({ fn, once: !!cfg.once, capture: captura });
    this._eventos.set(tipo, lista);
};

const __domRemoveEventListener = function (tipo, fn, opcoes) {
    const lista = this._eventos.get(tipo);
    if (!lista) return;
    const cfg = typeof opcoes === "boolean" ? { capture: opcoes } : (opcoes || {});
    const captura = !!cfg.capture;
    const indice = lista.findIndex((reg) => reg.fn === fn && reg.capture === captura);
    if (indice >= 0) lista.splice(indice, 1);
};

const __domDispatchEvent = function (evento) { return __domDespachar(this, evento); };

const __domDespachar = (alvo, evento) => {
    const ev = evento && typeof evento === "object" ? evento : new __DomEvento(String(evento));
    if (typeof ev.type !== "string") ev.type = String(ev.type || "");
    if (ev._parar === undefined) ev._parar = false;
    if (ev._pararJa === undefined) ev._pararJa = false;
    if (typeof ev.preventDefault !== "function") ev.preventDefault = function () { this.defaultPrevented = true; };
    if (typeof ev.stopPropagation !== "function") ev.stopPropagation = function () { this._parar = true; };
    if (typeof ev.stopImmediatePropagation !== "function") {
        ev.stopImmediatePropagation = function () { this._parar = true; this._pararJa = true; };
    }
    if (!ev.target) ev.target = alvo;
    const caminho = [];
    let no = alvo;
    while (no) {
        caminho.push(no);
        no = no.parentNode;
    }
    const doc = __domDocumentoAtual;
    if (doc && caminho.indexOf(doc) < 0) caminho.push(doc);
    const janela = doc && doc.defaultView;
    if (janela && caminho.indexOf(janela) < 0) caminho.push(janela);
    ev._caminho = caminho;
    const chamar = (dono, fase) => {
        const lista = dono && dono._eventos ? dono._eventos.get(ev.type) : null;
        if (!lista) return;
        for (const reg of [...lista]) {
            if (ev._parar) return;
            if (fase === "captura" && !reg.capture) continue;
            if (fase === "bolha" && reg.capture) continue;
            if (reg.once) dono.removeEventListener(ev.type, reg.fn, { capture: reg.capture });
            ev.currentTarget = dono;
            reg.fn.call(dono, ev);
            if (ev._pararJa) return;
        }
    };
    for (let i = caminho.length - 1; i >= 1; i--) {
        if (ev._parar) break;
        chamar(caminho[i], "captura");
    }
    if (!ev._parar) chamar(caminho[0], "alvo");
    for (let i = 1; i < caminho.length; i++) {
        if (ev._parar) break;
        chamar(caminho[i], "bolha");
    }
    return !ev.defaultPrevented;
};

__DomNo.prototype.addEventListener = __domAddEventListener;
__DomNo.prototype.removeEventListener = __domRemoveEventListener;
__DomNo.prototype.dispatchEvent = __domDispatchEvent;

class __DomDocumento extends __DomNo {
    constructor() {
        super();
        this.nodeType = 9;
        this.documentElement = null;
        this.body = null;
        this.head = null;
        this.title = "";
        this.activeElement = null;
        this.defaultView = null;
    }
    createElement(tag) { return new __DomElemento(tag); }
    createElementNS(ns, tag) { return new __DomElemento(tag, ns); }
    createTextNode(texto) { return new __DomTexto(texto); }
    createDocumentFragment() { return new __DomFragmento(); }
    createRange() {
        const faixa = {
            startContainer: null, endContainer: null,
            startOffset: 0, endOffset: 0,
            collapsed: true, commonAncestorContainer: null,
            selectNodeContents(no) {
                this.startContainer = no;
                this.endContainer = no;
                this.commonAncestorContainer = no;
                this.startOffset = 0;
                this.endOffset = no && no.childNodes ? no.childNodes.length : 0;
                this.collapsed = false;
                return this;
            },
            selectNode(no) {
                this.commonAncestorContainer = (no && no.parentNode) || no;
                return this.selectNodeContents(no);
            },
            collapse() {
                this.collapsed = true;
                this.endContainer = this.startContainer;
                this.endOffset = this.startOffset;
            },
            cloneRange() { return Object.assign({}, this); },
            detach() {},
            toString() { return this.startContainer && this.startContainer.textContent ? String(this.startContainer.textContent) : ""; },
        };
        return faixa;
    }
    getElementById(id) {
        const procurado = String(id);
        const visitar = (no) => {
            for (const filho of no.childNodes) {
                if (filho.nodeType !== 1) continue;
                if (filho.id === procurado) return filho;
                const achado = visitar(filho);
                if (achado) return achado;
            }
            return null;
        };
        return visitar(this.documentElement || this);
    }
    elementFromPoint(x, y) {
        const px = Number(x);
        const py = Number(y);
        const dentro = [];
        const visitar = (no, profundidade) => {
            for (const filho of no.childNodes) {
                if (filho.nodeType !== 1) continue;
                const largura = filho.offsetWidth || 0;
                const altura = filho.offsetHeight || 0;
                if (largura > 0 && altura > 0) {
                    const esquerda = filho.offsetLeft || 0;
                    const topo = filho.offsetTop || 0;
                    if (px >= esquerda && px < esquerda + largura && py >= topo && py < topo + altura) {
                        dentro.push({ no: filho, ordem: (filho.__porCima ? 1000 : 0) + profundidade });
                    }
                }
                visitar(filho, profundidade + 1);
            }
        };
        visitar(this.documentElement || this, 0);
        if (!dentro.length) return this.body || null;
        dentro.sort((a, b) => a.ordem - b.ordem);
        return dentro[dentro.length - 1].no;
    }
    querySelector(seletor) {
        const achados = __domProcurar(this.documentElement || this, seletor, true);
        return achados.length ? achados[0] : null;
    }
    querySelectorAll(seletor) { return __domProcurar(this.documentElement || this, seletor, false); }
}

const __DOM_ESTILO_PADRAO = {
    display: "block",
    visibility: "visible",
    opacity: "1",
    pointerEvents: "auto",
};

const __domEstiloComputado = (el, vars) => {
    const mapa = Object.assign({}, vars || {}, (el && el._estiloDeclarado) || {}, (el && el._estilo) || {});
    const consultar = (nome) => {
        const chave = String(nome);
        if (chave.slice(0, 2) === "--") return (vars && vars[chave]) || "";
        const camel = __domCamel(chave);
        const valor = mapa[camel];
        if (valor !== undefined && valor !== null && valor !== "") return String(valor);
        return __DOM_ESTILO_PADRAO[camel] || "";
    };
    const alvo = { getPropertyValue: consultar };
    return new Proxy(alvo, {
        get(t, prop) {
            if (typeof prop !== "string") return Reflect.get(t, prop);
            if (prop in t) return t[prop];
            return consultar(__domKebab(prop));
        },
    });
};

const criarDomFalso = (opcoes) => {
    const cfg = opcoes || {};
    const vars = Object.assign({}, cfg.css || {});
    const doc = new __DomDocumento();
    __domDocumentoAtual = doc;
    const html = doc.createElement("html");
    const cabeca = doc.createElement("head");
    const corpo = doc.createElement("body");
    html.appendChild(cabeca);
    html.appendChild(corpo);
    doc.appendChild(html);
    doc.documentElement = html;
    doc.head = cabeca;
    doc.body = corpo;
    doc.activeElement = corpo;

    const quadros = new Map();
    let proximoQuadro = 0;
    const executarQuadros = () => {
        const lote = [...quadros.entries()];
        quadros.clear();
        for (const [, fn] of lote) fn(Date.now());
        return lote.length;
    };
    const criarArmazem = () => {
        const mapa = new Map();
        return {
            getItem: (chave) => (mapa.has(String(chave)) ? mapa.get(String(chave)) : null),
            setItem: (chave, valor) => { mapa.set(String(chave), String(valor)); },
            removeItem: (chave) => { mapa.delete(String(chave)); },
            clear: () => { mapa.clear(); },
            key: (indice) => [...mapa.keys()][indice] ?? null,
            get length() { return mapa.size; },
        };
    };
    const janela = {
        document: doc,
        _eventos: new Map(),
        addEventListener: __domAddEventListener,
        removeEventListener: __domRemoveEventListener,
        dispatchEvent: __domDispatchEvent,
        innerWidth: cfg.largura || 1200,
        innerHeight: cfg.altura || 800,
        devicePixelRatio: 1,
        setTimeout: (fn, ms) => setTimeout(fn, ms),
        clearTimeout: (id) => clearTimeout(id),
        require: () => {
            const vazio = () => new Proxy(function () {}, {
                get: (_t, p) => (p === "then" ? undefined : vazio()),
                apply: () => vazio(),
            });
            return vazio();
        },
        setInterval: (fn, ms) => setInterval(fn, ms),
        clearInterval: (id) => clearInterval(id),
        localStorage: criarArmazem(),
        sessionStorage: criarArmazem(),
        location: { href: "http://localhost/", origin: "http://localhost", pathname: "/", search: "", hash: "", reload() {} },
        navigator: { userAgent: "axio-dom-falso", platform: "Win32", language: "pt-PT" },
        requestAnimationFrame: (fn) => {
            proximoQuadro += 1;
            quadros.set(proximoQuadro, fn);
            return proximoQuadro;
        },
        cancelAnimationFrame: (id) => { quadros.delete(id); },
        matchMedia: (consulta) => ({
            matches: false, media: String(consulta),
            addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
        }),
        getComputedStyle: (el) => __domEstiloComputado(el, vars),
        getSelection: () => ({ toString: () => "", rangeCount: 0, removeAllRanges() {}, addRange() {} }),
        scrollTo() {},
        print() {},
        close() {},
    };
    janela.window = janela;
    janela.self = janela;
    janela.top = janela;
    janela.parent = janela;
    doc.defaultView = janela;

    const resolver = (alvo) => {
        const no = typeof alvo === "string" ? doc.querySelector(alvo) : alvo;
        if (!no) throw new Error("elemento nao encontrado: " + alvo);
        return no;
    };
    const el = (tag, props, ...filhos) => {
        const no = doc.createElement(tag);
        for (const [chave, valor] of Object.entries(props || {})) {
            if (chave === "id") no.id = String(valor);
            else if (chave === "class" || chave === "classe") no.className = String(valor);
            else if (chave === "texto") no.textContent = String(valor);
            else if (chave === "html") no.innerHTML = String(valor);
            else if (chave === "style") Object.assign(no.style, valor);
            else if (chave === "dataset") for (const [k, v] of Object.entries(valor)) no.dataset[k] = v;
            else if (chave === "attrs") for (const [k, v] of Object.entries(valor)) no.setAttribute(k, v);
            else if (typeof valor === "string" || typeof valor === "number" || typeof valor === "boolean") no.setAttribute(chave, valor);
            else no[chave] = valor;
        }
        for (const filho of filhos.flat()) {
            if (filho === null || filho === undefined || filho === false) continue;
            no.appendChild(typeof filho === "string" ? doc.createTextNode(filho) : filho);
        }
        return no;
    };
    const medir = (alvo, medidas, opcoes) => {
        const no = resolver(alvo);
        const m = medidas || {};
        if (opcoes && opcoes.porCima) no.__porCima = true;
        const altura = m.height !== undefined ? m.height : m.altura;
        const largura = m.width !== undefined ? m.width : m.largura;
        const topo = m.top !== undefined ? m.top : m.topo;
        const esquerda = m.left !== undefined ? m.left : m.esquerda;
        if (altura !== undefined) {
            no.offsetHeight = altura;
            if (m.clientHeight === undefined) no.clientHeight = altura;
        }
        if (largura !== undefined) {
            no.offsetWidth = largura;
            if (m.clientWidth === undefined) no.clientWidth = largura;
        }
        if (topo !== undefined) no.offsetTop = topo;
        if (esquerda !== undefined) no.offsetLeft = esquerda;
        if (m.clientHeight !== undefined) no.clientHeight = m.clientHeight;
        if (m.clientWidth !== undefined) no.clientWidth = m.clientWidth;
        if (m.scrollHeight !== undefined) no.scrollHeight = m.scrollHeight;
        if (m.scrollWidth !== undefined) no.scrollWidth = m.scrollWidth;
        return no;
    };
    const estilo = (alvo, props) => {
        const no = resolver(alvo);
        no._estiloDeclarado = Object.assign(no._estiloDeclarado || {}, props || {});
        return no;
    };
    const evento = (tipo, alvo, props) => {
        const ev = new __DomEvento(tipo, props || {});
        if (alvo) ev.target = alvo;
        return ev;
    };
    const disparar = (tipo, alvo, props) => {
        if (typeof tipo !== "string" && typeof alvo === "string") {
            const troca = tipo;
            tipo = alvo;
            alvo = troca;
        }
        const no = resolver(alvo);
        const ev = evento(tipo, no, props);
        no.dispatchEvent(ev);
        return ev;
    };
    const htmlDe = (markup) => __domNosDeHtml(String(markup == null ? "" : markup), (tag) => doc.createElement(tag));

    const retorno = {
        document: doc,
        window: janela,
        body: corpo,
        el,
        criar: (tag, props, ...filhos) => el(tag, props, ...filhos),
        porId: (id) => doc.getElementById(id),
        sel: (seletor) => doc.querySelector(seletor),
        selTodos: (seletor) => doc.querySelectorAll(seletor),
        medir,
        estilo,
        evento,
        disparar,
        html: htmlDe,
        serializar: (no) => (no && no.outerHTML) || "",
        agora: executarQuadros,
        aguardar: async (voltas) => {
            const total = voltas || 2;
            for (let i = 0; i < total; i++) {
                await new Promise((resolve) => setTimeout(resolve, 0));
                executarQuadros();
            }
        },
        Elemento: __DomElemento,
        Documento: __DomDocumento,
        Texto: __DomTexto,
        instalar: null,
        remover: null,
    };
    const instalados = [];
    const definir = (nome, valor) => { if (__domDefinirGlobal(nome, valor)) instalados.push(nome); };
    retorno.instalar = () => {
        definir("document", doc);
        definir("window", janela);
        definir("self", janela);
        definir("HTMLElement", __DomElemento);
        definir("Element", __DomElemento);
        definir("Node", __DomNo);
        definir("Document", __DomDocumento);
        definir("Event", __DomEvento);
        definir("CustomEvent", __DomEvento);
        definir("MouseEvent", __DomEvento);
        definir("KeyboardEvent", __DomEvento);
        definir("PointerEvent", __DomEvento);
        definir("getComputedStyle", janela.getComputedStyle);
        definir("requestAnimationFrame", janela.requestAnimationFrame);
        definir("cancelAnimationFrame", janela.cancelAnimationFrame);
        definir("matchMedia", janela.matchMedia);
        definir("localStorage", janela.localStorage);
        definir("location", janela.location);
        return retorno;
    };
    retorno.remover = () => {
        for (const nome of instalados) {
            try { delete globalThis[nome]; } catch (_erro) { /* global nao removivel (ex: navigator) */ }
        }
        instalados.length = 0;
        if (__domDocumentoAtual === doc) __domDocumentoAtual = null;
        return retorno;
    };
    if (cfg.instalar !== false) retorno.instalar();
    return retorno;
};
'''

def _snippet_python(codigo, raiz_projeto):
    """Codigo do agente com o cabecalho que o poe no ambiente certo.

    O cabecalho resolve o que eu repetia a mao em cada script de prova: sys.path
    com a raiz do Axio (para importar src.backend), sys.path com a raiz do projeto
    aberto, cwd nessa pasta e stdout/stderr em utf-8 (no Windows o subprocesso
    escreve em cp1252 e os acentos chegavam corrompidos ao relatorio).
    """
    return _CABECALHO_PYTHON.format(raiz_app=APP_ROOT, raiz_projeto=raiz_projeto) + codigo + "\n"

_NOMES_DO_CABECALHO_JS = frozenset({"process", "fs", "path", "assert", "importarProjeto", "__paraUrl", "__juntar"})
_INICIO_IMPORT_JS = re.compile(r"^\s*import\b")
_LIGACOES_IMPORT_JS = re.compile(r"^\s*import\s+(?:([\w$]+)\s*,?\s*)?(?:\*\s+as\s+([\w$]+)|\{([^}]*)\})\s*from\b")
_LIGACAO_DIRETA_JS = re.compile(r"^\s*import\s+([\w$]+)\s+from\b")

def _ligacoes_do_import(instrucao):
    achado = _LIGACOES_IMPORT_JS.match(instrucao)
    if achado:
        nomes = set()
        if achado.group(1):
            nomes.add(achado.group(1))
        if achado.group(2):
            nomes.add(achado.group(2))
        if achado.group(3):
            for parte in achado.group(3).split(","):
                if parte.strip():
                    nomes.add(parte.strip().split(" as ")[-1].strip())
        return nomes
    achado = _LIGACAO_DIRETA_JS.match(instrucao)
    return {achado.group(1)} if achado else set()

def _sem_imports_repetidos(codigo):
    """Larga do trecho os imports que o cabecalho ja declara (repeti-los rebenta o ficheiro
    com 'Identifier already declared'). So larga a instrucao quando TODOS os nomes que ela
    liga ja vem do cabecalho: import de outro modulo, ou de nomes novos do mesmo modulo,
    fica intacto.
    """
    linhas = codigo.splitlines(keepends=True)
    saida = []
    indice = 0
    while indice < len(linhas):
        linha = linhas[indice]
        if _INICIO_IMPORT_JS.match(linha):
            instrucao = linha
            fim = indice
            while ("from" not in instrucao
                   and instrucao.count("{") > instrucao.count("}")
                   and fim + 1 < len(linhas)):
                fim += 1
                instrucao += linhas[fim]
            ligacoes = _ligacoes_do_import(instrucao)
            if ligacoes and ligacoes <= _NOMES_DO_CABECALHO_JS:
                indice = fim + 1
                continue
        saida.append(linha)
        indice += 1
    return "".join(saida)

def _snippet_js(codigo, raiz_projeto):
    """Cabecalho do trecho JavaScript: poe o cwd na raiz do projeto aberto, para os
    caminhos relativos do trecho serem os mesmos que o agente usa nas ferramentas, e
    injeta criarDomFalso() (document/window minimos) para nao reescrever o stub de DOM
    em cada harness.
    """
    cabecalho = _CABECALHO_JS.replace("{RAIZ_JS}", json.dumps(raiz_projeto or ""))
    return cabecalho + _DOM_FALSO_JS + _sem_imports_repetidos(codigo) + "\n"

def _aviso_harness_velho():
    """O processo importou este modulo no arranque: se o ficheiro no disco for mais novo, o cabecalho
    injetado e o antigo e o trecho mente sobre o codigo de agora - o sintoma tipico e um auxiliar que
    existe no disco e da ReferenceError a correr.
    """
    try:
        editado = os.path.getmtime(os.path.abspath(__file__))
    except OSError:
        return ""
    if editado <= _ARRANQUE:
        return ""
    minutos = max(1, int((editado - _ARRANQUE) / 60))
    return ("AVISO: este harness foi editado ha ~" + str(minutos) + "min e o processo em curso ainda corre "
            "a versao de antes - Ctrl+Shift+B para entrar em vigor (o resultado abaixo pode nao refletir "
            "o ficheiro atual).")

def _relatorio_execucao(proc, limite, linguagem):
    veredito = "OK" if proc.returncode == 0 else f"FALHOU (codigo de saida {proc.returncode})"
    partes = [f"TRECHO {linguagem}: {veredito} | limite {limite}s | ficheiro temporario apagado",
              "--- stdout ---",
              recortar_texto(proc.stdout) or "(vazio)"]
    aviso = _aviso_harness_velho()
    if aviso:
        partes.insert(0, aviso)
    erro = recortar_texto(proc.stderr)
    if erro:
        partes.append("--- stderr ---")
        partes.append(erro)
    return "\n".join(partes)

_PREFIXOS_DE_PREPARO = ("import ", "from ", "#")

def _rotulo_teste(trecho, padrao):
    """Primeira linha que diz o que o trecho FAZ - os imports ficam de fora - para o
    terminal identificar o que esta a correr (o relatorio continua a voltar inteiro)."""
    primeira = ""
    for linha in trecho.splitlines():
        limpa = linha.strip()
        if not limpa:
            continue
        primeira = primeira or limpa
        if not limpa.startswith(_PREFIXOS_DE_PREPARO):
            return limpa[:100]
    return primeira[:100] or padrao

def _espelhar_teste_no_terminal(pid, proc):
    """Publica no terminal da doc a saida do trecho, para o utilizador acompanhar o
    que corre. E so espelho: o resultado continua a voltar inteiro para o modelo."""
    saida = proc.stdout or ""
    erro = proc.stderr or ""
    if erro.strip():
        saida = f"{saida}\n--- stderr ---\n{erro}"
    texto = recortar_texto(saida) or "(sem saida)"
    emit_event("process_output", pid=pid, chunk=texto + "\n")
    emit_event("process_finished", pid=pid, exit_code=proc.returncode,
               status="ok" if proc.returncode == 0 else "erro")

def _interpretador_python():
    return sys.executable

def _interpretador_node():
    return shutil.which("node")

_TRECHOS = {
    "python": {
        "rotulo": "trecho Python",
        "linguagem": "PYTHON",
        "executavel": "python",
        "prefixo": _PREFIXO_TEMP_PYTHON,
        "sufixo": ".py",
        "snippet": _snippet_python,
        "interpretador": _interpretador_python,
    },
    "javascript": {
        "rotulo": "trecho JavaScript",
        "linguagem": "JAVASCRIPT",
        "executavel": "node",
        "prefixo": _PREFIXO_TEMP_JS,
        "sufixo": ".mjs",
        "snippet": _snippet_js,
        "interpretador": _interpretador_node,
    },
}

def _correr_trecho(chave, trecho, timeout, rotulo=""):
    """Escreve o trecho num ficheiro temporario do sistema, corre-o num processo novo
    com timeout que mata a arvore, apaga o ficheiro e devolve o relatorio."""
    cfg = _TRECHOS[chave]
    interpretador = cfg["interpretador"]()
    if not interpretador:
        return (f"ERRO: o '{cfg['executavel']}' nao esta no PATH desta maquina, logo nao ha como "
                "correr um trecho desta linguagem.")
    try:
        limite = max(1, min(int(timeout or 60), _TIMEOUT_TRECHO_MAX))
    except (TypeError, ValueError):
        limite = 60
    raiz_projeto = estado.get("pasta_raiz") or APP_ROOT
    pid = id_processo()
    emit_event("executing", function=f"Executando {cfg['rotulo']} em processo novo")
    emit_event("process_started", pid=pid,
               comando=f"{cfg['executavel']} {(rotulo or '').strip() or _rotulo_teste(trecho, cfg['rotulo'])}",
               modo="aguardar")
    fd, caminho = tempfile.mkstemp(prefix=cfg["prefixo"], suffix=cfg["sufixo"])
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(cfg["snippet"](trecho, raiz_projeto))
        proc = run_com_timeout([interpretador, caminho], timeout=limite)
    except subprocess.TimeoutExpired:
        emit_event("process_finished", pid=pid, exit_code=None, status="timeout")
        return (f"ERRO: o trecho passou de {limite}s e a arvore de processos foi encerrada. Se o codigo "
                "abria um servidor ou um loop sem fim, e esse o motivo; nada do projeto foi alterado.")
    except OSError as e:
        emit_event("process_finished", pid=pid, exit_code=None, status="erro")
        return f"ERRO: nao consegui executar o trecho ({e})."
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass
    _espelhar_teste_no_terminal(pid, proc)
    return _relatorio_execucao(proc, limite, cfg["linguagem"])

@register(
    "tool_executar_python",
    "Corre um trecho de codigo Python NUM PROCESSO NOVO (o mesmo interpretador que corre o Axio) e "
    "devolve stdout, stderr e o codigo de saida. O trecho vai para um ficheiro temporario do sistema "
    "e e apagado no fim, por isso nada fica na pasta do projeto. E o caminho para PROVAR comportamento "
    "(um assert sobre a funcao real, um calculo, um resultado do despacho) em vez de criar scripts de "
    "prova na raiz. Nao substitui as ferramentas nativas: ler/editar/buscar/validar sintaxe tem "
    "ferramenta propria e a app Flask a responder tem tool_auditar_rotas.",
    {
        "codigo": {"tipo": "STRING", "obrig": True, "desc": "Codigo Python a executar (varios imports e asserts sao bem-vindos)"},
        "timeout": {"tipo": "INTEGER", "desc": "Segundos maximos (default 60, teto 300)", "padrao": 60},
        "rotulo": {"tipo": "STRING", "desc": "Nome curto do que este trecho faz, para o card do terminal (ex: 'Bluesky: criar a app password'). Sem ele o card mostra a primeira linha com conteudo - e como quase todos os trechos comecam por imports iguais, probes distintos ficam com o mesmo nome e parecem o mesmo a repetir-se.", "padrao": ""},
    },
)
def tool_executar_python(codigo, timeout=60, rotulo=""):
    trecho = (codigo or "").strip()
    if not trecho:
        return "ERRO: 'codigo' vazio. Informe o trecho Python a executar."
    return _correr_trecho("python", trecho, timeout, rotulo)

@register(
    "tool_executar_js",
    "Corre um trecho de codigo JavaScript (Node, ESM) NUM PROCESSO NOVO e devolve stdout, stderr e o "
    "codigo de saida. O trecho vai para um ficheiro temporario do sistema (.mjs) e e apagado no fim, "
    "por isso nada fica na pasta do projeto. E o espelho do tool_executar_python para o frontend: use "
    "para PROVAR comportamento em JS - um assert sobre uma funcao real lida do disco, um stub de DOM/"
    "globais, a comparacao de duas versoes do mesmo codigo na mesma cena. Tem 'import' de node:fs, "
    "node:path, node:assert e node:child_process, e top-level await; os caminhos relativos sao a raiz "
    "do projeto aberto. Para ler o repositorio git do projeto use gitDoDisco(['log', ...]) - corre o git "
    "SEM shell, por isso o '%' de um --pretty=format:%cI chega intacto (num execSync do Windows o cmd.exe "
    "come-o e o erro nao aponta para o formato). "
    "O cabecalho ja injeta criarDomFalso() - um document/window minimos prontos a usar em vez de "
    "reescrever o stub de DOM a mao (as armadilhas conhecidas ja vem resolvidas: insertBefore/"
    "appendChild soltam o no do pai, className e classList sao a mesma fonte, toggle respeita a "
    "forca, getBoundingClientRect e calculado no pedido a partir de offset*/dom.medir, "
    "replaceWith/before/after existem nos dois tipos de no, e dispatchEvent propaga em "
    "captura->alvo->bolha; o que ele NAO tem e TreeWalker/NodeFilter, por isso para percorrer os "
    "nos de texto de um elemento use childNodes a mao). Para ler o que foi pintado use dom.serializar"
    "(el) ou el.outerHTML - dom.html e o INVERSO (monta nos a partir de markup, nao serializa) e "
    "DEVOLVE UM ARRAY DE NOS SOLTOS, que so aparecem ao querySelector depois de anexados ao body. "
    "A propria chamada de criarDomFalso() INSTALA os globais document/window (usar 'document' sem a "
    "chamar da ReferenceError) e o valor devolvido traz el, sel, selTodos, porId, disparar, estilo, "
    "medir, agora e aguardar - document.querySelector/querySelectorAll funcionam, por isso NAO "
    "escreva um mini-DOM a mao para testar uma funcao que navega o DOM: monte a cena com dom.el(...) "
    "e navegue-a com dom.sel/dom.selTodos. "
    "Antes de importar um modulo grande do frontend so para testar uma funcao, saiba que o state.js "
    "le o DOM ao importar: se rebentar, extraia o texto da funcao do disco e avalie-a isolada. "
    "PARA EXTRAIR UMA FUNCAO REAL DO DISCO o cabecalho ja traz o auxiliar: funcaoDoDisco('src/x.js', "
    "'nome') devolve o TEXTO da funcao, uma STRING - NAO uma funcao (chamar o que ela devolve da "
    "TypeError '... is not a function'). Para a poder chamar, envolva-a: new Function(texto + "
    "' return nome;')() - ou, tendo dependencias, new Function('DEP1', texto + ' return {nome};')(dep). "
    "O texto vem EXATO (com o async a frente quando existir) e funcoesDoDisco('src/x.js', 'a', 'b') "
    "junta varias na ordem pedida (o caminho e relativo a raiz do projeto ou absoluto) - nao "
    "reescreva o balanceamento de chaves a mao, que esquecer o "
    "async de uma funcao assincrona da um SyntaxError que nao aponta para a causa. "
    "ATENCAO: no harness (ESM, modo estrito) o eval direto cria SEMPRE "
    "o seu proprio escopo, mesmo para var, logo uma constante ou funcao avaliada num eval NAO fica "
    "visivel para o eval seguinte - a funcao extraida rebenta com ReferenceError ao ser chamada. Use "
    "new Function('DEP1', 'DEP2', funcoesDoDisco(...) + 'return {a, b};')(dep1, dep2), passando as "
    "dependencias como argumentos; foi assim que se descobriu que lerZoomPersistido depende de "
    "normalizarZoom. "
    "O ficheiro corre na pasta TEMPORARIA do sistema: um import RELATIVO ('./x.js') nao resolve de la e "
    "rebenta com ERR_MODULE_NOT_FOUND. O cwd, esse, e a raiz do projeto - monte o caminho absoluto com "
    "path.join(process.cwd(), 'src/frontend/js/x.js') e importe pathToFileURL(esse).href.",
    {
        "codigo": {"tipo": "STRING", "obrig": True, "desc": "Codigo JavaScript (ESM) a executar (imports e asserts sao bem-vindos). Imports de modulos do projeto tem de ser por caminho ABSOLUTO: use pathToFileURL(path.join(process.cwd(), 'src/...')).href"},
        "timeout": {"tipo": "INTEGER", "desc": "Segundos maximos (default 60, teto 300)", "padrao": 60},
        "rotulo": {"tipo": "STRING", "desc": "Nome curto do que este trecho faz, para o card do terminal (ex: 'Provar o arredondamento das abas'). Sem ele o card fica com a primeira linha do codigo, que quase sempre e um import - igual ao de todos os outros.", "padrao": ""},
    },
)
def tool_executar_js(codigo, timeout=60, rotulo=""):
    trecho = (codigo or "").strip()
    if not trecho:
        return "ERRO: 'codigo' vazio. Informe o trecho JavaScript a executar."
    return _correr_trecho("javascript", trecho, timeout, rotulo)
