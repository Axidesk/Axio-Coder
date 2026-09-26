"""Mede o que o browser PINTA de facto (Electron + captura de pixels + Pillow).

Porque existe: metade dos defeitos visuais do painel so aparecem na pintura, nao no
codigo - guias de 1px com lacunas (o paint containment do content-visibility recorta
a tinta), cores que mudam de tom, um elemento que se desloca 1px. Ler o CSS nao
prova nada disso; medir o pixel prova. Antes disto eu montava o harness a mao em
cada rodada (pagina de teste + main.js do Electron + leitura com Pillow); agora e
uma chamada.

O que faz: carrega o CSS REAL do frontend do Axio numa pagina de teste (o do pedido,
ou todos os ficheiros de src/frontend), renderiza num Electron fora do ecra, faz
capturePage, e devolve tres coisas:
  * GEOMETRIA - getBoundingClientRect de cada elemento que casa com `seletores`,
    com o ::before/::after computados (medidas e cor), para ver a fiacao do CSS;
  * PALETA - as cores pintadas (nº de pixels + caixa de cada uma), sem o `fundo`,
    para descobrir tons inesperados; as cores PEDIDAS em `cor` entram sempre, mesmo
    com poucos pixels (o nucleo de um glifo pequeno nunca fica fora da lista);
  * DESENHO - com `cor`, o mapa traco a traco dessas cores: por coluna e por linha,
    com os troços contiguos (e e assim que se ve uma linha de 1px interrompida).
    Aceita VARIAS cores separadas por ';' - mede a tinta de varios elementos (o texto
    e o + de um cabecalho, por exemplo) numa so chamada.

O PNG fica num temporario do sistema (nada e escrito na pasta do projeto) e o
caminho e devolvido; com manter_png=True o temporario nao e apagado no fim.
"""

import os
import json
import re
import shutil
import tempfile
import subprocess

from src.backend.tools.registry import register
from src.backend.state import emit_event

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ_AXIO = os.path.abspath(os.path.join(_AQUI, "..", "..", ".."))
_FRONTEND = os.path.join(_RAIZ_AXIO, "src", "frontend")
_ELECTRON = os.path.join(_RAIZ_AXIO, "node_modules", "electron", "dist", "electron.exe")
TIMEOUT_PINTURA = 180.0
TAILWIND_CDN = "https://cdn.tailwindcss.com"
ESPERA_TAILWIND_MS = 5000
MAX_ELEMENTOS = 40
MAX_TONS = 12
MAX_TROCOS = 24


def _css_do_frontend():
    """style.css (tokens/):root) primeiro, depois os ficheiros de css/ por ordem."""
    ficheiros = [os.path.join(_FRONTEND, "style.css")]
    pasta = os.path.join(_FRONTEND, "css")
    if os.path.isdir(pasta):
        ficheiros += [os.path.join(pasta, n) for n in sorted(os.listdir(pasta))
                      if n.endswith(".css")]
    return [f for f in ficheiros if os.path.exists(f)]


_ATRIBUTO_CLASS = re.compile(r'class\s*=\s*"([^"]*)"')


def _classes_fora_do_css(html, estilo, ficheiros_css):
    """Classes usadas no HTML/estilo que NAO existem em nenhuma folha carregada.

    Sao as utilitarias do Tailwind: quem as aplica e o CDN, a correr na propria
    pagina. Sem ele, um elemento estilizado so por elas fica com a geometria de
    origem - e o relatorio tem de dizer QUAIS, porque uma medida vinda do Tailwind
    (w-[35%], w-80, flex-1) mente em silencio: foi assim que uma medicao deu "sem
    folga" numa coluna que no produto tem 20px dela. Uma classe que exista em
    qualquer folha do projeto nao entra na lista (essa aplica-se sempre).
    """
    usadas = []
    for achado in _ATRIBUTO_CLASS.finditer(html + "\n" + estilo):
        for classe in achado.group(1).split():
            if classe and classe not in usadas:
                usadas.append(classe)
    folhas = ""
    for caminho in ficheiros_css:
        try:
            with open(caminho, encoding="utf-8") as f:
                folhas += f.read()
        except OSError:
            continue
    alvo = (folhas + "\n" + estilo).replace("\\", "")
    return [c for c in usadas
            if not re.search(r"\." + re.escape(c) + r"(?![A-Za-z0-9_-])", alvo)]


