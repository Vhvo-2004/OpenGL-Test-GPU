# Rotating Triangles (GLUT)

Este repositório implementa um cenário mínimo inspirado no exemplo
[InstancedVsMultiDrawRendering](https://github.com/BoyBaykiller/InstancedVsMultiDrawRendering)
utilizando GLUT para desenhar triângulos coloridos em rotação. Ele também
oferece utilitários para medir o FPS conforme a quantidade de triângulos
renderizados e gerar um gráfico com os resultados.

> **Importante:** este ambiente de execução não possui uma GPU disponível nem
> oferece suporte a janelas gráficas. Compile e execute o projeto localmente em
> uma máquina com drivers OpenGL/GLUT instalados para visualizar o cenário e
> coletar medições de desempenho reais.

## Requisitos

- Compilador C++17
- [CMake](https://cmake.org/)
- Bibliotecas OpenGL e GLUT (por exemplo, `freeglut`)
- Python 3.9+
- Dependências Python: `matplotlib`, `pandas`

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
./build/triangle_demo --triangles 12
```

- **Setas do sistema**: não há interação via teclado/mouse; a animação roda
  automaticamente.
- A janela exibe triângulos coloridos girando em torno do centro. A cada segundo
  o título é atualizado com o FPS médio (requer freeglut).

Opções principais:

- `--triangles <N>`: define o número de triângulos (mínimo 1).
- `--benchmark`: executa em modo automático, registrando FPS no stdout e
  encerrando após o período configurado.
- `--duration <segundos>`: altera a duração do benchmark (padrão 10 s).
- `--show-log`: ao usar `--benchmark`, mantém os logs de FPS instantâneo no
  terminal.

## Benchmark automatizado

O script `scripts/run_benchmark.py` compila um CSV contendo o FPS médio para
várias quantidades de triângulos. Por padrão, ele espera que `triangle_demo`
ja tenha sido compilado em `build/`.

```bash
python scripts/run_benchmark.py --triangles 1,5,10,25,50 --duration 5
```

O script salva os resultados em `data/fps_results.csv`:

```
triangles,avg_fps
1,742.182403
5,612.904175
...
```

## Geração do gráfico

Com o CSV produzido pelo benchmark, gere o gráfico de FPS vs quantidade de
triângulos:

```bash
python scripts/plot_fps.py data/fps_results.csv --output data/fps_plot.png
```

O gráfico resultante será salvo em `data/fps_plot.png`.

## Limitações e dicas

- Em ambientes sem suporte a janelas (por exemplo, contêineres headless), a
  execução do binário falhará. Utilize um computador local com GPU.
- Ajuste a duração do benchmark para obter medições estáveis. Intervalos mais
  longos reduzem flutuações.
- Caso queira comparar implementações diferentes (instanced vs draw calls,
  por exemplo), reutilize o formato de saída `FPS_RESULT` para facilitar a
  análise com os scripts fornecidos.

## Estrutura do repositório

```
CMakeLists.txt           # Configuração do build C++
src/main.cpp             # Aplicação GLUT com triângulos girando
scripts/run_benchmark.py # Executa benchmarks automatizados
scripts/plot_fps.py      # Gera gráfico de FPS
requirements.txt         # Dependências Python para os scripts
data/                    # Resultados e gráficos gerados (ignorado pelo Git)
```

## Licença

Este projeto segue a licença MIT. Consulte `LICENSE` caso necessário.
