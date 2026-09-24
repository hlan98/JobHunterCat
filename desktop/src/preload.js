const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('petBridge', {
  onCursor: (cb) => ipcRenderer.on('cursor-position', (_e, d) => cb(d)),
  onLockState: (cb) => ipcRenderer.on('lock-state', (_e, v) => cb(v)),
  onPetEvent: (cb) => ipcRenderer.on('pet-event', (_e, msg) => cb(msg)),
  dragStart: () => ipcRenderer.send('drag-start'),
  dragMove: () => ipcRenderer.send('drag-move'),
  dragEnd: () => ipcRenderer.send('drag-end'),
  openContextMenu: () => ipcRenderer.send('pet-context-menu'),
  dropFile: (path) => ipcRenderer.send('resume-file', path),
  getPathForFile: (file) => webUtils.getPathForFile(file),
});
