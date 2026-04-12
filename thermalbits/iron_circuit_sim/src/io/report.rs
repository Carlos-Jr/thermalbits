//! Objetivo: serializar os resultados em formato texto legivel para inspecao humana.
//! Entradas: quantidade de PIs e `NodeResult` ordenados ou agregados.
//! Saidas: arquivo texto com contagens por node e distribuicoes joint de entrada e saida.

use std::fs::File;
use std::io::{BufWriter, Write};

use rayon::prelude::*;

use crate::sim::shared::NodeResult;

pub fn write_counts_file(
    path: &str,
    n_pis: usize,
    results: &[NodeResult],
) -> std::io::Result<()> {
    let lines: Vec<String> = results
        .par_iter()
        .map(|r| {
            let ij_str: String = (0..r.input_joint.len())
                .map(|p| {
                    format!(
                        "ij{:0>width$b}={}",
                        p,
                        r.input_joint[p],
                        width = r.n_inputs
                    )
                })
                .collect::<Vec<_>>()
                .join(" ");

            let oj_str: String = (0..r.output_joint.len())
                .map(|p| {
                    format!(
                        "oj{:0>width$b}={}",
                        p,
                        r.output_joint[p],
                        width = r.n_outputs
                    )
                })
                .collect::<Vec<_>>()
                .join(" ");

            format!(
                "gate={} n_in={} n_out={} total={} {} {}\n",
                r.gate_id, r.n_inputs, r.n_outputs, r.total, ij_str, oj_str,
            )
        })
        .collect();

    let f = File::create(path)?;
    let mut w = BufWriter::new(f);

    writeln!(
        w,
        "# circuit_sim state counts | pis={} nodes={}",
        n_pis,
        results.len()
    )?;
    writeln!(
        w,
        "# gate n_in n_out total input_joint... output_joint..."
    )?;

    for line in &lines {
        w.write_all(line.as_bytes())?;
    }

    w.flush()
}
