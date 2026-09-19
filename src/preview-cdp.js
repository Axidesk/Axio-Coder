const http = require('http');
const crypto = require('crypto');

const ROTA = '/preview';
const TETO_CORPO_BYTES = 2 * 1024 * 1024;
const TETO_CONSOLA = 400;
const TETO_REDE = 200;
const TETO_PEDIDOS = 500;
const TEMPO_COMANDO_MS = 8000;
const TETO_TEXTO_ENTRADA = 2000;
const PAUSA_CURSOR_MS = 150;
const ESPERA_VISTA_MS = 450;
const ESPERA_RECARGA_MS = 6000;
const ESPERA_EFEITO_MS = 220;
const TETO_EFEITO = 6;
const MARCA_DA_INSPECAO = '__axio_inspecionar__:';
const TOKEN = crypto.randomBytes(24).toString('hex');

let servidor = null;
let porta = 0;
let obterPreview = () => null;
let acoesDeFora = {};
let aoUsar = null;
let aoInspecionar = null;
let inspecaoLigada = false;
let consola = [];
let consolaDescartada = 0;
let rede = [];
let redeDescartada = 0;
let geracaoRegistos = 0;
const pedidos = new Map();
const vigiados = new WeakSet();

const SEM_PAGINA = new Set(['estado', 'consola', 'rede', 'carregar', 'mostrar']);
const ACOES_QUE_AGEM = new Set(['carregar', 'mostrar', 'clicar', 'escrever', 'teclar', 'recarregar']);

const TECLAS = {
  Enter: { key: 'Enter', code: 'Enter', vk: 13, texto: '\r' },
  Tab: { key: 'Tab', code: 'Tab', vk: 9 },
  Escape: { key: 'Escape', code: 'Escape', vk: 27 },
  Backspace: { key: 'Backspace', code: 'Backspace', vk: 8 },
  Delete: { key: 'Delete', code: 'Delete', vk: 46 },
  Space: { key: ' ', code: 'Space', vk: 32, texto: ' ' },
  Home: { key: 'Home', code: 'Home', vk: 36 },
  End: { key: 'End', code: 'End', vk: 35 },
  PageUp: { key: 'PageUp', code: 'PageUp', vk: 33 },
  PageDown: { key: 'PageDown', code: 'PageDown', vk: 34 },
  ArrowUp: { key: 'ArrowUp', code: 'ArrowUp', vk: 38 },
  ArrowDown: { key: 'ArrowDown', code: 'ArrowDown', vk: 40 },
  ArrowLeft: { key: 'ArrowLeft', code: 'ArrowLeft', vk: 37 },
  ArrowRight: { key: 'ArrowRight', code: 'ArrowRight', vk: 39 }
};

