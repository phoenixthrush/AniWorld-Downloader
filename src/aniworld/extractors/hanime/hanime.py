# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring

import argparse
import sys
import time
import json
import re

import requests


class SearchResult:
    def __init__(self, slug, title):
        self.title = title
        self.slug = slug

    @property
    def video(self):
        return Video.from_slug(self.slug)

    def __str__(self):
        return f"<Result {self.slug}: {self.title}>"

    __repr__ = __str__


class Video:
    def __init__(self, json_enc):
        self.title = json_enc["hentai_video"]["name"]
        self.slug = json_enc["hentai_video"]["slug"]
        self.sources = {}
        metadata = {}

        for server in json_enc["videos_manifest"]["servers"]:
            for source in server["streams"]:
                if source["url"] != "":
                    name = server["name"]
                    res = source["height"]
                    self.sources[f"{name}-{res}"] = source["url"]

        metadata["brand"] = json_enc["hentai_video"]["brand"]
        metadata["likes"] = json_enc["hentai_video"]["likes"]
        metadata["dislikes"] = json_enc["hentai_video"]["dislikes"]
        metadata["views"] = json_enc["hentai_video"]["views"]
        metadata["tags"] = list(
            map(lambda i: i["text"], json_enc["hentai_video"]["hentai_tags"]))
        metadata["thumbnail"] = json_enc["hentai_video"]["poster_url"]
        metadata["cover"] = json_enc["hentai_video"]["cover_url"]
        metadata["downloads"] = json_enc["hentai_video"]["downloads"]
        metadata["monthly_rank"] = json_enc["hentai_video"]["monthly_rank"]
        metadata["description"] = re.compile(
            r'<[^>]+>').sub("", json_enc["hentai_video"]["description"])
        metadata["franchise_slug"] = json_enc["hentai_franchise"]["slug"]
        metadata["franchise_title"] = json_enc["hentai_franchise"]["title"]
        metadata["franchise_videos"] = [vid["slug"]
                                        for vid in json_enc["hentai_franchise_hentai_videos"]]
        self.metadata = type("Metadata", (), metadata)()

    @staticmethod
    def from_slug(slug):
        r = requests.get(
            f"https://hanime.tv/api/v8/video?id={slug}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36"
            },
            timeout=15
        )
        json_enc = r.json()
        return Video(json_enc)

    def at_resolution(self, res):
        max_res = int(max(self.sources, key=lambda source: int(
            source.split("-")[1])).split("-")[1])

        res = min(res, max_res)

        sources = {x: url for x, url in self.sources.items()
                   if x.endswith(str(res))}

        return sources

    def __str__(self):
        return f'<Video {self.slug}: "{self.title}">'

    __repr__ = __str__


def parse_hanime_url(url):
    if "hanime.tv" in url:
        return url.split("/hentai/")[1]

    return None


def download(video, res=1080, verbose=False, folder=False):
    true_res = list(video.at_resolution(res).keys())[0].split("-")[1]
    _ = list(video.at_resolution(res).values())[0]  # source

    if folder:
        out = f"{video.metadata.franchise_slug}/{video.slug}-{true_res}p.mp4"
    else:
        out = f"{video.slug}-{true_res}p.mp4"

    opts = {
        "outtmpl": out
    }

    if not verbose:
        opts["external_downloader_args"] = ["-loglevel", "warning", "-stats"]

    # with YoutubeDL(opts) as dl:
    #    dl.download([source])


def get_random(seed):
    j = requests.get("https://members.hanime.tv/rapi/v7/hentai_videos",
                     params={
                         "source": "randomize",
                         "r": str(seed)
                     },
                     timeout=10
                     ).json()
    results = []

    for result in j["hentai_videos"]:
        results.append(SearchResult(result["slug"], result["name"]))

    return results


