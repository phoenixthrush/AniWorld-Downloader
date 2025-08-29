use clap::Parser;
use indexmap::IndexMap;
use once_cell::sync::Lazy;
use regex::Regex;
use reqwest::blocking::Client;
use scraper::{Html, Selector};
use serde::{Deserialize, Serialize};
use std::{collections::hash_map::RandomState, error::Error, fmt, process};

type EpisodeCountsMap = IndexMap<usize, usize, RandomState>;
type EpisodeListMap = IndexMap<String, IndexMap<String, String, RandomState>, RandomState>;
type AnimeResult<T> = Result<T, AnimeError>;

#[derive(Debug)]
enum AnimeError {
    Http(reqwest::Error),
    Parse(String),
    NotFound(String),
    InvalidUrl(String),
}

impl fmt::Display for AnimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AnimeError::Http(e) => write!(f, "HTTP error: {}", e),
            AnimeError::Parse(msg) => write!(f, "Parse error: {}", msg),
            AnimeError::NotFound(msg) => write!(f, "Not found: {}", msg),
            AnimeError::InvalidUrl(msg) => write!(f, "Invalid URL: {}", msg),
        }
    }
}

impl Error for AnimeError {}

static URL_PATTERNS: Lazy<Vec<Regex>> = Lazy::new(|| {
    vec![
        Regex::new(r"^https://aniworld\.to/anime/stream/[a-z0-9\-]+$").unwrap(),
        Regex::new(r"^https://aniworld\.to/anime/stream/[a-z0-9\-]+/staffel-\d+$").unwrap(),
        Regex::new(r"^https://aniworld\.to/anime/stream/[a-z0-9\-]+/staffel-\d+/episode-\d+$")
            .unwrap(),
        Regex::new(r"^https://aniworld\.to/anime/stream/[a-z0-9\-]+/filme$").unwrap(),
        Regex::new(r"^https://aniworld\.to/anime/stream/[a-z0-9\-]+/filme/film-\d+$").unwrap(),
    ]
});

static SLUG_REGEX: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"^https://aniworld\.to/anime/stream/([a-z0-9\-]+)").unwrap());

static TITLE_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("div.series-title span").unwrap());

static MOVIE_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("a[href*='/filme'][title='Alle Filme']").unwrap());

static SEASON_META_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("meta[itemprop='numberOfSeasons']").unwrap());

static EPISODE_META_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("meta[itemprop='episodeNumber']").unwrap());

static EPISODE_ROW_SELECTOR: Lazy<Selector> = Lazy::new(|| Selector::parse("tbody tr").unwrap());

static LANGUAGE_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("div.changeLanguageBox img").unwrap());

static EPISODE_LINK_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("ul.row li[data-lang-key]").unwrap());

static HTTP_CLIENT: Lazy<Client> = Lazy::new(|| {
    Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .user_agent("Mozilla/5.0 (Android 15; Mobile; rv:132.0) Gecko/132.0 Firefox/132.0")
        .build()
        .expect("Failed to create HTTP client")
});

#[derive(Serialize, Deserialize, Debug)]
struct AnimeInfo {
    title: String,
    url: String,
    slug: String,
    season_count: usize,
    episode_counts: EpisodeCountsMap,
    has_movies: bool,
    movie_count: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    episode_list: Option<EpisodeListMap>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    languages: Vec<String>,
}

#[derive(Parser, Debug)]
#[command(
    name = "aniworld",
    version,
    about = "Command-line tool for downloading and streaming content from aniworld.to and s.to",
    long_about = "Command-line tool for downloading and streaming content from aniworld.to and s.to. Currently available for Windows, macOS and Linux, it supports LoadX, VOE, Vidmoly, Filemoon, Luluvdo, Doodstream, Vidoza, SpeedFiles and Streamtape."
)]
struct Args {
    /// One or more AniWorld URLs to process
    #[arg(value_name = "URL")]
    urls: Vec<String>,
}

