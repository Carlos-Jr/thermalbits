//! Objetivo: definir o dominio do circuito e carregar o JSON de entrada.
//! Entradas: caminho do arquivo JSON e dados serializados do circuito combinacional.
//! Saidas: `Circuit` indexado por nivel/gate e o hash do arquivo para partials.

use serde::Deserialize;
use std::collections::{BTreeMap, HashMap, HashSet};

#[derive(Deserialize)]
struct CircuitJson {
    #[serde(rename = "file_name")]
    _file_name: String,
    pis: Vec<u32>,
    pos: Vec<u32>,
    nodes: Vec<NodeJson>,
}

#[derive(Deserialize)]
struct NodeJson {
    id: u32,
    fanin: Vec<Vec<u32>>,
    fanout: Vec<FanoutJson>,
    level: u32,
    suport: Vec<u32>,
}

#[derive(Deserialize)]
struct FanoutJson {
    input: Vec<usize>,
    invert: Vec<u32>,
    op: String,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Op {
    And,
    Or,
    Xor,
    Majority,
    Wire,
}

#[derive(Debug)]
pub struct FanoutEntry {
    pub input_indices: Vec<usize>,
    pub invert: Vec<bool>,
    pub op: Op,
}

#[derive(Debug)]
pub struct Gate {
    pub id: u32,
    pub fanin: Vec<(u32, u32)>,
    pub fanout: Vec<FanoutEntry>,
    pub support: Vec<u32>,
}

pub struct Circuit {
    pub pis: Vec<u32>,
    pub pos: Vec<u32>,
    pub pi_set: HashSet<u32>,
    pub gates: HashMap<u32, Gate>,
    pub max_level: u32,
    pub levels: BTreeMap<u32, Vec<u32>>,
}

pub fn load_circuit(path: &str) -> (Circuit, u64) {
    let data = std::fs::read_to_string(path).expect("Cannot read JSON");
    let circuit_hash = fnv1a_hash(data.as_bytes());
    let cj: CircuitJson = serde_json::from_str(&data).expect("Invalid JSON");

    let pi_set: HashSet<u32> = cj.pis.iter().copied().collect();
    let mut gates: HashMap<u32, Gate> = HashMap::new();
    let mut levels: BTreeMap<u32, Vec<u32>> = BTreeMap::new();
    let mut max_level = 0u32;

    for n in &cj.nodes {
        let fanin: Vec<(u32, u32)> = n.fanin.iter().map(|f| (f[0], f[1])).collect();

        let fanout: Vec<FanoutEntry> = n
            .fanout
            .iter()
            .enumerate()
            .map(|(fo_idx, fo)| {
                let op = match fo.op.as_str() {
                    "&" => Op::And,
                    "|" => Op::Or,
                    "^" => Op::Xor,
                    "M" => Op::Majority,
                    "-" => Op::Wire,
                    other => panic!("Node {}: unknown op '{}' in fanout[{}]", n.id, other, fo_idx),
                };

                assert_eq!(
                    fo.input.len(),
                    fo.invert.len(),
                    "Node {}, fanout[{}]: input and invert must have same length",
                    n.id,
                    fo_idx
                );

                for &idx in &fo.input {
                    assert!(
                        idx < fanin.len(),
                        "Node {}, fanout[{}]: input index {} >= fanin len {}",
                        n.id,
                        fo_idx,
                        idx,
                        fanin.len()
                    );
                }

                if op == Op::Wire {
                    assert_eq!(
                        fo.input.len(),
                        1,
                        "Node {}, fanout[{}]: Wire requires exactly 1 input",
                        n.id,
                        fo_idx
                    );
                }

                if op == Op::Majority {
                    assert!(
                        fo.input.len() % 2 == 1,
                        "Node {}, fanout[{}]: Majority requires odd number of inputs, got {}",
                        n.id,
                        fo_idx,
                        fo.input.len()
                    );
                }

                FanoutEntry {
                    input_indices: fo.input.clone(),
                    invert: fo.invert.iter().map(|&v| v != 0).collect(),
                    op,
                }
            })
            .collect();

        let mut sup = n.suport.clone();
        sup.sort();

        gates.insert(
            n.id,
            Gate {
                id: n.id,
                fanin,
                fanout,
                support: sup,
            },
        );

        levels.entry(n.level).or_default().push(n.id);
        if n.level > max_level {
            max_level = n.level;
        }
    }

    (
        Circuit {
            pis: cj.pis,
            pos: cj.pos,
            pi_set,
            gates,
            max_level,
            levels,
        },
        circuit_hash,
    )
}

fn fnv1a_hash(data: &[u8]) -> u64 {
    let mut h = 14695981039346656037u64;
    for &b in data {
        h ^= b as u64;
        h = h.wrapping_mul(1099511628211);
    }
    h
}
