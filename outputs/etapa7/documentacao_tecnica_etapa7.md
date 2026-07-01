# Documentacao tecnica - Etapa 7

## Papel da etapa

Sintese de decisao. Nao le base crua: consome os CSVs auditaveis das Etapas 3-6
e a base loja x SKU da Etapa 6 (que ja traz status recalculado por universo,
giro, curva, custo e margem). Para a Loja 93, quando a Etapa 6 nao traz curva
operacional propria, a Etapa 7 aplica fallback auditavel da curva da rede
completa como guarda-corpo conservador.

## Entradas

- `outputs/etapa6/plano_compras_sku_loja.csv`: base loja x SKU nos universos
  operacionais, com `STATUS_ESTOQUE_RECALC`, `DIAS_COBERTURA_PROJ`, `ESTOQUE_PROJ`,
  `CURVA_ABC_RECEITA`, `CURVA_ABC_ORIGEM`, `CUSTO_MEDIO_ARM`, flags de margem e a decisao de compra.
- `outputs/etapa6/priorizacao_compras.csv`: faixa de prioridade da compra.
- `outputs/etapa5/candidatos_repricing.csv`: candidatos a repricing por
  loja x SKU x embalagem, com motivos de margem, desconto e preco fora da faixa.
- `outputs/etapa3/impacto_loja93.csv`: receita por universo para reconciliacao.

## Regras de classificacao

- DESCONTINUAR: `STATUS_ESTOQUE_RECALC == 'SEM VENDA'`, `ESTOQUE_PROJ > 0`,
  `CURVA_ABC_RECEITA` conhecida e `CURVA_ABC_RECEITA != 'A'`. Curva A parado vira
  `FLAG_PROTEGIDO_CAMPEAO`; curva ausente vira `FLAG_PROTEGIDO_SEM_CURVA`. Ambos
  vao para PROMOVER/revisao, nunca para descontinue automatico.
- PROMOVER: `STATUS_ESTOQUE_RECALC == 'SAUDAVEL'` com
  `DIAS_COBERTURA_PROJ > 180` (excesso/encalhe) ou campeao
  protegido.
- REPRECIFICAR: candidato da Etapa 5 em faixa ALTA/MEDIA (colapsado de embalagem
  para loja x SKU). `SINAL_MARGEM_AUDITAVEL` exige custo e margem baixa/negativa;
  `SINAL_PRECO_LISTA` aponta desconto/preco fora da faixa e nao exige custo.
- COMPRAR: `QTD_RECOMENDADA_ARM > 0` na Etapa 6.

## Acao primaria e nao dupla contagem

Um par pode disparar mais de um sinal. A `ACAO_PRIMARIA` segue a precedencia
DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR. As agregacoes financeiras usam
so `VALOR_ACAO_PRIMARIA`, garantindo que nenhum par seja contado em duas acoes.
As reconciliacoes com as etapas-fonte usam os sinais (`FLAG_*`), nao a acao
primaria, por isso os numeros de sinal batem com as Etapas 5 e 6.

## Financeiro

- Capital imobilizado (descontinuar) e valor de encalhe (promover) =
  `ESTOQUE_PROJ * CUSTO_MEDIO_ARM`, apenas com custo valido.
- Investimento de recompra (comprar) = `INVESTIMENTO_ESTIMADO` da Etapa 6.
- REPRECIFICAR nao gera valor financeiro (sinal de preco). Sem custo -> NaN
  (nao avaliado), nunca zero.

## Prioridade

Faixa ALTA/MEDIA/BAIXA por (universo x acao): top 10% por urgencia = ALTA, ate
30% = MEDIA, restante = BAIXA, calculado apenas entre pares com metrica de
urgencia conhecida. Pares sem metrica (ex.: descontinuar/promover sem custo)
ficam em BAIXA. Urgencia = score da Etapa 6 (comprar), score da Etapa 5
(repricing), capital imobilizado (descontinuar) e valor de encalhe (promover).
A fila de execucao ordena por banda de prioridade, precedencia de acao e
urgencia.

## Arquivos gerados

- `recomendacoes_sku_loja.csv`: detalhe loja x SKU com flags, acao primaria e valores.
- `recomendacoes_acao_universo.csv`: KPIs por universo x acao.
- `recomendacoes_categoria_n1.csv`: agregacao por categoria N1 x acao.
- `recomendacoes_lojas.csv`: agregacao por loja x acao.
- `reprecificacao_candidatos.csv`: candidatos a repricing por loja x SKU com sinais.
- `priorizacao_acoes.csv`: fila de execucao ranqueada com faixa ALTA/MEDIA/BAIXA.
- `validacoes_etapa7.csv`, `autoaudit_etapa7.csv`, `recomendacoes_melhoria.csv`.
- `resumo_etapa7.md`, `documentacao_tecnica_etapa7.md`.

## Riscos e falsos positivos

- Estoque projetado pode nao existir fisicamente (sem inventario/transferencias).
- Itens sazonais podem parecer parados fora de estacao.
- Valor financeiro conhecido subestima o total (so itens com custo).
- Repricing por preco/lista, com ou sem custo, nao prova margem baixa sem o sinal
  `SINAL_MARGEM_AUDITAVEL`.
