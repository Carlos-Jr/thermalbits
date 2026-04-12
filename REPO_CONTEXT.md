# ThermalBits: contexto do repositório

## Resumo

Este repositório implementa duas camadas:

1. Uma biblioteca Python (`thermalbits`) para ler netlists Verilog combinacionais simples, convertê-los para um formato intermediário próprio chamado `overview`, editar/exportar esse formato, gerar Verilog novamente, visualizar o circuito como DAG e acionar o cálculo de entropia.
2. Um simulador exato em Rust (`thermalbits/iron_circuit_sim`) que recebe o `overview` em JSON, simula o circuito inteiro e calcula a entropia informacional por saída de cada nó e a entropia total do circuito.

Fluxo principal:

`Verilog -> parser Python -> overview -> JSON/edição/Verilog/DAG -> simulador Rust -> entropia total`

O repositório é centrado no `overview`. Ele é o formato padrão compartilhado entre parser, exportação, visualização e simulação.

## O que o repositório faz

- Faz parse de um subconjunto simples de Verilog combinacional.
- Constrói um IR/overview com IDs inteiros para PIs, POs e nós.
- Permite editar `pi`, `po` e `node` diretamente em memória.
- Exporta o estado atual para JSON.
- Reconstrói Verilog a partir do overview atual.
- Visualiza o circuito como DAG em imagem.
- Copia objetos `ThermalBits`.
- Calcula a entropia total do circuito usando o binário Rust.
- Processa circuitos em modo `full` ou em `chunks`, inclusive com merge de parciais.

## Formato padrão da biblioteca: `overview`

Formato canônico atual:

```json
{
  "file_name": "netlist.v",
  "pis": [0, 1],
  "pos": [2],
  "nodes": [
    {
      "id": 2,
      "fanin": [[0, 0], [1, 0]],
      "fanout": [
        {"input": [0, 1], "invert": [0, 1], "op": "&"}
      ],
      "level": 1,
      "suport": [0, 1]
    }
  ]
}
```

Campos de topo:

- `file_name`: nome do arquivo de origem; usado como metadado e base opcional para nome de módulo.
- `pis`: IDs inteiros das entradas primárias.
- `pos`: IDs inteiros das saídas primárias. Cada ID deve apontar para um PI ou para um nó existente.
- `nodes`: lista de nós lógicos.

Campos de cada nó:

- `id`: identificador único do nó.
- `fanin`: lista de referências de entrada no formato `[source_id, output_index]`.
  - `source_id`: ID de um PI ou de outro nó.
  - `output_index`: qual saída do nó de origem está sendo consumida. Para PIs, é sempre `0`.
- `fanout`: lista de saídas produzidas pelo nó. Cada entrada descreve uma saída independente do nó.
- `level`: nível topológico do nó. PIs ficam implicitamente no nível `0`; os nós começam em `1`.
- `suport`: conjunto ordenado dos PIs dos quais o nó depende transitivamente. No JSON/schema do `overview`, a chave usada pelo projeto é literalmente `suport`.

Campos de cada item de `fanout`:

- `input`: índices locais dentro do vetor `fanin`. Ex.: `input: [0, 2]` quer dizer "usa o primeiro e o terceiro item de `fanin`".
- `invert`: flags `0`/`1` alinhadas com `input`; `1` inverte a entrada antes da operação.
- `op`: operador lógico da saída.
  - `"&"`: AND.
  - `"|"`: OR.
  - `"^"`: XOR.
  - `"M"`: majority; exige número ímpar de entradas.
  - `"-"`: wire/pass-through; exige exatamente uma entrada.

Invariantes importantes:

- `pis` e `nodes[*].id` devem usar IDs distintos.
- `fanout[*].input` deve apontar apenas para posições válidas de `fanin`.
- `len(input) == len(invert)` em cada saída.
- Um `PI` só pode ser referenciado com `output_index = 0`.
- O formato suporta nós com múltiplas saídas, embora o parser Python gere apenas uma saída por `assign`.

Observações de compatibilidade:

