const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('bridge', {
  onEvent: (cb) => ipcRenderer.on('pet-event', (_e, msg) => cb(msg)),
  send: (obj) => ipcRenderer.send('to-bridge', obj),
  openSettings: () => ipcRenderer.send('open-llm-settings'),
  getPathForFile: (file) => webUtils.getPathForFile(file),
});
