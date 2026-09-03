# web

Frontend de `futuro-app`: Next.js 16 (App Router) + TypeScript + Tailwind v4.

Se levanta con el resto del stack desde la raíz del repositorio (`make up`),
no por separado: la página se renderiza en servidor y necesita la API, que a
su vez necesita Postgres. Para servir solo este componente:

```bash
npm ci
npm run dev     # necesita API_INTERNAL_URL apuntando a una API viva
```

Harness: `npm run lint`, `npm run typecheck`, `npm run test`. Los tres
corren también desde `make check` en la raíz, que es lo que reproduce el CI.

La paleta y el diseño de cada pantalla están decididos en
`docs/APP_SCREENS.md` del repositorio privado `Futuro`; `src/app/globals.css`
la traduce a variables de Tailwind con los nombres de token de ese
documento.
