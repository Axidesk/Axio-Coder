const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('raciocinio', {
    aoHistorico: (fn) => ipcRenderer.on('raciocinio:historico', (_evento, lista) => fn(lista || [])),
    aoEvento: (fn) => ipcRenderer.on('raciocinio:evento', (_evento, evento) => fn(evento)),
    aoAbrir: (fn) => ipcRenderer.on('raciocinio:abrir', () => fn()),
    aoRecolha: (fn) => ipcRenderer.on('raciocinio:recolhido', (_evento, valor) => fn(!!valor)),
    aoSair: (fn) => ipcRenderer.on('raciocinio:sair', () => fn()),
    aoTrocar: (fn) => ipcRenderer.on('raciocinio:trocar', (_evento, valor) => fn(!!valor)),
    aoEscala: (fn) => ipcRenderer.on('raciocinio:escala', (_evento, valor) => fn(Number(valor))),
    aoAnimacao: (fn) => ipcRenderer.on('raciocinio:animacao', (_evento, ligado) => fn(!!ligado)),
    alternar: () => ipcRenderer.send('raciocinio:alternar'),
    tique: () => ipcRenderer.send('raciocinio:tique')
});
