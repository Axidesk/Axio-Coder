const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('raciocinio', {
    aoHistorico: (fn) => ipcRenderer.on('raciocinio:historico', (_evento, lista) => fn(lista || [])),
    aoEvento: (fn) => ipcRenderer.on('raciocinio:evento', (_evento, evento) => fn(evento)),
    aoAbrir: (fn) => ipcRenderer.on('raciocinio:abrir', () => fn()),
    recolher: (estado) => ipcRenderer.send('raciocinio:recolher', !!estado)
});
