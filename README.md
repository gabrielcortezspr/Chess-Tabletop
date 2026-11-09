# Tabletop Voxel: Xadrez & Go

Uma mesa 3D em Python com **tabuleiro de xadrez** e **goban (Go)**, com gráficos
**voxel pixelados** no estilo de jogo retrô. A câmera gira livremente ao redor da
mesa, mas o foco fica sempre no tabuleiro.

- **Modo Jogo**: regras oficiais (xeque, roque, en passant, promoção, mate,
  afogamento, repetição tripla, regra dos 50 lances, material insuficiente; no Go:
  capturas, ko/superko, proibição de suicídio, passes e contagem).
- **Modo Livre**: use o tabuleiro como um tabuleiro de verdade: pegue qualquer
  peça, coloque onde quiser (inclusive nas bandejas ao lado), crie peças novas,
  coloque e tire pedras de Go sem regras. Depois, **Enter** começa uma partida a
  partir da posição montada.
- **Pontuação automática**:
  - Xadrez: material de cada lado (P=1, C=3, B=3, T=5, D=9), pontos capturados,
    resultado detectado sozinho e **placar de partidas** (vitória = 1, empate = ½).
  - Go: capturas, **estimativa ao vivo** do placar, e ao fim (dois passes) a
    contagem por **área (chinesa)** e por **território (japonesa)** com komi.
    As pedras mortas são sugeridas automaticamente e você ajusta com cliques.

![Xadrez](docs/xadrez.png)
![Go - contagem](docs/go.png)

## Instalação

Requer Python 3.9+ e uma placa de vídeo com OpenGL 3.3.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                   # começa no xadrez
python main.py --jogo go         # começa no Go
python main.py --pixel 4         # pixels maiores (1 = sem pixelização)
```

## Controles

### Câmera
| Ação | Comando |
|---|---|
| Girar ao redor do tabuleiro | botão direito + arrastar, `Q`/`E`, setas |
| Deslocar (sempre perto do tabuleiro) | botão do meio + arrastar, `Shift` + botão direito, `W A S D` |
| Zoom | roda do mouse, `PgUp`/`PgDn` |
| Ver do outro lado da mesa | `F` |
| Visão padrão | `Espaço` |

### Geral
| Ação | Tecla |
|---|---|
| Alternar Xadrez / Go | `Tab` |
| Alternar Modo Jogo / Modo Livre | `M` |
| Desfazer | `Z` |
| Nova partida / reiniciar | `R` |
| Tamanho do pixel | `[` e `]` |
| Screenshot (pasta `screenshots/`) | `F12` |
| Ajuda na tela | `H` |
| Sair | `Ctrl+Q` ou fechar a janela |

### Xadrez
- **Modo Jogo**: clique numa peça (os lances legais aparecem em verde, capturas em
  vermelho) e depois no destino. `G` desiste. Na promoção: `1` Dama, `2` Torre,
  `3` Bispo, `4` Cavalo.
- **Modo Livre**: clique para pegar e soltar peças em qualquer casa ou nas bandejas
  laterais (clicar numa casa ocupada troca as peças). `1`–`6` criam uma peça nova
  (peão, cavalo, bispo, torre, dama, rei; com `Shift` ela é preta), `C` troca a cor
  da peça na mão, `Del` descarta, `X` esvazia o tabuleiro (todas as peças vão para as
  bandejas), `R` volta à posição inicial. `Enter` inicia uma partida com as brancas
  jogando (`Shift+Enter`: pretas começam).

### Go
- **Modo Jogo**: clique para jogar (a pedra fantasma mostra se o ponto é legal).
  `P` passa, `G` desiste, `K` muda o komi (0.5 / 5.5 / 6.5 / 7.5), `B` muda o
  tamanho (9×9, 13×13, 19×19), `T` mostra o território estimado.
- **Contagem**: após dois passes seguidos, as pedras mortas são marcadas
  automaticamente (em vermelho). Clique num grupo para alternar morto/vivo, `U`
  refaz a sugestão automática, `V` volta a jogar e `Enter` confirma o resultado.
- **Modo Livre**: clique coloca uma pedra (cor atual, `C` troca, `Shift` usa a outra
  cor) ou remove uma pedra existente. `R` limpa o goban. `Enter` inicia uma partida
  a partir da posição.

## Como funciona

```
main.py                  ponto de entrada
tabletop/
  app.py                 janela pygame + OpenGL, entrada, HUD
  renderer.py            renderizador moderngl: cubos instanciados, sombra,
                         render em baixa resolução + dithering (visual pixelado)
  camera.py              câmera orbital com foco preso ao tabuleiro + picking
  voxels.py              peças de xadrez, pedras e potes gerados em voxels
  chess_rules.py         regras completas de xadrez (sem dependências)
  go_rules.py            regras de Go, contagem e sugestão de pedras mortas
  chess_scene.py         cena do xadrez (modos Jogo/Livre, animações, placar)
  go_scene.py            cena do Go (modos Jogo/Livre, contagem, placar)
tests/                   testes das regras (perft do xadrez, capturas/ko/contagem do Go)
```

O visual pixelado vem de renderizar a cena num framebuffer pequeno
(janela ÷ tamanho do pixel) e ampliá-lo sem suavização, com paleta reduzida e
dithering ordenado. Tudo na cena é feito de cubos.

## Testes

```bash
pip install pytest
python -m pytest
```
