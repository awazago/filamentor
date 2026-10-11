# Filamentor — Instruções para Agentes Claude

> Documento de handoff criado em 2026-10-11 a partir da sessão de levantamento de requisitos
> (originalmente aberta no repositório do FisioApp — **sem relação** com este projeto).
> Nome comercial definido em 2026-10-11: **Filamentor** (slogan provisório: "sua peça pronta para imprimir" / "your model, print-ready"). Não usar a marca "Bambu" no nome do produto.

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

## Arquitetura (confirmada pelo usuário em 2026-10-11)

Como a chave da API Claude **não pode ficar no navegador**, um backend é necessário de qualquer forma.
Proposta:

- **Backend Python (FastAPI)**: análise de malha com `trimesh` + `numpy` (watertight, normais, volume,
  overhangs, orientação ótima, paredes finas via ray casting), leitura/escrita de 3MF, geração dos presets,
  proxy para a Claude API (chave via variável de ambiente, nunca commitada).
- **Frontend Vanilla JS + Three.js**: upload, visualizador 3D com heatmap de overhang, questionário,
  painel de recomendação, download dos arquivos.
- Arquivos do usuário processados em memória, sem persistência no MVP (privacidade).
- Deploy futuro: Railway (usuário já usa) ou similar.

## Fatos técnicos validados (Bambu Studio 02.08.02.61 instalado localmente, 2026-10-11)

- **Volume de impressão:** A1 = 256 × 256 × 256 mm; A1 mini = 180 × 180 × 180 mm.
- **Presets oficiais** ficam em `/Applications/BambuStudio.app/Contents/Resources/profiles/BBL/`
  (`machine/`, `process/`, `filament/`). Nomes: máquina `Bambu Lab A1 0.4 nozzle`, `Bambu Lab A1 mini 0.6 nozzle`…;
  processo `0.20mm Standard @BBL A1` / `@BBL A1M` (+ variantes `0.2/0.6/0.8 nozzle`); filamento
  `Bambu PETG HF @BBL A1`, `Bambu PLA Matte @BBL A1M 0.2 nozzle`… (161 presets PLA/PETG/TPU para A1/A1M).
  Usar como **catálogo-fonte**; não copiar para o repo (fazem parte do Bambu Studio, AGPL) — ler em runtime / na imagem Docker.
- **Presets são cadeias de herança** (`inherits`): ex. `0.20mm Standard @BBL A1` → `fdm_process_single_0.20` → … ;
  `Bambu PETG HF @BBL A1` → `Bambu PETG HF @base` → …. Valores efetivos exigem resolver a cadeia.
- **Preset de usuário** (formato que o Bambu Studio grava em
  `~/Library/Application Support/BambuStudio/user/<id>/process/`): JSON com `name`, `inherits` (preset do sistema),
  `from: "User"`, `print_settings_id`, `version` e **só as chaves alteradas** + arquivo `.info` ao lado.
  O usuário já tem presets próprios lá (ex.: "Action Figure PETG | C0,20 · 8% · 3P | Suporte Tree") — boa referência
  de estilo de nomes e de ajustes que ele valoriza.
- **Formatos importáveis** pelo Bambu Studio: `*.json`, `*.zip`, `*.bbscfg` (bundle de impressora) e `*.bbsflmt`
  (bundle de filamento), com `bundle_structure.json` interno. Estrutura do bundle ainda a detalhar.
- **CLI do Bambu Studio funciona (testado):**
  `BambuStudio --load-settings "machine.json;process.json" --load-filaments "fil.json" [--orient 1] [--arrange 1] --export-3mf /abs/out.3mf model.stl`
  - Gera **3MF de projeto completo** (`Metadata/project_settings.config`, `model_settings.config`, miniaturas
    das placas etc.) com printer/process/filament embutidos → **saída (B) resolvida pelo próprio Bambu Studio**.
  - Preset customizado com `inherits` + overrides (ex. `wall_loops`, `sparse_infill_density`, `brim_type`) foi aplicado corretamente.
  - `--slice 0` fatia em < 1 s para peças simples e grava em `slice_info.config` o **tempo previsto** e o
    **filamento usado (m / g)** → estimativa real, não aproximada.
  - ⚠️ **Caminhos de saída devem ser absolutos** (relativo falha com "Unable to open the file").
  - ⚠️ O CLI grava um `result.json` (status, `return_code`, tempos) no diretório de trabalho → rodar sempre
    com `cwd` numa pasta temporária por requisição e ler esse arquivo para diagnosticar falhas.
  - ⚠️ O preset de filamento do sistema passado direto **não teve a herança resolvida** (tipo saiu "PLA", peso 0 g):
    **sempre passar configs de filamento já "achatadas"** (cadeia de `inherits` resolvida pelo nosso backend).
- **Deploy (risco):** em produção o backend precisará do Bambu Studio CLI em Linux (AppImage/Docker) ou do OrcaSlicer.
  Validar empacotamento antes da fase SaaS. Rever licença (AGPL) ao abrir ao público.
- A máquina local tem MCPs `bambu-printer` / `bambu-studio-tools` disponíveis, úteis para **validar**
  os arquivos gerados (ex.: `inspect_3mf`, `slice_model`) durante o desenvolvimento.

