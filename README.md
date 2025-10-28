# OpenGL Rotating Triangles Benchmark

Este repositório contém uma aplicação OpenGL escrita em Python para analisar o impacto do número de triângulos texturizados e iluminados no FPS. Inclui scripts para coleta de métricas de hardware e geração de relatórios em \LaTeX.

## Pré-requisitos

1. Python 3.10+
2. Dependências:

```bash
pip install -r requirements.txt
```

> \*\*Observação importante:\*\* a execução da aplicação requer suporte a OpenGL 3.3 ou superior, disponível apenas em ambientes com aceleração gráfica. Os testes não foram executados neste ambiente de desenvolvimento por ausência de GPU.

## Executando a aplicação

Para visualizar um triângulo girando com textura e iluminação omnidirecional:

```bash
python run_app.py
```

Parâmetros úteis:

- `--triangles N`: define o número de triângulos renderizados.
- `--light {omnidirectional,spot,directional}`: alterna o modo de iluminação.
- `--texture CAMINHO`: define uma textura externa. Quando omitido, o programa gera uma textura
  procedural (gradiente) em tempo de execução. Como o repositório não versiona binários, adicione
  texturas personalizadas localmente.
- `--benchmark`: encerra automaticamente após o tempo definido em `--duration` (segundos).
- `--headless`: utiliza uma janela 1x1 para execuções remotas.
- `--monitor-usage`: ativa a coleta contínua de uso de CPU/GPU (habilitado automaticamente no modo benchmark).
- `--monitor-interval`: define o intervalo entre amostras de uso (padrão: 1 segundo).

## Benchmark automatizado

```bash
python scripts/run_benchmark.py --counts 1 10 25 50 100 250 --lights omnidirectional spot --duration 10
```

Os resultados abrangem FPS médio/máximo/mínimo por quantidade de triângulos e modo de iluminação, além do uso médio/máximo de CPU e GPU quando disponível. As medições são gravadas em `data/benchmark_results.json`.

Para gerar gráficos comparativos (FPS, uso de CPU e uso de GPU) execute:

```bash
python scripts/plot_results.py
```

O script cria `docs/figures/fps_vs_triangles.png` com três painéis comparando os modos de iluminação analisados.
Esse arquivo é gerado localmente e ignorado pelo controle de versão para evitar inclusão de binários.

## Coleta de informações de hardware

```bash
python scripts/system_probe.py --duration 10 --interval 1
```

O comando tenta identificar CPU, GPUs disponíveis e estatísticas de utilização durante o período informado. Se houver múltiplas GPUs, o arquivo `data/system_probe.json` listará a utilização média/máxima de cada uma.

## Relatório

O relatório em \LaTeX está em `docs/report.tex`, pronto para ser importado no Overleaf. Atualize a tabela e os gráficos após coletar dados reais.

## Limitações conhecidas

- Este repositório não inclui dados reais de FPS ou utilização de GPU/CPU devido à ausência de uma GPU no ambiente de desenvolvimento.
- Alguns recursos (como captura de utilização em tempo real) dependem de ferramentas externas (`nvidia-smi`) e bibliotecas como `psutil`.

## Licença

MIT
