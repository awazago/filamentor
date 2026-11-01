# Coleção de Santos — Filamentor

Estátuas católicas geradas por código (SDF → malha), pensadas para **uma cor (PLA mármore branco)**
nas Bambu Lab **A1 / A1 mini**: detalhe visível, mínimo de suporte e pouco filamento.

| # | Santo | Arquivo | Dimensões (padrão) |
|---|-------|---------|--------------------|
| 1 | São Miguel Arcanjo | `saida/sao_miguel_arcanjo_150mm.3mf` | 80,8 × 80,8 × 150 mm |

Padrão da coleção: **150 mm de altura** (cabe na A1 mini; cabe até 180 mm nela e 256 mm na A1).

## Gerar / regerar

```bash
.venv/bin/pip install scikit-image fast-simplification matplotlib   # além do ".[dev]"
cd colecao-santos
../.venv/bin/python sao_miguel.py --altura 150 --voxel 0.25          # ~1 min → saida/*.stl + *.3mf
../.venv/bin/python preview.py saida/sao_miguel_arcanjo_150mm.stl saida/preview_sao_miguel.png
```

O STL (~80 MB) não é versionado; o 3MF (mesma malha, compactado) é.

## São Miguel Arcanjo — o que foi feito para economizar filamento e suporte

- Tudo nasce da base: **asas descem até o pedestal**, manto vai até a rocha, lança crava no dragão,
  escudo apoia a ponta no dragão → a peça cresce de baixo para cima sem "ilhas".
- Braços descem do ombro até um ponto apoiado (mão na lança / no escudo); o antebraço direito
  vira uma **ponte** curta entre cotovelo e lança.
- Barra da túnica com fundo **cônico a 45°**, auréola em **disco** (sem teto), cruz da lança com
  seção em **losango** (faces a 45°).
- Base plana Ø 70 mm (área de contato ~51 cm²) → **sem brim**.

Análise do Filamentor (`analysis.analyze`) no arquivo final: malha fechada, 1 corpo, 0 defeitos,
1,65 M triângulos; overhang **2,2 % da superfície a 45°** (1,4 % a 30°); parede mais fina p5 = 2,2 mm
(só 0,2 % abaixo da largura de linha do bico 0.4); melhor orientação = em pé, como está.

## Configuração recomendada (Bambu Studio)

| Item | Valor | Por quê |
|---|---|---|
| Impressora / bico | A1 ou A1 mini, **0.4 mm** | detalhe × tempo; 0.2 só se for reduzir a escala |
| Filamento | PLA mármore branco (ex.: Bambu PLA Marble *White Marble*) | confirmar o preset na lista do Bambu Studio |
| Processo base | **0.12mm Fine @BBL A1 / A1M** (alternativa: 0.16mm Optimal) | rosto, cachos e penas pedem camada fina |
| Paredes | **2** | as partes finas (asas, penas, lança) já saem maciças |
| Topo / fundo | 5 / 3 camadas | |
| Preenchimento | **Lightning (relâmpago) 10 %** | só sustenta os topos — o mais econômico para estátua |
| Suporte | Ativar, **tree (auto)**, limite 30° | poucos pontos (cotovelos, queixo, borda de penas); conferir na pré-visualização |
| Brim | Não | base larga e plana |
| Costura | **Atrás** (back) | esconde a costura no manto |

Estimativa provisória (cálculo pelo volume/área, **não** fatiado): **~65–80 g** a 150 mm
(maciço seria ~185 g); a 120 mm, ~40–50 g. O valor real sai do fatiamento no Bambu Studio.
