# Case Técnico — Análise de Desempenho de Produtos no Varejo

Análise completa de 24 meses de dados de uma rede de varejo de materiais de construção com 11 lojas em 5 estados do Nordeste (PE, BA, SE, PB, RN).

---

## Estrutura do repositório

```
.
├── data/
│   ├── raw/                        # Bases originais fornecidas (CSV / XLSX)
│   └── processed/                  # Bases tratadas em Parquet (geradas pelo código)
│
├── notebooks/                      # Análises por etapa
│   ├── 01_etapa1_entendimento_dados.ipynb   # 📘 notebook executado (entregável de leitura)
│   ├── 02_etapa2_estoque_projetado.ipynb    # 📘 notebook executado (com validações antes/depois)
│   ├── 03_etapa3_desempenho_vendas.ipynb    # 📘 notebook executado (rankings, ABC e sazonalidade)
│   ├── 04_etapa4_cobertura_categoria_loja.ipynb # 📘 notebook executado (cobertura por categoria/loja)
│   ├── 05_etapa5_precificacao_margem.ipynb  # 📘 notebook executado (margem, desconto e dispersão de preço)
│   ├── 06_etapa6_projecao_compras.ipynb     # 📘 notebook executado (projeção de compras)
│   ├── 07_etapa7_recomendacoes_finais.ipynb # 📘 notebook executado (recomendações finais)
│   ├── etapa1_entendimento_dados.py         # script-fonte de referência
│   ├── etapa2_estoque_projetado.py          # script-fonte de referência (corrigido)
│   ├── etapa3_desempenho_vendas.py          # script-fonte de referência
│   ├── etapa4_cobertura_categoria_loja.py   # script-fonte de referência
│   ├── etapa5_precificacao_margem.py        # script-fonte de referência
│   ├── etapa6_projecao_compras.py           # script-fonte de referência
│   └── etapa7_recomendacoes_finais.py       # script-fonte de referência
│
├── src/
│   └── utils.py                    # Funções e constantes compartilhadas
│
├── scripts/
│   └── gerar_dashboard.py          # Gera o dashboard HTML a partir dos CSVs reais
│
├── outputs/
│   ├── etapa1/                     # Decisões de tratamento, dicionário de dados
│   ├── etapa2/                     # Cobertura de estoque, investigação de outliers de preço
│   ├── etapa3/                     # Rankings, ABC, categorias, lojas e sazonalidade
│   ├── etapa4/                     # Cobertura por categoria/loja e priorização de reposição
│   ├── etapa5/                     # Margem, preço de lista/desconto, dispersão e candidatos a repricing
│   ├── etapa6/                     # Projeção de compras, priorização e validações
│   ├── etapa7/                     # Recomendações finais (promover/descontinuar/reprecificar/comprar) e fila priorizada
│   └── relatorio_qualidade_dados.html       # 📊 dashboard executivo (abre no navegador)
│
├── requirements.txt
└── README.md
```

---

## Como executar

> **Insumo bruto da Etapa 1:** a Etapa 1 lê `data/raw/fato_vendas_1.csv` (~59 MB), que **não é
> versionado** por tamanho (ver [`data/raw/README.md`](data/raw/README.md)). Coloque esse arquivo
> (entregue à parte com o case) em `data/raw/` antes de rodar a Etapa 1. **As Etapas 2–7 não
> precisam dele** — elas partem dos Parquets já versionados em `data/processed/`, então é possível
> reproduzir toda a análise a partir do passo 3 sem o CSV bruto de vendas.

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Rodar Etapa 1 (limpeza e tratamento — gera os Parquets em data/processed/)
#    Requer data/raw/fato_vendas_1.csv (ver nota acima). Pule este passo para
#    reproduzir a partir dos Parquets já versionados.
cd notebooks
python etapa1_entendimento_dados.py

# 3. Rodar Etapa 2 (estoque projetado e análise de cobertura — já com as correções)
python etapa2_estoque_projetado.py

# 4. Rodar Etapa 3 (desempenho de vendas, rankings, ABC e sazonalidade)
python etapa3_desempenho_vendas.py

# 5. Rodar Etapa 4 (cobertura por categoria/loja e priorização)
python etapa4_cobertura_categoria_loja.py

# 6. Rodar Etapa 5 (precificação, margem, desconto e dispersão de preço)
python etapa5_precificacao_margem.py

# 7. Rodar Etapa 6 (projeção de compras para 90 dias)
python etapa6_projecao_compras.py

# 8. Rodar Etapa 7 (recomendações finais e plano de execução comercial)
python etapa7_recomendacoes_finais.py