- O parser Python atual gera um `fanout` por `assign`.
- `write_verilog`, `visualize_dag` e o simulador Rust já suportam nós multi-saída.
- O arquivo `thermalbits/iron_circuit_sim/sin.json` parece legado: usa campo `op` direto no nó, não o schema atual baseado em `fanout`. Para entender o formato atual, use `README.md`, `tests/test_overview_schema.py`, `thermalbits/generate_overview.py` e `thermalbits/iron_circuit_sim/src/circuit.rs`.

## Funcionalidades do módulo `thermalbits`

### Classe `ThermalBits`

Estado principal:

- `verilog_path`: caminho do Verilog de origem.
- `file_name`: nome do arquivo de origem.
- `pi`: lista de IDs de PIs.
- `po`: lista de IDs de POs.
- `node`: lista de nós no schema acima.
- `entropy`: entropia total calculada, ou `None`.

Funcionalidades:

- `ThermalBits(verilog_path=None)`: cria objeto vazio ou, se receber caminho, gera o overview na inicialização.
- `copy()` / `__copy__()` / `__deepcopy__()`: duplica `verilog_path`, `file_name`, `pi`, `po` e `node`. Não copia `entropy`.
- `generate_overview()`: lê o Verilog em `verilog_path`, gera overview e atualiza o estado do objeto.
- `write_json(output_path)`: salva o overview atual em JSON.
- `write_verilog(output_path, module_name=None)`: reconstrói um módulo Verilog a partir do overview atual.
- `visualize_dag(...)`: gera imagem do DAG do circuito.
- `update_entropy(chunks=2, parallel_chunks=2)`: exporta JSON temporário, chama o simulador Rust, armazena o valor em `self.entropy` e retorna o valor.

### Subconjunto de Verilog aceito pelo parser Python

Entradas aceitas:

- declarações `input`, `output`, `wire`;
- atribuições `assign dest = expr;`.

Expressões aceitas:

- sinais simples;
- `~` aplicado diretamente a literal;
- operações binárias de topo apenas com `&` ou `|`;
- constantes de 1 bit: `1'b0` e `1'b1`;
- parênteses para agrupamento.

Restrições:

- só circuitos combinacionais;
- uma atribuição vira um nó;
- não aceita mistura de `&` e `|` na mesma expressão;
- não gera XOR nem majority a partir de Verilog, embora o schema suporte ambos;
- atribuições unárias viram `op: "-"`;
- constantes são reescritas para portas equivalentes usando um sinal âncora existente.

### Como o overview é gerado

Pipeline de `generate_overview()`:

1. `load_verilog()` lê o arquivo e extrai `inputs`, `outputs`, `wires` e `assigns`.
2. `build_gates()` transforma cada `assign` em uma descrição de porta local.
3. `build_drivers()` monta dependências por sinal.
4. `compute_levels()` calcula níveis topológicos.
5. `_build_signal_ids()` atribui IDs inteiros: primeiro PIs, depois saídas de gates.
6. Para cada gate, `_build_node_fanin_and_fanout()` cria `fanin` e o único `fanout` emitido pelo parser.
7. `compute_cone_for_gate()` preenche `suport`.
8. `generate_overview()` salva tudo em `self.file_name`, `self.pi`, `self.po`, `self.node`.

### Verilog de saída

`write_verilog()`:

- valida o overview atual;
- aceita multi-saída;
- gera nomes `pi<ID>`, `n<ID>` e `n<ID>_o<K>`;
- gera `po0`, `po1`, ... para portas de saída;
- usa `level` para ordenar nós;
- suporta `&`, `|`, `^`, `M` e `-`.

Majority é expandido para soma-de-produtos via combinações mínimas; não existe primitive `maj` no Verilog gerado.

### Visualização

`visualize_dag()`:

- lê o overview atual;
- posiciona nós por `level`;
- suporta orientação horizontal ou vertical;
- pode mostrar apenas uma janela de níveis (`level_window`);
- colore PIs, POs e nós internos de forma diferente;
- muda o marcador conforme o operador;
- mostra setas para conexões ocultas quando um recorte de níveis esconde parte do circuito.