const SNIPPET_ALVOS = `(function (parametros) {
  var seletor = parametros.seletor || '';
  var texto = parametros.texto || '';
  var limite = parametros.limite || 20;

  function atributo(el, nome) {
    try { return el.getAttribute ? (el.getAttribute(nome) || '') : ''; } catch (e) { return ''; }
  }

  function limpo(t) {
    return String(t == null ? '' : t).replace(/\\s+/g, ' ').trim();
  }

  function partesDoRotulo(el) {
    var fontes = [el.textContent, el.value, atributo(el, 'aria-label'), atributo(el, 'placeholder'), atributo(el, 'title'), atributo(el, 'alt'), atributo(el, 'name')];
    var juntas = [];
    for (var i = 0; i < fontes.length; i++) {
      var p = limpo(fontes[i]);
      if (p) juntas.push(p);
    }
    return juntas;
  }

  function rotulo(el) {
    var juntas = partesDoRotulo(el);
    for (var i = 0; i < juntas.length; i++) juntas[i] = juntas[i].toLowerCase();
    return juntas.join(' | ');
  }

  function caminhoDe(el) {
    var partes = [];
    var atual = el;
    while (atual && atual.nodeType === 1 && partes.length < 6) {
      var nome = atual.tagName.toLowerCase();
      if (atual.id) { partes.unshift('#' + atual.id); break; }
      var pai = atual.parentNode;
      if (pai && pai.children) {
        var iguais = [];
        for (var i = 0; i < pai.children.length; i++) {
          if (pai.children[i].tagName === atual.tagName) iguais.push(pai.children[i]);
        }
        if (iguais.length > 1) nome += ':nth-of-type(' + (iguais.indexOf(atual) + 1) + ')';
      }
      partes.unshift(nome);
      atual = atual.parentNode;
    }
    return partes.join(' > ');
  }

  function tapa(el, cx, cy) {
    if (cx < 0 || cy < 0 || cx >= window.innerWidth || cy >= window.innerHeight) {
      return { fora_da_janela: true };
    }
    var topo = null;
    try { topo = document.elementFromPoint(cx, cy); } catch (e) { topo = null; }
    if (!topo || topo === el || el.contains(topo)) return null;
    if (topo === document.body || topo === document.documentElement) return null;
    return {
      seletor: caminhoDe(topo),
      etiqueta: topo.tagName.toLowerCase(),
      id: topo.id || '',
      classes: limpo(typeof topo.className === 'string' ? topo.className : '')
    };
  }

  function resumo(el) {
    var r = el.getBoundingClientRect();
    var estilo = window.getComputedStyle(el);
    var largura = Math.round(r.width);
    var altura = Math.round(r.height);
    var pintado = largura > 0 && altura > 0 && estilo.visibility !== 'hidden' && estilo.display !== 'none' && Number(estilo.opacity) !== 0;
    return {
      seletor: caminhoDe(el),
      etiqueta: el.tagName.toLowerCase(),
      id: el.id || '',
      classes: limpo(typeof el.className === 'string' ? el.className : ''),
      rotulo: rotulo(el).slice(0, 200),
      caixa: { x: Math.round(r.left), y: Math.round(r.top), largura: largura, altura: altura },
      centro: { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) },
      dentro_da_janela: r.bottom > 0 && r.right > 0 && r.top < window.innerHeight && r.left < window.innerWidth,
      pintado: pintado,
      tapado_por: pintado ? tapa(el, Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2)) : null
    };
  }

  function porSeletor(lista) {
    var saida = [];
    for (var i = 0; i < lista.length && i < limite; i++) saida.push(resumo(lista[i]));
    return saida;
  }

  var INTERACTIVOS = 'a[href], button, input, textarea, select, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], [role="option"], [role="textbox"], [role="searchbox"], [role="combobox"], [contenteditable]:not([contenteditable="false"]), [onclick], [tabindex]:not([tabindex="-1"])';
  var ANCORAS_POR_VARREDURA = 4000;

  function rotuloCurto(el) {
    var partes = partesDoRotulo(el);
    return partes.length ? partes[0].slice(0, 60) : '';
  }

  function seletorPorDado(el) {
    var atributos = el.attributes || [];
    for (var i = 0; i < atributos.length; i++) {
      var nome = atributos[i].name || '';
      if (nome.slice(0, 5) !== 'data-') continue;
      var valor = atributos[i].value || '';
      if (!valor || valor.length > 80) continue;
      var tentativa = '[' + nome + '="' + valor + '"]';
      var quantos = 0;
      try { quantos = document.querySelectorAll(tentativa).length; } catch (e) { continue; }
      if (quantos === 1) return tentativa;
      if (quantos > 1) {
        var comTag = el.tagName.toLowerCase() + tentativa;
        try { if (document.querySelectorAll(comTag).length === 1) return comTag; } catch (e) {}
      }
    }
    return '';
  }

  function candidatosPorCursor() {
    var todos = [];
    try { todos = document.querySelectorAll('*'); } catch (e) { return []; }
    var cache = new Map();
    var cursorDe = function (no) {
      if (!no) return '';
      if (cache.has(no)) return cache.get(no);
      var c = '';
      try { c = window.getComputedStyle(no).cursor || ''; } catch (e) { c = ''; }
      cache.set(no, c);
      return c;
    };
    var saida = [];
    var fim = Math.min(todos.length, ANCORAS_POR_VARREDURA);
    for (var i = 0; i < fim; i++) {
      var no = todos[i];
      if (cursorDe(no) !== 'pointer') continue;
      if (cursorDe(no.parentElement) === 'pointer') continue;
      saida.push(no);
    }
    return saida;
  }

  function juntarCandidatos(primeiros, segundos) {
    var saida = [];
    var vistos = new Set();
    var juntar = function (lista) {
      for (var i = 0; i < lista.length; i++) {
        if (vistos.has(lista[i])) continue;
        vistos.add(lista[i]);
        saida.push(lista[i]);
      }
    };
    juntar(primeiros);
    juntar(segundos);
    return saida;
  }

  function mapaDaPagina() {
    var lista = [];
    try { lista = document.querySelectorAll(INTERACTIVOS); } catch (e) { lista = []; }
    lista = juntarCandidatos(lista, candidatosPorCursor());
    var achados = [];
    var semRotulo = 0;
    var fora = 0;
    var tapados = 0;
    for (var i = 0; i < lista.length; i++) {
      var el = lista[i];
      var rot = rotuloCurto(el);
      if (!rot) { semRotulo++; continue; }
      var r = el.getBoundingClientRect();
      var estilo = window.getComputedStyle(el);
      var pintado = r.width > 0 && r.height > 0 && estilo.visibility !== 'hidden' && estilo.display !== 'none' && Number(estilo.opacity) !== 0;
      var dentro = r.bottom > 0 && r.right > 0 && r.top < window.innerHeight && r.left < window.innerWidth;
      if (!pintado || !dentro) { fora++; continue; }
      var cx = Math.round(r.left + r.width / 2);
      var cy = Math.round(r.top + r.height / 2);
      if (tapa(el, cx, cy)) { tapados++; continue; }
      achados.push({
        seletor: seletorPorDado(el) || caminhoDe(el),
        id: el.id || '',
        etiqueta: el.tagName.toLowerCase(),
        rotulo: rot,
        centro: { x: cx, y: cy },
        caixa: { x: Math.round(r.left), y: Math.round(r.top), largura: Math.round(r.width), altura: Math.round(r.height) }
      });
    }
    achados.sort(function (a, b) {
      if (a.centro.y !== b.centro.y) return a.centro.y - b.centro.y;
      return a.centro.x - b.centro.x;
    });
    return {
      itens: achados.slice(0, limite),
      total: achados.length,
      candidatos: lista.length,
      sem_rotulo: semRotulo,
      fora: fora,
      tapados: tapados
    };
  }

  var elementos = [];
  var total = 0;
  var erro = '';
  if (seletor) {
    var lista = null;
    try { lista = document.querySelectorAll(seletor); } catch (e) { erro = 'seletor invalido: ' + seletor; }
    if (lista) { elementos = porSeletor(lista); total = lista.length; }
  } else if (texto) {
    var alvo = texto.toLowerCase();
    var todos = document.querySelectorAll('body *');
    var fundos = [];
    var rasos = [];
    for (var j = 0; j < todos.length; j++) {
      var el = todos[j];
      var rot = rotulo(el);
      if (!rot || rot.indexOf(alvo) === -1) continue;
      var filhoCasa = false;
      for (var k = 0; k < el.children.length; k++) {
        var rotFilho = rotulo(el.children[k]);
        if (rotFilho && rotFilho.indexOf(alvo) !== -1) { filhoCasa = true; break; }
      }
      if (filhoCasa) continue;
      fundos.push(el);
      if (fundos.length >= limite) break;
    }
    if (!fundos.length) {
      for (var m = 0; m < todos.length; m++) {
        var rot2 = rotulo(todos[m]);
        if (rot2 && rot2.indexOf(alvo) !== -1) rasos.push(todos[m]);
      }
      rasos.sort(function (a, b) { return limpo(a.textContent).length - limpo(b.textContent).length; });
      fundos = rasos.slice(0, limite);
    }
    elementos = [];
    for (var n = 0; n < fundos.length; n++) elementos.push(resumo(fundos[n]));
    total = elementos.length;
  } else {
    erro = parametros.mapa ? '' : 'Sem seletor e sem texto para procurar.';
  }

  var resposta = {
    pagina: {
      url: location.href,
      titulo: document.title,
      rolagem: { x: Math.round(window.scrollX), y: Math.round(window.scrollY) },
      janela: { largura: window.innerWidth, altura: window.innerHeight }
    },
    elementos: elementos,
    total: total,
    erro: erro
  };

  if (parametros.mapa) {
    var indice = mapaDaPagina();
    resposta.elementos = indice.itens;
    resposta.total = indice.total;
    resposta.resumo = {
      candidatos: indice.candidatos,
      sem_rotulo: indice.sem_rotulo,
      fora: indice.fora,
      tapados: indice.tapados
    };
  }

  return resposta;
})`;

const SNIPPET_FOCAR = `(function (parametros) {
  var el = null;
  try { el = document.querySelector(parametros.seletor); } catch (e) { return { ok: false, erro: 'seletor invalido: ' + parametros.seletor }; }
  if (!el) return { ok: false, erro: 'Nenhum elemento encontrado para ' + parametros.seletor };
  var tag = el.tagName;
  var campo = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  var superficie = document.activeElement === el || campo || el.isContentEditable === true || !!el.editContext;
  var caixa = el.getBoundingClientRect();
  if (!superficie && (caixa.width <= 0 || caixa.height <= 0)) {
    return { ok: false, erro: 'O elemento ' + parametros.seletor + ' nao esta renderizavel (' + Math.round(caixa.width) + 'x' + Math.round(caixa.height) + ') e nao e um campo de entrada: escrever agora nao teria destino. Aponte a um campo visivel.' };
  }
  el.focus();
  var selecionou = false;
  if (parametros.limpar) {
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      if (typeof el.select === 'function') { el.select(); selecionou = true; }
    } else if (el.isContentEditable) {
      var faixa = document.createRange();
      faixa.selectNodeContents(el);
      var selecao = window.getSelection();
      selecao.removeAllRanges();
      selecao.addRange(faixa);
      selecionou = true;
    }
  }
  caixa = el.getBoundingClientRect();
  return {
    ok: true,
    focado: document.activeElement === el,
    selecionou: selecionou,
    etiqueta: el.tagName.toLowerCase(),
    centro: { x: caixa.left + caixa.width / 2, y: caixa.top + caixa.height / 2 }
  };
})`;

const SNIPPET_CURSOR = `(function (p) {
  var ID = '__axio_cursor';
  var el = document.getElementById(ID);
  if (!el) {
    el = document.createElement('div');
    el.id = ID;
    (document.body || document.documentElement).appendChild(el);
  }
  var s = el.style;
  s.position = 'fixed';
  s.left = p.x + 'px';
  s.top = p.y + 'px';
  s.width = '14px';
  s.height = '14px';
  s.margin = '-7px 0 0 -7px';
  s.borderRadius = '50%';
  s.pointerEvents = 'none';
  s.zIndex = '2147483647';
  s.background = 'rgba(144,160,21,.5)';
  s.boxShadow = '0 0 0 2px rgba(144,160,21,.95), 0 0 14px 5px rgba(144,160,21,.45)';
  s.transition = 'opacity .12s linear, transform .12s ease-out';
  s.opacity = String(p.opacidade);
  s.transform = p.escala === 1 ? 'none' : 'scale(' + p.escala + ')';
  return true;
})`;

