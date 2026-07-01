# data/raw/ — bases brutas do case

Esta pasta guarda as bases **originais** fornecidas com o case. A maioria é pequena
e está versionada no repositório. **Uma exceção** não é versionada por tamanho:

## Arquivo NÃO versionado (colocar manualmente)

| Arquivo | Tamanho | Onde obter |
|---|---|---|
| `fato_vendas_1.csv` | ~59 MB | Entregue à parte junto com o case (base de vendas de 24 meses). |

O `.gitignore` ignora `data/raw/fato_vendas_1.csv` para manter o repositório leve.
Coloque o arquivo aqui, com este nome exato, **antes de rodar a Etapa 1**.

## O que precisa deste arquivo

- **Somente a Etapa 1** (`notebooks/etapa1_entendimento_dados.py`) lê `fato_vendas_1.csv`.
  Sem o arquivo, a Etapa 1 falha com uma mensagem clara apontando para cá.
- **As Etapas 2 a 7 NÃO precisam dele:** elas partem dos Parquets já versionados em
  `data/processed/*.parquet`, gerados pela Etapa 1. Ou seja, é possível reproduzir toda
  a análise (Etapas 2–7 + dashboard) sem o CSV bruto de vendas.

## Bases versionadas nesta pasta

`fato_compras_2.csv`, `fato_estoque_inicial_2.csv`, `dim_produto_1.csv`,
`dimensao_lojas_2.csv`, `dimensao_precos_2.csv`, `dimensao_voltagem_2.csv`,
`Descr_unidades_medida_2.csv` e `Descritivo_bases_de_dados_2.xlsx`.