## Análise geométrica esperada

Dimensões e bounding box · cabe na A1 / A1 mini · volume e área · contagem de triângulos ·
malha fechada (manifold) e normais consistentes · overhangs por ângulo (limite configurável, ex. 45°) ·
área de contato com a mesa e risco de tombamento (razão altura/base) · pontes · paredes finas e detalhes
menores que a largura de extrusão do bico · sugestão de orientação · necessidade de suporte e brim.

## Próximos passos

1. ~~Definir o nome comercial~~ → **Filamentor**.
2. ~~Validar formato de presets e 3MF~~ → feito (ver acima).
3. Plano de MVP em fases: ver seção "Plano do MVP".

## Plano do MVP

| Fase | Entrega |
|---|---|
| F0 ✅ | Estrutura do repo (`backend/` FastAPI, `frontend/`), venv, `ruff` + `pytest`, `.env.example` |
| F1 ✅ | Catálogo de presets: leitura dos presets oficiais A1/A1M + resolução de herança |
| F2 ✅ | Análise geométrica (`trimesh`): métricas, malha, overhangs, encaixe na mesa, orientação sugerida, escala sob demanda |
| F3 | Frontend: upload, visualizador Three.js com heatmap de overhang, questionário (uso, filamento, bico, impressora, AMS), i18n PT/EN |
| F4 | Motor de recomendação por regras (filamento + parâmetros, prioridade qualidade) + explicação via Claude |
| F5 | Saídas: preset de usuário (JSON/bundle) + 3MF de projeto via CLI + fatiamento para tempo/filamento reais |
| F6 | Multicor/AMS Lite (até 4 slots) e validação com impressões reais |

## Desenvolvimento

```bash
/opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn filamentor.main:app --reload --reload-dir backend --port 8000   # http://localhost:8000
.venv/bin/ruff check . && .venv/bin/ruff format --check .                          # lint (rodar antes de commitar)
.venv/bin/pytest -q
```

- `backend/filamentor/catalog.py` — `PresetLibrary` (carrega e achata presets) e `Catalog` (escopo do Filamentor).
- `backend/filamentor/analysis.py` — análise geométrica (`analyze()`), exposta em `POST /api/analyze` (upload).
- `backend/filamentor/main.py` — API (`/api/health`, `/api/printers`, `/api/materials`, `/api/processes`,
  `/api/filaments`, `/api/presets/resolved`) e serve `frontend/` em `/`.
- Testes em `backend/tests/`: `test_catalog.py` usa presets sintéticos; `test_bambu_studio_profiles.py`
  roda contra o Bambu Studio instalado (pulado se ausente).

## Conhecimento de domínio descoberto

- **Não existe preset de TPU para bico 0.2** (A1 e A1 mini) — o motor de recomendação não deve sugerir TPU com 0.2.
- `filament_type` tem variantes: `TPU-AMS` (TPU rígido que passa pelo AMS Lite) e `PLA-AERO` (PLA espumante) —
  agrupados nas famílias TPU e PLA (`MATERIAL_FAMILIES`). TPU comum **não** deve ir pelo AMS Lite.
- Filtros do catálogo: `instantiation == "true"`, `compatible_printers` contém a máquina, família suportada,
  `filament_is_support != 1`, `required_nozzle_HRC <= 20` (exclui CF/GF).
- Catálogo atual: A1 e A1 mini × bicos 0.2/0.4/0.6/0.8; ex. A1 0.4 = 10 processos e 37 filamentos.

## Análise geométrica — decisões e limitações (F2)

- **Overhang** segue a convenção do Bambu Studio (`support_threshold_angle`): inclinação da face voltada para
  baixo em relação à horizontal; reportamos 30°/45°/60°. Faces até 0,2 mm da mesa não contam.
- **Espessura de parede** por ray casting (20 mil amostras ponderadas por área) comparada à largura de linha
  de cada bico (1,05 × diâmetro). **Exige `embreex`**: com o ray casting padrão (rtree) uma malha de 2 M de
  faces passou de 10 min; com Embree leva 0,8 s.
- **Orientação**: candidatas = original + até 8 poses estáveis (`trimesh.poses.compute_stable_poses`).
  Pontuação "qualidade primeiro": −3 × overhang + 1 × contato relativo − 0,2 × altura relativa.
- **Fragmentos** (corpo com extensão ≤ 0,5 mm e volume ≤ 0,1 mm³) são descartados — Meshy deixou um assim.
- Malha aberta: volume vira estimativa pelo casco convexo (`volume_is_estimate`).
- Limitações conhecidas: não detecta pontes; **faces internas** (peças sobrepostas sem união booleana)
  geram falso overhang; aviso de unidade só por faixa de tamanho (< 5 mm ou > 1 m).
- Caso de referência: `Meshy_AI_Master Mason with Gavel` (STL 95 MB, ~2 M faces, 26×26×50 mm) → 7 s no total,
  malha fechada após remover 1 fragmento, 9% de overhang a 45°, base plana de 538 mm², melhor orientação = original.

## Regras

- Nunca commitar credenciais (chave Anthropic etc.) — usar `.env` + `.gitignore`.
- Commitar apenas quando o usuário pedir.
- Comunicação com o usuário em **português**.
