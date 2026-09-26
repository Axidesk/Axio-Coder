process.env.ELECTRON_NO_ATTACH_CONSOLE = 'true';
const { app, BrowserWindow, WebContentsView, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');
const { iniciarPonte, pararPonte, prepararDepurador, inspecionarPreview } = require('./preview-cdp');

app.commandLine.appendSwitch('log-level', '3');
app.commandLine.appendSwitch('disable-logging');
process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = 'true';

app.commandLine.appendSwitch('enable-gpu-rasterization');
app.commandLine.appendSwitch('enable-zero-copy');
app.commandLine.appendSwitch('ignore-gpu-blocklist');
app.commandLine.appendSwitch('force_high_performance_gpu');
app.commandLine.appendSwitch('enable-native-gpu-memory-buffers');
app.commandLine.appendSwitch('enable-features', 'UseSkiaRenderer,CanvasOopRasterization');
app.commandLine.appendSwitch('js-flags', '--max-old-space-size=4096');
app.commandLine.appendSwitch('high-dpi-support', '1');
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

let mainWindow;
let flaskProcess;
let temaAtual = 'dark';
let inspectAtivo = false;
let quitting = false;
let flaskRestarts = 0;
let reiniciandoBackend = false;
let previewViews = { node: null, web: null };
let previewAtiva = null;
let previewVisivel = false;
let previewFerramentas = false;
let previewLimites = null;
let previewAncora = null;
let pontePorta = 0;
let ponteToken = '';
let zoomDaInterface = 1;
let raciocinioView = null;
let raciocinioRecolhido = true;
let raciocinioLargo = false;
let raciocinioBuffer = [];
let raciocinioOcioso = null;
let raciocinioSaidaEm = null;
let raciocinioAnimando = null;
let raciocinioPronto = false;
let raciocinioSaindo = false;
let raciocinioQuerido = false;
let raciocinioEmTurno = false;
let raciocinioRevelado = false;
const ALTURA_DA_BARRA_DE_TITULO = 32;
const CAMINHO_SETTINGS = path.join(__dirname, '..', 'data', 'settings.json');
const ZOOM_MINIMO = 0.5;
const ZOOM_MAXIMO = 2;
const PASSOS_DE_ZOOM = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2];
const RACIOCINIO_LARGURA = 380;
const RACIOCINIO_ALTURA = 200;
const RACIOCINIO_LARGURA_MAX = 760;
const RACIOCINIO_ALTURA_MAX = 420;
const RACIOCINIO_JANELA_REF_LARGURA = 1400;
const RACIOCINIO_JANELA_REF_ALTURA = 900;
const RACIOCINIO_FRACAO_MAX = 0.72;
const RACIOCINIO_LARGURA_RECOLHIDA = 200;
const RACIOCINIO_ALTURA_RECOLHIDA = 38;
const RACIOCINIO_MARGEM_FUNDO = 16;
const RACIOCINIO_PAD_LATERAL = 16;
const RACIOCINIO_RAIO_JANELA = 12;
const RACIOCINIO_SAIDA_MS = 200;
const RACIOCINIO_CAIXA_MS = 250;
const RACIOCINIO_MOVIMENTO_MS = 160;
const RACIOCINIO_SALTO_PX = 40;
const RACIOCINIO_QUADRO_MS = 8;
const RACIOCINIO_FUNDO = '#1e1e1e';
const RACIOCINIO_MEMORIA = 80;
const RACIOCINIO_OCIOSO_MS = 300000;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    icon: path.join(__dirname, '..', 'data', 'icons', 'icon.ico'),
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#1e1e1e',
      symbolColor: '#d6d8dc',
      height: ALTURA_DA_BARRA_DE_TITULO
    },
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      backgroundThrottling: false,
      spellcheck: false
    },
    backgroundColor: '#1e1e1e'
  });

  mainWindow.setMenuBarVisibility(false);
  zoomDaInterface = lerZoomPersistido();
  mainWindow.webContents.setZoomFactor(zoomDaInterface);
  mainWindow.webContents.on('did-finish-load', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.setZoomFactor(zoomDaInterface);
    descartarRaciocinioView();
  });
  mainWindow.loadURL('http://127.0.0.1:5000/');

  let loadAttempts = 0;
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    if (errorDescription === 'ERR_CONNECTION_REFUSED' && loadAttempts < 30) {
      loadAttempts += 1;
      setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.loadURL('http://127.0.0.1:5000/');
        }
      }, 1000);
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  const isMac = process.platform === 'darwin';
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return;
    const cmdOrCtrl = isMac ? input.meta : input.control;
    if (!cmdOrCtrl) return;
    if (input.shift || input.alt) return;
    if (input.key === 'v' || input.code === 'KeyV') {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.paste();
      }
      event.preventDefault();
    }
  });

  mainWindow.on('resize', () => acompanharGeometriaDaJanela());
  mainWindow.on('move', () => acompanharGeometriaDaJanela());
  mainWindow.on('resized', () => assentarGeometriaDaJanela());
  mainWindow.on('moved', () => assentarGeometriaDaJanela());
  mainWindow.on('maximize', () => assentarGeometriaDaJanela());
  mainWindow.on('unmaximize', () => assentarGeometriaDaJanela());
  mainWindow.on('restore', () => assentarGeometriaDaJanela());

  mainWindow.on('closed', function () {
    descartarPreviewView();
    descartarRaciocinioView();
    previewLimites = null;
    previewAncora = null;
    previewVisivel = false;
    mainWindow = null;
  });
}

function waitForFlask(url, cb) {
  let attempts = 0;
  const tryConnect = () => {
    const req = http.get(url, (res) => {
      res.resume();
      flaskRestarts = 0;
      cb();
    });
    req.on('error', () => {
      attempts += 1;
      if (attempts > 60) {
        cb();
      } else {
        setTimeout(tryConnect, 500);
      }
    });
    req.setTimeout(2000, () => {
      req.destroy();
    });
  };
  tryConnect();
}

