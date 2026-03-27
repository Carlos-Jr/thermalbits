//! Objetivo: executar a simulacao full com tabelas-verdade por suporte local.
//! Entradas: `Circuit` completo, sempre considerando todas as gates do circuito.
//! Saidas: `Vec<GateResult>` com contagens exatas por gate/output no modo full.

use rayon::prelude::*;
use std::collections::{HashMap, HashSet};

use crate::circuit::Circuit;
use crate::sim::shared::{
    compute_gate_refcounts, eval_output_words, mask_last_word, num_words, release_refcount,
    GateResult,
};

#[inline]
fn truth_table_bits(k: usize) -> usize {
    1usize.checked_shl(k as u32).unwrap_or_else(|| {
        panic!(
            "full mode does not support support_len={} on this platform",
            k
        )
    })
}

#[inline]
fn truth_table_total(k: usize) -> u64 {
    1u64.checked_shl(k as u32).unwrap_or_else(|| {
        panic!(
            "full mode does not support support_len={} because total vectors exceed u64",
            k
        )
    })
}

fn gen_pi_tt(pi_id: u32, support: &[u32]) -> Vec<u64> {
    let k = support.len();
    let pos = support
        .iter()
        .position(|&v| v == pi_id)
        .expect("PI not in support");
    let num_bits = truth_table_bits(k);
    let nw = num_words(num_bits);
    let mut tt = vec![0u64; nw];

    if pos < 6 {
        let block = 1u64 << pos;
        let mut pattern = 0u64;
        for bit in 0u64..64 {
            if (bit / block) & 1 == 1 {
                pattern |= 1u64 << bit;
            }
        }
        for w in &mut tt {
            *w = pattern;
        }
    } else {
        let words_per_stripe = 1usize << (pos - 6);
        let mut i = 0usize;
        while i < nw {
            i += words_per_stripe;
            let end = (i + words_per_stripe).min(nw);
            for w in &mut tt[i..end] {
                *w = !0u64;
            }
            i = end;
        }
    }

    mask_last_word(&mut tt, k);
    tt
}

fn expand_tt(old_tt: &[u64], old_support: &[u32], new_support: &[u32]) -> Vec<u64> {
    let old_k = old_support.len();
    let new_k = new_support.len();
    debug_assert!(new_k >= old_k);

    if old_k == new_k {
        return old_tt.to_vec();
    }

    let new_bits = truth_table_bits(new_k);
    let nw = num_words(new_bits);
    let mut result = vec![0u64; nw];

    let mut old_to_new: Vec<usize> = Vec::with_capacity(old_k);
    let mut new_only_pos: Vec<usize> = Vec::with_capacity(new_k - old_k);
    {
        let mut oi = 0usize;
        for (ni, &nv) in new_support.iter().enumerate() {
            if oi < old_k && old_support[oi] == nv {
                old_to_new.push(ni);
                oi += 1;
            } else {
                new_only_pos.push(ni);
            }
        }
    }

    let old_size = truth_table_bits(old_k);
    for old_idx in 0..old_size {
        let bit = (old_tt[old_idx / 64] >> (old_idx % 64)) & 1;
        if bit == 1 {
            let mut new_idx = 0usize;
            for (op, &np) in old_to_new.iter().enumerate() {
                if (old_idx >> op) & 1 == 1 {
                    new_idx |= 1 << np;
                }
            }
            result[new_idx / 64] |= 1u64 << (new_idx % 64);
        }
    }

    for &p in &new_only_pos {
        if p < 6 {
            let shift = 1u64 << p;
            for w in &mut result {
                *w |= *w << shift;
            }
        } else {
            let stride = 1usize << (p - 6);
            let mut base = 0usize;
            while base + stride <= nw {
                for d in 0..stride {
                    let src = result[base + d];
                    let dst = base + stride + d;
                    if dst < nw {
                        result[dst] |= src;
                    }
                }
                base += 2 * stride;
            }
        }
    }

    mask_last_word(&mut result, new_k);
    result
}