### Entropia via Python

`update_entropy()` em Python não implementa a simulação; ele orquestra o binário Rust.

Comportamento:

- por padrão usa `chunks=2`, portanto o default da API Python já é chunk mode;
- `chunks=None` tenta `full` apenas se `max_support <= 25`;
- `chunks=None` com `max_support > 25` gera erro e exige `chunks=<N>`;
- `parallel_chunks` controla quantos subprocessos de chunk rodam simultaneamente;
- cada chunk grava um `.bin` temporário e o merge é feito ao final;
- o overview é serializado para um JSON temporário e apagado depois.

## Funcionalidades do Iron simulator

### O que ele calcula

Para cada saída de cada nó:

- a distribuição conjunta das entradas locais (`joint_counts`);
- o número de vezes em que a saída vale `1` (`pop_y`);
- a entropia local `H(X) - H(Y)`, onde `X` é a distribuição conjunta das entradas da saída e `Y` é a distribuição binária da saída.

A entropia total do circuito é a soma dessas entropias locais.

### Representação interna

Tipos centrais em Rust:

- `Circuit`: PIs, POs, gates, conjunto de PIs, níveis e nível máximo.
- `Gate`: `id`, `fanin`, `fanout` e `support`.
- `FanoutEntry`: índices locais de entrada, flags de inversão e operador.
- `GateResult`: resultado por saída de nó: `gate_id`, `output_index`, `op`, `support_len`, `total`, `joint_counts`, `pop_y`.
- `Op`: enum com `And`, `Or`, `Xor`, `Majority`, `Wire`.

### Modos de simulação

### `full`

Como funciona:

- cada gate é avaliada sobre sua própria tabela-verdade local de tamanho `2^k`, onde `k = len(gate.support)`;
- PIs locais são gerados como bitsets;
- se um fanin vem de um nó com suporte menor, sua tabela é expandida para o suporte atual;
- cada saída do nó é avaliada separadamente;
- resultados são processados por nível topológico, com paralelismo por nível via Rayon;
- sinais que não serão mais usados são liberados via refcount.

Uso recomendado:

- circuitos com `max_support` moderado;
- quando se quer evitar chunking;
- o modo automático do binário usa esse modo apenas se `max_support <= 25`.

### `chunk`

Como funciona:

- simula apenas a fatia global `[start, start + count)`;
- cada sinal é um vetor de palavras de 64 bits cobrindo essa fatia;
- PIs são gerados analiticamente, sem tabela-verdade completa em disco;
- gates são avaliadas por nível topológico;
- cada saída produz seu vetor de bits e também suas contagens;
- pode gravar um parcial binário para merge posterior.

Uso recomendado:

- circuitos grandes;
- execução distribuída;
- quando `max_support` é alto.

Limites práticos:

- o wrapper Python planeja chunks apenas para `n_pis <= 63`, porque precisa que `2^n_pis` caiba em `u64`;
- o kernel Rust aceita até `64` PIs na geração de palavras, mas o fluxo de sweep completo depende do limite acima.

### `auto`, `full`, `chunk` e `merge` na CLI Rust

- `auto`: se receber `--start` ou `--count`, cai em `chunk`; senão usa `full` apenas quando `max_support <= 25`.
- `full`: proíbe `--start`, `--count` e `--binary`.
- `chunk`: aceita `--start`, `--count` e `--binary`.
- `merge`: combina arquivos `.bin` já calculados.

### Como a saída é calculada no nível de bits

Função central: `eval_output_words()`.

Ela:

- aplica as inversões de entrada;
- calcula o vetor de saída por operação bit a bit;
- em paralelo calcula `joint_counts` por padrão binário de entradas;
- usa indexação big-endian para os padrões: a entrada `0` é o bit mais significativo do índice do padrão.

Para `majority`, o cálculo usa `compute_majority_words()`, que monta uma soma por árvore de carry e compara o total com o limiar `n/2 + 1`.

### Merge de parciais

`partial_bin.rs`:

