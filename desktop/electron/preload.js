const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pharmacare", {
  apiBase: "http://127.0.0.1:8000/api/v1",
  printPrescription: () => ipcRenderer.invoke("pharmacare:print"),
});
