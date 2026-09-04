# Instagram + Facebook Reel Publishing Setup

Mint-YT-Factory can publish every finished Short to:

- YouTube Shorts
- Instagram Reels
- Facebook Page Reels

Both the normal Publish Short workflow and Riddles Shorts workflow use the same social publishing module.

## GitHub Actions secrets

Add these repository secrets:

| Secret | Required for |
|---|---|
| `INSTAGRAM_USER_ID` | Instagram |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram |
| `FACEBOOK_PAGE_ID` | Facebook |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Facebook |
| `META_GRAPH_API_VERSION` | Optional |
| `SOCIAL_PUBLISH_STRICT` | Optional |

Use `SOCIAL_PUBLISH_STRICT=false` while testing. When enabled, any configured social destination that fails will fail the workflow.

## Instagram

Use an Instagram professional/business account and a Meta app authorized for content publishing.

The pipeline creates a resumable Reel container, uploads the generated MP4 directly to Meta, waits for processing, then publishes it.

Typical required publishing permissions depend on the Meta login/product configuration and include Instagram business/content publishing permissions.

## Facebook

Use a Facebook Page access token with permission to publish to the Page. The pipeline:

1. Starts a Page Reel upload session.
2. Uploads the generated video directly to Meta.
3. Publishes the Reel.

## Video format

The YouTube master remains untouched at 4K/60fps.

For Meta, the pipeline automatically creates:

- 1080x1920
- 9:16 portrait
- H.264 video
- AAC audio
- 60fps
- moderate Reel-friendly bitrate

The social derivative is saved as `social_reel.mp4` in the workflow output directory.

## Safety during rollout

If no Meta credentials are configured, social publishing is skipped and YouTube continues normally.

If credentials are configured and `SOCIAL_PUBLISH_STRICT=false`, YouTube remains successful even if Meta rejects a social upload. The failure is written to `social_publish_status.json`.

After testing successfully, set `SOCIAL_PUBLISH_STRICT=true` if you want a social publishing failure to fail the workflow.
