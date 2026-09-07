"use client";

import { useActionState } from "react";

import { captureOffer, type CaptureState } from "./actions";

const INITIAL: CaptureState = { error: null };

export function CaptureForm() {
  const [state, action, pending] = useActionState(captureOffer, INITIAL);

  return (
    <form action={action} className="space-y-4">
      <div className="space-y-2">
        <label htmlFor="raw_text" className="block text-sm text-ink2">
          Texto del anuncio
        </label>
        <textarea
          id="raw_text"
          name="raw_text"
          rows={16}
          required
          placeholder="Pega aquí el anuncio entero, tal cual."
          className="w-full rounded-lg border border-white/10 bg-white/[0.02] p-4 font-mono text-sm leading-relaxed outline-none placeholder:text-ink3 focus:border-acc"
        />
        <p className="text-xs text-ink3">
          Se guarda tal como llega: es la prueba de qué se recibió y cuándo.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="capture_note" className="block text-sm text-ink2">
          Nota <span className="text-ink3">(opcional)</span>
        </label>
        <input
          id="capture_note"
          name="capture_note"
          placeholder="Dudas o preferencias tuyas al capturar."
          className="w-full rounded-lg border border-white/10 bg-white/[0.02] px-4 py-2 text-sm outline-none placeholder:text-ink3 focus:border-acc"
        />
      </div>

      {state.error ? (
        <p role="alert" className="font-mono text-sm text-neg">
          ▲ {state.error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-acc px-4 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Capturando…" : "Capturar y extraer"}
      </button>
    </form>
  );
}
