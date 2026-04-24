//! Objetivo: expor o nucleo do transform EO/DO para uso via binario e por outros consumidores.
//! Entradas: overviews em JSON carregados pelo main e politicas escolhidas na CLI.
//! Saidas: funcoes reutilizaveis de (de)serializacao e aplicacao do metodo.

pub mod model;
pub mod transform;

pub use model::{FanoutEntry, Node, Overview};
pub use transform::{apply, Policy};
