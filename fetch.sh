#!/usr/bin/env bash

domain=""
curl_output=""

error_exit() {
    echo "Error: $1" >&2
    exit 1
}

check_arguments() {
    [[ $# -eq 0 ]] && error_exit "No argument provided. Please provide a link."
}

check_spam() {
    local link="$1"
    if ! curl_output=$(curl -sL "$link"); then
        error_exit "Failed to fetch URL: $link"
    fi
    if echo "$curl_output" | grep -q 'Deine Anfrage wurde als Spam erkannt. Gleich geht'\''s weiter...'; then
        error_exit "Your IP-Address is blacklisted, please use a VPN or try later."
    fi
}

download_youtube_dl() {
    mkdir -p yt_dlp || error_exit "Failed to create directory: yt_dlp"
    cd yt_dlp || error_exit "Failed to change directory to: yt_dlp"

    if ! curl -sLO https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp ||
       ! curl -sLO https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-512SUMS; then
        error_exit "Failed to download yt-dlp binary."
    fi

    yt_dlp_hash=$(grep yt-dlp SHA2-512SUMS | head -n 1 | awk '{print $1}')
    local_hash=$(shasum -a 512 yt-dlp | cut -d ' ' -f 1)

    if [ "$local_hash" != "$yt_dlp_hash" ]; then
        error_exit "The yt-dlp file may have been tampered with!"
    fi

    chmod +x yt-dlp || error_exit "Failed to make yt-dlp executable."
    cd - >/dev/null || error_exit "Failed to change directory back."
}

get_title() {
    local link="$1"
    curl -sL "$link" | grep 'title' | grep -o '<span>[^<]*</span>' | sed 's/<[^>]*>//g' | head -n 1 | tr ' ' '\ '
}

create_and_change_directory() {
    local directory="$1"
    mkdir -p "$directory" || error_exit "Failed to create directory: $directory"
    cd "$directory" || error_exit "Failed to change directory to: $directory"
}

get_download_link() {
    local episode="$1"
    local link
    local episode_filename
    if [[ "$domain" == "s.to" ]]; then
        link=$(curl https://s.to/redirect/"$episode" -sL | grep -o '\<https\?://voe\.sx/[^"]*')
        link=$(curl -sL "$link" | grep m3u8 | grep -oE 'https?://\S+' | head -n 1 | rev | cut -c 3- | rev)
        episode_filename=$(curl https://s.to/redirect/"$episode" -sL | grep '<div class="plyr-player-title">' | sed 's/<[^>]*>//g')
    elif [[ "$domain" == "aniworld.to" ]]; then
        link=$(curl -sL https://aniworld.to/redirect/"$episode" | grep m3u8 | grep -oE 'https?://\S+' | head -n 1 | rev | cut -c 3- | rev)
        episode_filename=$(curl -sL https://aniworld.to/redirect/2446186 | grep -o '<meta name="og:title" content="[^"]*"' | sed 's/content="//;s/"$//' | awk '{print $3}')
    else
        error_exit "Invalid domain."
    fi
    echo "$link" "$episode_filename"
}

main() {
    local link=""
    local watch_selected=false
    local download_selected=false

    for arg in "$@"; do
        case "$arg" in
            --watch)
                if [[ "$download_selected" == true ]]; then
                    error_exit "Invalid combination of arguments: --watch and --download cannot be used together."
                fi
                watch_selected=true
                ;;
            --download)
                if [[ "$watch_selected" == true ]]; then
                    error_exit "Invalid combination of arguments: --watch and --download cannot be used together."
                fi
                download_selected=true
                ;;
            http*://*)
                link="$arg"
                ;;
            *)
                error_exit "Invalid argument: $arg. Please use --download or --watch."
                ;;
        esac
    done

    if [[ "$watch_selected" == true && "$download_selected" == true ]]; then
        error_exit "Invalid combination of arguments: --watch and --download cannot be used together."
    fi

    if [[ "$watch_selected" == false && "$download_selected" == false ]]; then
        download_selected=true
    fi

    if [[ -z "$link" ]]; then
        error_exit "No link provided. Please provide a valid link."
    fi

    if [[ "$link" =~ ^(https?://)?s\.to/.*$ ]]; then
        domain="s.to"
    elif [[ "$link" =~ ^(https?://)?aniworld\.to/.*$ ]]; then
        domain="aniworld.to"
    else
        error_exit "Invalid link. Please provide a valid link from s.to or aniworld.to domain."
    fi

    if [[ "$watch_selected" == true ]]; then
        watch "$link"
    elif [[ "$download_selected" == true ]]; then
        download "$link"
    fi
}

download() {
    local link="$1"
    check_arguments "$link"
    download_youtube_dl
    check_spam "$link"
    local title=$(get_title "$link")
    create_and_change_directory "Downloads/$title"
    local episode=$(curl -sL "$link" | grep -o 'episodeLink[0-9]*' | awk -F'episodeLink' '{print $2}' | head -n 1)
    local download_info=$(get_download_link "$episode")
    local download_link=$(echo "$download_info" | cut -d ' ' -f 1)
    local episode_filename=$(echo "$download_info" | cut -d ' ' -f 2)
    ../../yt_dlp/yt-dlp -q --progress "$download_link" --no-warnings -o "$episode_filename"
}

watch() {
    local link="$1"
    check_arguments "$link"
    check_spam "$link"
    local title=$(get_title "$link")
    local episode=$(curl -sL "$link" | grep -o 'episodeLink[0-9]*' | awk -F'episodeLink' '{print $2}' | head -n 1)
    local download_info=$(get_download_link "$episode")
    local download_link=$(echo "$download_info" | cut -d ' ' -f 1)
    local episode_filename=$(echo "$download_info" | cut -d ' ' -f 2)
    mpv "$download_link" --quiet --really-quiet
}

main "$@"