function killProcessOnPort(port) {
  const { execSync } = require('child_process');
  try {
    if (process.platform === 'win32') {
      const out = execSync(`netstat -ano -p TCP`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString();
      const pids = new Set();
      for (const line of out.split(/\r?\n/)) {
        const parts = line.trim().split(/\s+/);
        if (parts.length < 5) continue;
        const localAddr = parts[1];
        if (!localAddr.endsWith(':' + port)) continue;
        const pid = parseInt(parts[parts.length - 1], 10);
        if (!Number.isInteger(pid)) continue;
        if (pid <= 4) continue;
        pids.add(pid);
      }
      if (pids.size) console.log(`[main] killProcessOnPort(${port}): processos na porta -> ${[...pids].join(', ')}`);
      for (const pid of pids) {
        let name = '';
        try {
          name = execSync(`tasklist /FI "PID eq ${pid}" /FO CSV /NH`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().split(',')[0].replace(/"/g, '').trim();
        } catch (e) {}
        try {
          execSync(`taskkill /F /PID ${pid}`);
          console.log(`[main] killProcessOnPort(${port}): PID ${pid} (${name || 'desconhecido'}) finalizado.`);
        } catch (e) {
          console.log(`[main] killProcessOnPort(${port}): falha ao matar PID ${pid} (${name || 'desconhecido'}): ${e.message}`);
        }
      }
      if (!pids.size) console.log(`[main] killProcessOnPort(${port}): nenhum processo segurando a porta.`);
    } else {
      const out = execSync(`lsof -ti :${port}`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString();
      for (const pid of out.split(/\n/).map((s) => s.trim()).filter(Boolean)) {
        const n = parseInt(pid, 10);
        if (!Number.isInteger(n) || n <= 1) continue;
        try { execSync(`kill -9 ${n}`); } catch (e) {}
      }
    }
  } catch (e) {}
}

function startFlask() {
  const flaskEnv = Object.assign({}, process.env, {
    KMP_DUPLICATE_LIB_OK: 'TRUE',
    OMP_NUM_THREADS: '4',
    PYTHONUNBUFFERED: '1',
    PYTHONFAULTHANDLER: '1'
  });
  if (pontePorta) {
    flaskEnv.AXIO_PONTE_PORTA = String(pontePorta);
    flaskEnv.AXIO_PONTE_TOKEN = ponteToken;
  }
  flaskProcess = spawn('python', ['app.py'], { windowsHide: true, env: flaskEnv });
  console.log(`[main] Flask iniciado. PID=${flaskProcess.pid}`);

  flaskProcess.stdout.on('data', (data) => {
    console.log(`Flask stdout: ${data}`);
  });

  flaskProcess.stderr.on('data', (data) => {
    console.error(`Flask stderr: ${data}`);
  });

  flaskProcess.on('error', (err) => {
    console.error(`[main] Erro ao spawnar Flask: ${err.message}`);
  });

  flaskProcess.on('exit', (code, signal) => {
    const exitedPid = flaskProcess ? flaskProcess.pid : '?';
    console.log(`[main] Flask saiu. PID=${exitedPid} code=${code} signal=${signal} ts=${Date.now()}`);
    flaskProcess = null;
    if (reiniciandoBackend) {
      return;
    }
    if (quitting) {
      return;
    }
    if (code === 3221225477) {
      console.log('Flask crash nativo (0xC0000005). Reiniciando...');
    }
    flaskRestarts += 1;
    if (flaskRestarts > 5) {
      console.log('Flask falhou 5 vezes consecutivas. Abortando reinicializacao.');
      return;
    }
    setTimeout(() => {
      killProcessOnPort(5000);
      startFlask();
    }, 1000);
  });
}

function restartFlask() {
  if (reiniciandoBackend) {
    return;
  }
  reiniciandoBackend = true;
  console.log('[main] Reiniciando backend (Flask) a pedido do usuario...');
  flaskRestarts = 0;
  killProcessOnPort(5000);
  if (flaskProcess) {
    try {
      flaskProcess.kill();
    } catch (e) {}
  }
  setTimeout(() => {
    killProcessOnPort(5000);
    startFlask();
    waitForFlask('http://127.0.0.1:5000/', () => {
      reiniciandoBackend = false;
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reloadIgnoringCache();
      }
    });
  }, 600);
}

function avisarPreview(canal, dados) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(canal, dados);
  }
}

function veioDaJanelaPrincipal(evento) {
  return !!mainWindow && !mainWindow.isDestroyed() && evento.sender === mainWindow.webContents;
}

function estadoDoPreview(view) {
  const wc = view.webContents;
  const historico = wc.navigationHistory;
  return {
    url: wc.getURL(),
    titulo: wc.getTitle(),
    carregando: wc.isLoading(),
    podeVoltar: !!historico && historico.canGoBack(),
    podeAvancar: !!historico && historico.canGoForward()
  };
}

function enviarEstadoDoPreview() {
  const view = previewVivo();
  if (!view) return;
  avisarPreview('preview:estado', estadoDoPreview(view));
}

function ligarEventosDoPreview(view, precisaNode) {
  const wc = view.webContents;
  wc.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url) && !precisaNode) {
      setImmediate(() => {
        if (!wc.isDestroyed()) wc.loadURL(url);
      });
      return { action: 'deny' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });
  wc.on('did-start-loading', () => {
    avisarPreview('preview:estado', Object.assign(estadoDoPreview(view), { carregando: true }));
  });
  wc.on('did-stop-loading', enviarEstadoDoPreview);
  wc.on('did-navigate', enviarEstadoDoPreview);
  wc.on('did-navigate-in-page', enviarEstadoDoPreview);
  wc.on('page-title-updated', enviarEstadoDoPreview);
  wc.on('did-fail-load', (evento, codigo, descricao, url, principal) => {
    if (!principal || codigo === -3) return;
    avisarPreview('preview:erro', { codigo: codigo, descricao: descricao, url: url });
  });
}