# 9. (opcional) Reexecutar os notebooks de ponta a ponta
jupyter nbconvert --to notebook --execute --inplace 01_etapa1_entendimento_dados.ipynb
jupyter nbconvert --to notebook --execute --inplace 02_etapa2_estoque_projetado.ipynb
jupyter nbconvert --to notebook --execute --inplace 03_etapa3_desempenho_vendas.ipynb
jupyter nbconvert --to notebook --execute --inplace 04_etapa4_cobertura_categoria_loja.ipynb
jupyter nbconvert --to notebook --execute --inplace 05_etapa5_precificacao_margem.ipynb
jupyter nbconvert --to notebook --execute --inplace 06_etapa6_projecao_compras.ipynb
jupyter nbconvert --to notebook --execute --inplace 07_etapa7_recomendacoes_finais.ipynb

# 10. (opcional) Regenerar o dashboard HTML a partir dos CSVs
cd ..
python scripts/gerar_dashboard.py
```

> **Nota:** os arquivos `data/processed/*.parquet` já estão incluídos no repositório para facilitar a
> reprodução das Etapas 2–7 sem precisar do CSV bruto de vendas nem rodar a Etapa 1. A Etapa 1 só é
> necessária para regerar os Parquets a partir do dado bruto — ver a nota sobre `data/raw/fato_vendas_1.csv`.

### Abrir os entregáveis de leitura

- **Dashboard executivo:** basta abrir `outputs/relatorio_qualidade_dados.html` no navegador
  (duplo-clique). É autocontido — não precisa de servidor nem instalação. O dashboard consolida
  qualidade de dados, estoque projetado, desempenho de vendas, cobertura por categoria/loja,
  precificação e margem, projeção de compras e recomendações finais de execução comercial. O
  dicionário exibido no dashboard também é salvo em `outputs/dicionario_dados_projeto.csv` e cobre
  bases tratadas e principais outputs analíticos.
- **Notebooks executados:** `notebooks/01_etapa1_entendimento_dados.ipynb`,
  `notebooks/02_etapa2_estoque_projetado.ipynb`,
  `notebooks/03_etapa3_desempenho_vendas.ipynb`,
  `notebooks/04_etapa4_cobertura_categoria_loja.ipynb`,
  `notebooks/05_etapa5_precificacao_margem.ipynb`,
  `notebooks/06_etapa6_projecao_compras.ipynb` e
  `notebooks/07_etapa7_recomendacoes_finais.ipynb` já trazem todos os outputs salvos — podem ser
  lidos direto no GitHub, VS Code ou Jupyter, sem rodar nada.

---

## Contexto do negócio

| Dimensão | Dado |
|---|---|
| Período analisado | jan/2024 – dez/2025 (24 meses) |
| Receita total | <!--kpi:e1.receita_total:milhao-->R$ 482,5M<!--/kpi--> |
| Linhas de venda (proxy de transações) | <!--kpi:e1.transacoes:int-->1.090.390<!--/kpi--> |
| SKUs ativos | <!--kpi:e1.skus_ativos:int-->2.729<!--/kpi--> |
| Lojas | 11 (5 estados) |
| Categorias (Nível 1) | 23 |

**Ponto de atenção — Loja 93 (Alhandra-PB):** opera como canal B2B/atacado com receita média por linha de venda ~20× superior à rede e 76% da receita em Eletros. Todas as análises são apresentadas com e sem esta unidade para não distorcer os indicadores da rede física.

---

## Etapas realizadas

### Etapa 1 — Entendimento e Limpeza

- Inspeção de 8 bases (fatos + dimensões)
- 10 decisões de tratamento documentadas com justificativa analítica
- Integridade referencial 100% entre produtos, vendas e lojas
- Hipóteses de negócio levantadas antes das análises formais
- Bases tratadas exportadas em Parquet com colunas derivadas (RECEITA, QTD_ARMAZENAGEM, FLAG_LOJA93)

**Achados principais:**
- 80% da receita (R$385M) vem de SKUs sem compra registrada no período → estoque inicial é o principal ativo operacional
- Loja 93 representa <!--kpi:e3.loja93.receita_pct:pct-->31,8%<!--/kpi--> da receita com apenas 12% dos SKUs → operação B2B/atacado
- <!--kpi:e5.naive.amplitude:int-->2.619<!--/kpi--> SKUs com amplitude de preço bruto >30% → leitura ingênua de possível inconsistência de precificação (refinada na Etapa 5 para **<!--kpi:e5.dispersao.cv_alta_fisica:int-->46<!--/kpi--> SKUs** por CV, ao separar embalagem e atacado)

### Etapa 2 — Estoque Projetado e Cobertura

Metodologia: `Estoque_t = Estoque_inicial + ΣEntradas_até_t - ΣSaídas_até_t`

Todas as quantidades convertidas para **unidade de armazenagem** antes da operação.

Valores **pós-correção** (ver seção [Revisão de qualidade e correções](#revisão-de-qualidade-e-correções)):

| Status | Pares loja×produto | % |
|---|---|---|
| Em ruptura (estoque ≤ 0) | <!--kpi:e2.ruptura.pares:int-->26.140<!--/kpi--> | <!--kpi:e2.ruptura.pct:pct-->91,0%<!--/kpi--> |
| Crítico (1–30 dias de cobertura) | <!--kpi:e2.status.critico:int-->573<!--/kpi--> | 2,0% |
| Atenção (31–90 dias) | <!--kpi:e2.status.atencao:int-->391<!--/kpi--> | 1,4% |
| Saudável (>90 dias) | <!--kpi:e2.status.saudavel:int-->955<!--/kpi--> | 3,3% |
| Sem venda (capital imobilizado) | <!--kpi:e2.status.sem_venda:int-->662<!--/kpi--> | 2,3% |
| **Total** | **<!--kpi:e2.cobertura.total_pares:int-->28.721<!--/kpi-->** | **100%** |

**Interpretação:** o alto percentual de ruptura é consistente com a descoberta da Etapa 1 — a rede opera principalmente do estoque inicial, sem reposição registrada em ~88% dos SKUs. Após a correção, o topo do ranking de reposição passou a incluir os pares de maior receita da base (Eletros da loja 93), antes invisíveis. O foco da Etapa 6 (plano de compras) deve priorizar os pares **em ruptura/crítico com maior receita histórica**.

### Etapa 3 — Análise de Desempenho de Vendas

Foram gerados rankings por receita e quantidade em unidade de armazenagem, curva ABC por receita, agregações por hierarquia de produto (`NIVEL_1`, `NIVEL_2`, `NIVEL_3`), loja, cidade/estado e evolução mensal. Todas as saídas têm visão de **rede completa** e **rede física sem Loja 93**.

**Achados principais:**
- Rede completa: <!--kpi:e3.receita.rede_completa:milhao-->R$ 482,5M<!--/kpi-->, <!--kpi:e3.transacoes.rede_completa:int-->1.090.390<!--/kpi--> linhas de venda (proxy de transações) e <!--kpi:e3.skus_ativos.rede_completa:int-->2.729<!--/kpi--> SKUs ativos.
- Loja 93: <!--kpi:e3.loja93.receita_pct:pct-->31,8%<!--/kpi--> da receita e <!--kpi:e3.loja93.transacoes_pct:pct-->2,3%<!--/kpi--> das linhas de venda, com receita média de <!--kpi:e3.loja93.receita_media_linha:reais-->R$ 6.160,07<!--/kpi--> por linha.
- Rede física sem Loja 93: <!--kpi:e3.receita.rede_fisica:milhao-->R$ 329,2M<!--/kpi--> e <!--kpi:e3.transacoes.rede_fisica:int-->1.065.507<!--/kpi--> linhas de venda.
- Produto líder por receita na rede completa: `467774` — COND.SPLIT 9000 COND.S3UQ09 INV. 143, com R$ 12,5M.
- Produto líder por receita na rede física: `432048` — MASSA CORRIDA PVA CORAL PLS 25KG, com R$ 9,9M.
- Curva A: <!--kpi:e3.curva_a.completa:int-->522<!--/kpi--> SKUs concentram <!--kpi:e3.curva_a.pct_completa:pct-->80,0%<!--/kpi--> da receita na rede completa; sem Loja 93, são <!--kpi:e3.curva_a.fisica:int-->713<!--/kpi--> SKUs.
- **Queda de 2025 — hipótese a confirmar, não achado fechado.** A receita recua <!--kpi:e3.queda_2025.completa:pct_abs-->54,2%<!--/kpi--> em 2025 vs 2024 na rede completa e <!--kpi:e3.queda_2025.fisica:pct_abs-->47,6%<!--/kpi--> na rede física, de forma quase monotônica, com o nº de linhas caindo na mesma proporção. Essa queda proporcional é assinatura *possível* de **truncamento de captura** (extração incompleta dos meses finais), não necessariamente retração de mercado — ver diagnóstico em [`outputs/etapa3/diagnostico_captura_mensal.csv`](outputs/etapa3/diagnostico_captura_mensal.csv) e [`diagnostico_captura_lojas_mensal.csv`](outputs/etapa3/diagnostico_captura_lojas_mensal.csv): se a queda é homogênea entre lojas → mercado; se lojas "somem" da base → captura. **Impacto:** essa base alimenta `VENDA_MEDIA_MES` e a projeção de compras das Etapas 6/7, então a incerteza se propaga para a demanda projetada (ler as quantidades como ordem de prioridade, não previsão fechada).
- A maior contribuição bruta para a queda de 2025 veio de `D - ELETROS` e, por loja, da Loja 93.

**Limitações e cuidados:** a análise é descritiva; picos e quedas não são atribuídos a causa sem evidência adicional. `TRANSACOES` representa linhas de venda, não cupons únicos, pois a base não tem id de cupom/pedido/nota. Ticket médio = proxy de receita por linha de venda; preço médio = receita por unidade de armazenagem. A Loja 93 é segregada para evitar mistura entre atacado/B2B e rede física.

**Como executar:**

```bash
cd notebooks
python etapa3_desempenho_vendas.py
```

Arquivos auditáveis em `outputs/etapa3/`, incluindo rankings, curva ABC, desempenho por categorias/lojas, sazonalidade, decomposição da queda, notas metodológicas, recomendações de melhoria e `resumo_etapa3.md`.

### Etapa 4 — Cobertura por Categoria e Loja

A Etapa 4 agrega o snapshot de cobertura da Etapa 2 por `NIVEL_1`, `NIVEL_2`, `NIVEL_3`, loja e categoria×loja, cruzando com os outputs auditáveis da Etapa 3 para priorizar reposição por receita histórica em risco. A Loja 93 é mantida na rede completa, mas a priorização operacional compara a rede física separadamente.

**Achados principais:**
- Rede completa: <!--kpi:e4.cobertura.total_pares:int-->28.721<!--/kpi--> pares loja×produto; <!--kpi:e4.ruptura_critico.completa.pares:int-->26.713<!--/kpi--> (<!--kpi:e4.ruptura_critico.completa.pct:pct-->93,0%<!--/kpi-->) em ruptura/crítico.
- Receita histórica associada a pares em ruptura/crítico: <!--kpi:e4.ruptura_critico.completa.receita:milhao-->R$ 464,6M<!--/kpi--> na rede completa e <!--kpi:e4.ruptura_critico.fisico.receita:milhao-->R$ 316,3M<!--/kpi--> na rede física sem Loja 93.
- Categoria com maior receita em risco: `D - ELETROS` (R$ 190,7M na rede completa; R$ 78,8M na rede física).
- Loja física com maior receita em risco: loja 3 (SALVADOR-BA), com R$ 58,7M em ruptura/crítico.
- Maior prioridade categoria×loja na rede física: `D - ELETROS` na loja 92 (CABO DE SANTO AGOSTINHO-PE), com R$ 17,0M de receita em risco.
- Loja 93 é analisada à parte: `D - ELETROS` concentra R$ 111,9M de receita em risco nesse canal.

**Limitações e cuidados:** cobertura continua sendo uma métrica conservadora baseada nos dados disponíveis; não representa disponibilidade física real. `DIAS_COBERTURA` infinito/sem venda é contado separadamente, e médias/medianas usam apenas valores finitos. A ausência de transferências, ajustes de inventário, lead time e política de estoque limita a conversão direta da priorização em quantidade ideal de compra. `TRANSACOES` segue sendo proxy de linhas de venda nos cruzamentos com a Etapa 3.

**Como executar:**

```bash
cd notebooks
python etapa4_cobertura_categoria_loja.py
```

Arquivos auditáveis em `outputs/etapa4/`, incluindo cobertura por categorias/lojas, priorização categoria×loja, recomendações de melhoria, validações, `resumo_etapa4.md` e `documentacao_tecnica_etapa4.md`.

### Etapa 5 — Precificação e Variação de Margem

A Etapa 5 calcula a margem bruta realizada (R$ e %), markup e custo médio por SKU, categoria e loja, sempre na **mesma unidade de armazenagem**, e compara o preço praticado com o preço de lista (`dim_precos`) para medir o desconto efetivo — **dentro da mesma embalagem**. Também mede a dispersão de preço do mesmo SKU entre lojas (por embalagem) e prioriza candidatos a repricing. A Loja 93 (atacado/B2B) é segregada em universo próprio e o custo de cada universo usa apenas as compras das lojas do universo.

**Achados principais:**
- Custo de compra válido existe só para **<!--kpi:e5.cobertura_custo.skus_com_custo:int-->261<!--/kpi--> SKUs** (de <!--kpi:e5.skus_vendidos:int-->2.729<!--/kpi--> vendidos): **<!--kpi:e5.cobertura_custo.receita_completa:milhao-->R$ 79,1M<!--/kpi-->, <!--kpi:e5.cobertura_custo.pct_completa:pct-->16,4%<!--/kpi--> da receita** na rede completa (<!--kpi:e5.cobertura_custo.pct_fisica:pct-->15,2%<!--/kpi--> na rede física). A margem realizada vale apenas para esse subconjunto — análogo ao "88% vendem sem compra registrada" das Etapas 1/2.
- **`fato_compras_2.csv` parece PARCIAL** — 4 lojas com venda (**1, 4, 8 e 9**) não têm nenhuma compra no arquivo e **10 categorias inteiras** aparecem com 100% da receita sem custo (ex.: `R - ELETRONICOS`, `S - TINTAS E QUIMICOS`, `F - FERRAMENTAS`). A baixa cobertura de custo é, portanto, **provável lacuna de extração a levantar com a origem dos dados**, não característica do negócio. Detalhes em [`LIMITACOES.md`](LIMITACOES.md).
- Margem bruta % média ponderada (itens com custo): **<!--kpi:e5.margem.rede_completa:pct-->47,6%<!--/kpi--> na rede completa** (markup <!--kpi:e5.markup.rede_completa:markup-->1,91×<!--/kpi-->) e **<!--kpi:e5.margem.rede_fisica:pct-->49,8%<!--/kpi--> na rede física** (markup <!--kpi:e5.markup.rede_fisica:markup-->1,99×<!--/kpi-->).
- Maior margem por categoria na rede física (cobertura ≥10%): `C - PISOS E REVESTIMENTOS` (56,1%); menor: `D - ELETROS` (42,8%). `B - UTILIDADES DOMÉSTICAS` aparece com **margem negativa** (−15,4%) no subconjunto com custo — louças/porcelanas de baixo giro vendidas abaixo do custo.
- Desconto efetivo médio ponderado na rede física: **<!--kpi:e5.desconto.rede_fisica:pct-->17,4%<!--/kpi-->**; **<!--kpi:e5.acima_lista.rede_fisica:int-->2.079<!--/kpi-->** combinações loja×produto×embalagem vendem **acima da lista** (desconto negativo → tabela possivelmente desatualizada). Contagem de itens *estritamente* acima da lista, com tolerância de arredondamento para não contar empates preço = lista.
- Dispersão de preço entre lojas (rede física, embalagem 0): apenas **<!--kpi:e5.dispersao.cv_alta_fisica:int-->46<!--/kpi--> SKUs com CV>30%** — bem abaixo da leitura ingênua de "<!--kpi:e5.naive.amplitude:int-->2.619<!--/kpi--> SKUs com amplitude de preço bruto >30%" (métrica diferente: amplitude do preço bruto entre linhas, misturando embalagem e atacado).
- **<!--kpi:e5.candidatos.rede_fisica:int-->3.260<!--/kpi-->** candidatos a repricing na rede física (<!--kpi:e5.candidatos.alta_fisica:int-->326<!--/kpi--> de prioridade ALTA), combinando margem baixa/negativa, desconto alto e preço fora da faixa da rede. O sinal de margem é calculado no grão loja×produto×embalagem.

**Revisão de qualidade (autoaudit):** três armadilhas tratadas explicitamente — (1) **margens absurdas por erro de unidade**: preço e custo normalizados para a unidade de armazenagem mantêm todos os 261 markups na faixa sanitária (0,65×–4,76×), prevenindo o falso outlier de "venda em caixa"; (2) **custo de SKU sem compra vazando para a margem**: 2.468 SKUs (R$ 403,4M, 83,6% da receita) ficariam com margem fabricada se o custo fosse imputado — corrigido restringindo a margem aos SKUs com custo próprio; (3) **mistura de embalagem na dispersão**: a leitura ingênua marcava ~2,6k SKUs com variação >30%; separando embalagem e atacado, caem para 46 (pelo CV).

**Limitações e cuidados:**
- Margem realizada existe só para os ~261 SKUs com custo (~16% da receita); o restante fica sem margem por ausência de dado, não por erro.
- O custo é a média ponderada do período, sem camadas de custo (PEPS) nem custo de reposição atual.
- O preço de lista (`dim_precos`) pode não refletir promoções pontuais; o desconto efetivo é uma aproximação.
- A Loja 93 é atacado/B2B: margens não comparáveis ao varejo, por isso segregada em `LOJA_93_ATACADO_B2B` (margem auditável de 43,9% nos SKUs com custo).

**Como executar:**

```bash
cd notebooks
python etapa5_precificacao_margem.py
```

Arquivos auditáveis em `outputs/etapa5/`: `margem_produtos.csv`, `margem_categorias_n1/n2/n3.csv`, `margem_lojas.csv`, `margem_total_universo.csv`, `precificacao_desconto.csv`, `dispersao_preco_lojas.csv`, `candidatos_repricing.csv`, `recomendacoes_melhoria.csv`, `validacoes_etapa5.csv`, `autoaudit_etapa5.csv`, `resumo_etapa5.md` e `documentacao_tecnica_etapa5.md`.

### Etapa 6 — Projeção de Compras para o Próximo Período

A Etapa 6 transforma a cobertura e a priorização das etapas anteriores em um plano operacional de compra para **90 dias**, no grão loja×SKU. A quantidade recomendada usa demanda histórica do próprio par, estoque projetado utilizável e status de cobertura; o investimento financeiro só é estimado quando existe custo válido na Etapa 5. A Loja 93/B2B é tratada em escopo separado — com demanda **e status de cobertura recalculados** a partir das próprias vendas B2B — e os totais fecham em `REDE_COMPLETA`.

**Achados principais:**
- Rede completa: **<!--kpi:e6.pares.rede_completa:int-->20.357<!--/kpi--> pares loja×SKU** com compra recomendada, somando **<!--kpi:e6.unidades.rede_completa:int-->1.019.914<!--/kpi--> unidades de armazenagem**.
- Rede física sem Loja 93: **<!--kpi:e6.pares.rede_fisica:int-->20.061<!--/kpi--> pares** recomendados, **<!--kpi:e6.unidades.rede_fisica:int-->993.649<!--/kpi--> unidades**, com **<!--kpi:e6.investimento.rede_fisica:milhao-->R$ 5,7M<!--/kpi-->** de investimento conhecido.
- Loja 93/B2B: **<!--kpi:e6.pares.loja93:int-->296<!--/kpi--> pares** recomendados, **<!--kpi:e6.unidades.loja93:int-->26.265<!--/kpi--> unidades**, com **<!--kpi:e6.investimento.loja93:milhao-->R$ 2,1M<!--/kpi-->** de investimento conhecido (a demanda B2B recalculada reclassifica **37 pares** como CRÍTICO/ATENÇÃO que ficariam fora da fila se herdassem o status da Etapa 2).
- Apenas **<!--kpi:e6.cobertura_custo.pct_completa:pct-->9,7%<!--/kpi-->** dos pares recomendados têm custo válido; portanto, o plano é mais operacional do que financeiro até completar custos por SKU.
- Categoria com maior volume recomendado na rede física: `C - PISOS E REVESTIMENTOS` (**264.264 unidades**). Loja física com maior volume: loja 3 (SALVADOR-BA), com **166.885 unidades**.
- A fila operacional da rede física tem **<!--kpi:e6.prioridade_alta.rede_fisica:int-->2.007<!--/kpi--> pares de prioridade ALTA**.

**Autoaudit / cuidados críticos:** ausência de demanda observada não vira compra; custo ausente não vira investimento zero; estoque negativo vira zero utilizável, não dívida adicional; e itens com margem negativa exigem validação de preço/margem antes de compra.

**Como executar:**

```bash
cd notebooks
python etapa6_projecao_compras.py
```

Arquivos auditáveis em `outputs/etapa6/`: `plano_compras_sku_loja.csv`, `plano_compras_total_universo.csv`, `plano_compras_categorias_n1.csv`, `plano_compras_lojas.csv`, `priorizacao_compras.csv`, `recomendacoes_melhoria.csv`, `validacoes_etapa6.csv`, `autoaudit_etapa6.csv`, `resumo_etapa6.md` e `documentacao_tecnica_etapa6.md`.

### Etapa 7 — Recomendações Finais e Plano de Execução Comercial

A Etapa 7 é a **síntese de decisão**: consome os artefatos auditáveis das Etapas 3-6 (sem recalcular base crua) e classifica cada par loja×SKU em uma de quatro ações comerciais — **comprar**, **reprecificar**, **promover/queimar estoque** ou **descontinuar**. Um mesmo par pode disparar mais de um *sinal*, mas recebe **uma ação primária** por precedência (`DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR`) para que capital e quantidade **não sejam contados em duas ações**. Os três universos ficam segregados e fecham em `REDE_COMPLETA`. A base reaproveitada é o `plano_compras_sku_loja.csv` da Etapa 6, que já traz o status de cobertura recalculado por universo (corrigindo a Loja 93), giro, curva ABC, custo e margem.

**Lógica de classificação:**
- **Descontinuar** — par em `SEM VENDA` com estoque parado (>0), curva ABC conhecida e curva ABC ≠ A (capital imobilizado a delistar).
- **Promover/queimar** — estoque encalhado que ainda gira (`SAUDÁVEL` com cobertura > 180 dias), campeão curva A parado ou par parado com curva ausente que precisa de revisão antes de qualquer saída.
- **Reprecificar** — candidatos da Etapa 5 (faixa ALTA/MÉDIA), separando **sinal de margem auditável** (item com custo e margem baixa/negativa) de **sinal de preço/lista** (desconto alto ou preço fora da faixa, com ou sem custo).
- **Comprar** — fila de compra da Etapa 6 (`QTD_RECOMENDADA_ARM > 0`).

**Achados principais:**
- Rede física sem Loja 93: **<!--kpi:e7.comprar.rede_fisica:int-->19.126<!--/kpi-->** pares a comprar (<!--kpi:e7.comprar.rede_fisica.valor:milhao-->R$ 4,6M<!--/kpi--> de investimento conhecido), **<!--kpi:e7.reprecificar.rede_fisica:int-->956<!--/kpi-->** a reprecificar, **<!--kpi:e7.promover.rede_fisica:int-->752<!--/kpi-->** a promover/queimar (<!--kpi:e7.promover.rede_fisica.valor:milhao-->R$ 6,7M<!--/kpi--> de estoque encalhado com custo) e **<!--kpi:e7.descontinuar.rede_fisica:int-->434<!--/kpi-->** a descontinuar (<!--kpi:e7.descontinuar.rede_fisica.valor:milhao-->R$ 0,4M<!--/kpi--> de capital imobilizado com custo).
- Loja 93/B2B (escopo próprio): **263** a comprar, **33** a reprecificar, **20** a promover e **29** a descontinuar.
- **Guarda-corpo do campeão e curva ausente:** **132** pares curva A parados e **3** pares sem curva ABC foram protegidos do descontinue e roteados para escoar/transferir/revisar — nenhum item curva A ou sem curva entra em descontinuar.
- **Repricing (revisão interna):** dos **<!--kpi:e7.repricing.total:int-->1.011<!--/kpi-->** candidatos loja×SKU casados na base, **<!--kpi:e7.repricing.margem_auditavel:int-->41<!--/kpi-->** têm sinal de margem **auditável**; **<!--kpi:e7.repricing.preco_com_custo:int-->75<!--/kpi-->** têm custo válido mas apenas sinal de preço/lista; **<!--kpi:e7.repricing.preco_sem_custo:int-->895<!--/kpi-->** não têm custo e são tratados como ajuste de preço/lista, não como prova de margem.
- **Anti-dupla-contagem:** **<!--kpi:e7.anti_dupla.pares:int-->990<!--/kpi-->** pares disparam mais de um sinal; cada um entra uma única vez na fila via ação primária. As reconciliações com as etapas-fonte usam os *sinais* (o sinal de comprar bate com os <!--kpi:e6.pares.rede_completa:int-->20.357<!--/kpi--> pares da Etapa 6; o de reprecificar bate com os candidatos ALTA/MÉDIA da Etapa 5).
- **<!--kpi:e7.validacoes.ok:int-->23<!--/kpi-->/<!--kpi:e7.validacoes.total:int-->23<!--/kpi--> validações OK** (receita fecha com a Etapa 3; `REDE_COMPLETA = física + Loja 93` por ação; curva ausente não descontinua; pares sem métrica ficam em prioridade baixa; financeiro nunca imputado sem custo).

**Autoaudit / armadilhas tratadas:** (1) descontinuar campeão histórico só por giro recente baixo ou curva ausente → curva A/ausente protegido; (2) promover/reprecificar item como se a margem fosse conhecida sem evidência → separação de sinais e financeiro só com custo; (3) misturar a Loja 93 nas recomendações de varejo → escopo próprio com status B2B recalculado e curva de guarda-corpo; (4) dupla contagem de par que dispara mais de uma ação → ação primária por precedência.

**Limitações e cuidados:** estoque projetado não é contagem física — descontinuar/promover exige validar saldo e obsolescência antes de agir; giro usa média dos meses com venda, e itens sazonais podem parecer parados fora de estação (cruzar com a sazonalidade da Etapa 3); o valor financeiro conhecido não é budget total, pois exclui itens sem custo (`NaN` = não avaliado ≠ `0`); a fila diz **o que** fazer e **em que ordem**, não **quanto** descontar nem o lote de recompra.

**Como executar:**

```bash
cd notebooks
python etapa7_recomendacoes_finais.py
```

Arquivos auditáveis em `outputs/etapa7/`: `recomendacoes_sku_loja.csv`, `recomendacoes_acao_universo.csv`, `recomendacoes_categoria_n1.csv`, `recomendacoes_lojas.csv`, `reprecificacao_candidatos.csv`, `priorizacao_acoes.csv`, `recomendacoes_melhoria.csv`, `validacoes_etapa7.csv`, `autoaudit_etapa7.csv`, `resumo_etapa7.md` e `documentacao_tecnica_etapa7.md`.

---

## Revisão de qualidade e correções

Uma revisão de qualidade da Etapa 2 identificou **4 problemas**, todos corrigidos em
[`notebooks/etapa2_estoque_projetado.py`](notebooks/etapa2_estoque_projetado.py) e revalidados.
O detalhamento visual (com antes/depois) está no **dashboard**
[`outputs/relatorio_qualidade_dados.html`](outputs/relatorio_qualidade_dados.html) e nos
notebooks executados
[`02_etapa2_estoque_projetado.ipynb`](notebooks/02_etapa2_estoque_projetado.ipynb) e
[`01_etapa1_entendimento_dados.ipynb`](notebooks/01_etapa1_entendimento_dados.ipynb).

| # | Sev. | Problema | Correção | Impacto mensurável |
|---|---|---|---|---|
| **1** | 🔴 Crítico | Receita por par calculada **sem a loja 93** → 263 pares da loja 93 em ruptura ficavam com receita nula e sumiam do ranking | Calcular receita com **todas as lojas** (`excluir_atacado=False`); segregar o atacado só como filtro posterior | **+263 pares** da loja 93 (Eletros de maior receita) reintegrados ao ranking de reposição |
| **2** | 🔴 Crítico | Skeleton montado **só com o estoque inicial**, ignorando pares que vendem sem foto de estoque | Skeleton = **união** de estoque ∪ vendas ∪ compras; sem foto inicial → `ESTOQUE_INICIAL = 0` | **+3.379 pares** incluídos, **+R$ 87,5M** (18,1% da receita) rastreados |
| **3** | 🟠 Médio | `DIAS_COBERTURA` ficava **negativo** (ex.: −566; mín. −720) em rupturas | Piso em 0 quando `ESTOQUE_PROJ ≤ 0` | **14.939 → 0** valores negativos no output |
| **4** | 🟠 Médio | Produto 119959 com preço de R$ 3,68 a R$ 391,55 na mesma loja | Investigado e documentado em [`investigacao_outliers_preco.csv`](outputs/etapa2/investigacao_outliers_preco.csv) | **Não é bug:** venda em caixa (EMBALAGEM=1, CONVERSAO=100) com conversão aplicada. Dos **75** pares com CV>1, **0** são erro de conversão |

**Validações executadas após a correção (no notebook 02):**
- ✅ 263 pares da loja 93 em ruptura agora têm `RECEITA_TOTAL` preenchida (antes: 0)
- ✅ Os 3.379 pares sem estoque inicial agora aparecem na cobertura
- ✅ Nenhum `DIAS_COBERTURA` negativo no output final
- ✅ Resumo antes/depois por `STATUS_ESTOQUE` impresso no notebook e no dashboard

---

## Próximas etapas (planejadas)

- **Etapa 8** — Apresentação executiva

---

## Decisões metodológicas

| Decisão | Justificativa |
|---|---|
| Encoding `latin1` em todos os CSVs | Arquivos gerados por sistema legado brasileiro |
| Nulos de estoque → 0 | Conservador: gera alertas precoces de ruptura |
| 132 preços de compra nulos excluídos do CMV | Volume físico válido; custo sem base não pode ser imputado |
| Loja 93 segmentada | Ticket 20× superior, 76% Eletros → operação B2B distorce médias da rede |
| QTD_ARMAZENAGEM = QTD × Conversão | Garantir mesma unidade em saídas, entradas e estoque inicial |
| Estoque negativo = ruptura | Direção conservadora: prioriza reposição dos itens mais vendidos |

---

## Premissas, limitações conhecidas e próximos passos

> 📋 As limitações materiais do projeto estão consolidadas em [`LIMITACOES.md`](LIMITACOES.md)
> (cobertura de custo de 16,4%, base de compras provavelmente parcial, queda de 2025 como hipótese
> a confirmar, entre outras). Abaixo, o resumo dos pontos que eu revisitaria antes de tratar os
> números como definitivos.

Decisões assumidas de forma transparente, com os pontos que eu revisitaria antes de tratar os números como definitivos:

- **Velocidade de venda (`VENDA_MEDIA_MES`) é a média dos meses *com* venda, não dos 24 meses.**
  Para itens de venda intermitente isso **superestima a velocidade** mensal e, portanto,
  **subestima os dias de cobertura** — empurrando itens para "Crítico". É uma escolha herdada da
  Etapa 2 original, mantida por consistência; uma variante dividindo o volume total pelos 24 meses
  (ou pelos meses desde a 1ª venda) deve ser comparada na próxima iteração.
- **A ruptura de ~91% não é ruptura física real de 91% da rede.** Ela reflete a *ausência de
  registros de reposição* na base (~88% dos SKUs vendem sem compra registrada — provável reposição
  via transferência entre lojas, não capturada) somada ao tratamento conservador de estoque nulo = 0.
  O indicador serve para **priorização relativa** (o que repor primeiro), não como medida absoluta
  de disponibilidade.
- **Loja 93 (atacado)** entra nos cálculos de receita e estoque (são fatos do par), mas é excluída
  da *referência de consumo da rede física* na cobertura em dias. Isso pode gerar pares da loja 93
  com receita alta e status "Sem Venda" — comportamento esperado, não erro.
- **Queda de 2025 (−54% de receita YoY) é uma HIPÓTESE A CONFIRMAR, não um achado fechado.** Os 24
  meses estão presentes, mas o volume cai quase monotonicamente ao longo de 2025 e o nº de linhas cai
  na mesma proporção — isso é assinatura *possível* de **truncamento de captura** (extração incompleta),
  tanto quanto de retração de mercado. O diagnóstico em `outputs/etapa3/diagnostico_captura_mensal.csv`
  e `diagnostico_captura_lojas_mensal.csv` testa as duas hipóteses (queda homogênea entre lojas → mercado;
  lojas sumindo da base → captura). Como essa base alimenta `VENDA_MEDIA_MES` e a projeção das Etapas 6/7,
  a incerteza se propaga para a demanda projetada. Ver também aba *Inconsistências* do dashboard.

**Próximos passos sugeridos:** (1) cobertura em dias com média sobre 24 meses + análise de
sensibilidade do status; (2) incorporar transferências entre lojas para fechar o gap dos SKUs sem
compra; (3) decompor a queda de 2025 por categoria e canal (atacado × rede).

---

## Tecnologias

- **Python 3.11+** (testado em 3.14) com pandas, numpy, pyarrow — versões fixadas em `requirements.txt`
- **Parquet** para armazenamento intermediário (5–10× mais rápido que CSV para 1M+ linhas)
- **Chart.js** (via CDN) no dashboard HTML autocontido
- Compatível com Power BI, Tableau e DuckDB para visualização
