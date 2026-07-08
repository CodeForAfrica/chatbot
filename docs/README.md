# Static edition — sensors.africa chatbot on GitHub Pages

`index.html` in this folder is a **fully self-contained, serverless version**
of the sensors.africa air-quality chatbot. The entire engine — intent parsing
with fuzzy city matching, live fetches from `api.sensors.africa`, EPA AQI
conversion, WHO 2021 guideline comparisons, audience-aware health advice,
city comparisons, rankings and trends — runs in the visitor's browser.
Nothing to host, pay for, or maintain.

## Get the link (one-time setup)

1. Repo **Settings → Pages → Source: "Deploy from a branch"**.
2. Branch: `main` · Folder: `/docs` · Save.
3. The chatbot goes live at **https://codeforafrica.github.io/chatbot/**
   and redeploys automatically on every push.

## Shareable questions

Pre-fill a question with the `?q=` parameter — useful for linking a specific
city from a news story:

```
https://codeforafrica.github.io/chatbot/?q=air+quality+in+nairobi
https://codeforafrica.github.io/chatbot/?q=is+it+safe+to+run+in+lagos
```

For testing, `?api=<base-url>` points the page at a different API host.

## Limits of the static edition

- **Rule-based only** — no Claude fallback for free-form questions (a public
  page cannot hide an API key).
- **No WhatsApp** — webhooks need a server. The FastAPI app at the repo root
  provides WhatsApp (Twilio + Meta Cloud API), the JSON API, and the optional
  Claude layer.
- **CORS** — the browser can only call `api.sensors.africa` if the API sends
  cross-origin headers. If replies show a network error while the API is up,
  that is the cause; deploy the server edition instead (or enable CORS on the
  API).

Data: [sensors.africa](https://sensors.africa), a Code for Africa project.
