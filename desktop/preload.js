const { contextBridge, ipcRenderer } = require('electron')

// Minimal, explicit surface exposed to the web UI.
contextBridge.exposeInMainWorld('localrepo', {
  pickFolder: () => ipcRenderer.invoke('pick-folder'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
})