const SNIPPET_ASSINATURA = `(function (p) {
  var alvo = null;
  var existe = false;
  var classes = '';
  var tamanho = '';
  var valor = null;
  if (p.seletor) {
    try { alvo = document.querySelector(p.seletor); } catch (e) { alvo = null; }
    existe = !!alvo;
    if (alvo) {
      var classe = alvo.getAttribute('class');
      classes = String(classe == null ? '' : classe).trim();
      var caixa = alvo.getBoundingClientRect();
      tamanho = Math.round(caixa.width) + 'x' + Math.round(caixa.height);
      if ('value' in alvo) valor = String(alvo.value == null ? '' : alvo.value).length;
    }
  }
  var todos = document.getElementsByTagName('*');
  var semCaixa = 0;
  for (var i = 0; i < todos.length; i++) {
    if (todos[i].getClientRects().length === 0) semCaixa++;
  }
  return {
    url: String(location.href),
    titulo: String(document.title || ''),
    total: todos.length,
    sem_caixa: semCaixa,
    alvo: p.seletor ? { existe: existe, classes: classes, tamanho: tamanho, valor: valor } : null
  };
})`;

const JS_RESUMO_ESTILO = `
  function _seletorDe(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return '#' + el.id;
    var classes = String(el.getAttribute('class') == null ? '' : el.getAttribute('class')).trim();
    if (classes) return el.tagName.toLowerCase() + '.' + classes.split(/\\s+/).slice(0, 2).join('.');
    return el.tagName.toLowerCase();
  }

  function _resumoDeEstilo(el) {
    var cs = getComputedStyle(el);
    var r = el.getBoundingClientRect();
    var display = cs.display;
    var layout = display;
    if (display.indexOf('flex') >= 0) {
      layout = 'flex ' + cs.flexDirection + (cs.flexWrap === 'nowrap' ? '' : ' ' + cs.flexWrap) + ' gap ' + cs.gap;
    } else if (display.indexOf('grid') >= 0) {
      layout = 'grid [' + cs.gridTemplateColumns + '] gap ' + cs.gap;
    }
    var alinhamento = (display.indexOf('flex') >= 0 || display.indexOf('grid') >= 0)
      ? (cs.alignItems + ' / ' + cs.justifyContent) : '';
    var semBorda = cs.borderTopStyle === 'none' || cs.borderTopWidth === '0px';
    return {
      seletor: _seletorDe(el),
      etiqueta: el.tagName.toLowerCase(),
      classes: String(el.getAttribute('class') == null ? '' : el.getAttribute('class')).trim(),
      texto: String(el.textContent == null ? '' : el.textContent).replace(/\\s+/g, ' ').trim().slice(0, 60),
      caixa: { x: Math.round(r.left), y: Math.round(r.top), largura: Math.round(r.width), altura: Math.round(r.height) },
      sem_area: r.width === 0 || r.height === 0,
      layout: layout,
      alinhamento: alinhamento,
      espacamento: { padding: cs.padding, margin: cs.margin, gap: cs.gap },
      arredondamento: cs.borderTopLeftRadius,
      fundo: cs.backgroundColor === 'rgba(0, 0, 0, 0)' ? '' : cs.backgroundColor,
      fundo_imagem: cs.backgroundImage === 'none' ? '' : cs.backgroundImage.slice(0, 80),
      cor: cs.color,
      borda: semBorda ? '' : (cs.borderTopWidth + ' ' + cs.borderTopStyle + ' ' + cs.borderTopColor),
      sombra: cs.boxShadow === 'none' ? '' : cs.boxShadow,
      fonte: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() + ' ' + cs.fontSize + ' / ' + cs.lineHeight + ' ' + cs.fontWeight,
      transicao: cs.transitionDuration === '0s' ? '' : cs.transition,
      opacidade: cs.opacity,
      cursor: cs.cursor
    };
  }
`;

const SNIPPET_ESTILO = `(function (parametros) {
${JS_RESUMO_ESTILO}
  var seletor = parametros.seletor || '';
  var limite = parametros.limite || 40;

  function _ordenar(mapa) {
    var lista = [];
    for (var chave in mapa) {
      if (Object.prototype.hasOwnProperty.call(mapa, chave)) lista.push({ valor: chave, vezes: mapa[chave] });
    }
    lista.sort(function (a, b) { return b.vezes - a.vezes; });
    return lista;
  }

  function _tokens() {
    var todos = document.querySelectorAll('body *');
    var fundos = {};
    var raios = {};
    var fontes = {};
    var grandes = [];
    for (var i = 0; i < todos.length; i++) {
      var el = todos[i];
      var r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      var cs = getComputedStyle(el);
      if (cs.backgroundColor !== 'rgba(0, 0, 0, 0)') fundos[cs.backgroundColor] = (fundos[cs.backgroundColor] || 0) + 1;
      if (cs.borderTopLeftRadius !== '0px') raios[cs.borderTopLeftRadius] = (raios[cs.borderTopLeftRadius] || 0) + 1;
      var fonte = cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() + ' ' + cs.fontSize + ' ' + cs.fontWeight;
      fontes[fonte] = (fontes[fonte] || 0) + 1;
      if (r.width * r.height > 900) grandes.push({ area: Math.round(r.width * r.height), el: el });
    }
    grandes.sort(function (a, b) { return b.area - a.area; });
    var principais = [];
    var vistos = {};
    for (var j = 0; j < grandes.length && principais.length < limite; j++) {
      var nome = _seletorDe(grandes[j].el);
      if (vistos[nome]) continue;
      vistos[nome] = true;
      principais.push(_resumoDeEstilo(grandes[j].el));
    }
    return {
      ok: true,
      sem_seletor: true,
      url: String(location.href),
      titulo: String(document.title || ''),
      janela: { largura: window.innerWidth, altura: window.innerHeight },
      total_de_elementos: todos.length,
      cores_de_fundo: _ordenar(fundos).slice(0, 8),
      arredondamentos: _ordenar(raios).slice(0, 6),
      fontes: _ordenar(fontes).slice(0, 8),
      principais: principais
    };
  }

  if (!seletor) return _tokens();
  var alvo = null;
  try { alvo = document.querySelector(seletor); } catch (e) { return { ok: false, erro: 'seletor invalido: ' + seletor }; }
  if (!alvo) return { ok: false, erro: 'Nenhum elemento encontrado para ' + seletor };
  var filhos = [];
  for (var k = 0; k < alvo.children.length && k < 12; k++) filhos.push(_resumoDeEstilo(alvo.children[k]));
  return {
    ok: true,
    sem_seletor: false,
    elemento: _resumoDeEstilo(alvo),
    pai: alvo.parentElement ? _resumoDeEstilo(alvo.parentElement) : null,
    filhos: filhos
  };
})`;