/// Resolve a fanin signal to its truth table over the gate's support (non-inverted).
fn resolve_fanin_tt(
    src_id: u32,
    src_output_idx: u32,
    gate_support: &[u32],
    pi_set: &HashSet<u32>,
    tt_store: &HashMap<u32, (Vec<u32>, Vec<Vec<u64>>)>,
) -> Vec<u64> {
    if pi_set.contains(&src_id) {
        gen_pi_tt(src_id, gate_support)
    } else {
        let (src_sup, src_outputs) = &tt_store[&src_id];
        let tt = &src_outputs[src_output_idx as usize];
        if src_sup.as_slice() == gate_support {
            tt.clone()
        } else {
            expand_tt(tt, src_sup, gate_support)
        }
    }
}

pub fn process_circuit(circuit: &Circuit) -> Vec<GateResult> {
    eprintln!(
        "  Full mode will process all {} gates in topological order",
        circuit.gates.len()
    );

    let refcounts = compute_gate_refcounts(circuit);
    let mut tt_store: HashMap<u32, (Vec<u32>, Vec<Vec<u64>>)> = HashMap::new();
    let mut results: Vec<GateResult> = Vec::new();

    for level in 1..=circuit.max_level {
        let Some(gate_ids) = circuit.levels.get(&level) else {
            continue;
        };

        let gates_here: Vec<_> = gate_ids.iter().map(|id| &circuit.gates[id]).collect();

        // Parallel: compute all gates at this level.
        let computed: Vec<(u32, Vec<u32>, Vec<(Vec<u64>, Option<(Vec<u64>, u64)>)>)> = gates_here
            .par_iter()
            .map(|g| {
                let sup = &g.support;
                let total = truth_table_total(sup.len());

                // Resolve all fanin TTs for this gate.
                let fanin_tts: Vec<Vec<u64>> = g
                    .fanin
                    .iter()
                    .map(|&(src_id, src_out_idx)| {
                        resolve_fanin_tt(src_id, src_out_idx, sup, &circuit.pi_set, &tt_store)
                    })
                    .collect();

                // Evaluate each fanout entry.
                let output_results: Vec<(Vec<u64>, Option<(Vec<u64>, u64)>)> = g
                    .fanout
                    .iter()
                    .map(|fo| {
                        let inputs: Vec<(&[u64], bool)> = fo
                            .input_indices
                            .iter()
                            .enumerate()
                            .map(|(i, &idx)| (fanin_tts[idx].as_slice(), fo.invert[i]))
                            .collect();
                        eval_output_words(&inputs, fo.op, total, true)
                    })
                    .collect();

                (g.id, sup.clone(), output_results)
            })
            .collect();

        // Sequential: store results and manage refcounts.
        for (gid, sup, output_results) in computed {
            let g = &circuit.gates[&gid];
            let total = truth_table_total(sup.len());
            let mut output_tts = Vec::with_capacity(output_results.len());

            for (fo_idx, (out_tt, maybe_counts)) in output_results.into_iter().enumerate() {
                if let Some((joint_counts, pop_y)) = maybe_counts {
                    results.push(GateResult {
                        gate_id: gid,
                        output_index: fo_idx as u32,
                        op: g.fanout[fo_idx].op,
                        support_len: sup.len(),
                        total,
                        joint_counts,
                        pop_y,
                    });
                }
                output_tts.push(out_tt);
            }

            tt_store.insert(gid, (sup, output_tts));

            for &(src_id, _) in &g.fanin {
                if release_refcount(&refcounts, src_id) {
                    tt_store.remove(&src_id);
                }
            }

            if release_refcount(&refcounts, gid) {
                tt_store.remove(&gid);
            }
        }
    }

    results.sort_by_key(|r| (r.gate_id, r.output_index));
    results
}