_USO_DE_VARIAVEL = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")


def _variaveis_sem_valor(html, estilo, ficheiros_css):
    """Variaveis CSS usadas na medicao que nenhuma folha carregada define.

    Uma folha que use var(--oliva) sem que ninguem defina --oliva cai no valor
    HERDADO, e o browser nao reclama de uma variavel ausente: a cor sai outra e
    a paleta nao e a do produto, em silencio. Foi assim que uma medicao devolveu
    uma grelha de cinzentos onde se esperava o verde da etiqueta acesa - sem
    este aviso, o defeito parece estar no CSS que se esta a medir.
    """
    folhas = ""
    for caminho in ficheiros_css:
        try:
            with open(caminho, encoding="utf-8") as f:
                folhas += f.read()
        except OSError:
            continue
    texto = folhas + "\n" + estilo + "\n" + html
    usadas = []
    for nome in _USO_DE_VARIAVEL.findall(texto):
        if nome not in usadas:
            usadas.append(nome)
    return [n for n in usadas if not re.search(re.escape(n) + r"\s*:", texto)]


def _url(caminho):
    return "file:///" + os.path.abspath(caminho).replace("\\", "/")


def _pagina(html, estilo, ficheiros_css):
    """Monta a pagina de teste. Concatenacao (e nao %-format) para o CSS do pedido
    poder trazer % e chaves sem quebrar nada."""
    partes = ["<!doctype html><html lang='pt'><head><meta charset='utf-8'>"]
    partes.append("<script src='" + TAILWIND_CDN + "'></script>")
    for caminho in ficheiros_css:
        partes.append("<link rel='stylesheet' href='" + _url(caminho) + "'>")
    partes.append("<style>" + estilo + "</style></head><body>")
    partes.append(html)
    partes.append("</body></html>")
    return "".join(partes)


def _lista_de_seletores(seletores):
    """Varios seletores (um por linha ou por virgula) viram uma lista CSS."""
    partes = []
    for linha in (seletores or "").splitlines():
        partes.extend(p.strip() for p in linha.split(","))
    return ", ".join(p for p in partes if p) or "[class]"


def _sonda_js(seletores):
    """JS que corre na pagina e devolve a geometria real dos elementos."""
    return """
(() => {
  const sel = %s;
  const out = [];
  let i = 0;
  const quatro = (a, b, c, d) => [a, b, c, d].map(v => {
    const n = parseFloat(v);
    return isNaN(n) ? v : Math.round(n * 10) / 10;
  }).join('/');
  const deslocamento = el => {
    const tr = getComputedStyle(el).transform;
    if (!tr || tr === 'none') return '';
    const m = tr.match(/^matrix\\(([^)]+)\\)$/);
    if (!m) return 'nao-matricial';
    const p = m[1].split(',').map(Number);
    return (p[4] || p[5]) ? p[4].toFixed(1) + ',' + p[5].toFixed(1) : '';
  };
  document.querySelectorAll(sel).forEach(el => {
    if (i++ >= %d) return;
    const r = el.getBoundingClientRect();
    const b = getComputedStyle(el, '::before');
    const a = getComputedStyle(el, '::after');
    const pseudo = p => (p.content && p.content !== 'none')
      ? p.width + 'x' + p.height + ' @ ' + p.top + ',' + p.left + ' bg=' + p.background.slice(0, 24)
      : '';
    const cs = getComputedStyle(el);
    out.push({ tag: el.tagName.toLowerCase(), classe: String(el.className).slice(0, 70),
               x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1),
               desloc: deslocamento(el),
               margem: quatro(cs.marginTop, cs.marginRight, cs.marginBottom, cs.marginLeft),
               espaco: quatro(cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft),
               antes: pseudo(b), depois: pseudo(a) });
  });
  return JSON.stringify({ pagina: [document.body.scrollWidth, document.body.scrollHeight],
                          raiz: getComputedStyle(document.documentElement).fontSize, rects: out });
})()
""" % (json.dumps(_lista_de_seletores(seletores)), MAX_ELEMENTOS)


