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

Walled sources appear automatically once OpenCLI is connected and you are logged
in. See `setup-opencli.md`. Run `net-sift doctor` to see the live set.

## Opt-in tools (separate from the sweep)

| Tool | What it covers | Requires |
|------|----------------|----------|
| `darkweb_search` | Tor onion-forum discussion (read-only, information-only; markets/credentials/illegal categories filtered out) | `tor` installed |
| `instagram_recon` | per-account Instagram analysis (profile, timeline, where, fans, followers, intersect) | HikerAPI key |

## Optional environment variables

| Variable | Effect |
|----------|--------|
| `GITHUB_TOKEN` | higher GitHub Search API rate limit |
| `HIKERAPI_KEY` | enables Instagram account recon |
| `NET_SIFT_HOME` | where sessions are stored (default `~/.net-sift`) |
| `NET_SIFT_OPENCLI_BIN` | path to the `opencli` binary if not on `PATH` |