const LOCAL_NO_PREVIEW = /^(file|about|devtools|chrome):/i;
const LOOPBACK_NO_PREVIEW = /^https?:\/\/(localhost|127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?(?:[/?#]|$)/i;

function alvoPrecisaNode(url) {
  const texto = String(url || '').trim();
  return LOCAL_NO_PREVIEW.test(texto) || LOOPBACK_NO_PREVIEW.test(texto);
}

const TIPOS_DE_VIEW = ['node', 'web'];

function tipoDoAlvo(alvo) {
  const texto = String(alvo || '').trim();
  if (!texto) return 'web';
  if (/^[a-z]:[\\/]/i.test(texto) || texto.startsWith('\\\\') || texto.startsWith('/')) return 'node';
  return alvoPrecisaNode(texto) ? 'node' : 'web';
}

function viewDoTipo(tipo) {
  const view = tipo ? previewViews[tipo] : null;
  if (!view || view.webContents.isDestroyed()) return null;
  return view;
}

function previewVivo() {
  return viewDoTipo(previewAtiva);
}

function descartarPreviewView(tipo) {
  const alvos = tipo ? [tipo] : TIPOS_DE_VIEW.slice();
  for (const chave of alvos) {
    const view = previewViews[chave];
    if (!view) continue;
    previewViews[chave] = null;
    if (previewAtiva === chave) previewAtiva = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      try {
        mainWindow.contentView.removeChildView(view);
      } catch (e) {}
    }
    if (!view.webContents.isDestroyed()) view.webContents.close();
  }
}

function criarViewDoTipo(tipo) {
  const existente = viewDoTipo(tipo);
  if (existente) return existente;
  const querNode = tipo === 'node';
  const view = new WebContentsView({
    webPreferences: querNode
      ? {
          nodeIntegration: true,
          contextIsolation: false,
          sandbox: false,
          spellcheck: false
        }
      : {
          nodeIntegration: false,
          contextIsolation: true,
          sandbox: true
        }
  });
  previewViews[tipo] = view;
  view.__axioAlvo = tipo;
  view.setBackgroundColor('#1e1e1e');
  view.setBounds(previewLimites || limitesDeArranque());
  aplicarVisibilidadeDaView(view, false);
  ligarEventosDoPreview(view, querNode);
  view.webContents.on('did-finish-load', () => {
    aplicarZoomAoPreview();
    aplicarFerramentasDoPreview();
  });
  prepararDepurador(view);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.contentView.addChildView(view);
    garantirRaciocinioNoTopo();
  }
  avisarPreview('preview:novo', {});
  return view;
}

function aplicarVisibilidadeDaView(view, visivel) {
  if (!view || view.webContents.isDestroyed()) return;
  view.setVisible(!!visivel);
  view.webContents.setBackgroundThrottling(!visivel);
}

function mostrarSoAVista(tipo) {
  previewAtiva = tipo;
  for (const chave of TIPOS_DE_VIEW) {
    const view = viewDoTipo(chave);
    if (!view) continue;
    aplicarVisibilidadeDaView(view, previewVisivel && chave === tipo);
  }
}

function definirVisibilidadeDoPreview(visivel) {
  const alguma = viewDoTipo('node') || viewDoTipo('web');
  if (!visivel && !alguma) return;
  previewVisivel = !!visivel;
  if (previewVisivel) {
    criarRaciocinioView();
    if (raciocinioQuerido) mostrarRaciocinioView();
  } else {
    esconderRaciocinioView(raciocinioEmTurno);
  }
  for (const chave of TIPOS_DE_VIEW) {
    const view = viewDoTipo(chave);
    if (!view) continue;
    aplicarVisibilidadeDaView(view, previewVisivel && chave === previewAtiva);
    if (previewVisivel && mainWindow && !mainWindow.isDestroyed()) {
      if (!mainWindow.contentView.children.includes(view)) {
        mainWindow.contentView.addChildView(view);
      }
    }
  }
  garantirRaciocinioNoTopo();
}

function trazerParaFrente() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return { ok: false, erro: 'A janela principal nao esta disponivel.' };
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  if (!mainWindow.isVisible()) mainWindow.show();
  mainWindow.focus();
  return { ok: true };
}

function aplicarLimitesDoPreview(limites) {
  const caixa = escalarLimites(limites, zoomDaJanela());
  if (!caixa) return;
  if (caixa.width < RACIOCINIO_LARGURA_RECOLHIDA || caixa.height < RACIOCINIO_ALTURA_RECOLHIDA) return;
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const cliente = mainWindow.getContentBounds();
  if (caixa.x + caixa.width > cliente.width + 2 || caixa.y + caixa.height > cliente.height + 2) return;
  previewLimites = caixa;
  previewAncora = ancorarLimites(caixa);
  posicionarPreview(limitesDoPreview());
  aplicarLimitesDoRaciocinio();
}

function ancorarLimites(caixa) {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  const cliente = mainWindow.getContentBounds();
  return {
    esquerda: caixa.x,
    topo: caixa.y,
    direita: Math.max(0, cliente.width - (caixa.x + caixa.width)),
    fundo: Math.max(0, cliente.height - (caixa.y + caixa.height))
  };
}

function limitesDoPreview() {
  if (!previewAncora) return previewLimites;
  if (!mainWindow || mainWindow.isDestroyed()) return previewLimites;
  const cliente = mainWindow.getContentBounds();
  const largura = Math.max(1, cliente.width - previewAncora.esquerda - previewAncora.direita);
  const altura = Math.max(1, cliente.height - previewAncora.topo - previewAncora.fundo);
  return { x: previewAncora.esquerda, y: previewAncora.topo, width: largura, height: altura };
}

function posicionarPreview(caixa) {
  if (!caixa) return;
  for (const chave of TIPOS_DE_VIEW) {
    const view = viewDoTipo(chave);
    if (!view || mesmoRect(view.getBounds(), caixa)) continue;
    view.setBounds(caixa);
  }
}

function acompanharGeometriaDaJanela() {
  posicionarPreview(limitesDoPreview());
  aplicarLimitesDoRaciocinio();
}

function invalidarPainel() {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  raciocinioView.webContents.invalidate();
}

function assentarGeometriaDaJanela() {
  acompanharGeometriaDaJanela();
  invalidarPainel();
}

function escalarLimites(limites, fator) {
  const escala = (Number.isFinite(fator) && fator > 0) ? fator : 1;
  const x = Math.round(Number(limites && limites.x) * escala);
  const y = Math.round(Number(limites && limites.y) * escala);
  const largura = Math.round(Number(limites && limites.width) * escala);
  const altura = Math.round(Number(limites && limites.height) * escala);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(largura) || !Number.isFinite(altura)) return null;
  return { x: x, y: y, width: Math.max(1, largura), height: Math.max(1, altura) };
}

function zoomDaJanela() {
  if (!mainWindow || mainWindow.isDestroyed()) return zoomDaInterface;
  return mainWindow.webContents.getZoomFactor() || zoomDaInterface;
}