const SNIPPET_INSPECIONAR = `(function (parametros) {
${JS_RESUMO_ESTILO}
  var MARCA = '${MARCA_DA_INSPECAO}';
  var anterior = window.__axioInspecionar;
  if (anterior && anterior.desligar) { try { anterior.desligar(); } catch (e) {} }
  window.__axioInspecionar = null;
  if (!parametros.ligado) return { ok: true, ligado: false };

  var caixa = document.createElement('div');
  var etiqueta = document.createElement('div');
  var painel = document.createElement('div');
  caixa.id = '__axio_inspect_box';
  etiqueta.id = '__axio_inspect_tag';
  painel.id = '__axio_inspect_painel';
  caixa.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:2147483646;border:1px solid rgba(144,160,21,.95);background:rgba(144,160,21,.12);transition:left .08s linear,top .08s linear,width .08s linear,height .08s linear;display:none';
  etiqueta.style.cssText = 'position:fixed;left:0;top:0;pointer-events:none;z-index:2147483647;background:rgba(20,20,20,.94);color:#c3dc44;font:11px/1.4 ui-monospace,Consolas,monospace;padding:2px 7px;border-radius:6px;display:none;white-space:nowrap';
  painel.style.cssText = 'position:fixed;right:12px;bottom:12px;max-width:440px;max-height:48vh;overflow:auto;z-index:2147483647;background:rgba(20,20,20,.96);color:#e5e7eb;font:11.5px/1.55 ui-monospace,Consolas,monospace;padding:10px 12px;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.55);display:none;white-space:pre-wrap';
  document.documentElement.appendChild(caixa);
  document.documentElement.appendChild(etiqueta);
  document.documentElement.appendChild(painel);

  function alvoDe(alvo) {
    if (alvo && alvo.nodeType === 3) alvo = alvo.parentElement;
    return alvo;
  }

  function pintar(el) {
    if (!el || el.nodeType !== 1 || el === caixa || el === etiqueta || el === painel) {
      caixa.style.display = 'none';
      etiqueta.style.display = 'none';
      return;
    }
    var r = el.getBoundingClientRect();
    caixa.style.display = 'block';
    caixa.style.left = r.left + 'px';
    caixa.style.top = r.top + 'px';
    caixa.style.width = r.width + 'px';
    caixa.style.height = r.height + 'px';
    etiqueta.style.display = 'block';
    etiqueta.textContent = _seletorDe(el) + '  ' + Math.round(r.width) + 'x' + Math.round(r.height);
    var acima = r.top - 20;
    etiqueta.style.top = (acima < 2 ? r.top + 2 : acima) + 'px';
    etiqueta.style.left = Math.max(2, r.left) + 'px';
  }

  function linhas(info) {
    var l = [];
    l.push(info.seletor + '  <' + info.etiqueta + '>');
    if (info.texto) l.push('texto: ' + info.texto);
    l.push('caixa: ' + info.caixa.largura + 'x' + info.caixa.altura + ' em (' + info.caixa.x + ',' + info.caixa.y + ')');
    l.push('layout: ' + info.layout + (info.alinhamento ? ' - ' + info.alinhamento : ''));
    l.push('padding: ' + info.espacamento.padding);
    if (info.espacamento.gap && info.espacamento.gap !== 'normal') l.push('gap: ' + info.espacamento.gap);
    if (info.fundo) l.push('fundo: ' + info.fundo);
    l.push('cor: ' + info.cor);
    if (info.arredondamento !== '0px') l.push('radius: ' + info.arredondamento);
    if (info.borda) l.push('borda: ' + info.borda);
    if (info.sombra) l.push('sombra: ' + info.sombra);
    l.push('fonte: ' + info.fonte);
    if (info.transicao) l.push('transicao: ' + info.transicao);
    return l;
  }

  function recolher(el) {
    var info = _resumoDeEstilo(el);
    var partes = [];
    var no = el;
    while (no && no.nodeType === 1 && partes.length < 8) {
      partes.unshift(_seletorDe(no));
      no = no.parentElement;
    }
    info.caminho = partes.join(' > ');
    return info;
  }

  function mostrar(info) {
    painel.style.display = 'block';
    painel.textContent = '';
    var titulo = document.createElement('div');
    titulo.textContent = 'Inspecionar no preview - Esc sai - Shift+clique interage';
    titulo.style.cssText = 'color:#9ca3af;margin-bottom:6px';
    painel.appendChild(titulo);
    var corpo = document.createElement('div');
    corpo.textContent = linhas(info).join('\\n');
    painel.appendChild(corpo);
  }

  function aoMover(e) {
    pintar(alvoDe(e.target));
  }

  function aoClicar(e) {
    if (e.shiftKey) return;
    var el = alvoDe(e.target);
    if (painel.contains(el)) return;
    e.preventDefault();
    e.stopPropagation();
    var info = recolher(el);
    mostrar(info);
    try { console.log(MARCA + JSON.stringify(info)); } catch (x) {}
  }

  function aoTeclar(e) {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    e.stopPropagation();
    desligar();
    try { console.log(MARCA + JSON.stringify({ sair: true })); } catch (x) {}
  }

  function desligar() {
    document.removeEventListener('mousemove', aoMover, true);
    document.removeEventListener('click', aoClicar, true);
    document.removeEventListener('keydown', aoTeclar, true);
    if (caixa.parentNode) caixa.parentNode.removeChild(caixa);
    if (etiqueta.parentNode) etiqueta.parentNode.removeChild(etiqueta);
    if (painel.parentNode) painel.parentNode.removeChild(painel);
    window.__axioInspecionar = null;
  }

  document.addEventListener('mousemove', aoMover, true);
  document.addEventListener('click', aoClicar, true);
  document.addEventListener('keydown', aoTeclar, true);
  window.__axioInspecionar = { desligar: desligar };
  return { ok: true, ligado: true };
})`;

function nivelDaConsola(tipo) {
  const t = String(tipo || 'log').toLowerCase();
  if (t === 'error') return 'erro';
  if (t === 'warning' || t === 'warn') return 'aviso';
  if (t === 'debug' || t === 'verbose') return 'depuracao';
  return 'log';
}

function nivelDoLog(nivel) {
  const n = String(nivel || 'info').toLowerCase();
  if (n === 'error') return 'erro';
  if (n === 'warning') return 'aviso';
  if (n === 'verbose') return 'depuracao';
  return 'log';
}

function textoDoArgumento(arg) {
  if (!arg) return '';
  if (arg.type === 'string') return String(arg.value == null ? '' : arg.value);
  if (arg.unserializableValue != null) return String(arg.unserializableValue);
  if ('value' in arg) {
    if (arg.value === undefined) return 'undefined';
    if (typeof arg.value === 'string') return arg.value;
    try { return JSON.stringify(arg.value); } catch (e) { return String(arg.value); }
  }
  return String(arg.description || arg.type || '');
}

function descreverExcecao(detalhes) {
  if (!detalhes) return 'A pagina devolveu um erro sem descricao.';
  const excecao = detalhes.exception || {};
  const texto = String(detalhes.text || excecao.description || excecao.value || 'Erro na pagina.');
  const linha = Number(detalhes.lineNumber);
  const onde = detalhes.url ? ` (${detalhes.url}${Number.isFinite(linha) && linha >= 0 ? ':' + (linha + 1) : ''})` : '';
  return texto.split('\n')[0] + onde;
}

function guardarNaLista(lista, entrada, teto) {
  lista.push(entrada);
  if (lista.length <= teto) return 0;
  lista.shift();
  return 1;
}

function registarEntrada(entrada) {
  consolaDescartada += guardarNaLista(consola, entrada, TETO_CONSOLA);
}

function registarRede(entrada) {
  redeDescartada += guardarNaLista(rede, entrada, TETO_REDE);
}

function limparConsola() {
  consola = [];
  consolaDescartada = 0;
}

