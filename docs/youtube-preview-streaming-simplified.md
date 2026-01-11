# YouTube Preview Streaming with yt-dlp (Simplified)

## Problem

YouTube iframe embeds are blocked in many environments (corporate networks, privacy filters, embedding disabled by video owner). Users can't preview videos before downloading.

## Solution

Use yt-dlp to get direct stream URL and play in HTML5 `<video>` element instead of iframe.

**Total code:** ~100 lines across 2 files

## Implementation

### Backend: Add One Route (~40 lines)

**File:** `pikaraoke/routes/search.py`

```python
@search_bp.route("/preview/stream/<video_id>")
def preview_stream(video_id):
    """Get YouTube stream URL for preview."""
    k = get_karaoke_instance()

    # Run yt-dlp to get stream URL (no download)
    cmd = [
        k.youtubedl_path,
        "--print",
        "url",
        "-f",
        "worst",  # Lowest quality for fast loading
        "--no-playlist",
        f"https://www.youtube.com/watch?v={video_id}",
    ]

    # Add proxy if configured
    if k.youtubedl_proxy:
        cmd += ["--proxy", k.youtubedl_proxy]

    # Add additional args (cookies, etc.)
    if k.additional_ytdl_args:
        cmd += shlex.split(k.additional_ytdl_args)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=True
        )
        stream_url = result.stdout.strip()

        return flask.jsonify(
            {
                "stream_url": stream_url,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    except Exception as e:
        logging.error(f"Preview error for {video_id}: {e}")
        return flask.jsonify({"error": str(e)}), 500
```

### Frontend: Replace iframe with video (~60 lines)

**File:** `pikaraoke/templates/search.html`

**1. Update modal HTML:**

```html
<div id="modal-js-example" class="modal">
    <div class="modal-background"></div>
    <div class="modal-content">
        <video id="modal-video" controls style="width:100%; background:#000"></video>
        <a id="youtube-link" href="" target="_blank" class="button">Open in YouTube</a>
    </div>
    <button class="modal-close is-large"></button>
</div>
```

**2. Update JavaScript click handler:**

```javascript
$("#search-results").on("click", ".img-wrapper", function () {
    const modal = document.getElementById("modal-js-example");
    const video = document.getElementById("modal-video");
    const link = document.getElementById("youtube-link");
    const videoId = $(this).closest("li").data("ytid");

    // Fetch stream URL
    $.get(`/preview/stream/${videoId}`, function(data) {
        video.src = data.stream_url;
        link.href = data.video_url;
        video.play();
    });

    modal.classList.add("is-active");

    // Close handler
    $(".modal-close, .modal-background").click(function() {
        modal.classList.remove("is-active");
        video.pause();
        video.src = "";
    });
});
```

## That's It!

**No cache class needed** - YouTube URLs stay valid for hours

**No new files** - just modify 2 existing files

**No complex error handling** - let it fail gracefully, "Open in YouTube" button works as fallback

## Browser Cookie Support

Automatically inherited via `k.additional_ytdl_args` - no extra code needed.

If user runs:

```bash
pikaraoke --ytdl-args "--cookies-from-browser firefox"
```

Preview will use those cookies automatically.

## Performance

- yt-dlp call: 1-2 seconds (metadata only, no download)
- Video streaming: Direct from YouTube to browser (Pi does nothing)
- Memory: Negligible
- CPU: \< 1% for 1-2 seconds

Safe for Raspberry Pi 3B.