- grava cabeçalho com `magic`, versão, `n_pis`, `start`, `count`, `circuit_hash` e `n_records`;
- grava um registro por saída de nó;
- ao fazer merge, valida `circuit_hash`, `n_pis`, quantidade de registros e sobreposição de intervalos;
- soma `joint_counts` e `pop_y` saída a saída.

### Relatório textual

`report.rs` gera um TXT com uma linha por saída de nó:

- `gate`, `out`, `op`, `k`, `total`;
- `n000...=...` para cada padrão de entrada;
- `y0` e `y1`.

## Inventário de arquivos

### Raiz

- `README.md`: documentação de uso da biblioteca, schema do overview, visualização, Verilog reverso e entropia.
- `LICENSE`: licença MIT.
- `.gitignore`: padrões ignorados pelo Git.
- `pyproject.toml`: metadata do pacote Python e dependências opcionais (`viz`, `dev`).
- `requirements.txt`: dependências para uso com visualização.
- `requirements-dev.txt`: dependências de desenvolvimento.
- `generate_overviews.py`: script de lote para gerar `.json` a partir de todos os `.v` de uma pasta.
- `run_tests.py`: script de lote para calcular entropia de todos os `.v`/`.sv` de uma pasta e registrar resultados; apesar do nome, não roda a suíte `pytest`.
- `dag_horizontal_test.png`: exemplo de DAG horizontal gerado do `test_files/simple.v`.
- `dag_vertical_window_test.png`: exemplo de DAG vertical com janela de níveis.

### Biblioteca Python: `thermalbits/`

#### `thermalbits/__init__.py`

- Papel: expõe `ThermalBits` e `__version__`.
- Sem funções.

#### `thermalbits/thermalbits.py`

- Papel: classe fachada; conecta métodos definidos em arquivos separados.
- `class ThermalBits`: agrega `__init__`, cópia, geração de overview, exportação, visualização e entropia.

#### `thermalbits/_init_method.py`

- Papel: inicialização do objeto.
- `init_thermalbits`: inicializa estado vazio; se `verilog_path` existir, chama `generate_overview()`.

#### `thermalbits/copy_methods.py`

- Papel: cópia do objeto.
- `copy_thermalbits`: cria clone profundo de `verilog_path`, `file_name`, `pi`, `po` e `node`.
- `deepcopy_dunder`: alias para `copy_thermalbits`.

#### `thermalbits/generate_overview.py`

- Papel: converter Verilog em overview e serializar o estado atual.
- `_build_signal_ids`: atribui IDs inteiros a PIs e saídas de gates.
- `_build_node_fanin_and_fanout`: transforma um gate interno em `fanin` e em um item de `fanout`.
- `_compute_overview`: pipeline completo de parse e montagem do JSON intermediário.
- `generate_overview`: executa `_compute_overview` a partir de `self.verilog_path` e atualiza o objeto.
- `_state_overview`: extrai o estado atual do objeto no schema padrão.
- `write_json`: salva o overview atual em disco.

#### `thermalbits/verilog_utils.py`

- Papel: parser e normalização do subconjunto Verilog aceito.
- `_strip_comments`: remove comentários `//` e `/* ... */`.
- `_is_signal_name`: valida identificadores simples e escaped.
- `_is_const_token`: reconhece constantes binárias do tipo `N'b...`.
- `_parse_const_token`: aceita apenas constantes binárias de 1 bit com valor `0` ou `1`.
- `parse_signal_list`: normaliza listas de `input`, `output` e `wire`.
- `parse_verilog`: extrai `inputs`, `outputs`, `wires` e `assigns`.
- `_tokenize_expr`: tokeniza expressões lógicas.
- `_top_level_binary_ops`: detecta operadores binários no nível externo.
- `_is_outer_parenthesized`: testa se a expressão inteira está embrulhada por um par de parênteses externo.
- `_strip_outer_parentheses`: remove parênteses externos redundantes.
- `extract_deps`: extrai sinais conhecidos usados na expressão.
- `compute_levels`: calcula níveis topológicos dos sinais.
- `_parse_gate_literal_tokens`: normaliza um literal possivelmente invertido.
- `_collect_gate_literals`: coleta literais de uma expressão homogênea em `&` ou `|`.
- `_literal_const_value`: converte literal constante com inversão em bit efetivo.
- `_pick_anchor_signal`: escolhe um sinal existente para materializar constantes como porta.
- `_const_to_gate`: converte `0`/`1` em uma porta equivalente baseada em um sinal âncora.
- `extract_gate_from_expr`: converte uma expressão em `(op, fanin)` segundo as regras do parser.
- `build_gates`: gera descrições internas de gate para cada `assign`.
- `build_drivers`: monta o mapa de dependências por saída.
- `compute_cone_for_gate`: calcula o cone transitivo de PIs de um nó.
- `load_verilog`: lê arquivo e chama `parse_verilog`.

