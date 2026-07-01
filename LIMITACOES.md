# Limitações conhecidas e cuidados de interpretação

Este documento reúne, de forma pública e transparente, as limitações materiais do
projeto — o que eu revisitaria antes de tratar os números como definitivos. Elas já
estão citadas nas etapas e no dashboard; aqui ficam consolidadas para leitura rápida.

Os números das seções abaixo saem do próprio pipeline (bases tratadas em
`data/processed/` e saídas em `outputs/`), não de valores digitados à mão.

---

## 1. Cobertura de custo baixa: a margem vale para um subconjunto, não para a rede

Apenas **261 SKUs** (de 2.729 vendidos) têm preço de compra válido no período,
cobrindo **R$ 79,1M (16,4% da receita)** na rede completa. A margem realizada
(47,6% rede completa / 49,8% rede física) é **auditável só nesse subconjunto** —
generalizá-la para a rede inteira seria enganoso. Os demais SKUs ficam **sem margem
por ausência de dado, nunca por imputação** (é o análogo do achado "88% vendem sem
compra registrada" das Etapas 1/2).

Propagar custo de um SKU entre lojas (premissa já aplicada, custo por `CODIGO`) sobe
a cobertura em menos de 1 p.p. — não resolve o buraco.

## 2. A base de compras (`fato_compras_2.csv`) parece PARCIAL — provável lacuna de extração

Sinais fortes de incompletude, que sugerem tratar a baixa cobertura de custo como
**provável lacuna de extração a levantar com a origem dos dados**, não como
característica do negócio:

- Vendas: 1.090.390 linhas, 2.729 SKUs, 11 lojas. Compras: **1.393 linhas, 329 SKUs, 7 lojas**.
- **4 lojas com venda não têm nenhuma compra no arquivo: lojas 1, 4, 8 e 9.**
- Loja 6 tem 1 linha de compra em 24 meses; loja 7 tem 16 linhas, todas com preço nulo.
- **10 categorias inteiras aparecem com 100% da receita sem custo** (R$ 85,9M, ~17,8%
  da receita), incluindo `R - ELETRONICOS`, `S - TINTAS E QUIMICOS`, `F - FERRAMENTAS`,
  `M - MAQUINAS E MOTORES` e `N - INDUSTRIAL E NEGOCIOS`.
- SKUs campeões de receita (ex.: `467774` D-ELETROS, R$ 12,5M) não têm qualquer origem
  de custo — implausível numa operação varejista completa.

**Ação recomendada:** confirmar com a origem o escopo da extração (lojas incluídas,
tipos de movimento, compras de CD/transferências, custo cadastral, período anterior
ao corte) antes de tratar a ausência de custo como real.

## 3. Repricing: separar sinal de margem auditável de alerta de preço/lista

Boa parte dos candidatos a repricing é, na verdade, **alerta de desconto/preço fora da
faixa sem custo** para confirmar margem. A Etapa 5/7 já separa `SINAL_MARGEM_AUDITAVEL`
(tem custo, margem baixa/negativa) de `SINAL_PRECO_LISTA` (não exige custo) e não gera
valor financeiro para o sinal de preço. Não confundir "problema de preço/lista" com
"problema de margem comprovada".

## 4. Margem negativa em categoria de baixa cobertura não é margem da categoria

`B - UTILIDADES DOMÉSTICAS` aparece com margem **−15,4%**, mas a cobertura de custo da
categoria é ~2,7% da receita. O achado vale para o subconjunto com custo, **não** deve
ser lido como "a categoria inteira dá prejuízo".

## 5. Queda de 2025: mercado ou truncamento de captura? (hipótese aberta)

A receita cai ~54% YoY e o nº de linhas cai na mesma proporção, quase monotonicamente
ao longo de 2025. Isso é assinatura *possível* de **truncamento de captura** (extração
incompleta dos meses finais), tanto quanto de retração de mercado. O diagnóstico em
`outputs/etapa3/diagnostico_captura_mensal.csv` e `diagnostico_captura_lojas_mensal.csv`
testa as hipóteses. **Impacto:** essa base alimenta `VENDA_MEDIA_MES` e a projeção de
compras das Etapas 6/7 — a incerteza se propaga para a demanda projetada.

## 6. Demais cuidados herdados

- **`TRANSACOES` = linhas de venda, não cupons.** A base não tem id de cupom/pedido/nota;
  ticket médio é proxy por linha.
- **Ruptura de ~91% não é indisponibilidade física de 91%.** Reflete ausência de registros
  de reposição (~88% dos SKUs vendem sem compra registrada — provável transferência entre
  lojas não capturada) + tratamento conservador de estoque nulo = 0. Serve para priorização
  relativa, não medida absoluta.
- **Custo é média ponderada do período**, sem camadas (PEPS) nem custo de reposição atual.
- **Preço de lista sem vigência/promoção:** o desconto efetivo é uma aproximação.
- **Loja 93 é atacado/B2B:** margens e preços não comparáveis ao varejo, por isso segregada
  em universo próprio.
- **Estoque projetado ≠ contagem física:** descontinuar/promover exige validar saldo e
  obsolescência antes de agir.

---

*Para o detalhamento numérico de cada ponto, ver os `resumo_etapaN.md`, os `autoaudit_etapaN.csv`
e o dashboard `outputs/relatorio_qualidade_dados.html`.*
