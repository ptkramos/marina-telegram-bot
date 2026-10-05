-- Lovense, passo 3 (05/10): o que ela já sentiu na sessão, pro bot só criar turno quando ela sente diferença
-- (ligou, parou, salto de nível, ritmo novo) ou depois de um tempo no mesmo ritmo (o tesão acumulando).
-- JSON: {em, motivo, b: {brinquedo: [nivel, modo, padrao]}, ritmo_desde}.
ALTER TABLE lovense_sessoes ADD COLUMN sentido_json TEXT;
