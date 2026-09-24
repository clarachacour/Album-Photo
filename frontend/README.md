# Frontend (React + Vite)

See the main [README](../README.md) for how to run the whole app.

```bash
npm install --legacy-peer-deps
cp .env.example .env
npm start          # dev server on http://localhost:3000 (instant reload)
npm run build      # production build in build/ (what Vercel runs)
npm run preview    # serve that production build locally to check it
npm run lint       # code checks (ESLint)
```

- `src/pages/` — one file per screen (routes are declared in `src/App.jsx`)
- `src/components/` — reusable pieces; `src/components/ui/` is shadcn/ui
- `src/locales/` — English and French texts (i18next)
- `src/lib/api.js` — every call to the backend goes through here
- `index.html` — the page shell; `src/index.jsx` starts React in it
- `vite.config.js` — build settings (the `@/` shortcut for `src/`, output folder)

Environment variables must start with `REACT_APP_` and are read in the code
with `import.meta.env.REACT_APP_...` (see `.env.example`). They end up in
the public JavaScript, so never put a secret there.
