//! Objetivo: concentrar metricas estatisticas calculadas sobre a simulacao.
//! Entradas: contagens acumuladas por gate (`GateResult`).
//! Saidas: entropia local e entropia total do circuito.

use rayon::prelude::*;

use crate::sim::shared::GateResult;

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

pub fn total_entropy(results: &[GateResult]) -> f64 {
    results
        .par_iter()
        .map(|r| {
            let h_ab = entropy(&r.joint_counts);
            let h_y = entropy(&[r.total - r.pop_y, r.pop_y]);
            h_ab - h_y
        })
        .sum()
}
