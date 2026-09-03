# cv_builder

Genera el `.tex` y el `README.md` de cada variante base de CV a partir de:

- una plantilla Jinja2 del CV maestro (`--master`);
- el banco de bullets profesionales (`--bullet-bank`,
  `cv/content/professional_bullet_bank.yaml` en el repo privado `Futuro`);
- el contenido por variante (`--role-content`,
  `cv/content/role_variant_content.yaml`);
- la configuración de variantes y `claim_rules` (`--variants-config`,
  `config/cv_variants.yaml`).

Este paquete no conoce ni contiene ningún dato personal: recibe las cuatro
rutas anteriores como argumentos y no asume ninguna ubicación fija dentro del
repositorio privado.

## Uso

```bash
uv run cv-builder build \
  --master path/to/master.tex.jinja2 \
  --bullet-bank path/to/professional_bullet_bank.yaml \
  --role-content path/to/role_variant_content.yaml \
  --variants-config path/to/cv_variants.yaml \
  --output-dir path/to/output
```

Un fallo en cualquier variante (bullet con `evidence_status` o `cv_usage` no
elegible, verbo de contribución no permitido, `bullet_id` desconocido,
variante sin contenido en `role_variant_content.yaml`) aborta el build
entero, sin escribir nada a disco, e imprime el motivo en stderr con
`exit(1)`.

Una variante con `status` en `config/cv_variants.yaml` (por ejemplo
`quant_exploratory`, con `status: blocked_pending_role_research_and_evidence`)
se salta: no hace falta que tenga contenido en `role_variant_content.yaml`.

## Contrato de la plantilla del maestro

`--master` debe ser una plantilla Jinja2 con delimitadores **no
estándar** — `\VAR{...}` en vez de `{{ ... }}`, `\BLOCK{...}` en vez de
`{% ... %}` — que exponga exactamente estas variables/bloques y nada más:

```latex
\section{Profile}
\VAR{profile}

\section{Work Experience}
\entry
  {...}
  {
    \begin{itemize}
\BLOCK{for bullet in role_bullets}
      \item \VAR{bullet}
\BLOCK{endfor}
    \end{itemize}
  }
...

\section{Technical Skills}
\BLOCK{for row in skill_rows}
\skillrow{\VAR{row.label}}{\VAR{row.value}}
\BLOCK{endfor}
```

Los delimitadores por defecto de Jinja2 no sirven aquí: el LaTeX fijo del
maestro real define macros con
`\newcommand{\entry}[5]{\textbf{#1}...}`, y la secuencia literal `{#`
colisiona con el delimitador de comentario por defecto (`{# ... #}`). Es el
mismo ajuste que usa Sphinx para generar LaTeX con Jinja2.

El resto del documento (identidad y contacto, empresa y fechas, educación,
Selected Project, Languages, Awards) debe ser LaTeX literal, sin `\VAR{`,
`\BLOCK{` ni `\#{`: como esas secciones no son variables Jinja2, ningún dato
de entrada puede tocarlas. Así es como este generador cumple, por
construcción y no por una comprobación en tiempo de ejecución, que las
`fixed_sections` de `config/cv_variants.yaml` no son editables por ningún
camino.

Ver `tests/fixtures/master.tex.jinja2` para un ejemplo mínimo completo.
