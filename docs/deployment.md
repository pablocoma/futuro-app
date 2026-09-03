# Despliegue

Qué hay que provisionar a mano para que `deploy.yml` pueda ejecutarse, y por
qué cada pieza es como es. La topología y sus motivos están en
`ARCHITECTURE.md` §12 del repositorio privado `Futuro`; esto es la lista
operativa.

**Estado a 2026-09-03: nada de esto existe todavía.** El workflow está
escrito y su paso de comprobación previa falla con un mensaje claro mientras
falten los secretos, para no dejar un deploy a medias.

## 1. La VM de Oracle

Instancia Ampere A1 (Always Free), Ubuntu 24.04 LTS arm64.

- Security list de Oracle y `ufw` abriendo solo 22, 80 y 443.
- SSH solo por clave; contraseña deshabilitada.
- Docker Engine con el plugin de Compose.
- `/opt/futuro/` como raíz del stack, con `caddy/` dentro. El workflow copia
  ahí `docker-compose.yml` y `caddy/Caddyfile`; el resto lo pone Compose.

Cuidado documentado en `ARCHITECTURE.md` §12: Oracle puede reclamar
instancias Always Free inactivas. Con la app corriendo y el cron de backup
no se considera inactiva.

## 2. El dominio

Un nombre apuntando a la IP pública de la VM. Sirve un dominio propio
(~10 €/año) o DuckDNS gratis con reto DNS. Caddy resuelve el certificado con
Let's Encrypt en el primer arranque, sin configuración extra.

## 3. El cliente OAuth de Google

En Google Cloud Console, credenciales de tipo *OAuth 2.0 Client ID* /
aplicación web:

- Origen autorizado: `https://<dominio>`
- Redirect URI autorizado: `https://<dominio>/api/auth/callback`

La pantalla de consentimiento puede quedarse en modo *Testing* con la propia
cuenta como usuario de prueba: la allowlist es de un solo email, así que no
hay nada que verificar ante Google.

## 4. El `.env` de producción, en la VM

Vive en `/opt/futuro/.env` y **no pasa nunca por CI**. Se escribe a mano una
vez, partiendo del bloque de producción de `.env.example`:

```
ENV=production
APP_DOMAIN=<dominio>
PUBLIC_BASE_URL=https://<dominio>
DEV_AUTH_BYPASS=false
SESSION_SECRET=<openssl rand -hex 32>
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ALLOWED_EMAILS=<tu email>
POSTGRES_PASSWORD=<openssl rand -hex 32>
```

Con `ENV=production` la API no arranca si falta cualquiera de esos, si
`SESSION_SECRET` sigue en el valor de desarrollo o si `PUBLIC_BASE_URL` no
es `https://`. Es deliberado: un esqueleto que levanta con la configuración
de desarrollo en producción es peor que uno que no levanta.

## 5. Los secretos de GitHub

En un **Environment** llamado `production` (no en variables de
repositorio, según `ARCHITECTURE.md` §11):

| Secreto | Qué es |
|---|---|
| `DEPLOY_SSH_HOST` | IP o nombre de la VM |
| `DEPLOY_SSH_USER` | Usuario con permiso sobre `/opt/futuro` y Docker |
| `DEPLOY_SSH_KEY` | Clave privada dedicada al deploy, revocable |
| `DEPLOY_SSH_KNOWN_HOSTS` | Salida de `ssh-keyscan <host>` |
| `APP_DOMAIN` | El dominio, para la comprobación de salud |

`DEPLOY_SSH_KNOWN_HOSTS` no es opcional: sin fijar la huella, el deploy
confiaría en el primer servidor que respondiese.

## 6. Backup

`pg_dump` diario cifrado a Oracle Object Storage (10 GB gratis), retención
de 30 días. El perfil ya está respaldado por vivir en git.

## Riesgo conocido: el rollback no revierte migraciones

`deploy.yml` vuelve al tag de imagen anterior si la comprobación de salud
falla, pero **no** hace `alembic downgrade`: revertir un esquema a ciegas
puede perder datos. Si el fallo fue de migración hay que arreglarlo a mano.
La alternativa —migraciones siempre compatibles hacia atrás— es la buena, y
es la disciplina a mantener desde la primera tabla de M1.
