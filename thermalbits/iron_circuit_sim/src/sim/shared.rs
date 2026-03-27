//! Objetivo: fornecer tipos e primitivas compartilhadas entre os modos full e chunk.
//! Entradas: bitsets de sinais, dependencias de gates e contagens brutas.
//! Saidas: `GateResult`, mascaras de palavras e suporte a refcount/dependencias.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU32, Ordering};

use crate::circuit::{Circuit, Op};

#[derive(Clone, Debug)]
pub struct GateResult {
    pub gate_id: u32,
    pub output_index: u32,
    pub op: Op,
    pub support_len: usize,
    pub total: u64,
    /// Joint input distribution: length = 2^n_inputs.
    /// Indexed by big-endian pattern: input_0 is MSB.
    pub joint_counts: Vec<u64>,
    pub pop_y: u64,
}

#[inline]
pub(crate) fn num_words(num_bits: usize) -> usize {
    num_bits.div_ceil(64)
}

#[inline]
pub(crate) fn mask_last_word(tt: &mut [u64], k: usize) {
    let num_bits = 1usize << k;
    let rem = num_bits % 64;
    if rem != 0 && !tt.is_empty() {
        let last = tt.len() - 1;
        tt[last] &= (1u64 << rem) - 1;
    }
}

#[inline]
pub(crate) fn last_word_mask_from_total(total_bits: u64) -> u64 {
    let rem = (total_bits & 63) as u32;
    if rem == 0 {
        !0u64
    } else {
        (1u64 << rem) - 1
    }
}

/// Evaluate a single fanout output over word vectors.
///
/// `input_sigs`: slice of (word_vector, is_inverted) per input to this output.
/// Returns (output_words, Option<(joint_counts, pop_y)>).
/// Joint counts use big-endian indexing: input_0 contributes to the MSB of the pattern index.
pub(crate) fn eval_output_words(
    input_sigs: &[(&[u64], bool)],
    op: Op,
    total_bits: u64,
    need_counts: bool,
) -> (Vec<u64>, Option<(Vec<u64>, u64)>) {
    let n_inputs = input_sigs.len();
    assert!(n_inputs > 0, "fanout output must have at least 1 input");
    let n_words = input_sigs[0].0.len();
    let last_mask = last_word_mask_from_total(total_bits);

    // Prepare input words: apply inversions and mask last word.
    let mut prepared: Vec<Vec<u64>> = Vec::with_capacity(n_inputs);
    for &(words, inverted) in input_sigs {
        debug_assert_eq!(words.len(), n_words);
        let mut w: Vec<u64> = if inverted {
            words.iter().map(|&v| !v).collect()
        } else {
            words.to_vec()
        };
        if let Some(lw) = w.last_mut() {
            *lw &= last_mask;
        }
        prepared.push(w);
    }

    // Compute output.
    let mut out = match op {
        Op::Wire => prepared[0].clone(),
        Op::And => {
            let mut r = prepared[0].clone();
            for inp in &prepared[1..] {
                for (o, &i) in r.iter_mut().zip(inp.iter()) {
                    *o &= i;
                }
            }
            r
        }
        Op::Or => {
            let mut r = prepared[0].clone();
            for inp in &prepared[1..] {
                for (o, &i) in r.iter_mut().zip(inp.iter()) {
                    *o |= i;
                }
            }
            r
        }
        Op::Xor => {
            let mut r = prepared[0].clone();
            for inp in &prepared[1..] {
                for (o, &i) in r.iter_mut().zip(inp.iter()) {
                    *o ^= i;
                }
            }
            r
        }
        Op::Majority => compute_majority_words(&prepared, n_words, last_mask),
    };
    if let Some(lw) = out.last_mut() {
        *lw &= last_mask;
    }

    if !need_counts {
        return (out, None);
    }

    // Compute joint counts (big-endian: input_0 is MSB of pattern index).
    let n_patterns = 1usize << n_inputs;
    let mut counts = vec![0u64; n_patterns];

    for w in 0..n_words {
        let is_last = w + 1 == n_words;
        let mask = if is_last { last_mask } else { !0u64 };

        for p in 0..n_patterns {
            let mut pm = mask;
            for i in 0..n_inputs {
                let bit = (p >> (n_inputs - 1 - i)) & 1;
                if bit == 1 {
                    pm &= prepared[i][w];
                } else {
                    pm &= !prepared[i][w];
                }
            }
            counts[p] += pm.count_ones() as u64;
        }
    }

    let mut pop_y = 0u64;
    for &w in &out {
        pop_y += w.count_ones() as u64;
    }

    (out, Some((counts, pop_y)))
}

/// Compute majority output at word level using an adder-tree approach.
fn compute_majority_words(inputs: &[Vec<u64>], n_words: usize, last_mask: u64) -> Vec<u64> {
    let n = inputs.len();
    debug_assert!(n >= 1 && n % 2 == 1);
    let n_sum_bits = usize::BITS as usize - n.leading_zeros() as usize;
    let mut sum_bits: Vec<Vec<u64>> = vec![vec![0u64; n_words]; n_sum_bits];

    for input in inputs {
        let mut carry = input.clone();
        for k in 0..n_sum_bits {
            let (new_sum, new_carry): (Vec<u64>, Vec<u64>) = sum_bits[k]
                .iter()
                .zip(carry.iter())
                .map(|(&s, &c)| (s ^ c, s & c))
                .unzip();
            sum_bits[k] = new_sum;
            carry = new_carry;
            if carry.iter().all(|&w| w == 0) {
                break;
            }
        }
    }

    // Compare sum >= threshold where threshold = n/2 + 1.
    let threshold = n / 2 + 1;
    let mut gt = vec![0u64; n_words];
    let mut eq = vec![!0u64; n_words];

    for k in (0..n_sum_bits).rev() {
        let t_bit = (threshold >> k) & 1;
        if t_bit == 1 {
            for j in 0..n_words {
                eq[j] &= sum_bits[k][j];
            }
        } else {
            for j in 0..n_words {
                let new_gt = gt[j] | (eq[j] & sum_bits[k][j]);
                eq[j] &= !sum_bits[k][j];
                gt[j] = new_gt;
            }
        }
    }

    let mut out = vec![0u64; n_words];
    for j in 0..n_words {
        out[j] = gt[j] | eq[j];
    }
    if let Some(lw) = out.last_mut() {
        *lw &= last_mask;
    }
    out
}

pub(crate) fn compute_gate_refcounts(circuit: &Circuit) -> HashMap<u32, AtomicU32> {
    let mut rc: HashMap<u32, u32> = circuit.gates.keys().map(|&gid| (gid, 1)).collect();

    for gate in circuit.gates.values() {
        for &(src_id, _) in &gate.fanin {
            if let Some(value) = rc.get_mut(&src_id) {
                *value += 1;
            }
        }
    }

    rc.into_iter()
        .map(|(k, v)| (k, AtomicU32::new(v)))
        .collect()
}

#[inline]
pub(crate) fn release_refcount(refcounts: &HashMap<u32, AtomicU32>, sig_id: u32) -> bool {
    if let Some(rc) = refcounts.get(&sig_id) {
        let prev = rc.fetch_sub(1, Ordering::Relaxed);
        debug_assert!(prev > 0, "refcount underflow on signal {}", sig_id);
        prev == 1
    } else {
        false
    }
}
