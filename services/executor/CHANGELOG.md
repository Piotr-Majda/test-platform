# Executor changelog

Every change that can affect the discovered catalog, step identifiers, execution behavior,
or test outcomes must increment the executor package version before deployment. The
executor publishes this version as `PluginManifest.framework_version`, and the API stamps it
immutably on each new run.

## 0.1.1 — 2026-07-23

### Changed

- Replaced the live `GET` assertion against a YouTube `/watch` page with validation of the
  video metadata returned by the channel RSS feed.
- Renamed the catalog step from `assert_latest_video` to
  `assert_latest_video_metadata`.

### Reason

YouTube returned HTTP 429 to Railway's cloud egress IP even when the video existed and was
available to normal browsers. The old assertion therefore reported an external anti-bot
rate limit as a test failure. Version `0.1.1` keeps new history separate from runs produced
by the previous behavior in `0.1.0`.

## 0.1.0

- Initial executor framework, catalog, worker pool, steps, adapters, and example tests.