# pylint: disable=too-many-arguments, too-many-positional-arguments)
def search(
    query,
    blacklist=None,
    brands=None,
    order_by="title_sortable",
    ordering="asc",
    page=0,
    tags=None,
    tags_mode="AND"
):
    if blacklist is None:
        blacklist = []
    if brands is None:
        brands = []
    if tags is None:
        tags = []

    results = []

    r = requests.post("https://search.htv-services.com/",
                      headers={
                          "User-Agent": "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36",
                          "Content-Type": "application/json;charset=UTF-8"
                      },
                      json={
                          "blacklist": blacklist,
                          "brands": brands,
                          "order_by": order_by,
                          "ordering": ordering,
                          "page": page,
                          "search_text": query,
                          "tags": tags,
                          "tags_mode": tags_mode,
                      },
                      timeout=15
                      ).json()

    j = json.loads(r["hits"])

    for result in j:
        results.append(SearchResult(result["slug"], result["name"]))

    return r["nbPages"], results


def roll_search(
    query,
    blacklist=None,
    brands=None,
    order_by="title_sortable",
    ordering="asc",
    _page=0,
    tags=None,
    tags_mode="AND"
):
    if blacklist is None:
        blacklist = []
    if brands is None:
        brands = []
    if tags is None:
        tags = []

    num_pages, results = search(
        query,
        blacklist=blacklist,
        brands=brands,
        order_by=order_by,
        ordering=ordering,
        tags=tags,
        tags_mode=tags_mode
    )

    for p in range(num_pages):
        results += search(
            query,
            blacklist=blacklist,
            brands=brands,
            order_by=order_by,
            ordering=ordering,
            page=p,
            tags=tags,
            tags_mode=tags_mode
        )[1]

    return results


SORT_OPTS_MAP = {
    "upload": "created_at_unix",
    "u": "created_at_unix",
    "views": "views",
    "v": "views",
    "likes": "likes",
    "l": "likes",
    "release": "released_at_unix",
    "r": "released_at_unix",
    "title": "title_sortable",
    "t": "title_sortable"
}

SORT_ORDER_MAP = {
    "a": "asc",
    "ascending": "asc",
    "d": "desc",
    "descending": "desc"
}


def verbose_download(video, res=1080, verbose=False, folder=False):
    print(f"Downloading {video.title}...")
    download(video, res, verbose, folder)


def output(video, args, franchise=False):
    try:
        if args.franchise and franchise:
            if not args.url:
                print(
                    f"Downloading {video.metadata.franchise_title} "
                    "franchise...\n"
                )

            for slug in video.metadata.franchise_videos:
                fran_vid = Video.from_slug(slug)
                output(fran_vid, args, franchise=False)

            return
        if args.url or args.metadata:
            if args.url:
                sources = video.at_resolution(args.resolution)

                print(f"{video.title}:")
                for i, j in sources.items():
                    server, res = tuple(i.split("-"))
                    print(f"{server}, {res}p: {j}")

                print()
            if args.metadata:
                tags_str = ", ".join(video.metadata.tags)
                print(f"URL: https://hanime.tv/videos/hentai/{video.slug}")
                print(f"Brand: {video.metadata.brand}")
                print(f"Franchise: {video.metadata.franchise_title}")
                print(f"Likes: {video.metadata.likes}")
                print(f"Dislikes: {video.metadata.dislikes}")
                print(f"Views: {video.metadata.views}")
                print(f"Downloads: {video.metadata.downloads}")
                print(f"Monthly Rank: {video.metadata.monthly_rank}")
                print(f"Tags: {tags_str}")
                print(f"Description:\n{video.metadata.description}\n")
        else:
            verbose_download(video, args.resolution, args.verbose, args.folder)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Download of {video.title} failed with error \"{e}\"")


