# Etapa 3 — Análise de Desempenho de Vendas

## Escopo executado

- Rankings de produtos por receita e por quantidade em unidade de armazenagem, com participação, acumulado e curva ABC por receita.
- Visões separadas para rede completa e rede física sem Loja 93.
- Agregações por `NIVEL_1`, `NIVEL_2`, `NIVEL_3`, loja, cidade/estado e mês.
- Comparação 2024 vs 2025 e decomposição da queda por categoria e por loja.

## Principais achados

- A rede completa soma R$ 482,5M em receita, 1.090.390 linhas de venda (proxy de transações) e 2.729 SKUs ativos.
- A Loja 93 responde por 31,8% da receita, mas por 2,3% das linhas de venda. A receita média por linha dela é R$ 6.160,07, sinalizando operação fora do padrão da rede física.
- Sem a Loja 93, a rede física soma R$ 329,2M e 1.065.507 linhas de venda.
- Produto líder por receita na rede completa: `467774` — COND.SPLIT 9000 COND.S3UQ09 INV. 143, com R$ 12,5M (2,6% do universo).
- Produto líder por receita na rede física: `432048` — MASSA CORRIDA PVA CORAL PLS     25KG, com R$ 9,9M (3,0% do universo).
- Produto líder por quantidade na rede completa: `429455` — TOM.CJ.1T 2P+T 10A        LGX030 POP, com 281.011 unidades de armazenagem.
- A cauda dos rankings também é auditável: `RANK_RECEITA_MENOR` e `RANK_QUANTIDADE_MENOR` identificam os produtos de menor venda. Na rede completa, a menor receita é do produto `435055` (R$ 321,08) e a menor quantidade é do produto `430480` (1,00 unidade de armazenagem).
- A curva A concentra 80,0% da receita em 522 SKUs na rede completa; sem a Loja 93, concentra 80,0% em 713 SKUs.
- Foram observadas 23 categorias de nível 1. A maior categoria na rede completa é `D - ELETROS`, com R$ 197,6M; na rede física, `D - ELETROS`, com R$ 81,4M.
- A loja de maior receita na rede completa é 93 (ALHANDRA-PB), com R$ 153,3M. Sem a Loja 93, a líder é 3 (SALVADOR-BA), com R$ 62,6M.
- A receita caiu -54,2% em 2025 vs 2024 na rede completa e -47,6% na rede física sem Loja 93.
- O maior mês por receita na rede completa foi 2024-11, com R$ 47,2M; o menor foi 2025-12, com R$ 3,9M.
- A maior contribuição bruta para a queda de receita em 2025, por categoria na rede completa, veio de `D - ELETROS` (R$ -92,6M). Por loja, veio da loja 93 (ALHANDRA-PB), com R$ -76,4M.

## Limitações e cuidados metodológicos

- A análise é descritiva: variações e picos não são atribuídos a preço, demanda, ruptura ou captura de dados sem evidência adicional.
- `TRANSACOES` representa linhas de venda, não cupons únicos. A base processada não possui id de cupom, pedido ou nota. Isto está documentado como limitação relevante e recomendação de melhoria em `notas_metodologicas.csv` e `recomendacoes_melhoria.csv`.
- Ticket médio foi mantido como proxy de receita por linha de venda; preço médio foi calculado como receita por unidade de armazenagem.
- A Loja 93 é operação B2B/atacado e distorce médias, rankings e sazonalidade. Por isso todos os outputs trazem `UNIVERSO`.
- A queda de 2025 é comparada contra 2024 completo, usando apenas datas presentes em `vendas_tratadas.parquet`.
- Recomendações de melhoria foram registradas para pontos que limitam a leitura profissional dos dados: id de transação, canal formal da Loja 93, movimentações de estoque, variáveis causais da queda e dicionário de métricas.

## Validações

- 60 validações executadas, todas com status `OK`.
- Somas de receita, quantidade e linhas de venda dos rankings, categorias, lojas e meses batem com os totais de cada universo.
- As decomposições de queda por categoria e por loja fecham com o delta anual 2025 vs 2024.
- A soma Loja 93 + rede física sem Loja 93 fecha com a rede completa.
- As dimensões críticas (`NIVEL_1`, `NIVEL_2`, `NIVEL_3`, cidade e estado) não possuem nulos na base processada usada na análise.

## Como executar

```bash
cd notebooks
python etapa3_desempenho_vendas.py
```

Os arquivos auditáveis são gravados em `outputs/etapa3/`.