def _main_js(sonda):
    return """
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path');
// O frontend estiliza-se sobretudo por classes utilitarias e o Tailwind entra por
// CDN, a correr na propria pagina: enquanto ele nao aplicar, 'p-10' nao vale 40px
// e a geometria medida nao e a do produto. A prova e o PADDING (e nao o 'hidden',
// que ja deu falso positivo: qualquer regra do projeto o satisfazia). O resultado
// vai para tw.txt, para o relatorio poder avisar quando a medicao nao e a do
// produto.
const ESPERA_TW = `
  new Promise(res => {
    const d = document.createElement('div');
    d.className = 'p-10';
    d.style.position = 'absolute';
    d.style.left = '-9999px';
    document.body.appendChild(d);
    const t0 = Date.now();
    const passo = () => {
      if (getComputedStyle(d).paddingTop === '40px') { d.remove(); return res('aplicado'); }
      if (Date.now() - t0 > __ESPERA__) { d.remove(); return res('ausente'); }
      setTimeout(passo, 100);
    };
    passo();
  })
`;
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: __W__, height: __H__, x: -3000, y: -3000, show: true,
      frame: false, backgroundColor: '#1e1e1e', webPreferences: { backgroundThrottling: false } });
  await win.loadFile(path.join(__dirname, 'index.html'));
  await new Promise(r => setTimeout(r, 800));
  fs.writeFileSync(path.join(__dirname, 'tw.txt'), await win.webContents.executeJavaScript(ESPERA_TW));
  fs.writeFileSync(path.join(__dirname, 'geo.json'), await win.webContents.executeJavaScript(__SONDA__));
  fs.writeFileSync(path.join(__dirname, 'capture.png'), (await win.webContents.capturePage()).toPNG());
  app.quit();
});
""".replace("__SONDA__", json.dumps(sonda)).replace("__ESPERA__", str(int(ESPERA_TAILWIND_MS)))


def _espacos_do_elemento(r):
    """Margem e padding de um elemento medido, quando algum nao e zero.

    A geometria diz a CAIXA de cada elemento, nunca a COSTURA entre dois: um espaco
    grande entre dois blocos pode vir do margin-bottom do primeiro, do margin-top do
    segundo ou de um gap do pai, e descobri-lo por tentativa custa uma medicao por
    hipotese. Esta linha responde-o com o valor real.
    """
    partes = []
    if r.get("margem") and r["margem"] != "0/0/0/0":
        partes.append("margem cima/dir/baixo/esq %s" % r["margem"])
    if r.get("espaco") and r["espaco"] != "0/0/0/0":
        partes.append("padding cima/dir/baixo/esq %s" % r["espaco"])
    if not partes:
        return ""
    return "         " + "; ".join(partes) + "  (o espaco entre este elemento e os vizinhos vem daqui)"


def _cor_hex(texto, padrao):
    """'#ff0000' -> (255,0,0); string vazia -> padrao."""
    t = (texto or "").strip().lstrip("#")
    if not t:
        return padrao
    try:
        return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return padrao


def _cores(texto):
    """'#ff0000;#00ff00' -> [(255,0,0),(0,255,0)]; string vazia -> []."""
    cores = []
    for parte in (texto or "").replace(",", ";").split(";"):
        c = _cor_hex(parte, None)
        if c and c not in cores:
            cores.append(c)
    return cores


def _troços(valores):
    """Compressao de inteiros ordenados em intervalos contiguos."""
    out = []
    for v in valores:
        if out and v - out[-1][-1] <= 1:
            out[-1].append(v)
        else:
            out.append([v])
    return out


