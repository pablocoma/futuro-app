"""Renderiza el `.tex` y el `README.md` de una variante con Jinja2.

Contrato que debe cumplir la plantilla del maestro (el `--master` que recibe
el CLI): debe exponer exactamente estas variables/bloques y nada más. El
resto del documento (identidad, empresa y fechas, educación, Selected
Project, Languages, Awards) debe ser LaTeX literal sin sintaxis Jinja2, para
que esas secciones queden inmodificables por construcción:

    \\section{Profile}
    \\VAR{profile}

    \\section{Work Experience}
    ...
        \\begin{itemize}
    \\BLOCK{for bullet in role_bullets}
          \\item \\VAR{bullet}
    \\BLOCK{endfor}
        \\end{itemize}
    ...
    \\section{Technical Skills}
    \\BLOCK{for row in skill_rows}
    \\skillrow{\\VAR{row.label}}{\\VAR{row.value}}
    \\BLOCK{endfor}

El maestro usa delimitadores Jinja2 no estándar (`\\VAR{...}`, `\\BLOCK{...}`)
en vez de los `{{ }}` / `{% %}` por defecto: el LaTeX fijo del maestro real
define macros con `\\newcommand{...}[N]{...\\textbf{#1}...}`, y la secuencia
literal `{#` ahí colisiona con el delimitador de comentario por defecto de
Jinja2. Es el mismo ajuste que usa Sphinx para generar LaTeX con Jinja2.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class SkillRowContext:
    label: str
    value: str


@dataclass(frozen=True)
class VariantRenderContext:
    variant_id: str
    display_name: str
    use_when: str
    target_roles: list[str]
    profile: str
    role_bullets: list[str]
    skill_rows: list[SkillRowContext]


def _latex_environment(template_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


def render_variant(master_template_path: Path, context: VariantRenderContext) -> str:
    env = _latex_environment(master_template_path.parent)
    template = env.get_template(master_template_path.name)
    return template.render(
        profile=context.profile,
        role_bullets=context.role_bullets,
        skill_rows=context.skill_rows,
    )


def render_readme(context: VariantRenderContext) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    template = env.get_template("variant_readme.md.jinja2")
    return template.render(
        variant_id=context.variant_id,
        display_name=context.display_name,
        use_when=context.use_when,
        target_roles=context.target_roles,
        profile=context.profile,
        role_bullets=context.role_bullets,
        skill_rows=context.skill_rows,
    )
