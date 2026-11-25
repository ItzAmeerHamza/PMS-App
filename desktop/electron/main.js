const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");

const isDev = !app.isPackaged;

function createWindow() {
  const win = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1080,
    minHeight: 720,
    title: "PharmaCare",
    backgroundColor: "#eef3f1",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    win.loadURL("http://127.0.0.1:5173");
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

ipcMain.handle("pharmacare:print", async (event) => {
  const contents = event.sender;
  let printers = [];
  try {
    printers = await contents.getPrintersAsync();
  } catch {
    return { ok: false, error: "The printer did not accept this prescription" };
  }
  const printer = printers.find((item) => item.isDefault) || printers[0];
  if (!printer) {
    return { ok: false, error: "No printer is attached" };
  }
  return new Promise((resolve) => {
    contents.print(
      {
        silent: true,
        printBackground: true,
        deviceName: printer.name,
        copies: 1,
        pageSize: "A4",
      },
      (success, failureReason) => {
        if (success) {
          resolve({ ok: true, printer: printer.displayName || printer.name });
          return;
        }
        resolve({ ok: false, error: failureReason || "The printer did not accept this prescription" });
      },
    );
  });
});

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
