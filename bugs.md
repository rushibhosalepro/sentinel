# Meta / third-party issues encountered during the build

Only issues in Meta APIs/SDKs (Model API, SAM 3.1, Muse, `meta-sam-parser`)
or third-party packages we depend on are logged here: what broke, workaround
used, and (if applicable) a minimal repro to file upstream.

## META-01 (2026-10-27): `meta-sam-parser` 0.1.0 lacks `parse_image_stream`

- Symptom: the Python port has no `parse_image_stream` / `parse_video_stream`
  (the TS `@meta-sam/parser` entry points), despite docs saying "the parsing
  entry points mirror the TypeScript contract". Only the generic
  `parse_responses_stream(events, format)` + `image_segmentation_format()` /
  `video_segmentation_format()` exist.
- Workaround: use `parse_responses_stream` directly (see `perception/sam.py`).
- Impact: none after workaround. Upstream: docs or package gap, worth a
  release note when the convenience wrappers land.