function limitesDeArranque() {
  if (!mainWindow || mainWindow.isDestroyed()) return { x: 0, y: 0, width: 1, height: 1 };
  const caixa = mainWindow.getContentBounds();
  return { x: 0, y: 0, width: Math.max(1, caixa.width), height: Math.max(1, caixa.height) };
}

function limitesDoRaciocinio() {
  const area = limitesDoPreview() || limitesDeArranque();
  const medida = medidaDoRaciocinio();
  const tetoX = area.width > 0 ? Math.round(area.width * RACIOCINIO_FRACAO_MAX) : medida.largura;
  const tetoY = area.height > 0 ? Math.round(area.height * RACIOCINIO_FRACAO_MAX) : medida.altura;
  const largura = Math.max(RACIOCINIO_LARGURA_RECOLHIDA, Math.min(medida.largura, tetoX));
  const altura = Math.max(RACIOCINIO_ALTURA_RECOLHIDA, Math.min(medida.altura, tetoY));
  return {
    x: Math.round(area.x + Math.max(0, (area.width - largura) / 2)),
    y: Math.round(area.y + Math.max(0, area.height - altura - RACIOCINIO_MARGEM_FUNDO)),
    width: largura,
    height: altura
  };
}

function medidaDoRaciocinio() {
  const base = { largura: RACIOCINIO_LARGURA, altura: RACIOCINIO_ALTURA };
  if (!mainWindow || mainWindow.isDestroyed()) return base;
  const cliente = mainWindow.getContentBounds();
  const cresceLargura = Math.max(1, cliente.width / RACIOCINIO_JANELA_REF_LARGURA);
  const cresceAltura = Math.max(1, cliente.height / RACIOCINIO_JANELA_REF_ALTURA);
  return {
    largura: Math.min(RACIOCINIO_LARGURA_MAX, Math.round(RACIOCINIO_LARGURA * cresceLargura)),
    altura: Math.min(RACIOCINIO_ALTURA_MAX, Math.round(RACIOCINIO_ALTURA * cresceAltura))
  };
}

function caixaDeToqueDoRaciocinio() {
  const cheia = limitesDoRaciocinio();
  const alvo = raciocinioLargo ? caixaLargaDoRaciocinio(cheia) : cheia;
  if (!raciocinioRecolhido) return alvo;
  const largura = Math.round(Math.min(RACIOCINIO_LARGURA_RECOLHIDA, alvo.width));
  const altura = Math.round(Math.min(RACIOCINIO_ALTURA_RECOLHIDA, alvo.height));
  return {
    x: alvo.x + Math.round((alvo.width - largura) / 2),
    y: alvo.y + alvo.height - altura,
    width: largura,
    height: altura
  };
}

function caixaLargaDoRaciocinio(cheia) {
  const area = limitesDoPreview() || limitesDeArranque();
  const largura = Math.max(cheia.width, Math.round(area.width - RACIOCINIO_PAD_LATERAL * 2));
  return {
    x: Math.round(area.x + Math.max(0, (area.width - largura) / 2)),
    y: cheia.y,
    width: largura,
    height: cheia.height
  };
}

function mesmoRect(a, b) {
  return !!a && !!b && a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
}

function garantirRaciocinioNoTopo() {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const filhos = mainWindow.contentView.children;
  if (filhos[filhos.length - 1] === raciocinioView) return;
  mainWindow.contentView.addChildView(raciocinioView);
}

function aplicarLimitesDoRaciocinio() {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const destino = caixaDeToqueDoRaciocinio();
  const atual = raciocinioView.getBounds();
  if (mesmoRect(atual, destino)) return;
  const salto = Math.max(
    Math.abs(destino.x - atual.x),
    Math.abs(destino.y - atual.y),
    Math.abs(destino.width - atual.width),
    Math.abs(destino.height - atual.height)
  );
  if (salto > RACIOCINIO_SALTO_PX) {
    definirCaixaDoRaciocinio(destino, RACIOCINIO_MOVIMENTO_MS);
    return;
  }
  if (raciocinioAnimando) {
    clearInterval(raciocinioAnimando);
    raciocinioAnimando = null;
    avisarAnimacaoDoRaciocinio(false);
  }
  raciocinioView.setBounds(destino);
}

function descartarRaciocinioView() {
  const view = raciocinioView;
  if (raciocinioSaidaEm) {
    clearTimeout(raciocinioSaidaEm);
    raciocinioSaidaEm = null;
  }
  if (raciocinioAnimando) {
    clearInterval(raciocinioAnimando);
    raciocinioAnimando = null;
  }
  raciocinioView = null;
  raciocinioRecolhido = true;
  raciocinioLargo = false;
  raciocinioBuffer = [];
  raciocinioPronto = false;
  raciocinioSaindo = false;
  raciocinioQuerido = false;
  raciocinioRevelado = false;
  if (!view) return;
  if (mainWindow && !mainWindow.isDestroyed()) {
    try {
      mainWindow.contentView.removeChildView(view);
    } catch (erro) {}
  }
  if (!view.webContents.isDestroyed()) view.webContents.close();
}

