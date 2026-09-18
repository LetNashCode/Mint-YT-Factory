# Curated Found-Footage Mystery Workflow

The Mystery Footage Shorts pipeline is intentionally **catalog-driven**. It does not automatically choose a random archival video and invent a mystery around it.

## Case entry format

Add a case object to `mystery_footage_catalog.json`:

```json
{
  "id": "unique-case-id",
  "title": "Documented case title",
  "case_summary": "Short, neutral summary of the documented case.",
  "verified_facts": [
    "Fact supported by a reliable source",
    "Another documented fact"
  ],
  "theories_or_open_questions": [
    "Clearly attributed theory or unresolved question"
  ],
  "footage_description": "Exactly what the supplied video visibly contains.",
  "source_url": "https://example.com/source-page",
  "video_url": "https://example.com/direct-video-file.mp4",
  "license": "Specific license or permission basis",
  "rights_verified": false,
  "rights_notes": "What was checked and any restrictions",
  "attribution": "Required attribution text"
}
```

## Editorial and rights requirements

- The footage must actually relate to the selected case.
- `footage_description` must describe visible content, not assumptions.
- `verified_facts` must be supported by reliable sources.
- Theories must be labelled as theories or open questions.
- Do not add CCTV or news footage merely because it is easy to download.
- Set `rights_verified` to `true` only after checking the individual asset's commercial reuse conditions or obtaining permission.
- The workflow refuses to publish unverified cases.

## Cecil Hotel / Elisa Lam-style cases

Cases involving real victims may be added only with carefully sourced facts, respectful narration, and a lawful footage source. The pipeline does not automatically download or reuse famous CCTV footage based only on its availability online.

## Processing order

1. Select a curated case.
2. Download its matching footage.
3. Extract representative frames.
4. Send the frames plus case metadata to Gemini.
5. Generate a narration grounded in the visible footage and verified case facts.
6. Synthesize narration and loop the footage to cover the narration duration.
7. Upload privately for review.
