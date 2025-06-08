const { invoke } = window.__TAURI__.core;

let greetInputEl;
let greetMsgEl;

async function greet() {
  // Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
  greetMsgEl.textContent = await invoke("greet", { name: greetInputEl.value });
}

window.addEventListener("DOMContentLoaded", () => {
  greetInputEl = document.querySelector("#greet-input");
  greetMsgEl = document.querySelector("#greet-msg");
  document.querySelector("#greet-form").addEventListener("submit", (e) => {
    e.preventDefault();

    fetch("https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-1/episode-1")
      .then(r => r.text())
      .then(t => document.getElementById('fetch-content').innerText = t)
      .catch(e => document.getElementById('fetch-content').innerText = "Error: " + e);

    greet();
  });
});
