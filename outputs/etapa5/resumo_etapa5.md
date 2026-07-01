# Etapa 5 - Analise de precificacao e variacao de margem

## Glossario rapido (ler antes dos numeros)

- **Preco praticado (por unid. de armazenagem):** `receita / quantidade em
  unidade de armazenagem`. E o preco medio efetivamente realizado, ja na mesma
  unidade do custo.
- **Custo medio (CMV unitario):** media ponderada do preco de compra do SKU no
  periodo, convertido para a unidade de armazenagem
  (`preco de compra / conversao de compra`). So existe para SKUs com compra de
  preco valido.
- **Margem bruta (R$):** preco praticado - custo medio (mesma unidade).
- **Margem bruta (%):** margem R$ / preco praticado.
- **Markup:** preco praticado / custo medio (quantas vezes o custo o preco cobre).
- **Preco de lista:** preco de tabela cadastrado por loja x produto x embalagem.
- **Desconto efetivo (%):** `(preco de lista - preco praticado) / preco de lista`,
  sempre dentro da MESMA embalagem.
- **Dispersao de preco:** coeficiente de variacao do preco praticado do mesmo
  SKU entre lojas, por embalagem.
- **Repricing:** revisao de preco de itens com margem baixa/negativa, desconto
  fora do padrao ou preco fora da faixa da rede.

## Cobertura de custo (leia antes de generalizar a margem)

Margem realizada **so existe para os SKUs com custo de compra registrado**. Esse
e o analogo do achado das Etapas 1/2 ("88% vendem sem compra registrada"):

- 329 SKUs tem compra registrada no periodo, mas apenas
  261 tem preco de compra valido (9,5% das linhas de
  compra vem sem preco e sao excluidas do custo), de 2.729 SKUs vendidos.
- Esses SKUs respondem por R$ 79,1M
  (16,4% da receita) na rede completa e
  R$ 49,9M (15,2%)
  na rede fisica. Na Loja 93/B2B, a cobertura auditavel e
  R$ 19,7M (12,8%).
- Os demais SKUs **nao recebem margem por ausencia de dado, nunca por erro**.
  A margem deste relatorio vale para esse subconjunto, nao para a rede toda.

## Principais achados

- Margem bruta % media ponderada (apenas itens com custo): rede completa
  47,6% (markup 1.91x); rede
  fisica 49,8% (markup 1.99x).
- Categoria N1 de maior margem na rede fisica (cobertura de custo >=10%):
  `C - PISOS E REVESTIMENTOS` (56,1%, cobertura
  21,1%); de menor margem:
  `D - ELETROS` (42,8%, cobertura
  13,3%).
- Alerta: a categoria `B - UTILIDADES DOMESTICAS` aparece com margem NEGATIVA (-15,4%) no subconjunto com custo (cobertura de 2,7% da receita) - itens de baixo giro vendidos abaixo do custo, candidatos a repricing/descontinuacao.

- Entre os itens de alta receita (curva A) com custo na rede fisica, a menor
  margem e do SKU 447868 (PRATO RASO PORC.28CM    PEIXES 80000),
  com -52,8%; a maior e do SKU
  462811 (DISJ.BIPO.C DIN  16A       GII-C016A), com
  69,9%.
- 7 SKUs
  da rede fisica vendem com margem negativa (preco < custo), concentrados em
  utilidades domesticas/loucas de baixo giro - sinalizados, nao silenciados.
- Desconto efetivo medio ponderado na rede fisica: 17,4%.
  2.079 combinacoes loja x produto x embalagem vendem ACIMA da
  lista (desconto negativo), sinal de lista possivelmente desatualizada.
- Dispersao de preco entre lojas (rede fisica, embalagem 0): apenas
  46 SKUs com CV>30% - bem abaixo da leitura ingenua de
  2.619 SKUs com amplitude de preco bruto >30% (metrica diferente:
  amplitude do preco bruto entre linhas, misturando embalagem e atacado).
- Candidatos a repricing na rede fisica: 3.260 combinacoes
  loja x produto x embalagem com pelo menos um sinal (margem baixa/negativa,
  desconto alto ou preco fora da faixa). Dois rankings convivem: **risco**
  (nº de sinais + receita, para triagem) e **impacto** (receita x magnitude do
  sinal, para a fila comercial). O maior candidato por impacto na rede fisica e o
  SKU 480680 (REFRIG. 2P 391L FF RT38DG61  IX MBIV) na loja
  3, com R$ 1.723.994,28 de receita
  exposta (impacto estimado R$ 753.857,57),
  que no ranking de risco cai para o rank 226.

## Revisao de qualidade (autoaudit antes/depois)

- **Margens absurdas por erro de unidade (preco em caixa x custo).** No nivel da linha, vendas em caixa (EMBALAGEM=1, conversao de venda ate 100) chegariam a dezenas de vezes o custo unitario se lidas por unidade de venda; 10 dos SKUs com custo vendem em caixa/conversao>1. -> Apos normalizar, os 261 SKUs com custo tem markup entre 0.65x e 4.76x e margem entre -52,8% e 79,0%.
  (0 de 261 SKUs com markup acima de 20x (faixa sanitaria); a normalizacao funciona como salvaguarda contra o outlier de caixa.)
- **Custo de SKU sem compra vazando para a margem.** 2468 SKUs (90,4%) e R$ 403,4M (83,6% da receita) poderiam receber margem fabricada. -> 261 SKUs com custo real entram na margem; 2468 ficam corretamente sem margem.
- **Mistura de embalagem (e atacado) na dispersao de preco.** 2619 SKUs com amplitude de preco bruto >30% (todas as lojas, embalagens misturadas). -> 827 SKUs com amplitude >30% pela mesma metrica na rede fisica por embalagem; pelo CV, apenas 46 SKUs com CV>30%.
  (A maior parte da 'variacao de preco' era mistura de embalagem/atacado: cai de 2619 para 827 (46 pelo CV).)

## Limitacoes e cuidados

- Margem realizada existe so para os ~261 SKUs com custo
  (~16,4% da receita); o restante fica sem
  margem por ausencia de dado.
- O custo e a media ponderada do periodo, sem camadas de custo (PEPS) nem custo
  de reposicao atual.
- O preco de lista pode nao refletir promocoes pontuais; o desconto efetivo e uma
  aproximacao.
- A Loja 93 e atacado/B2B: margens nao comparaveis ao varejo, por isso segregada.
  A etapa gera um universo explicito `LOJA_93_ATACADO_B2B` para auditar esse canal.

## Validacoes

- 21 validacoes executadas, todas com status
  `OK`.
- Receita por universo, categoria e loja reconcilia com a Etapa 3, incluindo
  `LOJA_93_ATACADO_B2B`.
- Nenhuma margem % calculada sobre custo ausente; margens negativas sinalizadas.
- Preco praticado e de lista comparados apenas dentro da mesma embalagem.

## Como executar

```bash
.venv/Scripts/python.exe notebooks/etapa5_precificacao_margem.py
```

Os arquivos auditaveis sao gravados em `outputs/etapa5/`.