function limparRede() {
  rede = [];
  redeDescartada = 0;
  pedidos.clear();
}

function limparRegistos() {
  geracaoRegistos += 1;
  limparConsola();
  limparRede();
}

function novosRegistos(marca) {
  const intacta = marca.geracao === geracaoRegistos
    && consola.length >= marca.consola && rede.length >= marca.rede;
  const novasConsola = intacta ? consola.slice(marca.consola) : consola.slice(-TETO_EFEITO);
  const novaRede = intacta ? rede.slice(marca.rede) : rede.slice(-TETO_EFEITO);
  return {
    navegou: marca.geracao !== geracaoRegistos,
    consola: novasConsola.slice(-TETO_EFEITO),
    rede: novaRede.slice(-TETO_EFEITO)
  };
}

function aoMensagemDoDepurador(metodo, params) {
  if (metodo === 'Runtime.consoleAPICalled') {
    const partes = (params.args || []).map(textoDoArgumento).filter((p) => p !== '');
    const junto = partes.join(' ');
    if (junto.startsWith(MARCA_DA_INSPECAO)) {
      if (aoInspecionar) {
        try { aoInspecionar(JSON.parse(junto.slice(MARCA_DA_INSPECAO.length))); } catch (e) {}
      }
      return;
    }
    const quadros = (params.stackTrace && params.stackTrace.callFrames) || [];
    const quadro = quadros[0] || null;
    registarEntrada({
      nivel: nivelDaConsola(params.type),
      origem: 'console.' + String(params.type || 'log'),
      texto: partes.join(' ').slice(0, TETO_TEXTO_ENTRADA),
      ficheiro: quadro ? String(quadro.url || '') : '',
      linha: quadro ? Number(quadro.lineNumber) + 1 : 0,
      quando: Date.now()
    });
    return;
  }
  if (metodo === 'Runtime.exceptionThrown') {
    const detalhes = params.exceptionDetails || {};
    const excecao = detalhes.exception || {};
    const linha = Number(detalhes.lineNumber != null ? detalhes.lineNumber : excecao.lineNumber);
    registarEntrada({
      nivel: 'erro',
      origem: 'excecao',
      texto: String(detalhes.text || excecao.description || '').slice(0, TETO_TEXTO_ENTRADA),
      ficheiro: String(detalhes.url || excecao.fileName || ''),
      linha: Number.isFinite(linha) && linha >= 0 ? linha + 1 : 0,
      quando: Date.now()
    });
    return;
  }
  if (metodo === 'Network.requestWillBeSent') {
    const id = String(params.requestId || '');
    if (!id) return;
    const pedido = params.request || {};
    pedidos.set(id, { url: String(pedido.url || ''), tipo: String(params.type || '') });
    if (pedidos.size > TETO_PEDIDOS) pedidos.delete(pedidos.keys().next().value);
    return;
  }
  if (metodo === 'Network.responseReceived') {
    const resposta = params.response || {};
    const status = Number(resposta.status);
    const dono = pedidos.get(String(params.requestId || '')) || {};
    if (!(status >= 400)) return;
    registarRede({
      nivel: status >= 500 ? 'erro' : 'aviso',
      status: status,
      motivo: String(resposta.statusText || ''),
      url: String(resposta.url || dono.url || ''),
      tipo: String(params.type || dono.tipo || ''),
      quando: Date.now()
    });
    return;
  }
  if (metodo === 'Network.loadingFailed') {
    if (params.canceled) return;
    const dono = pedidos.get(String(params.requestId || '')) || {};
    registarRede({
      nivel: 'erro',
      status: 0,
      motivo: String(params.errorText || 'pedido falhado'),
      url: dono.url || '',
      tipo: dono.tipo || '',
      quando: Date.now()
    });
    return;
  }
  if (metodo === 'Log.entryAdded') {
    const entrada = params.entry || {};
    registarEntrada({
      nivel: nivelDoLog(entrada.level),
      origem: String(entrada.source || 'log'),
      texto: String(entrada.text || '').slice(0, TETO_TEXTO_ENTRADA),
      ficheiro: String(entrada.url || ''),
      linha: Number(entrada.lineNumber) >= 0 ? Number(entrada.lineNumber) + 1 : 0,
      quando: Date.now()
    });
  }
}

function depuradorDe(view) {
  if (!view) return null;
  const wc = view.webContents;
  if (!wc || wc.isDestroyed()) return null;
  const depurador = wc.debugger;
  if (!depurador) return null;
  try {
    if (!depurador.isAttached()) depurador.attach('1.3');
  } catch (e) {
    return null;
  }
  return depurador;
}

function depuradorDisponivel(view) {
  if (!view) return false;
  const wc = view.webContents;
  return !!(wc && !wc.isDestroyed() && wc.debugger);
}

function prepararDepurador(view) {
  limparRegistos();
  const depurador = depuradorDe(view);
  if (!depurador) return false;
  const wc = view.webContents;
  if (!vigiados.has(wc)) {
    vigiados.add(wc);
    depurador.on('message', (evento, metodo, params) => aoMensagemDoDepurador(metodo, params));
    depurador.on('detach', () => registarEntrada({
      nivel: 'aviso',
      origem: 'depurador',
      texto: 'O canal com a pagina foi desligado (o DevTools do preview ficou com ele).',
      ficheiro: '',
      linha: 0,
      quando: Date.now()
    }));
    wc.on('did-navigate', () => { limparRegistos(); reinjetarInspecaoAposNavegar(view); });
    wc.on('did-navigate-in-page', () => { limparRegistos(); reinjetarInspecaoAposNavegar(view); });
  }
  for (const dominio of ['Runtime.enable', 'Log.enable', 'Page.enable', 'Network.enable']) {
    enviarComando(depurador, dominio).catch(() => {});
  }
  return true;
}

function enviarComando(depurador, metodo, params) {
  return new Promise((resolve, reject) => {
    let terminado = false;
    const relogio = setTimeout(() => {
      if (terminado) return;
      terminado = true;
      reject(new Error('a pagina nao respondeu em ' + Math.round(TEMPO_COMANDO_MS / 1000) + 's: isso e a linha principal ocupada com codigo sincrono (um leitor a converter - tipicamente o IFC em WASM) e nao uma avaria do depurador. Enquanto nao responder, nenhum gesto nem troca de aba desta pagina acontece: recarregue o preview ou navegue para outra pagina para a libertar.'));
    }, TEMPO_COMANDO_MS);
    depurador.sendCommand(metodo, params || {})
      .then((resposta) => {
        if (terminado) return;
        terminado = true;
        clearTimeout(relogio);
        resolve(resposta);
      })
      .catch((erro) => {
        if (terminado) return;
        terminado = true;
        clearTimeout(relogio);
        reject(erro);
      });
  });
}

async function avaliarNaPagina(depurador, expressao) {
  const resposta = await enviarComando(depurador, 'Runtime.evaluate', {
    expression: expressao,
    returnByValue: true,
    awaitPromise: false,
    userGesture: false
  });
  if (resposta && resposta.exceptionDetails) {
    return { erro: descreverExcecao(resposta.exceptionDetails), valor: null };
  }
  const resultado = (resposta && resposta.result) || {};
  if ('value' in resultado) return { erro: '', valor: resultado.value };
  return { erro: '', valor: resultado.description != null ? resultado.description : null };
}

