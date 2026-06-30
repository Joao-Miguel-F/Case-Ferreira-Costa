# Documentacao tecnica - Etapa 6

## Entradas

- `data/processed/cobertura_estoque.parquet`: snapshot dez/2025 no grao loja x SKU, com estoque projetado, status, dias de cobertura e receita historica.
- `data/processed/vendas_tratadas.parquet`: recalculo da demanda media mensal por par loja x SKU, incluindo Loja 93 em escopo proprio.
- `outputs/etapa3/ranking_produtos_receita.csv` e `impacto_loja93.csv`: curva ABC e reconciliacao de receita por universo.
- `outputs/etapa4/cobertura_categorias_n1.csv`: reconciliacao de receita por categoria na rede fisica.
- `outputs/etapa5/margem_produtos.csv`: custo medio, margem e flags apenas para SKUs com custo valido.

## Granularidade

O arquivo principal `plano_compras_sku_loja.csv` esta no grao loja x SKU, com
`UNIVERSO_OPERACIONAL` separando `REDE_FISICA_SEM_LOJA93` e
`LOJA_93_ATACADO_B2B`. Os agregados tambem trazem `REDE_COMPLETA` como soma
reconciliada desses dois escopos.

## Formulas

- Demanda 90 dias = `VENDA_MEDIA_MES_PROJECAO * 3`.
- Estoque utilizavel = `max(ESTOQUE_PROJ, 0)`.
- Necessidade bruta = `max(demanda_90d - estoque_utilizavel, 0)`.
- Quantidade recomendada = teto da necessidade bruta, somente para status
  `EM RUPTURA`, `CRITICO` ou `ATENCAO` e com demanda observada.
- Investimento estimado = `QTD_RECOMENDADA_ARM * CUSTO_MEDIO_ARM`, somente
  quando o custo medio existe na Etapa 5 para o mesmo universo.

## Premissas

- Horizonte de compra: 90 dias.
- A demanda usa media dos meses com venda. Ausencia de dado nao e imputada como zero para comprar.
- Estoque negativo nao aumenta a compra; e tratado como zero utilizavel.
- Margem e investimento nao sao calculados para itens sem custo valido.
- Loja 93 e canal B2B/atacado e nao deve ser misturada com rede fisica.

## Validacoes

`validacoes_etapa6.csv` cobre reconciliacao de receita com Etapa 3, soma dos
universos, fechamento de agregados por categoria/loja, restricao de compras a
status elegiveis e garantia de que investimento nao foi imputado para custo
ausente.

## Arquivos gerados

- `plano_compras_sku_loja.csv`: plano operacional detalhado.
- `plano_compras_total_universo.csv`: KPIs por universo.
- `plano_compras_categorias_n1.csv`: agregacao por categoria N1.
- `plano_compras_lojas.csv`: agregacao por loja.
- `priorizacao_compras.csv`: fila de compra ranqueada.
- `validacoes_etapa6.csv`: reconciliacoes numericas e status OK/FALHA.
- `autoaudit_etapa6.csv`: riscos de interpretacao e controles aplicados.
- `recomendacoes_melhoria.csv`: proximas melhorias de dados/processo.
- `resumo_etapa6.md`: leitura executiva.

## Riscos e falsos positivos

- Ruptura projetada pode refletir transferencia/ajuste ausente, nao prateleira vazia.
- Demanda historica pode nao representar pedidos B2B futuros.
- Quantidade recomendada sem custo nao tem investimento estimado.
- Itens de margem negativa exigem validacao comercial antes de compra.
