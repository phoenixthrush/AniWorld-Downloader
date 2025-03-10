const proxy = ""
const proxy_redirect = "https://nuss.tmaster055.com/fetch-url?link="
const proxy_html = "https://nuss.tmaster055.com/fetch-html?link="

const SPEEDFILES_PATTERN = /var _0x5opu234 = "(.*?)";/;

const languageMap = {
    1: "German Dub",
    2: "English Sub",
    3: "German Sub"
};

// event listener for when the fetch button is clicked
document.getElementById("fetchButton").addEventListener("click", async () => {
    const url = document.getElementById("urlInput").value;
    const output = document.getElementById("output");

    console.log("Fetch button clicked.");
    console.log("Input URL:", url);

    if (!url.startsWith("https://")) {
        output.textContent = "Invalid URL!";
        console.log("Invalid URL detected.");
        return;
    }

    console.log("URL is valid. Attempting to fetch...");

    let html;

    try {
        console.log("Trying proxy:", proxy + url);
        const proxyResponse = await fetch(proxy + url);
        console.log("Proxy response status:", proxyResponse.status);

        if (proxyResponse.ok) {
            html = await proxyResponse.text();
            console.log("Successfully fetched HTML via proxy.");
            console.log("First 50 characters of HTML:", html.substring(0, 50));
        } else {
            throw new Error("Proxy failed");
        }
    } catch (proxyError) {
        console.warn("Proxy failed, attempting direct fetch...", proxyError);

        try {
            const response = await fetch(url);
            console.log("Direct fetch response status:", response.status);
            html = await response.text();
            console.log("Successfully fetched HTML directly.");
            console.log("HTML:\n", html.substring(0, 200) + "...");
        } catch (error) {
            console.error("Both proxy and direct fetch failed:", error);
            output.textContent = "Failed to fetch content, even with CORS proxy.\nPlease try again later.";
            return;
        }
    }

    if (html) {
        await extractData(html, url, output);
        console.log("Data extraction completed.");
    } else {
        console.error("No HTML content retrieved.");
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

// this does absolutely not work
async function getDirectLinkFromSpeedFiles(html) {
    const match = html.match(SPEEDFILES_PATTERN);
    if (!match) {
        throw new Error("Pattern not found in the response.");
    }

    let encodedData = match[1];
    let decoded = atob(encodedData);
    decoded = decoded.split('').reverse().join('').toUpperCase();
    decoded = atob(decoded);
    decoded = decoded.split('').reverse().join('');

    let decodedHex = decoded.match(/.{1,2}/g).map(hex => String.fromCharCode(parseInt(hex, 16))).join('');

    let shifted = decodedHex.split('').map(char => String.fromCharCode(char.charCodeAt(0) - 3)).join('');

    return atob(shifted.split('').reverse().join('')).toLowerCase();
}

// extract necessary data from the HTML content
async function extractData(html, url, outputElement) {
    console.log("Extracting data from HTML...");
    const doc = new DOMParser().parseFromString(html, "text/html");

    const title = getTitle(doc);
    console.log("Title:", title);
    outputElement.textContent += `Title:\t\t${title}\n`;

    const slug = getSlug(url);
    console.log("Slug:", slug);
    outputElement.textContent += `Slug:\t\t${slug}\n`;

    const { episode, season } = getEpisodeAndSeason(doc);
    console.log("Season:", season, ",", "Episode:", episode);
    outputElement.textContent += `Season:\t\t${season}\nEpisode:\t${episode}\n`;

    const description = getDescription(doc);
    console.log("Full Description:", description);
    // outputElement.textContent += `Full Description: ${description}\n`;

    const germanTitle = getGermanTitle(doc);
    console.log("German Title:", germanTitle);
    outputElement.textContent += `German Title:\t${germanTitle}\n`;

    const englishTitle = getEnglishTitle(doc);
    console.log("English Title:", englishTitle);
    outputElement.textContent += `English Title:\t${englishTitle}\n`;

    const languages = getAvailableLanguages(doc);
    console.log("Available Languages:", languages);
    outputElement.textContent += `Avl. Languages:\t${languages}\n`;

    const description_shortened = shortenDescription(description);
    console.log("Shortened Description:", description_shortened);
    outputElement.textContent += `Description:\t${description_shortened}\n`;

    const episodeLinks = getEpisodeLinks(doc);
    console.log("Episode Links:", episodeLinks);
    // outputElement.textContent += `Episode Links: ${JSON.stringify(episodeLinks)}\n`;

    const providerLinks = await formatProviderLinks(episodeLinks);
    console.log("Formatted Provider Links:", providerLinks);
    outputElement.textContent += `\nProvider Links:\n${providerLinks}\n`;

    const filteredEpisodeLinks = filterEpisodeLinks(episodeLinks);
    console.log("Supported Episode Links:", filteredEpisodeLinks);
    outputElement.textContent += `Supported Episode Links:\n${JSON.stringify(filteredEpisodeLinks, null, 4)}\n\n`;

    const selected_language = languageMap[document.getElementById("selected_language").value];
    const selected_provider = document.getElementById("selected_provider").value;
    const redirect_link = episodeLinks[selected_provider]?.[selected_language];

    console.log("Selected Language:", selected_language);
    outputElement.textContent += `Selected Language:\t${selected_language}\n`;

    console.log("Selected Provider:", selected_provider);
    outputElement.textContent += `Selected Provider:\t${selected_provider}\n\n`;

    console.log("Selected Redirect Link:", redirect_link);
    outputElement.textContent += `Selected Redirect:\t${redirect_link}\n`;

    if (!redirect_link) {
        alert('Selected language or provider is not available.');
        return 1;
    }

    fetch(proxy_redirect + redirect_link)
        .then(response => response.text())
        .then(async data => {
            const embedded_url = data;
            console.log("Embedded Link:", embedded_url);
            outputElement.textContent += `Embedded Link:\t\t${embedded_url}\n`;

            let embedded_url_html = '';  // Declare it here to make it accessible in all the provider logic

            try {
                console.log("Fetching Link:", embedded_url);
                const response = await fetch(proxy_html + embedded_url);
                console.log(`Response status: ${response.status}`);
                embedded_url_html = await response.text();
                console.log("HTML:\n" + embedded_url_html.substring(0, 200) + "...");
            } catch (error) {
                console.error("Error fetching embedded URL:", error);
                outputElement.textContent += "Failed to fetch the embedded URL.\n";
                return;  // Return early if fetching the embedded URL fails
            }

            if (selected_provider === 'Vidoza') {
                console.log("Processing Vidoza Provider...");
                outputElement.textContent += `\nProcessing Vidoza Provider...\n`;
                const scripts = new DOMParser().parseFromString(embedded_url_html, 'text/html').querySelectorAll('script');
                let found = false;

                for (let script of scripts) {
                    if (script.textContent.includes('sourcesCode:')) {
                        const match = script.textContent.match(/src: "(.*?)"/);
                        if (match) {
                            console.log("Vidoza Video Source:", match[1]);
                            outputElement.textContent += `Vidoza Video Source:\t${match[1]}\n`;
                            // alert(match[1]);
                            found = true;
                            break;
                        }
                    }
                }

                if (!found) {
                    console.log("Video source not found.");
                    alert("Video source not found :(");
                }
            } else if (selected_provider === 'SpeedFiles') {
                console.log("Processing SpeedFiles provider...");
                outputElement.textContent += `Processing SpeedFiles provider...\n`;
                alert("Sorry SpeedFiles is currently not implemented");
                return;

                const scripts = new DOMParser().parseFromString(embedded_url_html, 'text/html').querySelectorAll('script');
                for (let script of scripts) {
                    if (script.textContent.includes('sourcesCode:')) {
                        console.log("Found script:", script);
                        outputElement.textContent += `Found script: ${script.textContent}\n`;
                        const match = script.textContent.match(/src: "(.*?)"/);
                        if (match) {
                            console.log("SpeedFiles Match:", match);
                            try {
                                const result = await getDirectLinkFromSpeedFiles(match[1]);
                                console.log("Decoded SpeedFiles Link:", result);
                                alert(result);
                            } catch (error) {
                                console.error("Error decoding SpeedFiles link:", error);
                                outputElement.textContent += `Error decoding SpeedFiles link: ${error}\n`;
                            }
                        }
                    }
                }
            }
        })
        .catch(error => {
            console.error("Error fetching the redirect link:", error);
            outputElement.textContent += "Failed to fetch the redirect link.\n";
        });
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
    if (descriptionWords.length > 10) {
        return descriptionWords.slice(0, 10).join(' ') + ' [...]';
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
        console.log(`Fetching URL: ${url}`);

        const response = await fetch(proxy + url, {
            method: 'GET',
            headers: {
                'Referer': "https://vidoza.net",
                'User-Agent': navigator.userAgent,
                'Accept': '*/*',
                'Origin': "https://aniworld.to"
            },
            redirect: 'manual'
        });

        console.log(`Response status: ${response.status}`);

        if (response.status === 301 || response.status === 302) {
            const newUrl = response.headers.get('Location');
            console.log(`Redirected to: ${newUrl}`);
            if (newUrl) return newUrl;
        }

        console.log(`Final URL: ${response.url}`);
        return response.url;
    } catch (error) {
        console.error('Fetch Error:', error);
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
                    // const finalUrl = await getFinalUrl(link);
                    // return `${paddedLang}${spaceAfterColon}${link} -> ${finalUrl}`;
                    return `${paddedLang}${spaceAfterColon}${link}`;
                })
            );
            return `${hoster}\n${linkUrls.join(' \n')}\n\n`;
        })
    );
    return result.join('');
}

const outputElement = document.getElementById('output');
const observer = new MutationObserver(() => {
    outputElement.scrollTop = outputElement.scrollHeight;
});

observer.observe(outputElement, { childList: true, subtree: true });