fn validate_url(url: &str) -> AnimeResult<()> {
    if !url.starts_with("https://aniworld.to/") {
        return Err(AnimeError::InvalidUrl(
            "URL must be from aniworld.to".into(),
        ));
    }

    if URL_PATTERNS.iter().any(|pattern| pattern.is_match(url)) {
        Ok(())
    } else {
        Err(AnimeError::InvalidUrl(
            "URL format not supported. Supported formats:\n\
             - https://aniworld.to/anime/stream/anime-name\n\
             - https://aniworld.to/anime/stream/anime-name/staffel-N\n\
             - https://aniworld.to/anime/stream/anime-name/staffel-N/episode-N\n\
             - https://aniworld.to/anime/stream/anime-name/filme\n\
             - https://aniworld.to/anime/stream/anime-name/filme/film-N"
                .into(),
        ))
    }
}

fn extract_slug(url: &str) -> AnimeResult<String> {
    SLUG_REGEX
        .captures(url)
        .and_then(|caps| caps.get(1))
        .map(|m| m.as_str().to_string())
        .ok_or_else(|| AnimeError::Parse("Could not extract anime slug from URL".into()))
}

fn fetch_page(url: &str) -> AnimeResult<Html> {
    let response = HTTP_CLIENT.get(url).send().map_err(AnimeError::Http)?;

    if !response.status().is_success() {
        return Err(AnimeError::Http(reqwest::Error::from(
            response.error_for_status().unwrap_err(),
        )));
    }

    let html = response.text().map_err(AnimeError::Http)?;
    Ok(Html::parse_document(&html))
}

fn extract_title(document: &Html) -> AnimeResult<String> {
    document
        .select(&TITLE_SELECTOR)
        .next()
        .map(|element| element.inner_html().trim().to_string())
        .filter(|title| !title.is_empty())
        .ok_or_else(|| AnimeError::NotFound("Series title not found".into()))
}

fn has_movies(document: &Html) -> bool {
    document.select(&MOVIE_SELECTOR).next().is_some()
}

fn extract_season_count(document: &Html) -> AnimeResult<usize> {
    let movies_exist = has_movies(document);

    let season_count = document
        .select(&SEASON_META_SELECTOR)
        .next()
        .and_then(|element| element.value().attr("content"))
        .and_then(|content| content.parse::<usize>().ok())
        .ok_or_else(|| AnimeError::NotFound("Season count not found".into()))?;

    Ok(if movies_exist {
        season_count.saturating_sub(1)
    } else {
        season_count
    })
}

fn get_episode_count(anime_slug: &str, season: usize) -> AnimeResult<usize> {
    let url = format!(
        "https://aniworld.to/anime/stream/{}/staffel-{}",
        anime_slug, season
    );
    let document = fetch_page(&url)?;

    let max_episode = document
        .select(&EPISODE_META_SELECTOR)
        .filter_map(|element| element.value().attr("content"))
        .filter_map(|content| content.parse::<usize>().ok())
        .max()
        .unwrap_or(0);

    if max_episode > 0 {
        Ok(max_episode)
    } else {
        Err(AnimeError::NotFound(format!(
            "No episodes found for season {}",
            season
        )))
    }
}

fn get_movie_count(anime_slug: &str) -> AnimeResult<usize> {
    let url = format!("https://aniworld.to/anime/stream/{}/filme", anime_slug);
    let document = fetch_page(&url)?;
    Ok(document.select(&EPISODE_ROW_SELECTOR).count())
}

fn get_all_episode_counts(anime_slug: &str, season_count: usize) -> EpisodeCountsMap {
    let mut episode_counts = IndexMap::with_hasher(RandomState::new());

    for season in 1..=season_count {
        if let Ok(count) = get_episode_count(anime_slug, season) {
            episode_counts.insert(season, count);
        }
    }

    episode_counts
}

