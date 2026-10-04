# Sources

## Keyless (no login, on by default)

| Source | What it covers | Notes |
|--------|----------------|-------|
| `bluesky` | AT Protocol posts | cursor-paged |
| `hackernews` | HN stories and comments | Algolia index |
| `github` | repos, issues, pull requests | optional `GITHUB_TOKEN` lifts the rate limit |
| `arxiv` | preprints | multi-word queries are phrase-matched |
| `polymarket` | prediction markets | what people are betting on |
| `stocktwits` | cashtag streams | the query is read as a ticker |
| `mastodon` | public hashtag timelines | federation-limited |
| `habr` | Russian-language IT community | search RSS |
| `v2ex` | Chinese developer community | full-text via sov2ex |
| `telegram` | public channels | needs a channel list; recent history only |
| `sogou_wechat` | WeChat public-account articles | single page, snippet-level |
| `gdelt` | worldwide news in 65 languages | 250 articles per call, bisected by date; one request per 5 seconds per IP |
| `marginalia` | independent index of the small, non-commercial web | undated; in the default sweep only with `MARGINALIA_API_KEY` |

`telegram` needs a channel list. Pass one, or connect a browser: net-sift then asks
Google for `site:t.me subscribers <query>` and reads the channels it finds.

## Open web (no account, through OpenCLI)

Sources marked *browser* need a connected Chromium session; the rest need only the
`opencli` binary.

| Source | What it covers | Notes |
|--------|----------------|-------|
| `google` | general web search | browser; 10 results per query; often CAPTCHA-blocked |
| `brave` | general web search, independent index | browser; up to 18 per query |
| `duckduckgo` | general web search | browser; up to 10 per query |
| `google_news` | news headlines | dated |
| `reuters` | Reuters articles | browser |
| `youtube` | videos | browser |
| `tiktok` | videos | browser |
| `apple_podcasts` | podcast shows | |
| `substack` | newsletter posts | |
| `medium` | articles | browser |
| `weixin` | WeChat public-account articles | browser; 10 per query |
| `tieba` | Baidu Tieba threads | browser |
| `stackoverflow` | questions | |
| `wikipedia` | encyclopedia articles | |
| `wikidata` | entities | |
| `archive` | Internet Archive items | |

## Keyed (opt-in by key)

| Source | What it covers | Requires |
|--------|----------------|----------|
| `brave_api` | Brave Search API, for when there is no managed profile | `BRAVE_API_KEY`; metered, at most 10 requests and 200 results per sweep |
| `context7` | up-to-date code and library documentation | `CONTEXT7_API_KEY` |
| `marginalia` | independent index of the small, non-commercial web | `MARGINALIA_API_KEY` for the default sweep |

## Walled (login, through OpenCLI, opt-in by connectivity)

| Source | Requires |
|--------|----------|
| `twitter` | logged-in Chromium session |
| `reddit` | logged-in Chromium session |
| `instagram` | logged-in Chromium session |
| `facebook` | logged-in Chromium session (often blocks automation even so) |
| `bilibili` | logged-in Chromium session |
| `xiaohongshu` | logged-in Chromium session |
| `zhihu` | logged-in Chromium session |

Walled sources become available once net-sift has a managed browser profile (copied
from your logged-in Chromium during `net-sift install`); searches then run headless
with the browser closed. See `setup-opencli.md`. Run `net-sift doctor` to see which
accounts are signed in.

## Opt-in tools (separate from the sweep)

| Tool | What it covers | Requires |
|------|----------------|----------|
| `darkweb_search` | Tor onion-forum discussion (read-only, information-only; markets/credentials/illegal categories filtered out) | `tor` installed |
| `instagram_recon` | per-account Instagram analysis (profile, timeline, where, fans, followers, intersect) | HikerAPI key |

## Optional environment variables

| Variable | Effect |
|----------|--------|
| `GITHUB_TOKEN` | higher GitHub Search API rate limit |
| `BRAVE_API_KEY` | enables the keyed `brave_api` source (keyless `brave` runs through the browser) |
| `MARGINALIA_API_KEY` | personal Marginalia key; adds `marginalia` to the default sweep |
| `CONTEXT7_API_KEY` | enables Context7 code and library documentation search |
| `HIKERAPI_KEY` | enables Instagram account recon |
| `NET_SIFT_HOME` | where sessions are stored (default `~/.net-sift`) |
| `NET_SIFT_OPENCLI_BIN` | path to the `opencli` binary if not on `PATH` |
