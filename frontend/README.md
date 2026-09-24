# Frontend (React)

See the main [README](../README.md) for how to run the whole app.

```bash
npm install --legacy-peer-deps
cp .env.example .env
npm start        # dev server on http://localhost:3000
npm run build    # production build in build/ (what Vercel runs)
```

- `src/pages/` — one file per screen (routes are declared in `src/App.js`)
- `src/components/` — reusable pieces; `src/components/ui/` is shadcn/ui
- `src/locales/` — English and French texts (i18next)
- `src/lib/api.js` — every call to the backend goes through here