def _paleta(px, W, H, fundo, obrigatorias=()):
    """Cores pintadas (nº de pixels + caixa) por ordem de quantidade, com o total de tons.

    As cores de `obrigatorias` ficam sempre na lista, mesmo fora do topo por quantidade.
    """
    tons = {}
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            if c == fundo:
                continue
            t = tons.setdefault(c, [0, x, y, x, y])
            t[0] += 1
            t[1] = min(t[1], x)
            t[2] = min(t[2], y)
            t[3] = max(t[3], x)
            t[4] = max(t[4], y)
    topo = sorted(tons.items(), key=lambda kv: -kv[1][0])[:MAX_TONS]
    nomes = {k for k, _ in topo}
    fora = [c for c in obrigatorias if c in tons and c not in nomes]
    return topo + [(c, tons[c]) for c in fora], len(tons)


def _desenho(px, W, H, alvo):
    """Mapa traco a traco de uma cor: colunas e linhas com troços contiguos."""
    colunas, linhas = {}, {}
    for y in range(H):
        for x in range(W):
            if px[x, y] != alvo:
                continue
            colunas.setdefault(x, []).append(y)
            linhas.setdefault(y, []).append(x)
    resumo_col = sorted(colunas.items(), key=lambda kv: -len(kv[1]))[:MAX_TROCOS]
    resumo_lin = sorted(linhas.items(), key=lambda kv: -len(kv[1]))[:MAX_TROCOS]
    return resumo_col, resumo_lin


