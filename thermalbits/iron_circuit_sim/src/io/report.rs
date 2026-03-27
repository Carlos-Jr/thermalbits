//! Objetivo: serializar os resultados em formato texto legivel para inspecao humana.
//! Entradas: quantidade de PIs e `GateResult` ordenados ou agregados.
//! Saidas: arquivo texto com contagens por gate/output e estatisticas derivadas de Y.

use std::fs::File;
use std::io::{BufWriter, Write};

use rayon::prelude::*;

use crate::circuit::Op;
use crate::sim::shared::GateResult;

pub fn write_counts_file(
    path: &str,
    n_pis: usize,
    results: &[GateResult],
) -> std::io::Result<()> {
    let lines: Vec<String> = results
        .par_iter()
        .map(|r| {
            let op_str = match r.op {
                Op::And => "&",
                Op::Or => "|",
                Op::Xor => "^",
                Op::Majority => "M",
                Op::Wire => "-",
            };

            let n_jc = r.joint_counts.len();
            debug_assert!(n_jc.is_power_of_two() && n_jc > 0);
            let n_inputs = n_jc.trailing_zeros() as usize;

            // Build joint count labels: big-endian binary pattern.
            let jc_str: String = (0..n_jc)
                .map(|p| format!("n{:0>width$b}={}", p, r.joint_counts[p], width = n_inputs))
                .collect::<Vec<_>>()
                .join(" ");

            format!(
                "gate={} out={} op={} k={} total={} {} y0={} y1={}\n",
                r.gate_id,
                r.output_index,
                op_str,
                r.support_len,
                r.total,
                jc_str,
                r.total - r.pop_y,
                r.pop_y,
            )
        })
        .collect();

    let f = File::create(path)?;
    let mut w = BufWriter::new(f);

    writeln!(
        w,
        "# circuit_sim state counts | pis={} outputs={}",
        n_pis,
        results.len()
    )?;
    writeln!(w, "# gate out op k total joint_counts... y0 y1")?;

    for line in &lines {
        w.write_all(line.as_bytes())?;
    }

    w.flush()
}
