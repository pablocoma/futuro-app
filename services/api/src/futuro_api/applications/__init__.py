"""El dossier mínimo: qué variante de CV confirmó Pablo para una oferta.

`docs/OFFER_DATA_CONTRACT.md` (repositorio privado `Futuro`) ya reserva el
nombre `applications` para la candidatura completa —con `status`, `channel`,
`submitted_at`, `follow_up_at`, `outcome` e interacciones—. Esta rebanada
(M3) solo escribe la mitad que no depende de seguimiento: qué variante se
confirmó y qué PDF exacto se sirvió. El resto es Fase 3, y entra con un
`ALTER TABLE` aditivo, no con un renombrado.
"""
