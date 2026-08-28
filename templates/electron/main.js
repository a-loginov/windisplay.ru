const { app, BrowserWindow, Menu, globalShortcut, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");

const DEFAULT_SERVER_URL = "https://panel.windisplay.ru";
const CONFIG_PATH = () => path.join(app.getPath("userData"), "device.json");
const CACHE_DIR = () => path.join(app.getPath("userData"), "cache");
const CACHE_MANIFEST = () => path.join(CACHE_DIR(), "manifest.json");

let mainWindow = null;
let showingSettings = false;

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH(), "utf-8"));
  } catch {
    return { serverUrl: DEFAULT_SERVER_URL };
  }
}

function writeConfig(patch) {
  const next = { ...readConfig(), ...patch };
  fs.mkdirSync(path.dirname(CONFIG_PATH()), { recursive: true });
  fs.writeFileSync(CONFIG_PATH(), JSON.stringify(next, null, 2));
  return next;
}

function ensureCacheDir() {
  fs.mkdirSync(CACHE_DIR(), { recursive: true });
}

function readManifest() {
  try {
    return JSON.parse(fs.readFileSync(CACHE_MANIFEST(), "utf-8"));
  } catch {
    return null;
  }
}

function writeManifest(manifest) {
  ensureCacheDir();
  fs.writeFileSync(CACHE_MANIFEST(), JSON.stringify(manifest, null, 2));
}

function extFromContentType(contentType, fallbackUrl) {
  if (contentType && contentType.includes("video")) return ".mp4";
  if (contentType && contentType.includes("png")) return ".png";
  if (contentType && contentType.includes("gif")) return ".gif";
  if (contentType && contentType.includes("jpeg")) return ".jpg";
  const match = /\.[a-zA-Z0-9]+($|\?)/.exec(fallbackUrl || "");
  return match ? match[0].replace(/\?$/, "") : ".bin";
}

async function downloadToCache(item) {
  const res = await fetch(item.url);
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  const contentType = res.headers.get("content-type") || "";
  const ext = extFromContentType(contentType, item.url);
  const fileName = `${item.id}${ext}`;
  const filePath = path.join(CACHE_DIR(), fileName);
  const buffer = Buffer.from(await res.arrayBuffer());
  ensureCacheDir();
  fs.writeFileSync(filePath, buffer);
  return fileName;
}

async function refreshPlaylist() {
  const config = readConfig();
  if (!config.token) {
    return { items: [], online: false, error: "not-paired" };
  }

  const serverUrl = config.serverUrl || DEFAULT_SERVER_URL;

  try {
    const res = await fetch(`${serverUrl}/api/device/playlist`, {
      headers: { Authorization: `Bearer ${config.token}` },
    });
    if (!res.ok) throw new Error(`server responded ${res.status}`);
    const data = await res.json();
    const remoteItems = Array.isArray(data.items) ? data.items : [];

    const previous = readManifest();
    const previousById = new Map((previous?.items || []).map((i) => [i.id, i]));

    const cachedItems = [];
    for (const remote of remoteItems) {
      const known = previousById.get(remote.id);
      let fileName = known && known.remoteUrl === remote.url ? known.fileName : null;
      if (!fileName || !fs.existsSync(path.join(CACHE_DIR(), fileName))) {
        fileName = await downloadToCache(remote);
      }
      cachedItems.push({
        id: remote.id,
        type: remote.type,
        duration: remote.duration || 8,
        remoteUrl: remote.url,
        fileName,
      });
    }

    const manifest = { updatedAt: new Date().toISOString(), items: cachedItems };
    writeManifest(manifest);

    return {
      online: true,
      updatedAt: manifest.updatedAt,
      items: cachedItems.map((i) => ({
        id: i.id,
        type: i.type,
        duration: i.duration,
        src: `file://${path.join(CACHE_DIR(), i.fileName)}`,
      })),
    };
  } catch (err) {
    const manifest = readManifest();
    if (!manifest) {
      return { items: [], online: false, error: "no-cache" };
    }
    return {
      online: false,
      updatedAt: manifest.updatedAt,
      items: manifest.items.map((i) => ({
        id: i.id,
        type: i.type,
        duration: i.duration,
        src: `file://${path.join(CACHE_DIR(), i.fileName)}`,
      })),
    };
  }
}

