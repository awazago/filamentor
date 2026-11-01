# Versão realista via IA — São Miguel Arcanjo

Fluxo: **imagem-conceito original** → **imagem para 3D** (Hitem3D ou Meshy) → `preparar_modelo.py`
(reparo, base plana, 150 mm, análise) → Bambu Studio.

> Gere uma imagem **original** em vez de subir fotos de estátuas comerciais ou artes de terceiros
> direto no gerador 3D: evita copiar o desenho de alguém e deixa a coleção livre para
> MakerWorld / venda no futuro. As referências servem de inspiração para pose e estilo.

## 1. Imagem-conceito (ChatGPT, Gemini, Midjourney ou FLUX)

Regras que tornam o resultado **imprimível sem desperdício**: corpo inteiro, fundo liso, vista
frontal levemente 3/4, asas encostadas no manto (não abertas no ar), lança/espada tocando a base,
nada fino e solto, base redonda maciça.

**Variante A — Triunfante** (inspirada nas referências 3 e 4)

```text
Full-body studio photo of a classical white Carrara marble statue of Saint Michael the Archangel,
realistic Renaissance sculpture style. He stands on a round rocky base, his right foot on a coiled
dragon. His right hand holds a long spear topped with a Latin cross, the spear tip resting on the
dragon's head. His left arm holds a round shield against his body. Large detailed feathered wings
folded slightly upward and touching his flowing cape behind him. Roman armor with leather strips,
serene noble face, curly hair, small halo attached to the back of the head. Compact silhouette,
no thin floating parts. Entire statue visible, centered, front three-quarter view, plain light
grey seamless background, soft even lighting, sharp detail.
```

**Variante B — Guardião ajoelhado** (inspirada na referência 1; mais compacta e fácil de imprimir)

```text
Full-body studio photo of a classical white Carrara marble statue of Saint Michael the Archangel
kneeling on one knee on a round rocky base, head bowed in prayer, both hands resting on the
crossguard of a broad sword whose tip touches the base. Ornate Roman armor with a lion face on
the breastplate, leather strips, cape draped over the knee, large feathered wings folded close to
his back and reaching down to the base. Realistic Renaissance sculpture style, compact silhouette,
no thin floating parts. Entire statue visible, centered, front three-quarter view, plain light
grey seamless background, soft even lighting, sharp detail.
```

Gere 4–6 opções e escolha a que tiver **silhueta mais compacta** e mãos/rosto mais limpos.

## 2. Imagem → 3D

| Ferramenta | Configuração |
|---|---|
| **Hitem3D** | Image to 3D, maior resolução de geometria (1536/2K), **sem textura** (vai ser uma cor), exportar **STL** ou GLB |
| **Meshy** | Image to 3D, modelo mais recente, *Topology: Triangle*, *Polycount: High*, **Texture off**, *Symmetry: Auto*, exportar **STL** |

Se o gerador aceitar várias vistas (frente/lado/costas), gere-as a partir da mesma imagem-conceito:
asas e costas saem bem melhores.

## 3. Preparar para a A1 / A1 mini

```bash
.venv/bin/python colecao-santos/preparar_modelo.py ~/Downloads/sao_miguel.stl --altura 150 --pedestal
# GLB/OBJ (Y para cima):  acrescentar --eixo-y-para-cima
# frente virada para o lado errado:  --girar-z 90 (ou 180)
```

O script repara a malha (furos, fragmentos, cascas internas), escala para 150 mm, aplaina a base,
adiciona pedestal chanfrado e imprime a análise (overhang, paredes finas, se cabe na A1 / A1 mini).
**Meta:** overhang a 45° ≤ 5 % e paredes finas (bico 0.4) ≤ 1 %. Acima disso, gere de novo com uma
pose mais compacta antes de gastar filamento.

## 4. Mármore + dourado — opções

| Opção | Desperdício | Resultado | Recomendação |
|---|---|---|---|
| **Imprimir em mármore e dourar à mão** (Rub 'n Buff Gold Leaf, caneta Posca/Molotow Liquid Chrome) nas penas, bordas da armadura, auréola, cruz e friso do pedestal | **zero** | o mais parecido com as referências: dourado só nos detalhes | ✅ **melhor custo × resultado** |
| **Peças separadas** (asas, auréola, lança, escudo) impressas em PLA Silk dourado e coladas com pinos de encaixe | zero (troca manual de carretel) | dourado "de verdade", sem pintura | ✅ boa para a fase 2 da coleção |
| **AMS Lite pintando cores no Bambu Studio** | **alto**: o dourado aparece em quase todas as alturas (asas, armadura), então cada camada troca de filamento → purga + torre podem pesar **mais que a estátua** | bom, mas caro | ❌ só se o dourado ficar numa faixa de altura (ex.: só o friso da base) |
