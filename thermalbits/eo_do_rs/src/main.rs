//! Objetivo: expor os metodos EO/DO como binario CLI para o modulo Python.
//! Entradas: caminho do JSON do overview e selecao da politica (depth_oriented|energy_oriented).
//! Saidas: JSON do overview transformado no caminho fornecido em `-o`, ou em stdout.

use std::fs;
use std::io::{self, Read, Write};
use std::process;

use eo_do_rs::{apply, Overview, Policy};

fn usage_and_exit() -> ! {
    eprintln!(
        "Usage:\n  eo_do_rs <input.json> --method depth_oriented|energy_oriented [-o <output.json>]\n  eo_do_rs - --method depth_oriented|energy_oriented  (le stdin, escreve stdout)"
    );
    process::exit(2);
}

fn parse_policy(raw: &str) -> Policy {
    match raw {
        "depth_oriented" | "DO" | "do" => Policy::DepthOriented,
        "energy_oriented" | "EO" | "eo" => Policy::EnergyOriented,
        other => {
            eprintln!(
                "Invalid --method: {} (expected depth_oriented or energy_oriented)",
                other
            );
            process::exit(2);
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        usage_and_exit();
    }

    let input = args[1].clone();
    let mut method: Option<Policy> = None;
    let mut output: Option<String> = None;

    let mut i = 2usize;
    while i < args.len() {
        match args[i].as_str() {
            "--method" | "-m" => {
                i += 1;
                if i >= args.len() {
                    usage_and_exit();
                }
                method = Some(parse_policy(&args[i]));
            }
            "-o" | "--output" => {
                i += 1;
                if i >= args.len() {
                    usage_and_exit();
                }
                output = Some(args[i].clone());
            }
            other => {
                eprintln!("Unknown argument: {}", other);
                usage_and_exit();
            }
        }
        i += 1;
    }

    let policy = method.unwrap_or_else(|| {
        eprintln!("Missing --method argument");
        usage_and_exit();
    });

    let raw = if input == "-" {
        let mut buf = String::new();
        io::stdin()
            .read_to_string(&mut buf)
            .expect("failed to read stdin");
        buf
    } else {
        fs::read_to_string(&input).unwrap_or_else(|e| {
            eprintln!("Cannot read {}: {}", input, e);
            process::exit(1);
        })
    };

    let mut overview: Overview = serde_json::from_str(&raw).unwrap_or_else(|e| {
        eprintln!("Invalid JSON: {}", e);
        process::exit(1);
    });

    if let Err(msg) = apply(&mut overview, policy) {
        eprintln!("Transform error: {}", msg);
        process::exit(1);
    }

    let payload = serde_json::to_string(&overview).unwrap_or_else(|e| {
        eprintln!("Failed to serialize overview: {}", e);
        process::exit(1);
    });

    match output {
        Some(path) => {
            fs::write(&path, payload).unwrap_or_else(|e| {
                eprintln!("Cannot write {}: {}", path, e);
                process::exit(1);
            });
        }
        None => {
            let stdout = io::stdout();
            let mut handle = stdout.lock();
            handle
                .write_all(payload.as_bytes())
                .expect("failed to write stdout");
        }
    }
}
