process.env.ELECTRON_NO_ATTACH_CONSOLE = 'true';
const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

app.commandLine.appendSwitch('log-level', '3');
app.commandLine.appendSwitch('disable-logging');
process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = 'true';

// ---- Performance / aceleração de hardware ----
// Rasterização via GPU (compositor Chromium) para scroll/animações fluidas.
app.commandLine.appendSwitch('enable-gpu-rasterization');
// Zero-copy: evita cópia de texturas entre CPU e GPU (menos latência no paint).
app.commandLine.appendSwitch('enable-zero-copy');
// Usa a GPU mesmo quando o driver está na blocklist do Chromium (máquinas potentes).
app.commandLine.appendSwitch('ignore-gpu-blocklist');
// Força a GPU dedicada de alto desempenho (NVIDIA Optimus / AMD) em vez da integrada.
app.commandLine.appendSwitch('force_high_performance_gpu');
// Buffers de memória nativos de GPU (compartilhamento eficiente de texturas).
app.commandLine.appendSwitch('enable-native-gpu-memory-buffers');
// Skia como renderer (padrão moderno do Chromium) + rasterização fora do compositor.
app.commandLine.appendSwitch('enable-features', 'UseSkiaRenderer,CanvasOopRasterization');
// Mais memória heap para o V8 (o renderer é pesado: Monaco + sessão + logs).
app.commandLine.appendSwitch('js-flags', '--max-old-space-size=4096');
// Suporte a DPI alto (monitores 4K/Retina) mantendo o paint nítido e rápido.
app.commandLine.appendSwitch('high-dpi-support', '1');
// Evita que o Chromium "estrangule" a renderização de janelas/timers em
// segundo plano ou ocluídas (causa clássica de engasgo em animações no Windows).
app.commandLine.appendSwitch('disable-renderer-backgrounding');
app.commandLine.appendSwitch('disable-background-timer-throttling');
app.commandLine.appendSwitch('disable-backgrounding-occluded-windows');
// Windows: desliga um recurso de "occlusão nativa" que pode congelar a janela.
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');

let mainWindow;
let flaskProcess;
let temaAtual = 'dark';
let quitting = false;
let flaskRestarts = 0;
let reiniciandoBackend = false;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    icon: path.join(__dirname, '..', 'data', 'icons', 'icon.ico'),
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      backgroundThrottling: false,
      spellcheck: false
    },
    backgroundColor: '#1e1e1e'
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

  // Abre links externos (ex.: URLs visitadas pela busca web) no navegador padrão
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Correção do Ctrl+V no Monaco (Electron 34+ removeu document.execCommand('paste')).
  // Intercepta o atalho e usa o caminho de paste nativo do Electron, que funciona
  // tanto no editor quanto nos inputs do find/replace widget.
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

  mainWindow.on('closed', function () {
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
        // Nunca matar processos do sistema: 0 = System Idle, 4 = System (kernel).
        // O socket de um processo que crashou pode aparecer como PID 4 no netstat.
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

// Reinicia apenas o processo Python (Flask), sem fechar o Electron.
// Necessario porque o Flask roda com debug=False (sem auto-reload): codigo .py
// alterado so entra em vigor quando o processo morre e sobe de novo.
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

app.on('ready', () => {
  // Configurar IPC para seleção de pasta
  ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory']
    });
    return result.filePaths[0];
  });

  // Menu nativo: tema do dock (dark / cinza espacial)
  function setTema(tema, enviar) {
    temaAtual = (tema === 'espacial') ? 'espacial' : 'dark';
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
          { type: 'separator' },
          { role: 'reload', label: 'Recarregar' },
          { role: 'forceReload', label: 'Recarregar ignorando cache', accelerator: 'CmdOrCtrl+Shift+R' },
          { type: 'separator' },
          { label: 'Reiniciar Backend', accelerator: 'CmdOrCtrl+Shift+B', click: () => restartFlask() },
          { type: 'separator' },
          { role: 'toggleDevTools', label: 'Ferramentas de Desenvolvedor' }
        ]
      }
    ]);
    Menu.setApplicationMenu(menu);
    if (enviar !== false && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('menu:set-tema', temaAtual);
    }
  }
  ipcMain.on('tema:set', (e, tema) => setTema(tema, false));
  setTema('dark', false);

  // Mata qualquer processo orfao que esteja segurando a porta 5000 (de uma
  // sessao anterior fechada de forma abrupta). Sem isso, o Flask novo morre
  // com "Address already in use" e a interface abre com ERR_CONNECTION_REFUSED.
  killProcessOnPort(5000);

  startFlask();

  // Espera o Flask subir antes de abrir a janela (a interface agora e servida via HTTP)
  waitForFlask('http://127.0.0.1:5000/', createWindow);
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  quitting = true;
  if (flaskProcess) {
    console.log(`[main] quit: finalizando Flask PID=${flaskProcess.pid} (arvore /T /F)...`);
    if (process.platform === 'win32') {
      // Mata a árvore inteira: o minerador (python -m mempalace mine) é
      // filho do Flask. Se matarmos só o pai, o filho fica órfão segurando
      // o lock do chroma.sqlite3 e trava o app no próximo start.
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
  // Garantia extra: mata qualquer processo que ainda esteja segurando a porta
  // 5000 (filhos orfaos do mempalace que sobreviveram ao kill da arvore).
  killProcessOnPort(5000);
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});
