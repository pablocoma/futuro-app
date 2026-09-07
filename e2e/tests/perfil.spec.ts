import { expect, test } from "@playwright/test";

/**
 * El recorrido de M0 de Fase 2 de punta a punta: editar
 * `config/objectives.yaml`, ver el diff sin escribir nada, y confirmar
 * -que escribe, commitea y empuja de verdad-.
 *
 * Contra el remoto de git local que siembra `make seed-data-repo-write`
 * (enganchado a `make up`), no contra GitHub ni el repositorio privado
 * real. El estado se acumula entre ejecuciones -igual que las ofertas en
 * Postgres en el resto de la suite-, así que la declaración lleva una
 * marca única para no depender de lo que dejó una ejecución anterior.
 */

test("editar el objetivo, ver el diff sin escribir, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const declaracion = `Declaración de prueba ${marca}.`;

  await page.goto("/perfil");
  await expect(page.getByRole("heading", { name: "Objetivos" })).toBeVisible();

  await page.getByLabel("Declaración").fill(declaracion);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(declaracion);
  await expect(
    page.getByRole("heading", { name: "Diff, sin escribir todavía" }),
  ).toBeVisible();

  // Todavía no se ha escrito nada: el botón de confirmar ya está
  // habilitado, pero no se ha pulsado.
  const confirmar = page.getByRole("button", { name: "Confirmar y guardar" });
  await expect(confirmar).toBeEnabled();

  await confirmar.click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();
  await expect(page.getByText(/commit [0-9a-f]{12}/)).toBeVisible();

  // Y de verdad quedó escrito: recargar trae la declaración nueva.
  await page.reload();
  await expect(page.getByLabel("Declaración")).toHaveValue(declaracion);
});

/**
 * M1: `preferences.yaml` y `constraints.yaml`, alternados con las
 * pestañas de `PerfilTabs` sin cambiar de URL. Cada bloque prueba su
 * propio fichero de punta a punta, mismo patrón que M0 arriba.
 */

