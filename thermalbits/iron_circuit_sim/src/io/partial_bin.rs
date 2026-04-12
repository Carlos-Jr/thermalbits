//! Objetivo: ler, escrever e combinar arquivos parciais binarios da simulacao chunk.
//! Entradas: `NodeResult`, metadados do circuito e caminhos de arquivos `.bin`.
//! Saidas: partials persistidos e resultados agregados validados para merge do circuito inteiro.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Read, Write};

use crate::sim::shared::NodeResult;

struct PartialData {
    circuit_hash: u64,
    n_pis: u32,
    start: u64,
    count: u64,
    records: Vec<NodeResult>,
}

/// Binary format v4:
/// Header: magic(4) + version(1) + flags(1) + n_pis(4) + start(8) + count(8)
///         + circuit_hash(8) + n_records(4) = 38 bytes
/// Record: gate_id(4) + n_inputs(2) + n_outputs(2)
///         + input_joint(8 × 2^n_inputs) + output_joint(8 × 2^n_outputs)
pub fn write_partial_bin(
    path: &str,
    circuit_hash: u64,
    n_pis: u32,
    start: u64,
    count: u64,
    results: &[NodeResult],
) -> std::io::Result<()> {
    let f = File::create(path)?;
    let mut w = BufWriter::new(f);

    w.write_all(b"CSIM")?;
    w.write_all(&[4u8, 1u8])?;
    w.write_all(&n_pis.to_le_bytes())?;
    w.write_all(&start.to_le_bytes())?;
    w.write_all(&count.to_le_bytes())?;
    w.write_all(&circuit_hash.to_le_bytes())?;
    w.write_all(&(results.len() as u32).to_le_bytes())?;

    for r in results {
        w.write_all(&r.gate_id.to_le_bytes())?;
        w.write_all(&(r.n_inputs as u16).to_le_bytes())?;
        w.write_all(&(r.n_outputs as u16).to_le_bytes())?;
        for &v in &r.input_joint {
            w.write_all(&v.to_le_bytes())?;
        }
        for &v in &r.output_joint {
            w.write_all(&v.to_le_bytes())?;
        }
    }

    w.flush()
}

fn read_partial_bin(path: &str) -> std::io::Result<PartialData> {
    let mut data = Vec::new();
    File::open(path)?.read_to_end(&mut data)?;
    let mut pos = 0usize;

    macro_rules! take {
        ($n:expr) => {{
            let s = &data[pos..pos + $n];
            pos += $n;
            s
        }};
    }
    macro_rules! u16le {
        () => {
            u16::from_le_bytes(take!(2).try_into().unwrap())
        };
    }
    macro_rules! u32le {
        () => {
            u32::from_le_bytes(take!(4).try_into().unwrap())
        };
    }
    macro_rules! u64le {
        () => {
            u64::from_le_bytes(take!(8).try_into().unwrap())
        };
    }

    let magic = take!(4);
    assert_eq!(magic, b"CSIM", "Invalid magic — not a CSIM partial file");
    let version = take!(1)[0];
    assert_eq!(
        version, 4,
        "Unsupported CSIM version {} (expected 4)",
        version
    );
    let _flags = take!(1)[0];

    let n_pis = u32le!();
    let start = u64le!();
    let count = u64le!();
    let circuit_hash = u64le!();
    let n_records = u32le!() as usize;

    let mut records = Vec::with_capacity(n_records);
    for _ in 0..n_records {
        let gate_id = u32le!();
        let n_inputs = u16le!() as usize;
        let n_outputs = u16le!() as usize;
        let n_ij = 1usize << n_inputs;
        let n_oj = 1usize << n_outputs;
        let mut input_joint = Vec::with_capacity(n_ij);
        for _ in 0..n_ij {
            input_joint.push(u64le!());
        }
        let mut output_joint = Vec::with_capacity(n_oj);
        for _ in 0..n_oj {
            output_joint.push(u64le!());
        }
        records.push(NodeResult {
            gate_id,
            n_inputs,
            n_outputs,
            total: count,
            input_joint,
            output_joint,
        });
    }

    Ok(PartialData {
        circuit_hash,
        n_pis,
        start,
        count,
        records,
    })
}

pub fn merge_partials(paths: &[String]) -> Vec<NodeResult> {
    assert!(!paths.is_empty(), "No partial files to merge");

    let first = read_partial_bin(&paths[0]).expect("Cannot read partial file");
    let circuit_hash = first.circuit_hash;
    let n_pis = first.n_pis;
    let expected_records = first.records.len();

    let mut all_data: Vec<PartialData> = std::iter::once(Ok(first))
        .chain(paths[1..].iter().map(|p| read_partial_bin(p)))
        .map(|r| r.expect("Cannot read partial file"))
        .collect();
    all_data.sort_by_key(|pd| pd.start);

    let mut next_free_start: Option<u64> = None;
    for pd in &all_data {
        assert_eq!(
            pd.circuit_hash, circuit_hash,
            "circuit_hash mismatch — partial files are from different circuits"
        );
        assert_eq!(pd.n_pis, n_pis, "n_pis mismatch in partial files");
        assert_eq!(
            pd.records.len(),
            expected_records,
            "record count mismatch in partial files"
        );
        assert!(pd.count > 0, "partial file with count=0 is invalid");

        if let Some(prev_end) = next_free_start {
            assert!(
                pd.start >= prev_end,
                "partial files overlap — previous end: {}, next start: {}",
                prev_end,
                pd.start
            );
        }
        next_free_start = Some(
            pd.start
                .checked_add(pd.count)
                .expect("partial range overflows u64"),
        );
    }

    let mut acc: HashMap<u32, NodeResult> = HashMap::new();
    let mut total_count: u64 = 0;

    for pd in all_data {
        total_count += pd.count;

        for r in pd.records {
            let e = acc.entry(r.gate_id).or_insert(NodeResult {
                gate_id: r.gate_id,
                n_inputs: r.n_inputs,
                n_outputs: r.n_outputs,
                total: 0,
                input_joint: vec![0u64; r.input_joint.len()],
                output_joint: vec![0u64; r.output_joint.len()],
            });
            for (dst, &src) in e.input_joint.iter_mut().zip(r.input_joint.iter()) {
                *dst += src;
            }
            for (dst, &src) in e.output_joint.iter_mut().zip(r.output_joint.iter()) {
                *dst += src;
            }
        }
    }

    let mut results: Vec<NodeResult> = acc.into_values().collect();
    for r in &mut results {
        r.total = total_count;
    }
    results.sort_by_key(|r| r.gate_id);

    eprintln!(
        "Merged {} partial files — {} nodes, total vectors: {}",
        paths.len(),
        results.len(),
        total_count
    );

    results
}
