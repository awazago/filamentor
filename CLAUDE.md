# Bambu Print Advisor — Instruções para Agentes Claude

> Documento de handoff criado em 2026-10-11 a partir da sessão de levantamento de requisitos
> (originalmente aberta no repositório do FisioApp — **sem relação** com este projeto).
> Nome do projeto é provisório.

## O que é

Aplicação web que recebe o upload de um modelo **STL ou 3MF**, faz uma **análise geométrica criteriosa**,
pergunta o **filamento** que o usuário pretende usar e a **finalidade da peça**, **recomenda o melhor
filamento** e gera **configurações prontas para o Bambu Studio** voltadas às impressoras
**Bambu Lab A1** e **A1 mini**.

Objetivo de produto: começar como ferramenta de uso pessoal; se funcionar bem, abrir ao público
(SaaS por mensalidade ou doação). Interface **bilíngue (PT-BR e EN)**.

**Prioridade: qualidade de impressão acima de custo/tempo** em todas as recomendações.

---

## Decisões já tomadas

| # | Tema | Decisão |
|---|------|---------|
| 1 | Saída do MVP | **(A)** presets do Bambu Studio (process + filament, JSON herdando presets oficiais `@BBL A1` / `@BBL A1M`) **e (B)** arquivo `.3mf` de projeto com as configurações já embutidas, para o usuário abrir no Bambu Studio e só fatiar. Se o Bambu Studio aceitar um formato de configuração mais adequado que JSON avulso (ex.: bundles `.bbscfg` / `.bbsflmt`), usar esse formato. |
| 2 | Arquitetura | Processamento local/privado aceito. Ver "Questão em aberto" sobre backend. |
| 3 | IA | **Claude** (Anthropic API) para explicar a recomendação em linguagem natural. Usar o modelo Claude mais recente/capaz. |
| 4 | Público | Uso pessoal primeiro → depois SaaS / mensalidade / doação. Arquitetura deve permitir auth e cobrança no futuro, mas **não implementar no MVP**. |
| 5 | Stack | Usuário aceita HTML + Vanilla JS + Three.js, mas acredita que **Python** tem libs numéricas melhores (numpy, trimesh). Ver recomendação abaixo. |
| 6 | Multicor | Usuário tem **AMS Lite** → suportar 3MF multicor/multimaterial (mapeamento de slots). |
| 7 | Bicos | **0.2, 0.4, 0.6 e 0.8 mm** (aço inox padrão). **Sem bicos endurecidos** por ora → sem filamentos CF/GF abrasivos. |
| 8 | Filamentos | **PLA, PETG e TPU** (e variações compatíveis com A1/A1 mini). A1 é aberta (sem câmara) → ABS/ASA/PC/PA fora do escopo. |
| 9 | Perguntas de uso | Decorativa x funcional, uso externo/UV, exposição a calor, flexibilidade, resistência mecânica, contato com alimento, acabamento desejado. |
| 10 | Escala | Só escalar **se o usuário pedir**; ao escalar, mostrar **dimensões resultantes** e **estimativa de filamento** (g / m). Orientação: recomendar (e aplicar no 3MF de saída se o usuário aceitar). |
| 11 | Parâmetros | Sugerir altura de camada, infill (padrão + %), paredes, topo/fundo, tipo de suporte (tree/normal), brim, velocidades, temperaturas, resfriamento. Estimar tempo e filamento. |
| 12 | Idioma | PT-BR e EN. |

## Recomendação de arquitetura (a confirmar com o usuário no início da nova sessão)

Como a chave da API Claude **não pode ficar no navegador**, um backend é necessário de qualquer forma.
Proposta:

- **Backend Python (FastAPI)**: análise de malha com `trimesh` + `numpy` (watertight, normais, volume,
  overhangs, orientação ótima, paredes finas via ray casting), leitura/escrita de 3MF, geração dos presets,
  proxy para a Claude API (chave via variável de ambiente, nunca commitada).
- **Frontend Vanilla JS + Three.js**: upload, visualizador 3D com heatmap de overhang, questionário,
  painel de recomendação, download dos arquivos.
- Arquivos do usuário processados em memória, sem persistência no MVP (privacidade).
- Deploy futuro: Railway (usuário já usa) ou similar.

## Fatos técnicos relevantes (verificar contra a versão atual do Bambu Studio)

- **Volume de impressão:** A1 = 256 × 256 × 256 mm; A1 mini = 180 × 180 × 180 mm.
- **Presets do Bambu Studio** são JSON com campos como `type` (`process` / `filament` / `machine`),
  `name`, `inherits` (ex.: `"0.20mm Standard @BBL A1"`), `from: "User"` e só as chaves sobrescritas.
  Existem também bundles de preset exportáveis/importáveis (`.bbscfg`, `.bbsflmt`) — confirmar formato.
- **3MF da Bambu** é um ZIP contendo, entre outros: `3D/3dmodel.model` (geometria),
  `Metadata/project_settings.config` (JSON com as configurações do projeto),
  `Metadata/model_settings.config` (XML com overrides por objeto/placa), `Metadata/slice_info.config`.
  A saída (B) deve ser gerada de forma que o Bambu Studio abra sem aviso de incompatibilidade.
- **Estimativa de filamento/tempo** sem fatiar é aproximada (volume, infill, paredes). Deixar isso claro na UI.
  Fatiamento real via CLI do Bambu Studio/OrcaSlicer é uma evolução pós-MVP (opção C, `.gcode.3mf`).
- A máquina local tem MCPs `bambu-printer` / `bambu-studio-tools` disponíveis, úteis para **validar**
  os arquivos gerados (ex.: `inspect_3mf`, `slice_model`) durante o desenvolvimento.

## Análise geométrica esperada

Dimensões e bounding box · cabe na A1 / A1 mini · volume e área · contagem de triângulos ·
malha fechada (manifold) e normais consistentes · overhangs por ângulo (limite configurável, ex. 45°) ·
área de contato com a mesa e risco de tombamento (razão altura/base) · pontes · paredes finas e detalhes
menores que a largura de extrusão do bico · sugestão de orientação · necessidade de suporte e brim.

## Próximos passos

1. Confirmar com o usuário a arquitetura (backend Python + frontend JS) e o nome do projeto.
2. Pesquisar e validar o formato exato de presets/bundles e do 3MF atual do Bambu Studio.
3. Montar plano de MVP em fases e só então implementar.

## Regras

- Nunca commitar credenciais (chave Anthropic etc.) — usar `.env` + `.gitignore`.
- Commitar apenas quando o usuário pedir.
- Comunicação com o usuário em **português**.