async function elementosDe(depurador, pedido) {
  const expressao = SNIPPET_ALVOS + '(' + JSON.stringify({
    seletor: String(pedido.seletor || ''),
    texto: String(pedido.texto || ''),
    mapa: !!pedido.mapa,
    limite: Math.max(1, Math.min(Number(pedido.limite) || 20, 300))
  }) + ')';
  const resposta = await avaliarNaPagina(depurador, expressao);
  if (resposta.erro) return { erro: resposta.erro };
  if (!resposta.valor || typeof resposta.valor !== 'object') {
    return { erro: 'A pagina nao devolveu elementos (ainda a carregar?).' };
  }
  if (resposta.valor.erro) return { erro: resposta.valor.erro };
  return resposta.valor;
}

async function caixaDoPedido(depurador, params) {
  const seletor = String(params.seletor || '').trim();
  if (seletor) {
    const achado = await elementosDe(depurador, { seletor: seletor, limite: 1 });
    if (achado.erro) return { erro: achado.erro };
    const primeiro = (achado.elementos || [])[0];
    if (!primeiro) return { erro: 'Nenhum elemento encontrado para ' + seletor };
    return {
      caixa: primeiro.caixa,
      centro: primeiro.centro,
      onde: primeiro.seletor,
      pintado: primeiro.pintado,
      dentro_da_janela: primeiro.dentro_da_janela,
      tapado_por: primeiro.tapado_por
    };
  }
  const regiao = String(params.regiao || '').trim();
  if (regiao) {
    const partes = regiao.split(',').map((p) => Number(String(p).trim()));
    if (partes.length !== 4 || partes.some((n) => !Number.isFinite(n))) {
      return { erro: 'Regiao invalida: use x,y,largura,altura.' };
    }
    if (partes[2] <= 0 || partes[3] <= 0) return { erro: 'Regiao com largura ou altura igual a zero.' };
    return {
      caixa: { x: partes[0], y: partes[1], largura: partes[2], altura: partes[3] },
      centro: { x: partes[0] + partes[2] / 2, y: partes[1] + partes[3] / 2 },
      onde: regiao
    };
  }
  const x = Number(params.x);
  const y = Number(params.y);
  if (Number.isFinite(x) && Number.isFinite(y)) {
    return { caixa: null, centro: { x: x, y: y }, onde: x + ',' + y };
  }
  return { caixa: null, centro: null, onde: '' };
}

function mensagemTapado(alvo, topo) {
  if (!topo) return 'O alvo ' + alvo + ' nao esta acessivel no ponto onde o gesto cairia.';
  if (topo.fora_da_janela) {
    return 'O centro do alvo ' + alvo + ' cai fora da area visivel da pagina: nao ha onde clicar. Role ate ele ou aproxime a vista.';
  }
  const quem = topo.id ? '#' + topo.id : (topo.seletor || topo.etiqueta || 'outro elemento');
  return 'O alvo ' + alvo + ' esta tapado por ' + quem + ' no ponto onde o gesto cairia, logo o clique iria para esse elemento. Feche, mova ou role o que esta por cima e repita.';
}

async function assinarPagina(depurador, seletor) {
  const expressao = SNIPPET_ASSINATURA + '(' + JSON.stringify({ seletor: String(seletor || '') }) + ')';
  const resposta = await avaliarNaPagina(depurador, expressao).catch(() => null);
  if (!resposta || resposta.erro || !resposta.valor || typeof resposta.valor !== 'object') return null;
  return resposta.valor;
}

async function marcarGesto(depurador, seletor) {
  return {
    geracao: geracaoRegistos,
    consola: consola.length,
    rede: rede.length,
    pagina: await assinarPagina(depurador, seletor)
  };
}

async function efeitoDoGesto(depurador, marca, seletor) {
  await aguardar(ESPERA_EFEITO_MS);
  const registos = novosRegistos(marca);
  return {
    antes: marca.pagina,
    depois: await assinarPagina(depurador, seletor),
    navegou: registos.navegou,
    consola: registos.consola,
    rede: registos.rede
  };
}

function acaoEstado(view) {
  if (!view) return { ok: true, tem_pagina: false };
  const wc = view.webContents;
  let visivel = null;
  try { visivel = view.getVisible(); } catch (e) { visivel = null; }
  return {
    ok: true,
    tem_pagina: true,
    url: wc.getURL(),
    titulo: wc.getTitle(),
    carregando: wc.isLoading(),
    visivel: visivel,
    depurador: depuradorDisponivel(view)
  };
}

function lerBuffer(lista, descartadas, params, teto) {
  const nivel = String(params.nivel || '').trim().toLowerCase();
  const limite = Math.max(1, Math.min(Number(params.limite) || 100, teto));
  const base = nivel ? lista.filter((e) => e.nivel === nivel) : lista;
  return {
    ok: true,
    entradas: base.slice(-limite),
    total: base.length,
    descartadas: descartadas
  };
}

function acaoConsola(view, params) {
  const resposta = lerBuffer(consola, consolaDescartada, params, TETO_CONSOLA);
  if (params.limpar) limparConsola();
  return resposta;
}

function acaoRede(view, params) {
  const resposta = lerBuffer(rede, redeDescartada, params, TETO_REDE);
  if (params.limpar) limparRede();
  return resposta;
}

async function acaoElemento(view, params) {
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const achado = await elementosDe(depurador, params);
  if (achado.erro) return { ok: false, erro: achado.erro };
  return {
    ok: true,
    pagina: achado.pagina,
    elementos: achado.elementos || [],
    total: achado.total || 0
  };
}

async function acaoMapa(view, params) {
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const achado = await elementosDe(depurador, { mapa: true, limite: params.limite || 120 });
  if (achado.erro) return { ok: false, erro: achado.erro };
  return {
    ok: true,
    pagina: achado.pagina,
    elementos: achado.elementos || [],
    total: achado.total || 0,
    resumo: achado.resumo || null
  };
}

function expressaoDeAmostras(js, params) {
  const total = Math.max(0, Math.min(Number(params.durante) || 0, 20000));
  if (!total) return '';
  const passo = Math.max(10, Math.min(Number(params.intervalo) || 50, 2000));
  return '(async function(){'
    + 'var t0=performance.now(),fim=t0+' + total + ',s=[];'
    + 'while(true){s.push([Math.round(performance.now()-t0),(' + js + ')]);'
    + 'if(performance.now()-t0>=' + total + ')break;'
    + 'await new Promise(function(r){setTimeout(r,' + passo + ')});}'
    + 'return s;})()';
}

async function acaoAvaliar(view, params) {
  const js = String(params.js || '').trim();
  if (!js) return { ok: false, erro: 'Sem expressao para avaliar.' };
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const resposta = await enviarComando(depurador, 'Runtime.evaluate', {
    expression: expressaoDeAmostras(js, params) || js,
    returnByValue: true,
    awaitPromise: true,
    userGesture: true
  });
  if (resposta && resposta.exceptionDetails) {
    return { ok: false, erro: descreverExcecao(resposta.exceptionDetails) };
  }
  const resultado = (resposta && resposta.result) || {};
  if (resultado.type === 'undefined') return { ok: true, resultado: null, tipo: 'undefined' };
  if ('value' in resultado) return { ok: true, resultado: resultado.value, tipo: resultado.type };
  return { ok: true, resultado: resultado.description != null ? resultado.description : null, tipo: resultado.type };
}

