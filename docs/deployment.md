# Despliegue

Qué hay que provisionar para que `deploy.yml` pueda ejecutarse, cómo se hace
y con qué trampas nos hemos encontrado al hacerlo de verdad. La topología y
sus motivos están en `ARCHITECTURE.md` §12 del repositorio privado `Futuro`;
esto es la parte operativa.

**Este fichero no contiene valores concretos** —ni IP, ni OCID, ni dominio,
ni secretos— y no debe contenerlos nunca: es un repositorio público, y esos
datos son un mapa de la infraestructura. Los valores reales viven en el
repositorio privado `Futuro`. Aquí van marcadores del tipo `<IP-PUBLICA>`.

## 1. La VM de Oracle

Instancia Ampere A1 (Always Free), Ubuntu 24.04 LTS arm64, en la región
home de la cuenta.

Crear primero la **red** con el asistente *Networking → Virtual cloud
networks → Start VCN Wizard → Create VCN with Internet Connectivity*, y solo
después la instancia seleccionando esa VCN. Hacerlo al revés, desde el
formulario de la instancia, tiene dos problemas: el checkbox de IP pública
valida contra una subred que aún no existe y se queda bloqueado, y el
asistente inline puede dejar la VCN **sin internet gateway**, con lo que la
VM tiene IP pública pero no llega a internet.

Al crear la instancia:

- Elegir **primero la shape** (`VM.Standard.A1.Flex`) y después la imagen:
  la lista de imágenes se filtra por arquitectura, y al revés ofrece la de
  x86.
- Subred **pública**, con IP pública asignada automáticamente.
- Boot volume 50 GB, VPU **10**. Subir el VPU se factura aparte de los GB.
- *Restore instance lifecycle state after infrastructure maintenance*
  **activado**, o tras un mantenimiento de Oracle la VM vuelve parada.
- Del agente de Oracle Cloud, dejar **Compute Instance Monitoring**
  activado: sus métricas son las que demuestran que la instancia no está
  inactiva, y por tanto lo que evita que Oracle la reclame.

### La capacidad ARM es el cuello de botella real

`Out of host capacity` al crear la instancia es lo normal, no un error de
configuración. Lo que aprendimos peleándolo:

- **La mayoría de regiones europeas tienen una sola availability domain**,
  así que el consejo del propio mensaje de error ("prueba otra AD") no
  aplica. Verificable con `oci iam availability-domain list`.
- **Pedir menos máquina no ayuda tanto como parece.** Fallaron por igual
  4 OCPU/24 GB, 2/12 y 1/6.
- **Oracle limita el ritmo de intentos.** Tres seguidos en seis minutos ya
  disparan `Too many requests`, y seguir insistiendo renueva el bloqueo. Un
  intento cada 4 minutos se mantiene por debajo del umbral.
- **Lo que de verdad lo desbloquea es pasar la cuenta a Pay As You Go.** Con
  free tier: 65 intentos en 14 horas, ninguna ventana. Tras el upgrade: 34
  intentos, dentro. El cuello de botella no es la suerte, es el tramo de
  prioridad.
- El upgrade **mantiene gratis lo Always Free** y no cobra nada por
  adelantado; solo hace una autorización temporal en la tarjeta que se
  revierte sola. Lo que se pierde es el techo duro, así que la alarma de
  presupuesto deja de ser opcional.
- Se puede comprobar que el upgrade se ha propagado mirando la cuota:
  `oci limits resource-availability get --service-name compute --limit-name
  standard-a1-core-count`. En free tier son 4 cores; en PAYG, decenas.
  **Cuota y capacidad física son cosas distintas**: la cuota dice cuánto te
  dejan pedir, no cuántos hosts hay libres.
- Con la cuota alta, **nada impide ya pedir una máquina que se cobre**.
  Always Free cubre 4 OCPU y 24 GB de Ampere; a partir de ahí se factura, y
  el aviso *Always Free eligible* de la consola pasa a ser la única
  barandilla.

Un bucle de reintentos es la herramienta correcta, pero **no lo ejecutes en
un portátil sin enchufar**: macOS suspende el proceso y se pierden horas sin
un solo intento. `caffeinate -s` solo es efectivo con alimentación externa, y
cerrar la tapa suspende igualmente.

## 2. El dominio

Un nombre apuntando a la IP pública de la VM. Sirve un dominio propio o
DuckDNS gratis.

