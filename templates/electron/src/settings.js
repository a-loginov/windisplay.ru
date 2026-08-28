const deviceNameEl = document.getElementById("deviceName");
const pairStatusEl = document.getElementById("pairStatus");
const cacheInfoEl = document.getElementById("cacheInfo");
const serverUrlInput = document.getElementById("serverUrl");

function formatBytes(bytes) {
    if (!bytes) return "0 МБ";
    const mb = bytes / (1024 * 1024);
    if (mb < 1024) return `${mb.toFixed(1)} МБ`;
    return `${(mb / 1024).toFixed(2)} ГБ`;
}

async function load() {
    const config = await window.api.getConfig();
    deviceNameEl.textContent = config.deviceName || "Без имени";
    serverUrlInput.value = config.serverUrl || "";

    pairStatusEl.className = `status ${config.paired ? "status--online" : "status--offline"}`;
    pairStatusEl.innerHTML = `<span class="status__dot"></span>${config.paired ? "Подключено" : "Не подключено"}`;

    const cache = await window.api.getCacheInfo();
    cacheInfoEl.textContent = `${formatBytes(cache.bytes)} · ${cache.count} файлов`;
}

document.getElementById("saveServer").addEventListener("click", async () => {
    await window.api.setServerUrl(serverUrlInput.value.trim());
    load();
});

document.getElementById("clearCache").addEventListener("click", async () => {
    await window.api.clearCache();
    load();
});

document.getElementById("relaunch").addEventListener("click", () => {
    window.api.relaunchApp();
});

document.getElementById("unpair").addEventListener("click", async () => {
    const sure = confirm("Отвязать это устройство от аккаунта? Кэш и настройки сервера сохранятся.");
    if (sure) await window.api.unpair();
});

document.getElementById("back").addEventListener("click", () => {
    window.api.backToPlayer();
});

load();