async function acaoEstilo(view, params) {
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const expressao = SNIPPET_ESTILO + '(' + JSON.stringify({
    seletor: String(params.seletor || ''),
    limite: Math.max(1, Math.min(Number(params.limite) || 40, 200))
  }) + ')';
  const resposta = await avaliarNaPagina(depurador, expressao);
  if (resposta.erro) return { ok: false, erro: resposta.erro };
  const dados = resposta.valor;
  if (!dados || typeof dados !== 'object') {
    return { ok: false, erro: 'A pagina nao devolveu o estilo (ainda a carregar?).' };
  }
  if (dados.erro) return { ok: false, erro: dados.erro };
  return dados;
}

async function prepararAlvo(view, params) {
  const depurador = depuradorDe(view);
  if (!depurador) return { erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const alvo = await caixaDoPedido(depurador, params);
  if (alvo.erro) return { erro: alvo.erro };
  return { depurador: depurador, alvo: alvo };
}

async function acaoPrint(view, params) {
  const pronto = await prepararAlvo(view, params);
  if (pronto.erro) return { ok: false, erro: pronto.erro };
  const depurador = pronto.depurador;
  const alvo = pronto.alvo;
  const pedido = { format: 'png', captureBeyondViewport: false };
  if (alvo.caixa) {
    pedido.clip = {
      x: alvo.caixa.x,
      y: alvo.caixa.y,
      width: alvo.caixa.largura,
      height: alvo.caixa.altura,
      scale: 1
    };
  }
  const resposta = await enviarComando(depurador, 'Page.captureScreenshot', pedido);
  if (!resposta || !resposta.data) return { ok: false, erro: 'A pagina nao devolveu imagem.' };
  return { ok: true, base64: resposta.data, mime: 'image/png', regiao: alvo.caixa, onde: alvo.onde };
}

async function injetarInspecao(view, ligado) {
  const depurador = view ? depuradorDe(view) : null;
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const expressao = SNIPPET_INSPECIONAR + '(' + JSON.stringify({ ligado: !!ligado }) + ')';
  const resposta = await avaliarNaPagina(depurador, expressao);
  if (resposta.erro) return { ok: false, erro: resposta.erro };
  return resposta.valor || { ok: false, erro: 'A pagina nao respondeu a injecao.' };
}

function reinjetarInspecaoAposNavegar(view) {
  if (!inspecaoLigada) return;
  setTimeout(() => { injetarInspecao(view, true).catch(() => {}); }, 400);
}

async function inspecionarPreview(view, ligado) {
  inspecaoLigada = !!ligado;
  if (!view) return { ok: true, sem_pagina: true, ligado: false };
  try {
    return await injetarInspecao(view, inspecaoLigada);
  } catch (e) {
    return { ok: false, erro: e && e.message ? e.message : String(e) };
  }
}

function aguardar(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function cursorAVista(view) {
  try { return !!view.getVisible(); } catch (e) { return false; }
}

async function esperarAVista(view, ms) {
  const limite = Date.now() + (ms || 0);
  while (Date.now() < limite) {
    if (cursorAVista(view)) return true;
    await aguardar(25);
  }
  return cursorAVista(view);
}

async function desenharCursor(depurador, x, y, opacidade, escala) {
  const expressao = SNIPPET_CURSOR + '(' + JSON.stringify({
    x: Math.round(x),
    y: Math.round(y),
    opacidade: String(opacidade),
    escala: Number(escala)
  }) + ')';
  return avaliarNaPagina(depurador, expressao).catch(() => null);
}

function apagarCursor(depurador, x, y) {
  setTimeout(() => { desenharCursor(depurador, x, y, 0, 1); }, 240);
}

async function acaoClicar(view, params) {
  await esperarAVista(view, ESPERA_VISTA_MS);
  const pronto = await prepararAlvo(view, params);
  if (pronto.erro) return { ok: false, erro: pronto.erro };
  const depurador = pronto.depurador;
  const alvo = pronto.alvo;
  if (!alvo.centro) return { ok: false, erro: 'Indique um seletor ou uma regiao x,y,largura,altura para clicar.' };
  const seletor = String(params.seletor || '').trim();
  const marca = await marcarGesto(depurador, seletor);
  const botao = String(params.botao || 'left').toLowerCase();
  const aVista = cursorAVista(view);
  let x = Math.round(alvo.centro.x);
  let y = Math.round(alvo.centro.y);
  let onde = alvo.onde;
  if (aVista) {
    await desenharCursor(depurador, x, y, 1, 1);
    await aguardar(PAUSA_CURSOR_MS);
  }
  const agora = await caixaDoPedido(depurador, params);
  if (!agora.erro && agora.centro) {
    const novoX = Math.round(agora.centro.x);
    const novoY = Math.round(agora.centro.y);
    onde = agora.onde || onde;
    if (novoX !== x || novoY !== y) {
      x = novoX;
      y = novoY;
      if (aVista) await desenharCursor(depurador, x, y, 1, 1);
    }
    if (seletor && agora.tapado_por) {
      if (aVista) {
        await desenharCursor(depurador, x, y, 1, 0.55);
        apagarCursor(depurador, x, y);
      }
      return {
        ok: false,
        erro: mensagemTapado(onde, agora.tapado_por),
        x: x,
        y: y,
        onde: onde,
        tapado_por: agora.tapado_por
      };
    }
  }
  await enviarComando(depurador, 'Input.dispatchMouseEvent', {
    type: 'mouseMoved', x: x, y: y, button: 'none', buttons: 0
  });
  for (const tipo of ['mousePressed', 'mouseReleased']) {
    await enviarComando(depurador, 'Input.dispatchMouseEvent', {
      type: tipo, x: x, y: y, button: botao, buttons: 1, clickCount: 1
    });
  }
  if (aVista) {
    await desenharCursor(depurador, x, y, 1, 0.55);
    apagarCursor(depurador, x, y);
  }
  return { ok: true, x: x, y: y, onde: onde, cursor: aVista, efeito: await efeitoDoGesto(depurador, marca, seletor) };
}

async function acaoEscrever(view, params) {
  await esperarAVista(view, ESPERA_VISTA_MS);
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const seletor = String(params.seletor || '').trim();
  const marca = await marcarGesto(depurador, seletor);
  const aVista = cursorAVista(view);
  let pontoDoCursor = null;
  let jaSelecionado = false;
  if (seletor) {
    const expressao = SNIPPET_FOCAR + '(' + JSON.stringify({ seletor: seletor, limpar: !!params.limpar }) + ')';
    const foco = await avaliarNaPagina(depurador, expressao);
    if (foco.erro) return { ok: false, erro: foco.erro };
    if (!foco.valor || !foco.valor.ok) {
      return { ok: false, erro: (foco.valor && foco.valor.erro) || 'Nao consegui focar o campo.' };
    }
    if (foco.valor.focado === false) {
      return { ok: false, erro: 'O alvo ' + seletor + ' existe mas recusou o foco; escrever agora iria para o elemento em foco. Aponte a um campo visivel.' };
    }
    const vizinho = await caixaDoPedido(depurador, params);
    if (!vizinho.erro && vizinho.tapado_por) {
      return {
        ok: false,
        erro: mensagemTapado(vizinho.onde || seletor, vizinho.tapado_por),
        escrito: 0,
        onde: vizinho.onde || seletor,
        tapado_por: vizinho.tapado_por
      };
    }
    jaSelecionado = foco.valor.selecionou === true;
    const centro = foco.valor.centro || null;
    if (aVista && centro) {
      pontoDoCursor = centro;
      await desenharCursor(depurador, centro.x, centro.y, 1, 1);
      await aguardar(PAUSA_CURSOR_MS);
    }
  }
  const texto = String(params.texto == null ? '' : params.texto);
  if (params.limpar && !jaSelecionado) await selecionarTudo(depurador);
  if (texto) {
    await enviarComando(depurador, 'Input.insertText', { text: texto });
  } else if (seletor && params.limpar) {
    await premirTecla(depurador, 'Delete');
  }
  if (pontoDoCursor) {
    setTimeout(() => { desenharCursor(depurador, pontoDoCursor.x, pontoDoCursor.y, 0, 1); }, 240);
  }
  return { ok: true, escrito: texto.length, onde: seletor, cursor: aVista, efeito: await efeitoDoGesto(depurador, marca, seletor) };
}

async function premirTecla(depurador, nome) {
  const espec = TECLAS[nome];
  const base = {
    key: espec.key,
    code: espec.code,
    windowsVirtualKeyCode: espec.vk,
    nativeVirtualKeyCode: espec.vk
  };
  await enviarComando(depurador, 'Input.dispatchKeyEvent', Object.assign({ type: 'rawKeyDown' }, base));
  if (espec.texto) {
    await enviarComando(depurador, 'Input.dispatchKeyEvent', Object.assign({ type: 'char' }, base, { text: espec.texto, unmodifiedText: espec.texto }));
  }
  await enviarComando(depurador, 'Input.dispatchKeyEvent', Object.assign({ type: 'keyUp' }, base));
  return true;
}

async function selecionarTudo(depurador) {
  const base = {
    key: 'a',
    code: 'KeyA',
    windowsVirtualKeyCode: 65,
    nativeVirtualKeyCode: 65,
    modifiers: 2
  };
  await enviarComando(depurador, 'Input.dispatchKeyEvent', Object.assign({ type: 'rawKeyDown', commands: ['selectAll'] }, base));
  await enviarComando(depurador, 'Input.dispatchKeyEvent', Object.assign({ type: 'keyUp' }, base));
  return true;
}

async function acaoTeclar(view, params) {
  await esperarAVista(view, ESPERA_VISTA_MS);
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const pedido = String(params.tecla || '').trim();
  const nome = Object.keys(TECLAS).find((t) => t.toLowerCase() === pedido.toLowerCase());
  if (!nome) {
    return { ok: false, erro: 'Tecla nao suportada: ' + pedido + '. Disponiveis: ' + Object.keys(TECLAS).join(', ') + '.' };
  }
  const marca = await marcarGesto(depurador, '');
  await premirTecla(depurador, nome);
  return { ok: true, tecla: nome, efeito: await efeitoDoGesto(depurador, marca, '') };
}

async function acaoRecarregar(view) {
  const depurador = depuradorDe(view);
  if (!depurador) return { ok: false, erro: 'A pagina do preview nao esta a falar com o depurador.' };
  const url = view.webContents.getURL();
  await enviarComando(depurador, 'Page.reload', { ignoreCache: true });
  const limite = Date.now() + ESPERA_RECARGA_MS;
  let pronto = false;
  while (Date.now() < limite) {
    await aguardar(120);
    let completo = false;
    try {
      completo = await avaliarNaPagina(depurador, "document.readyState === 'complete'");
    } catch (e) {
      completo = false;
    }
    if (completo === true) {
      pronto = true;
      break;
    }
  }
  return { ok: true, url: url, pronto: pronto };
}

const ACOES = {
  estado: (view) => acaoEstado(view),
  consola: (view, params) => acaoConsola(view, params),
  rede: (view, params) => acaoRede(view, params),
  elemento: (view, params) => acaoElemento(view, params),
  mapa: (view, params) => acaoMapa(view, params),
  avaliar: (view, params) => acaoAvaliar(view, params),
  estilo: (view, params) => acaoEstilo(view, params),
  print: (view, params) => acaoPrint(view, params),
  clicar: (view, params) => acaoClicar(view, params),
  escrever: (view, params) => acaoEscrever(view, params),
  teclar: (view, params) => acaoTeclar(view, params),
  recarregar: (view) => acaoRecarregar(view)
};

function responder(res, status, dados) {
  const corpo = Buffer.from(JSON.stringify(dados), 'utf8');
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': corpo.length,
    'Cache-Control': 'no-store'
  });
  res.end(corpo);
}

