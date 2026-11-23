"use strict";
const byId = id => document.getElementById(id);
const input = byId("message");
const send = byId("send");
const status = byId("status");
const endpoint = "/api/apartment/ilse";

function add(role, text) {
  const row = document.createElement("p");
  const speaker = document.createElement("strong");
  speaker.textContent = role === "user" ? "Кот — " : "Ильза — ";
  row.append(speaker, document.createTextNode(text));
  byId("dialogue").append(row);
}

async function request(options) {
  const response = await fetch(endpoint, options);
  if (response.status === 401) throw new Error("Войди через основной чат Катера.");
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Запрос не выполнен.");
  return data;
}

byId("chat").onsubmit = async event => {
  event.preventDefault();
  if (send.disabled || !input.value.trim()) return;
  const text = input.value.trim();
  send.disabled = true;
  status.textContent = "Ильза отвечает…";
  try {
    const data = await request({
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text})
    });
    add("user", text);
    add("assistant", data.answer);
    if (input.value.trim() === text) input.value = "";
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    send.disabled = false;
  }
};

request().then(data => {
  data.messages.forEach(message => add(message.role, message.content));
  input.disabled = false;
  send.disabled = false;
}).catch(error => { status.textContent = error.message; });
