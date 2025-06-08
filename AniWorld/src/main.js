const { invoke } = window.__TAURI__.core;

const ANIWORLD_TO = "https://aniworld.to";

function getProvidersFromHTML(html) {
  const langMapping = {
    1: "German Dub",
    2: "English Sub",
    3: "German Sub"
  };

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  const episodeLinks = [...doc.querySelectorAll("li")].filter(li =>
    [...li.classList].some(c => c.startsWith("episodeLink"))
  );

  if (!episodeLinks.length) throw new Error("Keine Streams verfügbar");

  const providers = {};

  episodeLinks.forEach(link => {
    const provider = link.querySelector("h4")?.textContent.trim();
    const redirect = link.querySelector("a.watchEpisode")?.getAttribute("href");
    const langKey = langMapping[parseInt(link.getAttribute("data-lang-key"), 10)];

    if (provider && redirect && langKey) {
      if (!providers[provider]) providers[provider] = {};
      providers[provider][langKey] = ANIWORLD_TO + redirect;
    }
  });

  if (!Object.keys(providers).length) throw new Error("Keine gültigen Provider gefunden");

  return providers;
}

window.addEventListener("DOMContentLoaded", () => {
  const episodeInput = document.getElementById("episode");
  const providerSel = document.getElementById("provider");
  const langSel = document.getElementById("language");
  const status = document.getElementById("status");

  document.querySelector("button[type='submit']").addEventListener("click", e => {
    e.preventDefault();

    fetch(episodeInput.value.trim())
      .then(r => r.text())
      .then(html => {
        const data = getProvidersFromHTML(html);

        providerSel.textContent = "";
        Object.keys(data).forEach(p => {
          const option = document.createElement("option");
          option.textContent = p;
          providerSel.appendChild(option);
        });

        // for now default to Filemoon provider if available
        if (data["Filemoon"]) {
          providerSel.value = "Filemoon";
        } else {
          providerSel.value = providerSel.options[0]?.text || "";
        }

        providerSel.style.display = "inline-block";
        langSel.style.display = "inline-block";

        providerSel.onchange = () => {
          const langs = data[providerSel.value];
          langSel.textContent = "";
          Object.keys(langs).forEach(l => {
            const option = document.createElement("option");
            option.textContent = l;
            langSel.appendChild(option);
          });
          // for now default to German Sub provider if available
          langSel.value = langs["German Sub"] ? "German Sub" : langSel.options[0]?.text || "";
          langSel.onchange();
        };

        langSel.onchange = () => {
          const url = data[providerSel.value]?.[langSel.value] ?? "";
          fetch(url)
            .then(r => r.text())
            .then(html => {
              status.innerHTML = html;
            })
            .catch(err => {
              status.textContent = "Error loading content: " + err.message;
            });
        };

        providerSel.onchange();
      })
      .catch(err => {
        status.textContent = "Error: " + err.message;
      });
  });
});
