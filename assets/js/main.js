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
    const proxyUrl = "https://api.codetabs.com/v1/proxy/?quest=" + encodeURIComponent(url);

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
            output.textContent = "Failed to fetch content, even with direct request.";
            return null;
        });
    }

    // if we have HTML content, extract the necessary data
    if (html) {
        extractData(html, url, output);
    }
});

// extract necessary data from the HTML content
function extractData(html, url, outputElement) {
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
    const providerLinks = formatProviderLinks(episodeLinks);

    // display the extracted details on the page
    outputElement.textContent = `
Fetching details of ${url}...\n
Title:          ${title}
Slug:           ${slug}
Description:    ${description_shortened}
Season:         ${season}
Episode:        ${episode}
Ger. Title:     ${germanTitle}
Eng. Title:     ${englishTitle}
\nProcessing available languages...
Avl. Languages: ${languages}
\nProcessing provider links...
${providerLinks}`;
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
        const languageMap = {
            1: "German Dub",
            2: "English Sub",
            3: "German Sub"
        };
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
    const keyMapping = {
        1: "German Dub",
        2: "English Sub",
        3: "German Sub"
    };
    const allLinks = [...doc.querySelectorAll('li')].filter(linkElement =>
        /episodeLink\d+/.test(linkElement.className)
    );

    allLinks.forEach((linkElement) => {
        const hosterName = linkElement.querySelector('i')?.title?.split(' ')[1] || 'Unknown Host';
        const episodeLink = linkElement.querySelector('a')?.getAttribute('href') || 'No link';
        const langKey = linkElement.getAttribute('data-lang-key');
        const language = keyMapping[langKey] || 'Unknown Language';

        if (!episodeLinks[hosterName]) {
            episodeLinks[hosterName] = {};
        }
        episodeLinks[hosterName][language] = `https://aniworld.to${episodeLink}`;
    });

    return episodeLinks;
}

// format provider links for display
function formatProviderLinks(episodeLinks) {
    const maxLangLength = Math.max(...Object.values(episodeLinks).flatMap(links => Object.keys(links).map(lang => lang.length)));

    return Object.entries(episodeLinks)
        .map(([hoster, links]) => {
            const linkUrls = Object.entries(links)
                .map(([lang, link]) => {
                    // add padding after the colon
                    const paddedLang = lang + ":";
                    const spaceAfterColon = " ".repeat(maxLangLength - lang.length + 1);
                    return `${paddedLang}${spaceAfterColon}${link}`;
                })
                .join(' \n');
            return `${hoster}\n${linkUrls}\n\n`;
        })
        .join('');
}