function dirSize(dirPath) {
  let total = 0;
  let count = 0;
  if (!fs.existsSync(dirPath)) return { total, count };
  for (const name of fs.readdirSync(dirPath)) {
    if (name === "manifest.json") continue;
    const stat = fs.statSync(path.join(dirPath, name));
    if (stat.isFile()) {
      total += stat.size;
      count += 1;
    }
  }
  return { total, count };
}

function createWindow(startPage) {
  mainWindow = new BrowserWindow({
    fullscreen: true,
    kiosk: true,
    frame: false,
    autoHideMenuBar: true,
    backgroundColor: "#000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "src", startPage));
}

function goToSettings() {
  const config = readConfig();
  if (!config.token || showingSettings) return;
  showingSettings = true;
  mainWindow.loadFile(path.join(__dirname, "src", "settings.html"));
}

function goToPlayer() {
  showingSettings = false;
  mainWindow.loadFile(path.join(__dirname, "src", "player.html"));
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);

  const config = readConfig();
  createWindow(config.token ? "player.html" : "pairing.html");

  globalShortcut.register("CommandOrControl+Shift+S", () => {
    if (showingSettings) goToPlayer();
    else goToSettings();
  });
  globalShortcut.register("CommandOrControl+Shift+Q", () => app.quit());
  globalShortcut.register("CommandOrControl+Shift+I", () => {
    mainWindow.webContents.toggleDevTools();
  });
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  app.quit();
});

// ---------------- IPC ----------------

ipcMain.handle("config:get", () => {
  const { token, ...safe } = readConfig();
  return { ...safe, paired: Boolean(token) };
});

ipcMain.handle("device:set-server", (_e, serverUrl) => {
  writeConfig({ serverUrl });
  return true;
});

ipcMain.handle("pairing:start", async () => {
  const config = readConfig();
  const serverUrl = config.serverUrl || DEFAULT_SERVER_URL;
  const res = await fetch(`${serverUrl}/api/device/register`, { method: "POST" });
  if (!res.ok) throw new Error(`register failed: ${res.status}`);
  const data = await res.json();
  writeConfig({ deviceId: data.deviceId, serverUrl });
  return { code: data.code, expiresAt: data.expiresAt };
});

ipcMain.handle("pairing:poll", async () => {
  const config = readConfig();
  if (!config.deviceId) return { paired: false };
  const serverUrl = config.serverUrl || DEFAULT_SERVER_URL;
  const res = await fetch(`${serverUrl}/api/device/pair/status?deviceId=${config.deviceId}`);
  if (!res.ok) return { paired: false };
  const data = await res.json();
  if (data.paired) {
    writeConfig({ token: data.token, deviceName: data.deviceName });
    return { paired: true };
  }
  return { paired: false };
});

ipcMain.handle("player:get-playlist", () => refreshPlaylist());

ipcMain.handle("player:go-pairing", () => {
  mainWindow.loadFile(path.join(__dirname, "src", "pairing.html"));
});

ipcMain.handle("settings:get-cache-info", () => {
  const { total, count } = dirSize(CACHE_DIR());
  return { bytes: total, count };
});

ipcMain.handle("settings:clear-cache", () => {
  if (fs.existsSync(CACHE_DIR())) {
    fs.rmSync(CACHE_DIR(), { recursive: true, force: true });
  }
  return true;
});

ipcMain.handle("settings:unpair", () => {
  const config = readConfig();
  delete config.token;
  delete config.deviceId;
  delete config.deviceName;
  fs.writeFileSync(CONFIG_PATH(), JSON.stringify(config, null, 2));
  showingSettings = false;
  mainWindow.loadFile(path.join(__dirname, "src", "pairing.html"));
  return true;
});

ipcMain.handle("settings:back-to-player", () => goToPlayer());

ipcMain.handle("app:relaunch", () => {
  app.relaunch();
  app.exit(0);
});