@register(
    "tool_medir_pintura",
    "Renderiza HTML com o CSS real do frontend do Axio num Electron fora do ecra e le os PIXEIS do que foi pintado: desenho traco a traco de uma cor (colunas e linhas, com lacunas), paleta de cores com a caixa de cada uma, e a geometria real dos elementos (clienteRect + ::before/::after computados). Usa quando a duvida e o que o browser PINTA (linha de 1px cortada, tom diferente, elemento deslocado), e nao o que o CSS diz. TEXTO NA PALETA VEM COM FRANJAS DE SUBPIXEL (duas cores lado a lado nas mesmas coordenadas, tipicamente um par azul/vermelho) porque o Chromium desenha glifos com antialiasing subpixel: nao leia a cor do glifo como se fosse a cor do elemento. Para medir a OPACIDADE de um texto, compare a cor pintada com a MISTURA esperada - opacidade*cor_do_texto + (1-opacidade)*fundo; ex: --text-suave #9ca3af a 40% sobre #1e1e1e da #505358 (0.4*156+0.6*30=80=0x50). A paleta serve para FORMAS (fundos, bordas, linhas); o mapa de uma cor (parametro 'cor') tambem.",
    {
        "html": {"tipo": "STRING", "desc": "Markup a medir (o corpo da pagina de teste).", "obrig": True, "padrao": ""},
        "estilo": {"tipo": "STRING", "desc": "Texto de CSS extra, injetado depois dos ficheiros (ex: ':root{--border-suave:#ff0000}').", "obrig": False, "padrao": ""},
        "css": {"tipo": "STRING", "desc": "CAMINHOS de ficheiros CSS do projeto, separados por virgula (ex: 'src/frontend/css/dock.css') e nao o texto das regras - o texto vai no 'estilo'; vazio = style.css + css/*.css do frontend.", "obrig": False, "padrao": ""},
        "cor": {"tipo": "STRING", "desc": "Cor alvo do mapa de desenho, em hex sem # (ex: 'ff0000'). Aceita VARIAS separadas por ';' (ex: 'ff0000;00ff00') - cada uma sai com o seu mapa e entra SEMPRE na paleta, mesmo com poucos pixels. Vazio = so paleta e geometria.", "obrig": False, "padrao": ""},
        "fundo": {"tipo": "STRING", "desc": "Cor de fundo a ignorar na paleta, hex sem # (padrao '1e1e1e').", "obrig": False, "padrao": "1e1e1e"},
        "seletores": {"tipo": "STRING", "desc": "Seletor CSS dos elementos cuja geometria medir (padrao '[class]'); aceita VARIOS, um por linha ou separados por virgula.", "obrig": False, "padrao": ""},
        "largura": {"tipo": "INTEGER", "desc": "Largura da janela em px (padrao 460).", "obrig": False, "padrao": 460},
        "altura": {"tipo": "INTEGER", "desc": "Altura da janela em px (padrao 900).", "obrig": False, "padrao": 900},
        "manter_png": {"tipo": "BOOLEAN", "desc": "Nao apagar o temporario (o caminho do PNG fica no resultado).", "obrig": False, "padrao": False},
    },
    disponivel="edicao",
)
def tool_medir_pintura(html, estilo="", css="", cor="", fundo="1e1e1e",
                       seletores="", largura=460, altura=900, manter_png=False):
    emit_event("executing", function="Medindo o desenho")
    if not os.path.exists(_ELECTRON):
        return f"ERRO: Electron nao encontrado em {_ELECTRON}."
    try:
        from PIL import Image  # import-local: Pillow so serve esta medicao (carga tardia)
    except ImportError:
        return "ERRO: Pillow nao instalado no ambiente do Axio (pip install pillow)."
    ficheiros = [f.strip() for f in (css or "").split(",") if f.strip()] or _css_do_frontend()
    em_falta = [f for f in ficheiros if not os.path.exists(f)]
    if em_falta:
        return "ERRO: CSS nao encontrado: " + ", ".join(em_falta)

    tmp = tempfile.mkdtemp(prefix="axio_pintura_")
    try:
        with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
            f.write(_pagina(html, estilo or "", ficheiros))
        with open(os.path.join(tmp, "main.js"), "w", encoding="utf-8") as f:
            f.write(_main_js(_sonda_js(seletores)).replace("__W__", str(int(largura))).replace("__H__", str(int(altura))))
        proc = subprocess.run([_ELECTRON, os.path.join(tmp, "main.js")],
                              capture_output=True, text=True, errors="replace",
                              timeout=TIMEOUT_PINTURA, cwd=tmp)
        png = os.path.join(tmp, "capture.png")
        if not os.path.exists(png):
            cauda = (proc.stderr or proc.stdout or "")[-400:]
            return "ERRO: o Electron nao produziu imagem. " + cauda

        im = Image.open(png).convert("RGB")
        W, H = im.size
        px = im.load()
        alvos = _cores(cor)
        fundo_rgb = _cor_hex(fundo, (30, 30, 30))

        linhas = ["PINTURA MEDIDA: imagem %dx%d | CSS: %s" % (W, H, ", ".join(os.path.basename(f) for f in ficheiros))]
        tw = os.path.join(tmp, "tw.txt")
        if os.path.exists(tw):
            with open(tw, encoding="utf-8") as f:
                estado_tw = f.read().strip()
            if estado_tw == "aplicado":
                linhas.append("Tailwind (CDN): utilitarias aplicadas (sonda p-10 = 40px) - a geometria de quem depende de classes e a do produto.")
            else:
                linhas.append("AVISO: as classes utilitarias do Tailwind (CDN) NAO entraram nesta medicao -")
                linhas.append("       a geometria de elementos estilizados SO por classes (p-4, text-sm, grid...) nao e a do produto.")
                fora = _classes_fora_do_css(html, estilo, ficheiros)
                if fora:
                    linhas.append("       CLASSES SEM EFEITO NESTA MEDICAO (%d): %s"
                                  % (len(fora), ", ".join(fora[:14]) + (" ..." if len(fora) > 14 else "")))
                    linhas.append("       (largura, altura ou display vindos dalguma delas NAO foram aplicados:"
                                  " nao se tira conclusao de uma folga medida com elas)");
        sem_valor = _variaveis_sem_valor(html, estilo or "", ficheiros)
        if sem_valor:
            linhas.append("AVISO: %d variavel(eis) CSS usada(s) nesta medicao nao esta(o) definida(s) em nenhuma folha carregada: %s"
                          % (len(sem_valor), ", ".join(sem_valor[:14]) + (" ..." if len(sem_valor) > 14 else "")))
            linhas.append("       As regras que dependem delas caem no valor HERDADO, logo a paleta nao e a do produto."
                          " Carregue a folha que as define (no Axio o :root vive no style.css).")

        geo = os.path.join(tmp, "geo.json")
        if os.path.exists(geo):
            with open(geo, encoding="utf-8") as f:
                dados = json.load(f)
            raiz = dados.get("raiz", "")
            if raiz and raiz != "16px":
                linhas.append("AVISO: o font-size do root nesta medicao e %s, logo 1rem deixou de valer 16px -"
                              " os valores em rem NAO comparam com os do produto." % raiz)
                linhas.append("       Causa habitual: CSS de PAGINAS DIFERENTES misturados na mesma medicao"
                              " (basta um 'font: 13px' num html). Medir cada pagina com o seu CSS.")
            linhas.append("")
            linhas.append("GEOMETRIA (pagina %dx%d, primeiros %d elementos de %s):"
                          % (dados["pagina"][0], dados["pagina"][1], len(dados["rects"]), _lista_de_seletores(seletores)))
            for r in dados["rects"]:
                linhas.append("  %-6s %-40s x=%7.1f y=%7.1f w=%7.1f h=%6.1f" %
                              (r["tag"], r["classe"], r["x"], r["y"], r["w"], r["h"]))
                if r.get("desloc"):
                    if r["desloc"] == "nao-matricial":
                        linhas.append("         ATENCAO: este elemento tem um transform nao-matricial - as medidas acima ja estao transformadas")
                    else:
                        dx, dy = [float(v) for v in r["desloc"].split(",")]
                        linhas.append("         DESLOCADA por transform: a posicao no LAYOUT e x=%.1f y=%.1f (+%.1f x, +%.1f y)"
                                      % (r["x"] - dx, r["y"] - dy, dx, dy))
                if _espacos_do_elemento(r):
                    linhas.append(_espacos_do_elemento(r))
                if r["antes"]:
                    linhas.append("         ::before %s" % r["antes"])
                if r["depois"]:
                    linhas.append("         ::after  %s" % r["depois"])

        tons, total_tons = _paleta(px, W, H, fundo_rgb, alvos)
        linhas.append("")
        cabecalho_paleta = "PALETA (sem o fundo #%02x%02x%02x):" % fundo_rgb
        if total_tons > len(tons):
            cabecalho_paleta += ("  %d tons distintos, mostrados os %d com mais pixels -"
                                 " uma cor pouco pintada (o nucleo de um texto pequeno) pode nao caber"
                                 " nesta lista: confirme-a com o parametro cor." % (total_tons, len(tons)))
        linhas.append(cabecalho_paleta)
        for c, t in tons:
            linhas.append("  #%02x%02x%02x: %6d px, caixa x %d..%d y %d..%d%s" %
                          (c[0], c[1], c[2], t[0], t[1], t[3], t[2], t[4],
                           "   <- cor pedida" if c in alvos else ""))

        for alvo in alvos:
            colunas, linhas_cor = _desenho(px, W, H, alvo)
            linhas.append("")
            linhas.append("DESENHO DA COR #%02x%02x%02x:" % alvo)
            linhas.append("  por coluna (x: pixels, y min..max, troços). [vertical] = traco alto")
            linhas.append("  (uma guia); [cruzamento] = so passa por linhas horizontais:")
            for x, ys in colunas:
                troços = _troços(sorted(set(ys)))
                maior = max(len(t) for t in troços)
                tipo = "vertical" if maior >= 8 else "cruzamento"
                linhas.append("    x=%3d: %4d px, y %d..%d, %d troço(s) [%s] %s" %
                              (x, len(ys), ys[0], ys[-1], len(troços), tipo,
                               [(t[0], t[-1]) for t in troços[:6]]))
            linhas.append("  por linha (y: pixels, x min..max):")
            for y, xs in linhas_cor:
                linhas.append("    y=%3d: %4d px, x %d..%d" % (y, len(xs), min(xs), max(xs)))
        linhas.append("")
        linhas.append("PNG: " + png + (" (temporario mantido)" if manter_png else " (temporario apagado no fim)"))
        return "\n".join(linhas)
    except subprocess.TimeoutExpired:
        return "ERRO: o Electron passou de %ds sem responder." % int(TIMEOUT_PINTURA)
    finally:
        if not manter_png:
            shutil.rmtree(tmp, ignore_errors=True)
