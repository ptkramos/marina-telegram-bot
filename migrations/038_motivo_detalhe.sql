-- Redesenho dos Bastidores, passo 5 (06/10): o motivo de cada sentimento vira frase inteira (a coluna cause, que o
-- prompt dela lê) e o detalhe vai à parte, com o tipo que dá o ícone na tela: JSON [["valor", "De R$ 200"], ...].
ALTER TABLE emotion_episodes ADD COLUMN detalhe_json TEXT;
