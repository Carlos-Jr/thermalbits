//! Objetivo: definir o schema do overview ThermalBits para o transform EO/DO em Rust.
//! Entradas: JSON do overview (file_name, pis, pos, nodes) produzido pelo modulo Python.
//! Saidas: structs tipadas `Overview`, `Node` e `FanoutEntry` com (de)serializacao preservando chaves.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Overview {
    pub file_name: String,
    pub pis: Vec<u32>,
    pub pos: Vec<u32>,
    pub nodes: Vec<Node>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Node {
    pub id: u32,
    pub fanin: Vec<[u32; 2]>,
    pub fanout: Vec<FanoutEntry>,
    pub level: u32,
    pub suport: Vec<u32>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FanoutEntry {
    pub input: Vec<usize>,
    pub invert: Vec<u8>,
    pub op: String,
}

pub const WIRE_OP: &str = "-";
pub const SUPPORTED_OPS: &[&str] = &["&", "|", "^", "M", "-"];
