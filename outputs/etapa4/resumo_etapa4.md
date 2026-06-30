# Etapa 4 - Análise de cobertura por categoria e loja

## Glossário rápido (ler antes dos números)

- **Par loja × produto:** cada combinação de uma loja com um produto. É o grão
  desta análise. A rede completa tem 28.721 pares.
- **Cobertura (dias de estoque):** `estoque projetado ÷ venda média mensal × 30`.
  Estima por quantos dias o estoque atende a venda média.
- **Estoque projetado:** **não** é contagem física. É reconstruído como
  `estoque inicial + compras − vendas` na janela jan/2024–dez/2025 (vem da Etapa 2).
- **Em ruptura / crítico:** par com estoque projetado ≤ 0 (ruptura) ou cobertura
  ≤ 30 dias (crítico). São os pares que entram na fila de reposição.
- **Receita histórica em risco:** receita **já realizada no passado** pelos pares
  hoje classificados em ruptura/crítico. É usada para **ordenar prioridade** de
  reposição — **não** é uma previsão de perda futura.

## Como interpretar a cobertura (leia antes de reagir aos 93%)

A taxa de ruptura é altíssima de propósito, por limitação de dados, não por erro:

- A base **não tem foto de estoque de abertura** para a maioria dos pares (entram
  com estoque inicial = 0) e **~88% dos SKUs vendem sem nenhuma compra registrada**.
  Com isso, o estoque projetado fica ≤ 0 na maior parte dos pares, que são então
  marcados como "EM RUPTURA".
- É uma escolha **conservadora deliberada**: na dúvida, o método assume falta de
  estoque — ou seja, **erra para sinalizar ruptura a mais, nunca a menos**.
- Portanto, "93,0% em ruptura/crítico"
  **não** significa "93,0% das prateleiras
  vazias na vida real". É um **ranking de prioridade relativa** de reposição, não a
  taxa real de ruptura física.
- "Disponibilidade física real" exigiria inventário/contagem física, transferências
  entre lojas e ajustes de saldo que **não existem nesta base**.

## Principais achados

- Rede completa: 28.721 pares loja × produto; 26.713 (93,0%) estão em ruptura/crítico (lembrando: prioridade relativa, ver seção acima).
- A receita histórica associada a ruptura/crítico na rede completa é R$ 464,6M, equivalente a 96,3% da receita histórica dos pares. Leia como "concentração de receita por trás da fila de reposição", não como perda projetada.
- Rede física sem Loja 93: 26.395 pares; 24.481 (92,7%) em ruptura/crítico, com R$ 316,3M de receita histórica associada.
- Categoria N1 com maior receita histórica em ruptura/crítico na rede completa: `D - ELETROS`, com R$ 190,7M.
- Categoria N1 com maior receita histórica em ruptura/crítico na rede física: `D - ELETROS`, com R$ 78,8M.
- Loja física com maior pressão de reposição por receita histórica em ruptura/crítico: loja 3 (SALVADOR-BA), com R$ 58,7M.
- Loja 93 deve ser analisada separadamente: no escopo de rede completa, soma R$ 148,3M de receita histórica em ruptura/crítico.
- Maior prioridade na rede física: `D - ELETROS` na loja 92 (CABO DE SANTO AGOSTINHO-PE), com R$ 17,0M de receita histórica associada.
- Maior prioridade da Loja 93: `D - ELETROS`, com R$ 111,9M de receita histórica associada.

## Limitações e cuidados

- A cobertura é uma métrica **conservadora** (erra para o lado de sinalizar ruptura
  a mais) e mede **prioridade relativa**, não disponibilidade física real. Ver a
  seção "Como interpretar a cobertura".
- A base não possui transferências entre lojas, ajustes de inventário nem saldo
  físico posterior ao corte inicial — daí o excesso de ruptura.
- `VENDA_MEDIA_MES` vem da Etapa 2 e usa a média dos meses **com** venda, o que pode
  superestimar a velocidade e subestimar a cobertura de itens intermitentes.
- A Loja 93 é atacado/B2B e não deve ser comparada diretamente com lojas físicas;
  por isso é segregada nas agregações e na priorização.
- `TRANSACOES` nos cruzamentos com a Etapa 3 representa **linhas de venda**, não
  cupons/pedidos/notas reais (a base não tem id de transação).

## Validações

- 43 validações executadas, todas com status `OK`.
- Totais de pares e receita das agregações fecham com `outputs/etapa2/cobertura_estoque.csv`.
- Receita das agregações por categoria e loja fecha com os outputs correspondentes da Etapa 3.
- Loja 93 não aparece no universo `REDE_FISICA_SEM_LOJA93`.
- Estatísticas de dias de cobertura não carregam valores infinitos em médias/medianas.

## Como executar

```bash
cd notebooks
python etapa4_cobertura_categoria_loja.py
```

Os arquivos auditáveis são gravados em `outputs/etapa4/`.
