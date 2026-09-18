# Validação externa da biblioteca v1

**Validação concluída pelo agente externo em 18/09/2026.** `validation_results.v1.json` registra 241 testes aprovados, zero falhas, zero pulados, 26 seeds validados e quatro checagens positivas da simulação de três cenários. Os arquivos gerados foram revisados sem repetir a execução.

No Gemini/Antigravity, abrir a raiz `C:\Arquivos\GitHub\marin-telegram-bot` e executar:

```powershell
& .\venv\Scripts\python.exe scripts\story_datasets\run_external_validation.py
```

O comando valida a biblioteca, roda a suíte com banco SQLite descartável e gera a simulação de 1.095 dias para `baseline`, `realistic_context` e `contextual_stress`. O resumo fica em `validation_results.v1.json`; os resultados detalhados ficam em `simulation_report.v1.json`.

O resumo registrou `status: passed`. No cenário realista, houve sinais observados em 555 dos 1.095 dias, entre os extremos de 0 e 1.095. Os três cenários tiveram 120 eventos, ~89,0% de dias sem evento novo (dias banais) e nenhum evento grave. O comando acima fica disponível para futuras mudanças; estes resultados valem para a calibração de cadência da release 3.6.2 revisada aqui.
