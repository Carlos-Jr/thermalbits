//! Objetivo: ler, escrever e combinar arquivos parciais binarios da simulacao chunk.
//! Entradas: `GateResult`, metadados do circuito e caminhos de arquivos `.bin`.
//! Saidas: partials persistidos e resultados agregados validados para merge do circuito inteiro.

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufWriter, Read, Write};

use crate::circuit::Op;
use crate::sim::shared::GateResult;

struct PartialData {
    circuit_hash: u64,
    n_pis: u32,
    start: u64,
    count: u64,
    records: Vec<GateResult>,
}

fn op_to_byte(op: Op) -> u8 {
    match op {
        Op::And => 0,
        Op::Or => 1,
        Op::Xor => 2,
        Op::Majority => 3,
        Op::Wire => 4,
    }
}

fn byte_to_op(b: u8) -> Op {
    match b {
        0 => Op::And,
        1 => Op::Or,
        2 => Op::Xor,
        3 => Op::Majority,
        4 => Op::Wire,
        _ => panic!("Unknown op byte {} in partial file", b),
    }
}

/// Binary format v3:
/// Header: magic(4) + version(1) + flags(1) + n_pis(4) + start(8) + count(8)
///         + circuit_hash(8) + n_records(4) = 38 bytes
/// Record: gate_id(4) + output_index(4) + op(1) + n_jc(2) + pop_y(8) + joint_counts(8 × n_jc)
pub fn write_partial_bin(
    path: &str,
    circuit_hash: u64,
    n_pis: u32,
    start: u64,
    count: u64,
    results: &[GateResult],
) -> std::io::Result<()> {
    let f = File::create(path)?;
    let mut w = BufWriter::new(f);

    w.write_all(b"CSIM")?;
    w.write_all(&[3u8, 1u8])?;
    w.write_all(&n_pis.to_le_bytes())?;
    w.write_all(&start.to_le_bytes())?;
    w.write_all(&count.to_le_bytes())?;
    w.write_all(&circuit_hash.to_le_bytes())?;
    w.write_all(&(results.len() as u32).to_le_bytes())?;

    for r in results {
        w.write_all(&r.gate_id.to_le_bytes())?;
        w.write_all(&r.output_index.to_le_bytes())?;
        w.write_all(&[op_to_byte(r.op)])?;
        w.write_all(&(r.joint_counts.len() as u16).to_le_bytes())?;
        w.write_all(&r.pop_y.to_le_bytes())?;
        for &jc in &r.joint_counts {
            w.write_all(&jc.to_le_bytes())?;
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
        version, 3,
        "Unsupported CSIM version {} (expected 3)",
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
        let output_index = u32le!();
        let op = byte_to_op(take!(1)[0]);
        let n_jc = u16le!() as usize;
        let pop_y = u64le!();
        let mut joint_counts = Vec::with_capacity(n_jc);
        for _ in 0..n_jc {
            joint_counts.push(u64le!());
        }
        records.push(GateResult {
            gate_id,
            output_index,
            op,
            support_len: 0,
            total: count,
            joint_counts,
            pop_y,
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

pub fn merge_partials(paths: &[String]) -> Vec<GateResult> {
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

    let mut acc: HashMap<(u32, u32), GateResult> = HashMap::new();
    let mut total_count: u64 = 0;

    for pd in all_data {
        total_count += pd.count;

        for r in pd.records {
            let key = (r.gate_id, r.output_index);
            let n_jc = r.joint_counts.len();
            let e = acc.entry(key).or_insert(GateResult {
                gate_id: r.gate_id,
                output_index: r.output_index,
                op: r.op,
                support_len: 0,
                total: 0,
                joint_counts: vec![0u64; n_jc],
                pop_y: 0,
            });
            for (dst, &src) in e.joint_counts.iter_mut().zip(r.joint_counts.iter()) {
                *dst += src;
            }
            e.pop_y += r.pop_y;
        }
    }

    let mut results: Vec<GateResult> = acc.into_values().collect();
    for r in &mut results {
        r.total = total_count;
    }
    results.sort_by_key(|r| (r.gate_id, r.output_index));

    eprintln!(
        "Merged {} partial files — {} outputs, total vectors: {}",
        paths.len(),
        results.len(),
        total_count
    );

    results
}
