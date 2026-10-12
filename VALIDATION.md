# Validation record — 12 October 2026

- Python backend compiled successfully.
- Dashboard JavaScript passed `node --check`.
- 20 pytest tests passed (isolated temporary databases, mocked external paid/notification calls).
- One upstream Starlette deprecation warning about TestClient's httpx transport; no failing tests.
- Real no-key discovery succeeded: 60 Himalayas jobs, 15 Remotive jobs, 0 feed errors.
- Two prior application records were imported from Nepal_Application_Review.md. They are historical records, not newly sent applications.
- One free draft was produced during ingestion before senior-title gating was tightened. It was retired with an audit event after the rule change; the job no longer passes auto-preparation. No AI call occurred.
- CVs were read and retrieved: Nepal Fullstack and Frontend PDFs. Both include 3+ years; current profile uses 2 years and mandates review.
- No credentials were supplied for AI or Telegram. No paid calls, Telegram messages, application submissions, Connect purchases, or external writes were made.
- No browser-rendered visual QA or live ATS filling was performed; only frontend syntax, form-field mapping and authenticated API flows were tested.
- Source documentation: https://himalayas.app/docs/remote-jobs-api ; https://github.com/remotive-com/remote-jobs-api ; https://docs.greenhouse.io/job-board.html

## Manual acceptance on your Mac

1. Install requirements; run the launcher and unlock with your generated token.
2. Filter/search existing listings and open an opportunity; verify source attribution and missing-data labels.
3. Import a genuinely relevant listing with accurate Nepal eligibility, publication date and compensation evidence.
4. Confirm deterministic preparation is blocked for an ineligible or insufficiently evidenced job.
5. Generate a free draft, correct answers/CV, review it and inspect the complete packet.
6. Confirm approval sends nothing and Applied requires a platform confirmation reference.
7. Replacing a CV or updating a listing must invalidate review/approval.
8. With AI disabled, attempts to polish must retain a free draft and produce no provider request.
9. Inspect desktop/mobile layout and keyboard access in your preferred browser.
10. Enable optional services only after supplying and checking your own credentials.
