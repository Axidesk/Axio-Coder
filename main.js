process.env.ELECTRON_NO_ATTACH_CONSOLE = 'true';
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

app.commandLine.appendSwitch('log-level', '3');
app.commandLine.appendSwitch('disable-logging');
process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = 'true';

let mainWindow;
let flaskProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    icon: path.join(__dirname, 'icons', 'icon.ico'),
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    backgroundColor: '#1e1e1e'
  });

  mainWindow.loadFile('index.html');

  // Abre links externos (ex.: URLs visitadas pela busca web) no navegador padrão
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.on('ready', () => {
  // Configurar IPC para seleção de pasta
  ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory']
    });
    return result.filePaths[0];
  });

  // Iniciar o servidor Flask
  flaskProcess = spawn('python', ['app.py']);

  flaskProcess.stdout.on('data', (data) => {
    console.log(`Flask stdout: ${data}`);
  });

  flaskProcess.stderr.on('data', (data) => {
    console.error(`Flask stderr: ${data}`);
  });

  // Esperar um pouco para o Flask iniciar antes de abrir a janela
  setTimeout(createWindow, 2000);
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  if (flaskProcess) {
    if (process.platform === 'win32') {
      // Mata a árvore inteira: o minerador (python -m mempalace mine) é
      // filho do Flask. Se matarmos só o pai, o filho fica órfão segurando
      // o lock do chroma.sqlite3 e trava o app no próximo start.
      try {
        require('child_process').execSync(`taskkill /pid ${flaskProcess.pid} /T /F`);
      } catch (e) {
        flaskProcess.kill();
      }
    } else {
      flaskProcess.kill();
    }
  }
});

app.on('activate', function () {
  if (mainWindow === null) {
    createWindow();
  }
});