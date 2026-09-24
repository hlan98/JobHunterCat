const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('bridge', {
  onEvent: (cb) => ipcRenderer.on('pet-event', (_e, msg) => cb(msg)),
  onGotoPage: (cb) => ipcRenderer.on('goto-page', (_e, page) => cb(page)),
  send: (obj) => ipcRenderer.send('to-bridge', obj),
  openResumePicker: () => ipcRenderer.send('open_resume_picker'),
});
