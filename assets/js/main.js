const proxy = "https://api.codetabs.com/v1/proxy/?quest="

const languageMap = {
    1: "German Dub",
    2: "English Sub",
    3: "German Sub"
};

// event listener for when the fetch button is clicked
document.getElementById("fetchButton").addEventListener("click", async () => {
    const url = document.getElementById("urlInput").value;
    const output = document.getElementById("output");

    // check if the URL is valid
    if (!url.startsWith("https://")) {
        output.textContent = "Invalid URL!";
        return;
    }

    // construct proxy URL to fetch content
    const proxyUrl = proxy + encodeURIComponent(url);

    let html;

    // attempt to fetch content through proxy or directly
    try {
        const proxyResponse = await fetch(proxyUrl);
        if (proxyResponse.ok) {
            html = await proxyResponse.text();
        } else {
            throw new Error("Proxy failed");
        }
    } catch (proxyError) {
        html = await fetch(url).then(response => response.text()).catch(error => {
            output.textContent = "Failed to fetch content, even with cors proxy.\nPlease try again later.";
            return null;
        });
    }

    // if we have HTML content, extract the necessary data
    if (html) {
        await extractData(html, url, output);
    }
});

function filterEpisodeLinks(episodeLinks) {
    const allowedHosts = ["Vidoza", "Speedfiles"];
    const filteredLinks = {};

    Object.entries(episodeLinks).forEach(([hoster, languages]) => {
        if (allowedHosts.includes(hoster)) {
            filteredLinks[hoster] = languages;
        }
    });

    return filteredLinks;
}

// extract necessary data from the HTML content
async function extractData(html, url, outputElement) {
    const doc = new DOMParser().parseFromString(html, "text/html");

    const title = getTitle(doc);
    const slug = getSlug(url);
    const description = getDescription(doc);
    const germanTitle = getGermanTitle(doc);
    const englishTitle = getEnglishTitle(doc);
    const description_shortened = shortenDescription(description);
    const { episode, season } = getEpisodeAndSeason(doc);
    const languages = getAvailableLanguages(doc);
    const episodeLinks = getEpisodeLinks(doc);
    const providerLinks = await formatProviderLinks(episodeLinks);
    const filteredEpisodeLinks = filterEpisodeLinks(episodeLinks)

    // console.log(JSON.stringify(filteredEpisodeLinks, null, 2));

    const selected_language = languageMap[document.getElementById("selected_language").value];
    const selected_provider = document.getElementById("selected_provider").value;

    const embedded_link_redirect = episodeLinks[selected_provider]?.[selected_language];
    if (!embedded_link_redirect) {
        alert('Selected language or provider is not available.');
    }

    const embedded_url = await getFinalUrl(embedded_link_redirect);

    // TODO: current proxy does not allow this domain
    const embedded_url_html = await fetch(proxy + encodeURIComponent(embedded_url)).text();

    if (selected_provider === 'vidoza') {
        const scripts = new DOMParser().parseFromString(embedded_url_html, 'text/html').querySelectorAll('script');
        for (let script of scripts) {
            if (script.textContent.includes('sourcesCode:')) {
                const match = script.textContent.match(/src: "(.*?)"/);
                if (match) {
                    alert(match[1]);
                }
            }
        }
    } else if (selected_provider === 'SpeedFiles') {
        alert("Sorry SpeedFiles is not implemented yet")
    }

    // display the extracted details on the page
    outputElement.textContent = `
Fetching details of ${url}...
\nTitle:          ${title}
Slug:           ${slug}
Description:    ${description_shortened}
Season:         ${season}
Episode:        ${episode}
Ger. Title:     ${germanTitle}
Eng. Title:     ${englishTitle}
\nProcessing available languages...
Avl. Languages: ${languages}
\nProcessing provider links...
${providerLinks}
Selected Provider: ${selected_provider}
Selected Language: ${selected_language}
\nEmbedded Link:   ${embedded_url}
`;
}

// get the title from the HTML document
function getTitle(doc) {
    return doc.querySelector(".series-title h1 span")?.textContent || "Title not found";
}

