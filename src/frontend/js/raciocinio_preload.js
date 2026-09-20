const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('raciocinio', {
    aoHistorico: (fn) => ipcRenderer.on('raciocinio:historico', (_evento, lista) => fn(lista || [])),
    aoEvento: (fn) => ipcRenderer.on('raciocinio:evento', (_evento, evento) => fn(evento)),
    aoAbrir: (fn) => ipcRenderer.on('raciocinio:abrir', () => fn()),
    aoRecolha: (fn) => ipcRenderer.on('raciocinio:recolhido', (_evento, valor) => fn(!!valor)),
    aoLargo: (fn) => ipcRenderer.on('raciocinio:largo', (_evento, valor) => fn(!!valor)),
    aoSair: (fn) => ipcRenderer.on('raciocinio:sair', () => fn()),
    aoEscala: (fn) => ipcRenderer.on('raciocinio:escala', (_evento, valor) => fn(Number(valor))),
    alternar: () => ipcRenderer.send('raciocinio:alternar'),
    largo: () => ipcRenderer.send('raciocinio:largo')
});
