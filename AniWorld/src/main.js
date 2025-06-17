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

async function getAnimesFromSearch(query) {
  const searchUrl = `${ANIWORLD_TO}/ajax/seriesSearch?keyword=${encodeURIComponent(query)}`;
  const response = await fetch(searchUrl);
  if (!response.ok) throw new Error("Fehler beim Abrufen der Suchergebnisse");
  return response.json();
}

async function get_direct_link(embed_link, provider = "vidmoly") {
  const USER_AGENT = "Mozilla/5.0 (Android 15; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0";

  const response = await fetch(embed_link, {
    headers: {
      "User-Agent": USER_AGENT,
      "Referer": get_referer(provider)
    }
  });

  if (!response.ok) throw new Error(`Failed to fetch ${provider} page`);

  const html = await response.text();

  const parser = parsers[provider];
  if (!parser) throw new Error(`No parser implemented for provider: ${provider}`);

  return parser(html);
}

function get_referer(provider) {
  const referers = {
    vidmoly: "https://vidmoly.to",
    example: "https://example.com"
  };
  return referers[provider] || "";
}

const parsers = {
  vidmoly: html => {
    const file_link_pattern = /file:\s*"((https?:\/\/)[^"]+)"/;
    const scripts = Array.from(html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)).map(m => m[1]);

    for (const script of scripts) {
      const match = file_link_pattern.exec(script);
      if (match) return match[1];
    }

    throw new Error("No direct link found in vidmoly response.");
  },

  example: html => {
    // Placeholder for future providers
    throw new Error("Example parser not implemented.");
  }
};

window.addEventListener("DOMContentLoaded", () => {
  const episodeInput = document.getElementById("episode");
  const providerSel = document.getElementById("provider");
  const langSel = document.getElementById("language");
  const status = document.getElementById("status");
  const queryInput = document.getElementById("query");
  const animeSelect = document.getElementById("anime");

  const copyBtn = document.getElementById("copy");
  copyBtn.addEventListener("click", () => {
    if (status.textContent) {
      navigator.clipboard.writeText(status.textContent);
    }
  });

  queryInput.addEventListener("input", () => {
    getAnimesFromSearch(queryInput.value)
      .then(animes => {
        animeSelect.textContent = "";
        if (animes.length > 0) {
          animes.forEach(anime => {
            const option = document.createElement("option");
            option.value = anime.link ? `${ANIWORLD_TO}/anime/stream/${anime.link}/staffel-1/episode-1` : "";
            option.textContent = anime.title || anime.link || "";
            animeSelect.appendChild(option);
          });
          episodeInput.value = animes[0].link ? `${ANIWORLD_TO}/anime/stream/${animes[0].link}/staffel-1/episode-1` : "";
          episodeInput.style.display = "inline-block";  // will be replaced by selection
        } else {
          episodeInput.value = "";
          episodeInput.style.display = "none";
        }
      })
      .catch(() => {
        animeSelect.textContent = "";
        episodeInput.value = "";
        episodeInput.style.display = "none";
      });
  });

  animeSelect.addEventListener("change", () => {
    episodeInput.value = animeSelect.value;
  });

  document.querySelector("button[type='submit']").addEventListener("click", e => {
    e.preventDefault();

    fetch(episodeInput.value.trim())
      .then(r => r.text())
      .then(html => {
        const data = getProvidersFromHTML(html);

        providerSel.style.display = "inline-block";
        langSel.style.display = "inline-block";

        providerSel.innerHTML = "";
        Object.keys(data).forEach(p => {
          const option = document.createElement("option");
          option.textContent = p;
          providerSel.appendChild(option);
        });

        // for now default to Vidmoly provider if available
        if (data["Vidmoly"]) {
          providerSel.value = "Vidmoly";
        } else {
          providerSel.value = providerSel.options[0]?.text || "";
        }

        providerSel.onchange = () => {
          const langs = data[providerSel.value];
          langSel.innerHTML = "";
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
          /*
          fetch(url)
            .then(r => r.text())
            .then(html => {
              status.innerHTML = html;
            })
            .catch(err => {
              status.textContent = "Error loading content: " + err.message;
            });
            */
          get_direct_link(url).then(result => {
            status.textContent = `yt-dlp --add-header "Referer: https://vidmoly.to"\n${result}`;
            copyBtn.style.display = "block";
          }).catch(err => {
            status.textContent = `Error: ${err.message}`;
          });
        };

        providerSel.onchange();
      })
      .catch(err => {
        status.textContent = "Error: " + err.message;
      });
  });
});
