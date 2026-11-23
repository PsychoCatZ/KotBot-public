"use strict";
const byId = id => document.getElementById(id);
const status = byId("status");
let state;
let pending = false;
let requestNumber = 0;
let inFlight = 0;
let firstRender = true;

function renderLines(container, lines) {
  container.replaceChildren();
  for (const line of lines) {
    const row = document.createElement("p");
    const speaker = document.createElement("strong");
    speaker.textContent = line.speaker + " — ";
    row.append(speaker, document.createTextNode(line.text));
    container.append(row);
  }
}

function render() {
  const log = byId("room-log");
  const previousTop = log.scrollTop;
  const follow = firstRender || log.scrollHeight - log.clientHeight - previousTop < 48;
  byId("automation").disabled = false;
  byId("automation").textContent = state.auto_paused ? "Возобновить автоматику" : "Пауза автоматики";
  byId("room").disabled = pending || state.active;
  byId("repair-archive").hidden = !state.archive.repair;
  renderLines(byId("repair-past"), state.archive.repair || []);
  byId("broken-archive").hidden = !state.archive.broken_box;
  renderLines(byId("broken-past"), state.archive.broken_box || []);
  byId("box-archive").hidden = !state.archive.box;
  renderLines(byId("box-past"), state.archive.box || []);
  byId("next").disabled = pending || !state.active || state.auto_running;
  byId("stop").disabled = !state.active;
  byId("send").disabled = false;
  const past = state.archive.meeting;
  byId("archive").hidden = !past;
  renderLines(byId("past"), past || []);
  renderLines(byId("dialogue"), state.dialogue);
  log.scrollTop = follow ? log.scrollHeight : previousTop;
  firstRender = false;
  status.textContent = pending ? "Ход персонажа…" : state.active
    ? "Разговор в квартире"
    : "В квартире тихо.";
}

async function action(path = "", body) {
  const id = ++requestNumber;
  inFlight++;
  try {
    const response = await fetch("/api/apartment" + path, path ? {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: body ? JSON.stringify(body) : undefined
    } : {});
    if (response.status === 401) throw new Error("Войди через основной чат Катера.");
    if (!response.ok) {
      const data = await response.json();
      throw new Error(typeof data.detail === "string" ? data.detail : "Запрос не выполнен.");
    }
    const updated = await response.json();
    if (id === requestNumber) {
      state = updated;
      render();
    }
    return true;
  } catch (error) {
    if (id === requestNumber) status.textContent = error.message;
    return false;
  } finally {
    inFlight--;
  }
}

byId("room").onclick = async () => {
  if (pending) return;
  pending = true;
  render();
  if (await action("/start/room")) {
    for (let i = 0; i < 6 && state.active; i++) {
      if (!await action("/turn")) break;
    }
  }
  pending = false;
  if (state) {
    const message = status.textContent;
    render();
    if (message && message !== "Ход персонажа…") status.textContent = message;
  }
};
byId("automation").onclick = () => action("/automation/" + (state.auto_paused ? "resume" : "pause"));
byId("stop").onclick = () => action("/stop");
byId("next").onclick = async () => {
  if (pending) return;
  pending = true;
  render();
  const ok = await action("/turn");
  pending = false;
  const message = status.textContent;
  render();
  if (!ok) status.textContent = message;
};
byId("intervene").onsubmit = async (event) => {
  event.preventDefault();
  const input = byId("message");
  const draft = input.value;
  if (await action("/say", {text: draft}) && input.value === draft) input.value = "";
};
for (const id of ["room", "next", "stop", "send"]) byId(id).disabled = true;
action();

setInterval(() => { if (!pending && !inFlight && !document.hidden) action(); }, 15000);
