//! Objetivo: orquestrar os fluxos de simulacao e merge da aplicacao.
//! Entradas: `Command` parseado, arquivos de circuito/partials e parametros da execucao.
//! Saidas: arquivos de saida, partials binarios opcionais e entropia total impressa.

use std::time::Instant;

use crate::circuit::{load_circuit, Circuit};
use crate::cli::{Command, MergeArgs, SimArgs, SimulationMode};
use crate::io::partial_bin::{merge_partials, write_partial_bin};
use crate::io::report::write_counts_file;
use crate::sim::chunk::simulate_chunk;
use crate::sim::full::process_circuit;
use crate::stats::total_entropy;

const AUTO_FULL_MAX_SUPPORT: usize = 25;

enum ExecutionPlan {
    Full,
    Chunk { start: u64, count: u64 },
}

pub fn run(command: Command) {
    match command {
        Command::Sim(args) => run_sim(args),
        Command::Merge(args) => run_merge(args),
    }
}

fn run_sim(args: SimArgs) {
    let t0 = Instant::now();

    eprintln!("Loading circuit from {} ...", args.input);
    let (circuit, circuit_hash) = load_circuit(&args.input);
    let max_support = max_support_len(&circuit);
    eprintln!(
        "  {} PIs, {} POs, {} gates, max level {}, max support {}  (hash={:#018x})",
        circuit.pis.len(),
        circuit.pos.len(),
        circuit.gates.len(),
        circuit.max_level,
        max_support,
        circuit_hash,
    );

    let plan = resolve_execution_plan(&args, &circuit, max_support);

    let results = match plan {
        ExecutionPlan::Full => {
            ensure_full_mode_supported(max_support);
            eprintln!("Full truth-table simulation over the entire circuit ...");
            let results = process_circuit(&circuit);
            eprintln!(
                "Compute done in {:.3}ms",
                t0.elapsed().as_secs_f64() * 1000.0
            );
            results
        }
        ExecutionPlan::Chunk { start, count } => {
            eprintln!(
                "Chunk simulation over the entire circuit: start={}, count={} ({} words/signal) ...",
                start,
                count,
                count.div_ceil(64)
            );

            let results = simulate_chunk(&circuit, start, count);
            let elapsed_compute = t0.elapsed();

            if let Some(ref bin_path) = args.binary_out {
                eprintln!("Writing binary partial to {} ...", bin_path);
                write_partial_bin(
                    bin_path,
                    circuit_hash,
                    circuit.pis.len() as u32,
                    start,
                    count,
                    &results,
                )
                .expect("Failed to write binary partial");
            }

            eprintln!(
                "Chunk compute done in {:.3}ms",
                elapsed_compute.as_secs_f64() * 1000.0
            );
            results
        }
    };

    let total_entropy = total_entropy(&results);

    eprintln!("Writing state counts to {} ...", args.output);
    write_counts_file(&args.output, circuit.pis.len(), &results).expect("Failed to write output");

    println!(
        "total_circuit_entropy = {:.6} bits  ({} outputs)",
        total_entropy,
        results.len()
    );

    eprintln!("Done — total {:.3}ms", t0.elapsed().as_secs_f64() * 1000.0);
}

fn run_merge(args: MergeArgs) {
    let t0 = Instant::now();

    eprintln!("Merging {} partial files ...", args.partials.len());
    let results = merge_partials(&args.partials);
    let total_entropy = total_entropy(&results);

    eprintln!("Writing merged counts to {} ...", args.output);
    write_counts_file(&args.output, 0, &results).expect("Failed to write merged output");

    println!(
        "total_circuit_entropy = {:.6} bits  ({} outputs)",
        total_entropy,
        results.len()
    );

    eprintln!("Merge done in {:.3}ms", t0.elapsed().as_secs_f64() * 1000.0);
}

fn resolve_execution_plan(args: &SimArgs, circuit: &Circuit, max_support: usize) -> ExecutionPlan {
    match args.mode {
        SimulationMode::Auto => {
            if args.start.is_some() || args.count.is_some() {
                resolve_chunk_plan(args, circuit)
            } else {
                if args.binary_out.is_some() {
                    exit_with_cli_error(
                        "--binary only works with chunk simulation; use --mode chunk or provide --count/--start",
                    );
                }
                if max_support <= AUTO_FULL_MAX_SUPPORT {
                    ExecutionPlan::Full
                } else {
                    exit_with_cli_error(&format!(
                        "Auto mode refused full simulation because max support {} exceeds the safe threshold {}. Use --mode full to force full simulation or --mode chunk --count <u64> to process slices.",
                        max_support, AUTO_FULL_MAX_SUPPORT
                    ));
                }
            }
        }
        SimulationMode::Full => {
            if args.start.is_some() || args.count.is_some() {
                exit_with_cli_error("--start and --count cannot be combined with --mode full");
            }
            if args.binary_out.is_some() {
                exit_with_cli_error("--binary only works with chunk simulation");
            }
            ExecutionPlan::Full
        }
        SimulationMode::Chunk => resolve_chunk_plan(args, circuit),
    }
}

fn resolve_chunk_plan(args: &SimArgs, circuit: &Circuit) -> ExecutionPlan {
    let start = args.start.unwrap_or(0);
    let count = args
        .count
        .unwrap_or_else(|| default_chunk_count(circuit.pis.len()));

    if count == 0 {
        exit_with_cli_error("--count must be greater than zero");
    }

    ExecutionPlan::Chunk { start, count }
}

fn max_support_len(circuit: &Circuit) -> usize {
    circuit
        .gates
        .values()
        .map(|gate| gate.support.len())
        .max()
        .unwrap_or(0)
}

fn ensure_full_mode_supported(max_support: usize) {
    let max_supported = ((u64::BITS - 1) as usize).min((usize::BITS - 1) as usize);
    if max_support > max_supported {
        exit_with_cli_error(&format!(
            "Full mode does not support max support {} on this platform. Use chunk mode instead.",
            max_support
        ));
    }
}

fn default_chunk_count(n_pis: usize) -> u64 {
    if n_pis > 63 {
        exit_with_cli_error(&format!(
            "chunk mode without --count is only supported for up to 63 PIs; found {}",
            n_pis
        ));
    }
    1u64 << n_pis
}

fn exit_with_cli_error(message: &str) -> ! {
    eprintln!("{}", message);
    std::process::exit(1);
}
