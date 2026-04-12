//! Objetivo: agrupar os motores de simulacao e seus utilitarios compartilhados.
//! Entradas: `Circuit` inteiro e parametros de execucao dos modos full/chunk.
//! Saidas: vetores de `NodeResult` produzidos para todas as nodes do circuito.

pub mod chunk;
pub mod full;
pub mod shared;