#### `thermalbits/overview_to_verilog.py`

- Papel: validar o overview atual e gerar Verilog.
- `_require_int_list`: valida listas inteiras como `pis` e `pos`.
- `_sanitize_module_name`: sanitiza nome de módulo.
- `_literal_expr`: aplica `~` quando necessário.
- `_join_terms`: junta termos com um operador binário.
- `_majority_expr`: expande majority em soma-de-produtos.
- `_parse_nodes`: valida e normaliza `nodes`, `fanin`, `fanout`, `level`.
- `_fanout_expr`: monta a expressão Verilog de uma saída específica de um nó.
- `write_verilog`: gera o arquivo Verilog final.

#### `thermalbits/visualize_dag.py`

- Papel: desenhar o overview como DAG.
- `_parse_level_window`: valida janela de níveis.
- `_node_role`: classifica nó como `input`, `output`, `input_output` ou `internal`.
- `_node_color`: escolhe cor por papel do nó.
- `_node_marker`: escolhe marcador por operador/tipo.
- `_gate_label`: gera texto mostrado sobre o nó.
- `_group_by_level`: agrupa IDs por nível.
- `_build_positions`: calcula coordenadas dos nós e limites da figura.
- `visualize_dag`: renderiza e salva a imagem do DAG.

#### `thermalbits/update_entropy.py`

- Papel: ponte Python para o simulador Rust.
- `_check_binary`: verifica se o binário release existe.
- `_parse_entropy`: extrai `total_circuit_entropy` do stdout do binário.
- `_run_full`: executa o binário em modo `full`.
- `_build_chunk_plan`: particiona o espaço de vetores em chunks balanceados.
- `_run_chunks_parallel`: executa batches de subprocessos chunk, faz merge e devolve a entropia.
- `update_entropy`: escolhe modo, escreve JSON temporário, chama o binário e armazena `self.entropy`.

### Scripts e testes Python

#### `generate_overviews.py`

- `generate_overviews`: gera um overview `.json` para cada `.v` em uma pasta.
- `main`: CLI do script.

#### `run_tests.py`

- `parse_args`: lê argumentos do script de lote.
- `find_verilog_files`: encontra `.v` e `.sv` recursivamente.
- `format_result`: formata uma linha de resultado com timestamp e tempo.
- `write_line`: escreve no stdout e no arquivo de log.
- `main`: percorre arquivos, cria `ThermalBits`, calcula entropia e registra sucesso/erro.

#### `tests/test_overview_schema.py`

- `test_compute_overview_uses_fanout_schema`: valida o schema atual com `fanout`.
- `test_compute_overview_uses_wire_fanout_for_unary_assign`: valida emissão de `op "-"` para atribuição unária.
- `test_write_verilog_supports_multi_output_nodes`: valida Verilog reverso para nó multi-saída.
- `test_sin_epfl_entropy_matches_expected_value`: valida entropia do benchmark `sin`.

### Simulador Rust: `thermalbits/iron_circuit_sim/`

#### `thermalbits/iron_circuit_sim/README.md`

- Papel: documentação do simulador, CLI, schema e modos.

#### `thermalbits/iron_circuit_sim/Cargo.toml`

- Papel: configuração do crate Rust e dependências (`serde`, `serde_json`, `rayon`).

#### `thermalbits/iron_circuit_sim/Cargo.lock`