Con DuckDNS **no hace falta el reto DNS** que menciona `ARCHITECTURE.md`, y
por tanto tampoco recompilar Caddy con el plugin `caddy-dns/duckdns`:
DuckDNS está en la Public Suffix List, así que cada subdominio cuenta como
dominio propio para Let's Encrypt y el reto HTTP-01 estándar funciona con la
imagen `caddy:2-alpine` tal cual. Solo exige que el puerto 80 sea
alcanzable.

Apuntar el subdominio es una llamada:

```bash
curl "https://www.duckdns.org/update?domains=<SUBDOMINIO>&token=<TOKEN>&ip=<IP-PUBLICA>"
```

El token de DuckDNS es una credencial: quien lo tenga puede reapuntar el
dominio. No entra en ningún repositorio.

## 3. Abrir los puertos: hay que hacerlo DOS veces

Esta es la trampa que más tiempo cuesta encontrar.

1. **En la security list de la VCN**, reglas de entrada TCP para 80 y 443
   desde `0.0.0.0/0`. Por consola, o por CLI con
   `oci network security-list update`, que **reemplaza la lista entera**:
   hay que incluir las reglas que ya había, o se pierde el acceso por SSH.
2. **En la propia VM.** Las imágenes de Ubuntu de Oracle traen reglas de
   `iptables` preinstaladas que `ufw` no gestiona y que descartan 80 y 443
   aunque la VCN los abra. Sin esto, `ufw status` dice que están permitidos
   y el sitio sigue sin responder:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 4. Preparar la VM

- Docker Engine con el plugin de Compose, desde el repositorio de Docker
  (`arch=arm64`), no el `docker.io` de Ubuntu.
- `/opt/futuro/` y `/opt/futuro/caddy/` como raíz del stack, propiedad del
  usuario `ubuntu`. El workflow copia ahí `docker-compose.yml` y
  `caddy/Caddyfile`; el resto lo pone Compose.
- Añadir `ubuntu` al grupo `docker` y **volver a entrar por SSH** para que
  aplique.
- 2 GB de swap: con 6 GB de RAM un build puntual puede picar alto, y un OOM
  matando Postgres es peor que unos MB de swap.
- `unattended-upgrades` para las actualizaciones de seguridad.

## 5. El cliente OAuth de Google

En Google Cloud Console, credenciales *OAuth 2.0 Client ID* / aplicación web:

- Origen autorizado: `https://<DOMINIO>`
- Redirect URI autorizado: `https://<DOMINIO>/api/auth/callback`

La pantalla de consentimiento puede quedarse en modo *Testing* con la propia
cuenta como usuario de prueba: la allowlist es de un solo email, así que no
hay nada que verificar ante Google.

## 6. El `.env` de producción, en la VM

Vive en `/opt/futuro/.env` y **no pasa nunca por CI**. Se escribe a mano una
vez, partiendo del bloque de producción de `.env.example`. Con
`ENV=production` la API no arranca si falta cualquiera de sus variables, si
`SESSION_SECRET` sigue en el valor de desarrollo o si `PUBLIC_BASE_URL` no
es `https://`. Es deliberado: un esqueleto que levanta con configuración de
desarrollo en producción es peor que uno que no levanta.

## 7. Los secretos de GitHub

En un **Environment** llamado `production` (no en variables de repositorio,
según `ARCHITECTURE.md` §11):

| Secreto | Qué es |
|---|---|
| `DEPLOY_SSH_HOST` | IP o nombre de la VM |
| `DEPLOY_SSH_USER` | Usuario con permiso sobre `/opt/futuro` y Docker |
| `DEPLOY_SSH_KEY` | Clave privada dedicada al deploy, revocable |
| `DEPLOY_SSH_KNOWN_HOSTS` | Salida de `ssh-keyscan <host>` |
| `APP_DOMAIN` | El dominio, para la comprobación de salud |

`DEPLOY_SSH_KNOWN_HOSTS` no es opcional: sin fijar la huella, el deploy
confiaría en el primer servidor que respondiese.

La clave de deploy debe ser **distinta** de la clave personal de
administración, para poder revocarla sin perder el acceso a la VM.

## 8. Backup

`pg_dump` diario cifrado a Oracle Object Storage (10 GB gratis), retención
de 30 días. El perfil ya está respaldado por vivir en git.

## Riesgo conocido: el rollback no revierte migraciones

`deploy.yml` vuelve al tag de imagen anterior si la comprobación de salud
falla, pero **no** hace `alembic downgrade`: revertir un esquema a ciegas
puede perder datos. Si el fallo fue de migración hay que arreglarlo a mano.
La alternativa —migraciones siempre compatibles hacia atrás— es la buena, y
es la disciplina a mantener desde la primera tabla de M1.
