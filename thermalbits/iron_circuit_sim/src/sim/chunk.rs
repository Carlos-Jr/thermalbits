//! Objetivo: executar a simulacao chunk com bitsets globais por fatia da tabela-verdade.
//! Entradas: `Circuit` inteiro, `start` e `count` da janela simulada.
//! Saidas: `Vec<NodeResult>` com contagens acumuladas para todas as nodes na faixa.

use rayon::prelude::*;
use std::collections::{HashMap, HashSet};

use crate::circuit::Circuit;
use crate::sim::shared::{
    compute_gate_refcounts, compute_joint_counts, eval_output_words, last_word_mask_from_total,
    release_refcount, NodeResult,
};

const STANDARD_PI_WORDS: [u64; 6] = [
    0xAAAA_AAAA_AAAA_AAAA,
    0xCCCC_CCCC_CCCC_CCCC,
    0xF0F0_F0F0_F0F0_F0F0,
    0xFF00_FF00_FF00_FF00,
    0xFFFF_0000_FFFF_0000,
    0xFFFF_FFFF_0000_0000,
];

#[inline]
fn gen_pi_word(base: u64, j: u32) -> u64 {
    if j >= 6 {
        if (base >> j) & 1 == 1 {
            !0u64
        } else {
            0u64
        }
    } else {
        let period = 1u32 << (j + 1);
        let phase = (base % period as u64) as u32;
        STANDARD_PI_WORDS[j as usize].rotate_right(phase)
    }
}

/// Resolve a fanin signal to a word-vector reference.
fn resolve_fanin_sig<'a>(
    src_id: u32,
    src_output_idx: u32,
    pi_sigs: &'a HashMap<u32, Vec<u64>>,
    sig_store: &'a HashMap<u32, Vec<Vec<u64>>>,
) -> &'a [u64] {
    if let Some(pi_sig) = pi_sigs.get(&src_id) {
        debug_assert_eq!(src_output_idx, 0, "PI {} has only output 0", src_id);
        pi_sig.as_slice()
    } else {
        let outputs = sig_store
            .get(&src_id)
            .unwrap_or_else(|| panic!("Signal {} not found in stores", src_id));
        outputs[src_output_idx as usize].as_slice()
    }
}

pub fn simulate_chunk(circuit: &Circuit, start: u64, count: u64) -> Vec<NodeResult> {
    assert!(count > 0, "count must be > 0");
    assert!(
        circuit.pis.len() <= 64,
        "Only up to 64 PIs supported in chunk mode"
    );

    let n_words = count.div_ceil(64) as usize;
    let last_mask = last_word_mask_from_total(count);

    let pi_index: HashMap<u32, u32> = circuit
        .pis
        .iter()
        .enumerate()
        .map(|(i, &id)| (id, i as u32))
        .collect();

    // Collect all PIs referenced by any gate fanin.
    let mut needed_pis: HashSet<u32> = HashSet::new();
    for gate in circuit.gates.values() {
        for &(src_id, _) in &gate.fanin {
            if circuit.pi_set.contains(&src_id) {
                needed_pis.insert(src_id);
            }
        }
    }

    // Generate PI signal vectors.
    let mut pi_sigs: HashMap<u32, Vec<u64>> = HashMap::with_capacity(needed_pis.len());
    for &pi_id in &needed_pis {
        let j = pi_index[&pi_id];
        let mut words: Vec<u64> = (0..n_words)
            .map(|w| gen_pi_word(start + w as u64 * 64, j))
            .collect();
        if last_mask != !0u64 {
            if let Some(lw) = words.last_mut() {
                *lw &= last_mask;
            }
        }
        pi_sigs.insert(pi_id, words);
    }

    eprintln!(
        "  Chunk [{}, {}+{}) — full circuit: {} gates, words/signal: {}, needed PIs: {}",
        start,
        start,
        count,
        circuit.gates.len(),
        n_words,
        pi_sigs.len(),
    );

    let refcounts = compute_gate_refcounts(circuit);
    let mut sig_store: HashMap<u32, Vec<Vec<u64>>> = HashMap::new();
    let mut results: Vec<NodeResult> = Vec::new();

    for level in 1..=circuit.max_level {
        let Some(gate_ids) = circuit.levels.get(&level) else {
            continue;
        };

        let gates_here: Vec<_> = gate_ids.iter().map(|id| &circuit.gates[id]).collect();

        let computed: Vec<(u32, Vec<Vec<u64>>, NodeResult)> = gates_here
            .par_iter()
            .map(|g| {
                // Resolve all fanin signals.
                let fanin_sigs: Vec<&[u64]> = g
                    .fanin
                    .iter()
                    .map(|&(src_id, src_out_idx)| {
                        resolve_fanin_sig(src_id, src_out_idx, &pi_sigs, &sig_store)
                    })
                    .collect();

                // Evaluate each fanout entry.
                let output_tts: Vec<Vec<u64>> = g
                    .fanout
                    .iter()
                    .map(|fo| {
                        let inputs: Vec<(&[u64], bool)> = fo
                            .input_indices
                            .iter()
                            .enumerate()
                            .map(|(i, &idx)| (fanin_sigs[idx], fo.invert[i]))
                            .collect();
                        eval_output_words(&inputs, fo.op, count)
                    })
                    .collect();

                // Compute input joint distribution.
                let input_joint = compute_joint_counts(&fanin_sigs, n_words, count);

                // Compute output joint distribution.
                let output_refs: Vec<&[u64]> =
                    output_tts.iter().map(|t| t.as_slice()).collect();
                let output_joint = compute_joint_counts(&output_refs, n_words, count);

                let result = NodeResult {
                    gate_id: g.id,
                    n_inputs: fanin_sigs.len(),
                    n_outputs: output_tts.len(),
                    total: count,
                    input_joint,
                    output_joint,
                };

                (g.id, output_tts, result)
            })
            .collect();

        for (gid, output_tts, node_result) in computed {
            let g = &circuit.gates[&gid];
            results.push(node_result);
            sig_store.insert(gid, output_tts);

            for &(src_id, _) in &g.fanin {
                if release_refcount(&refcounts, src_id) {
                    sig_store.remove(&src_id);
                }
            }

            if release_refcount(&refcounts, gid) {
                sig_store.remove(&gid);
            }
        }
    }

    results.sort_by_key(|r| r.gate_id);
    results
}
