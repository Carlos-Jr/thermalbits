//! Objetivo: converter argumentos de linha de comando em comandos tipados.
//! Entradas: `std::env::args()` com parametros de simulacao ou merge.
//! Saidas: `Command`, `SimArgs` ou `MergeArgs` prontos para a camada de aplicacao.

use std::env;

pub enum Command {
    Sim(SimArgs),
    Merge(MergeArgs),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SimulationMode {
    Auto,
    Full,
    Chunk,
}

pub struct SimArgs {
    pub input: String,
    pub output: String,
    pub binary_out: Option<String>,
    pub mode: SimulationMode,
    pub start: Option<u64>,
    pub count: Option<u64>,
}

pub struct MergeArgs {
    pub partials: Vec<String>,
    pub output: String,
}

impl SimulationMode {
    fn parse(raw: &str) -> Self {
        match raw {
            "auto" => Self::Auto,
            "full" => Self::Full,
            "chunk" => Self::Chunk,
            other => {
                eprintln!(
                    "Invalid value for --mode: {} (expected auto, full, or chunk)",
                    other
                );
                std::process::exit(1);
            }
        }
    }
}

pub fn parse_args() -> Command {
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 {
        eprintln!(
            "Usage:\n  circuit_sim <input.json> [-o out.txt] [--mode auto|full|chunk]\n             \
             [--start <u64>] [--count <u64>] [--binary <partial.bin>]\n  \
             circuit_sim merge <p1.bin> [p2.bin …] [-o out.txt]"
        );
        std::process::exit(1);
    }

    if args[1] == "merge" {
        let mut partials = Vec::new();
        let mut output = String::from("merged.txt");
        let mut i = 2usize;
        while i < args.len() {
            match args[i].as_str() {
                "-o" | "--output" => {
                    i += 1;
                    output = args[i].clone();
                }
                p => partials.push(p.to_string()),
            }
            i += 1;
        }
        if partials.is_empty() {
            eprintln!("merge: no partial files specified");
            std::process::exit(1);
        }
        return Command::Merge(MergeArgs { partials, output });
    }

    let input = args[1].clone();
    let mut output = String::from("states.txt");
    let mut binary_out: Option<String> = None;
    let mut mode = SimulationMode::Auto;
    let mut start: Option<u64> = None;
    let mut count: Option<u64> = None;

    let mut i = 2usize;
    while i < args.len() {
        match args[i].as_str() {
            "-o" | "--output" => {
                i += 1;
                output = args[i].clone();
            }
            "--binary" => {
                i += 1;
                binary_out = Some(args[i].clone());
            }
            "--mode" => {
                i += 1;
                mode = SimulationMode::parse(&args[i]);
            }
            "--start" => {
                i += 1;
                start = Some(args[i].parse::<u64>().expect("--start must be u64"));
            }
            "--count" => {
                i += 1;
                count = Some(args[i].parse::<u64>().expect("--count must be u64"));
            }
            other => {
                eprintln!("Unknown argument: {}", other);
                std::process::exit(1);
            }
        }
        i += 1;
    }

    Command::Sim(SimArgs {
        input,
        output,
        binary_out,
        mode,
        start,
        count,
    })
}