function criarRaciocinioView() {
  if (raciocinioView && !raciocinioView.webContents.isDestroyed()) return raciocinioView;
  raciocinioPronto = false;
  raciocinioView = new WebContentsView({
    webPreferences: {
      preload: path.join(__dirname, 'frontend', 'js', 'raciocinio_preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
      spellcheck: false
    }
  });
  raciocinioView.setBackgroundColor(RACIOCINIO_FUNDO);
  raciocinioView.setBorderRadius(Math.round(RACIOCINIO_RAIO_JANELA * zoomDaInterface));
  raciocinioView.setBounds(caixaDeToqueDoRaciocinio());
  raciocinioView.setVisible(false);
  raciocinioView.webContents.setZoomFactor(zoomDaInterface);
  raciocinioView.webContents.on('did-fail-load', (evento, codigo, descricao, url, quadroPrincipal) => {
    if (quadroPrincipal && codigo !== -3) descartarRaciocinioView();
  });
  raciocinioView.webContents.on('did-start-loading', () => {
    raciocinioRevelado = false;
  });
  raciocinioView.webContents.on('did-finish-load', () => {
    if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
    raciocinioPronto = true;
    raciocinioView.webContents.send('raciocinio:historico', raciocinioBuffer);
    raciocinioView.webContents.send('raciocinio:recolhido', raciocinioRecolhido);
    raciocinioView.webContents.send('raciocinio:largo', raciocinioLargo);
    avisarEscalaDoRaciocinio();
    if (raciocinioQuerido && previewVisivel) mostrarRaciocinioView();
  });
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.contentView.addChildView(raciocinioView);
  raciocinioView.webContents.loadURL('http://127.0.0.1:5000/raciocinio');
  return raciocinioView;
}

function esperarOciosidadeDoRaciocinio() {
  if (raciocinioOcioso) clearTimeout(raciocinioOcioso);
  raciocinioOcioso = setTimeout(esconderRaciocinioView, RACIOCINIO_OCIOSO_MS);
}

function esconderRaciocinioView(manterPedido) {
  if (raciocinioOcioso) {
    clearTimeout(raciocinioOcioso);
    raciocinioOcioso = null;
  }
  if (!manterPedido) raciocinioQuerido = false;
  if (!raciocinioView || raciocinioView.webContents.isDestroyed() || !raciocinioView.getVisible()) return;
  if (raciocinioSaindo) return;
  raciocinioSaindo = true;
  raciocinioRevelado = false;
  raciocinioView.webContents.send('raciocinio:sair');
  raciocinioSaidaEm = setTimeout(() => {
    raciocinioSaidaEm = null;
    raciocinioSaindo = false;
    if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
    raciocinioView.setVisible(false);
  }, RACIOCINIO_SAIDA_MS);
}

function mostrarRaciocinioView() {
  raciocinioQuerido = true;
  if (!previewVisivel) return;
  if (!mainWindow || mainWindow.isDestroyed() || mainWindow.isMinimized()) return;
  const voltouDaSaida = !!raciocinioSaidaEm;
  if (raciocinioSaidaEm) {
    clearTimeout(raciocinioSaidaEm);
    raciocinioSaidaEm = null;
  }
  raciocinioSaindo = false;
  esperarOciosidadeDoRaciocinio();
  const view = criarRaciocinioView();
  garantirRaciocinioNoTopo();
  if (!raciocinioPronto) {
    if (!view.webContents.isLoading()) view.webContents.reload();
    return;
  }
  const apareceu = !view.getVisible() || voltouDaSaida;
  aplicarLimitesDoRaciocinio();
  view.setVisible(true);
  if (!apareceu && raciocinioRevelado) return;
  if (apareceu) avisarEscalaDoRaciocinio();
  if (view.webContents.isLoading()) return;
  raciocinioRevelado = true;
  view.webContents.send('raciocinio:abrir');
}

function alimentarRaciocinio(evento) {
  if (!evento || typeof evento !== 'object' || !evento.tipo) return;
  if (evento.tipo === 'inicio' || evento.tipo === 'fim') {
    raciocinioBuffer = [];
    raciocinioEmTurno = evento.tipo === 'inicio';
    if (evento.tipo === 'inicio') definirRecolhaDoRaciocinio(true);
    else esconderRaciocinioView();
  } else {
    raciocinioBuffer.push(evento);
    if (raciocinioBuffer.length > RACIOCINIO_MEMORIA) raciocinioBuffer.shift();
    esperarOciosidadeDoRaciocinio();
  }
  if (raciocinioView && !raciocinioView.webContents.isDestroyed() && !raciocinioView.webContents.isLoading()) {
    raciocinioView.webContents.send('raciocinio:evento', evento);
  }
}

function avisarRecolhaDoRaciocinio(recolhido) {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  if (raciocinioView.webContents.isLoading()) return;
  raciocinioView.webContents.send('raciocinio:recolhido', !!recolhido);
}

function avisarLargoDoRaciocinio(largo) {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  if (raciocinioView.webContents.isLoading()) return;
  raciocinioView.webContents.send('raciocinio:largo', !!largo);
}

function avisarEscalaDoRaciocinio() {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  if (raciocinioView.webContents.isLoading()) return;
  const zoom = raciocinioView.webContents.getZoomFactor() || 1;
  raciocinioView.webContents.send('raciocinio:escala', zoom);
}

function avisarAnimacaoDoRaciocinio(animando) {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  if (raciocinioView.webContents.isLoading()) return;
  raciocinioView.webContents.send('raciocinio:animando', !!animando);
}

function definirRecolhaDoRaciocinio(recolhido) {
  const alvo = !!recolhido;
  const mudou = alvo !== raciocinioRecolhido;
  raciocinioRecolhido = alvo;
  if (!raciocinioView || raciocinioView.webContents.isDestroyed() || raciocinioSaindo) return;
  if (!raciocinioView.getVisible()) {
    avisarRecolhaDoRaciocinio(alvo);
    return;
  }
  if (!mudou) return;
  if (alvo) {
    avisarRecolhaDoRaciocinio(true);
    definirCaixaDoRaciocinio(caixaDeToqueDoRaciocinio(), RACIOCINIO_CAIXA_MS);
    return;
  }
  definirCaixaDoRaciocinio(caixaDeToqueDoRaciocinio(), RACIOCINIO_CAIXA_MS);
}

function definirLargoDoRaciocinio(largo) {
  const alvo = !!largo;
  const mudou = alvo !== raciocinioLargo;
  raciocinioLargo = alvo;
  avisarLargoDoRaciocinio(alvo);
  if (!mudou) return;
  if (!raciocinioView || raciocinioView.webContents.isDestroyed() || raciocinioSaindo) return;
  if (!raciocinioView.getVisible()) return;
  definirCaixaDoRaciocinio(caixaDeToqueDoRaciocinio(), RACIOCINIO_CAIXA_MS);
}

function definirCaixaDoRaciocinio(destino, duracao) {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  const animava = !!raciocinioAnimando;
  if (raciocinioAnimando) {
    clearInterval(raciocinioAnimando);
    raciocinioAnimando = null;
  }
  const inicio = raciocinioView.getBounds();
  if (mesmoRect(inicio, destino) || !(duracao > 0)) {
    if (!mesmoRect(inicio, destino)) raciocinioView.setBounds(destino);
    if (animava) avisarAnimacaoDoRaciocinio(false);
    avisarRecolhaDoRaciocinio(raciocinioRecolhido);
    return;
  }
  avisarAnimacaoDoRaciocinio(true);
  const partida = Date.now();
  raciocinioAnimando = setInterval(() => {
    if (!raciocinioView || raciocinioView.webContents.isDestroyed()) {
      clearInterval(raciocinioAnimando);
      raciocinioAnimando = null;
      return;
    }
    const avanco = curvaDaCaixa(Math.min(1, (Date.now() - partida) / duracao));
    if (avanco >= 1) {
      clearInterval(raciocinioAnimando);
      raciocinioAnimando = null;
      if (!mesmoRect(raciocinioView.getBounds(), destino)) raciocinioView.setBounds(destino);
      avisarAnimacaoDoRaciocinio(false);
      avisarRecolhaDoRaciocinio(raciocinioRecolhido);
      return;
    }
    const quadro = {
      x: Math.round(inicio.x + (destino.x - inicio.x) * avanco),
      y: Math.round(inicio.y + (destino.y - inicio.y) * avanco),
      width: Math.round(inicio.width + (destino.width - inicio.width) * avanco),
      height: Math.round(inicio.height + (destino.height - inicio.height) * avanco)
    };
    if (!mesmoRect(raciocinioView.getBounds(), quadro)) raciocinioView.setBounds(quadro);
  }, RACIOCINIO_QUADRO_MS);
}

function curvaDaCaixa(tempo) {
  const acharT = (x) => {
    let baixo = 0;
    let alto = 1;
    let meio = x;
    for (let passo = 0; passo < 12; passo++) {
      const atual = 3 * (1 - meio) * (1 - meio) * meio * 0.4 + 3 * (1 - meio) * meio * meio * 0.2 + meio * meio * meio;
      if (atual < x) baixo = meio;
      else alto = meio;
      meio = (baixo + alto) / 2;
    }
    return meio;
  };
  const t = Math.max(0, Math.min(1, Number(tempo) || 0));
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const s = acharT(t);
  return 3 * (1 - s) * s * s + s * s * s;
}

function urlDoAlvo(texto) {
  const temEsquema = /^[a-z][a-z0-9+.-]*:\/\//i.test(texto);
  if (temEsquema || /^(localhost|127\.0\.0\.1):/i.test(texto)) {
    return { remoto: true, url: temEsquema ? texto : 'http://' + texto, caminho: '' };
  }
  if (/^[a-z]:[\\/]/i.test(texto) || texto.startsWith('\\\\') || texto.startsWith('/')) {
    const caminho = path.resolve(texto);
    return { remoto: false, url: 'file:///' + caminho.replace(/\\/g, '/'), caminho: caminho };
  }
  return null;
}

function mesmoAlvoCarregado(wc, url) {
  const atual = wc.getURL();
  if (!atual) return false;
  if (atual === url) return true;
  if (!/^file:/i.test(atual) || !/^file:/i.test(url)) return false;
  try {
    const a = decodeURIComponent(new URL(atual).pathname);
    const b = decodeURIComponent(new URL(url).pathname);
    return a.toLowerCase() === b.toLowerCase();
  } catch (e) {
    return false;
  }
}

function carregarNoPreview(alvo) {
  const texto = String(alvo || '').trim();
  if (!texto) return { ok: false, erro: 'Endereco vazio.' };
  const destino = urlDoAlvo(texto);
  if (!destino) return { ok: false, erro: 'Endereco invalido: ' + texto };
  const tipo = tipoDoAlvo(texto);
  const view = criarViewDoTipo(tipo);
  mostrarSoAVista(tipo);
  const wc = view.webContents;
  if (mesmoAlvoCarregado(wc, destino.url)) {
    enviarEstadoDoPreview();
    return { ok: true, alvo: destino.url, reutilizado: true };
  }
  if (destino.remoto) wc.loadURL(destino.url);
  else wc.loadFile(destino.caminho);
  return { ok: true, alvo: destino.url };
}

const PRAZO_DA_SONDA_MS = 1500;

function mesmaPagina(atual, destino) {
  try {
    const a = new URL(atual);
    const b = new URL(destino);
    return a.origin === b.origin && a.pathname === b.pathname && a.search === b.search;
  } catch (e) {
    return false;
  }
}

function paginaResponde(view, limite) {
  if (!view || view.webContents.isDestroyed()) return Promise.resolve(true);
  const sonda = view.webContents.executeJavaScript('1').then(() => true, () => true);
  const prazo = new Promise((resolve) => setTimeout(() => resolve(false), limite));
  return Promise.race([sonda, prazo]);
}

async function carregarRespeitandoPaginaPresa(alvo) {
  const destino = String(alvo || '').trim();
  const resolvido = urlDoAlvo(destino);
  const tipo = tipoDoAlvo(destino);
  const view = viewDoTipo(tipo);
  const atual = view && resolvido ? view.webContents.getURL() : '';
  const mesma = !!atual && mesmaPagina(atual, resolvido.url);
  const repetida = mesma && mesmoAlvoCarregado(view.webContents, resolvido.url);
  if (mesma && !repetida) {
    const respondeu = await paginaResponde(view, PRAZO_DA_SONDA_MS);
    if (!respondeu) descartarPreviewView(tipo);
  }
  return carregarNoPreview(alvo);
}

function recarregarPreview() {
  const view = previewVivo();
  if (!view) return { ok: false, erro: 'Nenhuma pagina carregada no preview.' };
  view.webContents.reload();
  return { ok: true };
}

function navegarPreview(passo) {
  const view = previewVivo();
  if (!view) return { ok: false, erro: 'Nenhuma pagina carregada no preview.' };
  const historico = view.webContents.navigationHistory;
  if (!historico) return { ok: false, erro: 'Historico indisponivel nesta versao do Electron.' };
  if (passo < 0) {
    if (!historico.canGoBack()) return { ok: false, erro: 'Nao ha pagina anterior.' };
    historico.goBack();
  } else {
    if (!historico.canGoForward()) return { ok: false, erro: 'Nao ha pagina seguinte.' };
    historico.goForward();
  }
  return { ok: true };
}

function normalizarZoom(valor) {
  const numero = Number(valor);
  if (!Number.isFinite(numero) || numero < ZOOM_MINIMO || numero > ZOOM_MAXIMO) return null;
  return numero;
}

function lerZoomPersistido() {
  try {
    const dados = JSON.parse(fs.readFileSync(CAMINHO_SETTINGS, 'utf8'));
    return normalizarZoom((dados.interface || {}).zoom) || 1;
  } catch (erro) {
    return 1;
  }
}

function gravarZoom(valor) {
  let dados = {};
  try {
    const lido = JSON.parse(fs.readFileSync(CAMINHO_SETTINGS, 'utf8'));
    if (lido && typeof lido === 'object' && !Array.isArray(lido)) dados = lido;
  } catch (erro) {
    dados = {};
  }
  dados.interface = Object.assign({}, dados.interface, { zoom: valor });
  const temporario = CAMINHO_SETTINGS + '.tmp';
  try {
    fs.mkdirSync(path.dirname(CAMINHO_SETTINGS), { recursive: true });
    fs.writeFileSync(temporario, JSON.stringify(dados, null, 2), 'utf8');
    fs.renameSync(temporario, CAMINHO_SETTINGS);
    return true;
  } catch (erro) {
    return false;
  }
}

function aplicarZoomAoPreview() {
  for (const chave of TIPOS_DE_VIEW) {
    const view = viewDoTipo(chave);
    if (!view) continue;
    try {
      view.webContents.setZoomFactor(zoomDaInterface);
    } catch (erro) {}
  }
}

function aplicarZoomAoRaciocinio() {
  if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
  try {
    raciocinioView.webContents.setZoomFactor(zoomDaInterface);
    raciocinioView.setBorderRadius(Math.round(RACIOCINIO_RAIO_JANELA * zoomDaInterface));
  } catch (erro) {}
  avisarEscalaDoRaciocinio();
  aplicarLimitesDoRaciocinio();
}

function definirZoomDaInterface(valor, avisar) {
  const zoom = normalizarZoom(valor);
  if (zoom === null) return { ok: false, erro: 'Zoom fora do intervalo: ' + valor };
  zoomDaInterface = zoom;
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.setZoomFactor(zoom);
  aplicarZoomAoPreview();
  aplicarZoomAoRaciocinio();
  gravarZoom(zoom);
  if (avisar !== false && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('menu:set-zoom', zoom);
  }
  return { ok: true, zoom: zoom };
}

function passoDeZoom(direcao) {
  let indice = PASSOS_DE_ZOOM.findIndex((v) => Math.abs(v - zoomDaInterface) < 0.001);
  if (indice === -1) indice = PASSOS_DE_ZOOM.indexOf(1);
  const alvo = Math.min(PASSOS_DE_ZOOM.length - 1, Math.max(0, indice + direcao));
  return definirZoomDaInterface(PASSOS_DE_ZOOM[alvo]);
}

async function escolherFicheiroDoPreview(raiz) {
  const opcoes = {
    properties: ['openFile'],
    filters: [
      { name: 'Paginas web', extensions: ['html', 'htm', 'svg'] },
      { name: 'Todos os ficheiros', extensions: ['*'] }
    ]
  };
  if (raiz) opcoes.defaultPath = raiz;
  const resultado = await dialog.showOpenDialog(mainWindow, opcoes);
  if (resultado.canceled || !resultado.filePaths.length) return { ok: false, cancelado: true };
  return carregarNoPreview(resultado.filePaths[0]);
}

function abrirPreviewNoNavegador() {
  const view = previewVivo();
  const url = view ? view.webContents.getURL() : '';
  if (!url) return { ok: false, erro: 'Nada para abrir no navegador.' };
  shell.openExternal(url);
  return { ok: true, url: url };
}

function abrirDevToolsDoPreview() {
  const view = previewVivo() || criarViewDoTipo(previewAtiva || 'node');
  const wc = view.webContents;
  try {
    if (wc.debugger.isAttached()) wc.debugger.detach();
  } catch (e) {}
  wc.openDevTools({ mode: 'detach' });
  wc.once('devtools-closed', () => prepararDepurador(view));
  return { ok: true };
}

const ACOES_DO_PREVIEW = {
  recarregar: () => recarregarPreview(),
  ferramentas: (valor) => definirFerramentasDoPreview(valor),
  voltar: () => navegarPreview(-1),
  avancar: () => navegarPreview(1),
  ficheiro: (valor) => escolherFicheiroDoPreview(valor),
  externo: () => abrirPreviewNoNavegador(),
  devtools: () => abrirDevToolsDoPreview()
};

function executarAcaoDoPreview(acao, valor) {
  const executar = ACOES_DO_PREVIEW[acao];
  if (!executar) return { ok: false, erro: 'Acao desconhecida: ' + acao };
  return executar(valor);
}

function aplicarFerramentasDoPreview() {
  const detalhe = previewFerramentas ? 'true' : 'false';
  for (const chave of TIPOS_DE_VIEW) {
    const view = viewDoTipo(chave);
    if (!view) continue;
    view.webContents
      .executeJavaScript("document.dispatchEvent(new CustomEvent('axio-ferramentas', { detail: " + detalhe + " }))")
      .catch(() => {});
  }
}

function definirFerramentasDoPreview(ligado) {
  previewFerramentas = !!ligado;
  aplicarFerramentasDoPreview();
  return { ok: true, ligado: previewFerramentas };
}

app.on('ready', () => {
  ipcMain.handle('select-folder', async (e, pastaAtual) => {
    const opcoes = { properties: ['openDirectory'] };
    if (pastaAtual) opcoes.defaultPath = pastaAtual;
    const result = await dialog.showOpenDialog(mainWindow, opcoes);
    return result.filePaths[0];
  });

  ipcMain.handle('preview:carregar', (e, alvo) => (
    veioDaJanelaPrincipal(e) ? carregarRespeitandoPaginaPresa(alvo) : { ok: false, erro: 'Origem nao autorizada.' }
  ));
  ipcMain.handle('preview:acao', (e, acao, valor) => (
    veioDaJanelaPrincipal(e) ? executarAcaoDoPreview(acao, valor) : { ok: false, erro: 'Origem nao autorizada.' }
  ));
  ipcMain.handle('preview:descartar', (e) => {
    if (!veioDaJanelaPrincipal(e)) return { ok: false, erro: 'Origem nao autorizada.' };
    descartarPreviewView();
    return { ok: true };
  });
  ipcMain.on('preview:limites', (e, limites) => {
    if (veioDaJanelaPrincipal(e)) aplicarLimitesDoPreview(limites);
  });
  ipcMain.on('preview:visivel', (e, visivel) => {
    if (veioDaJanelaPrincipal(e)) definirVisibilidadeDoPreview(!!visivel);
  });
  ipcMain.on('raciocinio:evento', (e, evento) => {
    if (veioDaJanelaPrincipal(e)) alimentarRaciocinio(evento);
  });
  ipcMain.on('raciocinio:alternar', (e) => {
    if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
    if (e.sender !== raciocinioView.webContents) return;
    definirRecolhaDoRaciocinio(!raciocinioRecolhido);
  });
  ipcMain.on('raciocinio:largo', (e) => {
    if (!raciocinioView || raciocinioView.webContents.isDestroyed()) return;
    if (e.sender !== raciocinioView.webContents) return;
    definirLargoDoRaciocinio(!raciocinioLargo);
  });
  function montarMenu() {
    const menu = Menu.buildFromTemplate([
      {
        label: 'Exibir',
        submenu: [
          {
            label: 'Tema do Dock',
            submenu: [
              { label: 'Dark', type: 'radio', checked: temaAtual === 'dark', click: () => setTema('dark') },
              { label: 'Cinza Espacial', type: 'radio', checked: temaAtual === 'espacial', click: () => setTema('espacial') }
            ]
          },
          {
            label: 'Zoom',
            submenu: [
              { label: 'Aumentar', accelerator: 'CmdOrCtrl+=', click: () => passoDeZoom(1) },
              { label: 'Diminuir', accelerator: 'CmdOrCtrl+-', click: () => passoDeZoom(-1) },
              { label: 'Repor 100%', accelerator: 'CmdOrCtrl+0', click: () => definirZoomDaInterface(1) }
            ]
          },
          { type: 'separator' },
          { role: 'reload', label: 'Recarregar' },
          { role: 'forceReload', label: 'Recarregar ignorando cache', accelerator: 'CmdOrCtrl+Shift+R' },
          { type: 'separator' },
          { label: 'Reiniciar Backend', accelerator: 'CmdOrCtrl+Shift+B', click: () => restartFlask() }
        ]
      },
      {
        label: 'Ferramentas',
        submenu: [
          { role: 'toggleDevTools', label: 'Dev Tools' },
          { type: 'separator' },
          { label: inspectAtivo ? 'Modo Inspecionar  ✓' : 'Modo Inspecionar', click: () => pedirInspect(!inspectAtivo) }
        ]
      }
    ]);
    Menu.setApplicationMenu(menu);
  }

  function setTema(tema, enviar) {
    temaAtual = (tema === 'espacial') ? 'espacial' : 'dark';
    montarMenu();
    if (enviar !== false && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('menu:set-tema', temaAtual);
    }
  }

  function pedirInspect(ativo) {
    inspectAtivo = !!ativo;
    montarMenu();
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('menu:set-inspect', inspectAtivo);
    }
    inspecionarPreview(previewVivo(), inspectAtivo).catch(() => {});
  }

  function executarAcaoDoMenu(acao, valor) {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (acao === 'tema') return setTema(valor);
    if (acao === 'reload') return mainWindow.webContents.reload();
    if (acao === 'reload-sem-cache') return mainWindow.webContents.reloadIgnoringCache();
    if (acao === 'reiniciar-backend') return restartFlask();
    if (acao === 'devtools') return mainWindow.webContents.toggleDevTools();
    if (acao === 'inspect') return pedirInspect(!inspectAtivo);
    if (acao === 'zoom') return definirZoomDaInterface(valor);
  }

  ipcMain.on('menu:acao', (e, acao, valor) => {
    if (veioDaJanelaPrincipal(e)) executarAcaoDoMenu(acao, valor);
  });

  ipcMain.handle('menu:zoom-atual', (e) => (
    veioDaJanelaPrincipal(e)
      ? { ok: true, zoom: zoomDaInterface, minimo: ZOOM_MINIMO, maximo: ZOOM_MAXIMO }
      : { ok: false, erro: 'Origem nao autorizada.' }
  ));

  ipcMain.on('tema:set', (e, tema) => setTema(tema, false));
  ipcMain.on('inspect:set', (e, ativo) => {
    inspectAtivo = !!ativo;
    montarMenu();
    if (e.sender && !e.sender.isDestroyed()) e.sender.send('menu:set-inspect', inspectAtivo);
    inspecionarPreview(previewVivo(), inspectAtivo).catch(() => {});
  });
  setTema('dark', false);

  killProcessOnPort(5000);

  iniciarPonte({
    obterPreview: () => previewVivo(),
    obterJanela: () => (mainWindow && !mainWindow.isDestroyed() ? mainWindow : null),
    aoUsar: (acao, interage) => {
      avisarPreview('preview:uso', { acao: acao, interage: !!interage });
      mostrarRaciocinioView();
    },
    aoInspecionar: (info) => {
      if (info && info.sair) {
        if (inspectAtivo) pedirInspect(false);
        return;
      }
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('preview:inspecao', info);
      }
    },
    acoesDeFora: {
      carregar: (view, params) => {
        mostrarRaciocinioView();
        const resultado = carregarNoPreview(params.alvo);
        if (resultado && resultado.ok && resultado.alvo) {
          avisarPreview('preview:alvo', { alvo: resultado.alvo });
        }
        return resultado;
      },
      mostrar: () => trazerParaFrente()
    }
  }, (porta, token) => {
    pontePorta = porta;
    ponteToken = token;
    if (porta) console.log(`[main] Ponte do preview a escutar em 127.0.0.1:${porta}`);
    startFlask();
    waitForFlask('http://127.0.0.1:5000/', createWindow);
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  quitting = true;
  pararPonte();
  if (flaskProcess) {
    console.log(`[main] quit: finalizando Flask PID=${flaskProcess.pid} (arvore /T /F)...`);
    if (process.platform === 'win32') {
      try {
        require('child_process').execSync(`taskkill /pid ${flaskProcess.pid} /T /F`);
        console.log('[main] quit: arvore do Flask finalizada.');
      } catch (e) {
        console.log(`[main] quit: taskkill falhou (${e.message}); tentando kill simples...`);
        try { flaskProcess.kill(); } catch (e2) { console.log(`[main] quit: kill simples falhou (${e2.message})`); }
      }
    } else {
      try { flaskProcess.kill(); } catch (e) { console.log(`[main] quit: kill falhou (${e.message})`); }
    }
  } else {
    console.log('[main] quit: nenhum Flask em execucao para finalizar.');
  }
  killProcessOnPort(5000);
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});
