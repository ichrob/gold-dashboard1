# Gold research v1

The Recherche tab performs read-only research from public FXStreet news and analysis RSS, the World Gold Council RSS, and its verified official YouTube channel feed. It refreshes in a separate server thread every 15 minutes; snapshots never wait for a network request. No paid API or subscription is used. Restarts reset the in-memory snapshot; counts are per latest run, not lifetime totals.

Each report distinguishes fetched feeds, distinct publishers, scanned entries, relevant deduplicated gold entries, structured article bodies successfully extracted, videos found and videos actually analyzed. Up to six current articles are fetched with bounded response sizes. Only HTTPS publisher URLs are followed. No arbitrary URLs, commands or instructions from source content are executed. Displayed strings use textContent and links retain origin evidence. Article bodies are transient, not republished or saved in full; short feed excerpts are at most 20 words per item.

The classifier is intentionally limited and clearly disclosed: subject-linked textual rules, not an LLM, FinBERT or semantic understanding. Historical direction is separate from explicit future outlook. Conditional statements and questions do not become firm predictions. Publication timestamps are not rewritten on retrieval; entries beyond seven days are omitted, unknown/future times and material older than 24 hours cannot vote. Different horizons are not pooled. At least two distinct publishers with unopposed explicit Intraday outlook are needed for a directional research consensus. Publisher grouping does not prove economic independence or detect every syndicated story.

In v1 videos had metadata only and contributed no directional votes; v2 caption support is described below. The initial live probe could not retrieve the YouTube feed; that failure is displayed rather than counted as a neutral opinion. No speech-to-text or paid model service is activated.

Research does not modify technical analysis, product ranking/approval, stops, targets, or pushes. It is not self-training and no predictive benefit is established. A semantic article/transcript pipeline and prospective price-outcome validation remain necessary before evaluating whether research improves the active forecast.

Validation: tests cover past/future separation, dollar/gold confusion, negation, conditional language, YouTube non-voting, source allowlists, stale/missing/future timestamps, duplicate feeds, publisher grouping, unsupported XML, missing article bodies and unavailable feeds. Authentication tests include /api/gold-research. Existing dashboard tests remain unchanged. Local live probe: 70 feed entries, 12 gold items, 3 full article bodies, 3/4 feeds available, 2 publishers; counts vary with time. Publication authorized by the user on 7 October 2026.


## YouTube transcript support v2

The first three discovered official-channel videos per run are offered to a public-caption reader. It validates video ID, playability status, caption URL/video identity and official channel ID, prefers published English/German captions over automatic captions, limits response sizes, and caches derived results for one hour. Empty/missing captions, login walls and non-YouTube redirects fail closed; no proxy, challenge bypass, account cookies or paid service is used. Signed caption URLs are never logged or returned. No audio/video is downloaded and no chart imagery is analyzed.

Recherche also provides “YouTube-Video prüfen” for a direct link and a transcript text import fallback. Imported text is explicitly unverified and excluded from publisher consensus, as are manually supplied links without a verified exact publication timestamp. Results include word count, caption language, automatic-caption disclosure and up to three gold-mention timestamps. Only derived results remain in memory (at most 20 manual reports, seven-day expiry, reset on restart); full transcripts are not persisted or republished.

Text analysis remains conservative and rule-based, not semantic AI. A recognized expression can be LONG/SHORT; otherwise the result stays unknown. Titles are excluded from transcript analysis. Tests cover English/German text, title/content disagreement, empty/short/invalid captions, JSON3/XML, wrong video/channel identity, unsafe URL rejection, blocked playback and authenticated POST handling. Live verification found an English automatic caption track but its text endpoint returned an empty body; automatic retrieval is therefore not claimed to work for every video. Manual transcript analysis is the available fallback.

## Screenshot-only entry

Recherche → YouTube-Video prüfen now starts with a single image picker. The image is retained before resetting the Android picker, then processed locally using the existing bounded OCR worker/queue in a new plain-text mode (no financial-field repair). Only extracted text is sent to Bob; the image is not uploaded or retained by this feature.

A visible valid YouTube URL resolves directly. Otherwise Bob searches up to two gold-title lines on YouTube and requires both the entire title and channel name to occur in the screenshot text with one unique result. It never picks a fuzzy winner. Multiple links, multiple matches, truncated titles, absent channel names and ambiguous screenshots fail with a request for a clearer crop. Public search JSON is parsed as data, never executed.

Successful identification immediately invokes the existing caption-content analyzer; no link entry or confirmation is required. The recognized title/link remains visible even when captions cannot be retrieved, and that case is explicitly not a completed video analysis. A screenshot cannot supply unseen spoken content or bypass unavailable captions. Optional link/transcript entry remains under secondary controls.

Validation: backend tests cover direct links, title/channel matching, ambiguity, script-data parsing and caption failure. UI tests cover Android file retention before reset, automatic lookup, picker cancel and OCR failure without a network call. Live search returned 18 videos and resolved a full World Gold Council title/channel pair. Real user screenshots and device interactions remain unverified until supplied.

Bei vollständigem Titel ohne sichtbaren Kanal oder mehreren gleichnamigen Videos zeigt Bob bis zu acht Treffer mit Kanal, Veröffentlichungsalter und Aufrufzahl zur Auswahl. Erst die Auswahl startet die Untertitelprüfung. Alter und Aufrufe sind Suchmetadaten und werden nicht als automatische Identitätsbestätigung benutzt. Linkänderungen löschen alte Screenshot-Fehler.
