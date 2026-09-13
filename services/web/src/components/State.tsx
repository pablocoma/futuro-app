/**
 * Un estado: texto con subrayado de color, no una pastilla de fondo.
 *
 * `label` es opcional: en un `<dl>` de detalle va etiquetado, y en la celda
 * de una tabla -donde la cabecera de columna ya dice qué es- no hace falta
 * repetirlo. Elementos genéricos y no `dt`/`dd` a propósito: el segundo uso
 * no vive dentro de un `<dl>`, y `dt`/`dd` sueltos ahí serían HTML inválido.
 */
export function State({
  label,
  value,
  tone,
}: {
  label?: string;
  value: string;
  tone: "pos" | "neg" | "acc";
}) {
  const underline = {
    pos: "decoration-pos",
    neg: "decoration-neg",
    acc: "decoration-acc",
  }[tone];
  return (
    <div>
      {label ? (
        <p className="font-mono text-xs uppercase tracking-widest text-ink3">
          {label}
        </p>
      ) : null}
      <p
        className={`text-sm underline decoration-2 underline-offset-4 ${underline} ${
          label ? "mt-1" : ""
        }`}
      >
        {value}
      </p>
    </div>
  );
}