// extract the slug from the URL
function getSlug(url) {
    const slugMatch = url.match(/\/anime\/stream\/([^/]+)/);
    return slugMatch ? slugMatch[1] : "Slug not found";
}

// get the description from the HTML document
function getDescription(doc) {
    return doc.querySelector(".seri_des")?.getAttribute("data-full-description") || "Description not found";
}

// get the German title from the HTML document
function getGermanTitle(doc) {
    return doc.querySelector(".episodeGermanTitle")?.textContent || "German title not found";
}

// get the English title from the HTML document
function getEnglishTitle(doc) {
    return doc.querySelector(".episodeEnglishTitle")?.textContent || "English title not found";
}

// shorten the description if it's too long
function shortenDescription(description) {
    const descriptionWords = description.split(' ');
    if (descriptionWords.length > 15) {
        return descriptionWords.slice(0, 15).join(' ') + ' [...]';
    }
    return description;
}

// extract episode number and season from the HTML document
function getEpisodeAndSeason(doc) {
    const currentElement = doc.querySelector(".currentActiveLink a");
    const episode = currentElement?.querySelector("span[itemprop='name']")?.textContent.trim().match(/\d+/)?.[0] || "Not found";
    const seasonMatch = currentElement?.href.match(/staffel-(\d+)/);
    const season = seasonMatch ? seasonMatch[1] : "Not found";
    return { episode, season };
}

// get the available languages from the HTML document
function getAvailableLanguages(doc) {
    const languageBox = doc.querySelector(".changeLanguageBox");
    let languages = "Not found";
    if (languageBox) {
        const langKeys = [...languageBox.querySelectorAll("img[data-lang-key]")]
            .map(img => img.getAttribute("data-lang-key"))
            .filter(lang => lang && !isNaN(lang))
            .map(lang => languageMap[lang] || `Unknown (${lang})`);
        if (langKeys.length) {
            languages = langKeys.join(", ");
        }
    }
    return languages;
}

// get episode links for all available hosts
function getEpisodeLinks(doc) {
    const episodeLinks = {};
    const allLinks = [...doc.querySelectorAll('li')].filter(linkElement =>
        /episodeLink\d+/.test(linkElement.className)
    );

    allLinks.forEach((linkElement) => {
        const hosterName = linkElement.querySelector('i')?.title?.split(' ')[1] || 'Unknown Host';
        const episodeLink = linkElement.querySelector('a')?.getAttribute('href') || 'No link';
        const langKey = linkElement.getAttribute('data-lang-key');
        const language = languageMap[langKey] || 'Unknown Language';

        if (!episodeLinks[hosterName]) {
            episodeLinks[hosterName] = {};
        }
        episodeLinks[hosterName][language] = `https://aniworld.to${episodeLink}`;
    });

    return episodeLinks;
}

// TODO: broken, someone please fix this
async function getFinalUrl(url) {
    try {
        const con_url = "https://nuss.tmaster055.com/fetch-url?link=" + encodeURIComponent(url)
        const response = await fetch(con_url, {
            method: 'GET',
            redirect: 'follow'
        });

        if (!response.ok) {
            throw new Error('Network response was not ok: ' + response.statusText);
        }

        const content = await response.text();
        return content;
    } catch (error) {
        console.error('Error fetching final URL:', error);
        throw error;
    }
}

// display provider links padded
async function formatProviderLinks(episodeLinks) {
    const maxLangLength = Math.max(...Object.values(episodeLinks).flatMap(links => Object.keys(links).map(lang => lang.length)));

    const result = await Promise.all(Object.entries(episodeLinks)
        .map(async ([hoster, links]) => {
            const linkUrls = await Promise.all(Object.entries(links)
                .map(async ([lang, link]) => {
                    const paddedLang = lang + ":";
                    const spaceAfterColon = " ".repeat(maxLangLength - lang.length + 1);
                    const finalUrl = await getFinalUrl(link);
                    return `${paddedLang}${spaceAfterColon}${link} -> ${finalUrl}`;
                })
            );
            return `${hoster}\n${linkUrls.join(' \n')}\n\n`;
        })
    );
    return result.join('');
}