# pylint: disable=too-many-locals, too-many-branches, too-many-statements
def hanime(url: str = None):
    if url:
        slug = parse_hanime_url(url)
        video = Video.from_slug(slug)
        if video:
            sources = video.at_resolution(1080)
            print(f"{video.title}:")
            for source_name, source_url in sources.items():
                server, res = source_name.split("-")
                print(f"{server}, {res}p: {source_url}")
            return

        print("Video not found.")
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("video", nargs="*", help="Video URL or search term")
    parser.add_argument("--tags", "-t", help="Tags to search for",
                        action="store", nargs="+", default=[])
    parser.add_argument(
        "--broad-tag-match",
        help="Match videos including any tags specified by --tags",
        action="store_const",
        const="OR",
        default="AND",
    )
    parser.add_argument("--blacklist", "-b", help="Blacklisted tags",
                        action="store", nargs="+", default=[])
    parser.add_argument("--company", "-c", help="Companies/brands to filter by",
                        action="store", nargs="+", default=[])
    parser.add_argument(
        "--page", "-p", help="Page # of search results", default=1, type=int)
    parser.add_argument(
        "--sort-by", "-s",
        help=(
            "Sorting method for search results "
            "([u]pload, [v]iews, [l]ikes, [r]elease, [t]itle)"
        ),
        default="title"
    )
    parser.add_argument(
        "--sort-order", "-w",
        help="Order of sorting ([a]scending or [d]escending)",
        default="ascending",
    )
    parser.add_argument(
        "--roll-search", "-R",
        help=(
            "Roll all search pages into one long page, "
            "useful for large-volume downloads"
        ),
        action="store_true",
        default=False
    )
    parser.add_argument(
        "--resolution", "-r",
        help="Resolution of download, default 1080",
        default=1080,
        type=int,
    )
    parser.add_argument(
        "--index", "-i",
        help="Index of search results to download",
        action="store",
        nargs="+",
        type=int,
        default=[],
    )
    parser.add_argument(
        "--all", "-a",
        help="Download all search results in page",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--folder", "-F",
        help="Create folders by franchise when downloading",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--franchise", "-f",
        help="Download the video and all other videos in its franchise",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--url", "-u",
        help="Show URLs of the source video, do not download",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--metadata", "-m",
        help="Show metadata of the source video, do not download",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--verbose", "-v",
        help="Enable verbose logging for video download",
        action="store_true",
        default=False,
    )

    args = parser.parse_args()

    slugs = list(map(parse_hanime_url, args.video))

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    if None not in slugs:
        for slug in slugs:
            video = Video.from_slug(slug)

            output(video, args, args.franchise)
    else:
        query = " ".join(args.video)

        if query == "ALL":
            query = ""

        if query == "random":
            seed = int(time.time() * 1000)
            results = get_random(seed)

            print("Random:")
            if args.index and not args.all:
                for i in args.index:
                    if i <= len(results):
                        output(results[i - 1].video, args, args.franchise)
            else:
                for result in results:
                    if args.all:
                        output(result.video, args, args.franchise)
                    else:
                        print(f"{result.title}")

            sys.exit(0)
        elif query == "new-uploads":
            num_pages, results = search(
                "", order_by="created_at_unix", ordering="desc")
        elif query == "new-releases":
            num_pages, results = search(
                "", order_by="released_at_unix", ordering="desc")
        else:
            sort_by = args.sort_by
            sort_order = args.sort_order

            if sort_by not in SORT_OPTS_MAP:
                print(f'Unknown sort method "{args.sort_by}", using sort by title')
                sort_by = "title"
            if sort_order not in SORT_ORDER_MAP:
                print(f'Unknown sort order "{args.sort_order}", using ascending order')
                sort_order = "ascending"

            search_kwargs = {
                "blacklist": args.blacklist,
                "brands": args.company,
                "tags": args.tags,
                # "page": args.page - 1,
                "tags_mode": args.broad_tag_match,
                "order_by": SORT_OPTS_MAP[sort_by],
                "ordering": SORT_ORDER_MAP[sort_order]
            }

            if args.roll_search:
                num_pages, results = 1, roll_search(query, **search_kwargs)
            else:
                num_pages, results = search(query, **search_kwargs)

        if len(results) > 1 and args.index == [] and not args.all:
            print(f'Found more than one match for "{query}"')
            print(f"Page {args.page} of {num_pages}")
            for index, result in enumerate(results):
                print(f"{index + 1}\t{result.title}")

            print(
                "\nSpecify results to download with --index/-i, "
                "or download all results shown with --all/-a"
            )

        else:
            if len(results) == 0:
                print(f'No results for "{query}"')
            elif args.index and not args.all:
                for i in args.index:
                    if i <= len(results):
                        output(results[i - 1].video, args, args.franchise)
            elif args.all or len(results) == 1:
                for result in results:
                    output(result.video, args, args.franchise)


if __name__ == "__main__":
    hanime()