- Papel: lockfile das dependências Rust.

#### `thermalbits/iron_circuit_sim/sin.json`

- Papel: grande exemplo de circuito em JSON.
- Observação: parece estar em schema legado, não no schema atual com `fanout`.

#### `thermalbits/iron_circuit_sim/src/lib.rs`

- Papel: expõe os módulos `app`, `circuit`, `cli`, `io`, `sim`, `stats`.
- Sem funções.

#### `thermalbits/iron_circuit_sim/src/main.rs`

- `main`: ponto de entrada; faz parse da CLI e chama `app::run`.

#### `thermalbits/iron_circuit_sim/src/cli.rs`

- Papel: parser manual da linha de comando.
- `Command`: enum `Sim` ou `Merge`.
- `SimulationMode`: enum `Auto`, `Full`, `Chunk`.
- `SimArgs`: argumentos de simulação.
- `MergeArgs`: argumentos de merge.
- `SimulationMode::parse`: valida o valor de `--mode`.
- `parse_args`: converte `argv` em `Command`.

#### `thermalbits/iron_circuit_sim/src/app.rs`

- Papel: orquestra execução.
- `ExecutionPlan`: enum interno `Full` ou `Chunk { start, count }`.
- `run`: despacha para simulação ou merge.
- `run_sim`: carrega circuito, resolve modo, executa simulação, escreve relatório e imprime entropia.
- `run_merge`: faz merge de parciais, escreve relatório e imprime entropia.
- `resolve_execution_plan`: escolhe `full` ou `chunk` conforme CLI e `max_support`.
- `resolve_chunk_plan`: normaliza `start` e `count`.
- `max_support_len`: calcula o maior suporte do circuito.
- `ensure_full_mode_supported`: bloqueia `full` se o suporte exceder o limite da plataforma.
- `default_chunk_count`: define sweep completo `2^n_pis` para chunk sem `--count`.
- `exit_with_cli_error`: imprime erro e termina o processo.

#### `thermalbits/iron_circuit_sim/src/circuit.rs`

- Papel: domínio interno do circuito e parser do JSON.
- `CircuitJson`, `NodeJson`, `FanoutJson`: structs de desserialização.
- `Op`: enum de operadores.
- `FanoutEntry`: saída normalizada de nó.
- `Gate`: gate normalizada.
- `Circuit`: circuito inteiro indexado por níveis.
- `load_circuit`: lê JSON, valida fanouts, cria `Circuit` e calcula hash FNV-1a do arquivo.
- `fnv1a_hash`: hash usado para validar parciais no merge.

#### `thermalbits/iron_circuit_sim/src/stats.rs`

- Papel: entropia.
- `entropy`: Shannon entropy de um vetor de contagens.
- `total_entropy`: soma `H(X) - H(Y)` para todos os `GateResult`.

#### `thermalbits/iron_circuit_sim/src/sim/mod.rs`

- Papel: agrega os motores de simulação.
- Sem funções.

#### `thermalbits/iron_circuit_sim/src/sim/shared.rs`

- Papel: utilitários comuns a `full` e `chunk`.
- `GateResult`: estrutura de resultado por saída.
- `num_words`: calcula quantidade de palavras de 64 bits para um número de bits.
- `mask_last_word`: mascara bits excedentes da última palavra de uma tabela-verdade local.
- `last_word_mask_from_total`: máscara da última palavra para uma fatia de tamanho arbitrário.
- `eval_output_words`: avalia uma saída do nó e calcula vetor de saída, `joint_counts` e `pop_y`.
- `compute_majority_words`: implementa majority por soma e comparação de limiar.
- `compute_gate_refcounts`: conta quantas vezes cada sinal ainda será consumido.
- `release_refcount`: decrementa refcount e informa se o sinal já pode ser liberado.

#### `thermalbits/iron_circuit_sim/src/sim/full.rs`

