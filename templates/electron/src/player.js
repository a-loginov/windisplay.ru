const stage = document.getElementById("stage");
const emptyState = document.getElementById("empty");
const badge = document.getElementById("badge");

let items = [];
let currentIds = "";
let activeIndex = 0;
let advanceTimer = null;

function setOffline(offline) {
    badge.classList.toggle("visible", Boolean(offline));
}

function buildStage() {
    stage.innerHTML = "";
    for (const item of items) {
        const el = document.createElement(item.type === "video" ? "video" : "img");
        el.src = item.src;
        el.dataset.id = item.id;
        if (item.type === "video") {
            el.muted = true;
            el.playsInline = true;
            el.loop = true;
        }
        stage.appendChild(el);
    }
}

function showSlide(index) {
    const nodes = stage.querySelectorAll("img, video");
    nodes.forEach((n) => n.classList.remove("active"));
    const node = nodes[index];
    if (!node) return;
    node.classList.add("active");
    if (node.tagName === "VIDEO") {
        node.currentTime = 0;
        node.play().catch(() => {});
    }
}

function scheduleAdvance() {
    clearTimeout(advanceTimer);
    if (items.length === 0) return;
    const current = items[activeIndex];
    const duration = (current.duration || 8) * 1000;
    advanceTimer = setTimeout(() => {
        activeIndex = (activeIndex + 1) % items.length;
        showSlide(activeIndex);
        scheduleAdvance();
    }, duration);
}

async function refresh() {
    let result;
    try {
        result = await window.api.getPlaylist();
    } catch {
        return;
    }

    if (result.error === "not-paired") {
        window.api.goToPairing();
        return;
    }

    setOffline(!result.online);

    const nextItems = result.items || [];
    const nextIds = nextItems.map((i) => i.id).join(",");

    if (nextItems.length === 0) {
        items = [];
        stage.innerHTML = "";
        emptyState.style.display = "flex";
        clearTimeout(advanceTimer);
        currentIds = "";
        return;
    }

    emptyState.style.display = "none";

    if (nextIds !== currentIds) {
        items = nextItems;
        currentIds = nextIds;
        activeIndex = 0;
        buildStage();
        showSlide(activeIndex);
        scheduleAdvance();
    }
}

refresh();
setInterval(refresh, 45000);
