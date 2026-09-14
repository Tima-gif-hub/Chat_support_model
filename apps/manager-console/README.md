# Manager console

## Purpose

This app presents the complaint queue for managers. It keeps triage focused on consented complaint records, their conversation context, status, internal note, and append-only audit history.

## Presentation scope

This is a portfolio reconstruction of a manager-facing complaint queue. It presents synthetic records and contract-shaped runtime responses; it does not claim to be the original company's production frontend or establish ownership of that interface.

## Boundary

Presentation logic only. The browser uses same-origin support-runtime routes and an HTTP-only manager session cookie. It has no database credentials and never calls RAG or model serving directly. This is a queue, not a CRM: it does not manage customers, sales, orders, refunds, or delivery schedules.

## Inputs and outputs

- Input: runtime-owned complaint records and manager filter/action choices.
- Output: status patches and internal-note updates to the versioned runtime endpoint.
- Displayed record fields: subtype, created time, status, conversation excerpt, consent source, customer context, and audit history.

## Architecture

`index.html` defines the semantic queue/detail workspace, `styles.css` owns the responsive service-ledger visual system, and `app.mjs` maps runtime data to safe DOM nodes using `textContent`. Nginx serves static files with security headers. The root gateway owns authentication entry and same-origin routing.

## Main workflow

1. Request the queue from `/api/v1/manager/complaints`.
2. Filter locally by status, subtype, or reference/excerpt text.
3. Open one record and review its consent source and audit trail.
4. Acknowledge or resolve with a versioned `PATCH`.
5. Add a concise internal note through the same update endpoint.

Appending `?fixture=queue` uses deterministic synthetic queue data for portfolio review and Playwright screenshots. Fixture mode performs no runtime writes.

## Configuration

No API host is bundled. All requests are relative `/api/v1/manager/*` paths and include the same-origin session cookie. The gateway maps `/manager/` to this app.

## Failure handling

An expired manager session requests sign-in again. A failed status or note update is not applied optimistically and displays an associated alert. Empty filters have an explicit empty state. Raw provider errors and stack traces remain hidden.

## Owned tests and workflow

`npm test` runs dependency-free source checks for required fields, operations, safe rendering, focus, and reduced motion. After `npm ci`, `npm run test:ui` starts the prefixed static test server and runs Playwright at 1440×900 and 390×844. Root `frontends.yml` owns frontend CI.

## User journeys

- review the open queue and inspect a complaint;
- filter by status and subtype;
- conversation excerpt and consent source review;
- acknowledge and resolve;
- add an internal note;
- inspect audit history.

## Accessibility

The workspace includes a skip link, labelled search and filters, semantic buttons, visible focus, polite detail updates, live save/error feedback, AA-contrast tokens, and a single-column mobile reading order. Reduced-motion preferences disable scroll animation.

## Screenshots

The browser-captured deterministic synthetic manager queue is shown in the root [screenshot gallery](../../docs/screenshots/gallery.md).

## Production build

```bash
docker build -t furniture-support-manager-console apps/manager-console
docker run --rm -p 8081:8080 furniture-support-manager-console
```

Open `http://localhost:8081/manager/?fixture=queue` for the static deterministic view. Use the root Compose stack for authenticated runtime actions.

## Local repository map

```text
manager-console/
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
