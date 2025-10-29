# Rotating Triangles (GLUT)

Este repositório implementa um cenário mínimo inspirado no exemplo
[InstancedVsMultiDrawRendering](https://github.com/BoyBaykiller/InstancedVsMultiDrawRendering)
utilizando GLUT para desenhar triângulos coloridos em rotação. A aplicação
suporta texturas procedurais, luzes omnidirecionais ou spotlight e expõe dados
de FPS via `stdout` para uso em benchmarks automatizados. Scripts auxiliares
coletam métricas de CPU/GPU, verificam as GPUs disponíveis e geram gráficos de
comparação.

> **Importante:** este ambiente de execução não possui uma GPU disponível nem
> oferece suporte a janelas gráficas. Compile e execute o projeto localmente em
> uma máquina com drivers OpenGL/GLUT instalados para visualizar o cenário e
> coletar medições de desempenho reais.

## Requisitos

- Compilador C++17
- [CMake](https://cmake.org/)
- Bibliotecas OpenGL e GLUT (por exemplo, `freeglut`)
- Python 3.9+
- Dependências Python: `matplotlib`, `pandas`, `numpy`, `psutil`, `nvidia-ml-py3`

Em distribuições baseadas em Debian/Ubuntu, as dependências de sistema podem ser
instaladas com:

```bash
sudo apt-get install build-essential cmake freeglut3-dev libglu1-mesa-dev
```

E as bibliotecas Python:

```bash
pip install -r requirements.txt
```

## Compilação

```bash
cmake -S . -B build
cmake --build build
```

O executável `triangle_demo` será gerado dentro da pasta `build/`.

## Uso interativo

```bash
./build/triangle_demo --triangles 12 --lighting spot
```

- A animação roda automaticamente; não há interação por teclado/mouse.
- O título da janela (no FreeGLUT) mostra FPS, modo de iluminação e se a
  textura está habilitada.

Opções principais:

- `--triangles <N>`: define o número de triângulos (mínimo 1).
- `--lighting <modo>`: seleciona a iluminação (`none`, `point`, `spot` ou `both`).
- `--no-texture`: desativa o uso da textura procedural.
- `--benchmark`: executa em modo automático, registrando FPS no stdout e
  encerrando após o período configurado.
- `--duration <segundos>`: altera a duração do benchmark (padrão 10 s).
- `--show-log`: ao usar `--benchmark`, mantém os logs de FPS instantâneo no
  terminal.

## Benchmark automatizado

O script `scripts/run_benchmark.py` executa o binário para diferentes combinações
de quantidade de triângulos, modos de iluminação e uso de textura. Enquanto o
processo roda, o script coleta métricas de CPU (via `psutil`) e GPU (via NVML,
quando disponível) para responder às questões de uso de hardware.

```bash
python scripts/run_benchmark.py \
  --triangles 1,100,1000,10000,30000,100000,200000,300000 \
  --lighting-modes none,point,spot,both \
  --textured both \
  --duration 10
```

O script salva os resultados em `data/metrics.csv` (por padrão) com colunas para
FPS médio, uso médio/máximo de CPU (total e por processo), utilização da GPU
(incluindo percentuais do motor e da memória, consumo de memória em MB,
temperatura, potência e clocks médios/máximos), número e nomes de GPUs
detectadas, bem como observações sobre a coleta:

```
triangles,lighting,textured,duration_s,avg_fps,cpu_percent_mean,...,gpu_count,gpu_names,...
1,none,yes,5,742.1824,12.5010,...,0,,psutil not installed;...
```

Ao iniciar, o script imprime `SYSTEM_INFO` com o processador identificado,
lista de GPUs (indicando a memória disponível, útil para placas como a RTX 3050)
e eventuais avisos (por exemplo, ausência de NVML). Essas informações também
são registradas na coluna `notes` do CSV.

## Geração do gráfico

Com o CSV produzido pelo benchmark, gere o gráfico de FPS vs quantidade de
triângulos:

```bash
python scripts/plot_fps.py data/metrics.csv --output data/fps_plot.png
```

Passe `--textured any` para comparar execuções com e sem textura, ou
`--lighting none,spot` para focar em modos específicos.

Para analisar CPU/GPU, gere também o gráfico combinado (que cria painéis para
CPU, utilização da GPU, uso de memória de vídeo, temperatura, potência e
frequências sempre que os dados estiverem disponíveis):

```bash
python scripts/plot_resource_usage.py data/metrics.csv --output data/resource_usage.png
```

## Limitações e dicas

- Em ambientes sem suporte a janelas (por exemplo, contêineres headless), a
  execução do binário falhará. Utilize um computador local com GPU.
- Ajuste a duração do benchmark para obter medições estáveis. Intervalos mais
  longos reduzem flutuações, especialmente ao avaliar contagens altas como
  100&nbsp;000, 200&nbsp;000 ou 300&nbsp;000 triângulos.
- Execute as quatro combinações de iluminação (`none`, `point`, `spot`, `both`)
  com e sem textura para comparar o impacto de cada fonte de luz na carga da
  GPU e do processador.
- Caso deseje comparar implementações diferentes, mantenha o formato
  `FPS_RESULT` (com campos `triangles`, `lighting`, `textured`, `avg_fps`) para
  que os scripts continuem compatíveis.
- O script de benchmark identifica automaticamente a disponibilidade de GPUs via
  NVML. Em ambientes sem GPU ou sem `nvidia-ml-py3`, a coluna `notes` registra o
  motivo e as curvas de GPU aparecerão vazias.

## Estrutura do repositório

```
CMakeLists.txt                   # Configuração do build C++
src/main.cpp                     # Aplicação GLUT com texturas, luzes e FPS logging
scripts/run_benchmark.py         # Benchmarks e coleta de métricas de CPU/GPU
scripts/plot_fps.py              # Gera gráfico de FPS vs quantidade de triângulos
scripts/plot_resource_usage.py   # Gera gráfico de CPU/GPU vs quantidade de triângulos
requirements.txt                 # Dependências Python para os scripts
data/                            # Resultados e gráficos gerados (ignorado pelo Git)
```

## Licença

Este projeto segue a licença MIT. Consulte `LICENSE` caso necessário.