fn translate_language(german_title: &str) -> String {
    match german_title {
        "Deutsch" => "German Dub".to_string(),
        "mit Untertitel Deutsch" => "German Sub".to_string(),
        "mit Untertitel Englisch" => "English Sub".to_string(),
        _ => german_title.to_string(),
    }
}

fn extract_episode_list_and_languages(
    url: &str,
) -> AnimeResult<(Option<EpisodeListMap>, Vec<String>)> {
    if !url.contains("/episode-") {
        return Ok((None, Vec::new()));
    }

    let document = fetch_page(url)?;

    let mut languages = Vec::new();
    let mut lang_key_to_title = IndexMap::with_hasher(RandomState::new());

    for element in document.select(&LANGUAGE_SELECTOR) {
        if let Some(title) = element.value().attr("title") {
            languages.push(translate_language(title));
            if let Some(lang_key) = element.value().attr("data-lang-key") {
                lang_key_to_title.insert(lang_key.to_string(), title.to_string());
            }
        }
    }

    let mut episode_list = IndexMap::with_hasher(RandomState::new());

    for episode_link in document.select(&EPISODE_LINK_SELECTOR) {
        if let Some(h4_element) = episode_link.select(&Selector::parse("h4").unwrap()).next() {
            let hoster_name = h4_element.text().collect::<String>().trim().to_string();

            if let Some(lang_key) = episode_link.value().attr("data-lang-key") {
                if let Some(redirect_path) = episode_link.value().attr("data-link-target") {
                    let full_url = format!("https://aniworld.to{}", redirect_path);

                    if let Some(language_name) = lang_key_to_title.get(lang_key) {
                        let translated_language = translate_language(language_name);

                        let hoster_entry = episode_list
                            .entry(hoster_name)
                            .or_insert_with(|| IndexMap::with_hasher(RandomState::new()));

                        hoster_entry.insert(translated_language, full_url);
                    }
                }
            }
        }
    }

    let result = if episode_list.is_empty() {
        None
    } else {
        Some(episode_list)
    };

    Ok((result, languages))
}

fn process_anime(url: &str) -> AnimeResult<AnimeInfo> {
    validate_url(url)?;
    let slug = extract_slug(url)?;

    let main_page_url = format!("https://aniworld.to/anime/stream/{}", slug);
    let document = fetch_page(&main_page_url)?;

    let title = extract_title(&document)?;
    let season_count = extract_season_count(&document)?;
    let has_movies_flag = has_movies(&document);

    let episode_counts = get_all_episode_counts(&slug, season_count);
    let movie_count = if has_movies_flag {
        get_movie_count(&slug).unwrap_or(0)
    } else {
        0
    };

    let (episode_list, languages) =
        extract_episode_list_and_languages(url).unwrap_or((None, Vec::new()));

    Ok(AnimeInfo {
        title,
        url: url.to_string(),
        slug,
        season_count,
        episode_counts,
        has_movies: has_movies_flag,
        movie_count,
        episode_list,
        languages,
    })
}

fn main() {
    let args = Args::parse();

    if args.urls.is_empty() {
        eprintln!("Error: No URLs provided");
        eprintln!("Usage: aniworld <URL>...");
        process::exit(1);
    }

    let mut anime_results = Vec::with_capacity(args.urls.len());

    for url in &args.urls {
        match process_anime(url) {
            Ok(anime_info) => anime_results.push(anime_info),
            Err(error) => {
                eprintln!("Error processing '{}': {}", url, error);
                if anime_results.is_empty() && args.urls.len() == 1 {
                    process::exit(1);
                }
            }
        }
    }

    if anime_results.is_empty() {
        eprintln!("No anime information could be extracted from the provided URLs");
        process::exit(1);
    }

    match serde_json::to_string_pretty(&anime_results) {
        Ok(json) => println!("{}", json),
        Err(e) => {
            eprintln!("Error serializing to JSON: {}", e);
            process::exit(1);
        }
    }
}