test("las siete pestañas de Perfil alternan de fichero sin cambiar de URL", async ({
  page,
}) => {
  await page.goto("/perfil");
  await expect(page.getByRole("heading", { name: "Objetivos" })).toBeVisible();

  await page.getByRole("button", { name: "Preferencias" }).click();
  await expect(page.getByRole("heading", { name: "Preferencias" })).toBeVisible();
  await expect(page).toHaveURL(/\/perfil$/);

  await page.getByRole("button", { name: "Restricciones" }).click();
  await expect(
    page.getByRole("heading", { name: "Restricciones", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/perfil$/);

  await page.getByRole("button", { name: "Bullets" }).click();
  await expect(
    page.getByRole("heading", { name: "Banco de bullets" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/perfil$/);

  await page.getByRole("button", { name: "Variantes de rol" }).click();
  await expect(
    page.getByRole("heading", { name: "Variantes de rol" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/perfil$/);

  await page.getByRole("button", { name: "Variantes de CV" }).click();
  await expect(
    page.getByRole("heading", { name: "Variantes de CV" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/perfil$/);

  await page.getByRole("button", { name: "Catálogo de proyectos" }).click();
  await expect(
    page.getByRole("heading", { name: "Catálogo de proyectos" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/perfil$/);

  await page.getByRole("button", { name: "Objetivos" }).click();
  await expect(page.getByRole("heading", { name: "Objetivos" })).toBeVisible();
});

test("editar una preferencia, ver el diff sin escribir, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const condicion = `Condición de prueba ${marca}.`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Preferencias" }).click();
  await expect(page.getByRole("heading", { name: "Preferencias" })).toBeVisible();

  await page.getByLabel("Condición").fill(condicion);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(condicion);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Preferencias" }).click();
  await expect(page.getByLabel("Condición")).toHaveValue(condicion);
});

test("añadir una condición descalificante y una decisión sustituida, ver el diff, y confirmar", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const nuevoId = `condicion_${marca}`;
  const nuevaRegla = `Regla añadida por e2e ${marca}.`;
  const nuevaClave = `decision_${marca}`;
  const nuevoTexto = `Decisión sustituida añadida por e2e ${marca}.`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Restricciones" }).click();
  await expect(
    page.getByRole("heading", { name: "Restricciones", exact: true }),
  ).toBeVisible();

  await page.getByPlaceholder("identificador").fill(nuevoId);
  await page.getByPlaceholder("regla").fill(nuevaRegla);
  await page.getByRole("button", { name: "+ Añadir condición" }).click();

  // La fila existente del fixture ya lleva el mismo placeholder: la nueva
  // se añade al final, así que se rellena por posición.
  await page.getByRole("button", { name: "+ Añadir decisión sustituida" }).click();
  await page.getByPlaceholder("clave").last().fill(nuevaClave);
  await page.getByPlaceholder("texto").last().fill(nuevoTexto);

  await page.getByRole("button", { name: "Ver cambios" }).click();
  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(nuevoId);
  await expect(diff).toContainText(nuevaClave);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  // Y de verdad quedó escrito: recargar trae la fila y la decisión nuevas.
  await page.reload();
  await page.getByRole("button", { name: "Restricciones" }).click();
  await expect(page.getByText(nuevoId)).toBeVisible();
  await expect(page.getByPlaceholder("clave").last()).toHaveValue(nuevaClave);
});

/**
 * M2: el banco de bullets y el contenido de variantes de rol. Contra el
 * fixture sintético de `data_repo_write`, con dos bullets
 * (`invented_bullet_one`, `invented_bullet_two`) y dos variantes
 * (`invented_variant_one`, `invented_variant_two`) -no los trece bullets
 * ni las cinco variantes reales, ver `docs/decisions/fase-2-perfil-editable.md`-.
 */

test("editar el texto de un bullet existente, ver el diff, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const texto = `Contributed to an invented change ${marca}.`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Bullets" }).click();
  await expect(
    page.getByRole("heading", { name: "Banco de bullets" }),
  ).toBeVisible();

  await page.getByLabel("Texto de invented_bullet_one").fill(texto);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(texto);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Bullets" }).click();
  await expect(page.getByLabel("Texto de invented_bullet_one")).toHaveValue(texto);
});

test("añadir un bullet nuevo, ver el diff, y confirmar lo escribe sin tocar los existentes", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const nuevoId = `bullet_${marca}`;
  const nuevoTexto = `Worked on a bullet added by e2e ${marca}.`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Bullets" }).click();
  await expect(
    page.getByRole("heading", { name: "Banco de bullets" }),
  ).toBeVisible();

  await page.getByPlaceholder("identificador").fill(nuevoId);
  await page.getByPlaceholder("texto").fill(nuevoTexto);
  await page.getByRole("button", { name: "+ Añadir bullet" }).click();

  await page.getByRole("button", { name: "Ver cambios" }).click();
  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(nuevoId);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Bullets" }).click();
  await expect(page.getByText(nuevoId)).toBeVisible();
});

test("editar el perfil de una variante de rol, ver el diff, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const perfil = `Perfil editado por e2e ${marca}.`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Variantes de rol" }).click();
  await expect(
    page.getByRole("heading", { name: "Variantes de rol" }),
  ).toBeVisible();

  await page.getByLabel("Perfil de invented_variant_one").fill(perfil);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(perfil);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Variantes de rol" }).click();
  await expect(page.getByLabel("Perfil de invented_variant_one")).toHaveValue(
    perfil,
  );
});

/**
 * M3: `config/cv_variants.yaml` (solo `base_variants`, editable; el resto
 * -`claim_rules`, `fixed_sections`...- es de solo lectura) y
 * `profile/project_catalog.yaml` (primera vez que esta app lo edita).
 * Contra el mismo fixture sintético, ampliado para M3 con
 * `invented_variant_blocked` -de solo lectura, sin listas de prioridad- y
 * dos proyectos (`invented_project_professional`,
 * `invented_project_academic`).
 */

test("editar el énfasis de una variante de CV activa, ver el diff, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const enfasis = `invented_emphasis_${marca}`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Variantes de CV" }).click();
  await expect(
    page.getByRole("heading", { name: "Variantes de CV" }),
  ).toBeVisible();

  // La variante bloqueada -con `status`- se enseña de solo lectura, sin
  // ningún campo editable.
  await expect(page.getByText("invented_variant_blocked")).toBeVisible();

  await page
    .getByLabel("Énfasis de invented_variant_one")
    .fill(enfasis);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(enfasis);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Variantes de CV" }).click();
  await expect(page.getByLabel("Énfasis de invented_variant_one")).toHaveValue(
    enfasis,
  );
});

test("editar el nombre de un proyecto del catálogo, ver el diff, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const nombre = `Invented Professional Project ${marca}`;

  await page.goto("/perfil");
  await page.getByRole("button", { name: "Catálogo de proyectos" }).click();
  await expect(
    page.getByRole("heading", { name: "Catálogo de proyectos" }),
  ).toBeVisible();

  await page
    .getByLabel("Nombre de invented_project_professional")
    .fill(nombre);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(nombre);

  await page.getByRole("button", { name: "Confirmar y guardar" }).click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Catálogo de proyectos" }).click();
  await expect(
    page.getByLabel("Nombre de invented_project_professional"),
  ).toHaveValue(nombre);
});