- Papel: simulação exata por tabela-verdade local.
- `truth_table_bits`: calcula `2^k` com checagem.
- `truth_table_total`: mesmo cálculo em `u64` para total de vetores.
- `gen_pi_tt`: gera tabela-verdade de um PI sobre um suporte local.
- `expand_tt`: expande uma tabela-verdade de suporte menor para suporte maior.
- `resolve_fanin_tt`: obtém a tabela-verdade de um fanin no suporte do gate atual.
- `process_circuit`: processa o circuito nível a nível, em paralelo por nível, e produz `GateResult`.

#### `thermalbits/iron_circuit_sim/src/sim/chunk.rs`

- Papel: simulação de uma faixa da tabela-verdade global.
- `STANDARD_PI_WORDS`: padrões base para gerar PIs nos primeiros 6 bits.
- `gen_pi_word`: gera uma palavra de um PI para a posição global desejada.
- `resolve_fanin_sig`: resolve o vetor de palavras de um fanin.
- `simulate_chunk`: processa um chunk inteiro do circuito e produz `GateResult`.

#### `thermalbits/iron_circuit_sim/src/io/mod.rs`

- Papel: agrega módulos de I/O.
- Sem funções.

#### `thermalbits/iron_circuit_sim/src/io/report.rs`

- Papel: relatório textual.
- `write_counts_file`: escreve o TXT com contagens por saída.

#### `thermalbits/iron_circuit_sim/src/io/partial_bin.rs`

- Papel: serialização e merge de parciais binários.
- `PartialData`: estrutura interna usada na leitura.
- `op_to_byte`: codifica `Op` para o formato binário.
- `byte_to_op`: decodifica `Op` do formato binário.
- `write_partial_bin`: grava um parcial `.bin`.
- `read_partial_bin`: lê um parcial `.bin`.
- `merge_partials`: valida e combina vários parciais.

#### `thermalbits/iron_circuit_sim/scripts/run_parallel_chunks.py`

- Papel: utilitário externo para rodar vários chunks em paralelo e fazer merge.
- `parse_args`: lê argumentos.
- `load_metadata`: extrai metadados do JSON do circuito.
- `build_or_find_binary`: usa `SIM_BIN` ou faz `cargo build --release`.
- `build_chunk_plan`: divide o espaço global em chunks balanceados.
- `parse_entropy`: extrai entropia do stdout do merge.
- `run_parallel_chunks`: executa todos os processos chunk, faz merge e imprime resumo CSV-like.
- `main`: ponto de entrada do script.

### Fixtures, benchmarks e exemplos

- `test_files/simple.v`: circuito pequeno usado nos exemplos de visualização.
- `test_files/EPFL/{cavlc,ctrl,dec,int2float,sin}.v`: benchmarks EPFL em Verilog.
- `test_files/EDGE/{C6288,apex2,b3,b4,bc0,bca,bcb,bcc,bcd,chkn,cps,duke2,exep,in3,in4,in5,in6,jbp,log2,mainpla,mark1,seq,signet,sin,t1,term1,too_large,x6dn,xparc}.v`: benchmarks EDGE em Verilog.
- `test_files/EDGE/{...}.json`: overviews JSON correspondentes aos benchmarks EDGE.
- `thermalbits/iron_circuit_sim/test_files/EDGE/{C6288,apex2,b3,b4,bc0,bca,bcb,bcc,bcd,chkn,cps,duke2,exep,in3,in4,in5,in6,jbp,log2,mainpla,mark1,seq,signet,sin,t1,term1,too_large,x6dn,xparc}.v`: cópia de benchmarks EDGE dentro do subprojeto Rust.

## Leitura operacional rápida para outro LLM

- O centro do projeto é o `overview`.
- O parser Python gera apenas um `fanout` por nó, mas o schema e o simulador aceitam múltiplos.
- No JSON/schema do `overview`, a chave é `suport`.
- Em estruturas internas do código, especialmente no Rust, aparecem nomes como `support` e `support_len`; isso não contradiz o schema serializado.
- A API Python defaulta para chunk mode (`update_entropy()` usa `chunks=2`).
- O binário Rust faz a simulação real; Python só prepara JSON, orquestra processos e lê a entropia.
- O schema atual está garantido pelos testes em `tests/test_overview_schema.py`.
