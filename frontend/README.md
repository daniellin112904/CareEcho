# Vela frontend

The patient kiosk (`/patient`) and the staff pages (`/care`), built with React, Vite, and TypeScript.
See the [project README](../README.md) for what Vela is, screenshots, and how to run everything.

```powershell
npm run dev      # from the repo root starts this and the API together
npm run build    # type-check and build
npm run lint
```

| Folder | What's in it |
|---|---|
| `src/pages/patient/` | The kiosk screen: the flame, the clock, cards, and the language picker |
| `src/pages/care/` | The staff pages: memories, today, conversations, alerts, life story, family messages, patient |
| `src/voice/` | Ember (the flame character), the agent's client tools, and conversation logging |
| `src/i18n.ts` | English, Spanish, and Chinese text for the patient screen |
| `src/theme.css` | Colors and the Inter font, shared by both sides |
| `public/` | The logo (`vela-logo.svg`) and the browser tab icon (`vela-icon.svg`) |