function tratarPedido(req, res) {
  const remoto = (req.socket && req.socket.remoteAddress) || '';
  const deCasa = remoto === '127.0.0.1' || remoto === '::1' || remoto === '::ffff:127.0.0.1';
  if (!deCasa) return responder(res, 403, { ok: false, erro: 'Origem nao permitida.' });
  if (req.method !== 'POST' || !String(req.url || '').startsWith(ROTA)) {
    return responder(res, 404, { ok: false, erro: 'Rota desconhecida.' });
  }
  if (req.headers['x-axio-token'] !== TOKEN) {
    return responder(res, 401, { ok: false, erro: 'Token invalido.' });
  }
  let corpo = '';
  let excedeu = false;
  req.on('data', (pedaco) => {
    if (excedeu) return;
    corpo += pedaco;
    if (corpo.length > TETO_CORPO_BYTES) {
      excedeu = true;
      corpo = '';
    }
  });
  req.on('error', () => responder(res, 400, { ok: false, erro: 'Pedido interrompido.' }));
  req.on('end', async () => {
    if (excedeu) return responder(res, 413, { ok: false, erro: 'Pedido grande demais.' });
    let dados = null;
    try {
      dados = JSON.parse(corpo || '{}');
    } catch (e) {
      return responder(res, 400, { ok: false, erro: 'JSON invalido no corpo do pedido.' });
    }
    const resultado = await executar(dados);
    responder(res, 200, resultado);
  });
}

async function executar(dados) {
  const acao = String((dados && dados.acao) || '').trim();
  const params = (dados && dados.params) || {};
  const tabela = Object.assign({}, ACOES, acoesDeFora);
  const escolhida = tabela[acao];
  if (!escolhida) {
    return { ok: false, erro: 'Acao desconhecida: ' + acao, acoes: Object.keys(tabela) };
  }
  try {
    const view = obterPreview();
    if (!view && !SEM_PAGINA.has(acao)) {
      return {
        ok: false,
        sem_pagina: true,
        erro: 'Nao ha pagina no preview. Carregue um endereco ou um ficheiro primeiro.'
      };
    }
    if (aoUsar) {
      try { aoUsar(acao, ACOES_QUE_AGEM.has(acao)); } catch (e) {}
    }
    return await escolhida(view, params);
  } catch (e) {
    return { ok: false, erro: 'Falha na acao ' + acao + ': ' + (e && e.message ? e.message : String(e)) };
  }
}

function iniciarPonte(opcoes, aoPronto) {
  obterPreview = (opcoes && opcoes.obterPreview) || (() => null);
  acoesDeFora = (opcoes && opcoes.acoesDeFora) || {};
  aoUsar = (opcoes && opcoes.aoUsar) || null;
  aoInspecionar = (opcoes && opcoes.aoInspecionar) || null;
  servidor = http.createServer(tratarPedido);
  servidor.on('error', () => {
    porta = 0;
    if (aoPronto) aoPronto(0, '');
  });
  servidor.listen(0, '127.0.0.1', () => {
    porta = servidor.address().port;
    if (aoPronto) aoPronto(porta, TOKEN);
  });
}

function pararPonte() {
  if (!servidor) return;
  try { servidor.close(); } catch (e) {}
  servidor = null;
  porta = 0;
}

module.exports = {
  iniciarPonte,
  pararPonte,
  prepararDepurador,
  depuradorDe,
  inspecionarPreview,
  limparConsola,
  TECLAS,
  ACOES
};
