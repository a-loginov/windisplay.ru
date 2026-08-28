const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  getConfig: () => ipcRenderer.invoke("config:get"),
  setServerUrl: (serverUrl) => ipcRenderer.invoke("device:set-server", serverUrl),

  startPairing: () => ipcRenderer.invoke("pairing:start"),
  pollPairing: () => ipcRenderer.invoke("pairing:poll"),

  getPlaylist: () => ipcRenderer.invoke("player:get-playlist"),
  goToPairing: () => ipcRenderer.invoke("player:go-pairing"),

  getCacheInfo: () => ipcRenderer.invoke("settings:get-cache-info"),
  clearCache: () => ipcRenderer.invoke("settings:clear-cache"),
  unpair: () => ipcRenderer.invoke("settings:unpair"),
  backToPlayer: () => ipcRenderer.invoke("settings:back-to-player"),

  relaunchApp: () => ipcRenderer.invoke("app:relaunch"),
});
