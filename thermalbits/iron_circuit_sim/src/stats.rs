//! Objetivo: concentrar metricas estatisticas calculadas sobre a simulacao.
//! Entradas: contagens acumuladas por node (`NodeResult`).
//! Saidas: entropia local e entropia total do circuito.

use rayon::prelude::*;

use crate::sim::shared::NodeResult;

pub fn entropy(counts: &[u64]) -> f64 {
    let total: u64 = counts.iter().sum();
    if total == 0 {
        return 0.0;
    }
    let t = total as f64;
    let mut h = 0.0f64;
    for &c in counts {
        if c > 0 {
            let p = c as f64 / t;
            h -= p * p.log2();
        }
    }
    h
}

pub fn total_entropy(results: &[NodeResult]) -> f64 {
    results
        .par_iter()
        .map(|r| {
            let h_in = entropy(&r.input_joint);
            let h_out = entropy(&r.output_joint);
            h_in - h_out
        })
        .sum()
}
