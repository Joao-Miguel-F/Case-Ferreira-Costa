# Documentacao tecnica - Etapa 5

Guia de reproducao e continuacao da analise de precificacao e margem.

## O que foi implementado

A Etapa 5 calcula margem bruta realizada (R$ e %), markup, custo medio, desconto
efetivo vs preco de lista e dispersao de preco entre lojas. O script canonico e
`notebooks/etapa5_precificacao_margem.py`.

## Unidades (ponto critico)

Tudo e comparado na unidade de ARMAZENAGEM:

- Preco praticado por unid. de armazenagem = `RECEITA / QTD_ARMAZENAGEM`.
- Custo medio por unid. de armazenagem = `PRECO_UNIT_UNIDADE_COMPRA / CONVERSAO_COMPRA_ARMAZENAGEM`,
  ponderado pela quantidade comprada. A divisao pela conversao e obrigatoria:
  sem ela, itens comprados em caixa teriam custo inflado e margem absurda.
- O desconto efetivo compara preco praticado e preco de lista DENTRO da mesma
  embalagem (mesma unidade de venda), nunca cruzando caixa com unidade.

## Entradas usadas

- `data/processed/vendas_tratadas.parquet` (loader `load_vendas`): receita,
  quantidade vendida, quantidade em armazenagem, embalagem, categoria, loja.
- `data/processed/compras_tratadas.parquet` (loader `load_compras`): preco e
  quantidade de compra; 9,5% das linhas sem preco sao excluidas do custo.
- `data/processed/dim_produto_tratada.parquet` (loader `load_dim_produto`):
  `CONVERSAO_COMPRA_ARMAZENAGEM` por SKU.
- `data/processed/dim_precos_tratada.parquet` (loader `load_dim_precos`): preco
  de lista por loja x produto x embalagem e desconto adicional de catalogo.
- `outputs/etapa3/impacto_loja93.csv`, `desempenho_categorias_n1.csv`,
  `desempenho_lojas.csv`, `ranking_produtos_receita.csv`: reconciliacao de
  receita e curva ABC ja auditadas na Etapa 3.

## Principais formulas

- Preco praticado (arm.) = receita / qtd. em armazenagem.
- Custo medio (arm.) = soma(preco compra x qtd) / soma(qtd) / conversao de compra.
- Margem bruta R$ = preco praticado - custo medio.
- Margem bruta % = margem R$ / preco praticado.
- Markup = preco praticado / custo medio.
- Margem agregada (categoria/loja) = (receita com custo - CMV) / receita com custo,
  ponderada por quantidade (CMV = soma de custo medio x qtd em armazenagem).
- Desconto efetivo % = (preco de lista - preco praticado da embalagem) / preco de lista.
- Dispersao = desvio padrao / media do preco praticado por unid. de armazenagem
  entre lojas, por SKU x embalagem.

## Separacao da Loja 93

Saidas agregadas trazem `UNIVERSO` com `REDE_COMPLETA`, `REDE_FISICA_SEM_LOJA93`
e `LOJA_93_ATACADO_B2B`. O custo de cada universo usa apenas as compras das
lojas do universo. Candidatos e dispersao da rede fisica nao incluem a Loja 93
(atacado/B2B), e o canal B2B fica auditavel em universo proprio.

## Arquivos gerados

- `margem_produtos.csv`: margem por SKU (somente com custo), com cobertura e ABC.
- `margem_categorias_n1.csv` / `_n2.csv` / `_n3.csv`: margem agregada por categoria.
- `margem_lojas.csv`: margem e preco por loja.
- `margem_total_universo.csv`: margem consolidada por universo (fonte dos KPIs do resumo/dashboard).
- `precificacao_desconto.csv`: preco praticado vs lista e desconto efetivo, por embalagem.
- `dispersao_preco_lojas.csv`: dispersao por SKU entre lojas, por embalagem.
- `candidatos_repricing.csv`: ranking de oportunidades de repricing.
- `recomendacoes_melhoria.csv`: melhorias de dados/modelagem/processo.
- `validacoes_etapa5.csv`: reconciliacoes numericas.
- `autoaudit_etapa5.csv`: revisao critica antes/depois.
- `resumo_etapa5.md`: resumo executivo, glossario e limitacoes.

## Como revisar ou continuar

1. Rode `.venv/Scripts/python.exe notebooks/etapa5_precificacao_margem.py`.
2. Confira `outputs/etapa5/validacoes_etapa5.csv`; qualquer `FALHA` bloqueia conclusoes.
3. Para estender a margem alem dos ~16% de receita coberta, e necessario custo por
   SKU para os itens sem compra registrada (ver `recomendacoes_melhoria.csv`).
4. Reexecute `python scripts/gerar_dashboard.py` para atualizar dashboard e dicionario.

## Limitacoes que nao foram resolvidas aqui

- Sem custo para ~84% da receita, a margem cobre so o subconjunto auditavel.
- Sem camadas de custo (PEPS) nem custo de reposicao, a margem e historica media.
- Sem vigencia/promocao no preco de lista, o desconto efetivo e aproximado.
- A Loja 93 precisa de uma dimensao formal de canal para substituir a regra por codigo.
