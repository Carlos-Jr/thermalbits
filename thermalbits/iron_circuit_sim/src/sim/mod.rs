//! Objetivo: agrupar os motores de simulacao e seus utilitarios compartilhados.
//! Entradas: `Circuit` inteiro e parametros de execucao dos modos full/chunk.
//! Saidas: vetores de `GateResult` produzidos para todas as gates do circuito.

pub mod chunk;
pub mod full;
pub mod shared;
