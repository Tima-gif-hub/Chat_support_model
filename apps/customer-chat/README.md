# Customer chat

## Purpose

This app presents the public implementation's customer-support conversation. It renders grounded answers, source citations, abstentions, complaint consent, submission references, and retryable failures without owning orchestration or business state.

## Presentation scope

This is a portfolio reconstruction of a customer-facing support flow. It presents synthetic fixtures and contract-shaped runtime responses; it does not claim to be the original company's production frontend or establish ownership of that interface.

## Boundary

Presentation logic only. The browser calls the support runtime through same-origin `/api/v1/*` routes. It never calls model serving, RAG, PostgreSQL, or Redis and contains no credentials. The assistant cannot place or modify orders, take payment, issue refunds, or promise availability.

## Inputs and outputs

- Input: anonymous session messages and complaint confirmation actions.
- Output: streamed text, status events, citations, complaint state, and safe client-facing errors.
- Runtime events: `status`, `token`, `citation`, `complaint.confirmation_required`, `complaint.submitted`, `completed`, and `error`.

## Architecture

`index.html` provides semantic structure, `styles.css` owns the responsive visual system, and `app.mjs` adapts runtime JSON/SSE events into safe DOM nodes using `textContent`. Nginx serves the static bundle with browser security headers; the root gateway owns external same-origin routing.

## Main workflow

1. Create an anonymous conversation when the first message is sent.
2. POST the message to the versioned runtime route.
3. Present live status, streamed tokens, and expandable citations.
4. Require a visible confirmation action for inferred complaints; show the queued ID after submission.
5. Preserve a clear retry path when RAG, model serving, or complaint persistence is unavailable.

The `Demo state` control selects deterministic synthetic views for portfolio review and screenshot capture. It does not write complaint records.

## Configuration

The client has no endpoint environment variable: all APIs are relative, same-origin paths. The gateway maps `/api/` to support runtime and `/customer/` to this container.

## Failure handling

Session expiry tells the customer to refresh. Retrieval failure is described as temporary inability to verify company information. Complaint persistence failure explicitly says the complaint was not submitted and leaves a retry action. Provider details and stack traces are never rendered.

## Owned tests and workflow

`npm test` runs dependency-free source checks for scope, state coverage, safe rendering, keyboard focus, and reduced motion. After `npm ci`, `npm run test:ui` starts the prefixed static test server and runs the Playwright desktop/mobile journeys. The root `frontends.yml` workflow owns frontend CI.

## User journeys

- catalog question with two expandable citations;
- insufficient-evidence abstention;
- ambiguous complaint awaiting confirmation;
- explicit complaint submitted with queued ID;
- retryable degraded response.

## Accessibility

The interface includes a skip link, semantic labels, visible focus, polite live regions, associated help text, keyboard-operable source disclosures, AA-contrast tokens, and reduced-motion handling. The 390 px layout keeps all controls reachable without horizontal scrolling.

## Screenshots

Browser captures of deterministic synthetic states are collected in the root [screenshot gallery](../../docs/screenshots/gallery.md): catalog, abstention, complaint confirmation, explicit submission, and degraded service states.

## Production build

```bash
docker build -t furniture-support-customer-chat apps/customer-chat
docker run --rm -p 8080:8080 furniture-support-customer-chat
```

Open `http://localhost:8080/customer/`. In the assembled repository, use the root Compose stack so same-origin runtime routes are available.

## Local repository map

```text
customer-chat/
├── src/index.html
├── src/styles.css
├── src/app.mjs
├── tests/smoke.test.mjs
├── tests/ui.spec.mjs
├── playwright.config.mjs
├── nginx.conf
├── Dockerfile
├── package-lock.json
└── package.json
```
