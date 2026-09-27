---
name: frente-imagens
description: Frente "imagens" da Marina — poses que o Patrick manda (print/arquivo/link do Civitai) para virar pose do catálogo, resgate do prompt de uma imagem, texto dos prompts de foto (diretor, regras do Krea 2, roupa, cômodo, zoom) e o motor (Civitai, LoRA marinaX, pilhas de LoRA, sliders, custo em Buzz). Use quando ele mandar pose, imagem de referência, pedir prompt, reclamar de uma foto dela ou falar de LoRA/Civitai/Buzz.
---

# Frente: imagens (poses, prompts, motor)

As três partes são uma cadeia: **pose de referência → prompt no jeito da casa → motor que gera**. Mexer numa
costuma pedir conferir as outras.

## Regras do Patrick (não negociáveis)
- **Nunca mostrar imagem adulta no chat** (nem a que ele mandou, nem a gerada). Pode ler/analisar; mostra só texto.
- **Buzz custa dinheiro:** ~18–27 por foto. Teste só com motivo e com o OK dele, 1–2 fotos por decisão. O que já foi
  aprovado se corrige por prompt, sem re-testar.
- Visual novo (corte, cor, roupa nova): 1–2 fotos com o LoRA antes de decidir; script de teste sempre com roupa.
- Imagem que ele manda fica em `references/` (fora do git). **Nunca commitar `references/`.**
- A chave do Civitai vazou em 24/09; enquanto ele não trocar, não imprimir nada do `.env` (só nomes de chave).

## Pose que ele manda → pose do catálogo
1. **Resgate do prompt:** a API do Civitai não devolve mais o prompt das imagens (testado). Tente, nesta ordem:
   metadado do arquivo (PNG `parameters`/`prompt`/`workflow` do ComfyUI, EXIF `UserComment` — com PIL), texto que ele
   colar da página do site, e por último descrever a imagem você mesmo.
2. **Reescreva no jeito da casa** (`photo_director.Pose`): `id`, `pt` (como ela descreveria), `rooms` (cômodos do
   apê canônico ou `("fora",)`), `levels` (0 dia a dia · 1 provocante vestida · 2 lingerie · 3 nua · 4 explícita),
   `zoom`, `framing` (selfie | mirror | timer | friend — ela mora sozinha: corpo inteiro em casa é timer),
   `action` em inglês concreto (posição, mãos, olhar), `outfit` se a pose exige, `beats` se é cena explícita.
3. Lições do Krea 2 (PLANO_VOZ, "Fotos pelo Civitai"): com CFG 1 **negação vira pedido** (nunca "sem X"); cor e
   posição concretas obedecem mais que adjetivo; o começo do prompt pesa mais; citar o celular desenha o celular.
4. Mostre a ele a pose em português (o `pt` e onde ela cabe) antes de gastar Buzz testando.

## Onde fica
- **Catálogo e diretor:** `photo_director.py` (`POSES`, `WARDROBE`, sessão com seed,
  nível por momento `CAP`, beats da cena explícita); regras do diretor em `visual_profile.py` (`KREA2_DIRECTOR_RULES`).
- **Motor:** `civitai_images.py` (`build_workflow_krea2`, `select_loras_krea2`, `conditional_loras`, `weight_slider`
  ligado ao peso do D1, pós-processo de saturação/corte). `.env`: `IMAGE_ENGINE`, `CIVITAI_ECOSYSTEM`, `CIVITAI_LORA_*`.
- **Quando ela manda foto:** `promessa_foto.py` e o bloco `[FOTO]` — isso é comportamento de chat, **fica na frente
  da voz** (PLANO_VOZ 15).
- Status que muda a foto: `unhas.py`, `cabelo.py` (a cor/penteado de agora entram em toda foto), `apartamento.py`.
- **Decisões e histórico:** `PLANO_VOZ_MARINA_V371.md`, seção "Fotos pelo Civitai" (pilha oficial, reprovados,
  lições, custo) e "Fase C.1b".

## Comece assim
Leia "6. Imagens" em `FRENTES_MARINA.md`. Fechar: testes, relatórios no mesmo commit, deploy, `passagem-de-bastao`.
